#!/usr/bin/env python3
"""Guard the PS5 Vulkan texture sampler workaround against regressions."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
gfx=(root/'ps5/porpoise_original/src/ui_gfx.cpp').read_text()
shader=(root/'ps5/porpoise_original/shaders/ui.frag').read_text()
workflow=(root.parent.parent/'.github/workflows/build-ps5nesx.yml').read_text()
ps5=(root/'ps5/frontend/fe_ps5.cpp').read_text()
assert gfx.count('fill(v[n].p2, {g->u0, g->v0, g->u1, g->v1});')==2, 'ordinary and mapped SDF text UV'
assert 'fill(v[i].p2, {uv[0], uv[1], uv[2], uv[3]});' in gfx, 'cropped image UV'
assert 'fill(v[i].p2, {0.0f, 0.0f, 1.0f, 1.0f});' in gfx, 'full images UV'
assert 'fill(v[i].p2, {u0, flip_v ? v1 : v0, u1, flip_v ? v0 : v1});' in gfx, 'cover + reflection UV'
assert shader.count('texture(tex, mix(v_p2.xy, v_p2.zw, v_local))')==3, 'covers/fonts/images use stable varying'
assert 'texture(tex, v_uv)' not in shader
assert 'rebuild_shader.py' in workflow, 'native CI must compile updated shader SPIR-V'
assert 'NotoSansJP-Porpoise.ttf' in ps5, 'optional JP font embedded'
assert 'texture_uv=flat_quad_rect+v_local' in (root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
print('PASS: Porpoise PS5 UV interpolation, original glass, and embedded CJK fonts')
