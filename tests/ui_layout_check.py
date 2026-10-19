#!/usr/bin/env python3
"""Assert title placement, QR removal and the in-app version at each build."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]
version = json.loads((root/'app.json').read_text())['version']
source = (root/'ps5/frontend/fe_app.cpp').read_text()
header = (root/'ps5/frontend/fe_app.h').read_text()
build_header = (root/'nes/src/ps5nes_build_version.h').read_text()
entry = (root/'nes/src/main_shelf.cpp').read_text()
assert 'const float title_y = H * 0.795f;' in source
assert 'title_y, px, white, 0.55f, Fonts::Center' in source
assert not any(marker in source for marker in ('m_qr', 'qrcodegen', 'HintQrCode'))
assert 'm_qr' not in header
assert f'kBuildTag[] = "v{version} by YAHBALLON"' in build_header
assert 'ps5nes_build_version.h' in entry
exact = (root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
assert '"NESYX"' in exact
assert 'nes_build::kVersion' in exact
assert '"Nintendo Entertainment System"' not in exact
assert 'kReportHeader[] = "NESYX v'+version+' by YAHBALLON"' in build_header
print("PASS: QR-free NESYX v"+version+" shelf; branded header and title without subtitle")
