#!/usr/bin/env python3
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the complete console readback, never host execution."""
import json
from pathlib import Path
import sys
records = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines()]
values = [r for r in records if r.get('probe') == 'r59_frag_coord']
field = lambda name: [r['value'] for r in values if r.get('field') == name]
assert field('frame') == [0, 1] and field('mismatches') == [0, 0]
assert field('left') == ['0xff008040', '0xff0080bf'] and field('right') == ['0xff0080bf', '0xff008040']
assert sum(r.get('status') == 'PASS' for r in values) == 2
print('PASS: gl_FragCoord.z follows the ramp for depth ranges 0-1 and 1-0, and .w is 0.5')
