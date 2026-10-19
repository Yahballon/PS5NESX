#!/usr/bin/env python3
"""Guard NESYX's original, asset-free Pixel Reactor loading animation."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'nes/src/loading.cpp').read_text()
platform=(root/'ps5/frontend/fe_ps5.cpp').read_text()
checks={
    "unique Pixel Reactor design": 'PIXEL REACTOR' in source,
    "animated shader backdrop": 'frame.bg.misc[3]=t;' in source,
    "native quads only": 'Fonts::AddRoundedRect' in source,
    "animated pixel starfield": 'flicker=Wave(t*' in source,
    "rotating outer orbit": 'float(i)/60.f+t*0.34f' in source,
    "counter-rotating inner orbit": 'float(i)/40.f-t*0.52f' in source,
    "pixel sparks": 'std::fmod(t*(' in source,
    "pixel N monogram": 'col==0||col==6||col==diagonal' in source,
    "moving scanlight": 'std::fmod(t*450.f*k' in source,
    "animated waveform": 'std::sin(float(i)*0.59f-t*5.7f)' in source,
    "real progress": all(s in source for s in ('progress.games','progress.entries','progress.sources_done','progress.sources_total','progress.directory')),
    "indeterminate when unknown": 'const bool known=progress.sources_total!=0;' in source,
    "finished animation": 'LIBRARY ONLINE' in source and 'const double ready_until=Now()+0.32;' in platform,
    "live PS5 animation frames": 'show_loading(progress,scanning_done)' in platform,
    "version from header": 'nes_build::kVersion' in source,
    "no network/video decode": all(k not in source for k in ('curl_easy','std::ifstream','CreateTexture(', 'DreamcastX','fopen('))
}
for name,okay in checks.items():
    assert okay,name
    print("PASS",name)
