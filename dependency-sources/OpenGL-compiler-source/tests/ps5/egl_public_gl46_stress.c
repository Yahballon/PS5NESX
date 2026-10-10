// PS5 OpenGL - OpenGL implementation for PlayStation 5.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>

int ps5_stress_buffer_main(void);
int ps5_stress_compute_api_main(void);
int ps5_stress_compute_render_main(void);
int ps5_stress_indirect_main(void);
int ps5_stress_spirv_main(void);
int ps5_stress_piglit_main(void);

#ifndef PS5_GL46_STRESS_CYCLES
#define PS5_GL46_STRESS_CYCLES 2
#endif

int
main(void)
{
   int (*const tests[])(void) = {
      ps5_stress_buffer_main,
      ps5_stress_compute_api_main,
      ps5_stress_compute_render_main,
      ps5_stress_indirect_main,
      ps5_stress_spirv_main,
      ps5_stress_piglit_main,
   };
   const char *const names[] = {
      "persistent-coherent-buffer",
      "compute-ssbo-image-atomic-indirect",
      "compute-graphics-synchronization",
      "graphics-indirect",
      "spirv-specialize-link-draw",
      "piglit-ordered-ssbo-atomic",
   };
   const unsigned count = sizeof(tests) / sizeof(tests[0]);

   for (unsigned cycle = 0; cycle < PS5_GL46_STRESS_CYCLES; ++cycle) {
      for (unsigned test = 0; test < count; ++test) {
         printf("[ps5-gl46-stress] cycle=%u test=%s begin\n", cycle, names[test]);
         if (tests[test]()) {
            printf("[ps5-gl46-stress] cycle=%u test=%s result=FAIL\n",
                   cycle, names[test]);
            return 1;
         }
         printf("[ps5-gl46-stress] cycle=%u test=%s result=PASS\n",
                cycle, names[test]);
      }
   }
   printf("[ps5-gl46-stress] completed=%u result=PASS\n",
          count * PS5_GL46_STRESS_CYCLES);
   return 0;
}
