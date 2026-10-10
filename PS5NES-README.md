(AI-assisted) See README.md, INSTALL.md and BUILDING.md for the current PS5NES release.

## v1.0.0.9 by YAHBALLON (AI-assisted)

Internal ROM discovery no longer requires successful path metadata for every file. Known directory-entry types and opened descriptors are used; header probing and bounded stream reads support mounts that also deny descriptor metadata. The library cache can be read without path metadata. Added internal aliases `/data/homebrew/PS5NES/games/`, `/data/homebrew/PS5NES/roms/` and `/data/homebrew/PPSA99204/roms/`. ROM source paths are displayed beneath the selected game title. Failed directory access and scan counts are reported in boot.log. USB and cached NFS regressions passed; internal detection under simulated metadata denial and the actual Vulkan path display were verified. Console retest remains required.
