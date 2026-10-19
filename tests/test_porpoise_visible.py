#!/usr/bin/env python3
"""Never silently regress to black cases when original Porpoise fails."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ps5=(root/'ps5/frontend/fe_ps5.cpp').read_text()
app=(root/'ps5/frontend/fe_app.cpp').read_text()
bridge=(root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
gfx=(root/'ps5/porpoise_original/src/ui_gfx.cpp').read_text()
workflow=(root.parent.parent/'.github/workflows/build-ps5nesx.yml').read_text()
checks={
    'embedded fonts': 'FE_INCBIN_ASSET(fe_pp_nunito_regular' in ps5,
    'writable font mount': 'original_ui.asset_dir=paths.top_dir+"/porpoise-ui"' in ps5,
    'prepare assets': 'PreparePorpoiseAssets(original_ui.asset_dir)' in ps5,
    'visible failure': 'PORPOISE UI INIT FAILED' in app,
    'original shader remains': 'sizeof(porpoise_ui_frag)' in gfx,
    'original grid room': 'g.background();' in bridge and 'Look look;' in bridge and 'm_theme=="oled"' in bridge,
    'NESYX header': '"NESYX"' in bridge and 'nes_build::kVersion' in bridge and 'by YAHBALLON' in bridge,
    'no system subtitle': '"Nintendo Entertainment System"' not in bridge,
    'compact header': '"Save States"' not in bridge and '"Library"' not in bridge and 'Glyph::L1' not in bridge and 'Glyph::R1' not in bridge,
    'original glass cases': 'glass_block(g,' in bridge,
    'recent dock removed': 'g.text(Font::SemiBold,22,dx+32' not in bridge and 'm_recent' not in bridge,
    'embedded no-cover texture': 'm_fallback = m_gfx.texture_rgba' in bridge,
    'user tiger brand': 'FE_INCBIN_ASSET(fe_pp_dolphin_mask, "tiger-logo.png")' in ps5,
    'embed assets stage': 'cp -R "$root/."' in workflow,
}
for name,ok in checks.items():
    assert ok,name
    print('PASS',name)
