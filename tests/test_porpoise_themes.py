#!/usr/bin/env python3
"""Five original Porpoise theme looks, persistent global settings, live preview."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
options=(root/'ps5/frontend/fe_options.cpp').read_text()
header=(root/'ps5/frontend/fe_options.h').read_text()
app=(root/'ps5/frontend/fe_app.cpp').read_text()
exact=(root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
look=(root/'ps5/porpoise_original/src/ui_theme.cpp').read_text()
expected={"porpoise":0,"oled":1,"cube":3,"aurora":7,"synthwave":10}
assert 'Seg("PS5NESX/Theme", "Theme"' in options
for name,background in expected.items():
    assert f'{{"{name}"' in options
    if name!="porpoise":
        assert f'm_theme=="{name}"' in exact
        assert f'look.background={background}' in exact
    assert f"make_{'midnight' if name=='oled' else name}" in look, name
assert 'std::string ThemeValue() const' in header
assert 'const std::string& destination=theme_only ? m_paths.gs_ini : m_path;' in options
assert 'const IniState& global = m_global ? m_own : m_globals;' in options
assert 'm_sheet.Open(m_cfg.options, nullptr);' in app
assert 'm_cfg.exact->SetTheme(m_sheet.ThemeValue());' in app
assert 'm_theme=next;' in exact
assert 'g.set_look(look);' in exact
print('PASS: five theme choices, original shader looks, persisted global values and hot switching')
