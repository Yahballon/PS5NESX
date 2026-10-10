# PS5NES v1.0.0.9 installation

(AI-assisted) This package contains the original PS5SX2-style NES app, custom controller bindings and YAHBALLON's supplied logo.

1. Copy the complete PPSA99204 folder to /data/homebrew/PPSA99204/.
2. Keep sce_module/libc.prx, lapy.elf, lapy-manifest.json and sce_sys/icon0.png.
3. Launch PS5NES through your compatible PS5 homebrew launcher.

Your game/save/settings folders are under /data/PS5NES/. Do not replace them when updating.

Add .nes, .unf, .unif or single-ROM ZIP files to:

~~~text
/data/PS5NES/games/
/data/homebrew/PS5NES/games/
/data/homebrew/PS5NES/roms/
/data/homebrew/PPSA99204/roms/
/mnt/usb0/homebrew/PS5NES/games/
~~~

For NFS: Square → R1 / All games → Settings → Network → NFS URL. Save an address such as nfs://192.168.1.10/NES and restart.

After changing library contents: use Rescan game library in the same Network group, then restart.

Default save state: L3 + R3 + D-pad Up. Default load state: L3 + R3 + D-pad Down. Default menu return: L1 + R1 + touchpad click.

View/change bindings in Square → R2 / Controls. Choose This game or All games. Changes save immediately and apply at the next game start.

Default NES controls: Cross = A, Circle = B, Options = Start, touchpad/Create = Select.

The restricted filesystem helper may need the local ELF loader on port 9021 if the app does not already have filesystem access.

ZIP limits: one ROM per ZIP, Stored/Deflate, no encryption or ZIP64, ROM ≤32 MiB and file ≤64 MiB.

Logs: /data/PS5NES/logs/boot.log. If /data is unavailable, check the fallback /download0/PS5NES/.

No ROMs, BIOS images or console keys are included.
