#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check ring capacity, reset ordering, ordinary draws and command bounds."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "src/platform/ps5_agc_native_runtime.c").read_text()
start = source.index("static uint32_t *set_linkage_uc_state(")
function = source[start:source.index("\n}\n", start) + 3]
ring_defines = "\n".join(line for line in source.splitlines()
                         if line.startswith("#define TESS_"))
code = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
typedef struct { uint16_t offset, padding; uint32_t value; } agc_register_t;
typedef struct { uint32_t *bottom, *top, *up, *down; } agc_command_buffer_t;
typedef struct { uint32_t *(*set_uc)(void *, const void *, uint32_t); } agc_api_t;
static int runtime_ngg_ge_pc_alloc_valid, runtime_hs_package;
static uint32_t runtime_ngg_ge_pc_alloc;
#define WORK_BYTES 0x10000u
''' + ring_defines + r'''
static unsigned calls;
static uint32_t *set_uc(void *ptr, const void *regs, uint32_t count) {
    agc_command_buffer_t *c = ptr;
    (void)regs;
    ++calls;
    assert(count == (runtime_hs_package ? 7u : 3u));
    assert(c->up - c->bottom == (runtime_hs_package ? 4 : 0));
    if (runtime_hs_package) {
        assert(c->bottom[0] == 0xc0004600 && c->bottom[1] == 0x40f);
        assert(c->bottom[2] == 0xc0004600 && c->bottom[3] == 0x24);
    }
    return c->up;
}
''' + function + r'''
int main(void) {
    static uint8_t memory[WORK_BYTES + TESS_OFFCHIP_BYTES + TESS_FACTOR_BYTES];
    /* The native SPIR-V receipt used slot 166 despite 160 requested slots.
     * The full architectural slot range must precede the factor/code region. */
    assert(167u * 32768u <= TESS_OFFCHIP_BYTES);
    assert(1024u * 32768u <= TESS_OFFCHIP_BYTES);
    assert(TESS_OFFCHIP_BYTES > TESS_OFFCHIP_WORKGROUPS * 32768u);
    uint32_t words[5];
    agc_api_t api = {set_uc};
    for (unsigned tess=0;tess<2;++tess) {
        runtime_hs_package=tess;
        for (unsigned capacity=0;capacity<=4;++capacity) {
            memset(words,0xa5,sizeof(words));
            calls=0;
            agc_command_buffer_t c={words,words+4,words,words+capacity};
            uint32_t *result=set_linkage_uc_state(&api,&c,memory);
            assert(!!result == (!tess || capacity>=4));
            assert(calls == (!tess || capacity>=4));
            assert(words[4] == 0xa5a5a5a5);
            if (tess && capacity<4) {
                assert(c.up==words);
                for(unsigned i=0;i<4;++i) assert(words[i]==0xa5a5a5a5);
            }
        }
    }
}
'''
with tempfile.TemporaryDirectory() as tmp:
    executable = str(Path(tmp) / "ring-reset")
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-x", "c", "-o", executable, "-"],
                   input=code, text=True, check=True)
    subprocess.run([executable], check=True)
print("PASS: driver slot 166/full slot range backed; reset ordering, command bounds and ordinary draws preserved")
