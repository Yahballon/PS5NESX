// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* Internal CS -> sampled draw -> CS fetch/size transitions. Twelve alternating
 * R32_FLOAT/UINT/SINT phases verify channels and padding at units 0 and 15.
 * Exercises resource slots, typed arrays, bounded LODs, memory barriers, and
 * audited parsed-GLSL fixtures through the actual native compute callbacks.
 * No public compute cap or display qualification: this test never swaps. */
#include <stdio.h>
#include <string.h>
#include "compiler/nir/nir_builder.h"
#include "compiler/nir/nir_serialize.h"
#include "util/blob.h"
#include "compute_glsl_fixtures.h"
#include "pipe/p_context.h"
#include "pipe/p_screen.h"
#include "util/u_inlines.h"
#include "util/half_float.h"
#include "ps5_screen.h"
#include "psbc_compile.h"

#define IMAGE_WORDS (64 * 3) /* 17x3 R32, 256-byte rows. */
#define GUARD_WORD UINT32_C(0xcdcdcdcd)
static const enum pipe_format image_formats[] = {
   PIPE_FORMAT_R32_FLOAT, PIPE_FORMAT_R32_UINT, PIPE_FORMAT_R32_SINT,
   PIPE_FORMAT_R32G32_FLOAT, PIPE_FORMAT_R32G32_UINT, PIPE_FORMAT_R32G32_SINT,
   PIPE_FORMAT_R32G32B32A32_FLOAT, PIPE_FORMAT_R32G32B32A32_UINT, PIPE_FORMAT_R32G32B32A32_SINT,
   PIPE_FORMAT_R16G16B16A16_FLOAT, PIPE_FORMAT_R16G16B16A16_UINT, PIPE_FORMAT_R16G16B16A16_SINT};


/* Trusted, embedded exports from the tracked isolated GLSL harness only.
 * All options are native; serialized NIR does not carry host function pointers. */
static nir_shader *load_parsed_glsl(unsigned fixture, const nir_shader_compiler_options *options)
{
   if (fixture >= ARRAY_SIZE(ps5_glsl_fixtures) || !ps5_glsl_options_match(options))
      return NULL;
   const size_t size = ps5_glsl_fixtures[fixture].size;
   if (!size || size > 1048576)
      return NULL;
   struct blob_reader reader;
   blob_reader_init(&reader, ps5_glsl_fixtures[fixture].data, size);
   nir_shader *nir = nir_deserialize(NULL, options, &reader);
   if (!nir || reader.overrun || reader.current != reader.end ||
       nir->info.stage != MESA_SHADER_COMPUTE || nir->info.spec ||
       nir->info.workgroup_size_variable || nir->info.shared_size ||
       nir->info.workgroup_size[0] != 1 || nir->info.workgroup_size[1] != 1 ||
       nir->info.workgroup_size[2] != 1) {
      ralloc_free(nir);
      return NULL;
   }
   nir_validate_shader(nir, "audited parsed GLSL fixture");
   return nir;
}

static uint32_t parsed_glsl_expected(unsigned fixture, unsigned pass)
{
   if (fixture == 0) return pass ? 40 : 20;
   if (fixture == 1) return pass ? 11 : 7;
   return pass ? UINT32_C(0x3f400000) : UINT32_C(0x3e800000); /* 0.75 / 0.25 */
}

static unsigned count_parsed_glsl(const uint32_t *words, uint32_t expected)
{
   unsigned correct = 0;
   for (unsigned i = 0; i < 80; ++i)
      correct += words[i] == (i == 8 ? expected : GUARD_WORD);
   return correct;
}

static nir_shader *build_compute(unsigned kind)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-render-cs");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ubos = b.shader->info.num_images = 1;
   b.shader->info.first_ubo_is_default_ubo = true; /* Fixture uses pipe CB0. */
   nir_def *zero = nir_imm_int(&b, 0);
   nir_def *x = nir_iadd_imm(&b, nir_channel(&b, nir_load_local_invocation_id(&b), 0), 1);
   nir_def *sign = nir_load_ubo(&b, 1, 32, zero, zero, .align_mul = 4, .range = 4);
   nir_def *value = nir_fmul(&b, nir_fmul_imm(&b, nir_u2f32(&b, x), 0.25), sign);
   if (kind == 1)
      value = nir_iadd(&b, nir_imul_imm(&b, x, 3), nir_bcsel(&b, nir_flt_imm(&b, sign, 0),
         nir_imm_int(&b, 0x80000005u), nir_imm_int(&b, 0x10000005u)));
   else if (kind == 2) {
      value = nir_iadd_imm(&b, nir_imul_imm(&b, x, 7), 1000);
      value = nir_bcsel(&b, nir_flt_imm(&b, sign, 0), nir_ineg(&b, value), value);
   }
   nir_image_store(&b, zero, nir_vec4(&b, x, nir_imm_int(&b, 1), zero, zero), zero,
      nir_vec4(&b, value, zero, zero, zero), zero, .image_dim = GLSL_SAMPLER_DIM_2D,
      .format = image_formats[kind], .src_type = kind == 0 ? nir_type_float32 :
         kind == 1 ? nir_type_uint32 : nir_type_int32);
   return b.shader;
}

static nir_shader *build_compute_uniforms(bool explicit_ubo)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-default-uniforms");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->num_uniforms = explicit_ubo ? 0 : 2;
   b.shader->info.num_ubos = explicit_ubo ? 2 : 1;
   b.shader->info.first_ubo_is_default_ubo = explicit_ubo;
   b.shader->info.num_ssbos = 1;
   nir_def *zero = nir_imm_int(&b, 0);
   nir_def *defaults = explicit_ubo ? nir_load_ubo(&b, 4, 32, zero, nir_imm_int(&b, 16),
      .align_mul = NIR_ALIGN_MUL_MAX, .align_offset = 16, .range_base = 16, .range = 16) :
      nir_load_uniform(&b, 4, 32, zero, .base = 1, .range = 1);
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   nir_def *value = nir_iadd(&b, id, nir_load_ubo(&b, 1, 32, nir_imm_int(&b, explicit_ubo ? 1 : 0),
      zero, .align_mul = 4, .range = 4));
   for (unsigned lane = 0; lane < 4; ++lane)
      value = nir_iadd(&b, value, nir_imul_imm(&b, nir_channel(&b, defaults, lane), 1u << lane));
   nir_store_ssbo(&b, value, zero, nir_imul_imm(&b, id, 4), .align_mul = 4, .write_mask = 1);
   return b.shader;
}

static nir_shader *build_compute_user_ubo(bool explicit_ubo)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-user-ubo-only");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ubos = explicit_ubo ? 2 : 1;
   b.shader->info.first_ubo_is_default_ubo = explicit_ubo;
   b.shader->info.num_ssbos = 1;
   nir_def *zero = nir_imm_int(&b, 0);
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   nir_def *value = nir_load_ubo(&b, 1, 32, nir_imm_int(&b, explicit_ubo ? 1 : 0),
      zero, .align_mul = 4, .range = 4);
   nir_store_ssbo(&b, nir_iadd(&b, value, id), zero, nir_imul_imm(&b, id, 4),
      .align_mul = 4, .write_mask = 1);
   return b.shader;
}

static nir_shader *build_vertex(void)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_VERTEX,
      psbc_get_nir_options(PSBC_STAGE_VERTEX), "compute-render-vs");
   nir_variable *pos = nir_variable_create(b.shader, nir_var_shader_out, glsl_vec4_type(), "position");
   pos->data.location = VARYING_SLOT_POS;
   nir_def *id = nir_load_vertex_id_zero_base(&b);
   nir_store_var(&b, pos, nir_vec4(&b,
      nir_bcsel(&b, nir_ieq_imm(&b, id, 1), nir_imm_float(&b, 3), nir_imm_float(&b, -1)),
      nir_bcsel(&b, nir_ieq_imm(&b, id, 2), nir_imm_float(&b, 3), nir_imm_float(&b, -1)),
      nir_imm_float(&b, 0), nir_imm_float(&b, 1)), 0xf);
   return b.shader;
}

static nir_shader *build_fragment(unsigned kind)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
      psbc_get_nir_options(PSBC_STAGE_FRAGMENT), "compute-render-fs");
   nir_tex_instr *tex = nir_tex_instr_create(b.shader, 2);
   tex->op = nir_texop_txf;
   tex->sampler_dim = GLSL_SAMPLER_DIM_2D;
   tex->coord_components = 2;
   tex->dest_type = kind == 0 ? nir_type_float32 : kind == 1 ? nir_type_uint32 : nir_type_int32;
   tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_coord, nir_imm_ivec2(&b, 1, 1));
   tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_lod, nir_imm_int(&b, 0));
   nir_def_init(&tex->instr, &tex->def, 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_def *negative = nir_flt_imm(&b, nir_channel(&b, &tex->def, 0), 0);
   if (kind == 1)
      negative = nir_ine_imm(&b, nir_iand_imm(&b, nir_channel(&b, &tex->def, 0), 0x80000000u), 0);
   else if (kind == 2)
      negative = nir_ilt_imm(&b, nir_channel(&b, &tex->def, 0), 0);
   nir_def *channels_ok = nir_imm_true(&b);
   for (unsigned lane = 1; lane < 4; ++lane) {
      nir_def *component = nir_channel(&b, &tex->def, lane);
      nir_def *matches = kind == 0 ? nir_feq_imm(&b, component, lane == 3 ? 1 : 0) :
                                    nir_ieq_imm(&b, component, lane == 3 ? 1 : 0);
      channels_ok = nir_iand(&b, channels_ok, matches);
   }
   nir_variable *color = nir_variable_create(b.shader, nir_var_shader_out, glsl_vec4_type(), "color");
   color->data.location = FRAG_RESULT_DATA0;
   nir_store_var(&b, color, nir_vec4(&b, nir_b2f32(&b, negative),
      nir_b2f32(&b, nir_inot(&b, negative)), nir_b2f32(&b, nir_inot(&b, channels_ok)), nir_imm_float(&b, 1)), 0xf);
   nir_shader_gather_info(b.shader, nir_shader_get_entrypoint(b.shader));
   /* Indexed Gallium texture instructions require explicit usage metadata;
    * gather_info counts sampler variables but does not build these masks. */
   b.shader->info.num_textures = 1;
   BITSET_SET(b.shader->info.textures_used, 0);
   BITSET_SET(b.shader->info.textures_used_by_txf, 0);
   return b.shader;
}

static nir_shader *compute_sample(unsigned test, unsigned unit)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-sampled-input");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ssbos = 1;
   b.shader->info.num_textures = unit + 1;
   BITSET_SET(b.shader->info.textures_used, unit);
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   nir_tex_instr *tex = nir_tex_instr_create(b.shader, test == 3 || test == 6 ? 1 : 2);
   tex->op = test == 6 ? nir_texop_tex : test == 3 ? nir_texop_txs : test >= 4 ? nir_texop_txl : nir_texop_txf;
   tex->sampler_dim = GLSL_SAMPLER_DIM_2D;
   tex->texture_index = tex->sampler_index = unit;
   tex->coord_components = test == 3 ? 0 : 2;
   tex->dest_type = test == 1 ? nir_type_uint32 :
                   test == 2 || test == 3 ? nir_type_int32 : nir_type_float32;
   if (test == 3) {
      tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_lod, nir_imm_int(&b, 0));
   } else {
      tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_coord, test >= 4 ?
         nir_vec2(&b, nir_bcsel(&b, nir_ine_imm(&b, nir_iand_imm(&b, id, 1), 0),
            nir_imm_float(&b, test == 5 ? 1.25 : 0.75),
            nir_imm_float(&b, test == 5 ? -0.25 : 0.25)), test == 5 ?
            nir_bcsel(&b, nir_ine_imm(&b, nir_iand_imm(&b, id, 1), 0),
               nir_imm_float(&b, 1.5), nir_imm_float(&b, -0.5)) : nir_imm_float(&b, 0.5)) :
         nir_vec2(&b, nir_iadd_imm(&b, id, 1), nir_imm_int(&b, 1)));
      if (test != 6)
         tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_lod, test >= 4 ?
            nir_imm_float(&b, 0) : nir_imm_int(&b, 0));
   }
   nir_def_init(&tex->instr, &tex->def, test == 3 ? 2 : 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_def *value = test == 3 ? nir_vec4(&b, nir_channel(&b, &tex->def, 0),
      nir_channel(&b, &tex->def, 1), nir_imm_int(&b, 0), nir_imm_int(&b, 1)) : &tex->def;
   nir_store_ssbo(&b, value, nir_imm_int(&b, 0), nir_imul_imm(&b, id, 16),
      .write_mask = 0xf, .align_mul = 16);
   return b.shader;
}

