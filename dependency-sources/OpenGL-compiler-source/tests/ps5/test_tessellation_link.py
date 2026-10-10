#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Linked RADV/ACO compiler and hull-package regression; no native execution."""
import hashlib
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PSBC = ROOT / "third_party/opengnm-psbc"
LIB = PSBC / "libpsbc.a"


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 3] + "\n"


pipeline = (PSBC / "src/amd/vulkan/radv_pipeline_graphics.c").read_text()
compile_source = (PSBC / "libpsbc/psbc_compile.c").read_text()
util_source = (PSBC / "src/amd/common/ac_shader_util.c").read_text()
order = pipeline.index("static const mesa_shader_stage graphics_shader_order[]")
helpers = function(compile_source, "static void setup_ac_info(")
helpers += function(pipeline, "static void\nmerge_tess_info(")
helpers += pipeline[order:pipeline.index("};", order) + 2] + "\n"
for name in ("radv_graphics_shaders_fill_linked_vs_io_info",
             "radv_graphics_shaders_fill_linked_tcs_tes_io_info",
             "radv_graphics_shaders_fill_linked_tes_gs_io_info",
             "radv_graphics_shaders_fill_linked_io_info",
             "radv_graphics_shaders_link_varyings", "radv_fill_shader_info_ngg",
             "radv_declare_pipeline_args"):
    helpers += function(pipeline, "static void\n" + name + "(")
helpers += function(util_source, "static unsigned get_tcs_wg_output_mem_size(")
helpers += function((ROOT / "src/gallium/ps5/ps5_screen.c").read_text(),
                    "static void\nps5_lower_default_uniforms(")
helpers += function((ROOT / "src/gallium/ps5/ps5_screen.c").read_text(),
                    "static nir_shader *\nps5_stream_output_carrier_nir(")
helpers += function((PSBC / "src/compiler/nir/nir_passthrough_tcs.c").read_text(),
                    "nir_shader *\nnir_create_passthrough_tcs_impl(")
helpers += function((ROOT / "src/gallium/ps5/ps5_screen.c").read_text(),
                    "static bool\nps5_lower_default_tess_levels(")
helpers += function((ROOT / "src/gallium/ps5/ps5_screen.c").read_text(),
                    "static nir_shader *\nps5_default_tcs_nir(")
helpers += function((ROOT / "src/gallium/ps5/ps5_screen.c").read_text(),
                    "static uint32_t\nps5_tessellation_gl_tf_param(")

code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "psbc_compile.h"
#include "ps5_agc_package.h"
#include "compiler/nir/nir_serialize.h"
#include "util/blob.h"
#include "compiler/nir/nir_builder.h"
#include "compiler/nir/nir_xfb_info.h"
#include "amd/vulkan/radv_shader.h"
#include "amd/vulkan/radv_shader_args.h"
#include "amd/vulkan/radv_pipeline_graphics.h"
#include "amd/vulkan/radv_pipeline.h"
#include "amd/vulkan/nir/radv_nir.h"
#include "amd/common/nir/ac_nir.h"
#include "amd/common/ac_shader_util.h"
#include "amd/common/sid.h"
''' + helpers + r'''

static nir_variable *varying(nir_builder *b, nir_variable_mode mode,
                            const struct glsl_type *type, unsigned slot, bool patch) {
    nir_variable *v=nir_variable_create(b->shader,mode,type,"linked-value");
    v->data.location=slot; v->data.patch=patch;
    return v;
}
static nir_deref_instr *element(nir_builder *b,nir_variable *v,nir_def *i) {
    return nir_build_deref_array(b,nir_build_deref_var(b,v),i);
}
static nir_shader *build(mesa_shader_stage stage, bool cross,
                        const struct radv_compiler_info *ci) {
    nir_builder b=nir_builder_init_simple_shader(stage,&ci->nir_options[stage],"linked-tess-host");
    if(stage==MESA_SHADER_VERTEX) {
        nir_def *attr=nir_load_var(&b,varying(&b,nir_var_shader_in,
            glsl_vector_type(GLSL_TYPE_FLOAT,3),VERT_ATTRIB_GENERIC0,false));
        nir_def *p=nir_vec4(&b,nir_channel(&b,attr,0),nir_channel(&b,attr,1),
                            nir_channel(&b,attr,2),nir_imm_float(&b,1));
        nir_store_var(&b,varying(&b,nir_var_shader_out,glsl_vec4_type(),VARYING_SLOT_POS,false),p,15);
    } else if(stage==MESA_SHADER_GEOMETRY) {
        b.shader->info.gs.input_primitive=MESA_PRIM_TRIANGLES;
        b.shader->info.gs.output_primitive=MESA_PRIM_TRIANGLE_STRIP;
        b.shader->info.gs.vertices_in=3;
        b.shader->info.gs.vertices_out=3;
        b.shader->info.gs.invocations=1;
        b.shader->info.gs.active_stream_mask=1;
        nir_def *zero=nir_imm_int(&b,0);
        nir_variable *in=varying(&b,nir_var_shader_in,
            glsl_array_type(glsl_vec4_type(),3,0),VARYING_SLOT_POS,false);
        for(unsigned i=0;i<3;++i) {
            nir_def *p=nir_load_deref(&b,element(&b,in,nir_imm_int(&b,i)));
            nir_store_output(&b,p,zero,.src_type=nir_type_float32,
                .io_semantics={.location=VARYING_SLOT_POS,.num_slots=1});
            nir_emit_vertex(&b,0);
        }
        nir_end_primitive(&b,0);
    } else {
        b.shader->info.tess._primitive_mode=TESS_PRIMITIVE_TRIANGLES;
        b.shader->info.tess.spacing=TESS_SPACING_EQUAL;
        b.shader->info.tess.ccw=true;
        nir_variable *in=varying(&b,nir_var_shader_in,glsl_array_type(glsl_vec4_type(),3,0),VARYING_SLOT_POS,false);
        if(stage==MESA_SHADER_TESS_CTRL) {
            b.shader->info.tess.tcs_vertices_out=3;
            nir_def *id=nir_load_invocation_id(&b);
            nir_def *index=cross ? nir_umod(&b,nir_iadd_imm(&b,id,1),nir_imm_int(&b,3)) : id;
            nir_def *p=nir_load_deref(&b,element(&b,in,index));
            nir_variable *out=varying(&b,nir_var_shader_out,glsl_array_type(glsl_vec4_type(),3,0),VARYING_SLOT_POS,false);
            nir_store_deref(&b,element(&b,out,id),p,15);
            nir_push_if(&b,nir_ieq_imm(&b,id,0));
            if(cross) {
                nir_def *q=nir_load_deref(&b,element(&b,in,nir_imm_int(&b,2)));
                nir_store_var(&b,varying(&b,nir_var_shader_out,glsl_float_type(),VARYING_SLOT_PATCH0,true),
                              nir_fmul(&b,nir_channel(&b,q,0),nir_channel(&b,q,1)),1);
            }
            for(unsigned inner=0;inner<2;++inner) {
                unsigned count=inner ? 2 : 4;
                nir_variable *tf=varying(&b,nir_var_shader_out,glsl_array_type(glsl_float_type(),count,0),
                    inner ? VARYING_SLOT_TESS_LEVEL_INNER : VARYING_SLOT_TESS_LEVEL_OUTER,true);
                for(unsigned i=0;i<count;++i)
                    nir_store_deref(&b,element(&b,tf,nir_imm_int(&b,i)),nir_imm_float(&b,2),1);
            }
            nir_pop_if(&b,NULL);
        } else {
            nir_def *coord=nir_load_tess_coord(&b), *p=nir_imm_vec4(&b,0,0,0,0);
            for(unsigned i=0;i<3;++i) {
                nir_def *v=nir_load_deref(&b,element(&b,in,nir_imm_int(&b,i)));
                p=nir_fadd(&b,p,nir_fmul(&b,v,nir_channel(&b,coord,i)));
            }
            if(cross) {
                nir_def *q=nir_load_var(&b,varying(&b,nir_var_shader_in,glsl_float_type(),VARYING_SLOT_PATCH0,true));
                p=nir_fadd(&b,p,nir_vec4(&b,q,nir_imm_float(&b,0),nir_imm_float(&b,0),nir_imm_float(&b,0)));
            }
            nir_store_var(&b,varying(&b,nir_var_shader_out,glsl_vec4_type(),VARYING_SLOT_POS,false),p,15);
        }
    }
    nir_validate_shader(b.shader,"builder");
    return b.shader;
}
static void dump(nir_shader *nir,const char *phase) {
    char name[100]; snprintf(name,sizeof(name),"%u-%s.nir",nir->info.stage,phase);
    FILE *f=fopen(name,"w"); assert(f); nir_print_shader(nir,f); fclose(f);
}
static unsigned count(nir_shader *nir,nir_intrinsic_op op) {
    unsigned n=0;
    nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block)
        if(instr->type==nir_instr_type_intrinsic && nir_instr_as_intrinsic(instr)->intrinsic==op) ++n;
    return n;
}
static uint32_t context_value(const PsbcShaderMetadata *metadata, uint16_t offset) {
    for(unsigned i=0;i<metadata->context_register_count;++i)
        if(metadata->context_registers[i].offset==offset)
            return metadata->context_registers[i].value;
    assert(!"missing context register"); return 0;
}
static unsigned ring_access(nir_shader *nir, nir_intrinsic_op access, nir_intrinsic_op ring) {
    unsigned n=0;
    nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
        if(instr->type!=nir_instr_type_intrinsic) continue;
        nir_intrinsic_instr *i=nir_instr_as_intrinsic(instr);
        if(i->intrinsic!=access) continue;
        nir_instr *desc=nir_def_instr(i->src[access==nir_intrinsic_store_buffer_amd ? 1 : 0].ssa);
        if(desc->type==nir_instr_type_intrinsic && nir_instr_as_intrinsic(desc)->intrinsic==ring) ++n;
    }
    return n;
}
/* Ask the actual ABI lowering for constants in both producer/consumer contexts.
 * The witness is not compiled and has no hardware effect. */
