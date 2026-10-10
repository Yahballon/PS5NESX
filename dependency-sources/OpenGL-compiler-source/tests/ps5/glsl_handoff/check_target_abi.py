#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile-only host PSBC/native consumer NIR ABI gate; run under Linux/WSL.

No linking, execution, archive builds, or generated-header updates. This checks
the current headers/flags, not archive freshness or the entire serialized format.
Use the same PS5_PAYLOAD_SDK environment as build-native-test-app.sh.
"""
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PSBC = ROOT / "third_party/opengnm-psbc"
SECTION = ".psbc_glsl_abi"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45).stdout


def flags(cwd, makefile, temporary, native=False):
    # An explicit dependency-free target only prints expanded variables. Never
    # request the repository default target or use make -n (which can recurse).
    printer = temporary / ("native.mk" if native else "host.mk")
    printer.write_text(".PHONY: glsl-handoff-abi-flags\n"
                       "glsl-handoff-abi-flags:\n"
                       "\t$(info ABI_CC=$(CC))\n"
                       "\t$(info ABI_CFLAGS=$(CFLAGS))\n"
                       "\t$(info ABI_PSBC_CFLAGS=$(PSBC_CFLAGS))\n\t@:\n")
    args = ["make", "--no-print-directory", "-s", "-f", str(makefile),
            "-f", str(printer)]
    if native:
        args += ["PS5_PAYLOAD_SDK=" + os.environ.get("PS5_PAYLOAD_SDK", "/opt/ps5-payload-sdk")]
    output = run(args + ["glsl-handoff-abi-flags"], cwd)
    values = dict(line[4:].split("=", 1) for line in output.splitlines()
                  if line.startswith("ABI_"))
    return (shlex.split(values["CC"]) + shlex.split(values["CFLAGS"]) +
            (shlex.split(values["PSBC_CFLAGS"]) if native else []))


def source():
    # Keep the exporter probe's exact 22 entries, failing closed if its shape
    # changes. Nothing from abi.c is executed or linked.
    abi = (HERE / "abi.c").read_text()
    match = re.search(r"static const size_t values\[\]\s*=\s*\{(.*?)\};", abi, re.S)
    if not match or not re.search(r",\s*0\s*$", match[1]):
        raise RuntimeError("abi.c no longer has the audited 22-entry + sentinel form")
    entries = re.sub(r",\s*0\s*$", "", match[1])
    return r'''
#include <stddef.h>
#include <stdint.h>
#include "compiler/nir/nir.h"
_Static_assert(sizeof((size_t[]){ ORIGINAL_ENTRIES })/sizeof(size_t) == 22,
               "exporter ABI entries changed");
/* nir_serialize.c writes shader_info and nir_variable_data as raw bytes.
 * Pointer members stay NULL; no relocation or process address is exported.
 * The three info records cover defaults+UBO, UBO-only, and texture+SSBO.
 * Variable records exercise their uniform/UBO/SSBO/sampler metadata. Nonzero
 * location/offset/binding sentinels witness field placement, NOT fixture values
 * or a proposed binding contract. Separate flags avoid masking bit swaps.
 */
static const struct {
   size_t abi[26];
   uint32_t endian_bytes;
   struct shader_info info[3];
   nir_variable_data variables[6];
} probe __attribute__((used, section(".psbc_glsl_abi"), aligned(1))) = {
   .abi = { ORIGINAL_ENTRIES, sizeof(void *), __BYTE_ORDER__,
            sizeof(nir_variable_data), _Alignof(struct shader_info) },
   .endian_bytes = 0x01020304,
   .info = {
      {.stage=MESA_SHADER_COMPUTE, .num_ubos=2, .num_ssbos=1,
       .workgroup_size={1,1,1}, .first_ubo_is_default_ubo=true},
      {.stage=MESA_SHADER_COMPUTE, .num_ubos=1, .num_ssbos=1,
       .workgroup_size={1,1,1}, .writes_memory=true},
      {.stage=MESA_SHADER_COMPUTE, .num_textures=1, .num_ssbos=1,
       .workgroup_size={1,1,1}, .textures_used={1}, .samplers_used={1}},
   },
   .variables = {
      {.mode=nir_var_uniform, .read_only=1, .location=1, .driver_location=2},
      {.mode=nir_var_mem_ubo, .explicit_binding=1, .binding=3, .descriptor_set=4},
      {.mode=nir_var_mem_ssbo, .assigned=1, .offset=8, .alignment=16},
      {.mode=nir_var_uniform, .used=1, .binding=1},
      {.mode=nir_var_mem_ubo, .from_named_ifc_block=1},
      {.mode=nir_var_mem_ssbo, .explicit_offset=1},
   },
};
'''.replace("ORIGINAL_ENTRIES", entries)


def main():
    objcopy = shutil.which("llvm-objcopy-18") or shutil.which("objcopy")
    readelf = shutil.which("readelf") or shutil.which("llvm-readelf-18")
    if not objcopy or not readelf:
        raise RuntimeError("existing objcopy and readelf tools are required")
    with tempfile.TemporaryDirectory(prefix="glsl-target-abi-") as directory:
        temporary = Path(directory)
        cfile = temporary / "probe.c"
        cfile.write_text(source())
        blobs = []
        for name, cwd, config, native in (
            ("host", PSBC, ROOT / "toolchain/opengnm-psbc-host.mak", False),
            ("native", ROOT / "tests/ps5", Path("Makefile"), True),
        ):
            command = flags(cwd, config, temporary, native)
            obj, raw = temporary / (name + ".o"), temporary / (name + ".bin")
            command += ["-c", str(cfile), "-o", str(obj)]
            print(name + ": " + shlex.join(command), flush=True)
            run(command, cwd)
            # Initialized data must not depend on link-time relocation. Debug
            # sections may contain relocations, but our named section must not.
            relocations = run([readelf, "-rW", str(obj)], temporary)
            if ".rela" + SECTION in relocations or ".rel" + SECTION in relocations:
                raise RuntimeError(name + ": probe section contains relocations")
            run([objcopy, "--dump-section", SECTION + "=" + str(raw),
                 str(obj), str(temporary / (name + "-copy.o"))], temporary)
            data = raw.read_bytes()
            if not data:
                raise RuntimeError(name + ": empty probe section")
            blobs.append(data)
        if blobs[0] != blobs[1]:
            offset = next((i for i, (a, b) in enumerate(zip(*blobs)) if a != b),
                          min(map(len, blobs)))
            raise RuntimeError(f"ABI mismatch at byte {offset}; host/native lengths "
                               f"{len(blobs[0])}/{len(blobs[1])}")
        print(f"PASS host/native {SECTION}: {len(blobs[0])} identical bytes; "
              f"sha256={hashlib.sha256(blobs[0]).hexdigest()}; compile-only")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"FAIL: {shlex.join(error.cmd)}\n{error.stdout}{error.stderr}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"FAIL: {error}")
