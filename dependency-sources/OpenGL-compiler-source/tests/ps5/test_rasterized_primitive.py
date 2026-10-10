# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Final-stage topology, not input patches, controls point clipping."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "src/gallium/ps5/ps5_screen.c").read_text()
start = source.index("static uint32_t\nps5_fragment_primitive_type(")
function = source[start:source.index("\n}", start) + 3]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
enum { MESA_PRIM_POINTS, MESA_PRIM_LINES, MESA_PRIM_LINE_STRIP,
       MESA_PRIM_TRIANGLES, MESA_PRIM_TRIANGLE_STRIP };
enum { TESS_PRIMITIVE_TRIANGLES, TESS_PRIMITIVE_QUADS, TESS_PRIMITIVE_ISOLINES };
struct nir_shader { struct {
  struct { unsigned output_primitive; } gs;
  struct { unsigned _primitive_mode; bool point_mode; } tess;
} info; };
struct ps5_shader { struct nir_shader *nir; };
struct ps5_context { struct ps5_shader *tcs, *tes, *gs; };
''' + function + r'''
int main(void) {
  struct nir_shader tes = {0}, gs = {0};
  struct ps5_shader t = {&tes}, g = {&gs};
  struct ps5_context ctx = {0};
  for (unsigned draw = 1; draw <= 6; ++draw)
    assert(ps5_fragment_primitive_type(&ctx, draw) == draw);
  ctx.tcs = ctx.tes = &t;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 4);
  tes.info.tess._primitive_mode = TESS_PRIMITIVE_QUADS;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 4);
  tes.info.tess._primitive_mode = TESS_PRIMITIVE_ISOLINES;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 2);
  tes.info.tess.point_mode = true;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 1);
  ctx.gs = &g;
  gs.info.gs.output_primitive = MESA_PRIM_TRIANGLE_STRIP;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 6);
  gs.info.gs.output_primitive = MESA_PRIM_POINTS;
  assert(ps5_fragment_primitive_type(&ctx, 4) == 1);
  gs.info.gs.output_primitive = MESA_PRIM_LINE_STRIP;
  assert(ps5_fragment_primitive_type(&ctx, 9) == 3);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    executable = str(Path(tmp) / "rasterized-primitive")
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-x", "c", "-o", executable, "-"],
                   input=code, text=True, check=True)
    subprocess.run([executable], check=True)
assert "if (fragment_primitive_type == 1)\n         packed_cull |= packed_clip;" in source
print("PASS: VS/TES/GS output topology and final-point clip-mask selection")