static nir_shader *compute_dimensional(unsigned kind, bool filtered)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-dimensional");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ssbos = b.shader->info.num_textures = 1;
   BITSET_SET(b.shader->info.textures_used, 0);
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   nir_def *x = nir_iand_imm(&b, id, 3), *y = nir_ushr_imm(&b, id, 2), *z = y;
   if (kind == 3) {
      x = nir_fadd_imm(&b, nir_u2f32(&b, x), 0.5f);
      y = nir_fadd_imm(&b, nir_u2f32(&b, y), 0.5f);
      if (filtered) { x = nir_fmul_imm(&b, x, 2); y = nir_fmul_imm(&b, y, 2); }
   } else if (filtered && kind < 4) {
      x = nir_fmul_imm(&b, nir_fadd_imm(&b, nir_u2f32(&b, x), kind == 1 ? -0.5f : 0.5f), 0.25f);
      y = kind == 1 ? nir_u2f32(&b, y) :
         nir_fmul_imm(&b, nir_fadd_imm(&b, nir_u2f32(&b, y), 0.5f), 0.25f);
      z = y;
   }
   nir_tex_instr *tex = nir_tex_instr_create(b.shader,
      kind == 1 && filtered ? 3 : kind == 3 && !filtered ? 1 : 2);
   tex->op = kind >= 4 ? nir_texop_txf_ms : kind == 3 ? nir_texop_tex : filtered ? nir_texop_txl : nir_texop_txf;
   tex->sampler_dim = kind >= 4 ? GLSL_SAMPLER_DIM_MS : kind == 3 ? GLSL_SAMPLER_DIM_RECT :
      kind == 2 ? GLSL_SAMPLER_DIM_3D : GLSL_SAMPLER_DIM_1D;
   tex->is_array = kind == 1 || kind == 5;
   tex->coord_components = kind >= 4 ? 2 + tex->is_array : kind == 3 ? 2 : kind + 1;
   tex->dest_type = nir_type_float32;
   tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_coord,
      kind == 0 ? x : kind == 2 || kind == 5 ? nir_vec3(&b, x, y, z) : nir_vec2(&b, x, y));
   if (kind >= 4) {
      tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_ms_index, nir_imm_int(&b, filtered ? 3 : 0));
   } else if (kind == 3) {
      if (filtered) tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_projector, nir_imm_float(&b, 2));
   } else {
      tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_lod,
         filtered ? nir_imm_float(&b, 0) : nir_imm_int(&b, 0));
      if (kind == 1 && filtered)
         tex->src[2] = nir_tex_src_for_ssa(nir_tex_src_offset, nir_imm_int(&b, 1));
   }
   nir_def_init(&tex->instr, &tex->def, 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_store_ssbo(&b, &tex->def, nir_imm_int(&b, 0), nir_imul_imm(&b, id, 16),
      .write_mask = 0xf, .align_mul = 16);
   return b.shader;
}

static uint32_t expected_red(unsigned kind, unsigned x, float sign)
{
   if (kind == 1)
      return (sign < 0 ? UINT32_C(0x80000005) : UINT32_C(0x10000005)) + x * 3;
   if (kind == 2)
      return (uint32_t)((sign < 0 ? -1 : 1) * (1000 + (int)x * 7));
   float value = x * 0.25f * sign;
   uint32_t word;
   memcpy(&word, &value, 4);
   return word;
}

static nir_shader *compute_mip(unsigned operation, unsigned unit, unsigned level, unsigned layers, unsigned kind, bool dynamic)
{
   const bool array = layers > 1;
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-mip");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ssbos = 1;
   b.shader->info.num_textures = unit + 1;
   BITSET_SET(b.shader->info.textures_used, unit);
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   nir_def *layer = nir_umod_imm(&b, id, layers);
   nir_tex_instr *tex = nir_tex_instr_create(b.shader, operation == 1 ? 1 : 2);
   tex->op = operation == 1 ? nir_texop_txs : operation >= 2 ? nir_texop_txl : nir_texop_txf;
   tex->sampler_dim = GLSL_SAMPLER_DIM_2D;
   tex->is_array = array;
   tex->texture_index = tex->sampler_index = unit;
   tex->coord_components = operation == 1 ? 0 : array ? 3 : 2;
   tex->dest_type = operation == 1 || kind == 2 ? nir_type_int32 : kind == 1 ? nir_type_uint32 : nir_type_float32;
   nir_def *dynamic_lod = dynamic && operation >= 2 ?
      nir_bcsel(&b, nir_ine_imm(&b, nir_iand_imm(&b, id, 1), 0),
         nir_imm_float(&b, level ? level - 0.5f : 0), nir_imm_float(&b, level ? 0.5f : 0)) :
      nir_iand_imm(&b, id, level);
   tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_lod, dynamic ? dynamic_lod : operation >= 2 ?
      nir_imm_float(&b, level + (operation == 3 ? 0.5 : 0)) : nir_imm_int(&b, level));
   if (operation != 1) {
      nir_def *coord = operation >= 2 ? nir_imm_vec2(&b, 0.5, 0.5) : nir_imm_ivec2(&b, 0, 0);
      if (array) coord = nir_vec3(&b, nir_channel(&b, coord, 0), nir_channel(&b, coord, 1),
         operation >= 2 ? nir_u2f32(&b, layer) : layer);
      tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_coord, coord);
   }
   nir_def_init(&tex->instr, &tex->def, operation == 1 ? (array ? 3 : 2) : 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_def *value = operation == 1 ? nir_vec4(&b, nir_channel(&b, &tex->def, 0),
      nir_channel(&b, &tex->def, 1), array ? nir_channel(&b, &tex->def, 2) : nir_imm_int(&b, 0),
      nir_imm_int(&b, 1)) : &tex->def;
   nir_store_ssbo(&b, value, nir_imm_int(&b, 0), nir_imul_imm(&b, id, 16), .write_mask = 15, .align_mul = 16);
   return b.shader;
}

static nir_shader *compute_all_slots(void)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "compute-all-textures");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_ssbos = 1; b.shader->info.num_textures = 16;
   nir_def *id = nir_channel(&b, nir_load_local_invocation_id(&b), 0);
   for (unsigned unit = 0; unit < 16; ++unit) {
      BITSET_SET(b.shader->info.textures_used, unit);
      nir_push_if(&b, nir_ieq_imm(&b, id, unit));
      nir_tex_instr *tex = nir_tex_instr_create(b.shader, 2);
      tex->op = nir_texop_txf; tex->sampler_dim = GLSL_SAMPLER_DIM_2D;
      tex->texture_index = unit; tex->coord_components = 2; tex->dest_type = nir_type_float32;
      tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_lod, nir_imm_int(&b, 0));
      tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_coord, nir_imm_ivec2(&b, 0, 0));
      nir_def_init(&tex->instr, &tex->def, 4, 32); nir_builder_instr_insert(&b, &tex->instr);
      nir_store_ssbo(&b, &tex->def, nir_imm_int(&b, 0), nir_imul_imm(&b, id, 16), .write_mask = 15, .align_mul = 16);
      nir_pop_if(&b, NULL);
   }
   return b.shader;
}

static nir_shader *write_mip(unsigned level, bool array, unsigned kind)
{
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE,
      psbc_get_nir_options(PSBC_STAGE_COMPUTE), "write-mip");
   b.shader->info.workgroup_size[0] = 16;
   b.shader->info.workgroup_size[1] = b.shader->info.workgroup_size[2] = 1;
   b.shader->info.num_images = b.shader->info.num_ubos = 1;
   b.shader->info.first_ubo_is_default_ubo = true; /* Fixture uses pipe CB0. */
   nir_def *zero = nir_imm_int(&b, 0);
   nir_def *id = nir_iadd(&b, nir_channel(&b, nir_load_local_invocation_id(&b), 0),
      nir_imul_imm(&b, nir_channel(&b, nir_load_workgroup_id(&b), 0), 16));
   nir_def *sign = nir_load_ubo(&b, 1, 32, zero, zero, .align_mul = 4, .range = 4);
   nir_push_if(&b, nir_ult_imm(&b, id, (16u >> level) * (8u >> level)));
   nir_def *layer = array ? nir_channel(&b, nir_load_workgroup_id(&b), 1) : zero;
   nir_def *value = nir_fmul(&b, sign, nir_fadd_imm(&b,
      nir_fmul_imm(&b, nir_u2f32(&b, layer), 16), (float)(1u << level)));
   if (kind == 1)
      value = nir_iadd(&b, nir_bcsel(&b, nir_flt_imm(&b, sign, 0),
         nir_imm_int(&b, 0x80000000u), nir_imm_int(&b, 0x10000000u)),
         nir_iadd_imm(&b, nir_imul_imm(&b, layer, 0x10000), 1u << level));
   if (kind == 2)
      value = nir_imul(&b, nir_f2i32(&b, sign),
         nir_iadd_imm(&b, nir_imul_imm(&b, layer, 16), 1000 + (1u << level)));
   nir_image_store(&b, zero, nir_vec4(&b, nir_iand_imm(&b, id, (16u >> level) - 1),
      nir_ushr_imm(&b, id, 4 - level), layer, zero), zero,
      nir_vec4(&b, value, zero, zero, zero), zero, .image_dim = GLSL_SAMPLER_DIM_2D,
      .format = image_formats[kind], .src_type = kind == 1 ? nir_type_uint32 : kind == 2 ? nir_type_int32 : nir_type_float32,
      .image_array = array);
   nir_pop_if(&b, NULL);
   return b.shader;
}

static uint32_t mip_word(unsigned kind, unsigned level, unsigned layer, float sign, bool linear)
{
   if (kind == 1) return (sign < 0 ? 0x80000000u : 0x10000000u) + layer * 0x10000u + (1u << level);
   if (kind == 2) return (uint32_t)((int)sign * (int)(1000 + layer * 16 + (1u << level)));
   float value = sign * (layer * 16.0f + (float)(1u << level) * (linear ? 1.5f : 1.0f));
   uint32_t bits; memcpy(&bits, &value, 4); return bits;
}

static unsigned count_mip(const uint32_t *words, unsigned operation, unsigned physical_level, float sign, unsigned layers, unsigned kind)
{
   uint32_t expected[4] = {0, 0, 0, kind ? 1 : 0x3f800000};
   if (operation == 1) {
      expected[0] = 16u >> physical_level;
      expected[1] = 8u >> physical_level;
      expected[3] = 1;
      expected[2] = layers > 1 ? layers : 0;
   }
   unsigned correct = 0;
   for (unsigned i = 0; i < 80; ++i) {
      if (operation != 1 && i >= 8 && i < 72) {
         const unsigned layer = ((i - 8) / 4) % layers;
         expected[0] = mip_word(kind, physical_level, layer, sign, operation == 3);
      }
      correct += words[i] == (i < 8 || i >= 72 ? GUARD_WORD : expected[(i - 8) % 4]);
   }
   return correct;
}

