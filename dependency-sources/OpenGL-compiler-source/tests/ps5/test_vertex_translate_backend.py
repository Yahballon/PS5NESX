#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep PS5 CPU vertex conversion on the non-JIT path; retain desktop dispatch."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'third_party/mesa-26.2.0/src/gallium/auxiliary/translate/translate.c').read_text()
start = source.index('struct translate *translate_create(')
function = source[start:source.index('\n}\n', start) + 3]
code = r'''
#include <assert.h>
#include <stddef.h>
#define DETECT_ARCH_X86 0
#define DETECT_ARCH_X86_64 1
struct translate_key { int unused; };
struct translate { int unused; };
static struct translate generic, sse;
static int generic_calls, sse_calls;
struct translate *translate_generic_create(const struct translate_key *key)
{ (void)key; ++generic_calls; return &generic; }
struct translate *translate_sse2_create(const struct translate_key *key)
{ (void)key; ++sse_calls; return &sse; }
''' + function + r'''
int main(void) {
   struct translate *t=translate_create(NULL);
#ifdef __PROSPERO__
   assert(t==&generic && generic_calls==1 && sse_calls==0);
#else
   assert(t==&sse && sse_calls==1 && generic_calls==0);
#endif
}
'''
with tempfile.TemporaryDirectory() as directory:
    for flags in ([], ['-D__PROSPERO__']):
        exe = str(Path(directory) / 'check')
        subprocess.run(['clang-18', '-x', 'c', '-std=c11', '-Wall', '-Werror',
                        *flags, '-o', exe, '-'], input=code, text=True, check=True)
        subprocess.run([exe], check=True)
print('PASS: PS5 generic vertex conversion and unchanged desktop SSE selection')
