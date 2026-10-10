#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise actual compact/Vulkan attribute mapping and optional instance ABI."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
mapping = (root / 'third_party/opengnm-psbc/src/amd/vulkan/nir/radv_nir_lower_vs_inputs.c').read_text()
start = mapping.index('static bool\nlocation_is_64bit(')
mapping = mapping[start:mapping.index('static nir_def *\nlower_load_vs_input(', start)]
driver = (root / 'src/gallium/ps5/ps5_screen.c').read_text()
start = driver.index('   if (input_metadata->start_instance_valid) {')
instance = driver[start:driver.index('   if (input_metadata->vertex_buffer_table_valid)', start)]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define VERT_ATTRIB_GENERIC0 16
enum pipe_format { F32=32, F64=64 };
static unsigned util_format_get_max_channel_size(enum pipe_format f) { return f; }
typedef struct { unsigned value; } nir_src;
typedef struct { unsigned location,high_dvec2; } nir_io_semantics;
typedef struct { nir_src offset; nir_io_semantics sem; } nir_intrinsic_instr;
static nir_src *nir_get_io_offset_src(nir_intrinsic_instr *i) { return &i->offset; }
static bool nir_src_is_const(nir_src s) { (void)s; return true; }
static unsigned nir_src_as_uint(nir_src s) { return s.value; }
static nir_io_semantics nir_intrinsic_io_semantics(nir_intrinsic_instr *i) { return i->sem; }
struct gfx { struct { unsigned attributes_valid; enum pipe_format vertex_attribute_formats[16]; } vi; };
typedef struct { const struct gfx *gfx_state; bool compact_vertex_inputs; } lower_vs_inputs_state;
''' + mapping + r'''
struct context { int last_draw_status; unsigned split_instance_id; };
struct metadata { bool start_instance_valid; unsigned start_instance_user_data_dword;
                  bool instance_id_bias_valid; unsigned instance_id_bias_user_data_dword; };
struct draw { unsigned start_instance; };
static void setup(struct context *context, const struct metadata *input_metadata,
                  unsigned input_user_data_count, uint32_t *input_user_data,
                  const struct draw *info) {
''' + instance + r'''
}
int main(void) {
    struct gfx g={.vi.attributes_valid=0xffff};
    for(unsigned i=0;i<16;++i) g.vi.vertex_attribute_formats[i]=F64;
    lower_vs_inputs_state s={&g,true};
    for(unsigned location=0;location<16;++location) for(unsigned high=0;high<2;++high) {
        nir_intrinsic_instr i={.sem={16+location,high}};
        unsigned upper=9;
        assert(location_from_intrinsic(&i,&s,&upper)==location && upper==high);
    }
    /* Preserve the existing Vulkan split-location convention. */
    s.compact_vertex_inputs=false;
    nir_intrinsic_instr i={.sem={17,0}};
    unsigned upper=0;
    assert(location_from_intrinsic(&i,&s,&upper)==0 && upper==1);
    g.vi.vertex_attribute_formats[0]=F32;
    assert(location_from_intrinsic(&i,&s,&upper)==1 && upper==0);
    for(unsigned value=0;value<17;++value) for(unsigned present=0;present<2;++present) {
        struct context c={0}; struct draw d={value};
        struct metadata m={.start_instance_valid=present,.start_instance_user_data_dword=1};
        uint32_t data[3]={99,99,99};
        setup(&c,&m,3,data,&d);
        assert(!c.last_draw_status && data[0]==99 && data[2]==99);
        assert(data[1]==(present ? value : 99));
        m.start_instance_user_data_dword=3;
        setup(&c,&m,3,data,&d);
        assert(c.last_draw_status==(present ? -10 : 0));
    }
    struct context c={.split_instance_id=7}; struct draw d={5};
    struct metadata m={.start_instance_valid=true,.start_instance_user_data_dword=1,
                       .instance_id_bias_valid=true,.instance_id_bias_user_data_dword=2};
    uint32_t data[3]={99,99,99};
    setup(&c,&m,3,data,&d);
    assert(!c.last_draw_status && data[0]==99 && data[1]==5 && data[2]==7);
    m.instance_id_bias_user_data_dword=3;
    setup(&c,&m,3,data,&d);
    assert(c.last_draw_status==-10);
    c.last_draw_status=0; m.instance_id_bias_valid=false;
    setup(&c,&m,3,data,&d);
    assert(c.last_draw_status==-10);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    binary = str(Path(tmp) / 'check')
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-pie', '-no-pie',
                    '-x', 'c', '-', '-o', binary], input=code, text=True, check=True)
    subprocess.run([binary], check=True)
print('PASS: compact low/high double attributes, Vulkan mapping, absent/valid/invalid instance ABI')