static unsigned count_dynamic_mip(const uint32_t *words, unsigned operation, unsigned first,
                                 unsigned mask, float sign, unsigned layers, unsigned kind)
{
   unsigned correct = 0;
   for (unsigned i = 0; i < 80; ++i) {
      uint32_t expected = GUARD_WORD;
      if (i >= 8 && i < 72) {
         const unsigned id = (i - 8) / 4;
         const unsigned level = first + (operation >= 2 ? (mask && (id & 1) ? mask - 1 : 0) : id & mask);
         const uint32_t value[4] = {
            operation == 1 ? 16u >> level : mip_word(kind, level, id % layers, sign, operation >= 2 && mask),
            operation == 1 ? 8u >> level : 0, operation == 1 && layers > 1 ? layers : 0,
            operation == 1 || kind ? 1 : 0x3f800000u};
         expected = value[(i - 8) % 4];
      }
      correct += words[i] == expected;
   }
   return correct;
}

/* operation: fetch, size, then nearest/linear pairs for edge, repeat, mirror. */
static unsigned count_sampled(const uint32_t *words, float sign, unsigned operation, unsigned kind)
{
   unsigned correct = 0;
   for (unsigned i = 0; i < 80; ++i) {
      uint32_t expected = GUARD_WORD;
      if (i >= 8 && i < 72) {
         unsigned lane = (i - 8) % 4, invocation = (i - 8) / 4;
         if (operation == 1) {
            const uint32_t size[4] = {17, 3, 0, 1};
            expected = size[lane];
         } else {
            expected = lane == 0 ? expected_red(kind, invocation + 1, sign) :
               lane == 3 ? (kind == 0 ? UINT32_C(0x3f800000) : 1) : 0;
            if (operation >= 2 && lane == 0) {
               /* Exact coordinates .25/.75 yield texel positions 3.75/12.25. */
               bool high = (invocation & 1) ^ (operation == 4 || operation == 5);
               float value = sign * (high ? (operation & 1 ? 3.0625f : 3.0f) :
                                           (operation & 1 ? 0.9375f : 1.0f));
               memcpy(&expected, &value, 4);
            }
         }
      }
      correct += words[i] == expected;
   }
   return correct;
}

static unsigned count_image(const uint32_t *words, float sign, unsigned kind)
{
   unsigned correct = 0;
   for (unsigned i = 0; i < IMAGE_WORDS; ++i) {
      uint32_t expected = GUARD_WORD;
      if (i >= 65 && i < 81) {
         expected = expected_red(kind, i - 64, sign);
      }
      correct += words[i] == expected;
   }
   return correct;
}

static unsigned count_pixels(const uint8_t *pixels, unsigned stride, float sign)
{
   const uint8_t expected[4] = {sign < 0 ? 255 : 0, sign > 0 ? 255 : 0, 0, 255};
   unsigned correct = 0;
   for (unsigned y = 0; y < 8; ++y)
      for (unsigned x = 0; x < 8; ++x)
         correct += !memcmp(pixels + y * stride + 4 * x, expected, sizeof(expected));
   return correct;
}

static uint32_t fragment_image_component(unsigned kind, unsigned id, unsigned lane)
{
   if (kind % 3 == 1) return 17 + 3 * id + lane * 17;
   if (kind % 3 == 2) return (uint32_t)(-1000 - 7 * (int)id + (int)lane * 17);
   float value = ((int)id - 32) * 0.25f + lane * 0.5f;
   uint32_t bits; memcpy(&bits, &value, 4); return bits;
}

static uint32_t fragment_image_word(unsigned kind, unsigned id, bool load)
{
   if (!load) return fragment_image_component(kind, id, 0);
   unsigned channels = kind < 3 ? 1 : kind < 6 ? 2 : 4;
   uint32_t sum = 0; float total = 0;
   for (unsigned lane = 0; lane < channels; ++lane) {
      uint32_t bits = fragment_image_component(kind, id, lane);
      if (kind % 3) sum += bits * (1u << lane);
      else { float f; memcpy(&f, &bits, 4); total += f * (1u << lane); }
   }
   if (kind % 3) return sum + 100;
   total = total * 2 + 0.125f;
   memcpy(&sum, &total, 4); return sum;
}

static uint32_t fragment_image_packed_word(unsigned kind, unsigned id, unsigned word)
{
   if (kind < 9) return fragment_image_component(kind, id, word);
   uint32_t packed = 0;
   for (unsigned half = 0; half < 2; ++half) {
      uint32_t bits = fragment_image_component(kind, id, word * 2 + half);
      if (kind % 3 == 0) { float f; memcpy(&f, &bits, 4); bits = _mesa_float_to_half_slow(f); }
      packed |= (bits & 0xffffu) << (half * 16);
   }
   return packed;
}

static nir_shader *build_fragment_storage(unsigned atomic, unsigned slot, unsigned kind, bool mixed,
                                          bool array, unsigned layer)
{
   const enum pipe_format format = image_formats[kind];
   const unsigned channels = kind < 3 ? 1 : kind < 6 ? 2 : 4;
   kind %= 3;
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT,
      psbc_get_nir_options(PSBC_STAGE_FRAGMENT), "fragment-storage-native");
   /* Use Mesa's option-aware builder, as GLSL system-value lowering does. */
   nir_def *coord = nir_build_frag_coord(&b, 4);
   nir_def *id = nir_iadd(&b, nir_f2u32(&b, nir_channel(&b, coord, 0)),
      nir_imul_imm(&b, nir_f2u32(&b, nir_channel(&b, coord, 1)), 8));
   nir_def *buffer = nir_imm_int(&b, slot), *offset = nir_imul_imm(&b, id, 4);
   nir_def *value;
   if (atomic < 2)
      value = atomic ? nir_ssbo_atomic(&b, 32, buffer, nir_imm_int(&b, 256),
         nir_imm_int(&b, 1), .atomic_op = nir_atomic_op_iadd) :
         nir_iadd_imm(&b, nir_load_ssbo(&b, 1, 32, buffer, offset, .align_mul = 4), 100);
   else {
      nir_def *zero = nir_imm_int(&b, 0);
      nir_def *xy = nir_vec4(&b, nir_f2u32(&b, nir_channel(&b, coord, 0)),
         nir_f2u32(&b, nir_channel(&b, coord, 1)), nir_imm_int(&b, layer), zero);
      nir_def *image_id = nir_iadd_imm(&b, id, layer * 64);
      value = nir_iadd_imm(&b, nir_imul_imm(&b, image_id, 3), 17);
      if (kind == 0) value = nir_fmul_imm(&b, nir_i2f32(&b, nir_iadd_imm(&b, image_id, -32)), 0.25);
      if (kind == 2) value = nir_iadd_imm(&b, nir_imul_imm(&b, image_id, -7), -1000);
      const nir_alu_type type = kind == 0 ? nir_type_float32 : kind == 1 ? nir_type_uint32 : nir_type_int32;
      if (atomic == 2) {
         nir_def *components[4] = {value, zero, zero, zero};
         for (unsigned lane = 1; lane < channels; ++lane)
            components[lane] = kind ? nir_iadd_imm(&b, value, lane * 17) : nir_fadd_imm(&b, value, lane * 0.5);
         nir_image_store(&b, buffer, xy, zero, nir_vec(&b, components, 4), zero,
            .image_dim = GLSL_SAMPLER_DIM_2D, .image_array = array, .format = format, .src_type = type);
      }
      else if (atomic == 3) {
         nir_def *loaded = nir_image_load(&b, 4, 32, buffer, xy, zero, zero,
            .image_dim = GLSL_SAMPLER_DIM_2D, .image_array = array, .format = format, .dest_type = type);
         value = nir_channel(&b, loaded, 0);
         for (unsigned lane = 1; lane < channels; ++lane)
            value = kind ? nir_iadd(&b, value, nir_imul_imm(&b, nir_channel(&b, loaded, lane), 1u << lane)) :
                           nir_fadd(&b, value, nir_fmul_imm(&b, nir_channel(&b, loaded, lane), 1u << lane));
         if (mixed) {
            const unsigned unit = slot ? 15 : 0;
            nir_tex_instr *tex = nir_tex_instr_create(b.shader, 2);
            tex->op = nir_texop_txf;
            tex->sampler_dim = GLSL_SAMPLER_DIM_2D;
            tex->coord_components = 2;
            tex->texture_index = tex->sampler_index = unit;
            tex->dest_type = type;
            tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_coord, nir_channels(&b, xy, 3));
            tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_lod, zero);
            nir_def_init(&tex->instr, &tex->def, 4, 32);
            nir_builder_instr_insert(&b, &tex->instr);
            nir_def *sample = nir_channel(&b, &tex->def, 0);
            nir_def *uniform = nir_load_ubo(&b, 1, 32, nir_imm_int(&b, slot ? 12 : 0), zero,
               .align_mul = 4, .range = 4);
            value = kind == 0 ? nir_fadd(&b, nir_fadd(&b, value, sample), uniform) :
                               nir_iadd(&b, nir_iadd(&b, value, sample), uniform);
         } else
            value = kind == 0 ? nir_fadd_imm(&b, nir_fmul_imm(&b, value, 2), 0.125) : nir_iadd_imm(&b, value, 100);
      }
      else
         value = nir_image_atomic(&b, 32, buffer, nir_imm_ivec4(&b, 0, 0, 0, 0), zero,
            nir_imm_int(&b, kind == 2 ? -1 : 1), .image_dim = GLSL_SAMPLER_DIM_2D, .format = format,
            .atomic_op = nir_atomic_op_iadd);
      buffer = zero;
   }
   nir_def *coord_ok = nir_iand(&b,
      nir_feq_imm(&b, nir_ffract(&b, nir_channel(&b, coord, 0)), 0.5),
      nir_feq_imm(&b, nir_ffract(&b, nir_channel(&b, coord, 1)), 0.5));
   coord_ok = nir_iand(&b, coord_ok, nir_iand(&b,
      nir_feq_imm(&b, nir_channel(&b, coord, 2), 0.5),
      nir_feq_imm(&b, nir_channel(&b, coord, 3), 1)));
   value = nir_bcsel(&b, coord_ok, value, nir_imm_int(&b, 0xdeadbeef));
   nir_store_ssbo(&b, value, buffer, offset, .align_mul = 4, .write_mask = 1);
   nir_variable *color = nir_variable_create(b.shader, nir_var_shader_out, glsl_vec4_type(), "color");
   color->data.location = FRAG_RESULT_DATA0;
   nir_store_var(&b, color, nir_imm_vec4(&b, 0, 1, 0, 1), 15);
   nir_shader_gather_info(b.shader, nir_shader_get_entrypoint(b.shader));
   b.shader->info.num_ssbos = atomic < 2 ? slot + 1 : 1;
   b.shader->info.num_images = atomic < 2 ? 0 : slot + 1;
   if (mixed && atomic == 3) {
      b.shader->info.num_ubos = slot ? 13 : 1;
      b.shader->info.first_ubo_is_default_ubo = true;
      b.shader->info.num_textures = 1;
      BITSET_SET(b.shader->info.textures_used, slot ? 15 : 0);
      BITSET_SET(b.shader->info.textures_used_by_txf, slot ? 15 : 0);
   }
   return b.shader;
}

