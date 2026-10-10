// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef PS5_AGC_PACKAGE_H
#define PS5_AGC_PACKAGE_H

#include <stddef.h>
#include <stdint.h>

#include "psbc_compile.h"

/* Returns -7 for unqualified flat scratch. */
int ps5_agc_package_build(const PsbcShaderOutput *shader,
                          uint32_t esgs_ring_itemsize,
                          uint8_t **package, size_t *package_size);

struct pipe_screen;
struct pipe_resource;
struct ps5_agc_compute_memory_layout {
   size_t allocation_size;
   size_t private_offset;
   size_t private_size;
   size_t scratch_offset;
   size_t scratch_size;
};
/* Checked arena plan. Nonzero private stride describes ordinary
 * per-invocation storage; nonzero scratch bytes describe MUBUF ACO spills.
 * budget includes code, commands, alignment and two 16 KiB outer guards. */
int ps5_agc_compute_plan_memory(size_t code_size, uint32_t private_stride,
                                uint32_t scratch_bytes_per_wave,
                                const uint32_t local[3], const uint32_t groups[3],
                                size_t budget, struct ps5_agc_compute_memory_layout *out);
#define PS5_AGC_COMPUTE_SCRATCH_WAVES 1152u
#define PS5_AGC_COMPUTE_MAX_TEXTURES 16u
#define PS5_AGC_COMPUTE_MAX_IMAGES 16u
#define PS5_AGC_COMPUTE_MAX_RESOURCES \
   (32u + 15u + PS5_AGC_COMPUTE_MAX_IMAGES + PS5_AGC_COMPUTE_MAX_TEXTURES)
/* Internal bring-up path, not a public GL compute capability. All resources
 * must remain owned and unchanged until this synchronous call returns.
 * Raw UBO/SSBO and validated mip/layer image views; unbound slots are zero. */
int ps5_agc_compute_execute(struct pipe_screen *screen,
                            const PsbcShaderOutput *shader,
                            struct pipe_resource *descriptors,
                            struct pipe_resource *const *buffers,
                            unsigned buffer_count, const uint32_t groups[3]);

#endif
