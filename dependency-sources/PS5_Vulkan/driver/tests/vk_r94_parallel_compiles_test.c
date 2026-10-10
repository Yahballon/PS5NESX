/*
 * PS5 Vulkan driver - R94 test: pipelines compiled on several threads at once.
 *
 * Copyright (C) 2026 Mihawk-99
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Vulkan lets an application create pipelines from as many threads as it
 * likes, and emulators with asynchronous shader compilation do exactly that
 * (Dolphin's ubershader compile threads, PPSSPP's pipeline workers). The
 * driver compiled every pipeline under one global lock, so those threads took
 * turns and a draw linking its pipeline waited behind them (R94). Here four
 * threads create compute pipelines from two different shaders at the same
 * time, and every one must succeed; the direct build then checks that each
 * pipeline's compiled code is byte for byte what a compile on one thread
 * produced, so no compile saw another's state, and says how long the parallel
 * batch took against the same number of compiles one at a time.
 */

#define _POSIX_C_SOURCE 200809L /* clock_gettime under -std=c11 */

#include "ps5vk_test.h"

#include <pthread.h>
#include <stdlib.h>
#include <time.h>

#define THREADS 4u
#define PER_THREAD 6u

/* The shaders are read from the PC's probe directory, so the test runs on the
 * PC; the PS5 build links it and stops. */
#if defined(__linux__)
static VkInstance g_instance;
static VkDevice g_device;
static VkPipelineLayout g_layout;
static VkShaderModule g_modules[2];

struct worker {
   unsigned index;
   VkPipeline pipelines[PER_THREAD];
   unsigned failures;
};

static VkResult
create_pipeline(VkShaderModule module, VkPipeline *pipeline)
{
   const VkComputePipelineCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
      .stage =
         {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_COMPUTE_BIT,
            .module = module,
            .pName = "main",
         },
      .layout = g_layout,
   };
   *pipeline = VK_NULL_HANDLE;
   return VK_FUNCTION(g_instance, CreateComputePipelines)(g_device, VK_NULL_HANDLE, 1, &info,
                                                          NULL, pipeline);
}

static void *
worker_run(void *opaque)
{
   struct worker *const worker = opaque;
   for (unsigned at = 0; at < PER_THREAD; at++)
      if (create_pipeline(g_modules[(worker->index + at) & 1u], &worker->pipelines[at]) !=
          VK_SUCCESS)
         worker->failures++;
   return NULL;
}

static double
now_ms(void)
{
   struct timespec now;
   clock_gettime(CLOCK_MONOTONIC, &now);
   return (double)now.tv_sec * 1e3 + (double)now.tv_nsec / 1e6;
}

static uint32_t *
read_spirv(const char *probes, const char *file, size_t *bytes)
{
   char path[1024];
   snprintf(path, sizeof(path), "%s/%s", probes, file);
   FILE *const stream = fopen(path, "rb");
   if (!stream)
      return NULL;
   fseek(stream, 0, SEEK_END);
   const long length = ftell(stream);
   fseek(stream, 0, SEEK_SET);
   uint32_t *const words = length > 0 ? malloc((size_t)length) : NULL;
   const bool read = words && fread(words, 1, (size_t)length, stream) == (size_t)length;
   fclose(stream);
   if (!read) {
      free(words);
      return NULL;
   }
   *bytes = (size_t)length;
   return words;
}

#ifdef PS5VK_TEST_DIRECT
/* The stage mappings the device lists, oldest first, copied out. */
static uint32_t
stage_snapshot(ps5vk_debug_stage *stages, uint32_t capacity)
{
   return ps5vk_debug_pipeline_stages(g_device, stages, capacity);
}

static bool
same_stage(const ps5vk_debug_stage *a, const ps5vk_debug_stage *b)
{
   return a->bytes == b->bytes && memcmp(a->address, b->address, a->bytes) == 0;
}
#endif
#endif /* __linux__ */

