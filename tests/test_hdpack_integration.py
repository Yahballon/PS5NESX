#!/usr/bin/env python3
"""Static PS5NESX Mesen-HD-pack plumbing/opt-in regression checks."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
app=json.loads((root/'app.json').read_text())
# Version is determined by app.json; HD-pack invariants must survive releases.
import re
assert re.fullmatch(r'\d+\.\d+\.\d+', app['version']), app['version']
assert app['releaseTag'] == f"ps5nesx-v{app['version']}"
assert app['hdPacks']['enabledByDefault'] is False
mk=(root/'nes/tools/core-sources.mk').read_text()
assert 'HAVE_HDPACK := 1' in mk
build=(root/'nes/tools/build_shelf.py').read_text()
assert "'-DHAVE_HDPACK'" in build
core=(root/'nes/src/core_session.cpp').read_text()
assert 'm_system_directory.c_str()' in core
assert 'm_directory.c_str()' in core
assert 'w > 2560 || h > 2400' in core
src=(root/'nes/src/shelf_runtime.cpp').read_text()
assert 'get("NES/HDPacks","false")' in src
assert 'core.SetOption("fceumm_hdpacks",' in src
assert 'root+"/HdPacks/"+stem+"/hires.txt"' in src
# Integer scaling was extracted into a shared viewport helper when NESYX
# added native 16:9 fullscreen; preserve the same HD-pack/integer behavior.
viewport=(root/'nes/src/game_viewport.h').read_text()
assert 'const float scale=fit>=1.0f?' in viewport
assert 'CalcGameViewport(w,h,' in src
settings=(root/'ps5/frontend/fe_options.cpp').read_text()
assert 'Toggle("NES/HDPacks", "HD texture packs", "false"' in settings
main=(root/'nes/src/main_shelf.cpp').read_text()
assert '"HdPacks"' in main
print('PASS PS5NESX experimental HD pack paths, build flags, opt-in and video bounds')
