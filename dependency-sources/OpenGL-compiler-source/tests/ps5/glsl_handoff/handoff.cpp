// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

// Compiler-only prototype. No EGL context, renderer, native submission, or public caps.
#include "standalone.cpp"
#include "state_tracker/st_context.h"
#include "state_tracker/st_nir.h"
#include "psbc_compile.h"
#include "compiler/nir/nir_builder.h"
#include "compiler/glsl/gl_nir.h"
#include "compiler/nir/nir_serialize.h"
#include "util/blob.h"
#include <cassert>
#include "varying.inc"

extern "C" const size_t *mesa_abi(void);
#ifndef PS5_GLSL_PRIVATE_TEST
#define PS5_GLSL_PRIVATE_TEST 0
#endif

static const char *fixtures[] = {
#if PS5_GLSL_PRIVATE_TEST
#define PRIVATE_SOURCE(N) \
   "#version 430\nlayout(local_size_x=2,local_size_y=2,local_size_z=4) in;\n" \
   "layout(std430,binding=0) buffer Output { uint result[]; };\n" \
   "layout(std430,binding=1) readonly buffer Input { uint data[]; };\n" \
   "void main() { uint id=gl_LocalInvocationIndex+16u*(gl_WorkGroupID.x+" \
   "gl_NumWorkGroups.x*(gl_WorkGroupID.y+gl_NumWorkGroups.y*gl_WorkGroupID.z));" \
   "uint values[" #N "]; uint seed=data[3u*id+2u];" \
   "uint w=data[3u*id]%" #N "u, r=data[3u*id+1u]%" #N "u;" \
   "for(uint i=0u;i<" #N "u;++i) values[i]=seed^(17u+37u*i);" \
   "values[w]=seed+991u; result[id]=values[r]; }\n"
   PRIVATE_SOURCE(64), PRIVATE_SOURCE(256), PRIVATE_SOURCE(1024),
#undef PRIVATE_SOURCE
#else
   "#version 430\nlayout(local_size_x=1) in; uniform uint addend;\n"
   "layout(std140,binding=0) uniform Input { uint value; };\n"
   "layout(std430,binding=0) buffer Output { uint result; };\n"
   "void main() { result = value + addend; }\n",
   "#version 430\nlayout(local_size_x=1) in;\n"
   "layout(std140,binding=0) uniform Input { uint value; };\n"
   "layout(std430,binding=0) buffer Output { uint result; };\n"
   "void main() { result = value; }\n",
   "#version 430\nlayout(local_size_x=1) in;\n"
   "layout(binding=0) uniform sampler2D src;\n"
   "layout(std430,binding=0) buffer Output { float result; };\n"
   "void main() { result = texture(src, vec2(0.5)).x; }\n",
#endif
};