static void abi_constants(const struct radv_compiler_info *ci,const struct radv_graphics_state_key *gfx,
                          const struct radv_shader_stage *stage,unsigned values[3]) {
    struct radv_shader_stage witness=*stage;
    nir_builder b=nir_builder_init_simple_shader(stage->stage,&ci->nir_options[stage->stage],"abi-witness");
    b.shader->info.tess=stage->nir->info.tess;
    nir_def *stride=stage->stage==MESA_SHADER_TESS_EVAL ? nir_imm_int(&b,0) : nir_load_lshs_vertex_stride_amd(&b);
    nir_def *attr=stage->stage==MESA_SHADER_VERTEX ? nir_imm_int(&b,0) : nir_load_tcs_mem_attrib_stride(&b);
    nir_def *patch=stage->stage==MESA_SHADER_VERTEX ? nir_imm_int(&b,0) : nir_load_hs_out_patch_data_offset_amd(&b);
    nir_store_output(&b,nir_vec3(&b,stride,attr,patch),nir_imm_int(&b,0),.write_mask=7,
                     .io_semantics={.location=VARYING_SLOT_VAR0,.num_slots=1});
    witness.nir=b.shader;
    NIR_PASS(_,b.shader,radv_nir_lower_abi,ci->ac->gfx_level,&witness,gfx,ci->hw.address32_hi);
    NIR_PASS(_,b.shader,nir_opt_constant_folding);
    nir_foreach_function_impl(impl,b.shader) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
        if(instr->type!=nir_instr_type_intrinsic) continue;
        nir_intrinsic_instr *i=nir_instr_as_intrinsic(instr);
        if(i->intrinsic!=nir_intrinsic_store_output) continue;
        assert(nir_src_is_const(i->src[0]));
        for(unsigned c=0;c<3;++c) values[c]=nir_src_as_const_value(i->src[0])[c].u32;
    }
    dump(b.shader,"abi-witness"); ralloc_free(b.shader);
}

/* Public API checks are additional to, not a replacement for, the extracted
 * RADV reference below. They intentionally require a refreshed host archive. */
static PsbcResult checked_compile(nir_shader** inputs,
                                  const PsbcTessellationCompileOptions* options,
                                  PsbcTessellationOutput* out) {
    struct blob before[3], after[3];
    const struct nir_shader_compiler_options* pointers[3];
    for (unsigned i=0;i<3;++i) {
        blob_init(&before[i]);
        nir_serialize(&before[i],inputs[i],false);
        pointers[i]=inputs[i]->options;
    }
    PsbcResult result=psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],NULL,options,out);
    for (unsigned i=0;i<3;++i) {
        assert(inputs[i]->options==pointers[i]); /* Never dereference a stale options pointer. */
        blob_init(&after[i]);
        nir_serialize(&after[i],inputs[i],false);
        assert(before[i].size==after[i].size);
        assert(!memcmp(before[i].data,after[i].data,before[i].size));
        blob_finish(&before[i]); blob_finish(&after[i]);
    }
    return result;
}
static void expect_empty(const PsbcTessellationOutput* out) {
    const PsbcTessellationOutput empty={0};
    assert(!memcmp(out,&empty,sizeof(empty)));
}
static int type_size_vec4(const struct glsl_type* type,bool bindless) {
    return glsl_count_attribute_slots(type,false);
}
static void wide_io_tests(const struct radv_compiler_info *ci, bool patch) {
    nir_shader *inputs[] = {build(MESA_SHADER_VERTEX,false,ci),
                           build(MESA_SHADER_TESS_CTRL,false,ci),
                           build(MESA_SHADER_TESS_EVAL,false,ci)};
    for (unsigned stage=0;stage<3;++stage) {
        nir_builder b=nir_builder_at(nir_before_impl(nir_shader_get_entrypoint(inputs[stage])));
        for (unsigned slot=0;slot<(patch ? 30 : 31);++slot) {
            nir_def *value;
            if (!stage) {
                value=nir_load_ssbo(&b,4,32,nir_imm_int(&b,0),nir_imm_int(&b,slot*16),
                                    .align_mul=16);
                inputs[stage]->info.num_ssbos=1;
            } else {
                bool patch_input=patch && stage==2;
                nir_variable *in=varying(&b,nir_var_shader_in,patch_input ? glsl_vec4_type() :
                    glsl_array_type(glsl_vec4_type(),3,0),
                    (patch_input ? VARYING_SLOT_PATCH0 : VARYING_SLOT_VAR0)+slot,patch_input);
                value=patch_input ? nir_load_var(&b,in) :
                    nir_load_deref(&b,element(&b,in,stage==1 ? nir_load_invocation_id(&b)
                                                                          : nir_imm_int(&b,0)));
            }
            bool patch_output=patch && stage==1;
            nir_variable *out=varying(&b,nir_var_shader_out,stage==1 && !patch ?
                glsl_array_type(glsl_vec4_type(),3,0) : glsl_vec4_type(),
                (patch_output ? VARYING_SLOT_PATCH0 : VARYING_SLOT_VAR0)+slot,patch_output);
            if (patch_output) {
                nir_push_if(&b,nir_ieq_imm(&b,nir_load_invocation_id(&b),0));
                nir_store_var(&b,out,value,15);
                nir_pop_if(&b,NULL);
            } else if (stage==1)
                nir_store_deref(&b,element(&b,out,nir_load_invocation_id(&b)),value,15);
            else
                nir_store_var(&b,out,value,15);
        }
        nir_shader_gather_info(inputs[stage],nir_shader_get_entrypoint(inputs[stage]));
        nir_validate_shader(inputs[stage],"128-component stage IO");
    }
    PsbcTessellationCompileOptions options={
        .input_patch_vertices=3,.offchip_workgroup_capacity_dwords=8192,.address32_hi=2
    };
    options.vertex.gallium_buffer_arrays=true;
    options.vertex.vertex_attribute_count=1;
    options.vertex.vertex_attributes[0]=(PsbcVertexAttribute){
        .location=0,.binding=0,.format=PSBC_VERTEX_FORMAT_R32G32B32_FLOAT,.stride=12,.alignment=4};
    options.vertex.descriptor_binding_count=1;
    options.vertex.descriptor_bindings[0]=(PsbcDescriptorBinding){
        .binding=2,.type=PSBC_DESCRIPTOR_STORAGE_BUFFER,.array_size=1,.offset=0,.stride=16};
    PsbcTessellationOutput out={0};
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(out.runtime.valid && out.runtime.num_patches && out.runtime.lds_bytes<=65536);
    printf("PASS %u-component linked IO patch=%u: patches=%u LDS=%u HS=%zu TES=%zu\n",
           patch ? 120 : 128,patch,out.runtime.num_patches,out.runtime.lds_bytes,out.hs.machine_code_size,out.tes.machine_code_size);
    psbc_free_tessellation_output(&out);
    if (patch) {
        nir_builder b=nir_builder_at(nir_before_impl(nir_shader_get_entrypoint(inputs[2])));
        varying(&b,nir_var_shader_in,glsl_array_type(glsl_vec4_type(),2,0),
                VARYING_SLOT_TESS_MAX-1,true);
        assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
    }
    for(unsigned i=0;i<3;++i) ralloc_free(inputs[i]);
}

