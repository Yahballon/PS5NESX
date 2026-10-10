/*
 * PS5 Vulkan driver - R95 test: uploads into tiled images land where the map
 * says.
 *
 * Copyright (C) 2026 Mihawk-99
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * An upload into a tiled image (vkCmdCopyBufferToImage into an attachment) is
 * written by the CPU at a submission split point, and since R95 a run of texels
 * at a time rather than one texel: the run is the span the image's map keeps
 * contiguous. This test uploads regions whose edges are not aligned to a run,
 * or to a tile, into images of each texel size, and checks every texel of each
 * region at the offset the driver's own map gives for it
 * (ps5vk_debug_image_texel_offset, R91), and that a texel just outside a region
 * was not written. Direct build only: it reads the image's storage through the
 * driver's debug API.
 */

#include "ps5vk_test.h"

#include <stdlib.h>

#define WIDTH 300u
#define HEIGHT 200u

static VkInstance g_instance;
static VkDevice g_device;

#ifdef PS5VK_TEST_DIRECT
static uint8_t
pattern(uint32_t region, uint32_t x, uint32_t y, uint32_t byte)
{
   return (uint8_t)(x * 7u + y * 13u + byte * 31u + region * 101u + 1u);
}

struct upload {
   VkOffset2D offset;
   VkExtent2D extent;
};

/* One format: an image of WIDTH x HEIGHT, the regions uploaded in turn, each
 * checked texel by texel. */
static void
check_format(VkQueue queue, VkCommandPool pool, VkFormat format, uint32_t texel_bytes,
             const char *name)
{
   const VkImageCreateInfo image_info = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
      .imageType = VK_IMAGE_TYPE_2D,
      .format = format,
      .extent = {WIDTH, HEIGHT, 1},
      .mipLevels = 1,
      .arrayLayers = 1,
      .samples = VK_SAMPLE_COUNT_1_BIT,
      .tiling = VK_IMAGE_TILING_OPTIMAL,
      .usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT |
               VK_IMAGE_USAGE_SAMPLED_BIT,
      .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
   };
   VkImage image = VK_NULL_HANDLE;
   if (VK_FUNCTION(g_instance, CreateImage)(g_device, &image_info, NULL, &image) != VK_SUCCESS) {
      printf("  (%s: not an attachment format here; skipped)\n", name);
      return;
   }
   VkMemoryRequirements image_needs;
   VK_FUNCTION(g_instance, GetImageMemoryRequirements)(g_device, image, &image_needs);
   const VkMemoryAllocateInfo image_memory_info = {
      .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = image_needs.size,
      .memoryTypeIndex = PS5VK_TEST_HOST_MEMORY_TYPE,
   };
   VkDeviceMemory image_memory = VK_NULL_HANDLE;
   const uint64_t buffer_bytes = (uint64_t)WIDTH * HEIGHT * texel_bytes;
   const VkBufferCreateInfo buffer_info = {
      .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
      .size = buffer_bytes,
      .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
      .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
   };
   VkBuffer buffer = VK_NULL_HANDLE;
   VkDeviceMemory buffer_memory = VK_NULL_HANDLE;
   void *mapped = NULL;
   VkMemoryRequirements buffer_needs = {0};
   bool ready =
      VK_FUNCTION(g_instance, AllocateMemory)(g_device, &image_memory_info, NULL, &image_memory) ==
         VK_SUCCESS &&
      VK_FUNCTION(g_instance, BindImageMemory)(g_device, image, image_memory, 0) == VK_SUCCESS &&
      VK_FUNCTION(g_instance, CreateBuffer)(g_device, &buffer_info, NULL, &buffer) == VK_SUCCESS;
   if (ready) {
      VK_FUNCTION(g_instance, GetBufferMemoryRequirements)(g_device, buffer, &buffer_needs);
      const VkMemoryAllocateInfo buffer_memory_info = {
         .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
         .allocationSize = buffer_needs.size,
         .memoryTypeIndex = PS5VK_TEST_HOST_MEMORY_TYPE,
      };
      ready = VK_FUNCTION(g_instance, AllocateMemory)(g_device, &buffer_memory_info, NULL,
                                                      &buffer_memory) == VK_SUCCESS &&
              VK_FUNCTION(g_instance, BindBufferMemory)(g_device, buffer, buffer_memory, 0) ==
                 VK_SUCCESS &&
              VK_FUNCTION(g_instance, MapMemory)(g_device, buffer_memory, 0, VK_WHOLE_SIZE, 0,
                                                 &mapped) == VK_SUCCESS;
   }
   size_t storage_bytes = 0;
   uint8_t *const storage = ready ? ps5vk_debug_image_storage(image, &storage_bytes) : NULL;
   char what[160];
   snprintf(what, sizeof(what), "%s: an attachment image, its storage and a staging buffer", name);
   check(ready && storage != NULL, what);
   if (!ready || storage == NULL)
      goto done;

   /* Edges off every run and tile boundary: the whole image, a region from
    * (3, 5), one texel, and a region across the first tile's right edge. */
   static const struct upload uploads[] = {
      {{0, 0}, {WIDTH, HEIGHT}},
      {{3, 5}, {123, 77}},
      {{1, 1}, {1, 1}},
      {{125, 126}, {9, 7}},
   };
   unsigned wrong = 0, spilled = 0;
   for (uint32_t u = 0; u < sizeof(uploads) / sizeof(uploads[0]); u++) {
      const struct upload *const up = &uploads[u];
      uint8_t *const bytes = mapped;
      for (uint32_t y = 0; y < up->extent.height; y++)
         for (uint32_t x = 0; x < up->extent.width; x++)
            for (uint32_t b = 0; b < texel_bytes; b++)
               bytes[((uint64_t)y * up->extent.width + x) * texel_bytes + b] =
                  pattern(u, x, y, b);
      /* What lies just past the region's right edge, which must not change. */
      const uint32_t outside_x = (uint32_t)up->offset.x + up->extent.width;
      uint8_t before[16] = {0};
      uint64_t outside_offset = 0;
      const bool has_outside =
         outside_x < WIDTH &&
         ps5vk_debug_image_texel_offset(image, outside_x, (uint32_t)up->offset.y,
                                        &outside_offset);
      if (has_outside)
         memcpy(before, storage + outside_offset, texel_bytes);

      const VkCommandBufferAllocateInfo allocate = {
         .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
         .commandPool = pool,
         .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
         .commandBufferCount = 1,
      };
      VkCommandBuffer commands = VK_NULL_HANDLE;
      const VkCommandBufferBeginInfo begin = {
         .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
         .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
      };
      const VkBufferImageCopy region = {
         .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
         .imageOffset = {up->offset.x, up->offset.y, 0},
         .imageExtent = {up->extent.width, up->extent.height, 1},
      };
      VkFence fence = VK_NULL_HANDLE;
      const VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
      bool done_ok =
         VK_FUNCTION(g_instance, AllocateCommandBuffers)(g_device, &allocate, &commands) ==
            VK_SUCCESS &&
         VK_FUNCTION(g_instance, BeginCommandBuffer)(commands, &begin) == VK_SUCCESS;
      if (done_ok) {
         VK_FUNCTION(g_instance, CmdCopyBufferToImage)(commands, buffer, image,
                                                       VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1,
                                                       &region);
         const VkSubmitInfo submit = {
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1,
            .pCommandBuffers = &commands,
         };
         done_ok =
            VK_FUNCTION(g_instance, EndCommandBuffer)(commands) == VK_SUCCESS &&
            VK_FUNCTION(g_instance, CreateFence)(g_device, &fence_info, NULL, &fence) ==
               VK_SUCCESS &&
            VK_FUNCTION(g_instance, QueueSubmit)(queue, 1, &submit, fence) == VK_SUCCESS &&
            VK_FUNCTION(g_instance, WaitForFences)(g_device, 1, &fence, VK_TRUE,
                                                   UINT64_C(5000000000)) == VK_SUCCESS;
      }
      if (fence != VK_NULL_HANDLE)
         VK_FUNCTION(g_instance, DestroyFence)(g_device, fence, NULL);
      if (commands != VK_NULL_HANDLE)
         VK_FUNCTION(g_instance, FreeCommandBuffers)(g_device, pool, 1, &commands);
      if (!done_ok) {
         wrong++;
         continue;
      }
      for (uint32_t y = 0; y < up->extent.height; y++)
         for (uint32_t x = 0; x < up->extent.width; x++) {
            uint64_t offset = 0;
            if (!ps5vk_debug_image_texel_offset(image, (uint32_t)up->offset.x + x,
                                                (uint32_t)up->offset.y + y, &offset) ||
                offset + texel_bytes > storage_bytes) {
               wrong++;
               continue;
            }
            for (uint32_t b = 0; b < texel_bytes; b++)
               wrong += storage[offset + b] != pattern(u, x, y, b);
         }
      if (has_outside)
         spilled += memcmp(before, storage + outside_offset, texel_bytes) != 0;
   }
   snprintf(what, sizeof(what), "%s: every texel of four uploads is where the map puts it",
            name);
   check(wrong == 0, what);
   snprintf(what, sizeof(what), "%s: no upload wrote the texel past its region", name);
   check(spilled == 0, what);
   if (wrong != 0)
      printf("  (%s: %u wrong bytes)\n", name, wrong);