int main() {
   FILE *contract=fopen("contract.bin","rb");
   assert(contract);
   size_t abi[22];
   assert(fread(abi,sizeof(abi),1,contract)==1);
   for(unsigned i=0;i<22;++i) {
      if(mesa_abi()[i]!=abi[i]) {
         fprintf(stderr,"ABI mismatch field %u: Mesa=%zu PSBC=%zu\n",i,mesa_abi()[i],abi[i]);
         return 3;
      }
   }
   puts("PASS 22 NIR ABI sizes/offsets/enums across frontend and PSBC headers");
   nir_shader_compiler_options backend_options;
   assert(fread(&backend_options,sizeof(backend_options),1,contract)==1);
   assert(fgetc(contract)==EOF);
   fclose(contract);
   assert(!backend_options.varying_expression_max_cost);
   assert(!backend_options.lower_to_scalar_filter && !backend_options.lower_mediump_io &&
          !backend_options.lower_convert_alu_types && !backend_options.varying_estimate_instr_cost &&
          !backend_options.max_offset_shift && !backend_options.cb_data);
   backend_options.varying_expression_max_cost=ac_nir_varying_expression_max_cost;
   FILE *layout=fopen("fixtures.txt","w"); assert(layout);
   for (unsigned fixture=0; fixture<3; ++fixture) {
      gl_context ctx = {};
      const standalone_options settings = {.glsl_version=430};
      options = &settings;
      initialize_context(&ctx, API_OPENGL_CORE);
      // This is Mesa's private standalone language environment, never a PS5 screen.
      ctx.screen->nir_options[MESA_SHADER_COMPUTE] = &backend_options;
      ctx.Const.Program[MESA_SHADER_COMPUTE].MaxShaderStorageBlocks = 8;
      ctx.Const.MaxCombinedShaderStorageBlocks = 8;
      ctx.Const.Program[MESA_SHADER_COMPUTE].MaxUniformBlocks = 14;
      ctx.Const.MaxCombinedUniformBlocks = 14;
      ctx.Const.NativeIntegers = true;
      ctx.Const.PackedDriverUniformStorage = false;
      gl_shader_program *program = standalone_create_shader_program();
      gl_shader *shader = standalone_add_shader_source(&ctx, program, GL_COMPUTE_SHADER, fixtures[fixture]);
      _mesa_glsl_compile_shader(&ctx, shader, nullptr, false, false, true);
      if (!shader->CompileStatus) { fprintf(stderr,"parse[%u]: %s\n",fixture,shader->InfoLog); return 1; }
      program->data->LinkStatus = LINKING_SUCCESS;
      link_shaders_init(&ctx, program);
      if (!gl_nir_link_glsl(&ctx, program)) { fprintf(stderr,"link[%u]: %s\n",fixture,program->data->InfoLog); return 2; }
      gl_program *prog = program->_LinkedShaders[MESA_SHADER_COMPUTE]->Program;
      nir_shader *nir = prog->nir;
      char binding_name[48];
      snprintf(binding_name,sizeof(binding_name),"fixture-%u-ssbo.txt",fixture);
      FILE *bindings=fopen(binding_name,"w"); assert(bindings);
      for(unsigned i=0;i<prog->info.num_ssbos;++i)
         fprintf(bindings,"%u\n",prog->sh.ShaderStorageBlocks[i]->Binding);
      assert(fclose(bindings)==0);
      printf("linked[%u]: uniforms=%u params=%u ubos=%u default=%u\n",fixture,
             nir->num_uniforms,prog->Parameters->NumParameterValues,nir->info.num_ubos,nir->info.first_ubo_is_default_ubo);
      // Explicit partial boundary: real linker and finalizer, not st_link_shader/variant capture.
      gl_nir_lower_buffers(nir, program);
      nir_lower_system_values(nir);
      nir_lower_compute_system_values_options cs = {};
      nir_lower_compute_system_values(nir, &cs);
      struct st_context st = {};
      st.ctx = &ctx;
      st.screen = ctx.screen;
      st_finalize_nir(&st, prog, program, nir, false, false);
      nir_shader_gather_info(nir,nir_shader_get_entrypoint(nir));
      printf("finalized[%u]: uniforms=%u ubos=%u default=%u\n",fixture,nir->num_uniforms,
             nir->info.num_ubos,nir->info.first_ubo_is_default_ubo);
      nir_validate_shader(nir,"finalized parsed GLSL");
      assert(!nir->info.spec); // The two serializers differ only for this optional string.
      unsigned offset=0, default_bytes=prog->Parameters->NumParameterValues*4;
      if(fixture==0 && !PS5_GLSL_PRIVATE_TEST) {
         unsigned found=0;
         for(unsigned i=0;i<prog->Parameters->NumParameters;++i) {
            const gl_program_parameter *p=&prog->Parameters->Parameters[i];
            if(p->Name && !strcmp(p->Name,"addend")) {
               offset=p->ValueOffset*4;
               ++found;
            }
         }
         assert(found==1 && default_bytes && default_bytes<=64 && !(default_bytes%4));
         assert(offset+4<=default_bytes && !(offset%4));
         // Verify the measured GL parameter position against actual lowering,
         // not an assumed load_uniform address. Keep the exported NIR intact.
         nir_shader *check=nir_shader_clone(NULL,nir);
         nir_lower_uniforms_to_ubo(check,false,false);
         nir_opt_constant_folding(check);
         found=0;
         nir_foreach_function_impl(impl,check) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
            if(instr->type!=nir_instr_type_intrinsic) continue;
            nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
            if(intr->intrinsic!=nir_intrinsic_load_ubo) continue;
            assert(nir_src_is_const(intr->src[0]));
            if(nir_src_as_uint(intr->src[0])==0) {
               assert(nir_src_is_const(intr->src[1]) && nir_src_as_uint(intr->src[1])==offset);
               assert(intr->def.bit_size==32 && intr->def.num_components==1);
               ++found;
            }
         }
         assert(found==1); ralloc_free(check);
      } else assert(!default_bytes);
      fprintf(layout,"%u %u %u\n",fixture,offset,default_bytes);
      char source_name[32]; snprintf(source_name,sizeof(source_name),"fixture-%u.comp",fixture);
      FILE *literal=fopen(source_name,"wb"); assert(literal);
      assert(fwrite(fixtures[fixture],strlen(fixtures[fixture]),1,literal)==1);
      fclose(literal);
      blob serialized;
      blob_init(&serialized);
      nir_serialize(&serialized,nir,true);
      char name[32]; snprintf(name,sizeof(name),"fixture-%u.nir",fixture);
      FILE *out=fopen(name,"wb"); assert(out);
      assert(fwrite(serialized.data,serialized.size,1,out)==1);
      fclose(out);
      blob_finish(&serialized);
      standalone_compiler_cleanup(program, &ctx);
   }
   fclose(layout);
   puts("PASS 3 parsed GLSL fixtures: gl_nir_link_glsl -> selected ST passes/st_finalize_nir -> serialized NIR; partial, no driver API validation");
}