int
main(void)
{
   test_begin("r94 parallel compiles");
#if !defined(__linux__)
   /* The PS5 build links the test; the shaders are read from the PC's probe
    * directory, so the run is the PC's. */
   return test_finish();
#else
   const char *const probes = getenv("PS5VK_PROBES");
   size_t sizes[2] = {0, 0};
   uint32_t *const words[2] = {
      probes ? read_spirv(probes, "c0/dispatch.spv", &sizes[0]) : NULL,
      probes ? read_spirv(probes, "r84-subgroup/dispatch.spv", &sizes[1]) : NULL,
   };
   check(words[0] && words[1], "two compute shaders from the probe directory");
   if (!words[0] || !words[1])
      return test_finish();

   VkPhysicalDevice physical;
   if (!test_create_device(&g_instance, &physical, &g_device))
      return test_finish();

   const VkDescriptorSetLayoutBinding binding = {
      .binding = 0,
      .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
      .descriptorCount = 1,
      .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT,
   };
   const VkDescriptorSetLayoutCreateInfo set_info = {
      .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
      .bindingCount = 1,
      .pBindings = &binding,
   };
   VkDescriptorSetLayout set_layout = VK_NULL_HANDLE;
   VkResult result =
      VK_FUNCTION(g_instance, CreateDescriptorSetLayout)(g_device, &set_info, NULL, &set_layout);
   const VkPipelineLayoutCreateInfo layout_info = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
      .setLayoutCount = 1,
      .pSetLayouts = &set_layout,
   };
   if (result == VK_SUCCESS)
      result = VK_FUNCTION(g_instance, CreatePipelineLayout)(g_device, &layout_info, NULL, &g_layout);
   for (unsigned m = 0; m < 2 && result == VK_SUCCESS; m++) {
      const VkShaderModuleCreateInfo module_info = {
         .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
         .codeSize = sizes[m],
         .pCode = words[m],
      };
      result = VK_FUNCTION(g_instance, CreateShaderModule)(g_device, &module_info, NULL,
                                                           &g_modules[m]);
   }
   check(result == VK_SUCCESS, "a pipeline layout and two shader modules");
   if (result != VK_SUCCESS)
      return test_finish();

   /* One pipeline of each shader, compiled alone: the code every parallel
    * compile has to reproduce. */
   VkPipeline serial[2] = {VK_NULL_HANDLE, VK_NULL_HANDLE};
   const double serial_start = now_ms();
   const bool serial_ok = create_pipeline(g_modules[0], &serial[0]) == VK_SUCCESS &&
                          create_pipeline(g_modules[1], &serial[1]) == VK_SUCCESS;
   const double serial_ms = now_ms() - serial_start;
   check(serial_ok, "each shader compiles on one thread");

   static struct worker workers[THREADS];
   pthread_t threads[THREADS];
   unsigned started = 0;
   const double parallel_start = now_ms();
   for (unsigned at = 0; at < THREADS; at++) {
      workers[at].index = at;
      started += pthread_create(&threads[at], NULL, worker_run, &workers[at]) == 0;
   }
   unsigned failures = 0;
   for (unsigned at = 0; at < started; at++) {
      pthread_join(threads[at], NULL);
      failures += workers[at].failures;
   }
   const double parallel_ms = now_ms() - parallel_start;
   check(started == THREADS && failures == 0,
         "four threads create twenty-four compute pipelines at once, all successfully");
   printf("  (two compiles alone: %.1f ms; %u at once on %u threads: %.1f ms, %.1f ms each "
          "against %.1f ms alone)\n",
          serial_ms, THREADS * PER_THREAD, THREADS, parallel_ms,
          parallel_ms / (THREADS * PER_THREAD), serial_ms / 2.0);

#ifdef PS5VK_TEST_DIRECT
   enum { CAPACITY = 2 + THREADS * PER_THREAD };
   static ps5vk_debug_stage stages[CAPACITY];
   const uint32_t count = stage_snapshot(stages, CAPACITY);
   check(count == CAPACITY, "the device lists every pipeline's compiled code");
   /* The first two, in creation order, are the serial ones. */
   unsigned matched = 0;
   for (uint32_t at = 2; at < count && at < CAPACITY; at++)
      matched += same_stage(&stages[at], &stages[0]) || same_stage(&stages[at], &stages[1]);
   check(matched == THREADS * PER_THREAD,
         "every parallel compile's code is byte for byte a serial compile's");
#endif

   for (unsigned at = 0; at < started; at++)
      for (unsigned p = 0; p < PER_THREAD; p++)
         VK_FUNCTION(g_instance, DestroyPipeline)(g_device, workers[at].pipelines[p], NULL);
   for (unsigned p = 0; p < 2; p++) {
      VK_FUNCTION(g_instance, DestroyPipeline)(g_device, serial[p], NULL);
      VK_FUNCTION(g_instance, DestroyShaderModule)(g_device, g_modules[p], NULL);
   }
   VK_FUNCTION(g_instance, DestroyPipelineLayout)(g_device, g_layout, NULL);
   VK_FUNCTION(g_instance, DestroyDescriptorSetLayout)(g_device, set_layout, NULL);
   test_destroy_device(g_instance, g_device);
   free(words[0]);
   free(words[1]);
   return test_finish();
#endif
}
