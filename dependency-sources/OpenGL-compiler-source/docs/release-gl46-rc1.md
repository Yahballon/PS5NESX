# OpenGL 4.6 release candidate

This document freezes the local `0.3.0-gl46-rc1` candidate. It is release-ready
for independent review, but has not been published or submitted for Khronos
certification.

## Candidate identity

| Item | Value |
| --- | --- |
| Branch | `gl46-dev` |
| SDK source commit | `b4889e5b9658668a5ff3ce4ea18c10b75dae9267` |
| SDK directory | `ps5-opengl-sdk-0.3.0-gl46-rc1-b4889e5` |
| Archive | `ps5-opengl-sdk-0.3.0-gl46-rc1-b4889e5.tar.gz` |
| Archive size | 89,213,890 bytes |
| Archive SHA-256 | `eede80b1e6e08865c664560789162ebf4d27db7cb2ef53dd77c603b9351b5f82` |
| Runtime archive SHA-256 | `f5b6054c36f94d7a48c4c5cbcac3124b1996d18c7bddb7aa451b417f17340344` |

The archive is deterministic, its external checksum passes, and every file in
the extracted SDK matches `manifest.sha256`.

## Verification summary

- All 657 OpenGL 4.6 Core commands are exported.
- Installed-SDK consumers build through Make, pkg-config and CMake from a
  relocated extraction outside the source tree.
- The compatibility Make and pkg-config interfaces resolve the AGC imports
  from the selected SDK instead of an unrelated payload-toolchain copy.
- A native Yamagi Quake II application builds, links, signs and passes container
  inspection against this SDK. Its `eboot.bin` is 27,895,036 bytes with SHA-256
  `6401a6748e1601a93c1d107693c5e70362bf1fb1931a5e51e580d3fd5ee68493`.
- The host and compiler checks pass, including the historical 39,544-result
  OpenGL 3.3 accounting set and the generated 657-command link surface.

## Console evidence

The runtime from source commit `ac9214cb291def646aeeadb45278d999c634aad3`
completed the 12-case OpenGL 4.6 stress application on hardware. It covered
direct state access, persistent/coherent buffers, compute and graphics
synchronization, SSBOs, images, atomics, indirect draws and SPIR-V. The receipt
ended with `completed=12 result=PASS` and has SHA-256
`c98960f804711c3966fc0f2814a32856e1f7be41fd5ee9684259d82a6520199d`.

Commit `b4889e5` changes installed metadata only. Its runtime archive is
byte-identical to the hardware-tested candidate, as identified by the runtime
archive hash above.

The OpenGL 4.6 inventory accounts for 19,714 cases: 15,233 passes, 4,480
reviewed `NotSupported` results and one legal compatibility warning. The warning
comes from two requested framebuffer sample counts mapping to the same native
sample count; the resulting framebuffer status is permitted by the CTS case and
is not a failure.

## Boundaries

- This is engineering validation, not Khronos conformance certification.
- `NotSupported` results are reviewed exclusions, not passes.
- Display mode, lifecycle and performance qualifications remain limited to the
  documented hardware and configurations.
- Consumer build systems must use the AGC import stubs shipped with this SDK.
- The archive and report are local release artifacts until an explicit publish
  decision is made.
