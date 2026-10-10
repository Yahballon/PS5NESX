# Building PS5NES

(AI-assisted) The app is built under Linux or WSL with an out-of-tree object directory. The release was produced with a prepared public PS5 dependency environment; a completely fresh-machine dependency bootstrap has not been validated.

## Tools

Install Clang/LLD 18, CMake, Ninja, Make, Python 3, Git and the development tools required by the dependency projects.

The root PCSX2 CMake/Visual Studio projects belong to the inherited scaffold. For PS5NES, use **nes/tools/build.sh**.

## Tested source revisions

| Component | Revision / release |
| --- | --- |
| FCEUmm | 7a542dab1e87679921962a9f056186eca425c0c2 |
| PS5_Vulkan | f3cbf875f89978deae9f855b9be2610cec2818ae |
| PS5 payload SDK | upstream v0.42 with fork 95c08f27386fc698f6bbe21dde3030140a41d10b |
| OpenGL-derived shader compiler toolchain | 6cb291abea32281571c49705735046425cf000fd |
| Libnfs | libnfs-5.0.3 |
| PacBrew static libraries | v0.40.2 |
| Restricted Lapy helper | 54a095c0f19161825e845daa760a03b446e654fa |

FCEUmm source is included. Its revision is recorded in nes/third_party/fceumm/UPSTREAM_REVISION.txt, so extracting the source ZIP does not require its .git directory.

## Dependency layout

Prepare a dependency directory with this layout:

~~~text
deps/
├── PS5_Vulkan/
│   ├── build/driver/ps5/libps5vk.ps5.a
│   ├── build/driver/ps5/libpsbc_driver.ps5.a
│   ├── .deps/native/vulkan-runtime/lib/libvk_runtime.ps5.a
│   ├── .deps/native/psbc/lib/libpsbc_support.ps5.a
│   ├── .deps/native/ps5-payload-sdk/
│   └── runtime/libc.prx
├── libnfs/
├── libnfs-install/
│   ├── include/nfsc/
│   └── lib/libnfs.a
└── filesystem-helper/
    ├── tools/build-lapy-helper.py
    └── .deps/pacbrew/v0.40.2/sysroot/user/homebrew/
        ├── include/
        └── lib/
            ├── libcurl.a
            ├── libpsl.a
            ├── libssl.a
            ├── libcrypto.a
            ├── libzstd.a
            └── libz.a
~~~

Use the pinned public [PS5_Vulkan](https://github.com/mihawk-99/PS5_Vulkan) source and its documented SDK, compiler/runtime and driver build scripts. Its SDK setup expects the [PS5_PayloadSDK fork](https://github.com/mihawk-99/PS5_PayloadSDK) source or an explicit fork path. Keep the driver's dependency source available: the app builds its three required Mesa utility objects from that tree.

Build libnfs with the PS5 SDK toolchain:

~~~bash
git clone --branch libnfs-5.0.3 https://github.com/sahlberg/libnfs.git deps/libnfs
bash ps5/tools/build-libnfs.sh \
  deps/libnfs deps/libnfs-output \
  deps/PS5_Vulkan/.deps/native/ps5-payload-sdk/toolchain/prospero.cmake
~~~

That script prints LIBNFS_PREFIX. You can use its install directory directly instead of renaming it to libnfs-install.

Use [ps5-native-app-boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) as filesystem-helper. Its PacBrew setup script can resolve the static HTTPS dependency set:

~~~bash
bash deps/filesystem-helper/tools/setup-pacbrew-dependencies.sh --resolve libcurl
~~~

The helper builder fetches and verifies its own pinned public inputs. No Sony proprietary SDK is bundled.

## Build

~~~bash
export PS5NES_DEPS="$PWD/deps"
export PS5_PAYLOAD_SDK="$PS5NES_DEPS/PS5_Vulkan/.deps/native/ps5-payload-sdk"
export LIBNFS_PREFIX="$PS5NES_DEPS/libnfs-output/install"
export LIBZ_PREFIX="$PS5NES_DEPS/filesystem-helper/.deps/pacbrew/v0.40.2/sysroot/user/homebrew"
bash nes/tools/build.sh
~~~

LIBZ_PREFIX is the prefix for the complete static curl/SSL/compression library set, not just zlib.

If you already have compatible Mesa utility objects, PS5NES_MESA_UTIL_DIR can point to the directory containing u_thread.o, anon_file.o and os_file.o. Otherwise they are built into nes/build-shelf/mesa-util/.

Outputs:

~~~text
nes/build-shelf/package/PPSA99204/
nes/build-shelf/PS5NES-v1.0.0.9-Internal-ROM-Detection-by-YAHBALLON.zip
~~~

The build compiles the **project's PS5SX2 native writer**. Do not replace it with the driver helper packager: they emit different process-memory parameters. The generated ELF is checked before signing by nes/tools/check_memory.py.

## Shaders and assets

The checked-in fe_shaders.inc matches the shipped GLSL. After changing shaders, use a host glslang executable:

~~~bash
GLSLANG_VALIDATOR=/path/to/glslangValidator bash ps5/frontend/build_shaders.sh
~~~

The launcher icon must be a 512×512 PNG at nes/sce_sys/icon0.png. The supplied original logo is retained in nes/assets/logo-original.png.

## Verification

Useful checks include:

- nes/tools/check_memory.py — inspect the actual native ELF memory parameters.
- nes/tools/test.py — ROM/ZIP/input/audio/save-state/SRAM/PAL tests using a generated, original test ROM.
- ps5/frontend/host/test-nfs.py — NFS transport and failure tests.
- nes/tools/test_controller_bindings.cpp — input/chord and settings persistence checks.
- nes/tools/test_cover_window.cpp — bounded artwork streaming with a large library.

Some standalone test sources require compilation with their associated frontend sources; they are not all exposed through a single test runner. Host verification does not replace PS5 hardware testing.

Generated build folders, external dependency caches, local logs and Git internals are omitted from the release source archive.

## Preparing a GitHub source release (AI-assisted)

Review the diff, then refresh and verify the source inventory:

~~~bash
python3 tools/prepare_source.py --write
python3 tools/prepare_source.py --archive
~~~

The verified ZIP and SHA-256 checksum are written to `release/`. The ZIP contains
source and notices, including vendored dependency source, but no Git metadata
or ignored build output. Source hashes describe checkout bytes; line-ending
conversion can require refreshing the manifest on another machine.

Inherited PCSX2 desktop workflow definitions, funding configuration and support
links were removed for this PS5NES release. Their build helper sources remain
available in `.github/workflows/scripts/` for the retained desktop scaffold.
No automated PS5 build or hardware test is configured.
