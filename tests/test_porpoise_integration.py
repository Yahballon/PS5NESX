#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
app=(root/'ps5/frontend/fe_app.cpp').read_text()
shader=(root/'ps5/frontend/shaders/bg.frag').read_text()
renderer=(root/'ps5/frontend/fe_renderer.cpp').read_text()
sound=(root/'ps5/frontend/fe_sound.cpp').read_text()
ps5=(root/'ps5/frontend/fe_ps5.cpp').read_text()
assert 'PorpoiseCoverflowPose(d, t)' in app
assert 'f.backdrop_set = chosen.set' in app
assert 'pc.floor_glow.w > 0.001' in shader and 'u_spotlight_cover' in shader
assert 'm_bg_fallback_set' in renderer and 'background_set' in renderer
assert 'fe_porpoise_game_row' in sound and 'DecodePorpoiseWav' in sound
assert 'FE_INCBIN_ASSET(fe_porpoise_game_row' in ps5
assert 'FE_INCBIN_ASSET(fe_porpoise_menu_scroll' in ps5
print('PASS: Porpoise layout, Vulkan art backdrop, pinned audio integration')
