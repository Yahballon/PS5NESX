#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check stage-local buffer banks and real NIR/ACO compilation without a GPU."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PSBC = ROOT / "third_party/opengnm-psbc"
source = (PSBC / "libpsbc/psbc_compile.c").read_text()
start = source.index("struct gallium_buffer_state {")
lowering = source[start:source.index("static bool lower_gallium_texture_index", start)]
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "util/format/u_format.h"
#include "psbc_compile.h"
''' + lowering + r'''
static PsbcCompileOptions options(PsbcStage stage) {
    return (PsbcCompileOptions) {
        .target=PSBC_TARGET_PS5, .stage=stage, .entrypoint="main",
        .optimise=true, .address32_hi=2, .gallium_buffer_arrays=true,
        .descriptor_binding_count=2,
        .descriptor_bindings={
            {.binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(stage),
             .type=PSBC_DESCRIPTOR_UNIFORM_BUFFER, .array_size=15, .stride=16},
            {.binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(stage),
             .type=PSBC_DESCRIPTOR_STORAGE_BUFFER, .array_size=16,
             .offset=15*16, .stride=16}},
    };
}
static nir_def *resource(nir_builder *b, PsbcStage stage, nir_def *slot,
                         bool ubo, bool manual) {
    if (!manual) return slot;
    return nir_vulkan_resource_index(b, 3, 32, slot,
        .desc_set=0, .binding=ubo ? PSBC_GALLIUM_UBO_ARRAY_BINDING(stage)
                                 : PSBC_GALLIUM_SSBO_ARRAY_BINDING(stage),
        .desc_type=ubo ? nir_descriptor_type_uniform_buffer : nir_descriptor_type_storage_buffer,
        .resource_type=ubo ? nir_resource_type_uniform_buffer : nir_resource_type_read_write_storage_buffer);
}
static nir_shader *shader(PsbcStage stage, bool manual, bool dynamic, unsigned fixed_slot) {
    nir_builder b = nir_builder_init_simple_shader((mesa_shader_stage)(stage-1),
        psbc_get_nir_options(stage), "buffer-bank-contract");
    b.shader->info.workgroup_size[0]=16;
    b.shader->info.workgroup_size[1]=b.shader->info.workgroup_size[2]=1;
    b.shader->info.num_ubos=15;
    b.shader->info.num_ssbos=16;
    nir_def *slot = dynamic ? nir_iand_imm(&b,
        nir_channel(&b, nir_load_workgroup_id(&b), 0), 1) : nir_imm_int(&b, fixed_slot);
    nir_def *u = resource(&b, stage, slot, true, manual);
    nir_def *s = resource(&b, stage, slot, false, manual);
    nir_def *zero=nir_imm_int(&b, 0), *one=nir_imm_int(&b, 1);
    nir_def *value = nir_load_ubo(&b, 1, 32, u, zero,
        .align_mul=4, .range=4);
    value=nir_iadd(&b, value, nir_load_ssbo(&b, 1, 32, s, zero, .align_mul=4));
    value=nir_iadd(&b, value, nir_get_ssbo_size(&b, 32, s));
    value=nir_iadd(&b, value, nir_ssbo_atomic(&b, 32, s, nir_imm_int(&b, 4), one,
        .atomic_op=nir_atomic_op_iadd));
    value=nir_iadd(&b, value, nir_ssbo_atomic_swap(&b, 32, s, nir_imm_int(&b, 8),
        zero, one, .atomic_op=nir_atomic_op_cmpxchg));
    nir_store_ssbo(&b, value, s, zero, .align_mul=4, .write_mask=1);
    nir_validate_shader(b.shader, "buffer bank input");
    return b.shader;
}
static void structural(void) {
    PsbcCompileOptions texture_opts={0};
    texture_opts.descriptor_binding_count=16;
    for(unsigned i=0;i<16;++i)
        texture_opts.descriptor_bindings[i]=(PsbcDescriptorBinding){
            .binding=i,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,
            .array_size=1,.offset=i*48,.stride=48};
    assert(contiguous_sampler_count(&texture_opts,&texture_opts.descriptor_bindings[0])==16);
    texture_opts.descriptor_bindings[8].offset+=48;
    assert(contiguous_sampler_count(&texture_opts,&texture_opts.descriptor_bindings[0])==8);
    unsigned keys=0;
    for (PsbcStage stage=PSBC_STAGE_VERTEX; stage<=PSBC_STAGE_COMPUTE; ++stage) {
        PsbcCompileOptions opts=options(stage);
        nir_shader *nir=shader(stage, false, false, 1);
        struct gallium_buffer_state state={.options=&opts, .valid=true};
        assert(nir_shader_instructions_pass(nir, lower_gallium_buffer_index,
            nir_metadata_control_flow, &state) && state.valid);
        nir_validate_shader(nir, "buffer bank output");
        unsigned ubos=0, ssbos=0;
        nir_foreach_function_impl(impl, nir) nir_foreach_block(block, impl)
        nir_foreach_instr(instr, block) {
            if (instr->type != nir_instr_type_intrinsic) continue;
            nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
            if (intr->intrinsic != nir_intrinsic_vulkan_resource_index) continue;
            unsigned binding=nir_intrinsic_binding(intr);
            assert(binding<24 && nir_src_as_uint(intr->src[0])==1);
            if (binding==PSBC_GALLIUM_UBO_ARRAY_BINDING(stage)) ++ubos;
            else { assert(binding==PSBC_GALLIUM_SSBO_ARRAY_BINDING(stage)); ++ssbos; }
        }
        assert(ubos==1 && ssbos==5);
        unsigned bank_keys=(1u<<opts.descriptor_bindings[0].binding) |
                           (1u<<opts.descriptor_bindings[1].binding);
        assert(!(keys & bank_keys));
        keys |= bank_keys;
        assert(!nir_shader_instructions_pass(nir, lower_gallium_buffer_index,
            nir_metadata_control_flow, &state) && state.valid);
        ralloc_free(nir);
    }
}
static void compiled(bool dynamic, unsigned fixed_slot, PsbcShaderOutput *saved) {
    PsbcCompileOptions opts=options(PSBC_STAGE_COMPUTE);
    nir_shader *scalar=shader(opts.stage, false, dynamic, fixed_slot);
    nir_shader *manual=shader(opts.stage, true, dynamic, fixed_slot);
    PsbcShaderOutput a={0}, b={0};
    assert(psbc_compile_nir(scalar, &opts, &a)==PSBC_RESULT_OK);
    opts.gallium_buffer_arrays=false;
    assert(psbc_compile_nir(manual, &opts, &b)==PSBC_RESULT_OK);
    assert(a.metadata.version==PSBC_SHADER_METADATA_VERSION && a.machine_code_size);
    assert(a.machine_code_size==b.machine_code_size &&
           !memcmp(a.machine_code, b.machine_code, a.machine_code_size));
    assert(a.metadata.descriptor_binding_count==2 && a.metadata.descriptor_set0_valid);
    assert(!a.metadata.scratch_valid);
    printf("buffer arrays: dynamic=%u code=%zu matches explicit resource tuples\n",
        dynamic, a.machine_code_size);
    if (saved) *saved=a; else psbc_free_output(&a);
    psbc_free_output(&b);
    ralloc_free(scalar); ralloc_free(manual);
}
static void invalid(void) {
    for (unsigned fault=0; fault<6; ++fault) {
        PsbcCompileOptions opts=options(PSBC_STAGE_COMPUTE);
        nir_shader *nir=shader(opts.stage, false, false, 1);
        if (fault==0) {
            opts.gallium_buffer_arrays=false; /* Valid flat UBO, unsupported scalar SSBO. */
            opts.descriptor_bindings[0].binding=PSBC_GALLIUM_UBO_BINDING_BASE+1;
        }
        if (fault==1) opts.descriptor_binding_count=1;  /* Missing storage bank. */
        if (fault==2) opts.descriptor_bindings[1].type=PSBC_DESCRIPTOR_UNIFORM_BUFFER;
        if (fault==3) opts.descriptor_bindings[1].array_size=1; /* Slot 1 out of range. */
        if (fault==4) opts.descriptor_bindings[0].array_size=1;
        if (fault==5) opts.stage=PSBC_STAGE_FRAGMENT; /* Mismatched input stage. */
        PsbcShaderOutput out={0};
        assert(psbc_compile_nir(nir, &opts, &out)==
            (fault==5 ? PSBC_RESULT_UNSUPPORTED_STAGE : PSBC_RESULT_COMPILE_NIR));
        assert(!out.data && !out.machine_code && !out.size && !out.machine_code_size);
        ralloc_free(nir);
    }
}
static nir_shader *image_shader(unsigned operation, bool dynamic, bool manual, enum pipe_format format, bool array) {
    nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
        psbc_get_nir_options(PSBC_STAGE_COMPUTE), "image-bank-contract");
    b.shader->info.workgroup_size[0]=16;
    b.shader->info.workgroup_size[1]=b.shader->info.workgroup_size[2]=1;
    b.shader->info.num_images=8;
    b.shader->info.num_ssbos=16;
    const nir_alu_type type=util_format_is_pure_uint(format) ? nir_type_uint32 :
        util_format_is_pure_sint(format) ? nir_type_int32 : nir_type_float32;
    const enum glsl_base_type base_type=util_format_is_pure_uint(format) ? GLSL_TYPE_UINT :
        util_format_is_pure_sint(format) ? GLSL_TYPE_INT : GLSL_TYPE_FLOAT;
    nir_def *zero=nir_imm_int(&b,0), *id=nir_channel(&b,nir_load_local_invocation_id(&b),0);
    nir_def *slot=dynamic ? nir_iand_imm(&b,nir_channel(&b,nir_load_workgroup_id(&b),0),7)
                          : nir_imm_int(&b,7);
    nir_def *coord=nir_vec4(&b,id,zero,array ? nir_iand_imm(&b,id,3) : zero,zero);
    nir_def *value=nir_iadd_imm(&b,id,17), *result=NULL;
    const enum glsl_sampler_dim dim=operation==5 ? GLSL_SAMPLER_DIM_MS : GLSL_SAMPLER_DIM_2D;
    switch(operation) {
    case 0: result=nir_image_load(&b,4,32,slot,coord,zero,zero,
        .image_dim=GLSL_SAMPLER_DIM_2D,.image_array=array,.format=format,.dest_type=type); break;
    case 1: nir_image_store(&b,slot,coord,zero,nir_vec4(&b,value,zero,zero,zero),zero,
        .image_dim=GLSL_SAMPLER_DIM_2D,.image_array=array,.format=format,.src_type=type); break;
    case 2: result=nir_image_atomic(&b,32,slot,coord,zero,value,
        .image_dim=GLSL_SAMPLER_DIM_2D,.image_array=array,.format=format,
        .atomic_op=format==PIPE_FORMAT_R32_FLOAT ? nir_atomic_op_fadd : nir_atomic_op_iadd); break;
    case 3: result=nir_image_atomic_swap(&b,32,slot,coord,zero,zero,value,
        .image_dim=GLSL_SAMPLER_DIM_2D,.image_array=array,.format=format,.atomic_op=nir_atomic_op_cmpxchg); break;
    case 4: result=nir_image_size(&b,array ? 3 : 2,32,slot,zero,
        .image_dim=GLSL_SAMPLER_DIM_2D,.image_array=array,.format=format); break;
    case 5: result=nir_image_samples(&b,32,slot,
        .image_dim=GLSL_SAMPLER_DIM_MS,.image_array=array,.format=PIPE_FORMAT_NONE); break;
    }
    if(result) nir_store_ssbo(&b,nir_channel(&b,result,0),nir_imm_int(&b,15),
        nir_imul_imm(&b,id,4),.write_mask=1,.align_mul=4);
    if(manual) {
        nir_foreach_function_impl(impl,b.shader) nir_foreach_block(block,impl)
        nir_foreach_instr_safe(instr,block) {
            if(instr->type!=nir_instr_type_intrinsic) continue;
            nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
            if(!nir_intrinsic_has_image_dim(intr)) continue;
            b.cursor=nir_before_instr(instr);
            const glsl_type *type=glsl_array_type(glsl_image_type(dim,array,base_type),8,0);
            nir_variable *var=nir_variable_create(b.shader,nir_var_image,type,"manual-image-array");
            var->data.binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(PSBC_STAGE_COMPUTE);
            var->data.image.format=operation==5 ? PIPE_FORMAT_NONE : format;
            nir_rewrite_image_intrinsic(intr,&nir_build_deref_array(&b,nir_build_deref_var(&b,var),slot)->def,
                nir_image_intrinsic_type_deref);
        }
    }
    nir_validate_shader(b.shader,"image contract input");
    return b.shader;
}
static void image_contract(void) {
    PsbcCompileOptions opts=options(PSBC_STAGE_COMPUTE);
    opts.descriptor_binding_count=3;
    opts.descriptor_bindings[2]=(PsbcDescriptorBinding){
        .binding=PSBC_GALLIUM_IMAGE_ARRAY_BINDING(PSBC_STAGE_COMPUTE),
        .type=PSBC_DESCRIPTOR_STORAGE_IMAGE,.array_size=8,.offset=31*16,.stride=32};
    const enum pipe_format formats[]={PIPE_FORMAT_R32_UINT,PIPE_FORMAT_R32_SINT,PIPE_FORMAT_R32_FLOAT,
        PIPE_FORMAT_R32G32_UINT,PIPE_FORMAT_R32G32_SINT,PIPE_FORMAT_R32G32_FLOAT,
        PIPE_FORMAT_R32G32B32A32_UINT,PIPE_FORMAT_R32G32B32A32_SINT,PIPE_FORMAT_R32G32B32A32_FLOAT,
        PIPE_FORMAT_R16G16B16A16_UINT,PIPE_FORMAT_R16G16B16A16_SINT,PIPE_FORMAT_R16G16B16A16_FLOAT};
    for(unsigned array=0;array<2;++array)
    for(unsigned f=0;f<ARRAY_SIZE(formats);++f) for(unsigned op=0;op<5;++op) for(unsigned dynamic=0;dynamic<2;++dynamic) {
        if(f>=2 && (op==2 || op==3)) continue; /* Scalar integer atomics only. */
        PsbcShaderOutput out[2]={{0}};
        for(unsigned manual=0;manual<2;++manual) {
            nir_shader *nir=image_shader(op,dynamic,manual,formats[f],array);
            assert(psbc_compile_nir(nir,&opts,&out[manual])==PSBC_RESULT_OK);
            assert(!out[manual].metadata.scratch_valid && out[manual].metadata.descriptor_set0_valid);
            ralloc_free(nir);
        }
        assert(out[0].machine_code_size==out[1].machine_code_size);
        assert(!memcmp(out[0].machine_code,out[1].machine_code,out[0].machine_code_size));
        printf("Image compiler array=%u format=%u op=%u dynamic=%u code=%zu matches deref reference\n",array,formats[f],op,dynamic,out[0].machine_code_size);
        psbc_free_output(&out[0]); psbc_free_output(&out[1]);
    }
    for(unsigned array=0;array<2;++array) for(unsigned dynamic=0;dynamic<2;++dynamic) {
        PsbcShaderOutput out[2]={{0}};
        for(unsigned manual=0;manual<2;++manual) {
            nir_shader *nir=image_shader(5,dynamic,manual,PIPE_FORMAT_R32_FLOAT,array);
            assert(psbc_compile_nir(nir,&opts,&out[manual])==PSBC_RESULT_OK);
            ralloc_free(nir);
        }
        assert(out[0].machine_code_size==out[1].machine_code_size);
        assert(!memcmp(out[0].machine_code,out[1].machine_code,out[0].machine_code_size));
        psbc_free_output(&out[0]); psbc_free_output(&out[1]);
    }
    for(unsigned fault=0;fault<7;++fault) {
        PsbcCompileOptions bad=opts;
        nir_shader *nir=image_shader(fault>=6 ? 2 : 0,false,false,
            fault==6 ? PIPE_FORMAT_R32_FLOAT : PIPE_FORMAT_R32_UINT,false);
        if(fault==0) bad.gallium_buffer_arrays=false;
        if(fault==1) bad.descriptor_binding_count=2;
        if(fault==2) bad.descriptor_bindings[2].array_size=7;
        if(fault==3) bad.descriptor_bindings[2].stride=16;
        if(fault>=4 && fault<=5) {
            nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl)
            nir_foreach_instr(instr,block) {
                if(instr->type!=nir_instr_type_intrinsic) continue;
                nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
                if(intr->intrinsic!=nir_intrinsic_image_load) continue;
                /* Multisample images are supported now; keep real negatives. */
                if(fault==4) nir_intrinsic_set_image_dim(intr,GLSL_SAMPLER_DIM_EXTERNAL);
                if(fault==5) nir_intrinsic_set_format(intr,PIPE_FORMAT_R64_UINT);
            }
        }
        /* Exercise the actual boundary independently, before whole-shader optimization. */
        struct gallium_buffer_state state={.options=&bad,.valid=true};
        if(fault!=3) {
            assert(!nir_shader_instructions_pass(nir,lower_gallium_image_index,
                nir_metadata_control_flow,&state));
            assert(!state.valid);
        }
        PsbcShaderOutput out={0};
        assert(psbc_compile_nir(nir,&bad,&out)!=PSBC_RESULT_OK);
        assert(!out.data && !out.machine_code);
        ralloc_free(nir);
    }
}
static void fragment_storage(void) {
    for (unsigned atomic=0; atomic<2; ++atomic) for (unsigned slot=0; slot<=15; slot+=15) {
        PsbcShaderOutput out[2]={{0}};
        PsbcCompileOptions opts=options(PSBC_STAGE_FRAGMENT);
        for (unsigned manual=0; manual<2; ++manual) {
            nir_builder b=nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
                psbc_get_nir_options(PSBC_STAGE_FRAGMENT), "fragment-storage");
            b.shader->info.num_ssbos=16;
            nir_def *buffer=resource(&b,PSBC_STAGE_FRAGMENT,nir_imm_int(&b,slot),false,manual);
            nir_def *value=nir_load_ssbo(&b,1,32,buffer,nir_imm_int(&b,0),.align_mul=4);
            if(atomic)
                value=nir_ssbo_atomic(&b,32,buffer,nir_imm_int(&b,4),nir_imm_int(&b,1),.atomic_op=nir_atomic_op_iadd);
            else
                nir_store_ssbo(&b,value,buffer,nir_imm_int(&b,4),.align_mul=4,.write_mask=1);
            nir_variable *color=nir_variable_create(b.shader,nir_var_shader_out,glsl_vec4_type(),"color");
            color->data.location=FRAG_RESULT_DATA0;
            nir_store_var(&b,color,nir_vec4(&b,nir_u2f32(&b,value),nir_imm_float(&b,0),
                nir_imm_float(&b,0),nir_imm_float(&b,1)),15);
            nir_shader_gather_info(b.shader,nir_shader_get_entrypoint(b.shader));
            b.shader->info.num_ssbos=16;
            assert(b.shader->info.writes_memory);
            nir_validate_shader(b.shader,"fragment storage input");
            assert(psbc_compile_nir(b.shader,&opts,&out[manual])==PSBC_RESULT_OK);
            assert(out[manual].metadata.descriptor_set0_valid && !out[manual].metadata.scratch_valid);
            ralloc_free(b.shader);
        }
        assert(out[0].machine_code_size==out[1].machine_code_size);
        assert(!memcmp(out[0].machine_code,out[1].machine_code,out[0].machine_code_size));
        printf("Fragment storage atomic=%u slot=%u code=%zu matches resource-index reference\n",
            atomic,slot,out[0].machine_code_size);
        psbc_free_output(&out[0]); psbc_free_output(&out[1]);
    }
}
int main(void) {
    PsbcShaderOutput fixed[2]={{0}};
    psbc_init(); structural(); compiled(false,0,&fixed[0]); compiled(false,1,&fixed[1]);
    assert(fixed[0].machine_code_size==fixed[1].machine_code_size &&
           memcmp(fixed[0].machine_code,fixed[1].machine_code,fixed[0].machine_code_size));
    psbc_free_output(&fixed[0]); psbc_free_output(&fixed[1]);
    compiled(true,0,NULL); invalid(); image_contract(); fragment_storage(); psbc_shutdown();
}
'''
with tempfile.TemporaryDirectory() as directory:
    obj = str(Path(directory) / "buffers.o")
    executable = str(Path(directory) / "buffers")
    subprocess.run(["clang-18", "-std=gnu11", "-Wall", "-Werror",
        "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1", "-DHAVE_PTHREAD=1",
        "-DHAVE_STRUCT_TIMESPEC=1", "-D_GNU_SOURCE",
        "-I", str(PSBC / "include/mesa"), "-I", str(PSBC / "include"),
        "-I", str(PSBC / "src"), "-I", str(PSBC / "libpsbc"),
        "-x", "c", "-c", "-o", obj, "-"], input=code, text=True, check=True)
    subprocess.run(["g++", "-o", executable, obj, str(PSBC / "libpsbc.a"),
        "-pthread", "-lm"], check=True)
    subprocess.run([executable], check=True, timeout=30)
print("PASS: six-stage buffer/image banks, scalar/dynamic image operations, reference codegen and clean failures")
