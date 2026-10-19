# NESYX v1.0.27 by YAHBALLON

## Pixel Reactor: all-new animated loading sequence

- Original 8-bit "N" reactor cartridge with a breathing cyber-neon aura, rotating cyan/magenta dual-orbit telemetry rings, orbiting circuit nodes and ascending pixel sparks.
- Starfield shimmer, animated top scan beam, glowing synth-grid and waveform readout; all rendered as PS5-native UI quads, no textures, videos, external assets or DreamcastX code.
- Real scanned game count, directory, file entries and folder progress. Unknown NFS totals display indeterminate activity instead of a fabricated percentage.
- 320 ms "LIBRARY ONLINE" completion animation before entering CoverFlow; all scanning remains on a background thread.
- 16:9 fullscreen, existing high-resolution NO COVER, Tiger mark, native audio and game navigation, and Circle exit confirmation remain unchanged.

# NESYX v1.0.26 by YAHBALLON

- Add **16:9 Fullscreen** as a display-picture choice, the default on new installations; fills the complete Vulkan output, with no gray sidebars. Existing per-game and global saved picture settings are respected: choose Fullscreen once in Settings to override old 4:3.
- Keep original **4:3** and **Integer pixels** for players who prefer correct aspect ratio or unscaled pixel edges.
- Test viewport sizing with 1920x1080 and 3840x2160 displays, including integer scaling and HD pack native frames.
- Retain the neon NESYX loading screen and Circle-to-close confirmation from v1.0.25, full-resolution cover fallback and YAHBALLON branding.

# NESYX v1.0.25 by YAHBALLON

- Brand new native cyan/purple glass loading screen replacing the original red "PS5NES v7" page.
- Dynamic NESYX header with YAHBALLON credit and build version, real game / entry / NFS folder progress.
- Circle in the main menu opens a confirmation popup ("Close NESYX?"). Cross = Yes (exit), Circle = No (cancel).
- Does not interrupt an active NES game; normal Vulkan/HTTP/audio/controller teardown runs before exit.
- Existing title ID PPSA99204, ROMs, saves, settings and high-resolution NO COVER asset remain intact.

# NESYX v1.0.24 by YAHBALLON

- Rebrand PS5NES/PS5NESX to NESYX in the PS5 menu, native CoverFlow, web settings and release display names.
- Show "by YAHBALLON | v1.0.24" under NESYX in the main window header (version generated from app.json).
- Keep game titles free of the redundant console-system subtitle and retain the exact 1024x1536 NO COVER PNG with a full-size shared texture.
- Preserve title ID PPSA99204, install/data locations, PS5NESX source slug and legacy release-tag prefix for existing TESTBUILDS installations.
- Real downloaded boxart still replaces the fallback, tiger header icon retained.

# PS5NESX v1.0.23 by YAHBALLON

- Embed the exact high-resolution 1024 x 1536 PNG supplied for NO COVER in the PS5 binary (full-size, no JPEG compression or black letterboxing).
- Remove the redundant "Nintendo Entertainment System" subtitle below the selected game.
- Keep a single shared 1536px GPU fallback for Porpoise coverflow; preserve bounded legacy fallback memory use and automatic real-artwork overrides.
- Preserve tiger logo, cached cover downloading and hidden Recently Browsed dock.

# PS5NESX v1.0.22 by YAHBALLON

- Use the supplied neon NO COVER artwork (embedded, JPEG) for games without a valid local, cached or downloadable cover (also in the original Porpoise CoverFlow).
- Replace the Dolphin mark in the header with a custom blue tiger emblem.
- Remove the Recently Browsed dock and its selection-history bookkeeping.
- Preserve real cover download, refresh, caching and the regular fallback view.

# PS5NES v1.0.0.9

(AI-assisted) Fixes silent omission of readable internal ROMs under metadata restrictions, adds internal ROM folder aliases, retains bounded ROM/cache reads and displays the selected ROM path below the title. Existing local/USB/NFS cache behavior remains covered by regression tests. Native metadata: 01.000.009; title PPSA99204.
