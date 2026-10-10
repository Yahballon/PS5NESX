#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check real target/staging policy; transfers are covered by existing tests."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'src/gallium/ps5/ps5_screen.c').read_text()
def function(name):
    start = source.index('static bool\n' + name + '(')
    return source[start:source.index('\n}', start) + 2]

code = r'''
#include <assert.h>
#include <stdbool.h>
#define PS5_ENABLE_TEXTURE_1D_CANDIDATE 1
#define PS5_ENABLE_TEXTURE_CUBE_ARRAY_CANDIDATE 1
#define PS5_ENABLE_LAYERED_RENDER_TARGET_CANDIDATE 1
#define PS5_ENABLE_RENDER_TO_TEXTURE_CANDIDATE 1
enum pipe_texture_target { PIPE_BUFFER, PIPE_TEXTURE_1D, PIPE_TEXTURE_1D_ARRAY,
 PIPE_TEXTURE_2D, PIPE_TEXTURE_RECT, PIPE_TEXTURE_2D_ARRAY, PIPE_TEXTURE_CUBE,
 PIPE_TEXTURE_CUBE_ARRAY, PIPE_TEXTURE_3D };
enum { PIPE_FORMAT_Z32_FLOAT, PIPE_FORMAT_Z32_FLOAT_S8X24_UINT, COLOR };
enum { PIPE_BIND_RENDER_TARGET=1, PIPE_BIND_DEPTH_STENCIL=2 };
struct pipe_resource { unsigned target, bind, format, last_level; };
static bool ps5_linear_sampled_layout(const struct pipe_resource *r)
{ return r->target == PIPE_TEXTURE_RECT; }
''' + '\n'.join(function(name) for name in (
    'ps5_cube_texture_target', 'ps5_color_render_target', 'ps5_depth_render_target',
    'ps5_render_staging_required', 'ps5_depth_staging_required')) + r'''
int main(void) {
 assert(ps5_color_render_target(PIPE_TEXTURE_RECT)==PS5_ENABLE_TEXTURE_RECTANGLE_CANDIDATE);
 assert(ps5_depth_render_target(PIPE_TEXTURE_RECT)==PS5_ENABLE_TEXTURE_RECTANGLE_CANDIDATE);
 assert(ps5_color_render_target(PIPE_TEXTURE_2D));
 assert(ps5_depth_render_target(PIPE_TEXTURE_2D));
 assert(!ps5_color_render_target(PIPE_BUFFER));
 assert(!ps5_depth_render_target(PIPE_BUFFER));
 struct pipe_resource r={PIPE_TEXTURE_RECT,PIPE_BIND_RENDER_TARGET,COLOR,0};
 assert(ps5_render_staging_required(&r)==PS5_ENABLE_TEXTURE_RECTANGLE_CANDIDATE);
 r.bind=PIPE_BIND_DEPTH_STENCIL;
 for(unsigned f=PIPE_FORMAT_Z32_FLOAT;f<=PIPE_FORMAT_Z32_FLOAT_S8X24_UINT;f++) {
   r.format=f;
   assert(ps5_depth_staging_required(&r)==PS5_ENABLE_TEXTURE_RECTANGLE_CANDIDATE);
 }
 r.bind=0; assert(!ps5_depth_staging_required(&r));
 r.target=PIPE_TEXTURE_2D; r.bind=PIPE_BIND_DEPTH_STENCIL;
 assert(!ps5_depth_staging_required(&r));
 r.last_level=1; assert(ps5_depth_staging_required(&r));
}
'''
with tempfile.TemporaryDirectory() as directory:
    for enabled in (0, 1):
        exe = str(Path(directory) / 'check')
        subprocess.run(['clang-18', '-x', 'c', '-std=c11', '-Wall', '-Werror',
                        f'-DPS5_ENABLE_TEXTURE_RECTANGLE_CANDIDATE={enabled}',
                        '-o', exe, '-'], input=code, text=True, check=True)
        subprocess.run([exe], check=True)
print('PASS: rectangle color/depth staging, feature gate and 2D controls')
