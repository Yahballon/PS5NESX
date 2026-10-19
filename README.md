<p align="center">
  <img src="ps5/frontend/assets/tiger-logo.png" alt="NESYX tiger emblem" width="100">
</p>

<h1 align="center">NESYX</h1>
<p align="center"><strong>Native NES emulation for a jailbroken PlayStation 5</strong><br>
Retro games. Neon covers. Modern PS5 homebrew.<br>
<sub>v1.0.28 · by YAHBALLON · Title ID PPSA99204</sub></p>

<p align="center">
  <a href="https://github.com/Yahballon/PS5NESX/actions/workflows/build-nesyx.yml"><img alt="Native build" src="https://github.com/Yahballon/PS5NESX/actions/workflows/build-nesyx.yml/badge.svg"></a>
  <a href="https://github.com/Yahballon/PS5NESX/releases"><img alt="Latest GitHub release" src="https://img.shields.io/github/v/release/Yahballon/PS5NESX?style=flat-square"></a>
  <a href="LICENSE"><img alt="License GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue?style=flat-square"></a>
</p>

> **NESYX** is an open-source homebrew emulator for compatible jailbroken PS5 consoles, built around **FCEUmm** and an original **3D neon CoverFlow** frontend. The GitHub repository retains the name `PS5NESX` to preserve existing links, while the app and its menus are branded **NESYX**.

## ✨ Highlights

| Experience | What you get |
| --- | --- |
| **3D CoverFlow library** | Neon glass game cases, reflections, smooth wraparound navigation, original tiger emblem |
| **Automatic box art** | Libretro NES box-art lookup, secondary cover sources, persistent caching and download progress |
| **HD fallback art** | Full-resolution 1024 × 1536 NO COVER design if no matching artwork is found |
| **Pixel Reactor boot** | Original animated neon loading sequence with a rotating 8-bit reactor, pixel particles and live library scanning stats |
| **3 picture modes** | **16:9 Fullscreen** (default), classic **4:3**, or **Integer pixels** |
| **Emulation and saves** | FCEUmm NES core, configurable controller bindings, battery saves and save/load states |
| **ROM sources** | Internal storage, USB and NFS shares; NES, UNIF and compatible single-game ZIP files |
| **Safe exit** | Press **○** in the library to open the exit confirmation; **× Yes**, **○ No** |
| **HD packs (experimental)** | Mesen-format `hires.txt` support where compatible; not all packs are verified |

## 🛡️ Native PS5 exit fix (v1.0.28)

Closing with **○**, then **×** now exits through `sceSystemServiceLoadExec("exit", nullptr)` after native graphics/audio/HTTP/controller teardown. This replaces libc `exit()` that could cause SIGSYS (signal 12); the CRT main-return path is protected too. All existing saves and ROM folders remain untouched.

## 🎮 Controller guide

| Action | Input |
| --- | --- |
| Browse games | D-pad / left stick |
| Play selected game | **×** |
| Settings | **□** |
| Exit confirmation (library) | **○** |
| Confirm exit / Cancel | **× Yes** / **○ No** |
| NES A / B | **×** / **○** in-game |
| NES Start / Select | Options / Touchpad click or Create |
| Save state | L3 + R3 + D-pad Up |
| Load state | L3 + R3 + D-pad Down |
| Return from game to library | L1 + R1 + Touchpad click |

The menu's Circle-to-close shortcut is active **only in the library**, not while a NES game is running. Individual button and shortcut mappings can be customized under Settings.

## 📦 Install / Update

1. Download the latest **`PPSA99204.zip`** from [Releases](https://github.com/Yahballon/PS5NESX/releases).
2. Extract the ZIP and transfer its complete `PPSA99204` directory to the supported homebrew install location, typically `/data/homebrew/PPSA99204/`.
3. Start **NESYX** with your compatible PS5 homebrew launcher.

The package must retain `eboot.bin`, `sce_sys/`, `sce_module/`, `lapy.elf` and the helper manifest. **Keep the existing `/data/PS5NES/` folder during updates**: this legacy data path is intentionally unchanged to protect saves, settings, artwork and games.

### Add your legally obtained games

| Source | Example |
| --- | --- |
| Internal | `/data/PS5NES/games/` |
| USB | `/mnt/usb0/homebrew/PS5NES/games/` (supported USB volumes also scanned) |
| NFS | `nfs://192.168.1.10/NES` (configure in **Settings → Network**) |
| Game saves / configuration | `/data/PS5NES/` |

NESYX scans supported directories and caches thumbnails for faster subsequent launches. Use **Settings → Display → Picture → 16:9 Fullscreen** if an older installation retained a saved 4:3 preference.

## 🛠 Build from source

The repository contains the native app's NES/FCEUmm sources, PS5 adapter, Porpoise-derived Vulkan UI, header dependencies, and build scripts. The automated workflow compiles the real PS5 executable, verifies the signed installation package, and publishes versioned releases — not placeholder ZIPs.

- **Workflow:** [Build NESYX Native](.github/workflows/build-nesyx.yml)
- **Build instructions:** [BUILDING.md](BUILDING.md)
- **Native entry:** `nes/src/main_shelf.cpp`
- **Pixel Reactor:** `nes/src/loading.cpp`
- **UI and controller behavior:** `ps5/frontend/`
- **Asset sources:** `ps5/frontend/assets/`
- **Build script:** `nes/tools/build.sh`
- **Release version authority:** `app.json`

The GitHub Actions build restores pinned PS5 Vulkan/SDK dependencies, prepares shader and UI assets, compiles the native ELF, packages `PPSA99204.zip`, and uploads a versioned GitHub Release. It requires a suitable native PS5 SDK/toolchain; ordinary desktop compilation does **not** produce a PS5-installable application. New changes to native source on `main` automatically trigger the workflow. Releases use compatibility tags such as `ps5nesx-v1.0.28`.

## 🧾 Credits, rights and contributions

**Developed and customized by YAHBALLON.** NES emulation is based on the open-source [FCEUmm](https://github.com/libretro/libretro-fceumm) core. The native frontend includes components derived from open-source PS5 and Porpoise projects; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and original upstream licensing files.

**NESYX does not distribute commercial ROMs, BIOS files or pirated content.** Bring your own legally acquired game files. This project is community homebrew; it is not affiliated with Nintendo or Sony. Licensed material remains under the terms in [LICENSE](LICENSE) and the bundled third-party notices.

Bug reports and contributions are welcome through GitHub Issues and Pull Requests.
