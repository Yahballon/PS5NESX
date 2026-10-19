# Building NESYX for PlayStation 5

**NESYX v1.0.27** · **by YAHBALLON** · **Title ID `PPSA99204`**

This repository contains the actual native FCEUmm + Vulkan/Porpoise frontend used in the installed homebrew app. It is a PS5 application, not a PC executable. GitHub Actions builds, validates and publishes `PPSA99204.zip` from the checked-in source.

## Recommended: GitHub Actions

The supported build path is **[NESYX Native Build & Release](.github/workflows/build-nesyx.yml)**.

1. Push your code to `main` or start the workflow via **Actions → NESYX Native Build & Release → Run workflow**.
2. The job checks `app.json` (single version authority), runs all CoverFlow/asset/controller/display regression tests, installs PS5 toolchain dependencies, and compiles the PS5 executable.
3. It validates the signed `eboot.bin`, PS5 metadata and files inside `PPSA99204.zip`.
4. A successful main-branch build uploads a workflow artifact and creates a tagged [GitHub Release](https://github.com/Yahballon/PS5NESX/releases).

Release tags retain the compatibility prefix `ps5nesx-v<version>` while the app is called NESYX. **Never re-use an existing release tag**: increase `version` and `releaseTag` together in `app.json` first. Do not modify `PPSA99204` or the existing `/data/PS5NES` data directory.

The first native build for this repository can take a while because it creates the Vulkan compiler SDK and shader archives. Later builds may restore the repository's CI cache.

## Native build prerequisites

For an advanced local build use Ubuntu 24.04 or compatible Linux/WSL with Clang/LLD 18, LLVM 18, CMake, Ninja, Make, glslangValidator, Meson, Python 3, a working C/C++ toolchain and network access to the pinned open-source dependencies.

The CI configuration is the reproducible reference:

- `scripts/bootstrap_native.sh` — prepares PS5_Vulkan, the payload SDK, PS5 shader compiler sources and signed runtime imports.
- `scripts/build_generated_psbc.py` — compiles generated NIR/SPIR-V/ACO objects missing in a cold compiler build.
- `scripts/build_agc_imports.py` — creates **link-time** AGC import stubs (not packaged as substitute runtime libraries).
- `ps5/tools/build-libnfs.sh` — builds pinned libnfs for the console toolchain.
- `nes/tools/build.sh` → `nes/tools/build_shelf.py` — builds the FCEUmm core, PS5 application ELF, signs and packages it.

Never distribute the third-party toolchain caches, locally built proprietary content, or copyrighted ROMs.

### Set up SDK archives

The workflow performs these commands after apt package installation:

```bash
bash scripts/bootstrap_native.sh

export PS5_VULKAN_DIR="$PWD/build/deps/PS5_Vulkan"
export PS5_PAYLOAD_SDK="$PS5_VULKAN_DIR/.deps/native/ps5-payload-sdk"

python3 scripts/build_generated_psbc.py
python3 scripts/build_agc_imports.py
```

Build the native network libraries and PacBrew static dependencies using the exact commands in [the workflow](.github/workflows/build-nesyx.yml), then export:

```bash
export PS5NES_DEPS="$PWD/deps"
export PS5_PAYLOAD_SDK="$PS5NES_DEPS/PS5_Vulkan/.deps/native/ps5-payload-sdk"
export LIBNFS_PREFIX="$PS5NES_DEPS/libnfs-output/install"
export LIBZ_PREFIX="$PS5NES_DEPS/filesystem-helper/.deps/pacbrew/v0.40.2/sysroot/user/homebrew"
export PS5NES_PSBC_GENERATED="$PWD/build/ps5-core/generated-psbc.ps5.a"
export PS5NES_AGC_STUB_DIR="$PWD/build/ps5-core/agc-imports"

bash nes/tools/build.sh
```

`deps/PS5_Vulkan` is a symlink to `build/deps/PS5_Vulkan` created by the workflow. The builder also requires the **verified, previously signed `PPSA99204/lapy.elf` helper** from the source project's `ps5nesx-v1.0.11` archive. The CI workflow downloads and SHA-256-checks that package; set `PS5NES_LAPY_BASELINE` to the corresponding ZIP if building manually. The helper's source is no longer publicly available, so builds must not fabricate its replacement.

### Build output

```text
nes/build-shelf/NESYX-v1.0.27-by-YAHBALLON.zip
dist/PPSA99204.zip                  # validated CI release copy
```

The installed package contains a real signed `PPSA99204/eboot.bin`, a `sce_sys/` directory, `sce_module/libc.prx`, helper files and third-party licenses.

## Shader, source and interface layout

| Path | Responsibility |
| --- | --- |
| `app.json` | Display version, release tag, title identifier |
| `nes/src/core_session.cpp` | FCEUmm and Mesen-style HD pack integration |
| `nes/src/loading.cpp` | Animated Pixel Reactor startup screen |
| `nes/src/shelf_runtime.cpp` | Emulation session and 16:9/4:3/integer viewport |
| `ps5/frontend/fe_exact_porpoise.cpp` | NESYX CoverFlow, glass cases, tiger header, fallback covers |
| `ps5/frontend/fe_app.cpp` | Settings, menu input and Circle-to-close confirmation |
| `ps5/frontend/assets/no-cover.png` | Original 1024 × 1536 NO COVER fallback |
| `ps5/frontend/assets/tiger-logo.png` | Original tiger branding |
| `ps5/porpoise_original/` | Original Porpoise renderer with PS5-specific integration |
| `tests/` | Regression suite executed by native CI |

Rebuild modified shaders with `bash ps5/frontend/build_shaders.sh` and `python3 ps5/porpoise_original/tools/rebuild_shader.py`. The Porpoise source and legal notices are included; required runtime fonts/sounds are verified against pinned upstream hashes during CI.

## Source provenance and licensing

This standalone repository was synchronized from the **PS5-hardware-tested NESYX v1.0.27** files in `Yahballon/tmp_lap/homebrew/ps5nesx`; future changes can be made directly here. The one-time import helper is `[Import NESYX Source](.github/workflows/sync-nesyx-source.yml)`. Rerunning it deliberately reapplies its pinned source snapshot and can overwrite native source edits, so do not use it to build future releases.

No game ROMs, BIOS or copyrighted commercial game files are included. See `LICENSE`, `THIRD_PARTY_NOTICES.md` and the upstream libraries' own licenses.
