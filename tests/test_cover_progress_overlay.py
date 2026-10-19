#!/usr/bin/env python3
"""Porpoise layering, active downloads and non-spammy optional web source."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
app=(root/'ps5/frontend/fe_app.cpp').read_text()
renderer=(root/'ps5/frontend/fe_renderer.cpp').read_text()
frontend=(root/'ps5/frontend/fe_ps5.cpp').read_text()
covers=(root/'ps5/frontend/fe_covers.cpp').read_text()
header=(root/'ps5/frontend/fe_covers.h').read_text()
porpoise=(root/'ps5/frontend/fe_exact_porpoise.cpp').read_text()
api=(root/'ps5/frontend/fe_arcadeartwork.h').read_text()
assert 'ui.clear();' in app and 'BuildSheet(ui, W, H, k' in app
assert 'f.boxes.clear()' in app and 'f.reflections.clear()' in app
assert renderer.index('if (m_exact_enabled && m_exact_draw) m_exact_draw(cmd);') < renderer.index('if (!f.ui.empty() && m_atlas_set)')
assert 'renderer.ExactEnabled(exact_ready && !nes_game.Active());' in frontend
assert 'CoverProgress CoverService::Progress() const' in covers
assert 'CoverProgress m_progress;' in header
assert 'pending[background]=false;' in covers
assert 'CoverService::MissingCovers' in covers
assert 'DownloadCover(background,image)' in covers
assert 'Fetching: ' in porpoise and '!progress.done && !progress.offline' in porpoise
assert 'Cover search finished' not in porpoise
assert 'm_cover_progress' in porpoise
assert 'arcadeartwork::Lookup' in covers
assert 'cat_id=547' in api
assert 'thread_local bool loaded' in api
assert 'IsGalleryImage' in api
assert '.nescovers-v10.missing' in covers
assert 'libretro::Lookup' in covers
assert 'https://thumbnails.libretro.com/' in (root/'nes/src/cover_urls.h').read_text()
print('PASS: settings over Porpoise; progress, background caching and bounded ArcadeArtwork fallback')
