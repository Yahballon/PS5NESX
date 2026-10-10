// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "pipe/p_state.h"
#include "psbc_compile.h"
#include "compiler/nir/nir_serialize.h"
#include "util/blob.h"
#ifndef PS5_GLSL_PRIVATE_TEST
#define PS5_GLSL_PRIVATE_TEST 0
#endif
#define PS5_AGC_COMPUTE_MAX_TEXTURES 16
#define PS5_AGC_COMPUTE_MAX_IMAGES 8
bool handoff_prepare(nir_shader *nir);
void handoff_compile(nir_shader *nir, unsigned fixture);
_Static_assert(sizeof(nir_instr_type)==1, "NIR enum packing");
_Static_assert(offsetof(nir_intrinsic_instr,intrinsic)==56, "NIR intrinsic layout");
#include "prepare.inc"
const size_t *psbc_abi(void);
unsigned ac_nir_varying_expression_max_cost(nir_shader *producer, nir_shader *consumer);

void handoff_compile(nir_shader *nir, unsigned fixture) {
   nir_validate_shader(nir,"parsed GLSL handoff");
   assert(handoff_prepare(nir));
   unsigned ubos = nir->info.num_ubos;
   assert(handoff_prepare(nir) && nir->info.num_ubos == ubos);
   nir_opt_constant_folding(nir);
   unsigned ssbo_bindings[2]={0};
   if (PS5_GLSL_PRIVATE_TEST) {
      char name[48]; snprintf(name,sizeof(name),"fixture-%u-ssbo.txt",fixture);
      FILE *bindings=fopen(name,"r"); assert(bindings);
      assert(fscanf(bindings,"%u%u",&ssbo_bindings[0],&ssbo_bindings[1])==2);
      assert(ssbo_bindings[0]<2 && ssbo_bindings[1]==1-ssbo_bindings[0]);
      fclose(bindings);
      printf("private-bindings[%u]: slots -> GL bindings %u,%u\n",fixture,ssbo_bindings[0],ssbo_bindings[1]);
   }
   if (PS5_GLSL_PRIVATE_TEST) {
      struct blob prepared;
      blob_init(&prepared);
      nir_serialize(&prepared, nir, false);
      char name[48];
      snprintf(name, sizeof(name), "fixture-%u-prepared.nir", fixture);
      FILE *file = fopen(name, "wb"); assert(file);
      assert(fwrite(prepared.data, prepared.size, 1, file) == 1);
      assert(fclose(file) == 0);
      blob_finish(&prepared);
   }
   unsigned ubo_mask=0, tex_count=0;
   nir_foreach_function_impl(impl,nir) nir_foreach_block(block,impl) nir_foreach_instr(instr,block) {
      if (instr->type==nir_instr_type_intrinsic) {
         nir_intrinsic_instr *intr=nir_instr_as_intrinsic(instr);
         assert(intr->intrinsic!=nir_intrinsic_load_uniform);
         if (PS5_GLSL_PRIVATE_TEST && (intr->intrinsic==nir_intrinsic_load_ssbo ||
             intr->intrinsic==nir_intrinsic_store_ssbo)) {
            const bool store=intr->intrinsic==nir_intrinsic_store_ssbo;
            nir_scalar index=nir_scalar_resolved(intr->src[store?1:0].ssa,0);
            assert(nir_scalar_is_const(index));
            unsigned slot=nir_scalar_as_uint(index);
            assert(slot<2 && ssbo_bindings[slot]==(store?0u:1u));
         }
         if(intr->intrinsic==nir_intrinsic_load_ubo) {
            assert(nir_src_is_const(intr->src[0]));
            ubo_mask |= 1u << nir_src_as_uint(intr->src[0]);
         }
      }
      if(instr->type==nir_instr_type_tex) {
         nir_tex_instr *tex=nir_instr_as_tex(instr);
         assert(tex->op==nir_texop_txl);
         int lod=nir_tex_instr_src_index(tex,nir_tex_src_lod);
         assert(lod>=0 && nir_src_is_const(tex->src[lod].src) && nir_src_as_float(tex->src[lod].src)==0);
         ++tex_count;
      }
   }
   assert(ubo_mask==(PS5_GLSL_PRIVATE_TEST ? 0u : fixture==0 ? 3u : fixture==1 ? 2u : 0u));
   assert(tex_count==(!PS5_GLSL_PRIVATE_TEST && fixture==2));
   PsbcCompileOptions opts = {.target=PSBC_TARGET_PS5,.stage=PSBC_STAGE_COMPUTE,
      .compute_private_buffer=PS5_GLSL_PRIVATE_TEST,
      .optimise=true,.address32_hi=2,.gallium_buffer_arrays=true,.descriptor_binding_count=2,
      .descriptor_bindings={
         {.binding=PSBC_GALLIUM_SSBO_ARRAY_BINDING(PSBC_STAGE_COMPUTE),.type=PSBC_DESCRIPTOR_STORAGE_BUFFER,.array_size=16,.stride=16},
         {.binding=PSBC_GALLIUM_UBO_ARRAY_BINDING(PSBC_STAGE_COMPUTE),.type=PSBC_DESCRIPTOR_UNIFORM_BUFFER,.array_size=15,.stride=16,.offset=256}}};
   if(fixture==2 && !PS5_GLSL_PRIVATE_TEST) opts.descriptor_bindings[opts.descriptor_binding_count++]=(PsbcDescriptorBinding){
      .binding=0,.type=PSBC_DESCRIPTOR_COMBINED_IMAGE_SAMPLER,.array_size=1,.stride=48,.offset=752};
   PsbcShaderOutput out={0};
   PsbcResult status=psbc_compile_nir(nir,&opts,&out);
   printf("compile[%u]: rc=%d source-private=%u internal-stride=%u hardware-scratch=%u\n",
       fixture,status,nir->scratch_size,out.metadata.compute_private_stride,out.metadata.scratch_bytes_per_wave);
   fflush(stdout);
   assert(status==PSBC_RESULT_OK);
   if(PS5_GLSL_PRIVATE_TEST) {
      /* Existing AMD lowering retains arrays <=256 bytes in registers. */
      const unsigned bytes[]={0,1024,4096};
      assert(out.metadata.compute_private_stride==bytes[fixture]);
      assert(out.metadata.compute_grid_size_valid && !out.metadata.scratch_size_per_thread);
      PsbcShaderOutput baseline={0};
      opts.compute_private_buffer=false;
      assert(psbc_compile_nir(nir,&opts,&baseline)==PSBC_RESULT_OK);
      assert(baseline.metadata.scratch_valid==(fixture!=0));
      assert(!baseline.metadata.compute_private_stride);
      printf("private-baseline[%u]: hardware-scratch=%u opt-in-stride=%u\n",
          fixture,baseline.metadata.scratch_bytes_per_wave,out.metadata.compute_private_stride);
      psbc_free_output(&baseline);
   }
   assert(out.machine_code_size && !out.metadata.scratch_valid && out.metadata.descriptor_set0_valid);
   printf("prepared/compiled[%u]: ubo-mask=%u textures=%u bytes=%zu\n",fixture,ubo_mask,tex_count,out.machine_code_size);
   psbc_free_output(&out);
}

