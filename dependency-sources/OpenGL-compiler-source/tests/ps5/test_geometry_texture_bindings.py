#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise real descriptor helpers and NIR index remapping without a GPU."""
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
screen = (ROOT / "src/gallium/ps5/ps5_screen.c").read_text()


def function(name):
    start = screen.index("static bool\n" + name + "(")
    return screen[start:screen.index("\n}", start) + 3]


def structure(name):
    start = screen.index("struct " + name + " {")
    return screen[start:screen.index("\n};", start) + 3]


defines = "\n".join(re.findall(
    r"^#define PS5_(?:MAX_TEXTURE_UNITS|MERGED_TEXTURE_UNITS|MAX_CONSTANT_BUFFERS|"
    r"TEXTURE_DESCRIPTOR_STRIDE|TEXTURE_DESCRIPTOR_BYTES|CONSTANT_DATA_OFFSET) "
    r"(?:[^\n]*\\\n)?[^\n]*", screen, re.M))
code = r'''
#include <assert.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "psbc_compile.h"
''' + defines + "\n" + function("ps5_append_texture_descriptor") + "\n" + \
    function("ps5_append_ubo_descriptors") + "\n" + \
    structure("ps5_texture_offset_state") + "\n" + function("ps5_offset_geometry_texture") + "\n" + \
    structure("ps5_ubo_offset_state") + "\n" + \
    function("ps5_offset_ubo_index") + r'''
static void dynamic_ubo_offset(void) {
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_GEOMETRY,
        psbc_get_nir_options(PSBC_STAGE_GEOMETRY),"dynamic-geometry-ubo");
    nir_def *index=nir_load_primitive_id(&b);
    nir_def *value=nir_load_ubo(&b,1,32,index,nir_imm_int(&b,0),
        .align_mul=4,.range=4);
    nir_intrinsic_instr *load=nir_instr_as_intrinsic(nir_def_instr(value));
    struct ps5_ubo_offset_state state={.first=3,.source_count=2,.valid=true};
    assert(ps5_offset_ubo_index(&b,&load->instr,&state) && state.valid);
    assert(!nir_src_is_const(load->src[0]));
    nir_alu_instr *add=nir_instr_as_alu(nir_def_instr(load->src[0].ssa));
    assert(add->op==nir_op_iadd && nir_src_as_uint(add->src[1].src)==3);
    nir_validate_shader(b.shader,"dynamic geometry UBO offset");
    ralloc_free(b.shader);
}
int main(void) {
    psbc_init();
    dynamic_ubo_offset();
    PsbcCompileOptions options = {0};
    for (unsigned i = 0; i < 32; ++i) {
        assert(ps5_append_texture_descriptor(&options, i, 0));
        assert(ps5_append_texture_descriptor(&options, i, 0));
        assert(options.descriptor_binding_count == i + 1);
        assert(options.descriptor_bindings[i].offset == 48 * i);
    }
    assert(!ps5_append_texture_descriptor(&options, 32, 0));
    PsbcCompileOptions mixed={0};
    for(unsigned i=0;i<16;++i) {
        assert(ps5_append_texture_descriptor(&mixed,i,720));
        assert(mixed.descriptor_bindings[i].offset==720+i*48);
        assert(!ps5_append_texture_descriptor(&mixed,i,0));
    }
    assert(!ps5_append_texture_descriptor(&mixed,16,UINT32_MAX));
    assert(ps5_append_ubo_descriptors(&options, 0, 26));
    assert(options.descriptor_binding_count == 58);
    assert(ps5_append_ubo_descriptors(&options, 26, 4));
    assert(options.descriptor_binding_count == 62);
    assert(!ps5_append_ubo_descriptors(&options, 30, 1));
    for (unsigned i = 0; i < 62; ++i) {
        const PsbcDescriptorBinding *a = &options.descriptor_bindings[i];
        assert(a->offset + a->stride <= PS5_CONSTANT_DATA_OFFSET);
        for (unsigned j = 0; j < i; ++j) {
            const PsbcDescriptorBinding *b = &options.descriptor_bindings[j];
            assert(a->binding != b->binding);
            assert(a->offset >= b->offset + b->stride ||
                   b->offset >= a->offset + a->stride);
        }
    }
    for (unsigned first = 16; first <= 64; first += 16)
    for (unsigned i = 0; i < 16; ++i) {
        struct ps5_texture_offset_state valid = {.first=first, .valid=true};
        nir_tex_instr tex = {0};
        tex.instr.type = nir_instr_type_tex;
        tex.texture_index = tex.sampler_index = i;
        assert(ps5_offset_geometry_texture(NULL, &tex.instr, &valid));
        assert(valid.valid && tex.texture_index == i + first && tex.sampler_index == i + first);
        assert(!ps5_offset_geometry_texture(NULL, &tex.instr, &valid) && !valid.valid);
    }
    struct ps5_texture_offset_state valid = {.first=16, .valid=true};
    nir_instr other = {0};
    other.type = nir_instr_type_alu;
    assert(!ps5_offset_geometry_texture(NULL, &other, &valid) && valid.valid);
    psbc_shutdown();
}
'''
with tempfile.TemporaryDirectory() as temporary:
    obj = str(Path(temporary) / "geometry-bindings.o")
    executable = str(Path(temporary) / "geometry-bindings")
    psbc = ROOT / "third_party/opengnm-psbc"
    subprocess.run([
        "clang-18", "-std=gnu11", "-Wall", "-Werror",
        "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-D_GNU_SOURCE",
        "-DHAVE_PTHREAD=1", "-DHAVE_STRUCT_TIMESPEC=1",
        "-I", str(psbc / "include/mesa"), "-I", str(psbc / "include"),
        "-I", str(psbc / "src"), "-I", str(psbc / "src/gallium/include"),
        "-I", str(psbc / "libpsbc"),
        "-x", "c", "-c", "-o", obj, "-"], input=code, text=True, check=True)
    subprocess.run(["g++", "-o", executable, obj, str(psbc / "libpsbc.a"),
                    "-pthread", "-lm"], check=True)
    subprocess.run([executable], check=True)
print("PASS: 32 sampler + 30 UBO descriptors, no alias/overlap; GS NIR index bounds")