static void api_tests(const struct radv_compiler_info* ci,bool cross,
                      PsbcTessellationOutput* reference) {
    for(unsigned topology=0;topology<8;++topology) {
        uint32_t flags=0xa5a5011b & C_028B6C_TOPOLOGY;
        uint32_t actual=ps5_tessellation_gl_tf_param(flags|S_028B6C_TOPOLOGY(topology));
        unsigned expected=topology==V_028B6C_OUTPUT_TRIANGLE_CW ? V_028B6C_OUTPUT_TRIANGLE_CCW :
            topology==V_028B6C_OUTPUT_TRIANGLE_CCW ? V_028B6C_OUTPUT_TRIANGLE_CW : topology;
        assert(actual==(flags|S_028B6C_TOPOLOGY(expected)));
    }
    nir_shader* inputs[]={build(MESA_SHADER_VERTEX,cross,ci),
                         build(MESA_SHADER_TESS_CTRL,cross,ci),
                         build(MESA_SHADER_TESS_EVAL,cross,ci)};
    PsbcTessellationCompileOptions options={
        .input_patch_vertices=3,.offchip_workgroup_capacity_dwords=8192,.address32_hi=2
    };
    options.vertex.vertex_attribute_count=1;
    options.vertex.vertex_attributes[0]=(PsbcVertexAttribute){
        .location=0,.binding=0,.format=PSBC_VERTEX_FORMAT_R32G32B32_FLOAT,
        .stride=12,.alignment=4};
    PsbcTessellationOutput out={0};
    assert(psbc_compile_nir_tessellation_pipeline(NULL,inputs[1],inputs[2],NULL,&options,&out)
           ==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out);
    assert(checked_compile(inputs,NULL,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out);
    assert(checked_compile(inputs,&options,NULL)==PSBC_RESULT_INVALID_ARGUMENT);
    nir_shader* gs=build(MESA_SHADER_GEOMETRY,false,ci);
    PsbcResult gs_result=psbc_compile_nir_tessellation_pipeline(
        inputs[0],inputs[1],inputs[2],gs,&options,&out);
    printf("four-stage result=%d %s\n",gs_result,psbc_result_string(gs_result));
    assert(gs_result==PSBC_RESULT_OK);
    assert(out.tes.metadata.source_stage==PSBC_STAGE_GEOMETRY);
    assert(out.tes.metadata.hardware_stage==PSBC_HW_STAGE_NGG);
    assert(G_028B54_LS_EN(out.tes.metadata.linkage_stages_en.value)==V_028B54_LS_STAGE_ON);
    assert(G_028B54_HS_EN(out.tes.metadata.linkage_stages_en.value));
    assert(G_028B54_DYNAMIC_HS(out.tes.metadata.linkage_stages_en.value));
    assert(G_028B54_ES_EN(out.tes.metadata.linkage_stages_en.value)==V_028B54_ES_STAGE_DS);
    assert(G_028B54_GS_EN(out.tes.metadata.linkage_stages_en.value));
    assert(G_028B54_PRIMGEN_EN(out.tes.metadata.linkage_stages_en.value));
    assert(context_value(&out.tes.metadata,0x2ab));
    assert(out.runtime.final_offchip_layout_valid);
    assert(out.runtime.final_offchip_layout_user_data_dword<
           out.tes.metadata.user_sgpr_count);
    assert(out.runtime.final_offchip_layout);
    /* The later buffer-array path must not change a resource-free pipeline. */
    PsbcTessellationCompileOptions array_options=options;
    array_options.vertex.gallium_buffer_arrays=true;
    PsbcTessellationOutput array_out={0};
    assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],gs,
           &array_options,&array_out)==PSBC_RESULT_OK);
    assert(out.hs.machine_code_size==array_out.hs.machine_code_size);
    assert(out.tes.machine_code_size==array_out.tes.machine_code_size);
    assert(!memcmp(out.hs.machine_code,array_out.hs.machine_code,out.hs.machine_code_size));
    assert(!memcmp(out.tes.machine_code,array_out.tes.machine_code,out.tes.machine_code_size));
    assert(!memcmp(&out.runtime,&array_out.runtime,sizeof(out.runtime)));
    assert(!memcmp(&out.hs.metadata,&array_out.hs.metadata,sizeof(out.hs.metadata)));
    assert(!memcmp(&out.tes.metadata,&array_out.tes.metadata,sizeof(out.tes.metadata)));
    psbc_free_tessellation_output(&array_out);
    puts("PASS resource-free buffer-array parity: code, metadata, runtime");
    psbc_free_tessellation_output(&out); ralloc_free(gs);
    /* Gallium supplies lowered built-in outputs as well as position. Keep
     * these alive in the final GS so ACO must actually compile the exports. */
    const unsigned builtin_slots[]={VARYING_SLOT_PSIZ,VARYING_SLOT_LAYER,
                                    VARYING_SLOT_VIEWPORT,VARYING_SLOT_CLIP_DIST0,
                                    VARYING_SLOT_CLIP_DIST0};
    for(unsigned n=0;n<ARRAY_SIZE(builtin_slots);++n) {
        gs=build(MESA_SHADER_GEOMETRY,false,ci);
        nir_lower_io(gs,nir_var_shader_in|nir_var_shader_out,type_size_vec4,0);
        nir_remove_dead_variables(gs,nir_var_shader_in|nir_var_shader_out,NULL);
        gs->info.io_lowered=true;
        nir_builder b=nir_builder_at(nir_before_impl(nir_shader_get_entrypoint(gs)));
        unsigned slot=builtin_slots[n];
        bool combined=n==4;
        bool integer=slot==VARYING_SLOT_LAYER || slot==VARYING_SLOT_VIEWPORT;
        nir_def* value=integer ? nir_imm_int(&b,1) : nir_imm_float(&b,1);
        if(combined) value=nir_vec2(&b,value,value);
        nir_store_output(&b,value,
                         nir_imm_int(&b,0),.base=1,.write_mask=combined ? 3 : 1,
                         .src_type=integer ? nir_type_int32 : nir_type_float32,
                         .io_semantics={.location=slot,.num_slots=1});
        if(slot==VARYING_SLOT_CLIP_DIST0) gs->info.clip_distance_array_size=1;
        if(combined) gs->info.cull_distance_array_size=1;
        nir_shader_gather_info(gs,nir_shader_get_entrypoint(gs));
        nir_validate_shader(gs,"lowered tessellation built-in export");
        gs_result=psbc_compile_nir_tessellation_pipeline(
            inputs[0],inputs[1],inputs[2],gs,&options,&out);
        printf("four-stage builtin slot=%u result=%d\n",slot,gs_result);
        fflush(stdout);
        assert(gs_result==PSBC_RESULT_OK);
        const uint32_t control=context_value(&out.tes.metadata,0x207);
        assert(G_02881C_USE_VTX_POINT_SIZE(control)==(slot==VARYING_SLOT_PSIZ));
        assert(G_02881C_USE_VTX_RENDER_TARGET_INDX(control)==(slot==VARYING_SLOT_LAYER));
        assert(G_02881C_USE_VTX_VIEWPORT_INDX(control)==(slot==VARYING_SLOT_VIEWPORT));
        assert(out.tes.metadata.clip_distance_mask==(slot==VARYING_SLOT_CLIP_DIST0));
        assert(out.tes.metadata.cull_distance_mask==(combined ? 2 : 0));
        assert(G_02881C_VS_OUT_CCDIST0_VEC_ENA(control)==(slot==VARYING_SLOT_CLIP_DIST0));
        psbc_free_tessellation_output(&out);
        nir_foreach_block(block,nir_shader_get_entrypoint(gs)) {
            nir_foreach_instr(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr* intr=nir_instr_as_intrinsic(instr);
                if(intr->intrinsic!=nir_intrinsic_store_output ||
                   nir_intrinsic_io_semantics(intr).location!=slot) continue;
                /* The new built-ins do not bypass the single-slot bound. */
                nir_io_semantics semantics=nir_intrinsic_io_semantics(intr);
                semantics.num_slots=2;
                nir_intrinsic_set_io_semantics(intr,semantics);
            }
        }
        assert(psbc_compile_nir_tessellation_pipeline(
            inputs[0],inputs[1],inputs[2],gs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out); ralloc_free(gs);
    }
    /* The actual runtime generator supplies an optional application TCS. */
    mesa_shader_stage saved_next=inputs[0]->info.next_stage, saved_prev=inputs[2]->info.prev_stage;
    inputs[0]->info.next_stage=MESA_SHADER_TESS_EVAL;
    inputs[2]->info.prev_stage=MESA_SHADER_VERTEX;
    for (unsigned vertices=1; vertices<=32; vertices+=31) {
        float levels[6]={4,2,3,1,2,4};
        nir_shader *default_tcs=ps5_default_tcs_nir(inputs[0]->info.outputs_written,vertices,levels);
        assert(default_tcs && default_tcs->info.tess.tcs_vertices_out==vertices);
        nir_validate_shader(default_tcs,"runtime default TCS");
        PsbcTessellationCompileOptions default_options=options;
        default_options.input_patch_vertices=vertices;
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],default_tcs,inputs[2],
            NULL,&default_options,&out)==PSBC_RESULT_OK);
        assert(out.runtime.output_patch_vertices==vertices);
        assert(inputs[0]->info.next_stage==MESA_SHADER_TESS_EVAL);
        assert(inputs[2]->info.prev_stage==MESA_SHADER_VERTEX);
        psbc_free_tessellation_output(&out); ralloc_free(default_tcs);
    }
    inputs[0]->info.next_stage=saved_next; inputs[2]->info.prev_stage=saved_prev;
    puts("PASS actual runtime default TCS: 1/32 vertices, explicit default levels");
    /* Gallium TES factor sysvals must become linked patch inputs, not reach ACO. */
    {
        nir_shader *saved=inputs[2];
        inputs[2]=nir_shader_clone(NULL,saved);
        nir_builder b=nir_builder_at(nir_after_impl(nir_shader_get_entrypoint(inputs[2])));
        nir_def *inner=nir_load_tess_level_inner(&b);
        nir_def *outer=nir_load_tess_level_outer(&b);
        nir_store_output(&b,nir_fadd(&b,nir_channel(&b,inner,1),nir_channel(&b,outer,3)),
            nir_imm_int(&b,0),.src_type=nir_type_float32,
            .io_semantics={.location=VARYING_SLOT_VAR0,.num_slots=1});
        nir_shader_gather_info(inputs[2],nir_shader_get_entrypoint(inputs[2]));
        nir_shader *saved_tcs=inputs[1];
        inputs[1]=nir_shader_clone(NULL,saved_tcs);
        radv_nir_lower_io(inputs[1]);
        nir_foreach_function_impl(impl,inputs[1]) nir_foreach_block(block,impl)
            nir_foreach_instr_safe(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                if(intr->intrinsic!=nir_intrinsic_store_output) continue;
                unsigned slot=nir_intrinsic_io_semantics(intr).location;
                if(slot!=VARYING_SLOT_TESS_LEVEL_INNER && slot!=VARYING_SLOT_TESS_LEVEL_OUTER) continue;
                nir_builder writer=nir_builder_at(nir_before_instr(instr));
                nir_def *value=nir_load_ssbo(&writer,intr->num_components,32,nir_imm_int(&writer,0),
                    nir_imm_int(&writer,(slot==VARYING_SLOT_TESS_LEVEL_INNER ? 16 : 0)+
                        nir_intrinsic_component(intr)*4),.align_mul=4);
                nir_src_rewrite(&intr->src[0],value);
            }
        inputs[1]->info.num_ssbos=1;
        nir_shader_gather_info(inputs[1],nir_shader_get_entrypoint(inputs[1]));
        PsbcTessellationCompileOptions factor_options=options;
        factor_options.vertex.gallium_buffer_arrays=true;
        factor_options.vertex.descriptor_binding_count=1;
        factor_options.vertex.descriptor_bindings[0]=(PsbcDescriptorBinding){
            .binding=6,.type=PSBC_DESCRIPTOR_STORAGE_BUFFER,.array_size=1,.offset=0,.stride=16};
        assert(checked_compile(inputs,&factor_options,&out)==PSBC_RESULT_OK);
        PsbcTessellationOutput reference=out;
        memset(&out,0,sizeof(out));
        nir_foreach_function_impl(impl,inputs[1]) nir_foreach_block(block,impl)
            nir_foreach_instr(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                if(intr->intrinsic!=nir_intrinsic_store_output) continue;
                nir_io_semantics sem=nir_intrinsic_io_semantics(intr);
                if(sem.location!=VARYING_SLOT_TESS_LEVEL_INNER &&
                   sem.location!=VARYING_SLOT_TESS_LEVEL_OUTER) continue;
                sem.no_varying=true;
                nir_intrinsic_set_io_semantics(intr,sem);
            }
        nir_shader_gather_info(inputs[1],nir_shader_get_entrypoint(inputs[1]));
        assert(checked_compile(inputs,&factor_options,&out)==PSBC_RESULT_OK);
        assert(out.hs.machine_code_size==reference.hs.machine_code_size);
        assert(out.tes.machine_code_size==reference.tes.machine_code_size);
        assert(!memcmp(out.hs.machine_code,reference.hs.machine_code,out.hs.machine_code_size));
        assert(!memcmp(out.tes.machine_code,reference.tes.machine_code,out.tes.machine_code_size));
        psbc_free_tessellation_output(&out); psbc_free_tessellation_output(&reference);
        ralloc_free(inputs[1]); inputs[1]=saved_tcs;
        ralloc_free(inputs[2]); inputs[2]=saved;
        puts("PASS TES inner/outer tessellation-level system values");
    }
    /* Folded GLSL built-ins can leave an unused constant declaration. */
    {
        nir_shader *saved=inputs[2];
        inputs[2]=nir_shader_clone(NULL,saved);
        nir_variable *dead=nir_variable_create(inputs[2],nir_var_mem_constant,
                                               glsl_int_type(),"gl_PatchVerticesIn");
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            NULL,&options,&out)==PSBC_RESULT_OK);
        psbc_free_tessellation_output(&out);
        nir_builder b=nir_builder_at(nir_before_cf_list(&nir_shader_get_entrypoint(inputs[2])->body));
        nir_load_var(&b,dead);
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            NULL,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
        ralloc_free(inputs[2]); inputs[2]=saved;
        puts("PASS folded builtin declaration; live constant deref rejected");
    }
    /* Primitive counting must work without any declared feedback varying. */
    for (unsigned with_gs=0; with_gs<2; ++with_gs) {
        nir_shader *query_gs=with_gs ? build(MESA_SHADER_GEOMETRY,false,ci) : NULL;
        PsbcTessellationCompileOptions query_options=options;
        query_options.vertex.ps5_global_primitive_query=true;
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            query_gs,&query_options,&out)==PSBC_RESULT_OK);
        const PsbcShaderMetadata *m=&out.tes.metadata;
        assert(m->primitive_query_valid && !m->streamout_valid);
        assert(m->primitive_query_buffer_user_data_dword<m->user_sgpr_count);
        assert(m->primitive_query_state_user_data_dword<m->user_sgpr_count);
        assert(m->primitive_query_buffer_user_data_dword!=m->primitive_query_state_user_data_dword);
        assert(m->primitive_query_enable_mask==128 && m->primitive_query_counter_offset==8);
        assert(!out.hs.metadata.primitive_query_valid);
        printf("PASS query-only pipeline gs=%u buffer=%u state=%u\n",with_gs,
               m->primitive_query_buffer_user_data_dword,m->primitive_query_state_user_data_dword);
        psbc_free_tessellation_output(&out); ralloc_free(query_gs);
    }
    /* Only the final linked stage owns feedback, with explicit global counters. */
    for (unsigned with_gs=0; with_gs<2; ++with_gs) {
        nir_shader *xfb_gs=with_gs ? build(MESA_SHADER_GEOMETRY,false,ci) : NULL;
        nir_shader *final=with_gs ? xfb_gs : inputs[2];
        nir_xfb_info *xfb=rzalloc_size(final,nir_xfb_info_size(1));
        xfb->buffers_written=xfb->streams_written=1;
        xfb->buffers[0].stride=16; xfb->buffers[0].varying_count=1;
        xfb->output_count=1;
        xfb->outputs[0]=(nir_xfb_output_info){.location=VARYING_SLOT_POS,.component_mask=15};
        final->xfb_info=xfb;
        final->info.has_transform_feedback_varyings=true;
        final->info.xfb_stride[0]=4;
        PsbcTessellationCompileOptions xfb_options=options;
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            xfb_gs,&xfb_options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        xfb_options.vertex.ps5_global_streamout=true;
        /* Separable upstream declarations must be stripped without modifying
         * the shader object, while the final capture declaration survives. */
        inputs[0]->xfb_info=ralloc_memdup(inputs[0],xfb,nir_xfb_info_size(1));
        inputs[0]->info.has_transform_feedback_varyings=true;
        inputs[0]->info.xfb_stride[0]=4;
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            xfb_gs,&xfb_options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        nir_shader *carrier=ps5_stream_output_carrier_nir(inputs[0]);
        assert(carrier && !carrier->xfb_info && !carrier->info.has_transform_feedback_varyings);
        assert(inputs[0]->xfb_info && inputs[0]->info.xfb_stride[0]==4);
        PsbcResult xfb_result=psbc_compile_nir_tessellation_pipeline(
            carrier,inputs[1],inputs[2],xfb_gs,&xfb_options,&out);
        ralloc_free(carrier);
        ralloc_free(inputs[0]->xfb_info); inputs[0]->xfb_info=NULL;
        inputs[0]->info.has_transform_feedback_varyings=false; inputs[0]->info.xfb_stride[0]=0;
        printf("linked streamout gs=%u result=%d\n",with_gs,xfb_result); fflush(stdout);
        assert(xfb_result==PSBC_RESULT_OK);
        assert(!out.hs.metadata.streamout_valid && out.tes.metadata.streamout_valid);
        assert(out.tes.metadata.streamout_enabled_stream_buffers_mask==1);
        assert(out.tes.metadata.streamout_strides_dwords[0]==4);
        uint8_t *xfb_package=NULL; size_t xfb_size=0;
        assert(!ps5_agc_package_build(&out.tes,with_gs ? 1 : 0,&xfb_package,&xfb_size));
        free(xfb_package); psbc_free_tessellation_output(&out);
        final->xfb_info=NULL; final->info.has_transform_feedback_varyings=false;
        final->info.xfb_stride[0]=0; ralloc_free(xfb);
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            xfb_gs,&xfb_options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        ralloc_free(xfb_gs);
    }
    /* Each linked stage reads its own UBO and uses the returned SSBO atomic
     * value. This tests actual resource lowering, not resource masks alone. */
    for (unsigned with_uniform=0; with_uniform<2; ++with_uniform)
    for (unsigned tested=0; tested<4; ++tested) {
        nir_shader *resource_gs=tested==3 ? build(MESA_SHADER_GEOMETRY,false,ci) : NULL;
        nir_shader **resource_input=tested==3 ? &resource_gs : &inputs[tested];
        nir_shader *saved=*resource_input;
        *resource_input=nir_shader_clone(NULL,saved);
        nir_builder b=nir_builder_at(nir_before_cf_list(
            &nir_shader_get_entrypoint(*resource_input)->body));
        nir_variable *offset=nir_variable_create(*resource_input,nir_var_uniform,
                                               glsl_uint_type(),"offset");
        nir_build_deref_var(&b,offset); /* Dead after Mesa lowers the load. */
        nir_variable *sampler=nir_variable_create(*resource_input,nir_var_uniform,
            glsl_sampler_type(GLSL_SAMPLER_DIM_2D,false,false,GLSL_TYPE_FLOAT),"goku");
        nir_build_deref_var(&b,sampler); /* Left behind by legacy sampler lowering. */
        nir_def *value=with_uniform ? nir_load_uniform(&b,1,32,nir_imm_int(&b,0),.range=1)
                                   : nir_imm_int(&b,1);
        nir_def *old=nir_ssbo_atomic(&b,32,nir_imm_int(&b,0),nir_imm_int(&b,0),value,
            .atomic_op=nir_atomic_op_iadd);
        nir_store_ssbo(&b,old,nir_imm_int(&b,0),nir_imm_int(&b,4),
            .write_mask=1,.align_mul=4);
        const unsigned texture_binding=16+16*tested+11;
        nir_tex_instr *tex=nir_tex_instr_create(b.shader,2);
        tex->op=nir_texop_txl; tex->sampler_dim=GLSL_SAMPLER_DIM_2D;
        tex->texture_index=tex->sampler_index=texture_binding;
        tex->coord_components=2; tex->dest_type=nir_type_float32;
        tex->src[0]=nir_tex_src_for_ssa(nir_tex_src_coord,nir_imm_vec2(&b,0.5f,0.5f));
        tex->src[1]=nir_tex_src_for_ssa(nir_tex_src_lod,nir_imm_float(&b,0));
        nir_def_init(&tex->instr,&tex->def,4,32);
        nir_builder_instr_insert(&b,&tex->instr);
        nir_store_ssbo(&b,&tex->def,nir_imm_int(&b,0),nir_imm_int(&b,16),
            .write_mask=15,.align_mul=16);
        const unsigned image_binding=4*tested+3;
        nir_variable *image_var=nir_variable_create(*resource_input,nir_var_image,
            glsl_image_type(GLSL_SAMPLER_DIM_2D,false,GLSL_TYPE_UINT),"linked-image");
        image_var->data.binding=image_binding;
        image_var->data.image.format=PIPE_FORMAT_R32_UINT;
        nir_deref_instr *image_deref=nir_build_deref_var(&b,image_var);
        nir_def *image=nir_image_load(&b,4,32,nir_imm_int(&b,0),
            nir_imm_ivec4(&b,0,0,0,0),nir_imm_int(&b,0),nir_imm_int(&b,0),
            .image_dim=GLSL_SAMPLER_DIM_2D,.format=PIPE_FORMAT_R32_UINT,
            .dest_type=nir_type_uint32);
        nir_intrinsic_instr *image_load=nir_instr_as_intrinsic(nir_def_instr(image));
        nir_rewrite_image_intrinsic(image_load,&image_deref->def,nir_image_intrinsic_type_deref);
        nir_store_ssbo(&b,nir_channel(&b,image,0),nir_imm_int(&b,0),nir_imm_int(&b,32),
            .write_mask=1,.align_mul=4);
        b.shader->info.num_textures=1;
        b.shader->info.num_images=1;
        BITSET_SET(b.shader->info.textures_used,texture_binding);
        (*resource_input)->num_uniforms=with_uniform;
        (*resource_input)->info.num_ssbos=1;
        ps5_lower_default_uniforms(*resource_input);
        assert(count(*resource_input,nir_intrinsic_load_uniform)==0);
        assert(count(*resource_input,nir_intrinsic_load_ubo)==with_uniform);
        nir_foreach_variable_with_modes(var,*resource_input,nir_var_uniform)
            assert(!"dead uniform declaration retained");
        nir_validate_shader(*resource_input,"linked buffer input");
        PsbcTessellationCompileOptions resource_options=options;
        resource_options.vertex.gallium_buffer_arrays=true;
        resource_options.vertex.descriptor_binding_count=4;
        resource_options.vertex.descriptor_bindings[0]=(PsbcDescriptorBinding){
            .binding=4*tested+1,.type=PSBC_DESCRIPTOR_UNIFORM_BUFFER,
            .array_size=1,.offset=0,.stride=16};
        resource_options.vertex.descriptor_bindings[1]=(PsbcDescriptorBinding){
            .binding=4*tested+2,.type=PSBC_DESCRIPTOR_STORAGE_BUFFER,
            .array_size=1,.offset=16,.stride=16};
        resource_options.vertex.descriptor_bindings[2]=(PsbcDescriptorBinding){
            .binding=texture_binding,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
            .array_size=1,.offset=32,.stride=48};
        resource_options.vertex.descriptor_bindings[3]=(PsbcDescriptorBinding){
            .binding=image_binding,.type=PSBC_DESCRIPTOR_STORAGE_IMAGE,
            .array_size=1,.offset=80,.stride=32};
        PsbcResult result=psbc_compile_nir_tessellation_pipeline(
            inputs[0],inputs[1],inputs[2],resource_gs,&resource_options,&out);
        printf("linked buffers stage=%u result=%d\n",tested,result);
        assert(result==PSBC_RESULT_OK);
        assert(out.hs.metadata.descriptor_set0_valid && out.tes.metadata.descriptor_set0_valid);
        assert(out.hs.metadata.descriptor_binding_count==4 && out.tes.metadata.descriptor_binding_count==4);
        psbc_free_tessellation_output(&out); expect_empty(&out);
        resource_options.vertex.descriptor_bindings[2].binding++;
        assert(psbc_compile_nir_tessellation_pipeline(inputs[0],inputs[1],inputs[2],
            resource_gs,&resource_options,&out)!=PSBC_RESULT_OK);
        expect_empty(&out);
        resource_options.vertex.descriptor_bindings[2].binding--;
        resource_options.vertex.descriptor_bindings[1].binding=4*tested+1;
        assert(checked_compile(inputs,&resource_options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
        resource_options.vertex.descriptor_binding_count=PSBC_MAX_DESCRIPTOR_BINDINGS+1;
        assert(checked_compile(inputs,&resource_options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
        ralloc_free(*resource_input); *resource_input=saved;
        ralloc_free(resource_gs);
    }
    mesa_shader_stage stage=inputs[0]->info.stage;
    inputs[0]->info.stage=MESA_SHADER_FRAGMENT;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_UNSUPPORTED_STAGE);
    expect_empty(&out); inputs[0]->info.stage=stage;
    nir_function* unused=nir_function_create(inputs[0],"unused");
    nir_validate_shader(inputs[0],"valid unused function declaration");
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out); exec_node_remove(&unused->node);
    for (unsigned n=0;n<2;++n) {
        options.input_patch_vertices=n ? 33 : 0;
        assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
    }
    options.input_patch_vertices=3;
    const uint32_t capacities[]={0,1,UINT32_MAX};
    for (unsigned n=0;n<3;++n) {
        options.offchip_workgroup_capacity_dwords=capacities[n];
        assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        expect_empty(&out);
    }
    options.offchip_workgroup_capacity_dwords=8192;
    struct shader_info tcs_info=inputs[1]->info, tes_info=inputs[2]->info;
    inputs[2]->info.tess.tcs_vertices_out=4; /* Contradictory modes: no RADV assertion. */
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out); inputs[2]->info=tes_info;
    inputs[1]->info.tess.spacing=inputs[2]->info.tess.spacing=TESS_SPACING_FRACTIONAL_EVEN;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(G_028B6C_PARTITIONING(out.runtime.tf_param)==V_028B6C_PART_FRAC_EVEN);
    psbc_free_tessellation_output(&out); inputs[1]->info=tcs_info; inputs[2]->info=tes_info;
    inputs[2]->info.tess.point_mode=true;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(G_028B6C_TOPOLOGY(out.runtime.tf_param)==V_028B6C_OUTPUT_POINT);
    psbc_free_tessellation_output(&out); inputs[2]->info=tes_info;
    inputs[1]->info.tess._primitive_mode=inputs[2]->info.tess._primitive_mode=TESS_PRIMITIVE_QUADS;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(G_028B6C_TYPE(out.runtime.tf_param)==V_028B6C_TESS_QUAD);
    psbc_free_tessellation_output(&out); inputs[1]->info=tcs_info; inputs[2]->info=tes_info;
    inputs[1]->info.tess._primitive_mode=inputs[2]->info.tess._primitive_mode=TESS_PRIMITIVE_ISOLINES;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(G_028B6C_TYPE(out.runtime.tf_param)==V_028B6C_TESS_ISOLINE);
    assert(G_028A6C_OUTPRIM_TYPE(context_value(&out.tes.metadata,0x29b))==V_028A6C_LINESTRIP);
    psbc_free_tessellation_output(&out); inputs[1]->info=tcs_info; inputs[2]->info=tes_info;
    inputs[1]->info.tess.ccw=inputs[2]->info.tess.ccw=false;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_OK);
    assert(G_028B6C_TOPOLOGY(out.runtime.tf_param)==V_028B6C_OUTPUT_TRIANGLE_CW);
    psbc_free_tessellation_output(&out); inputs[1]->info=tcs_info; inputs[2]->info=tes_info;
    inputs[0]->info.num_ubos=1;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out); inputs[0]->info.num_ubos=0;
    /* A resource declaration with stale/zero resource counts must also fail. */
    nir_variable* resource=nir_variable_create(inputs[0],nir_var_uniform,glsl_float_type(),"unsupported-uniform");
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out); exec_node_remove(&resource->node);
    nir_variable* attr=nir_variable_create(inputs[0],nir_var_shader_in,glsl_vec4_type(),"unsupported-attribute");
    attr->data.location=VERT_ATTRIB_GENERIC0+1;
    assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
    expect_empty(&out); exec_node_remove(&attr->node);

    /* Mesa hands Gallium lowered I/O; the compiler accepts the exact
     * tessellation intrinsics rather than attempting a lossy round-trip. */
    nir_shader* lowered[3];
    for (unsigned i=0;i<3;++i) {
        lowered[i]=nir_shader_clone(NULL,inputs[i]); assert(lowered[i]);
        nir_lower_io(lowered[i],nir_var_shader_in|nir_var_shader_out,type_size_vec4,0);
        nir_lower_io_to_scalar(lowered[i],nir_var_shader_in|nir_var_shader_out,NULL,NULL);
        nir_opt_dce(lowered[i]);
        nir_opt_vectorize_io(lowered[i],nir_var_shader_in|nir_var_shader_out,false);
        nir_remove_dead_variables(lowered[i],nir_var_shader_in|nir_var_shader_out,NULL);
        lowered[i]->info.io_lowered=true;
        nir_shader_gather_info(lowered[i],nir_shader_get_entrypoint(lowered[i]));
    }
    PsbcResult lowered_result=checked_compile(lowered,&options,&out);
    printf("lowered result=%d\n",lowered_result);
    assert(lowered_result==PSBC_RESULT_OK);
    psbc_free_tessellation_output(&out); expect_empty(&out);
    for (unsigned i=0;i<3;++i) ralloc_free(lowered[i]);

    /* Actual merge rules: TCS-only and TES-only mode declarations both work.
     * OutputVertices may also arrive only in TES. The borrowed shader retains
     * its original, unmerged fields/options on success and on every failure. */
    for (unsigned modes=0;modes<3;++modes) {
        inputs[1]->info=tcs_info; inputs[2]->info=tes_info;
        if (modes==1) {
            inputs[1]->info.tess.spacing=TESS_SPACING_UNSPECIFIED;
            inputs[1]->info.tess._primitive_mode=TESS_PRIMITIVE_UNSPECIFIED;
            inputs[1]->info.tess.ccw=false;
            inputs[1]->info.tess.tcs_vertices_out=0;
            inputs[2]->info.tess.tcs_vertices_out=3;
        } else if (modes==2) {
            inputs[2]->info.tess.spacing=TESS_SPACING_UNSPECIFIED;
            inputs[2]->info.tess._primitive_mode=TESS_PRIMITIVE_UNSPECIFIED;
            inputs[2]->info.tess.ccw=false;
        }
        PsbcResult result=checked_compile(inputs,&options,&out);
        printf("public API %s modes=%u: %s\n",cross ? "cross" : "same",modes,psbc_result_string(result));
        assert(result==PSBC_RESULT_OK);
        PsbcShaderOutput* pair[]={&out.hs,&out.tes};
        assert(out.hs.machine_code!=out.tes.machine_code);
        for (unsigned i=0;i<2;++i) {
            assert(pair[i]->machine_code && pair[i]->machine_code_size);
            assert(!pair[i]->data && !pair[i]->size);
            assert(pair[i]->metadata.source_stage==(i ? PSBC_STAGE_TESS_EVAL : PSBC_STAGE_TESS_CTRL));
            assert(pair[i]->metadata.hardware_stage==(i ? PSBC_HW_STAGE_NGG : PSBC_HW_STAGE_HULL));
            uint8_t* package=NULL; size_t size=0;
            if (i) {
                assert(pair[i]->metadata.linkage_valid);
                assert(pair[i]->metadata.context_register_count);
                assert(pair[i]->metadata.shader_register_count==6);
                assert(G_028B54_LS_EN(pair[i]->metadata.linkage_stages_en.value)==V_028B54_LS_STAGE_ON);
                assert(G_028B54_HS_EN(pair[i]->metadata.linkage_stages_en.value));
                assert(G_028B54_DYNAMIC_HS(pair[i]->metadata.linkage_stages_en.value));
                assert(G_028B54_ES_EN(pair[i]->metadata.linkage_stages_en.value)==V_028B54_ES_STAGE_DS);
                assert(G_028B54_PRIMGEN_EN(pair[i]->metadata.linkage_stages_en.value));
                assert(G_03096C_VERT_GRP_SIZE(pair[i]->metadata.linkage_ge_cntl.value)==0);
                printf("TES metadata stages=%08x ge=%08x context=%u shader=%u ngg-lds=%u/%u\n",
                       pair[i]->metadata.linkage_stages_en.value,
                       pair[i]->metadata.linkage_ge_cntl.value,
                       pair[i]->metadata.context_register_count,
                       pair[i]->metadata.shader_register_count,
                       pair[i]->metadata.ngg_lds_layout_valid,
                       pair[i]->metadata.ngg_lds_layout);
                assert(ps5_agc_package_build(pair[i],0,&package,&size)==0);
                uint64_t sections=0, header_at=0;
                memcpy(&sections,package+40,8);
                memcpy(&header_at,package+sections+2*64+24,8);
                const uint8_t *header=package+header_at;
                assert(header[90]==2);
                free(package);
            } else {
                assert(!pair[i]->metadata.linkage_valid);
                assert(!pair[i]->metadata.context_register_count);
                assert(pair[i]->metadata.shader_register_count==2);
                assert(pair[i]->metadata.base_vertex_valid);
                assert(pair[i]->metadata.is_indexed_draw_valid);
                assert(pair[i]->metadata.base_vertex_user_data_dword <
                       pair[i]->metadata.user_sgpr_count);
                assert(pair[i]->metadata.shader_registers[0].offset==0x148);
                assert(pair[i]->metadata.shader_registers[1].offset==0x10a);
                assert(ps5_agc_package_build(pair[i],0,&package,&size)==0);
                uint64_t sections=0, header_at=0;
                memcpy(&sections,package+40,8);
                memcpy(&header_at,package+sections+2*64+24,8);
                const uint8_t *header=package+header_at;
                assert(header[90]==3 && header[91]==0 && header[92]==2);
                assert(!memcmp(header+96,pair[i]->metadata.shader_registers,
                               2*sizeof(PsbcRegisterWrite)));
                free(package);
            }
        }
        assert(out.runtime.valid && out.runtime.input_patch_vertices==3);
        assert(out.runtime.output_patch_vertices==3 && out.runtime.num_patches==64);
        assert(out.runtime.lds_bytes==4112);
        assert((out.runtime.hs_rsrc2 & S_00B42C_LDS_SIZE_GFX10(10))==
               S_00B42C_LDS_SIZE_GFX10(10));
        assert(out.runtime.ls_hs_config==
               (S_028B58_NUM_PATCHES(64)|S_028B58_HS_NUM_INPUT_CP(3)|
                S_028B58_HS_NUM_OUTPUT_CP(3)));
        assert(out.runtime.tf_param==
               (S_028B6C_TYPE(V_028B6C_TESS_TRIANGLE)|
                S_028B6C_PARTITIONING(V_028B6C_PART_INTEGER)|
                S_028B6C_TOPOLOGY(V_028B6C_OUTPUT_TRIANGLE_CCW)));
        assert(out.runtime.hs_ring_offsets_sgpr==0 &&
               out.runtime.tes_ring_offsets_sgpr==0);
        assert(out.runtime.hs_ring_offsets_register==0x102 &&
               out.runtime.tes_ring_offsets_register==0x082);
        assert(!out.runtime.final_offchip_layout_valid);
        assert(out.runtime.offchip_ring_bytes_per_workgroup==32768);
        assert(out.runtime.tess_factor_ring_bytes_per_workgroup==1024);
        PsbcTessellationOutput owned=out;
        assert(checked_compile(inputs,&options,&out)==PSBC_RESULT_INVALID_ARGUMENT);
        assert(!memcmp(&out,&owned,sizeof(out)));
        if (!modes) { *reference=out; memset(&out,0,sizeof(out)); }
        psbc_free_tessellation_output(&out); expect_empty(&out);
        psbc_free_tessellation_output(&out); expect_empty(&out);
    }
    psbc_free_tessellation_output(NULL);
    for (unsigned i=0;i<3;++i) ralloc_free(inputs[i]);
    puts("PASS public linked tessellation API: ownership, rejection, HS/TES packaging");
}

