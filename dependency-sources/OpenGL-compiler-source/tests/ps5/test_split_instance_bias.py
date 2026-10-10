#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the compiler's bias callback and check divided attribute indices."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'third_party/opengnm-psbc/libpsbc/psbc_compile.c').read_text()
start = source.index('static bool lower_instance_id_bias(')
function = source[start:source.index('\n}', start) + 2]
driver = (root / 'src/gallium/ps5/ps5_screen.c').read_text()
start = driver.index('            records = (uint64_t)info->start_instance +')
records = driver[start:driver.index(';', start) + 1]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint32_t value; } nir_def;
typedef struct { unsigned intrinsic, base, instr; nir_def def; } nir_intrinsic_instr;
typedef struct { unsigned cursor; } nir_builder;
struct ac_arg { unsigned arg_index; bool used; };
struct ac_shader_args { struct ac_arg instance_id; };
struct radv_shader_args { struct ac_shader_args ac; struct ac_arg instance_id_bias; };
enum { nir_intrinsic_load_vector_arg_amd=1 };
static nir_def bias, sum;
static unsigned nir_intrinsic_base(nir_intrinsic_instr *i) { return i->base; }
static unsigned nir_after_instr(unsigned *i) { return *i; }
static nir_def *ac_nir_load_arg(nir_builder *b,const struct ac_shader_args *a,struct ac_arg arg)
{ (void)b;(void)a;assert(arg.used && arg.arg_index==3);return &bias; }
static nir_def *nir_iadd(nir_builder *b,nir_def *a,nir_def *c)
{ (void)b;sum.value=a->value+c->value;return &sum; }
static void nir_def_rewrite_uses_after(nir_def *a,nir_def *c) { a->value=c->value; }
''' + function + r'''
static uint64_t record_count(unsigned base,unsigned instance,unsigned divisor) {
 struct { unsigned start_instance,instance_count; } storage={base,1}, *info=&storage;
 struct { unsigned split_instance_id; } c={instance}, *context=&c;
 struct { unsigned instance_divisor; } e={divisor}, *element=&e;
 uint64_t records;
''' + records + r'''
 return records;
}
int main(void) {
 struct radv_shader_args args={.ac.instance_id={5,true},.instance_id_bias={3,true}};
 nir_builder b={0};
 for(unsigned base=0;base<=7;base+=7) for(unsigned instance=0;instance<8;++instance)
 for(unsigned divisor=1;divisor<=4;++divisor) {
   bias.value=instance;
   nir_intrinsic_instr i={.intrinsic=1,.base=5,.def={0}};
   assert(lower_instance_id_bias(&b,&i,&args));
   assert(i.def.value==instance);
   assert(base+i.def.value/divisor==base+instance/divisor);
   assert(record_count(base,instance,divisor)==base+instance/divisor+1u);
   nir_intrinsic_instr unrelated={.intrinsic=1,.base=6,.def={91}};
   assert(!lower_instance_id_bias(&b,&unrelated,&args) && unrelated.def.value==91);
 }
 args.ac.instance_id.used=false;
 nir_intrinsic_instr missing={.intrinsic=1,.base=5};
 assert(!lower_instance_id_bias(&b,&missing,&args));
}
'''
with tempfile.TemporaryDirectory() as directory:
    exe = str(Path(directory) / 'check')
    subprocess.run(['clang-18', '-x', 'c', '-std=c11', '-Wall', '-Werror', '-o', exe, '-'], input=code, text=True, check=True)
    subprocess.run([exe], check=True)
print('PASS: split IDs, nonzero base instances, divisors 1..4, unrelated/missing arguments')
