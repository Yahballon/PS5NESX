#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-only actual compute sampler validation/encoding; no native submission."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MESA = ROOT / "third_party/mesa-26.2.0"
source = (ROOT / "src/gallium/ps5/ps5_screen.c").read_text()


def extract(name):
    at = source.index("\n" + name + "(")
    start = source.rfind("\nstatic ", 0, at) + 1
    return source[start:source.index("\n}\n", at) + 3]


code = r'''
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "pipe/p_state.h"
#define PS5_ENABLE_BORDER_COLOR_CANDIDATE 1
#define PS5_COMPUTE_TEXTURE_SLOTS 16
/* Only the fields touched by the extracted callback are modeled. */
struct pipe_context { unsigned unused; };
struct ps5_sampler_state { struct pipe_sampler_state base; };
struct ps5_context {
    struct pipe_context base;
    uint32_t compute_samplers[16][4];
    unsigned compute_sampler_mask;
    bool compute_samplers_invalid;
};
''' + "\n".join(extract(name) for name in (
    "ps5_float_bits", "ps5_float_is_finite", "ps5_texture_descriptor_wrap",
    "ps5_texture_descriptor_anisotropy", "ps5_texture_descriptor_filter",
    "ps5_texture_descriptor_mip_filter",
    "ps5_texture_descriptor_unsigned_lod", "ps5_texture_descriptor_lod_bias",
    "ps5_set_compute_sampler_states",
)) + r'''
int main(void)
{
    struct ps5_context c = {0};
    struct ps5_sampler_state sampler = {.base = {
        .wrap_s = PIPE_TEX_WRAP_REPEAT, .wrap_t = PIPE_TEX_WRAP_REPEAT,
        .wrap_r = PIPE_TEX_WRAP_REPEAT, .min_img_filter = PIPE_TEX_FILTER_NEAREST,
        .mag_img_filter = PIPE_TEX_FILTER_NEAREST, .min_mip_filter = PIPE_TEX_MIPFILTER_NONE,
    }};
    void *states[2] = {&sampler, &sampler};
    const struct { float min, max; uint32_t encoded; } valid[] = {
        {0, 1000, 0x00f00000}, /* Actual Mesa default: GL min -1000 -> pipe min 0. */
        {0, 16, 0x00f00000}, {0, FLT_MAX, 0x00f00000},
        {0, 0, 0}, {-0.0f, 0, 0}, {15, 15, 0x00f00f00},
        {16, 1000, 0x00f00f00}, {FLT_MAX, FLT_MAX, 0x00f00f00},
        {1.5f, 3.25f, 0x00340180}, {0, 1.0f / 512.0f, 0},
        {0, 1.0f / 256.0f, 0x00001000}, {14.5f, 1000, 0x00f00e80},
    };
    for (unsigned i = 0; i < sizeof(valid) / sizeof(valid[0]); ++i) {
        sampler.base.min_lod = valid[i].min;
        sampler.base.max_lod = valid[i].max;
        struct pipe_sampler_state before = sampler.base;
        ps5_set_compute_sampler_states(&c.base, 7, 1, states);
        assert(!c.compute_samplers_invalid && c.compute_sampler_mask == (1u << 7));
        assert(c.compute_samplers[7][1] == valid[i].encoded);
        assert(!memcmp(&before, &sampler.base, sizeof(before))); /* Borrowed state unchanged. */
    }
    sampler.base.min_lod = 0;
    sampler.base.max_lod = 1000;
    /* Clamp-to-edge and rectangle-coordinate normalization are supported. */
    sampler.base.wrap_t = PIPE_TEX_WRAP_CLAMP_TO_EDGE;
    sampler.base.unnormalized_coords = 1;
    ps5_set_compute_sampler_states(&c.base, 7, 1, states);
    assert(!c.compute_samplers_invalid && c.compute_sampler_mask == (1u << 7));
    sampler.base.wrap_t = PIPE_TEX_WRAP_REPEAT;
    sampler.base.unnormalized_coords = 0;
    struct ps5_sampler_state bad = sampler;
    states[1] = &bad;
    const float invalid[][2] = {
        {-1, 1000}, {0, -1}, {2, 1}, {1000, 16},
        {NAN, 1000}, {0, NAN}, {INFINITY, INFINITY},
        {0, INFINITY}, {-INFINITY, 1000}, {0, -INFINITY},
    };
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]) + 4; ++i) {
        bad = sampler;
        if (i < sizeof(invalid) / sizeof(invalid[0])) {
            bad.base.min_lod = invalid[i][0];
            bad.base.max_lod = invalid[i][1];
        } else {
            switch (i - sizeof(invalid) / sizeof(invalid[0])) {
            case 0: bad.base.lod_bias = 1; break;
            case 1: bad.base.lod_bias = NAN; break;
            case 2: bad.base.lod_bias = INFINITY; break;
            case 3: bad.base.max_anisotropy = 17; break;
            }
        }
        uint32_t saved[16][4];
        memcpy(saved, c.compute_samplers, sizeof(saved));
        ps5_set_compute_sampler_states(&c.base, 7, 2, states);
        assert(c.compute_samplers_invalid && c.compute_sampler_mask == (1u << 7));
        assert(!memcmp(saved, c.compute_samplers, sizeof(saved))); /* No partial update. */
    }
    ps5_set_compute_sampler_states(&c.base, 7, 1, states);
    assert(!c.compute_samplers_invalid && c.compute_samplers[7][1] == 0x00f00000);
    states[0] = NULL;
    ps5_set_compute_sampler_states(&c.base, 7, 1, states);
    assert(!c.compute_samplers_invalid && !c.compute_sampler_mask);
    for (unsigned i = 0; i < 4; ++i) assert(!c.compute_samplers[7][i]);
    return 0;
}
'''

with tempfile.TemporaryDirectory() as directory:
    formats = Path(directory) / "util/format"
    formats.mkdir(parents=True)
    with (formats / "u_format_gen.h").open("w") as generated:
        subprocess.run([sys.executable, str(MESA / "src/util/format/u_format_table.py"),
                        str(MESA / "src/util/format/u_format.yaml"), "--enums"],
                       stdout=generated, check=True, timeout=30)
    executable = str(Path(directory) / "compute-sampler-lod")
    subprocess.run(["clang-18", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined,float-cast-overflow", "-fno-sanitize-recover=all",
                    "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-D_GNU_SOURCE",
                    "-I", str(MESA / "include"), "-I", str(MESA / "src"),
                    "-I", str(MESA / "src/gallium/include"), "-I", directory,
                    "-x", "c", "-o", executable, "-"],
                   input=code, text=True, check=True, timeout=30)
    subprocess.run([executable], check=True, timeout=10)
print("PASS: actual compute sampler finite LOD saturation, encoding, rejection, atomic update and unbind")
