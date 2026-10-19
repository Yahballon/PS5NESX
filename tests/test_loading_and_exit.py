#!/usr/bin/env python3
"""Regression guards for native NESYX loading and menu-only Circle close dialog."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
meta=json.loads((root/'app.json').read_text())
loading=(root/'nes/src/loading.cpp').read_text()
app=(root/'ps5/frontend/fe_app.cpp').read_text()
hdr=(root/'ps5/frontend/fe_app.h').read_text()
platform=(root/'ps5/frontend/fe_ps5.cpp').read_text()
version=(root/'nes/src/ps5nes_build_version.h').read_text()
assert '"NESYX"' in loading and 'nes_build::kVersion' in loading
assert 'v7 modded by YAHBALLON' not in loading
assert 'Color(49,219,255)' in loading and 'Color(250,70,224)' in loading
assert 'progress.sources_done' in loading and 'progress.sources_total' in loading
assert 'progress.entries' in loading and 'progress.directory' in loading
assert 'm_exit_confirm' in hdr and 'm_exit_requested' in hdr
assert 'if (m_exit_confirm)' in app and 'if (in.circle && !m_prev.circle)' in app
assert 'else if (in.cross && !m_prev.cross)' in app
assert 'm_exit_requested = true;' in app
assert 'Close NESYX?' in app and 'Do you want to close NESYX?' in app
assert 'icon::Cross' in app and 'icon::Circle' in app
assert 'if (app.ExitRequested())' in platform and '::exit(0);' in platform
assert 'if (nes_game.Active())' in platform
assert f'kReportHeader[] = "NESYX v{meta["version"]} by YAHBALLON"' in version
print("PASS: NESYX neon loading, live progress, main-menu confirmation and clean exit")
