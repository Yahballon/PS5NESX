#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every unsupported narrow integer vertex input needs an integer fallback."""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'third_party/mesa-26.2.0/src/gallium/auxiliary/util/u_vbuf.c').read_text()
table = source.split('vbuf_format_fallbacks[] = {', 1)[1].split('};', 1)[0]
pairs = dict(re.findall(r'\{\s*(PIPE_FORMAT_\w+),\s*(PIPE_FORMAT_\w+)\s*\}', table))
for bits in (8, 16):
    for count in range(1, 5):
        for kind in ('SINT', 'UINT'):
            narrow = 'PIPE_FORMAT_' + ''.join(f'{c}{bits}' for c in 'RGBA'[:count]) + '_' + kind
            wide = 'PIPE_FORMAT_' + ''.join(f'{c}32' for c in 'RGBA'[:count]) + '_' + kind
            assert pairs.get(narrow) == wide, (narrow, pairs.get(narrow), wide)
print('PASS: all 16 narrow integer formats preserve signedness and component count')

# GL_DOUBLE feeding a float input is conversion, not the raw dvec/UINT path.
driver = (root / 'src/gallium/ps5/ps5_screen.c').read_text()
support = driver.split('ps5_is_format_supported(', 1)[1].split(
    'if (format == PIPE_FORMAT_Z32_FLOAT_S8X24_UINT', 1)[0]
for count in range(1, 5):
    wide = 'PIPE_FORMAT_' + ''.join(f'{c}64' for c in 'RGBA'[:count]) + '_FLOAT'
    converted = 'PIPE_FORMAT_' + ''.join(f'{c}32' for c in 'RGBA'[:count]) + '_FLOAT'
    assert wide not in support, wide
    assert pairs.get(wide) == converted, (wide, pairs.get(wide))
print('PASS: all four double-to-float formats use Mesa numeric conversion')
