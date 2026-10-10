#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check real framebuffer export selection and compile it with host PSBC/ACO."""
import subprocess
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/gallium/ps5/ps5_screen.c").read_text()
backend = (ROOT / "src/platform/ps5_agc_runtime_backend.c").read_text()
pattern = int(re.search(r"sample_location_offsets\[i\],\s*raster4 \? UINT32_C\((0x[0-9a-f]+)\)", backend)[1], 16)
positions = (ROOT / "third_party/mesa-26.2.0/src/gallium/auxiliary/util/u_sample_positions.c").read_text()
table = positions.split("u_default_sample_positions_4x[][4] = {", 1)[1].split("};", 1)[0]
expected = [float(value) for value in re.findall(r"0\.\d+", table)]
actual = [0.5 + (((pattern >> (4*i) & 15) ^ 8) - 8) / 16 for i in range(8)]
assert actual == expected, (actual, expected)
print("PASS: configured 4x sample positions match API query order")


def function(name):
    start = source.index(name + "(")
    return source[start:source.index("\n}", start) + 2]


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "amd/common/amdgfxregs.h"
#include "amd/common/ac_formats.h"
#include "amd/common/ac_shader_util.h"
#include "pipe/p_state.h"
#include "util/format/u_format.h"
#include "psbc_compile.h"
#define PS5_ENABLE_CORE_RENDER_FORMATS_CANDIDATE 1
struct ps5_fragment_exports { uint32_t formats, int8_mask, int10_mask, color_mask; unsigned rasterization_samples; bool ignore_sample_mask; };
''' + positions.replace('#include "u_sample_positions.h"', '#include "util/u_sample_positions.h"') + "\nstatic bool\n" + function("ps5_lower_sample_interpolation") + "\nstatic bool\n" + function("ps5_core_render_target_format") + "\nstatic uint32_t\n" + function("ps5_color_target_info") + "\nstatic struct ps5_fragment_exports\n" + function("ps5_fragment_exports_for_framebuffer") + "\nstatic bool\n" + function("ps5_lower_fragment_color") + "\nstatic bool\n" + function("ps5_remove_sample_mask") + r'''
static unsigned export_format(const PsbcShaderOutput *out) {
    for (unsigned i = 0; i < out->metadata.context_register_count; ++i)
        if (out->metadata.context_registers[i].offset == 0x1c5)
            return out->metadata.context_registers[i].value;
    assert(!"missing SPI_SHADER_COL_FORMAT");
    return 0;
}
static void compile(const struct pipe_framebuffer_state *fb, unsigned expected,
                    bool dual) {
    struct ps5_fragment_exports exports = ps5_fragment_exports_for_framebuffer(fb);
    PsbcCompileOptions options = {
        .target = PSBC_TARGET_PS5, .stage = PSBC_STAGE_FRAGMENT,
        .entrypoint = "main", .optimise = true,
        .spi_shader_col_format = exports.formats,
        .color_is_int8 = exports.int8_mask, .color_is_int10 = exports.int10_mask,
    };
    PsbcShaderOutput out;
    nir_builder b = nir_builder_init_simple_shader(
        MESA_SHADER_FRAGMENT, psbc_get_nir_options(PSBC_STAGE_FRAGMENT), "exports");
    for (unsigned i = 0; i < (dual ? 2 : fb->nr_cbufs); ++i) {
        enum pipe_format f = fb->cbufs[dual ? 0 : i].format;
        bool integer = util_format_is_pure_integer(f);
        const struct glsl_type *type = util_format_is_pure_uint(f) ? glsl_uvec4_type()
            : integer ? glsl_ivec4_type() : glsl_vec4_type();
        nir_variable *color = nir_variable_create(b.shader, nir_var_shader_out, type, "color");
        color->data.location = dual && i ? FRAG_RESULT_DUAL_SRC_BLEND : FRAG_RESULT_DATA0 + i;
        nir_store_var(&b, color, integer ? nir_imm_ivec4(&b, 511, 17, 4097, 3)
            : nir_imm_vec4(&b, 100000.0f, 0.25f, 0.125f, 1.0f), 15);
    }
    assert(psbc_compile_nir(b.shader, &options, &out) == PSBC_RESULT_OK);
    assert(out.machine_code_size && export_format(&out) == expected);
    psbc_free_output(&out);
    options.spi_shader_col_format = 0xa;
    assert(psbc_compile_nir(b.shader, &options, &out) == PSBC_RESULT_INTERNAL_ERROR);
    assert(!out.machine_code);
    options.spi_shader_col_format = exports.formats;
    options.color_is_int8 = 256;
    assert(psbc_compile_nir(b.shader, &options, &out) == PSBC_RESULT_INTERNAL_ERROR);
    assert(!out.machine_code);
    ralloc_free(b.shader);
}
static void compile_legacy_clear(bool lowered, unsigned mask, unsigned formats, unsigned expected) {
    nir_builder b = nir_builder_init_simple_shader(
        MESA_SHADER_FRAGMENT, psbc_get_nir_options(PSBC_STAGE_FRAGMENT), "legacy-clear");
    nir_variable *color = nir_variable_create(b.shader, nir_var_shader_out, glsl_vec4_type(), "color");
    color->data.location = FRAG_RESULT_COLOR;
    nir_store_var(&b, color, nir_imm_vec4(&b, 0.25f, 0.5f, 0.75f, 1.0f), 15);
    if (lowered) nir_lower_io_passes(b.shader, false);
    nir_shader_gather_info(b.shader, nir_shader_get_entrypoint(b.shader));
    nir_shader_instructions_pass(b.shader, ps5_lower_fragment_color, nir_metadata_control_flow, &mask);
    nir_shader_gather_info(b.shader, nir_shader_get_entrypoint(b.shader));
    PsbcCompileOptions options = {.target=PSBC_TARGET_PS5, .stage=PSBC_STAGE_FRAGMENT,
        .optimise=true, .spi_shader_col_format=formats};
    PsbcShaderOutput out;
    assert(psbc_compile_nir(b.shader, &options, &out) == PSBC_RESULT_OK);
    /* Negative control: the unlowered helper has no explicit color export. */
    assert(export_format(&out) == expected);
    assert(b.shader->info.outputs_written == (lowered
        ? (uint64_t)mask << FRAG_RESULT_DATA0 : BITFIELD64_BIT(FRAG_RESULT_COLOR)));
    printf("legacy-clear normalized=%u mask=%x bytes=%zu\n", lowered, mask, out.machine_code_size);
    psbc_free_output(&out);
    ralloc_free(b.shader);
}
int main(void) {
    for (unsigned samples=1; samples<=4; samples*=4) {
      for (unsigned mode=INTERP_MODE_SMOOTH; mode<=INTERP_MODE_NOPERSPECTIVE; ++mode) {
        if (mode==INTERP_MODE_FLAT) continue;
        for (unsigned index=0; index<=samples; ++index) {
          nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
              psbc_get_nir_options(PSBC_STAGE_FRAGMENT),"sample-index interpolation");
          nir_def *id=index==samples ? nir_load_sample_id(&b) : nir_imm_int(&b,index);
          nir_def *coord=nir_load_barycentric_at_sample(&b,32,id,.interp_mode=mode);
          nir_store_output(&b,nir_vec4(&b,nir_channel(&b,coord,0),nir_channel(&b,coord,1),
              nir_imm_float(&b,0),nir_imm_float(&b,1)),nir_imm_int(&b,0),
              .write_mask=15,.io_semantics={.location=FRAG_RESULT_DATA0,.num_slots=1});
          assert(nir_shader_intrinsics_pass(b.shader,ps5_lower_sample_interpolation,
                                            nir_metadata_control_flow,&samples));
          nir_opt_constant_folding(b.shader);
          unsigned barycentrics=0;
          nir_foreach_function_impl(impl,b.shader) nir_foreach_block(block,impl)
            nir_foreach_instr(instr,block) if(instr->type==nir_instr_type_intrinsic) {
              nir_intrinsic_instr *in=nir_instr_as_intrinsic(instr);
              assert(in->intrinsic!=nir_intrinsic_load_barycentric_at_sample);
              assert(in->intrinsic!=nir_intrinsic_load_sample_positions_amd);
              if(in->intrinsic==nir_intrinsic_load_barycentric_pixel ||
                 in->intrinsic==nir_intrinsic_load_barycentric_at_offset) {
                ++barycentrics; assert(nir_intrinsic_interp_mode(in)==mode);
                assert((in->intrinsic==nir_intrinsic_load_barycentric_pixel)==(samples==1));
                if(samples>1 && index<samples) {
                  float expected[2]; u_default_get_sample_position(NULL,samples,index,expected);
                  assert(nir_src_is_const(in->src[0]));
                  for(unsigned axis=0;axis<2;++axis)
                    assert(nir_src_comp_as_float(in->src[0],axis)==expected[axis]-0.5f);
                }
              }
            }
          assert(barycentrics==1);
          nir_shader_gather_info(b.shader,nir_shader_get_entrypoint(b.shader));
          PsbcCompileOptions options={.target=PSBC_TARGET_PS5,.stage=PSBC_STAGE_FRAGMENT,
              .optimise=true,.rasterization_samples=samples};
          PsbcShaderOutput out={0};
          assert(psbc_compile_nir(b.shader,&options,&out)==PSBC_RESULT_OK);
          psbc_free_output(&out); ralloc_free(b.shader);
        }
      }
    }
    puts("PASS: static/dynamic sample-index interpolation, center/4x positions and interpolation modes");
    for (unsigned remove=0;remove<2;++remove) {
        nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
            psbc_get_nir_options(PSBC_STAGE_FRAGMENT),"sample-mask export");
        nir_store_output(&b,nir_imm_vec4(&b,1,0,0,1),nir_imm_int(&b,0),
            .write_mask=15,.io_semantics={.location=FRAG_RESULT_DATA0,.num_slots=1});
        nir_store_output(&b,nir_imm_int(&b,0),nir_imm_int(&b,0),
            .write_mask=1,.io_semantics={.location=FRAG_RESULT_SAMPLE_MASK,.num_slots=1});
        if (remove)
            assert(nir_shader_intrinsics_pass(b.shader,ps5_remove_sample_mask,
                                              nir_metadata_control_flow,NULL));
        nir_shader_gather_info(b.shader,nir_shader_get_entrypoint(b.shader));
        assert(!!(b.shader->info.outputs_written & BITFIELD64_BIT(FRAG_RESULT_SAMPLE_MASK)) == !remove);
        PsbcCompileOptions options={.target=PSBC_TARGET_PS5,.stage=PSBC_STAGE_FRAGMENT,
            .entrypoint="main",.optimise=true,.rasterization_samples=remove ? 1 : 4};
        PsbcShaderOutput out={0};
        assert(psbc_compile_nir(b.shader,&options,&out)==PSBC_RESULT_OK);
        bool found=false;
        for (unsigned i=0;i<out.metadata.context_register_count;++i)
            if (out.metadata.context_registers[i].offset==0x203) {
                assert(!!(out.metadata.context_registers[i].value & S_02880C_MASK_EXPORT_ENABLE(1)) == !remove);
                found=true;
            }
        assert(found); psbc_free_output(&out); ralloc_free(b.shader);
    }
    puts("PASS sample-mask export: removed for non-multisample, preserved for multisample");
    {
        nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
            psbc_get_nir_options(PSBC_STAGE_FRAGMENT),"sample-position inputs");
        nir_def *position=nir_load_sample_pos(&b);
        nir_store_output(&b,nir_vec4(&b,nir_channel(&b,position,0),nir_channel(&b,position,1),
            nir_imm_float(&b,0),nir_imm_float(&b,1)),nir_imm_int(&b,0),
            .write_mask=15,.io_semantics={.location=FRAG_RESULT_DATA0,.num_slots=1});
        nir_shader_gather_info(b.shader,nir_shader_get_entrypoint(b.shader));
        b.shader->info.fs.uses_sample_shading=true;
        PsbcCompileOptions options={.target=PSBC_TARGET_PS5,.stage=PSBC_STAGE_FRAGMENT,
            .entrypoint="main",.optimise=true,.rasterization_samples=4};
        PsbcShaderOutput out={0};
        assert(psbc_compile_nir(b.shader,&options,&out)==PSBC_RESULT_OK);
        unsigned inputs=0;
        for (unsigned i=0;i<out.metadata.context_register_count;++i)
            if (out.metadata.context_registers[i].offset==0x1b4)
                inputs=out.metadata.context_registers[i].value;
        fprintf(stderr,"sample-position SPI_PS_INPUT_ADDR=%08x\n",inputs);
        assert((inputs & (S_0286D0_POS_X_FLOAT_ENA(1)|S_0286D0_POS_Y_FLOAT_ENA(1))) ==
                         (S_0286D0_POS_X_FLOAT_ENA(1)|S_0286D0_POS_Y_FLOAT_ENA(1)));
        psbc_free_output(&out); ralloc_free(b.shader);
    }
    static const struct { enum pipe_format format; unsigned export, int8, int10; } cases[] = {
        {PIPE_FORMAT_R8G8B8A8_UNORM, 4, 0, 0},
        {PIPE_FORMAT_R8G8B8A8_SRGB, 4, 0, 0},
        {PIPE_FORMAT_R16G16B16A16_UNORM, 9, 0, 0},
        {PIPE_FORMAT_R16G16B16A16_FLOAT, 4, 0, 0},
        {PIPE_FORMAT_R32G32B32A32_FLOAT, 9, 0, 0},
        {PIPE_FORMAT_R8G8B8A8_UINT, 7, 1, 0},
        {PIPE_FORMAT_R16G16B16A16_UINT, 7, 0, 0},
        {PIPE_FORMAT_R8G8B8A8_SINT, 8, 1, 0},
        {PIPE_FORMAT_R32G32B32A32_SINT, 9, 0, 0},
        {PIPE_FORMAT_R10G10B10A2_UINT, 7, 0, 1},
        {PIPE_FORMAT_R8_UNORM, 4, 0, 0},
        {PIPE_FORMAT_R16_UNORM, 3, 0, 0},
        {PIPE_FORMAT_R32_FLOAT, 3, 0, 0},
        {PIPE_FORMAT_R32G32_FLOAT, 9, 0, 0},
    };
    struct pipe_resource target = {0};
    struct pipe_framebuffer_state fb = {.nr_cbufs = 1};
    for (unsigned samples=0;samples<=4;++samples) {
        fb.samples=samples;
        assert(ps5_fragment_exports_for_framebuffer(&fb).ignore_sample_mask == (samples==0));
        assert(ps5_fragment_exports_for_framebuffer(&fb).rasterization_samples == samples);
    }
    fb.samples=0;
    fb.cbufs[0].texture = &target;
    psbc_init();
    compile_legacy_clear(false, 1, 4, 0);
    compile_legacy_clear(true, 1, 4, 4);
    /* PSBC compacts SPI format nibbles, while logical output semantics stay sparse. */
    compile_legacy_clear(true, 6, 0x440, 0x44);
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        fb.cbufs[0].format = cases[i].format;
        struct ps5_fragment_exports key = ps5_fragment_exports_for_framebuffer(&fb);
        assert((key.formats & 15) == cases[i].export);
        assert(key.int8_mask == cases[i].int8 && key.int10_mask == cases[i].int10);
        assert(key.color_mask == 1);
        compile(&fb, cases[i].export, false);
    }
    fb.cbufs[0].format = PIPE_FORMAT_R8G8B8A8_UNORM;
    compile(&fb, 0x44, true);
    fb.cbufs[0].format = PIPE_FORMAT_R32G32B32A32_FLOAT;
    compile(&fb, 0x99, true);
    fb.nr_cbufs = 2;
    fb.cbufs[0].format = PIPE_FORMAT_R8G8B8A8_UNORM;
    fb.cbufs[1].texture = &target;
    fb.cbufs[1].format = PIPE_FORMAT_R32G32B32A32_FLOAT;
    compile(&fb, 0x94, false);
    fb.nr_cbufs = 3;
    fb.cbufs[2] = fb.cbufs[0];
    fb.cbufs[0].texture = NULL;
    assert(ps5_fragment_exports_for_framebuffer(&fb).color_mask == 6);
    fb.nr_cbufs = 0;
    assert(ps5_fragment_exports_for_framebuffer(&fb).color_mask == 0);
    psbc_shutdown();
}
'''
with tempfile.TemporaryDirectory() as temporary:
    executable = str(Path(temporary) / "fragment-exports")
    obj = str(Path(temporary) / "fragment-exports.o")
    psbc = ROOT / "third_party/opengnm-psbc"
    subprocess.run(["clang-18", "-std=gnu11", "-Wall", "-Werror",
                    "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1",
                    "-DHAVE_PTHREAD=1", "-DHAVE_STRUCT_TIMESPEC=1", "-D_GNU_SOURCE",
                    "-I", str(psbc / "include/mesa"),
                    "-I", str(psbc / "include"), "-I", str(psbc / "src"),
                    "-I", str(psbc / "src/gallium/include"), "-I", str(psbc / "libpsbc"),
                    "-I", str(ROOT / "third_party/mesa-26.2.0/src/gallium/auxiliary"),
                    "-x", "c", "-c", "-o", obj, "-"], input=code, text=True, check=True)
    subprocess.run(["g++", "-o", executable, obj, str(psbc / "libpsbc.a"),
                    "-pthread", "-lm"], check=True)
    subprocess.run([executable], check=True)
for field in ("formats", "int8_mask", "int10_mask", "color_mask", "ignore_sample_mask", "rasterization_samples"):
    assert f"variant->exports.{field} == exports->{field}" in source
assert "nir_lower_io_passes(converted.ir.nir, false);" in source
print("PASS: 14 formats, integer/MRT/dual-source exports, invalid keys, lowered legacy helper outputs")
