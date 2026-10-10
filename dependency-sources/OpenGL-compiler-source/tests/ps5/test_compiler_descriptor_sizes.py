#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Both compiler entry points must use the same combined-sampler ABI."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "third_party/opengnm-psbc/libpsbc/psbc_compile.c").read_text()
start = source.index("static void psbc_setup_descriptor_sizes(")
helper = source[start:source.index("\n}", start) + 2]
assert source.count("psbc_setup_descriptor_sizes(&ci);") == 1
assert source.count("psbc_setup_descriptor_sizes(compiler_info);") == 1
fields = {
    "sampled_image_desc_size": 32, "combined_image_sampler_desc_size": 48,
    "combined_image_sampler_offset": 32, "sampler_descriptor_size": 16,
    "sampler_descriptor_alignment": 16, "image_descriptor_size": 32,
    "image_descriptor_alignment": 16, "buffer_descriptor_size": 16,
    "buffer_descriptor_alignment": 16,
}
code = "#include <assert.h>\n#include <string.h>\nstruct radv_compiler_info {\n"
code += "".join(f"unsigned {name};\n" for name in fields) + "};\n" + helper
code += "\nint main(void) { struct radv_compiler_info c; memset(&c, 0xa5, sizeof(c)); psbc_setup_descriptor_sizes(&c);\n"
code += "".join(f"assert(c.{name} == {value});\n" for name, value in fields.items())
code += "assert(c.combined_image_sampler_offset + c.sampler_descriptor_size == c.combined_image_sampler_desc_size); }\n"
with tempfile.TemporaryDirectory() as temporary:
    binary = str(Path(temporary) / "descriptor-sizes")
    subprocess.run(["clang-18", "-x", "c", "-std=c11", "-Wall", "-Werror", "-o", binary, "-"],
                   input=code, text=True, check=True)
    subprocess.run([binary], check=True)
print("PASS: ordinary and linked tessellation compiler share texture/sampler descriptor ABI")
