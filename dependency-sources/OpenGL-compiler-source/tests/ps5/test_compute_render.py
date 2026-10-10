#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compile the native compute/render shaders and challenge their readback oracle."""
import subprocess
import tempfile
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PSBC = ROOT / "third_party/opengnm-psbc"
source = (ROOT / "tests/ps5/egl_public_compute_render.c").read_text()
fixture_header = ROOT / "tests/ps5/compute_glsl_fixtures.h"
if not fixture_header.exists():
    raise SystemExit("Missing fixed GLSL fixtures: explicitly run tests/ps5/glsl_handoff/run.py --export-header")
fixture_text = fixture_header.read_text()
receipt_text = fixture_text.split('/* PS5_GLSL_RECEIPT_BEGIN\n', 1)[1].split('\nPS5_GLSL_RECEIPT_END */', 1)[0]
receipt = json.loads(receipt_text)
assert receipt['schema'] == 1 and receipt['target_abi']['compile_only']
receipt_hash = hashlib.sha256(receipt_text.encode()).hexdigest()
assert f'#define PS5_GLSL_RECEIPT_SHA256 "{receipt_hash}"' in fixture_text
for name, expected in receipt['source_sha256'].items():
    assert hashlib.sha256((ROOT / name).read_text().encode()).hexdigest() == expected, f"Stale GLSL fixture source: {name}"
for i, fixture in enumerate(receipt['fixtures']):
    assert hashlib.sha256(fixture['source'].encode()).hexdigest() == fixture['source_sha256']
    array = re.search(rf'ps5_glsl_blob_{i}\[\] = \{{(.*?)\}};', fixture_text, re.S)[1]
    blob = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-f]{2})', array))
    assert 0 < len(blob) == fixture['bytes'] <= 1048576
    assert hashlib.sha256(blob).hexdigest() == fixture['blob_sha256']
assert len(receipt['fixtures']) == 3
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "compiler/nir/nir_builtin_builder.h"
#include "compiler/nir/nir_serialize.h"
#include "pipe/p_state.h"
#include "util/blob.h"
#include "compute_glsl_fixtures.h"
#include "util/format/u_format.h"
#include "util/half_float.h"
#include "ps5_agc_package.h"
''' + source[source.index("#define IMAGE_WORDS"):source.index("static int run_fragment_storage(")] + r'''
static void compile(nir_shader *nir, PsbcCompileOptions *options) {
    nir_validate_shader(nir, "compute-render input");
    const nir_shader_compiler_options *borrowed_options=nir->options;
    if (options->stage==PSBC_STAGE_FRAGMENT && nir->info.num_ssbos) {
        unsigned xy=0,z=0,w=0;
        nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
            if(instr->type!=nir_instr_type_intrinsic) continue;
            nir_intrinsic_op op=nir_instr_as_intrinsic(instr)->intrinsic;
            assert(op!=nir_intrinsic_load_frag_coord);
            xy+=op==nir_intrinsic_load_frag_coord_xy;
            z+=op==nir_intrinsic_load_frag_coord_z;
            w+=op==nir_intrinsic_load_frag_coord_w_rcp;
        }
        assert(xy && z && w);
    }
    PsbcShaderOutput out = {0};
    assert(psbc_compile_nir(nir, options, &out) == PSBC_RESULT_OK);
    assert(nir->options==borrowed_options); /* Never retain compiler-stack options in borrowed NIR. */
    assert(out.machine_code_size && !out.metadata.scratch_size_per_thread);
    uint8_t *package = NULL;
    size_t size = 0;
    assert(!ps5_agc_package_build(&out, 0, &package, &size) && size);
    printf("stage=%u code=%zu package=%zu\n", options->stage, out.machine_code_size, size);
    free(package); psbc_free_output(&out); ralloc_free(nir);
}
static nir_shader *compute_buffer_pair(void) {
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE),"compute-buffer-pair");
    b.shader->info.workgroup_size[0]=b.shader->info.workgroup_size[1]=
        b.shader->info.workgroup_size[2]=1;
    b.shader->info.num_ssbos=1; b.shader->info.num_textures=2;
    for(unsigned unit=0;unit<2;++unit) {
        BITSET_SET(b.shader->info.textures_used,unit);
        nir_tex_instr *tex=nir_tex_instr_create(b.shader,2);
        tex->op=nir_texop_txf; tex->sampler_dim=GLSL_SAMPLER_DIM_BUF;
        tex->texture_index=tex->sampler_index=unit; tex->coord_components=1;
        tex->dest_type=nir_type_float32;
        tex->src[0]=nir_tex_src_for_ssa(nir_tex_src_coord,nir_imm_int(&b,unit));
        tex->src[1]=nir_tex_src_for_ssa(nir_tex_src_lod,nir_imm_int(&b,0));
        nir_def_init(&tex->instr,&tex->def,4,32); nir_builder_instr_insert(&b,&tex->instr);
        nir_store_ssbo(&b,&tex->def,nir_imm_int(&b,0),nir_imm_int(&b,unit*16),
            .write_mask=15,.align_mul=16);
    }
    return b.shader;
}
static nir_shader *compute_buffer_array(void) {
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE),"compute-buffer-array");
    b.shader->info.workgroup_size[0]=b.shader->info.workgroup_size[1]=
        b.shader->info.workgroup_size[2]=1;
    b.shader->info.num_ssbos=1; b.shader->info.num_ubos=1;
    b.shader->info.num_textures=16;
    for(unsigned unit=0;unit<16;++unit) BITSET_SET(b.shader->info.textures_used,unit);
    nir_def *zero=nir_imm_int(&b,0);
    nir_def *index=nir_iand_imm(&b,nir_load_ubo(&b,1,32,zero,zero,.align_mul=4,.range=4),15);
    nir_tex_instr *tex=nir_tex_instr_create(b.shader,4);
    tex->op=nir_texop_txf; tex->sampler_dim=GLSL_SAMPLER_DIM_BUF;
    tex->coord_components=1; tex->dest_type=nir_type_uint32;
    tex->src[0]=nir_tex_src_for_ssa(nir_tex_src_coord,zero);
    tex->src[1]=nir_tex_src_for_ssa(nir_tex_src_lod,zero);
    tex->src[2]=nir_tex_src_for_ssa(nir_tex_src_texture_offset,index);
    tex->src[3]=nir_tex_src_for_ssa(nir_tex_src_sampler_offset,index);
    nir_def_init(&tex->instr,&tex->def,4,32); nir_builder_instr_insert(&b,&tex->instr);
    nir_store_ssbo(&b,&tex->def,zero,zero,.write_mask=15,.align_mul=16);
    return b.shader;
}
static nir_shader *compute_buffer_image(void) {
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE),"compute-buffer-image");
    b.shader->info.workgroup_size[0]=b.shader->info.workgroup_size[1]=
        b.shader->info.workgroup_size[2]=1;
    b.shader->info.num_ssbos=1; b.shader->info.num_images=1;
    nir_def *zero=nir_imm_int(&b,0);
    nir_def *value=nir_image_load(&b,4,32,zero,nir_replicate(&b,zero,4),zero,zero,
        .image_dim=GLSL_SAMPLER_DIM_BUF,.format=PIPE_FORMAT_R32G32B32A32_UINT,
        .dest_type=nir_type_uint32);
    nir_store_ssbo(&b,value,zero,zero,.write_mask=15,.align_mul=16);
    return b.shader;
}
/* Reuse actual image-store builders; mutate only format/op and retain an
 * observable SSBO sink for loads/size/atomics. Compiler-only, not GL parsing. */
