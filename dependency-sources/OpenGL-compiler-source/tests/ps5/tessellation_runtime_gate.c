// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

/* One-patch public compiler -> AGC runtime completion gate. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#include "compiler/glsl_types.h"
#include "compiler/nir/nir_builder.h"
#include "ps5_agc_package.h"
#include "ps5_scanout.h"
#include "psbc_compile.h"

extern int64_t sceKernelGetDirectMemorySize(void);
extern int32_t sceKernelAllocateDirectMemory(int64_t, int64_t, size_t, size_t,
                                             int, int64_t *);
extern int32_t sceKernelMapDirectMemory(void **, size_t, int, int, int64_t,
                                       size_t);
extern int32_t sceKernelReleaseDirectMemory(int64_t, size_t);

extern int ps5_agc_gate2_set_packages(const void *, size_t, const void *, size_t);
extern int ps5_agc_gate2_set_tessellation(const void *, size_t, uint32_t,
                                          uint32_t, uint32_t, unsigned int);
extern int ps5_agc_gate2_set_ngg_control(uint32_t, uint32_t);
extern int ps5_agc_gate2_set_framebuffer(void *, size_t);
extern int ps5_agc_gate2_set_draw_state(uint32_t, unsigned int);
extern int ps5_agc_gate2_run(void);

static nir_variable *
varying(nir_builder *b, nir_variable_mode mode, const struct glsl_type *type,
        unsigned location, bool patch)
{
   nir_variable *v = nir_variable_create(b->shader, mode, type, "value");
   v->data.location = location;
   v->data.patch = patch;
   return v;
}

static nir_deref_instr *
element(nir_builder *b, nir_variable *v, nir_def *index)
{
   return nir_build_deref_array(b, nir_build_deref_var(b, v), index);
}

static nir_shader *
build_stage(mesa_shader_stage stage)
{
   PsbcStage psbc_stage = stage == MESA_SHADER_VERTEX ? PSBC_STAGE_VERTEX :
                          stage == MESA_SHADER_TESS_CTRL ? PSBC_STAGE_TESS_CTRL :
                          PSBC_STAGE_TESS_EVAL;
   nir_builder b = nir_builder_init_simple_shader(
      stage, psbc_get_nir_options(psbc_stage), "ps5-tess-runtime-gate");

   if (stage == MESA_SHADER_VERTEX) {
      nir_def *id = nir_load_vertex_id_zero_base(&b);
      nir_def *one = nir_ieq_imm(&b, id, 1);
      nir_def *two = nir_ieq_imm(&b, id, 2);
      nir_def *position = nir_vec4(
         &b, nir_bcsel(&b, one, nir_imm_float(&b, 0.65f),
                       nir_imm_float(&b, -0.65f)),
         nir_bcsel(&b, two, nir_imm_float(&b, 0.65f),
                       nir_imm_float(&b, -0.65f)),
         nir_imm_float(&b, 0.5f), nir_imm_float(&b, 1.0f));
      nir_store_var(&b, varying(&b, nir_var_shader_out, glsl_vec4_type(),
                                VARYING_SLOT_POS, false), position, 0xf);
      return b.shader;
   }

   b.shader->info.tess._primitive_mode = TESS_PRIMITIVE_TRIANGLES;
   b.shader->info.tess.spacing = TESS_SPACING_EQUAL;
   b.shader->info.tess.ccw = true;
   nir_variable *input = varying(
      &b, nir_var_shader_in, glsl_array_type(glsl_vec4_type(), 3, 0),
      VARYING_SLOT_POS, false);
   if (stage == MESA_SHADER_TESS_CTRL) {
      b.shader->info.tess.tcs_vertices_out = 3;
      nir_def *id = nir_load_invocation_id(&b);
      nir_variable *output = varying(
         &b, nir_var_shader_out, glsl_array_type(glsl_vec4_type(), 3, 0),
         VARYING_SLOT_POS, false);
      nir_store_deref(&b, element(&b, output, id),
                      nir_load_deref(&b, element(&b, input, id)), 0xf);
      nir_push_if(&b, nir_ieq_imm(&b, id, 0));
      for (unsigned inner = 0; inner < 2; ++inner) {
         unsigned count = inner ? 2 : 4;
         nir_variable *level = varying(
            &b, nir_var_shader_out,
            glsl_array_type(glsl_float_type(), count, 0),
            inner ? VARYING_SLOT_TESS_LEVEL_INNER :
                    VARYING_SLOT_TESS_LEVEL_OUTER, true);
         for (unsigned i = 0; i < count; ++i)
            nir_store_deref(&b, element(&b, level, nir_imm_int(&b, i)),
                            nir_imm_float(&b, 2.0f), 1);
      }
      nir_pop_if(&b, NULL);
   } else {
      nir_def *coord = nir_load_tess_coord(&b);
      nir_def *position = nir_imm_vec4(&b, 0, 0, 0, 0);
      for (unsigned i = 0; i < 3; ++i)
         position = nir_fadd(
            &b, position,
            nir_fmul(&b, nir_load_deref(&b, element(&b, input,
                                                    nir_imm_int(&b, i))),
                     nir_channel(&b, coord, i)));
      nir_store_var(&b, varying(&b, nir_var_shader_out, glsl_vec4_type(),
                                VARYING_SLOT_POS, false), position, 0xf);
   }
   return b.shader;
}

static nir_shader *
build_fragment(void)
{
   nir_builder b = nir_builder_init_simple_shader(
      MESA_SHADER_FRAGMENT, psbc_get_nir_options(PSBC_STAGE_FRAGMENT),
      "ps5-tess-runtime-fs");
   nir_store_var(&b, varying(&b, nir_var_shader_out, glsl_vec4_type(),
                             FRAG_RESULT_DATA0, false),
                 nir_imm_vec4(&b, 0.1f, 0.8f, 0.3f, 1.0f), 0xf);
   return b.shader;
}

int
main(void)
{
   PsbcTessellationOutput tess = {0};
   PsbcShaderOutput fs = {0};
   PsbcTessellationCompileOptions tess_options = {3, 8192, 2};
   PsbcCompileOptions fs_options = {
      .target = PSBC_TARGET_PS5, .stage = PSBC_STAGE_FRAGMENT,
      .entrypoint = "main", .optimise = true,
   };
   nir_shader *stages[3] = {0};
   nir_shader *fragment = NULL;
   uint8_t *hs_package = NULL, *tes_package = NULL, *fs_package = NULL;
   size_t hs_size = 0, tes_size = 0, fs_size = 0;
   int64_t direct = -1;
   void *framebuffer = NULL;
   int result = 1;

   psbc_init();
   stages[0] = build_stage(MESA_SHADER_VERTEX);
   stages[1] = build_stage(MESA_SHADER_TESS_CTRL);
   stages[2] = build_stage(MESA_SHADER_TESS_EVAL);
   fragment = build_fragment();
   if (psbc_compile_nir_tessellation_pipeline(
          stages[0], stages[1], stages[2], NULL, &tess_options, &tess) !=
          PSBC_RESULT_OK ||
       psbc_compile_nir(fragment, &fs_options, &fs) != PSBC_RESULT_OK ||
       ps5_agc_package_build(&tess.hs, 0, &hs_package, &hs_size) ||
       ps5_agc_package_build(&tess.tes, 0, &tes_package, &tes_size) ||
       ps5_agc_package_build(&fs, 0, &fs_package, &fs_size) ||
       sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(),
                                     PS5_SCANOUT_BYTES,
                                     PS5_SCANOUT_ALIGNMENT, 12, &direct) ||
       sceKernelMapDirectMemory(&framebuffer, PS5_SCANOUT_BYTES, 0x33, 0,
                                direct, PS5_SCANOUT_ALIGNMENT))
      goto done;
   memset(framebuffer, 0, PS5_SCANOUT_BYTES);
   if (ps5_agc_gate2_set_packages(tes_package, tes_size,
                                  fs_package, fs_size) ||
       ps5_agc_gate2_set_tessellation(hs_package, hs_size,
                                      tess.runtime.hs_rsrc2,
                                      tess.runtime.ls_hs_config,
                                      tess.runtime.tf_param, 3) ||
       ps5_agc_gate2_set_ngg_control(1, UINT32_C(0x7fe)) ||
       ps5_agc_gate2_set_framebuffer(framebuffer, PS5_SCANOUT_BYTES) ||
       ps5_agc_gate2_set_draw_state(9, 3))
      goto done;
   result = ps5_agc_gate2_run();

done:
   printf("[ps5-tess-runtime] hs=%zu tes=%zu fs=%zu result=%d\n",
          hs_size, tes_size, fs_size, result);
   fflush(stdout);
   if (framebuffer)
      munmap(framebuffer, PS5_SCANOUT_BYTES);
   if (direct >= 0)
      sceKernelReleaseDirectMemory(direct, PS5_SCANOUT_BYTES);
   free(hs_package);
   free(tes_package);
   free(fs_package);
   for (unsigned i = 0; i < 3; ++i)
      ralloc_free(stages[i]);
   ralloc_free(fragment);
   psbc_free_tessellation_output(&tess);
   psbc_free_output(&fs);
   psbc_shutdown();
   return result;
}
