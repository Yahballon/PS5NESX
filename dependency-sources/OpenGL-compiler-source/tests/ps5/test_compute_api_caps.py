#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private compute API caps and build isolation; host only, no archive builds."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests/ps5"
SOURCE = ROOT / "src/gallium/ps5/ps5_screen.c"


def run(command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, timeout=45, **kwargs)


def require_success(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def caps_source():
    source = SOURCE.read_text()
    assert "caps->max_label_length = 256;" in source
    assert ".compute_private_buffer = true, .compute_buffer_spills = true" in source
    assert ("if (PS5_ENABLE_GLSL_430_CANDIDATE)\n"
            "      vs_caps->max_shader_buffers = PS5_COMPUTE_STORAGE_SLOTS;" in source)
    assert ("if (PS5_ENABLE_GLSL_430_CANDIDATE)\n"
            "         tcs_caps->max_shader_buffers = tes_caps->max_shader_buffers =\n"
            "            PS5_COMPUTE_STORAGE_SLOTS;" in source)
    default = re.search(r"#ifndef PS5_ENABLE_COMPUTE_API_TEST\s*\n"
                        r"#define PS5_ENABLE_COMPUTE_API_TEST 0\s*\n#endif", source)
    assert default, "private compute macro must default to zero"
    begin = source.index("#if PS5_ENABLE_COMPUTE_API_TEST", source.index("fs_caps->integers = true;"))
    end = source.index("#endif", begin) + len("#endif")
    block = source[begin:end]
    assert block.count("#if") == 1, "review nested capability gates"
    fs_begin = source.rindex("   fs_caps->max_instructions =", 0, begin)
    baseline = source[fs_begin:begin]
    glsl_begin = source.index("   caps->glsl_feature_level =")
    glsl_end = source.index(";", source.index("caps->glsl_feature_level_compatibility", glsl_begin)) + 1
    constants = source + (ROOT / "src/platform/ps5_agc_package.h").read_text()
    defines = []
    for name in ("PS5_AGC_COMPUTE_MAX_IMAGES", "PS5_COMPUTE_CONSTANT_SLOTS", "PS5_COMPUTE_STORAGE_SLOTS",
                 "PS5_COMPUTE_IMAGE_SLOTS", "PS5_MAX_CONSTANT_BUFFERS",
                 "PS5_MAX_DEFAULT_CONSTANT_BUFFER_SIZE"):
        defines.append(re.search(r"^#define " + name + r" .+$", constants, re.M)[0])
    # Real pipe_screen, no mock layout. Only unwrap the production ps5_screen's
    # base member reference; all assignments inside the gate remain verbatim.
    block = block.replace("screen->base.", "screen->")
    return r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pipe/p_screen.h"
#include "pipe/p_state.h"
#define PS5_ENABLE_UBO_CANDIDATE 1
#define PS5_ENABLE_GLSL_330_CANDIDATE 1
#define PS5_ENABLE_GLSL_400_CANDIDATE 0
#define PS5_ENABLE_GLSL_410_CANDIDATE 0
#define PS5_ENABLE_GLSL_420_CANDIDATE 0
#define PS5_ENABLE_GLSL_430_CANDIDATE 0
#define PS5_ENABLE_GLSL_440_CANDIDATE 0
#define PS5_ENABLE_GLSL_450_CANDIDATE 0
#define PS5_ENABLE_GLSL_460_CANDIDATE 0
#define PS5_ENABLE_GEOMETRY_CANDIDATE 1
''' + default[0] + "\n" + "\n".join(defines) + r'''
static void baseline(struct pipe_screen *screen) {
   struct pipe_caps *caps = (struct pipe_caps *)&screen->caps;
   struct pipe_shader_caps *fs_caps = (struct pipe_shader_caps *)&screen->shader_caps[MESA_SHADER_FRAGMENT];
''' + baseline + source[glsl_begin:glsl_end] + r'''
}
static void apply(struct pipe_screen *screen) {
   struct pipe_caps *caps = (struct pipe_caps *)&screen->caps;
   struct pipe_shader_caps *fs_caps = (struct pipe_shader_caps *)&screen->shader_caps[MESA_SHADER_FRAGMENT];
   (void)caps; (void)fs_caps;
''' + block + r'''
}
int main(void) {
   struct pipe_screen actual = {0}, expected = {0};
   baseline(&actual); baseline(&expected);
   assert(!actual.caps.compute);
   assert(actual.shader_caps[MESA_SHADER_FRAGMENT].max_const_buffers == 15);
   apply(&actual);
#if PS5_ENABLE_COMPUTE_API_TEST
   struct pipe_caps *caps = (struct pipe_caps *)&expected.caps;
   struct pipe_shader_caps *fs = (struct pipe_shader_caps *)&expected.shader_caps[MESA_SHADER_FRAGMENT];
   struct pipe_shader_caps *cs = (struct pipe_shader_caps *)&expected.shader_caps[MESA_SHADER_COMPUTE];
   *cs = *fs;
   cs->max_const_buffers = 15;
   cs->max_shader_buffers = fs->max_shader_buffers = PS5_COMPUTE_STORAGE_SLOTS;
   cs->max_shader_images = fs->max_shader_images = PS5_COMPUTE_IMAGE_SLOTS;
   caps->compute = true;
   caps->image_store_formatted = true;
   caps->shader_buffer_offset_alignment = 16;
   caps->max_shader_buffer_size = 1u << 27;
   struct pipe_compute_caps *cc = (struct pipe_compute_caps *)&expected.compute_caps;
   *cc = (struct pipe_compute_caps){
      .max_threads_per_block=1024, .max_local_size=32768,
      .max_grid_size={65535,65535,65535}, .max_block_size={1024,1024,64},
   };
   assert(actual.shader_caps[MESA_SHADER_FRAGMENT].max_const_buffers == 15);
   assert(actual.compute_caps.max_variable_threads_per_block == 0);
#else
   const struct pipe_shader_caps disabled = {0};
   const struct pipe_compute_caps no_compute = {0};
   assert(!actual.caps.compute);
   assert(!memcmp(&actual.shader_caps[MESA_SHADER_COMPUTE], &disabled, sizeof(disabled)));
   assert(!memcmp(&actual.compute_caps, &no_compute, sizeof(no_compute)));
#endif
   assert(actual.caps.glsl_feature_level == 330);
   assert(actual.caps.glsl_feature_level_compatibility == 330);
   /* Whole-screen comparison also checks untouched FS compiler caps and other stages. */
   assert(!memcmp(&actual, &expected, sizeof(actual)));
   printf("PASS compute API caps enabled=%d: exact changes only, GLSL330 preserved\n",
          PS5_ENABLE_COMPUTE_API_TEST);
}
'''


def preflight(temporary, env):
    makefile = (TESTS / "Makefile").read_text()
    assert re.search(r"^egl_public_compute_api\.o:", makefile, re.M), (
        "Prerequisite pending: egl_public_compute_api.o rule must exist before preflight checks")
    script = ROOT / "tools/build-native-test-app.sh"
    # Even a regressed guard cannot reach builds: the template is deliberately
    # absent. Require the specific guard diagnostic, not 'unknown gate' or the
    # missing-template fallback.
    base = {**env, "PS5_NATIVE_APP_TEMPLATE": str(temporary / "absent-template")}
    cases = (
        ("egl_public_compute_render.o", {"PS5_COMPUTE_API_TEST": "1"},
         "restricted to egl_public_compute_api"),
        ("egl_public_compute_api.o", {"PS5_COMPUTE_API_TEST": "1", "PS5_OPENGL_PREFIX": str(temporary)},
         "Private compute API gate cannot use an SDK prefix"),
        ("egl_public_compute_api.o", {"PS5_COMPUTE_API_TEST": "2"}, "Invalid compute API test mode"),
    )
    for gate, settings, diagnostic in cases:
        result = run(["bash", str(script), gate], cwd=ROOT, env={**base, **settings})
        assert result.returncode == 2 and diagnostic in result.stderr, result.stdout + result.stderr
        assert "unknown public OpenGL test" not in result.stderr
    print("PASS three private-gate preflight rejections (before builds)")


def make_paths(temporary, env):
    printer = temporary / "print.mk"
    printer.write_text(".PHONY: compute-api-test-print\ncompute-api-test-print:\n"
                       "\t$(info ABI_BUILD=$(PS5_OPENGL_BUILD))\n"
                       "\t$(info ABI_RUNTIME=$(PS5_OPENGL_RUNTIME))\n"
                       "\t$(info ABI_FLAGS=$(PS5_OPENGL_RUNTIME_DEFINES))\n\t@:\n")
    # This target only prints variables; it needs no SDK/compiler definitions.
    sdk = temporary / "sdk"
    (sdk / "toolchain").mkdir(parents=True)
    (sdk / "toolchain/prospero.mk").write_text("")
    for mode, directory in (("0", "core33-native-runtime"), ("1", "compute-api-native-runtime")):
        output = require_success(run([
            "make", "--no-print-directory", "-s", "-f", "native-app.mk", "-f", str(printer),
            "PS5_PAYLOAD_SDK=" + str(sdk), "PS5_COMPUTE_API_TEST=" + mode,
            "compute-api-test-print"], cwd=TESTS, env=env))
        fields = dict(line[4:].split("=", 1) for line in output.splitlines() if line.startswith("ABI_"))
        expected = ROOT / "build" / directory
        assert fields["BUILD"] == str(expected), output
        assert fields["RUNTIME"] == str(expected / "libps5_opengl_core33.a"), output
        flags = fields["FLAGS"].split()
        assert "-DPS5_NATIVE_TITLE_RUNTIME=1" in flags
        private = [flag for flag in flags if "PS5_ENABLE_COMPUTE_API_TEST" in flag]
        assert private == (["-DPS5_ENABLE_COMPUTE_API_TEST=1"] if mode == "1" else []), output
    print("PASS distinct default/private runtime paths and flags (make print only)")


def main():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PS5_") and k not in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES")}
    with tempfile.TemporaryDirectory(prefix="compute-api-caps-") as directory:
        temporary = Path(directory)
        code = caps_source()
        for enabled in (0, 1):
            executable = temporary / ("caps-" + str(enabled))
            command = ["cc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
                       "-D_GNU_SOURCE", "-DHAVE_ENDIAN_H=1", "-DHAVE_FUNC_ATTRIBUTE_PACKED=1",
                       "-I" + str(ROOT / "build/mesa-ps5-probe/src"),
                       "-I" + str(ROOT / "third_party/mesa-26.2.0/include"),
                       "-I" + str(ROOT / "third_party/mesa-26.2.0/src"),
                       "-I" + str(ROOT / "third_party/mesa-26.2.0/src/gallium/include")]
            if enabled:
                command += ["-DPS5_ENABLE_COMPUTE_API_TEST=1"]
            require_success(run(command + ["-x", "c", "-o", str(executable), "-"],
                                input=code, env=env))
            print(require_success(run([str(executable)], env=env)), end="")
        preflight(temporary, env)
        make_paths(temporary, env)


if __name__ == "__main__":
    main()
