/*
 * PS5 Vulkan driver - R93 test: buffers from several threads.
 * Copyright (C) 2026 Mihawk-99
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Vulkan lets an application create and destroy buffers on one device from
 * any number of threads without synchronising the device. The driver keeps
 * the device's live buffers on a list for the runner's capture, and that list
 * was changed without a lock: a tester's PPSSPP run -- the core's threads and
 * the frontend's menu freeing buffers at once -- lost a link and crashed in
 * vkDestroyBuffer following a freed buffer's reused memory. Four threads here
 * each create, bind and destroy buffers, keeping a few alive; the direct
 * build then checks the device's list holds exactly the ones alive, and none
 * once they are destroyed. The unlocked list made this test spin for good --
 * three threads walking a cycle -- so on the PC a watchdog fails it instead.
 */

#include "ps5vk_test.h"

#include <pthread.h>
#if defined(__linux__)
#include <signal.h>
#include <unistd.h>

#define WATCHDOG_SECONDS 120u

static void
watchdog_fired(int signal)
{
   (void)signal;
   static const char line[] = "  FAIL the threads finish within the watchdog's time\n";
   (void)!write(STDOUT_FILENO, line, sizeof(line) - 1);
   _exit(1);
}
#endif

#define THREADS 4u
#define ROUNDS 4000u
#define KEPT 16u
#define BUFFER_BYTES 256u

static VkInstance g_instance;
static VkDevice g_device;
static VkDeviceMemory g_memory;

struct worker {
   VkBuffer kept[KEPT];
   unsigned failures;
};

static void *
worker_run(void *opaque)
{
   struct worker *const worker = opaque;
   const PFN_vkCreateBuffer create = VK_FUNCTION(g_instance, CreateBuffer);
   const PFN_vkBindBufferMemory bind = VK_FUNCTION(g_instance, BindBufferMemory);
   const PFN_vkDestroyBuffer destroy = VK_FUNCTION(g_instance, DestroyBuffer);
   const VkBufferCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
      .size = BUFFER_BYTES,
      .usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
      .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
   };
   for (unsigned round = 0; round < ROUNDS; round++) {
      VkBuffer *const slot = &worker->kept[round % KEPT];
      if (*slot != VK_NULL_HANDLE)
         destroy(g_device, *slot, NULL);
      *slot = VK_NULL_HANDLE;
      if (create(g_device, &info, NULL, slot) != VK_SUCCESS ||
          bind(g_device, *slot, g_memory, 0) != VK_SUCCESS)
         worker->failures++;
   }
   return NULL;
}

#ifdef PS5VK_TEST_DIRECT
static uint32_t
listed_buffers(void)
{
   return ps5vk_debug_buffers(g_device, NULL, 0);
}
#endif

int
main(void)
{
   test_begin("r93 threads");
#if defined(__linux__)
   signal(SIGALRM, watchdog_fired);
   alarm(WATCHDOG_SECONDS);
#endif
   VkPhysicalDevice physical;
   if (!test_create_device(&g_instance, &physical, &g_device))
      return test_finish();

   const VkMemoryAllocateInfo allocation = {
      .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = 65536,
      .memoryTypeIndex = PS5VK_TEST_HOST_MEMORY_TYPE,
   };
   check(VK_FUNCTION(g_instance, AllocateMemory)(g_device, &allocation, NULL, &g_memory) ==
            VK_SUCCESS,
         "one allocation every buffer is bound to");
#ifdef PS5VK_TEST_DIRECT
   const uint32_t before = listed_buffers();
#endif

   static struct worker workers[THREADS];
   pthread_t threads[THREADS];
   unsigned started = 0;
   for (unsigned at = 0; at < THREADS; at++)
      started += pthread_create(&threads[at], NULL, worker_run, &workers[at]) == 0;
   check(started == THREADS, "four threads create, bind and destroy buffers at once");
   unsigned failures = 0;
   for (unsigned at = 0; at < started; at++) {
      pthread_join(threads[at], NULL);
      failures += workers[at].failures;
   }
   check(failures == 0, "every buffer was created and bound");

#ifdef PS5VK_TEST_DIRECT
   check(listed_buffers() == before + started * KEPT,
         "the device lists exactly the buffers still alive");
#endif
   const PFN_vkDestroyBuffer destroy = VK_FUNCTION(g_instance, DestroyBuffer);
   for (unsigned at = 0; at < started; at++)
      for (unsigned slot = 0; slot < KEPT; slot++)
         destroy(g_device, workers[at].kept[slot], NULL);
#ifdef PS5VK_TEST_DIRECT
   check(listed_buffers() == before, "and none of them once they are destroyed");
#endif

   VK_FUNCTION(g_instance, FreeMemory)(g_device, g_memory, NULL);
   test_destroy_device(g_instance, g_device);
   return test_finish();
}
