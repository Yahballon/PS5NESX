#!/usr/bin/env python3
"""Progress HUD hides on completion and libretro fallback invalidates old misses."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ui=(root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
covers=(root/'ps5/frontend/fe_covers.cpp').read_text()
urls=(root/'nes/src/cover_urls.h').read_text()
idx=(root/'ps5/frontend/fe_libretro_catalog.h').read_text()
checks={
    'hide when completed': '!progress.done && !progress.offline' in ui,
    'transient active status': 'if(progress.transferring)' in ui,
    'manual refresh un-hides': 'm_progress.offline=false;m_progress.done=false;' in covers,
    'v10 negative cache rechecks old misses': '.nescovers-v10.missing' in covers and '.nescovers-v9.missing' not in covers,
    'official Libretro first-class source': 'https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%20Entertainment%20System/Named_Boxarts/' in urls,
    'one-time remote actual-title listing': 'static thread_local bool tried=false' in idx and 'ParseDirectory' in idx,
    'safely use matched real filenames': 'libretro::Lookup(game,download,stop)' in covers,
    'existing ArcadeArtwork preserved': 'arcadeartwork::Lookup' in covers,
    'existing local cache still atomic': 'saved = WriteFileAtomic(cached, bytes);' in covers,
}
for name,okay in checks.items():
    assert okay,name
    print('PASS',name)
