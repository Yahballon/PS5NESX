#!/usr/bin/env python3
"""Original high-resolution NO COVER artwork is embedded without letterboxing."""
from pathlib import Path
import struct
root = Path(__file__).resolve().parents[1]
image = root / 'ps5/frontend/assets/no-cover.png'
payload = image.read_bytes()
assert payload[:8] == b'\x89PNG\r\n\x1a\n', "Embedded artwork must be a real PNG"
width, height = struct.unpack(">II", payload[16:24])
assert (width, height) == (1024, 1536), (width, height)
assert len(payload) > 1_000_000, "Source image was downscaled or substituted"
assert not (root / 'ps5/frontend/assets/no-cover.jpg').exists(), "Remove low-res fallback"
ps5 = (root / 'ps5/frontend/fe_ps5.cpp').read_text()
exact = (root / 'ps5/frontend/fe_exact_porpoise.cpp').read_text()
covers = (root / 'ps5/frontend/fe_covers.cpp').read_text()
assert 'FE_INCBIN_ASSET(fe_nocover_png, "no-cover.png")' in ps5
assert 'CoverService::Decode(bytes, 1536, placeholder)' in exact
assert 'if (!cover) cover = m_fallback;' in exact
assert '"Nintendo Entertainment System"' not in exact, "Secondary label still appears"
assert 'CoverService::Decode(png, 768, result)' in covers
print("PASS: original full-resolution 1024x1536 fallback, cropped coverflow, clean title")
