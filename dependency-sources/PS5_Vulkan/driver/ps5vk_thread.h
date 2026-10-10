/*
 * PS5 Vulkan driver - the threads the driver starts for itself.
 * Copyright (C) 2026 Mihawk-99
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef PS5VK_THREAD_H
#define PS5VK_THREAD_H

#include <pthread.h>

/* The stack a thread the driver starts for itself runs on (the shader-cache
 * writer, the blit workers). A thread created with no attributes gets 64 KiB
 * on this console (the payload SDK fork's thread probe); the driver's threads
 * ask for their stack rather than inherit that. The shader compiler has its
 * own, larger one (PS5VK_COMPILE_STACK_BYTES). */
#define PS5VK_THREAD_STACK_BYTES (256u * 1024u)

static inline int
ps5vk_thread_create(pthread_t *thread, void *(*start)(void *), void *argument)
{
   pthread_attr_t attributes;
   if (pthread_attr_init(&attributes) != 0)
      return pthread_create(thread, NULL, start, argument);
   pthread_attr_setstacksize(&attributes, PS5VK_THREAD_STACK_BYTES);
   const int result = pthread_create(thread, &attributes, start, argument);
   pthread_attr_destroy(&attributes);
   return result;
}

#endif /* PS5VK_THREAD_H */