static int run_fragment_storage(struct pipe_context *pipe, struct pipe_resource *buffer,
                                uint32_t *words, size_t bytes, struct pipe_resource *target)
{
   if (bytes != 80 * 4) return 1;
   for (unsigned atomic = 0; atomic < 2; ++atomic) for (unsigned slot = 0; slot <= 15; slot += 15) {
      memset(words, 0xcd, bytes);
      for (unsigned i = 0; i < 64; ++i) words[8 + i] = 100 + i;
      if (atomic) words[72] = 0;
      struct pipe_shader_buffer bindings[16];
      for (unsigned i = 0; i < 16; ++i)
         bindings[i] = (struct pipe_shader_buffer){buffer, 32, (atomic ? 65u : 64u) * 4};
      pipe->set_shader_buffers(pipe, MESA_SHADER_FRAGMENT, 0, slot + 1, bindings, 65535);
      struct pipe_shader_state shader = {.type = PIPE_SHADER_IR_NIR, .ir.nir = build_fragment_storage(atomic, slot, 1, false, false, 0)};
      void *fs = pipe->create_fs_state(pipe, &shader);
      if (!fs) return 1;
      pipe->bind_fs_state(pipe, fs);
      const struct pipe_draw_info info = {.mode = MESA_PRIM_TRIANGLES, .instance_count = 1};
      const struct pipe_draw_start_count_bias draw = {.count = 3};
      pipe->draw_vbo(pipe, &info, 0, NULL, &draw, 1);
      pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
      int rc = ps5_context_last_draw_status(pipe, NULL);
      unsigned correct = 0;
      bool seen[64] = {false};
      for (unsigned i = 0; i < 80; ++i) {
         if (i >= 8 && i < 72) {
            const uint32_t value = words[i];
            if (atomic) {
               if (value < 64 && !seen[value]) { seen[value] = true; ++correct; }
            } else correct += value == 200 + i - 8;
         } else correct += words[i] == (atomic && i == 72 ? 64 : UINT32_C(0xcdcdcdcd));
      }
      struct pipe_transfer *transfer = NULL;
      uint8_t *pixels = rc ? NULL : pipe_texture_map(pipe, target, 0, 0, PIPE_MAP_READ, 0, 0, 8, 8, &transfer);
      unsigned pixel_ok = pixels ? count_pixels(pixels, transfer->stride, 1) : 0;
      if (pixels) pipe->texture_unmap(pipe, transfer);
      pipe->bind_fs_state(pipe, NULL);
      pipe->delete_fs_state(pipe, fs);
      pipe->set_shader_buffers(pipe, MESA_SHADER_FRAGMENT, 0, 16, NULL, 0);
      printf("[ps5-fragment-storage] atomic=%u slot=%u rc=%d words=%u/80 pixels=%u/64\n",
         atomic, slot, rc, correct, pixel_ok);
      fflush(stdout);
      if (rc || correct != 80 || pixel_ok != 64) return 1;
   }
   return 0;
}

static int run_fragment_images(struct pipe_context *pipe, struct pipe_resource *output,
                               uint32_t *words, size_t bytes, unsigned kind, bool mixed, void *sampler, bool array)
{
   int status = 1;
   const unsigned channels = kind < 3 ? 1 : kind < 6 ? 2 : 4;
   const unsigned texel_words = kind >= 9 ? 2 : channels;
   const unsigned layer_bytes = array ? (texel_words == 4 ? 22528 : 14336) : 2048;
   void *fs = NULL;
   struct pipe_sampler_view *sampled = NULL;
   struct pipe_resource *uniform_buffer = NULL;
   const struct pipe_resource templ = {.target = array ? PIPE_TEXTURE_2D_ARRAY : PIPE_TEXTURE_2D, .format = image_formats[kind],
      .width0 = array ? 32 : 8, .height0 = array ? 32 : 8, .depth0 = 1,
      .array_size = array ? 8 : 1, .last_level = array ? 2 : 0,
      .bind = PIPE_BIND_SHADER_IMAGE | PIPE_BIND_SAMPLER_VIEW};
   struct pipe_resource *image = pipe->screen->resource_create(pipe->screen, &templ);
   uint32_t *pixels = NULL;
   size_t image_bytes = 0;
   if (!image || bytes != 320 || ps5_resource_info(image, (void **)&pixels, &image_bytes, NULL) ||
       !pixels || image_bytes != layer_bytes * templ.array_size) goto out;
   const struct pipe_shader_buffer bound = {output, 32, 256};
   pipe->set_shader_buffers(pipe, MESA_SHADER_FRAGMENT, 0, 1, &bound, 1);
   if (mixed) {
      const struct pipe_sampler_view sv = {.target = PIPE_TEXTURE_2D, .format = image_formats[kind],
         .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y,
         .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W};
      sampled = pipe->create_sampler_view(pipe, image, &sv);
      uniform_buffer = pipe_buffer_create(pipe->screen, PIPE_BIND_CONSTANT_BUFFER, PIPE_USAGE_DEFAULT, 32);
      if (!sampled || !uniform_buffer) goto out;
   }
   for (unsigned slot = 0; slot <= 7; slot += 7) {
      const unsigned layer = array ? slot : 0;
      memset(pixels, 0xcd, image_bytes);
      struct pipe_image_view views[8];
      for (unsigned i = 0; i < 8; ++i) views[i] = (struct pipe_image_view){.resource = image,
         .format = image_formats[kind], .access = PIPE_IMAGE_ACCESS_READ_WRITE,
         .u.tex = {.level = templ.last_level, .last_layer = templ.array_size - 1,
                   .single_layer_view = !array}};
      pipe->set_shader_images(pipe, MESA_SHADER_FRAGMENT, 0, slot + 1, 0, views);
      uint32_t uniform = kind ? (slot ? 200u : 100u) : (slot ? UINT32_C(0x3ec00000) : UINT32_C(0x3e000000));
      if (mixed) {
         pipe_buffer_write(pipe, uniform_buffer, 16, 4, &uniform);
         struct pipe_constant_buffer cb = {.buffer = uniform_buffer, .buffer_offset = 16, .buffer_size = 4};
         for (unsigned i = 0; i < 13; ++i) pipe->set_constant_buffer(pipe, MESA_SHADER_FRAGMENT, i, &cb);
         if (!slot) {
            cb = (struct pipe_constant_buffer){.user_buffer = &uniform, .buffer_size = 4};
            pipe->set_constant_buffer(pipe, MESA_SHADER_FRAGMENT, 0, &cb);
         }
         pipe->set_sampler_views(pipe, MESA_SHADER_FRAGMENT, slot ? 15 : 0, 1, 0, &sampled);
         pipe->bind_sampler_states(pipe, MESA_SHADER_FRAGMENT, slot ? 15 : 0, 1, &sampler);
      }
      for (unsigned operation = 2; operation <= (kind == 0 || kind >= 3 || mixed ? 3u : 4u); ++operation) {
         memset(words, 0xcd, bytes); /* Output only; no CPU image access between producer and consumer. */
         struct pipe_shader_state shader = {.type = PIPE_SHADER_IR_NIR,
            .ir.nir = build_fragment_storage(operation, slot, kind, mixed, array, layer)};
         fs = pipe->create_fs_state(pipe, &shader);
         if (!fs) goto out;
         pipe->bind_fs_state(pipe, fs);
         const struct pipe_draw_info info = {.mode = MESA_PRIM_TRIANGLES, .instance_count = 1};
         const struct pipe_draw_start_count_bias draw = {.count = 3};
         pipe->draw_vbo(pipe, &info, 0, NULL, &draw, 1);
         pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
         int rc = ps5_context_last_draw_status(pipe, NULL);
         unsigned correct = 0;
         bool seen[64] = {false};
         for (unsigned i = 0; i < 80; ++i) {
            if (i >= 8 && i < 72) {
               uint32_t value = words[i];
               if (operation == 4) {
                  const uint32_t initial = fragment_image_word(kind, 0, false);
                  value = kind == 2 ? initial - value : value - initial;
                  if (value < 64 && !seen[value]) { seen[value] = true; ++correct; }
               } else {
                  uint32_t expected = fragment_image_word(kind, i - 8 + layer * 64, operation == 3);
                  if (mixed && operation == 3) {
                     if (kind) expected = 2u * fragment_image_word(kind, i - 8, false) + uniform;
                     else if (slot) { float f; memcpy(&f, &expected, 4); f += 0.25f; memcpy(&expected, &f, 4); }
                  }
                  correct += value == expected;
               }
            } else correct += words[i] == UINT32_C(0xcdcdcdcd);
         }
         pipe->bind_fs_state(pipe, NULL); pipe->delete_fs_state(pipe, fs); fs = NULL;
         printf("[ps5-fragment-image%s] mixed=%u kind=%u op=%u slot=%u rc=%d words=%u/80\n", array ? "-array" : "", mixed, kind, operation, slot, rc, correct);
         fflush(stdout);
         if (rc || correct != 80) goto out;
      }
      unsigned correct = 0;
      for (unsigned i = 0; i < image_bytes / 4; ++i) {
         const unsigned start = layer * layer_bytes / 4;
         const unsigned local = i - start;
         uint32_t expected = i >= start && local < 512 && local % 64 < 8 * texel_words ?
            fragment_image_packed_word(kind, layer * 64 + local / 64 * 8 + (local % 64) / texel_words, local % texel_words) : UINT32_C(0xcdcdcdcd);
         if (!i && kind && kind < 3 && !mixed) expected += kind == 2 ? (uint32_t)-64 : 64;
         correct += pixels[i] == expected;
      }
      printf("[ps5-fragment-image%s] kind=%u slot=%u image-and-padding=%u/%u\n", array ? "-array" : "", kind, slot, correct, (unsigned)image_bytes / 4);
      if (correct != image_bytes / 4) goto out;
   }
   status = 0;
out:
   pipe->bind_fs_state(pipe, NULL);
   if (fs) pipe->delete_fs_state(pipe, fs);
   pipe->set_shader_images(pipe, MESA_SHADER_FRAGMENT, 0, 0, 8, NULL);
   pipe->set_shader_buffers(pipe, MESA_SHADER_FRAGMENT, 0, 16, NULL, 0);
   if (mixed) {
      pipe->set_sampler_views(pipe, MESA_SHADER_FRAGMENT, 0, 0, 16, NULL);
      void *none = NULL;
      pipe->bind_sampler_states(pipe, MESA_SHADER_FRAGMENT, 0, 1, &none);
      pipe->bind_sampler_states(pipe, MESA_SHADER_FRAGMENT, 15, 1, &none);
      for (unsigned i = 0; i < 13; ++i) pipe->set_constant_buffer(pipe, MESA_SHADER_FRAGMENT, i, NULL);
   }
   pipe_sampler_view_reference(&sampled, NULL);
   pipe_resource_reference(&uniform_buffer, NULL);
   pipe_resource_reference(&image, NULL);
   return status;
}

