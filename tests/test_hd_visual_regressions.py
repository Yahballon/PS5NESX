#!/usr/bin/env python3
"""Structural guards for HD-pack left-edge and scanline regressions."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ppu=(root/'nes/third_party/fceumm/src/hdpack/hdpack_ppu.c').read_text()
render=(root/'nes/third_party/fceumm/src/hdpack/hdpack_render.c').read_text()
callback=(root/'nes/src/core_session.cpp').read_text()
checks = {
  'left 8 mask': 'if (bg_left_clip && x < 8)' in ppu and 'px->tile.bg_color = backdrop;' in ppu,
  'cache validates CHR+palette key': 'hd_tile_key_equal(&hd_cached_key, &key)' in render,
  'cache key saved before lookup': render.index('memcpy(&key, tile, sizeof(key));',render.index('static hd_pack_tile *hd_get_cached_matching_tile')) < render.index('result = hd_get_matching_tile(x, y, tile, &disable_cache);',render.index('static hd_pack_tile *hd_get_cached_matching_tile')),
  'HD compose buffer clear': 'memset(hd_frame_buf, 0, (size_t)hd_frame_pixels * sizeof(*hd_frame_buf));' in render,
  'HD dimensions and pitch logged': '[HDPACK] video_frame=%ux%u pitch=%zu' in callback,
  'HD compositor instrumentation': 'tile_key_guard=active' in render,
}
for label,ok in checks.items():
    assert ok,label
    print('PASS',label)