static nir_shader *normalized_image(nir_shader *nir, unsigned operation, enum pipe_format format,
                                    enum glsl_sampler_dim dim, bool array) {
    unsigned changed=0;
    nir_foreach_function_impl(impl,nir) {
        nir_builder b=nir_builder_create(impl);
        nir_foreach_block(block,impl) nir_foreach_instr_safe(instr,block) {
            if(instr->type!=nir_instr_type_intrinsic) continue;
            nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
            if(intr->intrinsic!=nir_intrinsic_image_store) continue;
            ++changed;
            nir_intrinsic_set_format(intr,format);
            nir_intrinsic_set_image_dim(intr,dim);
            nir_intrinsic_set_image_array(intr,array);
            nir_alu_type type=nir_intrinsic_src_type(intr);
            if(!operation) continue;
            b.cursor=nir_before_instr(instr);
            nir_def *slot=intr->src[0].ssa, *zero=nir_imm_int(&b,0), *value;
            if(operation==1)
                value=nir_image_load(&b,4,32,slot,intr->src[1].ssa,zero,zero,
                    .image_dim=dim,.image_array=array,.format=format,
                    .dest_type=type);
            else if(operation==2)
                value=nir_image_size(&b,dim==GLSL_SAMPLER_DIM_3D ? 3 :
                    (dim==GLSL_SAMPLER_DIM_1D || dim==GLSL_SAMPLER_DIM_BUF ? 1 : 2)+array,
                    32,slot,zero,.image_dim=dim,.image_array=array,.format=format);
            else
                value=nir_image_atomic(&b,32,slot,intr->src[1].ssa,zero,nir_imm_int(&b,1),
                    .image_dim=dim,.image_array=array,.format=PIPE_FORMAT_R32_UINT,
                    .atomic_op=nir_atomic_op_iadd);
            nir_store_ssbo(&b,value,zero,zero,.align_mul=4,
                .write_mask=(1u<<value->num_components)-1);
            nir_instr_remove(instr);
        }
        nir_progress(true,impl,nir_metadata_none);
    }
    assert(changed==1);
    if(operation) nir->info.num_ssbos=1;
    return nir;
}
int main(void) {
    (void)lower_gallium_texture_index;
    psbc_init();
    for(unsigned kind=0;kind<4;++kind) {
        enum pipe_format format=kind<3 ? image_formats[kind] : PIPE_FORMAT_R8G8B8A8_UNORM;
        const uint32_t expected_r32[6]={4,0,0,1,0,1}, expected_rgba[6]={4,5,6,7,0,1};
        for(unsigned channel=0;channel<6;++channel) {
            uint32_t selector=99;
            assert(ps5_texture_descriptor_swizzle(channel,format,&selector));
            assert(selector==(kind<3 ? expected_r32[channel] : expected_rgba[channel]));
        }
        uint32_t selector=99;
        assert(!ps5_texture_descriptor_swizzle(6,format,&selector) && selector==99);
    }
    assert(expected_red(0,1,-1)==0xbe800000 && expected_red(0,16,1)==0x40800000);
    assert(expected_red(1,1,-1)==0x80000008 && expected_red(1,16,1)==0x10000035);
    assert(expected_red(2,1,-1)==(uint32_t)-1007 && expected_red(2,16,1)==1112);
    PsbcCompileOptions options = {.target=PSBC_TARGET_PS5, .stage=PSBC_STAGE_COMPUTE,
        .optimise=true, .address32_hi=2, .gallium_buffer_arrays=true,
        .descriptor_binding_count=3, .descriptor_bindings={
          {.binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(PSBC_STAGE_COMPUTE),
           .type=PSBC_DESCRIPTOR_STORAGE_BUFFER, .array_size=16, .stride=16},
          {.binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(PSBC_STAGE_COMPUTE),
           .type=PSBC_DESCRIPTOR_UNIFORM_BUFFER, .array_size=15, .stride=16, .offset=256},
          {.binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(PSBC_STAGE_COMPUTE),
           .type=PSBC_DESCRIPTOR_STORAGE_IMAGE, .array_size=8, .stride=32, .offset=496}}};
    PsbcShaderOutput pair[2]={{0}};
    for(unsigned variant=0;variant<2;++variant) {
        PsbcCompileOptions pair_options=options;
        pair_options.descriptor_bindings[pair_options.descriptor_binding_count++]=
            (PsbcDescriptorBinding){.binding=0,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
                                    .array_size=1,.stride=48,.offset=752};
        pair_options.descriptor_bindings[pair_options.descriptor_binding_count++]=
            (PsbcDescriptorBinding){.binding=1,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
                                    .array_size=1,.stride=48,.offset=800+variant*48};
        nir_shader *nir=compute_buffer_pair();
        assert(psbc_compile_nir(nir,&pair_options,&pair[variant])==PSBC_RESULT_OK);
        ralloc_free(nir);
    }
    assert(pair[0].machine_code_size==pair[1].machine_code_size &&
           memcmp(pair[0].machine_code,pair[1].machine_code,pair[0].machine_code_size));
    for(unsigned i=0;i<2;++i) psbc_free_output(&pair[i]);
    nir_shader *buffer_array=compute_buffer_array();
    unsigned array_used=0,array_buffers=0,array_filtered=0,array_lod[16],array_dims=0;
    uint8_t array_bindings[16];
    assert(ps5_compute_texture_usage(buffer_array,&array_used,&array_buffers,&array_filtered,
        array_lod,&array_dims,array_bindings));
    assert(array_used==0xffff && array_buffers==0xffff && !array_filtered &&
           !array_dims && array_bindings[0]==16);
    PsbcCompileOptions buffer_array_options=options;
    buffer_array_options.descriptor_bindings[buffer_array_options.descriptor_binding_count++]=
        (PsbcDescriptorBinding){.binding=0,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
                                .array_size=16,.stride=48,.offset=752};
    compile(buffer_array,&buffer_array_options);
    compile(compute_buffer_image(),&options);
    const enum glsl_sampler_dim image_dims[]={GLSL_SAMPLER_DIM_1D,GLSL_SAMPLER_DIM_2D,
        GLSL_SAMPLER_DIM_3D,GLSL_SAMPLER_DIM_CUBE,GLSL_SAMPLER_DIM_RECT,GLSL_SAMPLER_DIM_BUF};
    for(unsigned d=0;d<ARRAY_SIZE(image_dims);++d) for(unsigned array=0;array<2;++array) {
        enum glsl_sampler_dim dim=image_dims[d];
        if(array && (dim==GLSL_SAMPLER_DIM_3D || dim==GLSL_SAMPLER_DIM_RECT || dim==GLSL_SAMPLER_DIM_BUF)) continue;
        for(unsigned stage=0;stage<2;++stage) for(unsigned op=0;op<4;++op) {
            PsbcCompileOptions candidate=options;
            candidate.stage=stage ? PSBC_STAGE_FRAGMENT : PSBC_STAGE_COMPUTE;
            candidate.spi_shader_col_format=stage ? 4 : 0;
            candidate.descriptor_bindings[0].binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(candidate.stage);
            candidate.descriptor_bindings[1].binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(candidate.stage);
            candidate.descriptor_bindings[2].binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(candidate.stage);
            nir_shader *nir=normalized_image(stage ? build_fragment_storage(2,7,10,false,false,0) :
                build_compute(1),op,PIPE_FORMAT_R32_UINT,dim,array);
            nir_validate_shader(nir,"image target regression");
            fprintf(stderr,"image-target dim=%u array=%u stage=%u op=%u\n",dim,array,stage,op);
            compile(nir,&candidate);
        }
    }
    const enum pipe_format normalized_formats[]={
        /* Formatless stores are tested separately for each GLSL numeric type. */
        PIPE_FORMAT_R8_UINT,
        PIPE_FORMAT_R8_SINT,
        PIPE_FORMAT_R8G8_UINT,
        PIPE_FORMAT_R8G8_SINT,
        PIPE_FORMAT_R8G8B8A8_UINT,
        PIPE_FORMAT_R8G8B8A8_SINT,
        PIPE_FORMAT_R16_UINT,
        PIPE_FORMAT_R16_SINT,
        PIPE_FORMAT_R16G16_UINT,
        PIPE_FORMAT_R16G16_SINT,
        PIPE_FORMAT_R16G16B16A16_UINT,
        PIPE_FORMAT_R16G16B16A16_SINT,
        PIPE_FORMAT_R32_UINT,
        PIPE_FORMAT_R32_SINT,
        PIPE_FORMAT_R32G32_UINT,
        PIPE_FORMAT_R32G32_SINT,
        PIPE_FORMAT_R32G32B32A32_UINT,
        PIPE_FORMAT_R32G32B32A32_SINT,
        PIPE_FORMAT_R8_UNORM,
        PIPE_FORMAT_R8_SNORM,
        PIPE_FORMAT_R8G8_UNORM,
        PIPE_FORMAT_R8G8_SNORM,
        PIPE_FORMAT_R8G8B8A8_UNORM,
        PIPE_FORMAT_R8G8B8A8_SNORM,
        PIPE_FORMAT_R16_UNORM,
        PIPE_FORMAT_R16_SNORM,
        PIPE_FORMAT_R16G16_UNORM,
        PIPE_FORMAT_R16G16_SNORM,
        PIPE_FORMAT_R16G16B16A16_UNORM,
        PIPE_FORMAT_R16G16B16A16_SNORM,
        PIPE_FORMAT_R16_FLOAT,
        PIPE_FORMAT_R16G16_FLOAT,
        PIPE_FORMAT_R16G16B16A16_FLOAT,
        PIPE_FORMAT_R32_FLOAT,
        PIPE_FORMAT_R32G32_FLOAT,
        PIPE_FORMAT_R32G32B32A32_FLOAT,
        PIPE_FORMAT_R10G10B10A2_UNORM,
        PIPE_FORMAT_R10G10B10A2_UINT,
        PIPE_FORMAT_R11G11B10_FLOAT};
    for(unsigned stage=0;stage<2;++stage) for(unsigned kind=0;kind<3;++kind) {
        PsbcCompileOptions candidate=options;
        candidate.stage=stage ? PSBC_STAGE_FRAGMENT : PSBC_STAGE_COMPUTE;
        candidate.spi_shader_col_format=stage ? 4 : 0;
        candidate.descriptor_bindings[0].binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(candidate.stage);
        candidate.descriptor_bindings[1].binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(candidate.stage);
        candidate.descriptor_bindings[2].binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(candidate.stage);
        for(unsigned op=0;op<4;++op) {
            if(op==2) continue; /* Size-query support is unchanged. */
            nir_shader *nir=normalized_image(stage ? build_fragment_storage(2,7,9+kind,false,false,0) :
                build_compute(kind),op,PIPE_FORMAT_NONE,GLSL_SAMPLER_DIM_2D,false);
            if(op==0) {
                nir_validate_shader(nir,"formatless store");
                compile(nir,&candidate);
                continue;
            }
            unsigned checked=0;
            nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                if(!nir_intrinsic_has_image_dim(intr)) continue;
                nir_intrinsic_set_format(intr,PIPE_FORMAT_NONE);
                struct gallium_buffer_state state={.options=&candidate,.valid=true};
                nir_builder b=nir_builder_create(impl);
                assert(!lower_gallium_image_index(&b,instr,&state) && !state.valid);
                ++checked;
            }
            assert(checked==1);
            ralloc_free(nir);
        }
    }
    for(unsigned f=0;f<ARRAY_SIZE(normalized_formats);++f) for(unsigned stage=0;stage<2;++stage) {
        PsbcCompileOptions normalized=options;
        normalized.stage=stage ? PSBC_STAGE_FRAGMENT : PSBC_STAGE_COMPUTE;
        normalized.spi_shader_col_format=stage ? 4 : 0;
        normalized.descriptor_bindings[0].binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(normalized.stage);
        normalized.descriptor_bindings[1].binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(normalized.stage);
        normalized.descriptor_bindings[2].binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(normalized.stage);
        for(unsigned operation=0;operation<4;++operation) {
            unsigned kind=util_format_is_pure_uint(normalized_formats[f]) ? 1 :
                util_format_is_pure_sint(normalized_formats[f]) ? 2 : 0;
            nir_shader *nir=normalized_image(stage ? build_fragment_storage(2,7,9+kind,false,false,0) :
                build_compute(kind),operation,normalized_formats[f],GLSL_SAMPLER_DIM_2D,false);
            nir_validate_shader(nir,"RGBA compiler regression");
            if(operation==3) {
                if(normalized_formats[f]==PIPE_FORMAT_R32_UINT || normalized_formats[f]==PIPE_FORMAT_R32_SINT) {
                    compile(nir,&normalized);
                    continue;
                }
                /* Narrow RGBA atomics are invalid NIR, so test the exact
                 * extracted admission guard, not an invalid compile pipeline. */
                unsigned changed=0;
                nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
                    if(instr->type!=nir_instr_type_intrinsic) continue;
                    nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                    if(intr->intrinsic==nir_intrinsic_image_atomic) {
                        nir_intrinsic_set_format(intr,normalized_formats[f]);
                        struct gallium_buffer_state state={.options=&normalized,.valid=true};
                        nir_builder b=nir_builder_create(impl);
                        assert(!lower_gallium_image_index(&b,instr,&state) && !state.valid);
                        nir_intrinsic_set_format(intr,PIPE_FORMAT_R32_UINT);
                        ++changed;
                    }
                }
                assert(changed==1);
                nir_validate_shader(nir,"restored R32UI atomic control");
                fprintf(stderr,"format=%u stage=%u atomic admission guard rejected\n",normalized_formats[f],normalized.stage);
                ralloc_free(nir);
                continue;
            }
            PsbcShaderOutput out={0};
            PsbcResult result=psbc_compile_nir(nir,&normalized,&out);
            fprintf(stderr,"format=%u stage=%u op=%s result=%d bytes=%zu\n",normalized_formats[f],normalized.stage,
                operation==0 ? "store" : operation==1 ? "load" : operation==2 ? "size" : "atomic-reject",
                result,out.machine_code_size);
            assert(result==PSBC_RESULT_OK && out.machine_code_size && !out.metadata.scratch_size_per_thread);
            uint8_t *package=NULL; size_t size=0;
            assert(!ps5_agc_package_build(&out,0,&package,&size) && size);
            free(package);
            psbc_free_output(&out); ralloc_free(nir);
        }
    }
    nir_shader_compiler_options native_options=*psbc_get_nir_options(PSBC_STAGE_COMPUTE);
    native_options.io_options |= nir_io_has_intrinsics; /* Same native screen contract. */
    assert(ps5_glsl_options_match(&native_options));
    nir_shader_compiler_options wrong_options=native_options;
    wrong_options.lower_fdiv=!wrong_options.lower_fdiv;
    assert(!ps5_glsl_options_match(&wrong_options));
    assert(!load_parsed_glsl(0,&wrong_options) && !load_parsed_glsl(3,&native_options));
    for(unsigned fixture=0;fixture<3;++fixture) {
        nir_shader *nir=load_parsed_glsl(fixture,&native_options);
        assert(nir && prepare_compute_nir(nir));
        unsigned ubos=nir->info.num_ubos;
        assert(prepare_compute_nir(nir) && nir->info.num_ubos==ubos);
        PsbcCompileOptions parsed_options=options;
        if(fixture==2) parsed_options.descriptor_bindings[parsed_options.descriptor_binding_count++]=
            (PsbcDescriptorBinding){.binding=0,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
                                    .array_size=1,.stride=48,.offset=752};
        compile(nir,&parsed_options);
        for(unsigned pass=0;pass<2;++pass) {
            uint32_t words[80]; memset(words,0xcd,sizeof(words));
            assert(count_parsed_glsl(words,parsed_glsl_expected(fixture,pass))==79);
            words[8]=parsed_glsl_expected(fixture,pass);
            assert(count_parsed_glsl(words,parsed_glsl_expected(fixture,pass))==80);
            words[0]=0; words[79]=0;
            assert(count_parsed_glsl(words,parsed_glsl_expected(fixture,pass))==78);
        }
    }
    PsbcShaderOutput uniform_out[2]={{0}};
    for(unsigned explicit_ubo=0;explicit_ubo<2;++explicit_ubo) {
        nir_shader *nir=build_compute_uniforms(explicit_ubo);
        assert(prepare_compute_nir(nir) && nir->info.num_ubos==2 && nir->info.first_ubo_is_default_ubo);
        assert(prepare_compute_nir(nir) && nir->info.num_ubos==2); /* No second shift/reservation. */
        nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block)
            if(instr->type==nir_instr_type_intrinsic)
                assert(nir_instr_as_intrinsic(instr)->intrinsic!=nir_intrinsic_load_uniform);
        nir_validate_shader(nir,"prepared compute defaults");
        assert(psbc_compile_nir(nir,&options,&uniform_out[explicit_ubo])==PSBC_RESULT_OK);
        assert(!uniform_out[explicit_ubo].metadata.scratch_valid);
        ralloc_free(nir);
    }
    assert(uniform_out[0].machine_code_size==uniform_out[1].machine_code_size);
    assert(!memcmp(uniform_out[0].machine_code,uniform_out[1].machine_code,uniform_out[0].machine_code_size));
    for(unsigned i=0;i<2;++i) psbc_free_output(&uniform_out[i]);
    for(unsigned explicit_ubo=0;explicit_ubo<2;++explicit_ubo) {
        nir_shader *nir=build_compute_user_ubo(explicit_ubo);
        assert(!nir->num_uniforms);
        assert(prepare_compute_nir(nir) && nir->info.num_ubos==2 && nir->info.first_ubo_is_default_ubo);
        assert(prepare_compute_nir(nir) && nir->info.num_ubos==2);
        nir_opt_constant_folding(nir);
        unsigned loads=0;
        nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block)
            if(instr->type==nir_instr_type_intrinsic) {
                nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                if(intr->intrinsic==nir_intrinsic_load_ubo) {
                    assert(nir_src_as_uint(intr->src[0])==1); ++loads;
                }
            }
        assert(loads==1);
        nir_validate_shader(nir,"user UBO without default uniforms");
        assert(psbc_compile_nir(nir,&options,&uniform_out[explicit_ubo])==PSBC_RESULT_OK);
        assert(!uniform_out[explicit_ubo].metadata.scratch_valid);
        ralloc_free(nir);
    }
    assert(uniform_out[0].machine_code_size==uniform_out[1].machine_code_size);
    assert(!memcmp(uniform_out[0].machine_code,uniform_out[1].machine_code,uniform_out[0].machine_code_size));
    for(unsigned i=0;i<2;++i) psbc_free_output(&uniform_out[i]);
    for(unsigned blocks=14;blocks<=15;++blocks) {
        nir_shader *nir=build_compute_user_ubo(false); nir->info.num_ubos=blocks;
        assert(prepare_compute_nir(nir)==(blocks==14));
        assert(nir->info.num_ubos==blocks+1);
        ralloc_free(nir);
    }
    for(unsigned blocks=14;blocks<=15;++blocks) {
        nir_shader *nir=build_compute_uniforms(false); nir->info.num_ubos=blocks;
        assert(prepare_compute_nir(nir)==(blocks==14));
        assert(nir->info.num_ubos==blocks+1);
        ralloc_free(nir);
    }
    nir_shader *wrong_stage=build_compute_uniforms(false);
    wrong_stage->info.stage=MESA_SHADER_FRAGMENT;
    assert(!prepare_compute_nir(wrong_stage) && wrong_stage->info.num_ubos==1);
    ralloc_free(wrong_stage);
    nir_shader *rejected_input=build_compute_user_ubo(true);
    const nir_shader_compiler_options *rejected_options=rejected_input->options;
    PsbcCompileOptions missing_banks=options; missing_banks.descriptor_binding_count=0;
    PsbcShaderOutput rejected_output={0};
    assert(psbc_compile_nir(rejected_input,&missing_banks,&rejected_output)!=PSBC_RESULT_OK);
    assert(rejected_input->options==rejected_options && !rejected_output.machine_code && !rejected_output.data);
    psbc_free_output(&rejected_output);
    nir_function_create(rejected_input,"unused");
    nir_validate_shader(rejected_input,"valid unused function declaration");
    assert(psbc_compile_nir(rejected_input,&options,&rejected_output)!=PSBC_RESULT_OK);
    assert(rejected_input->options==rejected_options && !rejected_output.machine_code && !rejected_output.data);
    psbc_free_output(&rejected_output); ralloc_free(rejected_input);
    for(unsigned kind=0;kind<3;++kind) compile(build_compute(kind), &options);
    PsbcCompileOptions all_slots=options;
    for(unsigned unit=0;unit<16;++unit)
        all_slots.descriptor_bindings[all_slots.descriptor_binding_count++]=(PsbcDescriptorBinding){
            .binding=unit,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,.stride=48,.offset=752+unit*48};
    nir_shader *all_nir=compute_all_slots();
    unsigned all_used=0,all_buffers=0,all_filtered=0,all_lod[PS5_COMPUTE_TEXTURE_SLOTS],all_arrays=0;
    assert(ps5_compute_texture_usage(all_nir,&all_used,&all_buffers,&all_filtered,all_lod,&all_arrays,(uint8_t[16]){0}));
    assert(all_used==65535 && !all_buffers && !all_filtered && !all_arrays);
    compile(all_nir,&all_slots);
    for(unsigned kind=0;kind<3;++kind) for(unsigned array=0;array<2;++array) for(unsigned level=0;level<4;++level)
        compile(write_mip(level,array,kind), &options);
    /* Sampled descriptors coexist with the three existing compute banks.
     * This is compiler/package coverage, not native sampler qualification. */
    for(unsigned unit=0;unit<=15;unit+=15) for(unsigned variant=0;variant<5;++variant) {
        nir_shader *nir=compute_sample(4,unit);
        nir_tex_instr *tex=NULL;
        nir_foreach_block(block,nir_shader_get_entrypoint(nir)) nir_foreach_instr(instr,block)
            if(instr->type==nir_instr_type_tex) tex=nir_instr_as_tex(instr);
        assert(tex);
        nir_tex_instr_remove_src(tex,nir_tex_instr_src_index(tex,nir_tex_src_lod));
        tex->op=nir_texop_tg4; tex->component=variant<4 ? variant : 0;
        if(variant==4) {
            nir_builder b=nir_builder_at(nir_before_instr(&tex->instr));
            tex->is_shadow=true;
            unsigned used,buffers,filtered,lods[16],arrays;
            assert(!ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
            nir_tex_instr_add_src(tex,nir_tex_src_comparator,nir_imm_float(&b,.5f));
            /* Offset lowering queries size on the same shadow sampler; the
             * query keeps is_shadow but has no comparison source. */
            nir_get_texture_size(&b,tex);
        }
        unsigned used=0,buffers=0,filtered=0,lods[16],arrays=0;
        assert(ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
        assert(used==(1u<<unit) && filtered==used && !buffers && !arrays && !lods[unit]);
        tex->sampler_dim=GLSL_SAMPLER_DIM_3D;
        assert(!ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
        tex->sampler_dim=GLSL_SAMPLER_DIM_2D;
        nir_validate_shader(nir,"bounded compute texture gather");
        compile(nir,&all_slots);
    }
    for(unsigned unit=0;unit<=15;unit+=15) {
        PsbcCompileOptions sampled=all_slots;
        PsbcShaderOutput output[2]={{0}};
        for(unsigned implicit=0;implicit<2;++implicit) {
            nir_shader *nir=compute_sample(implicit ? 6 : 4,unit);
            nir_tex_instr *tex=NULL;
            nir_foreach_block(block,nir_shader_get_entrypoint(nir)) nir_foreach_instr(instr,block)
                if(instr->type==nir_instr_type_tex) tex=nir_instr_as_tex(instr);
            assert(tex);
            unsigned used=0,buffers=0,filtered=0,lods[PS5_COMPUTE_TEXTURE_SLOTS],arrays=0;
            if(implicit) {
                assert(!ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
            }
            assert(prepare_compute_nir(nir) && prepare_compute_nir(nir));
            assert(tex->op==nir_texop_txl && tex->num_srcs==2);
            int lod=nir_tex_instr_src_index(tex,nir_tex_src_lod);
            assert(lod>=0 && nir_src_is_const(tex->src[lod].src) && nir_src_as_float(tex->src[lod].src)==0);
            assert(ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
            assert(used==(1u<<unit) && !buffers && filtered==used && !arrays && !lods[unit]);
            nir_validate_shader(nir,"compute implicit LOD normalized before usage validation");
            assert(psbc_compile_nir(nir,&sampled,&output[implicit])==PSBC_RESULT_OK);
            assert(!output[implicit].metadata.scratch_valid);
            uint8_t *package=NULL; size_t size=0;
            assert(!ps5_agc_package_build(&output[implicit],0,&package,&size) && size);
            free(package); ralloc_free(nir);
        }
        assert(output[0].machine_code_size==output[1].machine_code_size);
        assert(!memcmp(output[0].machine_code,output[1].machine_code,output[0].machine_code_size));
        assert(output[0].metadata.descriptor_binding_count==output[1].metadata.descriptor_binding_count);
        assert(!memcmp(output[0].metadata.descriptor_bindings,output[1].metadata.descriptor_bindings,
            output[0].metadata.descriptor_binding_count*sizeof(PsbcDescriptorBinding)));
        for(unsigned i=0;i<2;++i) psbc_free_output(&output[i]);
    }
    for(unsigned unit=0;unit<=15;unit+=15) for(unsigned test=0;test<6;++test) {
        nir_shader *checked=compute_sample(test,unit);
        unsigned used=0, buffers=0, filtered=0, max_lod[PS5_COMPUTE_TEXTURE_SLOTS], arrays=0;
        assert(ps5_compute_texture_usage(checked,&used,&buffers,&filtered,max_lod,&arrays,(uint8_t[16]){0}) && !arrays);
        assert(used==(1u<<unit) && !buffers && filtered==(test>=4 ? 1u<<unit : 0));
        ralloc_free(checked);
        PsbcCompileOptions sampled=options;
        sampled.descriptor_binding_count=4;
        sampled.descriptor_bindings[3]=(PsbcDescriptorBinding){.binding=unit,
            .type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,
            .stride=48,.offset=752+unit*48};
        compile(compute_sample(test,unit),&sampled);
        nir_shader *missing=compute_sample(test,unit);
        PsbcShaderOutput rejected={0};
        assert(psbc_compile_nir(missing,&options,&rejected)!=PSBC_RESULT_OK);
        assert(!rejected.machine_code);
        psbc_free_output(&rejected); ralloc_free(missing);
    }
    for(unsigned dimensional=0;dimensional<6;++dimensional) for(unsigned filtered_op=0;filtered_op<2;++filtered_op) {
        nir_shader *nir=compute_dimensional(dimensional,filtered_op);
        assert(prepare_compute_nir(nir));
        unsigned used=0,buffers=0,filtered=0,lods[16],arrays=0;
        assert(ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
        assert(used==1 && !buffers && filtered==(dimensional<4 && (dimensional==3 || filtered_op)) &&
               arrays==(dimensional==1 || dimensional==5));
        if(dimensional>=4) {
            nir_tex_instr *tex=NULL;
            nir_foreach_block(block,nir_shader_get_entrypoint(nir)) nir_foreach_instr(instr,block)
                if(instr->type==nir_instr_type_tex) tex=nir_instr_as_tex(instr);
            assert(tex);
            int index=nir_tex_instr_src_index(tex,nir_tex_src_ms_index);
            assert(index>=0);
            nir_def *sample=tex->src[index].src.ssa;
            nir_builder b=nir_builder_create(nir_shader_get_entrypoint(nir));
            b.cursor=nir_before_instr(&tex->instr);
            nir_src_rewrite(&tex->src[index].src,nir_imm_int(&b,4));
            assert(!ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
            nir_src_rewrite(&tex->src[index].src,sample);
        }
        compile(nir,&all_slots);
    }
    /* Sample-count queries have no coordinate, LOD, or sample-index source. */
    for(unsigned array=0;array<2;++array) {
        nir_shader *nir=compute_dimensional(array ? 5 : 4,0);
        nir_tex_instr *old=NULL;
        nir_foreach_block(block,nir_shader_get_entrypoint(nir)) nir_foreach_instr(instr,block)
            if(instr->type==nir_instr_type_tex) old=nir_instr_as_tex(instr);
        assert(old);
        nir_builder b=nir_builder_create(nir_shader_get_entrypoint(nir));
        b.cursor=nir_before_instr(&old->instr);
        nir_tex_instr *query=nir_tex_instr_create(nir,0);
        query->op=nir_texop_texture_samples;
        query->sampler_dim=GLSL_SAMPLER_DIM_MS;
        query->is_array=array;
        query->texture_index=old->texture_index;
        query->dest_type=nir_type_int32;
        nir_def_init(&query->instr,&query->def,1,32);
        nir_builder_instr_insert(&b,&query->instr);
        nir_def *v=&query->def;
        nir_def_rewrite_uses(&old->def,nir_vec4(&b,v,v,v,v));
        nir_instr_remove(&old->instr);
        assert(prepare_compute_nir(nir));
        unsigned used=0,buffers=0,filtered=0,lods[16],arrays=0;
        assert(ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
        assert(used && !buffers && !filtered && !!arrays==!!array);
        query->texture_index=16;
        assert(!ps5_compute_texture_usage(nir,&used,&buffers,&filtered,lods,&arrays,(uint8_t[16]){0}));
        query->texture_index=0;
        compile(nir,&all_slots);
    }
    const unsigned layer_counts[]={1,3,8};
    for(unsigned kind=0;kind<3;++kind) for(unsigned count=0;count<3;++count)
      for(unsigned unit=0;unit<=15;unit+=15) for(unsigned op=0;op<(kind ? 2u : 4u);++op)
        for(unsigned level=0;level<(op==3 ? 1u : 4u);++level) {
            nir_shader *checked=compute_mip(op,unit,level,layer_counts[count],kind,false);
            unsigned used=0, buffers=0, filtered=0, max_lod[PS5_COMPUTE_TEXTURE_SLOTS], arrays=0;
            assert(ps5_compute_texture_usage(checked,&used,&buffers,&filtered,max_lod,&arrays,(uint8_t[16]){0}));
            assert(!buffers);
            assert(arrays==(layer_counts[count]>1 ? 1u<<unit : 0));
            assert(used==(1u<<unit) && filtered==(op>=2 ? 1u<<unit : 0));
            assert(max_lod[unit]==level+(op==3));
            PsbcCompileOptions sampled=options;
            sampled.descriptor_binding_count=4;
            sampled.descriptor_bindings[3]=(PsbcDescriptorBinding){.binding=unit,
                .type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,.stride=48,.offset=752+unit*48};
            compile(checked,&sampled);
        }
    for(unsigned kind=0;kind<3;++kind) for(unsigned count=0;count<3;++count)
      for(unsigned op=0;op<(kind ? 2u : 4u);++op) for(unsigned level=0;level<(op==3 ? 3u : 4u);++level)
      for(unsigned negative=0;negative<2;++negative) {
        const unsigned layers=layer_counts[count];
        uint32_t words[80]; memset(words,0xcd,sizeof(words));
        const uint32_t reds[2][4]={{0x3f800000,0x40000000,0x40800000,0x41000000},
                                  {0x3fc00000,0x40400000,0x40c00000,0}};
        for(unsigned i=0;i<16;++i) {
            float red; memcpy(&red,&reds[op==3][level],4);
            red=(red+16.0f*(i%layers))*(negative ? -1 : 1);
            uint32_t bits; memcpy(&bits,&red,4);
            if(kind==1) bits=(negative ? 0x80000000u : 0x10000000u)+(i%layers)*65536u+(1u<<level);
            if(kind==2) bits=(uint32_t)((negative ? -1 : 1)*(int)(1000+(i%layers)*16+(1u<<level)));
            const uint32_t value[4]={op==1 ? 16u>>level : bits,
                op==1 ? 8u>>level : 0,op==1 && layers>1 ? layers : 0,op==1 || kind ? 1 : 0x3f800000u};
            memcpy(words+8+i*4,value,16);
        }
        assert(count_mip(words,op,level,negative ? -1 : 1,layers,kind)==80);
        words[0]^=1; words[8]^=1;
        assert(count_mip(words,op,level,negative ? -1 : 1,layers,kind)==78);
    }
    for(unsigned kind=0;kind<3;++kind) for(unsigned count=0;count<3;++count)
      for(unsigned op=0;op<(kind ? 2u : 3u);++op) for(unsigned unit=0;unit<=15;unit+=15)
      for(unsigned mask=0;mask<=3;++mask) {
        nir_shader *nir=compute_mip(op,unit,mask,layer_counts[count],kind,true);
        unsigned used=0,buffers=0,filtered=0,max_lod[PS5_COMPUTE_TEXTURE_SLOTS],arrays=0;
        assert(ps5_compute_texture_usage(nir,&used,&buffers,&filtered,max_lod,&arrays,(uint8_t[16]){0}));
        assert(!buffers);
        assert(used==(1u<<unit) && filtered==(op==2 ? 1u<<unit : 0) && max_lod[unit]==mask);
        PsbcCompileOptions sampled=options;
        sampled.descriptor_binding_count=4;
        sampled.descriptor_bindings[3]=(PsbcDescriptorBinding){.binding=unit,
            .type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,.stride=48,.offset=752+unit*48};
        compile(nir,&sampled);
        for(unsigned negative=0;negative<2;++negative) {
            uint32_t words[80]; memset(words,0xcd,sizeof(words));
            const uint32_t float_words[4]={0x3f800000,0x40000000,0x40800000,0x41000000};
            for(unsigned i=0;i<16;++i) {
                unsigned level=op==2 ? (mask && (i&1) ? mask-1 : 0) : i&mask,layer=i%layer_counts[count];
                float value; memcpy(&value,&float_words[level],4);
                if(op==2 && mask) value*=1.5f;
                value=(value+16.0f*layer)*(negative ? -1 : 1);
                uint32_t bits; memcpy(&bits,&value,4);
                if(kind==1) bits=(negative ? 0x80000000u : 0x10000000u)+layer*65536u+(1u<<level);
                if(kind==2) bits=(uint32_t)((negative ? -1 : 1)*(int)(1000+layer*16+(1u<<level)));
                const uint32_t channels[4]={op==1 ? 16u>>level : bits,op==1 ? 8u>>level : 0,
                    op==1 && layer_counts[count]>1 ? layer_counts[count] : 0,op==1 || kind ? 1 : 0x3f800000u};
                memcpy(words+8+i*4,channels,16);
            }
            assert(count_dynamic_mip(words,op,0,mask,negative ? -1 : 1,layer_counts[count],kind)==80);
            words[0]^=1; words[8]^=1;
            assert(count_dynamic_mip(words,op,0,mask,negative ? -1 : 1,layer_counts[count],kind)==78);
        }
      }
    for(unsigned fault=0;fault<8;++fault) {
        nir_shader *nir=compute_mip(fault==3 ? 2 : 0,0,fault ? 16 : 31,8,0,true);
        if(fault>=2) {
            nir_foreach_block(block,nir_shader_get_entrypoint(nir)) nir_foreach_instr_safe(instr,block) {
                if(instr->type!=nir_instr_type_tex) continue;
                nir_tex_instr *tex=nir_instr_as_tex(instr);
                nir_builder b=nir_builder_create(nir_shader_get_entrypoint(nir));
                b.cursor=nir_before_instr(instr);
                nir_def *zero=nir_imm_int(&b,0);
                nir_def *lod=nir_load_ubo(&b,1,32,zero,zero,.align_mul=4,.range=4);
                if(fault>=4) {
                    tex->op=nir_texop_txl;
                    tex->dest_type=nir_type_float32;
                    const uint32_t bad_bits[]={0xbf000000,0x7f800000,0x7fc00000,0x41780000};
                    lod=nir_bcsel(&b,nir_ine_imm(&b,lod,0),nir_imm_int(&b,bad_bits[fault-4]),nir_imm_float(&b,0.5));
                }
                nir_src_rewrite(&tex->src[0].src,fault==3 ? nir_u2f32(&b,nir_iand_imm(&b,lod,3)) : lod);
            }
        }
        unsigned used=0,buffers=0,filtered=0,max_lod[PS5_COMPUTE_TEXTURE_SLOTS],arrays=0;
        bool valid=ps5_compute_texture_usage(nir,&used,&buffers,&filtered,max_lod,&arrays,(uint8_t[16]){0});
        assert(valid==(fault==3));
        ralloc_free(nir);
    }
    for(unsigned fault=0;fault<7;++fault) {
        nir_shader *checked=compute_sample(fault>=5 ? 4 : 0,0);
        nir_tex_instr *tex=NULL;
        nir_foreach_block(block,nir_shader_get_entrypoint(checked))
            nir_foreach_instr(instr,block)
                if(instr->type==nir_instr_type_tex) tex=nir_instr_as_tex(instr);
        assert(tex);
        if(fault==0) tex->texture_index=16;
        if(fault==1) tex->is_array=true;
        if(fault==2) tex->sampler_dim=GLSL_SAMPLER_DIM_3D;
        if(fault==3) tex->src[1].src_type=nir_tex_src_texture_offset;
        if(fault==5) tex->sampler_index=1;
        if(fault==6) tex->dest_type=nir_type_uint32;
        if(fault==4) {
            nir_builder b=nir_builder_create(nir_shader_get_entrypoint(checked));
            b.cursor=nir_before_instr(&tex->instr);
            nir_src_rewrite(&tex->src[1].src,nir_imm_int(&b,16));
        }
        unsigned used=0, buffers=0, filtered=0, max_lod[PS5_COMPUTE_TEXTURE_SLOTS], arrays=0;
        bool valid=ps5_compute_texture_usage(checked,&used,&buffers,&filtered,max_lod,&arrays,(uint8_t[16]){0});
        assert(valid==(fault==6));
        if(valid) assert(used==1 && !buffers && filtered==1 && !arrays && !max_lod[0]);
        ralloc_free(checked);
    }
    options = (PsbcCompileOptions){.target=PSBC_TARGET_PS5, .stage=PSBC_STAGE_VERTEX,
        .optimise=true, .address32_hi=2, .ngg=true, .primitive_type=6};
    compile(build_vertex(), &options);
    options = (PsbcCompileOptions){.target=PSBC_TARGET_PS5, .stage=PSBC_STAGE_FRAGMENT,
        .optimise=true, .address32_hi=2, .spi_shader_col_format=4,
        .descriptor_binding_count=1, .descriptor_bindings={
          {.binding=0, .type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER, .array_size=1, .stride=48}}};
    nir_shader *fs = build_fragment(0);
    /* Gallium selects descriptors from these masks, not the tex instructions.
     * gather_info alone does not populate them for hand-built indexed NIR. */
    assert(fs->info.num_textures == 1 && BITSET_TEST(fs->info.textures_used, 0) &&
           BITSET_TEST(fs->info.textures_used_by_txf, 0));
    compile(fs, &options);
    for(unsigned kind=1;kind<3;++kind) compile(build_fragment(kind), &options);
    PsbcCompileOptions storage={.target=PSBC_TARGET_PS5,.stage=PSBC_STAGE_FRAGMENT,
        .optimise=true,.address32_hi=2,.gallium_buffer_arrays=true,.descriptor_binding_count=1,
        .descriptor_bindings={{.binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(PSBC_STAGE_FRAGMENT),
            .type=PSBC_DESCRIPTOR_STORAGE_BUFFER,.array_size=16,.stride=16}}};
    for(unsigned atomic=0;atomic<2;++atomic) for(unsigned slot=0;slot<=15;slot+=15)
        compile(build_fragment_storage(atomic,slot,1,false,false,0),&storage);
    storage.descriptor_binding_count=2;
    storage.descriptor_bindings[1]=(PsbcDescriptorBinding){
        .binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(PSBC_STAGE_FRAGMENT),
        .type=PSBC_DESCRIPTOR_STORAGE_IMAGE,.array_size=8,.offset=256,.stride=32};
    assert(fragment_image_packed_word(9,0,0)==0xc780c800u); /* -8, -7.5 */
    assert(fragment_image_packed_word(10,0,0)==0x00220011u); /* 17, 34 */
    assert(fragment_image_packed_word(11,0,0)==0xfc29fc18u); /* -1000, -983 */
    for(unsigned kind=0;kind<ARRAY_SIZE(image_formats);++kind)
      for(unsigned operation=2;operation<=((kind==1 || kind==2) ? 4u : 3u);++operation) for(unsigned slot=0;slot<=7;slot+=7)
        compile(build_fragment_storage(operation,slot,kind,false,false,0),&storage);
    for(unsigned kind=3;kind<ARRAY_SIZE(image_formats);++kind) for(unsigned slot=0;slot<=7;slot+=7)
        for(unsigned operation=2;operation<=3;++operation)
            compile(build_fragment_storage(operation,slot,kind,false,true,slot),&storage);
    for(unsigned slot=0;slot<=7;slot+=7) for(unsigned kind=0;kind<3;++kind) {
        PsbcCompileOptions mixed=storage;
        mixed.descriptor_binding_count=4;
        mixed.descriptor_bindings[2]=(PsbcDescriptorBinding){
            .binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(PSBC_STAGE_FRAGMENT),
            .type=PSBC_DESCRIPTOR_UNIFORM_BUFFER,.array_size=13,.offset=512,.stride=16};
        mixed.descriptor_bindings[3]=(PsbcDescriptorBinding){.binding=slot ? 15 : 0,
            .type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,.offset=720+(slot ? 15 : 0)*48,.stride=48};
        compile(build_fragment_storage(3,slot,kind,true,false,0),&mixed);
        PsbcShaderOutput rejected={0};
        nir_shader *missing=build_fragment_storage(3,slot,kind,true,false,0);
        assert(psbc_compile_nir(missing,&storage,&rejected)!=PSBC_RESULT_OK && !rejected.machine_code);
        psbc_free_output(&rejected); ralloc_free(missing);
    }
    assert(fragment_image_word(0,0,false)==0xc1000000 && fragment_image_word(0,32,true)==0x3e000000);
    assert(fragment_image_word(0,63,false)==0x40f80000 && fragment_image_word(1,63,true)==306);
    assert(fragment_image_word(2,0,false)==(uint32_t)-1000 && fragment_image_word(2,63,true)==(uint32_t)-1341);
    assert(fragment_image_word(4,0,true)==185 && fragment_image_word(7,0,true)==933);
    assert(fragment_image_word(8,0,true)==(uint32_t)-14322);
    uint32_t vector_bits=fragment_image_word(6,0,true); float vector_value;
    memcpy(&vector_value,&vector_bits,4); assert(vector_value==-205.875f);
    for(unsigned kind=0;kind<ARRAY_SIZE(image_formats);++kind) for(unsigned lane=0;lane<4;++lane) {
        const unsigned channels=kind<3 ? 1 : kind<6 ? 2 : 4;
        uint32_t selector=99;
        assert(ps5_texture_descriptor_swizzle(lane,image_formats[kind],&selector));
        assert(selector==(lane<channels ? lane+4 : lane==3 ? 1 : 0));
    }
    /* An incomplete legacy descriptor layout must return an error, not enter
     * RADV's unrelated bindless-heap path and abort the native application. */
    for (unsigned test=0; test<8; ++test) {
        fs = build_fragment(0);
        nir_tex_instr *tex = NULL;
        nir_foreach_block(block, nir_shader_get_entrypoint(fs))
            nir_foreach_instr(instr, block)
                if (instr->type == nir_instr_type_tex) tex=nir_instr_as_tex(instr);
        assert(tex);
        PsbcCompileOptions candidate = options;
        if (test == 0) candidate.descriptor_binding_count=0;
        if (test == 1) candidate.descriptor_bindings[0].binding=1;
        if (test == 2) {
            candidate.descriptor_bindings[0].type=PSBC_DESCRIPTOR_UNIFORM_BUFFER;
            candidate.descriptor_bindings[0].stride=16;
        }
        if (test == 3) tex->texture_index=64;
        if (test == 4 || test == 5) {
            nir_builder b=nir_builder_create(nir_shader_get_entrypoint(fs));
            b.cursor=nir_before_instr(&tex->instr);
            tex->op=nir_texop_txl;
            tex->sampler_index=7;
            nir_src_rewrite(&tex->src[0].src,nir_imm_vec2(&b,0.25,0.5));
            nir_src_rewrite(&tex->src[1].src,nir_imm_float(&b,0));
            if (test == 5) {
                candidate.descriptor_binding_count=2;
                candidate.descriptor_bindings[1]=candidate.descriptor_bindings[0];
                candidate.descriptor_bindings[1].binding=7;
                candidate.descriptor_bindings[1].offset=48;
            }
        }
        if (test == 6) tex->sampler_index=7; /* txf doesn't consume a sampler. */
        if (test == 7) tex->texture_index=candidate.descriptor_bindings[0].binding=63;
        nir_validate_shader(fs,"legacy layout guard input");
        PsbcShaderOutput output = {0};
        PsbcResult result=psbc_compile_nir(fs,&candidate,&output);
        assert((result == PSBC_RESULT_OK) == (test >= 5));
        assert((output.machine_code != NULL) == (test >= 5));
        psbc_free_output(&output); ralloc_free(fs);
    }
    psbc_shutdown();
    for (unsigned kind=0;kind<3;++kind) for (unsigned phase=0; phase<4; ++phase) {
        float sign=phase&1 ? 1 : -1;
        for(unsigned size_query=0;size_query<(kind==0 ? 8u : 2u);++size_query) {
            uint32_t sampled[80]; memset(sampled,0xcd,sizeof(sampled));
            for(unsigned i=0;i<16;++i) {
                if(size_query==1) {
                    const uint32_t size[4]={17,3,0,1};
                    memcpy(sampled+8+i*4,size,16);
                } else {
                    const uint32_t value[4]={expected_red(kind,i+1,sign),0,0,kind==0 ? 0x3f800000u : 1};
                    memcpy(sampled+8+i*4,value,16);
                    if(size_query>=2) {
                        const uint32_t bits[2][2]={{0x3f800000,0x40400000},{0x3f700000,0x40440000}};
                        sampled[8+i*4]=bits[size_query&1][(i&1)^(size_query==4 || size_query==5)] ^
                            (sign<0 ? 0x80000000u : 0);
                    }
                }
            }
            assert(count_sampled(sampled,sign,size_query,kind)==80);
            if(size_query!=1) assert(count_sampled(sampled,-sign,size_query,kind)==64);
            sampled[0]=0; sampled[71]^=1;
            assert(count_sampled(sampled,sign,size_query,kind)==78);
        }
        uint32_t words[IMAGE_WORDS];
        uint8_t pixels[8*256];
        memset(words,0xcd,sizeof(words));
        memset(pixels,0xcd,sizeof(pixels));
        for(unsigned i=65;i<81;++i) {
            words[i]=expected_red(kind,i-64,sign);
        }
        for(unsigned y=0;y<8;++y) for(unsigned x=0;x<8;++x) {
            uint8_t *p=pixels+y*256+4*x;
            p[0]=sign<0 ? 255 : 0; p[1]=sign>0 ? 255 : 0; p[2]=0; p[3]=255;
        }
        assert(count_image(words,sign,kind)==IMAGE_WORDS && count_pixels(pixels,256,sign)==64);
        assert(count_image(words,-sign,kind)==IMAGE_WORDS-16 && count_pixels(pixels,256,-sign)==0);
        words[0]=0; words[65]=0;
        assert(count_image(words,sign,kind)==IMAGE_WORDS-2);
        pixels[0]^=255; pixels[7*256+7*4+3]=0;
        assert(count_pixels(pixels,256,sign)==62);
    }
}
'''
driver = (ROOT / "src/gallium/ps5/ps5_screen.c").read_text()
swizzle_start = driver.index("static unsigned\nps5_format_swizzle(")
format_start = driver.index("static unsigned\nps5_storage_image_texel_size(")
swizzle = driver[format_start:driver.index("static bool\nps5_compute_image_array_resource(",format_start)] + driver[swizzle_start:driver.index("static bool\nps5_texture_descriptor_wrap(",swizzle_start)]
code = code.replace("static void compile(",swizzle+"static void compile(",1)
compiler = (PSBC / "libpsbc/psbc_compile.c").read_text()
state_at = compiler.index("struct gallium_buffer_state {")
count_at = compiler.index("static unsigned\ncontiguous_sampler_count(")
guard_at = compiler.index("static bool lower_gallium_image_index(")
guard = compiler[state_at:compiler.index("};",state_at)+2] + "\n" + compiler[count_at:compiler.index("/* Gallium scalar slots",count_at)] + compiler[guard_at:compiler.index("/* === Mesa stage mapping",guard_at)]
code = code.replace("static nir_shader *normalized_image(",guard+"static nir_shader *normalized_image(",1)
prepare_start = driver.index("   unsigned textures = 0", driver.index("ps5_create_compute_state("))
prepare_end = driver.index("   if (!context->compute_descriptors)", prepare_start)
prepare = "\n".join(line for line in driver.splitlines() if line.startswith((
    "#define PS5_COMPUTE_CONSTANT_SLOTS ", "#define PS5_COMPUTE_STORAGE_SLOTS ", "#define PS5_COMPUTE_IMAGE_SLOTS ")))
prepare += "\nstatic bool prepare_compute_nir(nir_shader *nir) {\n" + driver[prepare_start:prepare_end]
prepare += "return true; cleanup: return false;\n}\n"
code = code.replace("static void compile(",prepare+"static void compile(",1)
assert "screen->base.nir_options[MESA_SHADER_COMPUTE] = cs_options;" in driver
usage_start = driver.index("static bool\nps5_compute_texture_usage(")
usage = driver[usage_start:driver.index("/* Internal compute bring-up", usage_start)]
code = code.replace("static nir_shader *compute_sample(",
    "#define PS5_COMPUTE_TEXTURE_SLOTS PS5_AGC_COMPUTE_MAX_TEXTURES\n" + usage + "static nir_shader *compute_sample(", 1)
with tempfile.TemporaryDirectory() as directory:
    obj = str(Path(directory) / "compute-render.o")
    package = str(Path(directory) / "package.o")
    executable = str(Path(directory) / "compute-render")
    subprocess.run(["clang-18", "-std=gnu11", "-Wall", "-Werror",
        "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-DHAVE_PTHREAD=1",
        "-DHAVE_STRUCT_TIMESPEC=1", "-D_GNU_SOURCE",
        "-I", str(PSBC / "include/mesa"), "-I", str(PSBC / "include"),
        "-I", str(PSBC / "src"), "-I", str(PSBC / "src/gallium/include"),
        "-I", str(PSBC / "libpsbc"),
        "-I", str(ROOT / "src/platform"), "-I", str(ROOT / "tests/ps5"),
        "-x", "c", "-c", "-o", obj, "-"],
        input=code, text=True, check=True)
    subprocess.run(["clang-18", "-std=c11", "-Wall", "-Werror",
        "-I", str(PSBC / "libpsbc"), "-c", str(ROOT / "src/platform/ps5_agc_package.c"),
        "-o", package], check=True)
    subprocess.run(["g++", "-o", executable, obj, package, str(PSBC / "libpsbc.a"),
        "-pthread", "-lm"], check=True)
    subprocess.run([executable], check=True, timeout=30)
print("PASS: CS/VS/FS packages; typed, filtered, mip/array sampling and writers; descriptor rejections and readback/guard oracles (host only)")
print("PASS: RGBA16/8_UNORM and RGBA8_UINT/SINT CS/FS store/load/size compile+package; exact source guard rejects narrow RGBA atomics (NIR, not parsed GLSL)")