static int run_all_slots(struct pipe_context *pipe, uint32_t *words, size_t bytes)
{
   int status = 1;
   struct pipe_resource *images[16] = {0};
   struct pipe_sampler_view *views[16] = {0};
   uint32_t *data[16] = {0}; void *shader = NULL;
   const struct pipe_resource templ = {.target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R32_FLOAT,
      .width0 = 1, .height0 = 1, .depth0 = 1, .array_size = 1, .bind = PIPE_BIND_SAMPLER_VIEW};
   const struct pipe_sampler_view sv = {.target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R32_FLOAT,
      .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y, .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W};
   for (unsigned unit = 0; unit < 16; ++unit) {
      images[unit] = pipe->screen->resource_create(pipe->screen, &templ);
      size_t size = 0;
      if (!images[unit] || ps5_resource_info(images[unit], (void **)&data[unit], &size, NULL) || !data[unit] || size != 256) goto cleanup;
      memset(data[unit], 0xcd, size); data[unit][0] = expected_red(0, unit + 1, 1);
      views[unit] = pipe->create_sampler_view(pipe, images[unit], &sv);
      if (!views[unit]) goto cleanup;
   }
   struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR, .prog = compute_all_slots()};
   shader = pipe->create_compute_state(pipe, &cs);
   if (!shader) goto cleanup;
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 16, 0, views);
   pipe->bind_compute_state(pipe, shader);
   unsigned before = 0, after = 0;
   if (ps5_context_last_compute_status(pipe, &before)) goto cleanup;
   const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
   memset(words, 0xcd, bytes);
   pipe->launch_grid(pipe, &grid);
   pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
   int rc = ps5_context_last_compute_status(pipe, &after);
   unsigned correct = count_sampled(words, 1, 0, 0), source_correct = 0;
   for (unsigned unit = 0; unit < 16; ++unit) for (unsigned i = 0; i < 64; ++i)
      source_correct += data[unit][i] == (i ? GUARD_WORD : expected_red(0, unit + 1, 1));
   printf("[ps5-compute-all-slots] rc=%d dispatches=%u words=%u/80 images=%u/1024\n", rc, after, correct, source_correct);
   status = rc || after != before + 1 || correct != 80 || source_correct != 1024;
cleanup:
   pipe->bind_compute_state(pipe, NULL);
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 16, NULL);
   if (shader) pipe->delete_compute_state(pipe, shader);
   for (unsigned unit = 0; unit < 16; ++unit) {
      pipe_sampler_view_reference(&views[unit], NULL); pipe_resource_reference(&images[unit], NULL);
   }
   return status;
}

static int run_dimensional(struct pipe_context *pipe, uint32_t *words, size_t bytes)
{
   const unsigned targets[] = {PIPE_TEXTURE_1D, PIPE_TEXTURE_1D_ARRAY, PIPE_TEXTURE_3D,
      PIPE_TEXTURE_RECT, PIPE_TEXTURE_2D, PIPE_TEXTURE_2D_ARRAY};
   int status = 1;
   struct pipe_resource *image = NULL;
   struct pipe_sampler_view *view = NULL;
   void *shader = NULL;
   struct pipe_sampler_state ss = {.wrap_s = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
      .wrap_t = PIPE_TEX_WRAP_CLAMP_TO_EDGE, .wrap_r = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
      .min_img_filter = PIPE_TEX_FILTER_NEAREST, .mag_img_filter = PIPE_TEX_FILTER_NEAREST};
   void *sampler = pipe->create_sampler_state(pipe, &ss);
   if (!sampler || bytes != 320) goto cleanup;
   pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &sampler);
   for (unsigned trial = 0; trial < 2 * ARRAY_SIZE(targets); ++trial) {
      const unsigned kind = trial % ARRAY_SIZE(targets);
      const bool vector = trial >= ARRAY_SIZE(targets);
      const unsigned channels = vector ? 4 : 1;
      const enum pipe_format format = vector ? PIPE_FORMAT_R32G32B32A32_FLOAT : PIPE_FORMAT_R32_FLOAT;
      if (kind == 3) {
         void *none = NULL; pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &none);
         pipe->delete_sampler_state(pipe, sampler);
         ss.unnormalized_coords = true;
         sampler = pipe->create_sampler_state(pipe, &ss);
         if (!sampler) goto cleanup;
         pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &sampler);
      }
      const unsigned height = kind >= 2 ? 4 : 1, layers = kind == 1 || kind == 2 || kind == 5 ? 4 : 1;
      const struct pipe_resource templ = {.target = targets[kind], .format = format,
         .width0 = 4, .height0 = height, .depth0 = kind == 2 ? 4 : 1,
         .array_size = kind == 1 || kind == 5 ? 4 : 1,
         .nr_samples = kind >= 4 ? 4 : 0, .nr_storage_samples = kind >= 4 ? 4 : 0,
         .bind = PIPE_BIND_SAMPLER_VIEW | (kind >= 4 ? PIPE_BIND_RENDER_TARGET : 0)};
      image = pipe->screen->resource_create(pipe->screen, &templ);
      float *pixels = NULL; size_t size = 0, allocation = 0;
      if (!image || ps5_resource_info(image, (void **)&pixels, &size, &allocation) || !pixels) goto cleanup;
      if (kind >= 4) {
         if (size != 4 * height * layers * channels * 4 * 4 || allocation < 65536 * layers) goto cleanup;
         /* Constant per physical layer: checks sample 0/3 access and layer
          * selection, not distinct per-sample values or upload performance. */
         memset(pixels, 0xcd, allocation);
         for (unsigned i = 0; i < 16384 * layers; ++i) pixels[i] = 1 + 16 * (i / 16384);
      } else {
         if (size != 256 * height * layers) goto cleanup;
         memset(pixels, 0xcd, size);
         for (unsigned z = 0; z < layers; ++z) for (unsigned y = 0; y < height; ++y)
            for (unsigned x = 0; x < 4; ++x) for (unsigned c = 0; c < channels; ++c)
               pixels[(z * height + y) * 64 + x * channels + c] = 1 + x + 4 * y + 16 * z + 100 * c;
      }
      const struct pipe_sampler_view sv = {.target = targets[kind], .format = format,
         .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y,
         .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W,
         .u.tex.last_layer = kind == 1 || kind == 5 ? 3 : 0};
      view = pipe->create_sampler_view(pipe, image, &sv);
      if (!view) goto cleanup;
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &view);
      for (unsigned filtered = 0; filtered < 2; ++filtered) {
         const struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR,
            .prog = compute_dimensional(kind, filtered)};
         shader = pipe->create_compute_state(pipe, &cs);
         if (!shader) goto cleanup;
         pipe->bind_compute_state(pipe, shader);
         unsigned before = 0, after = 0;
         if (ps5_context_last_compute_status(pipe, &before)) goto cleanup;
         memset(words, 0xcd, bytes);
         const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
         int rc = ps5_context_last_compute_status(pipe, &after);
         unsigned correct = 0;
         for (unsigned i = 0; i < 80; ++i) {
            uint32_t expected = GUARD_WORD;
            if (i >= 8 && i < 72) {
               const unsigned lane = (i - 8) % 4, id = (i - 8) / 4;
               float red = kind >= 4 ? 1 + (kind == 5 ? 16 * (id >> 2) : 0) :
                  1 + (id & 3) + (kind == 1 || kind == 2 ? 16 * (id >> 2) : 0) + (kind >= 2 ? 4 * (id >> 2) : 0);
               float value = vector ? red + (kind >= 4 ? 0 : 100 * lane) : lane == 3 ? 1 : lane ? 0 : red;
               memcpy(&expected, &value, 4);
            }
            correct += words[i] == expected;
         }
         printf("[ps5-compute-dimensional] kind=%u channels=%u filtered=%u rc=%d words=%u/80 dispatch=%u\n",
                kind, channels, filtered, rc, correct, after - before);
         if (rc || after != before + 1 || correct != 80) goto cleanup;
         pipe->bind_compute_state(pipe, NULL); pipe->delete_compute_state(pipe, shader); shader = NULL;
      }
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 1, NULL);
      pipe_sampler_view_reference(&view, NULL); pipe_resource_reference(&image, NULL);
   }
   status = 0;
cleanup:
   pipe->bind_compute_state(pipe, NULL);
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 1, NULL);
   void *none = NULL; pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &none);
   if (shader) pipe->delete_compute_state(pipe, shader);
   if (sampler) pipe->delete_sampler_state(pipe, sampler);
   pipe_sampler_view_reference(&view, NULL); pipe_resource_reference(&image, NULL);
   return status;
}

static int run_compute_uniforms(struct pipe_context *pipe, uint32_t *words, size_t bytes)
{
   int status = 1;
   void *shaders[4] = {0};
   struct pipe_resource *ubo = pipe_buffer_create(pipe->screen, PIPE_BIND_CONSTANT_BUFFER, PIPE_USAGE_DEFAULT, 32);
   if (!ubo || bytes != 320) goto out;
   for (unsigned variant = 0; variant < ARRAY_SIZE(shaders); ++variant) {
      const struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR,
         .prog = variant < 2 ? build_compute_uniforms(variant & 1) : build_compute_user_ubo(variant & 1)};
      shaders[variant] = pipe->create_compute_state(pipe, &cs);
      if (!shaders[variant]) goto out;
   }
   unsigned expected_dispatches = 0;
   if (ps5_context_last_compute_status(pipe, &expected_dispatches)) goto out;
   const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
   for (unsigned pass = 0; pass < 2; ++pass) {
      uint32_t defaults[8] = {0, 0, 0, 0, 100 + pass, 200 + pass, 300 + pass, 400 + pass};
      const uint32_t user = 7 + pass;
      const struct pipe_constant_buffer cb0 = {.user_buffer = defaults, .buffer_size = sizeof(defaults)};
      const struct pipe_constant_buffer cb1 = {.buffer = ubo, .buffer_offset = 16, .buffer_size = 4};
      pipe_buffer_write(pipe, ubo, 16, 4, &user);
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 0, &cb0);
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 1, &cb1);
      memset(defaults, 0, sizeof(defaults)); /* Driver must retain a copy of CB0. */
      for (unsigned variant = 0; variant < ARRAY_SIZE(shaders); ++variant) {
         memset(words, 0xcd, bytes);
         pipe->bind_compute_state(pipe, shaders[variant]);
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
         unsigned dispatches = 0, correct = 0;
         int rc = ps5_context_last_compute_status(pipe, &dispatches);
         const unsigned base = variant < 2 ? 4907 + pass * 16 : user;
         for (unsigned i = 0; i < 80; ++i)
            correct += words[i] == (i >= 8 && i < 24 ? base + i - 8 : GUARD_WORD);
         printf("[ps5-compute-default-uniforms] pass=%u explicit=%u user-only=%u rc=%d dispatches=%u words=%u/80\n",
            pass, variant & 1, variant >= 2, rc, dispatches, correct);
         fflush(stdout);
         if (rc || dispatches != ++expected_dispatches || correct != 80) goto out;
      }
   }
   status = 0;
out:
   pipe->bind_compute_state(pipe, NULL);
   for (unsigned i = 0; i < ARRAY_SIZE(shaders); ++i)
      if (shaders[i]) pipe->delete_compute_state(pipe, shaders[i]);
   for (unsigned i = 0; i < 2; ++i)
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, i, NULL);
   pipe_resource_reference(&ubo, NULL);
   return status;
}

