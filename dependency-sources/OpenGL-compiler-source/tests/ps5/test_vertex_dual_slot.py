#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the real element-state constructor against Mesa's split uint64 layout."""
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = 'src/gallium/ps5/ps5_screen.c'
source = (subprocess.check_output(['git', 'show', '9704521:' + path], cwd=root, text=True)
          if '--baseline' in sys.argv else (root / path).read_text())
start = source.index('static void *\nps5_create_vertex_elements_state(')
function = source[start:source.index('\n}\n', start) + 3]
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define PIPE_MAX_ATTRIBS 32
#define PS5_ENABLE_FP64_CANDIDATE 1
enum { PIPE_FORMAT_R32_FLOAT, PIPE_FORMAT_R32G32_UINT,
       PIPE_FORMAT_R32G32B32A32_UINT, PIPE_FORMAT_R64G64B64_FLOAT,
       PIPE_FORMAT_R64G64B64A64_FLOAT };
struct pipe_context { int unused; };
struct pipe_vertex_element {
   unsigned src_offset, src_stride, instance_divisor, vertex_buffer_index, src_format;
   bool dual_slot;
};
struct ps5_vertex_elements { unsigned count; struct pipe_vertex_element elements[32]; };
''' + function + r'''
int main(void) {
   struct pipe_vertex_element e[5] = {
      {.src_format=PIPE_FORMAT_R32_FLOAT,.src_stride=4},
      {.src_format=PIPE_FORMAT_R32G32B32A32_UINT,.dual_slot=true,
       .src_offset=32,.src_stride=64,.vertex_buffer_index=2,.instance_divisor=3},
      {.src_format=PIPE_FORMAT_R32G32_UINT,.dual_slot=true,
       .src_offset=48,.src_stride=64,.vertex_buffer_index=2,.instance_divisor=3},
      {.src_format=PIPE_FORMAT_R32G32B32A32_UINT,.dual_slot=true,.src_offset=64},
      {.src_format=PIPE_FORMAT_R32G32B32A32_UINT,.dual_slot=true,.src_offset=80}
   };
   struct ps5_vertex_elements *s=ps5_create_vertex_elements_state(NULL,5,e);
   assert(s && s->count==3);
   assert(s->elements[0].src_format==PIPE_FORMAT_R32_FLOAT);
   assert(s->elements[1].src_format==PIPE_FORMAT_R64G64B64_FLOAT);
   assert(s->elements[1].src_offset==32 && s->elements[1].instance_divisor==3);
   assert(s->elements[2].src_format==PIPE_FORMAT_R64G64B64A64_FLOAT);
   assert(s->elements[2].src_stride==0); free(s);
   for(unsigned mismatch=0;mismatch<5;++mismatch) {
      struct pipe_vertex_element bad[2]={e[1],e[2]};
      if(mismatch==0) bad[1].src_offset++;
      if(mismatch==1) bad[1].src_stride++;
      if(mismatch==2) bad[1].vertex_buffer_index++;
      if(mismatch==3) bad[1].instance_divisor++;
      if(mismatch==4) bad[1].dual_slot=false;
      s=ps5_create_vertex_elements_state(NULL,2,bad);
      assert(s && s->count==2); free(s);
   }
   s=ps5_create_vertex_elements_state(NULL,1,&e[1]);
   assert(s && s->count==1); free(s);
   assert(!ps5_create_vertex_elements_state(NULL,33,e));
   assert(!ps5_create_vertex_elements_state(NULL,1,NULL));
}
'''
with tempfile.TemporaryDirectory() as directory:
    exe = str(Path(directory) / 'check')
    subprocess.run(['clang-18', '-x', 'c', '-std=c11', '-Wall', '-Werror',
                    '-fsanitize=address,undefined', '-o', exe, '-'], input=code,
                   text=True, check=True)
    subprocess.run([exe], check=True)
print('PASS: mixed dvec3/dvec4 pairs, constant/instanced layouts and mismatch guards')