done:
   if (mapped)
      VK_FUNCTION(g_instance, UnmapMemory)(g_device, buffer_memory);
   VK_FUNCTION(g_instance, DestroyBuffer)(g_device, buffer, NULL);
   VK_FUNCTION(g_instance, FreeMemory)(g_device, buffer_memory, NULL);
   VK_FUNCTION(g_instance, DestroyImage)(g_device, image, NULL);
   VK_FUNCTION(g_instance, FreeMemory)(g_device, image_memory, NULL);
}
#endif

int
main(void)
{
   test_begin("r95 tiled upload");
#ifdef PS5VK_TEST_DIRECT
   VkPhysicalDevice physical;
   if (!test_create_device(&g_instance, &physical, &g_device))
      return test_finish();
   VkQueue queue = VK_NULL_HANDLE;
   VK_FUNCTION(g_instance, GetDeviceQueue)(g_device, 0, 0, &queue);
   const VkCommandPoolCreateInfo pool_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
      .queueFamilyIndex = 0,
   };
   VkCommandPool pool = VK_NULL_HANDLE;
   check(queue != VK_NULL_HANDLE && VK_FUNCTION(g_instance, CreateCommandPool)(
                                        g_device, &pool_info, NULL, &pool) == VK_SUCCESS,
         "a queue and a command pool");
   check_format(queue, pool, VK_FORMAT_R8_UNORM, 1, "R8_UNORM");
   check_format(queue, pool, VK_FORMAT_R8G8_UNORM, 2, "R8G8_UNORM");
   check_format(queue, pool, VK_FORMAT_R8G8B8A8_UNORM, 4, "R8G8B8A8_UNORM");
   check_format(queue, pool, VK_FORMAT_R16G16B16A16_UNORM, 8, "R16G16B16A16_UNORM");
   check_format(queue, pool, VK_FORMAT_R32G32B32A32_UINT, 16, "R32G32B32A32_UINT");
   VK_FUNCTION(g_instance, DestroyCommandPool)(g_device, pool, NULL);
   test_destroy_device(g_instance, g_device);
#else
   (void)g_instance;
   (void)g_device;
#endif
   return test_finish();
}