static int run_mips(struct pipe_context *pipe, uint32_t *words, size_t bytes, unsigned layers, unsigned kind)
{
   int status = 1;
   struct pipe_resource *image = NULL;
   struct pipe_sampler_view *views[3] = {0};
   void *states[2] = {0}, *shaders[4][2][4] = {{{0}}}, *writers[4] = {0};
   void *dynamic_shaders[3][3][2] = {{{0}}};
   const unsigned first[3] = {0, 1, 2}, last[3] = {3, 3, 2};
   const unsigned masks[3] = {3, 1, 0};
   const struct pipe_resource templ = {.target = layers > 1 ? PIPE_TEXTURE_2D_ARRAY : PIPE_TEXTURE_2D,
      .format = image_formats[kind],
      .width0 = 16, .height0 = 8, .depth0 = 1, .array_size = layers, .last_level = 3,
      .bind = PIPE_BIND_SAMPLER_VIEW | PIPE_BIND_SHADER_IMAGE};
   image = pipe->screen->resource_create(pipe->screen, &templ);
   void *data = NULL; size_t size = 0;
   if (!image || ps5_resource_info(image, &data, &size, NULL) || !data || size != 3840 * layers) goto cleanup;
   memset(data, 0xcd, size);
   for (unsigned layer = 0; layer < layers; ++layer) for (unsigned level = 0; level < 4; ++level) {
      struct pipe_transfer *transfer = NULL;
      uint8_t *mapped = pipe_texture_map(pipe, image, level, layer, PIPE_MAP_WRITE,
         0, 0, 16 >> level, 8 >> level, &transfer);
      if (!mapped) goto cleanup;
      const uint32_t value = mip_word(kind, level, layer, 1, false);
      for (unsigned y = 0; y < (8u >> level); ++y) for (unsigned x = 0; x < (16u >> level); ++x)
         memcpy(mapped + y * transfer->stride + x * 4, &value, 4);
      pipe->texture_unmap(pipe, transfer);
   }
   for (unsigned i = 0; i < 3; ++i) {
      struct pipe_sampler_view sv = {.target = templ.target, .format = templ.format,
         .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y,
         .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W};
      sv.u.tex.first_level = first[i]; sv.u.tex.last_level = last[i];
      sv.u.tex.last_layer = layers - 1;
      views[i] = pipe->create_sampler_view(pipe, image, &sv);
      if (!views[i]) goto cleanup;
   }
   for (unsigned i = 0; i < 2; ++i) {
      const struct pipe_sampler_state ss = {.wrap_s = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
         .wrap_t = PIPE_TEX_WRAP_CLAMP_TO_EDGE, .wrap_r = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
         .min_img_filter = PIPE_TEX_FILTER_NEAREST, .mag_img_filter = PIPE_TEX_FILTER_NEAREST,
         .min_mip_filter = i ? PIPE_TEX_MIPFILTER_LINEAR : PIPE_TEX_MIPFILTER_NEAREST, .max_lod = 3};
      states[i] = pipe->create_sampler_state(pipe, &ss);
      if (!states[i]) goto cleanup;
   }
   for (unsigned op = 0; op < (kind ? 2u : 4u); ++op) for (unsigned unit = 0; unit < 2; ++unit)
      for (unsigned level = 0; level < (op == 3 ? 1u : 4u); ++level) {
         struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR,
            .prog = compute_mip(op, unit ? 15 : 0, level, layers, kind, false)};
         shaders[op][unit][level] = pipe->create_compute_state(pipe, &cs);
         if (!shaders[op][unit][level]) goto cleanup;
      }
   for (unsigned level = 0; level < 4; ++level) {
      struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR, .prog = write_mip(level, layers > 1, kind)};
      writers[level] = pipe->create_compute_state(pipe, &cs);
      if (!writers[level]) goto cleanup;
   }
   for (unsigned view = 0; view < 3; ++view) for (unsigned op = 0; op < (kind ? 2u : 3u); ++op)
      for (unsigned unit = 0; unit < 2; ++unit) {
         struct pipe_compute_state cs = {.ir_type = PIPE_SHADER_IR_NIR,
            .prog = compute_mip(op, unit ? 15 : 0, op == 2 ? last[view] - first[view] : masks[view], layers, kind, true)};
         dynamic_shaders[view][op][unit] = pipe->create_compute_state(pipe, &cs);
         if (!dynamic_shaders[view][op][unit]) goto cleanup;
      }
   unsigned expected_dispatches = 0;
   if (ps5_context_last_compute_status(pipe, &expected_dispatches)) goto cleanup;
   const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
   for (unsigned pass = 0; pass < 3; ++pass) {
   const float sign = pass == 1 ? -1 : 1;
   if (pass) {
      const struct pipe_constant_buffer cb = {.user_buffer = &sign, .buffer_size = sizeof(sign)};
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 0, &cb);
      const struct pipe_grid_info writer_grid = {.work_dim = layers > 1 ? 2 : 1,
         .block = {16, 1, 1}, .grid = {8, layers, 1}};
      for (unsigned level = 0; level < 4; ++level) {
         struct pipe_image_view iv = {.resource = image, .format = image_formats[kind],
            .access = PIPE_IMAGE_ACCESS_WRITE};
         iv.u.tex.level = level;
         iv.u.tex.last_layer = layers - 1;
         iv.u.tex.single_layer_view = layers == 1;
         pipe->set_shader_images(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &iv);
         pipe->bind_compute_state(pipe, writers[level]);
         pipe->launch_grid(pipe, &writer_grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_IMAGE | PIPE_BARRIER_TEXTURE);
         unsigned dispatches = 0;
         int rc = ps5_context_last_compute_status(pipe, &dispatches);
         printf("[ps5-compute-mip-write] kind=%u layers=%u pass=%u level=%u rc=%d dispatches=%u\n", kind, layers, pass, level, rc, dispatches);
         fflush(stdout);
         if (rc || dispatches != ++expected_dispatches) goto cleanup;
      }
   }
   for (unsigned view = 0; view < 3; ++view) for (unsigned op = 0; op < (kind ? 2u : 4u); ++op)
      for (unsigned unit = 0; unit < 2; ++unit)
         for (unsigned level = 0; level < (op == 3 ? (last[view] > first[view] ? 1u : 0u) : last[view] - first[view] + 1); ++level) {
            const unsigned slot = unit ? 15 : 0;
            pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, slot, 1, 0, &views[view]);
            pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, slot, 1, &states[op == 3]);
            pipe->bind_compute_state(pipe, shaders[op][unit][level]);
            memset(words, 0xcd, bytes);
            pipe->launch_grid(pipe, &grid);
            pipe->memory_barrier(pipe, PIPE_BARRIER_MAPPED_BUFFER | PIPE_BARRIER_SHADER_BUFFER);
            unsigned dispatches = 0;
            int rc = ps5_context_last_compute_status(pipe, &dispatches);
            unsigned correct = count_mip(words, op, first[view] + level, sign, layers, kind);
            printf("[ps5-compute-mip] kind=%u layers=%u pass=%u view=%u op=%u unit=%u lod=%u rc=%d dispatches=%u words=%u/80 first=%08x,%08x\n",
               kind, layers, pass, view, op, slot, level, rc, dispatches, correct, words[8], words[9]);
            fflush(stdout);
            if (rc || dispatches != ++expected_dispatches || correct != 80) goto cleanup;
         }
   for (unsigned view = 0; view < 3; ++view) for (unsigned op = 0; op < (kind ? 2u : 3u); ++op)
      for (unsigned unit = 0; unit < 2; ++unit) {
         const unsigned slot = unit ? 15 : 0;
         pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, slot, 1, 0, &views[view]);
         if (op == 2) pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, slot, 1, &states[1]);
         pipe->bind_compute_state(pipe, dynamic_shaders[view][op][unit]);
         memset(words, 0xcd, bytes);
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_MAPPED_BUFFER | PIPE_BARRIER_SHADER_BUFFER);
         unsigned dispatches = 0;
         int rc = ps5_context_last_compute_status(pipe, &dispatches);
         unsigned correct = count_dynamic_mip(words, op, first[view], op == 2 ? last[view] - first[view] : masks[view], sign, layers, kind);
         printf("[ps5-compute-dynamic-mip] kind=%u layers=%u pass=%u view=%u op=%u unit=%u rc=%d dispatches=%u words=%u/80\n",
            kind, layers, pass, view, op, slot, rc, dispatches, correct);
         fflush(stdout);
         if (rc || dispatches != ++expected_dispatches || correct != 80) goto cleanup;
      }
   /* Check all uploaded pixels and row padding after sampling. */
   unsigned offset = 0, correct = 0;
   for (unsigned layer = 0; layer < layers; ++layer) for (unsigned level = 4; level-- > 0;) {
      const uint32_t bits = mip_word(kind, level, layer, sign, false);
      for (unsigned y = 0; y < (8u >> level); ++y) for (unsigned x = 0; x < 64; ++x)
         correct += ((uint32_t *)data)[offset + y * 64 + x] == (x < (16u >> level) ? bits : GUARD_WORD);
      offset += (8u >> level) * 64;
   }
   printf("[ps5-compute-mip] kind=%u layers=%u pass=%u image=%u/%u\n", kind, layers, pass, correct, 960 * layers);
   if (correct != 960 * layers) goto cleanup;
   }
   status = 0;
cleanup:
   pipe->bind_compute_state(pipe, NULL);
   pipe->set_shader_images(pipe, MESA_SHADER_COMPUTE, 0, 0, 8, NULL);
   void *none = NULL;
   pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &none);
   pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 15, 1, &none);
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 16, NULL);
   for (unsigned i = 0; i < 3; ++i) pipe_sampler_view_reference(&views[i], NULL);
   for (unsigned i = 0; i < 2; ++i) if (states[i]) pipe->delete_sampler_state(pipe, states[i]);
   for (unsigned i = 0; i < 4; ++i) if (writers[i]) pipe->delete_compute_state(pipe, writers[i]);
   for (unsigned view = 0; view < 3; ++view) for (unsigned op = 0; op < 3; ++op)
      for (unsigned unit = 0; unit < 2; ++unit)
         if (dynamic_shaders[view][op][unit]) pipe->delete_compute_state(pipe, dynamic_shaders[view][op][unit]);
   for (unsigned op = 0; op < 4; ++op) for (unsigned unit = 0; unit < 2; ++unit)
      for (unsigned level = 0; level < 4; ++level)
         if (shaders[op][unit][level]) pipe->delete_compute_state(pipe, shaders[op][unit][level]);
   pipe_resource_reference(&image, NULL);
   return status;
}


/* Six dispatches appended to the established batch. The blobs are deliberately
 * not prepared here: the real create_compute_state owns and lowers their NIR. */
