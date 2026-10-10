#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the real varying-cloner ALU branch against expanded swizzles."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
psbc = root / "third_party/opengnm-psbc"
relative = "src/compiler/nir/nir_opt_varyings.c"

def alu_branch(source):
    source = source[source.index("clone_ssa_impl("):]
    return source[source.index("   case nir_instr_type_alu: {"):
                  source.index("   case nir_instr_type_intrinsic: {")]

branch = alu_branch((psbc / relative).read_text())
assert branch == alu_branch((root / "third_party/mesa-26.2.0" / relative).read_text())
code = r'''
#include <assert.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#define FLAG_ALU_IS_TES_INTERP_LOAD 1
struct linkage_info { nir_builder producer_builder; };
/* Recursion is outside this check: the source definitions stay in one shader. */
static nir_def *clone_ssa_impl(struct linkage_info *l, nir_builder *b, nir_def *d) { return d; }
static nir_def *get_stored_value_for_load(struct linkage_info *l, nir_instr *i) { abort(); }
static nir_def *clone_alu(nir_builder *b, nir_def *ssa) {
    struct linkage_info *linkage = NULL;
    nir_def *clone = NULL;
    switch (nir_def_instr_type(ssa)) {
''' + branch + r'''
    default: abort();
    }
    return clone;
}
int main(void) {
    glsl_type_singleton_init_or_ref();
    nir_shader_compiler_options options = {0};
    nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_VERTEX, &options, "swizzle-clone");
    for (unsigned width = 1; width <= 4; ++width) {
        nir_def *src = nir_undef(&b, width, 32);
        for (unsigned lane = 0; lane < width; ++lane) {
            for (unsigned reduction = 0; reduction < 2; ++reduction) {
                nir_alu_instr *original = nir_alu_instr_create(b.shader,
                    reduction ? nir_op_bany_fnequal4 : nir_op_fadd);
                for (unsigned i = 0; i < 2; ++i) {
                    original->src[i].src = nir_src_for_ssa(src);
                    memset(original->src[i].swizzle, lane, NIR_MAX_VEC_COMPONENTS);
                }
                nir_def_init(&original->instr, &original->def,
                             reduction ? 1 : 4, reduction ? 1 : 32);
                original->fp_math_ctrl = nir_op_valid_fp_math_ctrl(original->op,
                                                                  b.fp_math_ctrl);
                nir_builder_instr_insert(&b, &original->instr);
                nir_alu_instr *copy = nir_def_as_alu(clone_alu(&b, &original->def));
                assert(copy->def.num_components == original->def.num_components);
                assert(copy->def.bit_size == original->def.bit_size);
                assert(copy->fp_math_ctrl == original->fp_math_ctrl);
                for (unsigned i = 0; i < 2; ++i)
                    for (unsigned component = 0; component < 4; ++component)
                        assert(copy->src[i].swizzle[component] == lane);
            }
        }
    }
    nir_validate_shader(b.shader, "expanded swizzles survive varying cloning");
    ralloc_free(b.shader);
    glsl_type_singleton_decref();
}
'''
with tempfile.TemporaryDirectory(prefix="varying-clone-") as temporary:
    directory = Path(temporary)
    source, obj, binary = (directory / name for name in ("check.c", "check.o", "check"))
    source.write_text(code)
    command = ["clang-18", "-std=gnu11", "-Wall", "-Werror", "-DHAVE_ENDIAN_H=1",
               "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-DHAVE_PTHREAD=1",
               "-DHAVE_STRUCT_TIMESPEC=1", "-D_GNU_SOURCE"]
    for include in ("include/mesa", "include", "src"):
        command += ["-I", str(psbc / include)]
    subprocess.run(command + ["-c", str(source), "-o", str(obj)], check=True)
    subprocess.run(["g++", "-o", str(binary), str(obj), str(psbc / "libpsbc.a"), "-pthread", "-lm"], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: varying ALU clones preserve expanded swizzles and result dimensions (20 variants)")