int main(int argc,char **argv) {
    assert(argc==2); setvbuf(stdout,NULL,_IONBF,0);
    bool cross=!strcmp(argv[1],"cross");
    puts("HOST MODEL: capacity=8192 dwords, address32_hi=2; fixed runtime contract");
    psbc_init();
    struct ac_compiler_info ac={0}; setup_ac_info(&ac,GFX10_3);
    ac.hs_offchip_workgroup_dw_size=8192; /* Hypothetical host capacity; see ac_fill_tess_info. */
    struct radv_compiler_info ci={.ac=&ac};
    ci.key.family=ci.debug.family=CHIP_NAVI21;
    ci.key.ge_wave_size=64; ci.key.ps_wave_size=32; ci.key.use_ngg=true;
    ci.hw.address32_hi=2; radv_get_nir_options(&ci);
    wide_io_tests(&ci,false);
    wide_io_tests(&ci,true);
    PsbcTessellationOutput reference={0};
    api_tests(&ci,cross,&reference);
    struct radv_graphics_state_key gfx={0}; gfx.ts.patch_control_points=3;
    gfx.vi.attributes_valid=1;
    gfx.vi.vertex_attribute_formats[0]=PIPE_FORMAT_R32G32B32_FLOAT;
    gfx.vi.vertex_attribute_strides[0]=12;
    gfx.vi.vertex_binding_align[0]=4;
    struct radv_shader_stage stages[MESA_VULKAN_SHADER_STAGES]={0};
    const mesa_shader_stage ids[]={MESA_SHADER_VERTEX,MESA_SHADER_TESS_CTRL,MESA_SHADER_TESS_EVAL};
    const mesa_shader_stage next[]={MESA_SHADER_TESS_CTRL,MESA_SHADER_TESS_EVAL,MESA_SHADER_FRAGMENT};
    VkShaderStageFlagBits active=0;
    for(unsigned i=0;i<3;++i) {
        struct radv_shader_stage *s=&stages[ids[i]];
        s->stage=ids[i]; s->next_stage=next[i]; s->entrypoint="main";
        s->internal_nir=build(ids[i],cross,&ci);
        const struct radv_spirv_to_nir_options options={.lower_view_index_to_zero=true};
        s->nir=radv_shader_spirv_to_nir(&ci,s,&options,false); assert(s->nir);
        ralloc_free(s->internal_nir); s->internal_nir=NULL;
        NIR_PASS(_,s->nir,nir_normalize_sin_cos);
        radv_optimize_nir(s->nir,false);
        NIR_PASS(_,s->nir,ac_nir_lower_indirect_derefs);
        NIR_PASS(_,s->nir,nir_lower_vars_to_ssa);
        radv_nir_shader_info_init(ids[i],next[i],&s->info);
        active|=1<<ids[i];
    }
    struct radv_shader_stage *vs=&stages[MESA_SHADER_VERTEX], *hs=&stages[MESA_SHADER_TESS_CTRL], *tes=&stages[MESA_SHADER_TESS_EVAL];
    merge_tess_info(&tes->nir->info,&hs->nir->info);
    radv_fill_shader_info_ngg(&ci,stages,active);
    for(unsigned i=0;i<3;++i) {
        nir_shader *n=stages[ids[i]].nir;
        radv_nir_lower_io(n);
        NIR_PASS(_,n,nir_lower_io_to_scalar,nir_var_shader_in|nir_var_shader_out,NULL,NULL);
        NIR_PASS(_,n,nir_opt_copy_prop); NIR_PASS(_,n,nir_opt_constant_folding);
    }
    puts("link-varyings"); radv_graphics_shaders_link_varyings(stages,ac.gfx_level);
    for(unsigned i=0;i<3;++i) {
        struct radv_shader_stage *s=&stages[ids[i]];
        nir_validate_shader(s->nir,"linked IO"); dump(s->nir,"linked");
        radv_nir_shader_info_pass(&ci,s->nir,&s->layout,&s->key,&gfx,RADV_PIPELINE_GRAPHICS,false,&s->info);
    }
    radv_nir_shader_info_link(&ci,&gfx,stages);
    assert(vs->info.vs.as_ls && !vs->info.is_ngg && !hs->info.is_ngg && tes->info.is_ngg);
    assert(vs->info.outputs_linked && hs->info.inputs_linked && hs->info.outputs_linked && tes->info.inputs_linked);
    assert(!vs->info.merged_shader_compiled_separately && !hs->info.merged_shader_compiled_separately);
    assert(vs->info.vs.num_linked_outputs && vs->info.vs.num_linked_outputs==hs->info.tcs.num_linked_inputs);
    assert(hs->info.num_tess_patches && hs->info.num_tess_patches==tes->info.num_tess_patches);
    assert(hs->info.tcs.tcs_vertices_out==3 && tes->info.tes.tcs_vertices_out==3);
    assert(hs->info.tcs.lds_size && hs->info.tcs.lds_size<=ac.lds_size_per_workgroup);
    assert(hs->info.tcs.tes_inputs_read==tes->nir->info.inputs_read);
    assert(hs->info.tcs.tes_patch_inputs_read==tes->nir->info.patch_inputs_read);
    assert(hs->info.vs.tcs_in_out_eq && hs->info.workgroup_size==vs->info.workgroup_size);
    printf("linked slots=%u/%u tes=%u patch=%u patches=%u lds=%u wg=%u temp=%llx lds_mask=%llx\n",
           vs->info.vs.num_linked_outputs,hs->info.tcs.num_linked_inputs,tes->info.tes.num_linked_inputs,
           tes->info.tes.num_linked_patch_inputs,hs->info.num_tess_patches,hs->info.tcs.lds_size,
           hs->info.workgroup_size,(unsigned long long)hs->info.vs.tcs_inputs_via_temp,(unsigned long long)hs->info.vs.tcs_inputs_via_lds);
    assert(cross ? hs->info.vs.tcs_inputs_via_lds!=0 : hs->info.vs.tcs_inputs_via_temp!=0);
    assert(cross ? tes->info.tes.num_linked_patch_inputs!=0 : tes->info.tes.num_linked_patch_inputs==0);
    unsigned footprint=get_tcs_wg_output_mem_size(3,hs->info.tcs.io_info.highest_remapped_vram_output,
        hs->info.tcs.io_info.highest_remapped_vram_patch_output,hs->info.num_tess_patches);
    assert(footprint && footprint<=ac.hs_offchip_workgroup_dw_size*4);
    struct radv_shader_debug_info debug[MESA_VULKAN_SHADER_STAGES]={0};
    radv_declare_pipeline_args(&ci,stages,&gfx,active,debug);
    assert(!memcmp(&vs->args,&hs->args,sizeof(vs->args)));
    assert(!hs->args.ac.tcs_offchip_layout.used && !tes->args.ac.tcs_offchip_layout.used);
    assert(hs->args.ac.ring_offsets.used && tes->args.ac.ring_offsets.used);
    assert(hs->args.ac.args[hs->args.ac.ring_offsets.arg_index].offset==0 &&
           tes->args.ac.args[tes->args.ac.ring_offsets.arg_index].offset==0);
    assert(tes->args.ac.args[tes->args.ngg_lds_layout.arg_index].offset==8);
    printf("ring ABI hs arg=%u off=%u users=%u tes arg=%u off=%u users=%u ngg-layout arg=%u off=%u ud=%d\n",
           hs->args.ac.ring_offsets.arg_index,
           hs->args.ac.args[hs->args.ac.ring_offsets.arg_index].offset,
           hs->args.num_user_sgprs,
           tes->args.ac.ring_offsets.arg_index,
           tes->args.ac.args[tes->args.ac.ring_offsets.arg_index].offset,
           tes->args.num_user_sgprs,
           tes->args.ngg_lds_layout.arg_index,
           tes->args.ac.args[tes->args.ngg_lds_layout.arg_index].offset,
           tes->args.user_sgprs_locs.shader_data[AC_UD_NGG_LDS_LAYOUT].sgpr_idx);
    assert(hs->args.num_user_sgprs==3 && tes->args.num_user_sgprs==1);
    assert(hs->args.ac.merged_wave_info.used && hs->args.ac.tcs_factor_offset.used);
    unsigned abi[3][3]={{0}};
    for(unsigned i=0;i<3;++i) abi_constants(&ci,&gfx,&stages[ids[i]],abi[i]);
    assert(abi[0][0] && abi[0][0]==abi[1][0]);
    assert(abi[1][1] && !(abi[1][1]&255) && abi[1][1]==abi[2][1]);
    assert(abi[1][2] && abi[1][2]==abi[2][2]);
    printf("actual ABI constants: LS/HS stride=%u HS/TES attribute=%u patch_offset=%u footprint=%u\n",
           abi[0][0],abi[1][1],abi[1][2],footprint);
    for(unsigned i=0;i<3;++i) {
        struct radv_shader_stage io=stages[ids[i]];
        io.nir=nir_shader_clone(NULL,io.nir);
        assert(radv_nir_lower_io_to_mem(&ci,&io));
        nir_validate_shader(io.nir,"actual tess IO to memory"); dump(io.nir,"io-memory");
        if(i==0 && cross) assert(count(io.nir,nir_intrinsic_store_shared));
        if(i==1) {
            assert(ring_access(io.nir,nir_intrinsic_store_buffer_amd,nir_intrinsic_load_ring_tess_offchip_amd));
            assert(ring_access(io.nir,nir_intrinsic_store_buffer_amd,nir_intrinsic_load_ring_tess_factors_amd));
            if(cross) assert(count(io.nir,nir_intrinsic_load_shared));
        }
        if(i==2) assert(ring_access(io.nir,nir_intrinsic_load_buffer_amd,nir_intrinsic_load_ring_tess_offchip_amd));
        ralloc_free(io.nir);
    }
    puts("postprocess");
    for(unsigned i=0;i<3;++i) {
        struct radv_shader_stage *s=&stages[ids[i]];
        radv_postprocess_nir(&ci,&gfx,s); nir_validate_shader(s->nir,"postprocess"); dump(s->nir,"final");
        /* ac_nir filter_load_tcs_per_vertex_input intentionally retains the
         * same-invocation temp path; ACO load_input_from_temps consumes it.
         * Only the linked TCS temp-mask locations with constant IO offsets
         * are allowed to remain. LDS/TES inputs must have been lowered. */
        if(i==1 && !cross) {
            assert(count(s->nir,nir_intrinsic_load_per_vertex_input));
            nir_foreach_function_impl(impl,s->nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr *input=nir_instr_as_intrinsic(instr);
                if(input->intrinsic!=nir_intrinsic_load_per_vertex_input) continue;
                assert(s->info.vs.tcs_in_out_eq);
                assert(s->info.vs.tcs_inputs_via_temp & BITFIELD64_BIT(nir_intrinsic_io_semantics(input).location));
                assert(nir_src_is_const(*nir_get_io_offset_src(input)));
            }
        } else assert(!count(s->nir,nir_intrinsic_load_per_vertex_input));
        assert(!count(s->nir,nir_intrinsic_store_per_vertex_output));
        assert(!count(s->nir,nir_intrinsic_load_ring_tess_offchip_amd));
        assert(!count(s->nir,nir_intrinsic_load_ring_tess_factors_amd));
    }
    assert(cross ? !count(vs->nir,nir_intrinsic_store_output) : count(vs->nir,nir_intrinsic_store_output)>0);
    gfx10_get_ngg_info(&ci,&tes->info,NULL,&tes->info.ngg_info);
    tes->info.nir_shared_size=tes->info.ngg_info.lds_size;
    nir_shader *merged[]={vs->nir,hs->nir};
    puts("ACO merged VS+TCS count=2");
    struct radv_shader_binary *hs_binary=radv_shader_nir_to_asm(&ci,hs,merged,2,&gfx); assert(hs_binary);
    puts("ACO TES count=1 NGG");
    struct radv_shader_binary *tes_binary=radv_shader_nir_to_asm(&ci,tes,&tes->nir,1,&gfx); assert(tes_binary);
    struct radv_shader_binary_legacy *hb=(void *)hs_binary, *tb=(void *)tes_binary;
    assert(hb->code_size && hb->exec_size && tb->code_size && tb->exec_size);
    assert(reference.hs.machine_code_size==hb->code_size);
    assert(reference.tes.machine_code_size==tb->code_size);
    assert(!memcmp(reference.hs.machine_code,hb->data+hb->stats_size,hb->code_size));
    assert(!memcmp(reference.tes.machine_code,tb->data+tb->stats_size,tb->code_size));
    psbc_free_tessellation_output(&reference);
    puts("PASS public API matches extracted RADV reference code byte-for-byte");
    assert(radv_select_hw_stage(&hs->info,ac.gfx_level)==AC_HW_HULL_SHADER);
    assert(radv_select_hw_stage(&tes->info,ac.gfx_level)==AC_HW_NEXT_GEN_GEOMETRY_SHADER);
    printf("PASS %s: linked merged2 HS=%u bytes TES/NGG=%u bytes; runtime state pinned\n",argv[1],hb->code_size,tb->code_size);
    free(hs_binary); free(tes_binary);
    for(unsigned i=0;i<3;++i) ralloc_free(stages[ids[i]].nir);
    psbc_shutdown(); return 0;
}
'''


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, log, timeout, cwd):
    with log.open("w") as stream:
        stream.write("command: " + repr(command) + "\n")
        stream.flush()
        try:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout, env={**os.environ, "NIR_DEBUG": "validate"})
            status = result.returncode
        except subprocess.TimeoutExpired:
            status = 124
        stream.write(f"\nexit={status}\n")
    print(str(log) + "\n" + "\n".join(log.read_text().splitlines()[1:]), flush=True)
    return status


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with tempfile.TemporaryDirectory(prefix="linked-tess-") as directory:
        attempt = Path(directory)
        print("Linked tessellation compiler regression (host only)", flush=True)
        before = digest(LIB)
        (attempt / "archive.sha256").write_text(before + "  " + str(LIB) + "\n")
        cfile = attempt / "probe.c"
        cfile.write_text(code)
        obj, executable = attempt / "probe.o", attempt / "probe"
        command = ["clang-18", "-std=gnu11", "-O1", "-g", "-Wall", "-Werror",
                   "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-DHAVE_PTHREAD=1",
                   "-DHAVE_STRUCT_TIMESPEC=1", "-DHAVE_FUNC_ATTRIBUTE_UNUSED=1", "-D_GNU_SOURCE"]
        for include in ("include/mesa", "include", "src", "libpsbc", "src/amd/vulkan",
                        "src/amd/common", "src/compiler/nir", "src/amd/compiler", "src/compiler",
                        "src/amd/common/nir", "src/vulkan/runtime", "src/vulkan/util", "../Vulkan-Headers/include"):
            command += ["-I", str(PSBC / include)]
        command += ["-I", str(ROOT / "src/platform")]
        status = run(command + ["-c", str(cfile), "-o", str(obj)], attempt / "compile.log", 45, attempt)
        package_obj = attempt / "package.o"
        if not status:
            status = run(command + ["-c", str(ROOT / "src/platform/ps5_agc_package.c"),
                                    "-o", str(package_obj)], attempt / "package-compile.log", 45, attempt)
        if not status:
            status = run(["g++", "-o", str(executable), str(obj), str(package_obj), str(LIB), "-pthread", "-lm"],
                         attempt / "link.log", 45, attempt)
        if not status:
            for variant in ("same", "cross"):
                directory = attempt / variant
                directory.mkdir()
                status |= run([str(executable), variant], directory / "run.log", 30, directory)
        assert digest(LIB) == before, "host archive changed during probe"
        print(f"RESULT exit={status}; archive unchanged (host only)", flush=True)
        sys.exit(1 if status else 0)
