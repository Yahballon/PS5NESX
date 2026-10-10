// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stddef.h>
#include "compiler/nir/nir.h"
// Compiled separately against each tree. No NIR symbols are linked from this TU.
const size_t *ABI_FUNCTION(void);
const size_t *ABI_FUNCTION(void) {
   static const size_t values[]={
      sizeof(nir_shader),sizeof(nir_shader_compiler_options),sizeof(struct shader_info),
      sizeof(nir_instr),sizeof(nir_instr_type),sizeof(nir_intrinsic_op),
      sizeof(nir_intrinsic_instr),offsetof(nir_intrinsic_instr,intrinsic),
      sizeof(nir_tex_instr),sizeof(nir_def),sizeof(nir_src),sizeof(nir_variable),
      offsetof(nir_shader,info),offsetof(nir_shader,num_uniforms),offsetof(nir_shader,options),
      nir_intrinsic_load_uniform,nir_intrinsic_load_ubo,nir_intrinsic_store_ssbo,
      nir_texop_tex,nir_texop_txl,nir_var_mem_ubo,nir_var_mem_ssbo,0};
   return values;
}
