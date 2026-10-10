# OpenGL 4.6 development validation

This is the detailed engineering record behind SDK 0.3.0, not a Khronos
conformance claim. Its pinned CTS discovery inventory accounts for all
**19,714** cases: **15,233 Pass**, **4,480 reviewed NotSupported**, and one
legal compatibility warning.

The static SDK exports all **657/657 OpenGL 4.6 Core commands**. Isolated Make,
pkg-config and CMake consumers compile and link using only the installed SDK and
the public PS5 payload toolchain.

## Compatibility application gate

The hardware gate at commit `0f127f0` passes OpenGL 4.6 Compatibility and GLSL
4.60 compatibility contexts, material ambient state, all eight alpha functions,
color clamping, point sprites, polygon mode/culling restoration, legacy
`QUADS`/`QUAD_STRIP`/`POLYGON` draws, first/last provoking-vertex flat shading,
and shared-context migration and cleanup. Its eboot SHA-256 is
`63ffcaaa8ef71fd5e77a9d0f9141dad18d348e40e1c89a210a78fba0514a1254`.
The consolidated receipt reports `legacy=8/8 share=1 result=0` and clean runtime
layer release. The repository's 128 host tests and published-validation audit
also pass.

## Compatibility warning

`KHR-GL46.direct_state_access.framebuffers_check_status` reports a CTS
compatibility warning when two requested multisample counts both resolve to the
same native four-sample allocation. OpenGL permits implementation-selected
sample counts, and the tested framebuffer configurations are complete. The
warning is retained as evidence rather than converted into a false driver
failure or hidden by misreporting capabilities.

## NotSupported audit

`tools/audit-gl46-notsupported.py` matched every NotSupported case to its QPA
diagnostic; none lacked evidence. The result is an implementation triage, not
an acceptance waiver.

| Classification | Cases | Interpretation |
| --- | ---: | --- |
| Optional extension | 4,176 | Outside OpenGL 4.6 Core by itself |
| Profile/test-inapplicable | 212 | Test does not apply to this context or permutation |
| Format/sample/limit | 92 | Legal advertised limit or non-required renderability |
| Unresolved capability/review | 0 | No case remains in the review queue |

The large optional-extension count is dominated by sparse textures and
fragment shading rate. These results are an engineering disposition of the
pinned inventory, not a Khronos conformance waiver or certification claim.

Commit `4893195787e31ce30ed33d6a3eba405a2df3d02b` corrected the advertised
tessellation-control/evaluation shader-storage limits after the existing
descriptor, binding and lifetime paths were verified. One native-title batch
then passed all **464/464** affected constant-expression cases with zero
NotSupported results, followed by clean teardown and healthy console services.
The receipt is retained under
`results/opengl46-cts-tess-ssbo-constant464-20260917`.

The two functional tessellation-SSBO cases initially exposed sparse Gallium
storage slots produced by atomic-counter lowering. Commit
`efd4aec3685912ee3d390cbd43dd79e0713eef5d` now emits zero descriptors for
unbound holes while retaining validation for bound resources; both cases pass
in `results/opengl46-cts-tess-ssbo-functional2-fixed-20260917`.

Commits `c1f86b66d612668068552a5b9afbaf96fc35edac` and
`2916cf89f6c466659ee53d7ae9b36331bec61dc2` add vertex-stage shader-storage
buffers and preserve separate vertex/geometry storage banks in merged geometry
pipelines. All **51/51** affected cases pass: the first 14 are retained in
`results/opengl46-cts-vs-ssbo51-20260917`, and the repaired case plus the 36
previously unexecuted cases are retained in
`results/opengl46-cts-vs-ssbo-remaining37-20260917`.

Commits `0cac2d2`, `d657910`, and `79f1e35` add pre-raster image banks,
preserve images through tessellation linking, and compose missing texel-buffer
channels consistently for sampled and image access. Commits `0d7dc75` and
`b9f7d1d` then add native four-sample storage-image allocation, descriptors and
compiler lowering. `GL_MAX_IMAGE_SAMPLES` is now **4**. All **66/66** affected
cases pass; the earlier 24 multisampled-image NotSupported results are closed.
The exact receipts are retained under
`results/gl46-preraster-images-sync-fix-v2`,
`results/gl46-preraster-images-remaining59`, and
`results/gl46-ms-image-operations-native-v3`.

The focused native proof covers `image2DMS` and `image2DMSArray` size queries
in every shader stage and float, signed-integer and unsigned-integer forms.
It also passes CTS store, load, atomics, per-sample SSO access and
`imageSamples`. The final five-case receipt used eboot SHA-256
`789540d08ac4f357800aa86abc9558db355201eb06040356e237b4c09bfdd6c1`
and completed with clean title teardown and healthy console services.

The final **325-case** capability/review queue was then executed as one exact
native-title batch. **66 passed** and **259 returned NotSupported**, with no
failures or incomplete cases. A second three-case run used the 256x256 surface
required by the texture-query-LOD tests; all three passed. That 69-pass overlay
plus the multisampled-image implementation leaves **231** reviewed
NotSupported cases:

- 192 texture-swizzle permutations rejected by the CTS's own target/format or
  target/access guards;
- 16 cull-distance permutations explicitly excluded by the CTS test design;
- 15 optional-extension cases;
- four 8-sample cases above the advertised four-sample limit;
- one desktop-profile-inapplicable transform-feedback case;
- one GLSL 3.30 path below the integer-mix core version;
- one non-required `RGB9_E5` renderbuffer case; and
- one tessellation test limited by otherwise legal asymmetric transform-feedback
  and tessellation-output maxima.

Receipts are retained under `results/gl46-remaining325-v1` and
`results/gl46-texture-query-lod3-256-v1`. Both runs completed through native
title teardown; the PS5 services remained healthy and the exact lock token was
released after each run.

Reproduce the audit from retained local QPA results:

```sh
python3 tools/test_gl46_notsupported_audit.py
python3 tools/audit-gl46-notsupported.py \
  --plan .local/opengl46/queue-final-verified-20260917/plan.json \
  --results results --json not-supported.json --markdown NOT-SUPPORTED.md
```

That command reproduces the pre-fix baseline; apply the focused passing
receipts above and the final 325-case review receipts to obtain the current
aggregate. The full 19,714-case inventory was not rerun for these isolated
capability changes.

## Native stress and Piglit subset

Commit `71adf81a0ff2cf6364dfb639d419e7361880b526` combines six existing or
focused public-API oracles in one native title and repeats the complete set
twice. The frozen eboot SHA-256 was
`9b2056d267d9f3e6f3832cb7b1ed3dfaf6651985f06e3531294494aa038ca011`.

All **12/12** checks passed on the firmware-6.02 console, followed by exact-title
close, runtime-layer release, healthy FTP/klog/loader services, and exact lock
release. The checks cover:

- persistent/coherent immutable buffers;
- compute SSBOs, images, atomics and indirect dispatch;
- compute-to-graphics synchronization;
- indirect graphics draws;
- SPIR-V load, specialization, link and draw; and
- Piglit's ordered six-dispatch SSBO/atomic-counter sequence, including the
  final 256-word payload.

The focused Piglit mapping, upstream pin, attribution and license are under
[`tests/piglit`](../tests/piglit/README.md). This adapts selected edge cases to
the native title harness; it does not port or claim to run Piglit's desktop
runner.