static int run_parsed_glsl(struct pipe_context *pipe, struct pipe_resource *output,
                           uint32_t *words, size_t bytes, void *sampler)
{
   int status = 1;
   void *shaders[3] = {0};
   struct pipe_resource *ubo = NULL, *texture = NULL;
   struct pipe_sampler_view *view = NULL;
   if (bytes != 320 || !words || !sampler ||
       !ps5_glsl_options_match(pipe->screen->nir_options[MESA_SHADER_COMPUTE]))
      goto out;
   ubo = pipe_buffer_create(pipe->screen, PIPE_BIND_CONSTANT_BUFFER, PIPE_USAGE_DEFAULT, 32);
   const struct pipe_resource templ = {
      .target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R32_FLOAT,
      .width0 = 2, .height0 = 2, .depth0 = 1, .array_size = 1,
      .bind = PIPE_BIND_SAMPLER_VIEW
   };
   texture = pipe->screen->resource_create(pipe->screen, &templ);
   if (!ubo || !texture) goto out;
   const struct pipe_sampler_view sv = {
      .target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R32_FLOAT,
      .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y,
      .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W
   };
   view = pipe->create_sampler_view(pipe, texture, &sv);
   if (!view) goto out;
   for (unsigned fixture = 0; fixture < 3; ++fixture) {
      nir_shader *nir = load_parsed_glsl(fixture, pipe->screen->nir_options[MESA_SHADER_COMPUTE]);
      if (!nir) goto out;
      const struct pipe_compute_state cs = {
         .ir_type = PIPE_SHADER_IR_NIR, .prog = nir, .static_shared_mem = nir->info.shared_size
      };
      shaders[fixture] = pipe->create_compute_state(pipe, &cs);
      /* Ownership transferred even when the real driver reports failure. */
      if (!shaders[fixture]) goto out;
   }
   const struct pipe_shader_buffer bound = {output, 32, 256};
   pipe->set_shader_buffers(pipe, MESA_SHADER_COMPUTE, 0, 1, &bound, 1);
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &view);
   pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &sampler);
   unsigned expected_dispatches = 0;
   if (ps5_context_last_compute_status(pipe, &expected_dispatches)) goto out;
   const struct pipe_grid_info grid = {
      .work_dim = 1, .block = {1, 1, 1}, .grid = {1, 1, 1}
   };
   printf("[ps5-compute-parsed-glsl] receipt=%s\n", PS5_GLSL_RECEIPT_SHA256);
   for (unsigned pass = 0; pass < 2; ++pass) {
      const uint32_t user[4] = {pass ? 11 : 7, GUARD_WORD, GUARD_WORD, GUARD_WORD};
      pipe_buffer_write(pipe, ubo, 16, sizeof(user), user);
      const struct pipe_constant_buffer cb1 = {.buffer = ubo, .buffer_offset = 16, .buffer_size = sizeof(user)};
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 1, &cb1);
      struct pipe_transfer *transfer = NULL;
      uint8_t *mapped = pipe_texture_map(pipe, texture, 0, 0, PIPE_MAP_WRITE, 0, 0, 2, 2, &transfer);
      if (!mapped) goto out;
      const uint32_t texel = parsed_glsl_expected(2, pass);
      for (unsigned y = 0; y < 2; ++y)
         for (unsigned x = 0; x < 2; ++x)
            memcpy(mapped + y * transfer->stride + x * 4, &texel, 4);
      pipe->texture_unmap(pipe, transfer);
      for (unsigned fixture = 0; fixture < 3; ++fixture) {
         uint32_t defaults[PS5_GLSL_DEFAULT_BYTES / 4];
         for (unsigned i = 0; i < ARRAY_SIZE(defaults); ++i) defaults[i] = UINT32_C(0xdeadbeef);
         if (fixture == 0) defaults[PS5_GLSL_ADDEND_OFFSET / 4] = pass ? 29 : 13;
         const struct pipe_constant_buffer cb0 = {.user_buffer = defaults, .buffer_size = sizeof(defaults)};
         pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 0, &cb0);
         memset(defaults, 0, sizeof(defaults)); /* Real uploader must own its copy. */
         memset(words, 0xcd, bytes);
         pipe->bind_compute_state(pipe, shaders[fixture]);
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
         unsigned dispatches = 0;
         int rc = ps5_context_last_compute_status(pipe, &dispatches);
         unsigned correct = count_parsed_glsl(words, parsed_glsl_expected(fixture, pass));
         printf("[ps5-compute-parsed-glsl] pass=%u fixture=%u rc=%d dispatches=%u words=%u/80 value=%08x\n",
                pass, fixture, rc, dispatches, correct, words[8]);
         fflush(stdout);
         if (rc || dispatches != ++expected_dispatches || correct != 80) goto out;
      }
   }
   status = 0;
out:
   pipe->bind_compute_state(pipe, NULL);
   for (unsigned i = 0; i < 3; ++i)
      if (shaders[i]) pipe->delete_compute_state(pipe, shaders[i]);
   for (unsigned i = 0; i < 2; ++i)
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, i, NULL);
   pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 1, NULL);
   void *none = NULL;
   pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &none);
   pipe->set_shader_buffers(pipe, MESA_SHADER_COMPUTE, 0, 1, NULL, 0);
   pipe_sampler_view_reference(&view, NULL);
   pipe_resource_reference(&texture, NULL);
   pipe_resource_reference(&ubo, NULL);
   return status;
}

