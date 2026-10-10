#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deleting any linked stage must invalidate the cached tessellation pipeline."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "src/gallium/ps5/ps5_screen.c").read_text()
start = source.index("static void\nps5_delete_shader_state(")
function = source[start:source.index("\nint\nps5_shader_state_info", start)]
code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
struct pipe_context { int unused; };
struct ps5_shader_variant {
  struct ps5_shader_variant *next;
  void *package, *streamout_package;
  int streamout_output, output;
};
struct ps5_shader {
  unsigned stage;
  struct ps5_shader_variant *variants;
  void *nir;
};
struct ps5_context {
  struct pipe_context base;
  struct ps5_shader *vs, *tcs, *tes, *gs, *fs, *default_tcs;
  struct ps5_shader *geometry_vs, *geometry_gs;
  struct ps5_shader *tessellation_vs, *tessellation_tcs;
  struct ps5_shader *tessellation_tes, *tessellation_gs;
};
static unsigned releases;
static void ps5_release_geometry_pipeline(struct ps5_context *ctx) { (void)ctx; }
static void ps5_release_tessellation_pipeline(struct ps5_context *ctx) {
  ++releases;
  ctx->tessellation_vs = ctx->tessellation_tcs = NULL;
  ctx->tessellation_tes = ctx->tessellation_gs = NULL;
}
static void psbc_free_output(int *output) { (void)output; }
static void ralloc_free(void *ptr) { free(ptr); }
''' + function + r'''
int main(void) {
  for (unsigned stage = 0; stage < 5; ++stage) {
    struct ps5_context ctx = {0};
    struct ps5_shader *shader = calloc(1, sizeof(*shader));
    assert(shader);
    struct ps5_shader **cached[] = {
      &ctx.tessellation_vs, &ctx.tessellation_tcs,
      &ctx.tessellation_tes, &ctx.tessellation_gs
    };
    if (stage < 4) *cached[stage] = shader;
    if (stage == 1) ctx.default_tcs = shader;
    ctx.gs = shader;
    releases = 0;
    ps5_delete_shader_state(&ctx.base, shader);
    assert(!ctx.gs);
    assert(!ctx.default_tcs);
    assert(releases == (stage < 4));
    for (unsigned i = 0; i < 4; ++i) assert(!*cached[i]);
    ps5_delete_shader_state(&ctx.base, NULL);
    assert(releases == (stage < 4));
  }
}
'''
with tempfile.TemporaryDirectory() as tmp:
    executable = str(Path(tmp) / "shader-lifetime")
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-x", "c", "-o", executable, "-"],
                   input=code, text=True, check=True)
    subprocess.run([executable], check=True)
print("PASS: all four tessellation stages invalidate cache; unrelated/null deletion does not")
