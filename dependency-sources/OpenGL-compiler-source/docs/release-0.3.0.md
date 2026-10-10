# PS5 OpenGL SDK 0.3.0

SDK 0.3.0 is the first public OpenGL 4.6 Core / GLSL 4.60 release. It exports
all 657 OpenGL 4.6 Core commands through the generic Make, pkg-config and CMake
interfaces while retaining the OpenGL 3.3 compatibility aliases used by older
ports.

## Build and install

Download the archive and matching `.sha256` file from the
[v0.3.0 release](https://github.com/blackbearreloaded/ps5-opengl/releases/tag/v0.3.0),
then verify both archive and internal checksums:

```sh
sha256sum --check ps5-opengl-sdk-0.3.0*.tar.gz.sha256
tar -xzf ps5-opengl-sdk-0.3.0*.tar.gz
cd ps5-opengl-sdk-0.3.0*
sha256sum --check SHA256SUMS
export PS5_OPENGL_PREFIX="$PWD/sdk"
```

Build from source with `make source-fetch && make sdk-gl46`. The local package
is written to `build/sdk/ps5-opengl-gl46`.

## Included interfaces

- EGL fullscreen presentation and OpenGL 4.6 Core / GLSL 4.60;
- 657 OpenGL 4.6 Core exports and the 344-command 3.3 compatibility surface;
- relocatable static libraries, GL/EGL/KHR headers and checksums;
- generic Make, `ps5-opengl` pkg-config and `PS5OpenGL::OpenGL` CMake support;
- legacy Core33 build aliases for existing applications;
- public examples, source archives, dependency identities, licenses and provenance;
- optional 1080p60, 1440p120 and 2160p120 build profiles.

## Qualification

The engineering inventory accounts for 19,714 OpenGL 4.6 cases: 15,233 passes,
4,480 individually reviewed `NotSupported` results and one legal compatibility
warning. Focused native checks cover persistent/coherent buffers, compute and
graphics synchronization, SSBOs, images, atomics, indirect draws, SPIR-V,
multisampled images, presentation and lifecycle behavior. Substantial renderer
integration has also exercised the SDK without a remaining concrete OpenGL
driver rejection.

This is not Khronos certification. `NotSupported` cases are not passes. CTS,
performance and hardware results belong to their recorded exact binaries; the
fresh GitHub Actions archive is host/compiler/export/consumer checked and does
not automatically inherit console acceptance. See the
[validation report](gl46-development-validation.md), [limitations](limitations.md)
and [CI provenance](ci-releases.md).

## Distribution boundary

No vendor SDK, firmware module, device key, proprietary shader package,
console-enablement payload or raw device log is included. The public payload SDK
and an already configured native-homebrew environment are separate prerequisites.