int main(void)
{
   int status = 1;
   struct pipe_screen *screen = ps5_screen_create();
   struct pipe_context *pipe = screen ? screen->context_create(screen, NULL, 0) : NULL;
   struct pipe_resource *images[3] = {0}, *target = NULL, *render_pool = NULL;
   struct pipe_resource *sample_output = NULL;
   void *sample_cs[3][4] = {{0}};
   void *filtered_cs[2][2] = {{0}}, *linear_sampler = NULL, *wrap_samplers[2][2] = {{0}};
   struct pipe_sampler_view *views[3] = {0};
   void *writers[3] = {0}, *fragments[3] = {0}, *vs = NULL, *sampler = NULL;
   void *blend = NULL, *rasterizer = NULL, *depth = NULL;
   psbc_init();
   if (!pipe || !pipe->memory_barrier)
      goto cleanup;
   printf("[ps5-compute-render] explicit-memory-barrier-batch=1\n");
   fflush(stdout);
   /* The graphics backend requires its normal render pool even for offscreen
    * draws. It may open VideoOut internally; this test never swaps buffers. */
   const struct pipe_resource pool_template = {.target = PIPE_TEXTURE_2D,
      .format = PIPE_FORMAT_R8G8B8A8_UNORM, .width0 = PS5_SCANOUT_WIDTH,
      .height0 = PS5_SCANOUT_HEIGHT, .depth0 = 1, .array_size = 1,
      .bind = PIPE_BIND_RENDER_TARGET | PIPE_BIND_DISPLAY_TARGET};
   render_pool = screen->resource_create(screen, &pool_template);
   if (!render_pool) {
      printf("[ps5-compute-render] setup-failed render-pool=%ux%u\n",
         (unsigned)PS5_SCANOUT_WIDTH, (unsigned)PS5_SCANOUT_HEIGHT);
      goto cleanup;
   }
   struct pipe_resource templ = {.target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R32_FLOAT,
      .width0 = 17, .height0 = 3, .depth0 = 1, .array_size = 1,
      .bind = PIPE_BIND_SHADER_IMAGE | PIPE_BIND_SAMPLER_VIEW};
   void *image_data[3] = {0};
   for (unsigned kind = 0; kind < 3; ++kind) {
      templ.format = image_formats[kind];
      images[kind] = screen->resource_create(screen, &templ);
      size_t size = 0;
      if (!images[kind] || ps5_resource_info(images[kind], &image_data[kind], &size, NULL) ||
          !image_data[kind] || size != IMAGE_WORDS * 4)
         goto cleanup;
      memset(image_data[kind], 0xcd, size); /* No CPU source writes after initialization. */
   }
   templ.format = PIPE_FORMAT_R8G8B8A8_UNORM;
   templ.width0 = templ.height0 = 8;
   templ.bind = PIPE_BIND_RENDER_TARGET;
   target = screen->resource_create(screen, &templ);
   if (!target)
      goto cleanup;
   struct pipe_compute_state compute = {.ir_type = PIPE_SHADER_IR_NIR};
   struct pipe_shader_state shader = {.type = PIPE_SHADER_IR_NIR, .ir.nir = build_vertex()};
   vs = pipe->create_vs_state(pipe, &shader);
   if (!vs)
      goto cleanup;
   pipe->bind_vs_state(pipe, vs);
   struct pipe_sampler_view sv = {.target = PIPE_TEXTURE_2D,
      .swizzle_r = PIPE_SWIZZLE_X, .swizzle_g = PIPE_SWIZZLE_Y,
      .swizzle_b = PIPE_SWIZZLE_Z, .swizzle_a = PIPE_SWIZZLE_W};
   for (unsigned kind = 0; kind < 3; ++kind) {
      sv.format = image_formats[kind];
      views[kind] = pipe->create_sampler_view(pipe, images[kind], &sv);
      compute.prog = build_compute(kind);
      writers[kind] = pipe->create_compute_state(pipe, &compute);
      shader.ir.nir = build_fragment(kind);
      fragments[kind] = pipe->create_fs_state(pipe, &shader);
      if (!views[kind] || !writers[kind] || !fragments[kind])
         goto cleanup;
   }
   const struct pipe_sampler_state ss = {.wrap_s = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
      .wrap_t = PIPE_TEX_WRAP_CLAMP_TO_EDGE, .wrap_r = PIPE_TEX_WRAP_CLAMP_TO_EDGE,
      .min_img_filter = PIPE_TEX_FILTER_NEAREST, .mag_img_filter = PIPE_TEX_FILTER_NEAREST,
      .min_mip_filter = PIPE_TEX_MIPFILTER_NONE};
   sampler = pipe->create_sampler_state(pipe, &ss);
   struct pipe_sampler_state linear = ss;
   linear.min_img_filter = linear.mag_img_filter = PIPE_TEX_FILTER_LINEAR;
   linear_sampler = pipe->create_sampler_state(pipe, &linear);
   for (unsigned wrap = 0; wrap < 2; ++wrap) for (unsigned filter = 0; filter < 2; ++filter) {
      struct pipe_sampler_state state = filter ? linear : ss;
      state.wrap_s = state.wrap_t = state.wrap_r = wrap ? PIPE_TEX_WRAP_MIRROR_REPEAT : PIPE_TEX_WRAP_REPEAT;
      wrap_samplers[wrap][filter] = pipe->create_sampler_state(pipe, &state);
      if (!wrap_samplers[wrap][filter]) goto cleanup;
   }
   const struct pipe_blend_state bs = {.rt[0].colormask = PIPE_MASK_RGBA};
   blend = pipe->create_blend_state(pipe, &bs);
   const struct pipe_rasterizer_state rs = {.front_ccw = true,
      .fill_front = PIPE_POLYGON_MODE_FILL, .fill_back = PIPE_POLYGON_MODE_FILL,
      .line_width = 1, .point_size = 1, .depth_clip_near = true, .depth_clip_far = true,
      .half_pixel_center = true};
   rasterizer = pipe->create_rasterizer_state(pipe, &rs);
   const struct pipe_depth_stencil_alpha_state ds = {0};
   depth = pipe->create_depth_stencil_alpha_state(pipe, &ds);
   if (!sampler || !linear_sampler || !blend || !rasterizer || !depth)
      goto cleanup;
   const struct pipe_resource output_template = {.target = PIPE_BUFFER,
      .format = PIPE_FORMAT_R8_UNORM, .width0 = 80 * 4, .height0 = 1,
      .depth0 = 1, .array_size = 1, .bind = PIPE_BIND_SHADER_BUFFER};
   sample_output = screen->resource_create(screen, &output_template);
   uint32_t *sample_words = NULL;
   size_t sample_bytes = 0;
   if (!sample_output || ps5_resource_info(sample_output, (void **)&sample_words, &sample_bytes, NULL) ||
       !sample_words || sample_bytes != 80 * 4)
      goto cleanup;
   const struct pipe_shader_buffer output_binding = {sample_output, 8 * 4, 64 * 4};
   pipe->set_shader_buffers(pipe, MESA_SHADER_COMPUTE, 0, 1, &output_binding, 1);
   for (unsigned kind = 0; kind < 3; ++kind) for (unsigned i = 0; i < 4; ++i) {
      compute.prog = compute_sample(i & 1 ? 3 : kind, i >= 2 ? 15 : 0);
      sample_cs[kind][i] = pipe->create_compute_state(pipe, &compute);
      if (!sample_cs[kind][i])
         goto cleanup;
   }
   for (unsigned outside = 0; outside < 2; ++outside) for (unsigned i = 0; i < 2; ++i) {
      /* Exercise ordinary texture() inside the image; outside-coordinate
       * cases retain explicit LOD zero as the native reference. */
      compute.prog = compute_sample(outside ? 5 : 6, i ? 15 : 0);
      filtered_cs[outside][i] = pipe->create_compute_state(pipe, &compute);
      if (!filtered_cs[outside][i]) goto cleanup;
   }
   pipe->bind_sampler_states(pipe, MESA_SHADER_FRAGMENT, 0, 1, &sampler);
   pipe->bind_blend_state(pipe, blend);
   pipe->bind_rasterizer_state(pipe, rasterizer);
   pipe->bind_depth_stencil_alpha_state(pipe, depth);
   const struct pipe_viewport_state vp = {.scale = {4, 4, 0.5}, .translate = {4, 4, 0.5}};
   pipe->set_viewport_states(pipe, 0, 1, &vp);
   const struct pipe_framebuffer_state fb = {.width = 8, .height = 8, .nr_cbufs = 1,
      .cbufs[0] = {.texture = target, .format = PIPE_FORMAT_R8G8B8A8_UNORM}};
   pipe->set_framebuffer_state(pipe, &fb);
   for (unsigned phase = 0; phase < 12; ++phase) {
      const unsigned kind = phase / 4;
      struct pipe_sampler_view *view = views[kind];
      const struct pipe_image_view iv = {.resource = images[kind], .format = image_formats[kind],
         .access = PIPE_IMAGE_ACCESS_WRITE};
      pipe->set_shader_images(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &iv);
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &view);
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 15, 1, 0, &view);
      pipe->set_sampler_views(pipe, MESA_SHADER_FRAGMENT, 0, 1, 0, &view);
      pipe->bind_fs_state(pipe, fragments[kind]);
      const float sign = phase & 1 ? 1 : -1;
      float constants[4] = {sign, 0, 0, 0};
      const struct pipe_constant_buffer cb = {.user_buffer = constants, .buffer_size = sizeof(constants)};
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 0, &cb);
      memset(constants, 0, sizeof(constants)); /* The constant uploader must own its copy. */
      const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
      printf("[ps5-compute-render] phase=%u dispatch-start\n", phase);
      fflush(stdout);
      pipe->bind_compute_state(pipe, writers[kind]);
      pipe->launch_grid(pipe, &grid);
      pipe->memory_barrier(pipe, PIPE_BARRIER_IMAGE | PIPE_BARRIER_TEXTURE);
      unsigned dispatches = 0, draws = 0;
      int compute_rc = ps5_context_last_compute_status(pipe, &dispatches);
      if (compute_rc || dispatches != phase * 5 + 1)
         goto cleanup;
      /* No CPU image map/read/copy between its GPU producer and sampler consumer. */
      const struct pipe_draw_info info = {.mode = MESA_PRIM_TRIANGLES, .instance_count = 1};
      const struct pipe_draw_start_count_bias draw = {.count = 3};
      pipe->draw_vbo(pipe, &info, 0, NULL, &draw, 1);
      pipe->memory_barrier(pipe, PIPE_BARRIER_ALL);
      int draw_rc = ps5_context_last_draw_status(pipe, &draws);
      struct pipe_transfer *transfer = NULL;
      uint8_t *pixels = draw_rc ? NULL : pipe_texture_map(pipe, target, 0, 0,
         PIPE_MAP_READ, 0, 0, 8, 8, &transfer);
      unsigned pixel_ok = pixels ? count_pixels(pixels, transfer->stride, sign) : 0;
      if (pixels)
         pipe->texture_unmap(pipe, transfer);
      if (draw_rc || pixel_ok != 64)
         goto cleanup;
      for (unsigned i = 0; i < 4; ++i) {
         memset(sample_words, 0xcd, sample_bytes); /* Output only; source stays GPU-written. */
         pipe->bind_compute_state(pipe, sample_cs[kind][i]);
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_MAPPED_BUFFER | PIPE_BARRIER_SHADER_BUFFER);
         unsigned sampled_dispatches = 0;
         int rc = ps5_context_last_compute_status(pipe, &sampled_dispatches);
         unsigned correct = count_sampled(sample_words, sign, i & 1, kind);
         printf("[ps5-compute-sampled] phase=%u case=%u rc=%d dispatches=%u words=%u/80\n",
            phase, i, rc, sampled_dispatches, correct);
         if (correct != 80)
            printf("[ps5-compute-sampled] first=%08x,%08x,%08x,%08x next=%08x,%08x,%08x,%08x guards=%08x/%08x\n",
               sample_words[8], sample_words[9], sample_words[10], sample_words[11],
               sample_words[12], sample_words[13], sample_words[14], sample_words[15],
               sample_words[0], sample_words[79]);
         if (rc || sampled_dispatches != phase * 5 + i + 2 || correct != 80)
            goto cleanup;
      }
      unsigned image_ok = count_image(image_data[kind], sign, kind);
      printf("[ps5-compute-render] phase=%u compute=%d/%u draw=%d/%u pixels=%u/64 image=%u/%u\n",
         phase, compute_rc, dispatches, draw_rc, draws, pixel_ok, image_ok, IMAGE_WORDS);
      fflush(stdout);
      if (draw_rc || draws != phase + 1 || pixel_ok != 64 || image_ok != IMAGE_WORDS)
         goto cleanup;
   }
   for (unsigned phase = 0; phase < 2; ++phase) {
      const float sign = phase ? 1 : -1;
      const struct pipe_constant_buffer cb = {.user_buffer = &sign, .buffer_size = sizeof(sign)};
      const struct pipe_image_view iv = {.resource = images[0], .format = image_formats[0],
         .access = PIPE_IMAGE_ACCESS_WRITE};
      const struct pipe_grid_info grid = {.work_dim = 1, .block = {16, 1, 1}, .grid = {1, 1, 1}};
      pipe->set_shader_images(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &iv);
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 1, 0, &views[0]);
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 15, 1, 0, &views[0]);
      pipe->set_constant_buffer(pipe, MESA_SHADER_COMPUTE, 0, &cb);
      pipe->bind_compute_state(pipe, writers[0]);
      pipe->launch_grid(pipe, &grid);
      pipe->memory_barrier(pipe, PIPE_BARRIER_IMAGE | PIPE_BARRIER_TEXTURE);
      unsigned dispatches = 0;
      if (ps5_context_last_compute_status(pipe, &dispatches) || dispatches != 61 + phase * 13)
         goto cleanup;
      for (unsigned i = 0; i < 12; ++i) {
         const unsigned wrap = i / 4;
         void *state = wrap ? wrap_samplers[wrap - 1][i & 1] : i & 1 ? linear_sampler : sampler;
         const unsigned unit = i % 4 >= 2 ? 15 : 0;
         pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, unit, 1, &state);
         pipe->bind_compute_state(pipe, filtered_cs[wrap != 0][unit != 0]);
         memset(sample_words, 0xcd, sample_bytes);
         pipe->launch_grid(pipe, &grid);
         pipe->memory_barrier(pipe, PIPE_BARRIER_MAPPED_BUFFER | PIPE_BARRIER_SHADER_BUFFER);
         int rc = ps5_context_last_compute_status(pipe, &dispatches);
         unsigned correct = count_sampled(sample_words, sign, 2 + wrap * 2 + (i & 1), 0);
         printf("[ps5-compute-filtered] phase=%u case=%u rc=%d dispatches=%u words=%u/80 first=%08x next=%08x\n",
            phase, i, rc, dispatches, correct, sample_words[8], sample_words[12]);
         fflush(stdout);
         if (rc || dispatches != 62 + phase * 13 + i || correct != 80) goto cleanup;
      }
      unsigned image_ok = count_image(image_data[0], sign, 0);
      printf("[ps5-compute-filtered] phase=%u image=%u/%u\n", phase, image_ok, IMAGE_WORDS);
      if (image_ok != IMAGE_WORDS) goto cleanup;
   }
   if (run_mips(pipe, sample_words, sample_bytes, 1, 0) || run_mips(pipe, sample_words, sample_bytes, 3, 0)) goto cleanup;
   for (unsigned kind = 0; kind < 3; ++kind)
      if (run_mips(pipe, sample_words, sample_bytes, 8, kind)) goto cleanup;
   if (run_all_slots(pipe, sample_words, sample_bytes)) goto cleanup;
   if (run_dimensional(pipe, sample_words, sample_bytes)) goto cleanup;
   if (run_compute_uniforms(pipe, sample_words, sample_bytes)) goto cleanup;
   if (run_fragment_storage(pipe, sample_output, sample_words, sample_bytes, target)) goto cleanup;
   for (unsigned kind = 0; kind < 3; ++kind)
      if (run_fragment_images(pipe, sample_output, sample_words, sample_bytes, kind, false, sampler, false)) goto cleanup;
   for (unsigned kind = 0; kind < 3; ++kind)
      if (run_fragment_images(pipe, sample_output, sample_words, sample_bytes, kind, true, sampler, false)) goto cleanup;
   for (unsigned kind = 3; kind < ARRAY_SIZE(image_formats); ++kind)
      if (run_fragment_images(pipe, sample_output, sample_words, sample_bytes, kind, false, sampler, false) ||
          run_fragment_images(pipe, sample_output, sample_words, sample_bytes, kind, false, sampler, true)) goto cleanup;
   if (run_parsed_glsl(pipe, sample_output, sample_words, sample_bytes, sampler)) goto cleanup;
   status = 0;
cleanup:
   if (pipe) {
      pipe->bind_compute_state(pipe, NULL);
      pipe->bind_vs_state(pipe, NULL);
      pipe->bind_fs_state(pipe, NULL);
      pipe->bind_blend_state(pipe, NULL);
      pipe->bind_rasterizer_state(pipe, NULL);
      pipe->bind_depth_stencil_alpha_state(pipe, NULL);
      void *none = NULL;
      pipe->bind_sampler_states(pipe, MESA_SHADER_FRAGMENT, 0, 1, &none);
      pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 0, 1, &none);
      pipe->bind_sampler_states(pipe, MESA_SHADER_COMPUTE, 15, 1, &none);
      pipe->set_sampler_views(pipe, MESA_SHADER_FRAGMENT, 0, 0, 1, NULL);
      pipe->set_sampler_views(pipe, MESA_SHADER_COMPUTE, 0, 0, 16, NULL);
      for (unsigned kind = 0; kind < 3; ++kind) {
         pipe_sampler_view_reference(&views[kind], NULL);
         if (writers[kind]) pipe->delete_compute_state(pipe, writers[kind]);
         if (fragments[kind]) pipe->delete_fs_state(pipe, fragments[kind]);
         for (unsigned i = 0; i < 4; ++i)
            if (sample_cs[kind][i]) pipe->delete_compute_state(pipe, sample_cs[kind][i]);
      }
      if (vs) pipe->delete_vs_state(pipe, vs);
      if (sampler) pipe->delete_sampler_state(pipe, sampler);
      if (linear_sampler) pipe->delete_sampler_state(pipe, linear_sampler);
      for (unsigned i = 0; i < 2; ++i) for (unsigned j = 0; j < 2; ++j) {
         if (filtered_cs[i][j]) pipe->delete_compute_state(pipe, filtered_cs[i][j]);
         if (wrap_samplers[i][j]) pipe->delete_sampler_state(pipe, wrap_samplers[i][j]);
      }
      if (blend) pipe->delete_blend_state(pipe, blend);
      if (rasterizer) pipe->delete_rasterizer_state(pipe, rasterizer);
      if (depth) pipe->delete_depth_stencil_alpha_state(pipe, depth);
      pipe->destroy(pipe);
   }
   for (unsigned kind = 0; kind < 3; ++kind)
      pipe_resource_reference(&images[kind], NULL);
   pipe_resource_reference(&target, NULL);
   pipe_resource_reference(&sample_output, NULL);
   pipe_resource_reference(&render_pool, NULL);
   if (screen) screen->destroy(screen);
   psbc_shutdown();
   printf("[ps5-compute-render] result=%d\n", status);
   return status;
}
