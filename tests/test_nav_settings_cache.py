#!/usr/bin/env python3
"""Structural regression: Porpoise header, settings overlay and persistent cover cache."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ps5=(root/'ps5/frontend/fe_ps5.cpp').read_text()
app=(root/'ps5/frontend/fe_app.cpp').read_text()
header=(root/'ps5/frontend/fe_app.h').read_text()
shelf=(root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
covers=(root/'ps5/frontend/fe_covers.cpp').read_text()
urls=(root/'nes/src/cover_urls.h').read_text()
checks={
    "settings sheet reported": 'bool SheetVisible() const' in header,
    "Porpoise stays active with settings": 'renderer.ExactEnabled(exact_ready && !nes_game.Active());' in ps5,
    "sheet as only legacy overlay": 'ui.clear();' in app and 'BuildSheet(ui, W, H, k' in app,
    "Square still opens settings": 'OpenSheet(m_games.empty())' in app,
    "Porpoise header tabs removed": 'const std::string tabs[3]' not in shelf and 'Glyph::L1' not in shelf,
    "navigation wrap": 'WrappedGameIndex(m_selected, dir, n)' in app,
    "snap on wrap": 'm_scroll_vel = 0.0f;' in app,
    "automatic download for local ROMs": 'cc.download_usb_only = false;' in ps5,
    "bounded near-selection download worker": 'RunWindow()' in covers,
    "download saves image atomically": 'saved = WriteFileAtomic(cached, bytes);' in covers,
    "cache loaded before remote download": 'm_cache_dir + "/" + g.serial + ".jpg"' in covers,
    "collection prefix normalized": 's.erase(0,4);' in urls,
    "libretro fallback retained": '/Named_Boxarts/' in urls,
}
for label,valid in checks.items():
    assert valid,label
    print("PASS",label)