int main(int argc, char **argv) {
   psbc_init();
   if(argc==2 && !strcmp(argv[1],"--contract")) {
      nir_shader_compiler_options opts=*psbc_get_nir_options(PSBC_STAGE_COMPUTE);
      assert(opts.varying_expression_max_cost==ac_nir_varying_expression_max_cost);
      assert(!opts.lower_to_scalar_filter && !opts.lower_mediump_io && !opts.lower_convert_alu_types && !opts.varying_estimate_instr_cost &&
             !opts.max_offset_shift && !opts.cb_data);
      opts.varying_expression_max_cost=NULL; // Rebound to the exact extracted body in the frontend process.
      opts.io_options |= nir_io_has_intrinsics;
      FILE *out=fopen("contract.bin","wb"); assert(out);
      assert(fwrite(psbc_abi(),22*sizeof(size_t),1,out)==1);
      assert(fwrite(&opts,sizeof(opts),1,out)==1); fclose(out);
      FILE *values=fopen("options-values.txt","w"); assert(values);
#include "options-values.inc"
      fclose(values);
      values=fopen("abi-values.txt","w"); assert(values);
      for(unsigned i=0;i<22;++i) fprintf(values,"%zu\n",psbc_abi()[i]);
      fclose(values);
   } else {
      for(unsigned fixture=0;fixture<3;++fixture) {
         char name[32]; snprintf(name,sizeof(name),"fixture-%u.nir",fixture);
         FILE *in=fopen(name,"rb"); assert(in);
         assert(!fseek(in,0,SEEK_END)); long size=ftell(in); assert(size>0 && size<1048576);
         rewind(in); void *data=malloc(size); assert(data);
         assert(fread(data,size,1,in)==1); fclose(in);
         struct blob_reader reader; blob_reader_init(&reader,data,size);
         nir_shader *nir=nir_deserialize(NULL,psbc_get_nir_options(PSBC_STAGE_COMPUTE),&reader);
         assert(nir && !reader.overrun && reader.current==reader.end);
         nir_validate_shader(nir,"PSBC deserialized parsed GLSL");
         handoff_compile(nir,fixture);
         ralloc_free(nir); free(data);
      }
      puts("PASS 3 deserialized fixtures -> extracted driver preparation -> PSBC (partial boundary)");
   }
   psbc_shutdown();
}
