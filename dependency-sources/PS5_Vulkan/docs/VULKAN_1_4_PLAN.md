# Vulkan 1.4 and a clean CTS: the plan

Drafted 2026-09-26, for my decision. It answers two questions: what stands between
this driver and a Vulkan 1.4 device, and the most efficient way to reach a driver
that passes the whole Vulkan CTS for everything it reports. The version ladder in
[M5_REFERENCE.md](M5_REFERENCE.md) and the CTS recipe in [CTS.md](CTS.md) stay the
rules; this file changes the route, not the rules.

**The recommendation, in one paragraph.** Do not climb to 1.4 by growing ps5vk
subsystem by subsystem. Port Mesa's RADV driver to the console instead: RADV stays
whole, and a PS5 *winsys* (the layer RADV already keeps the kernel behind) supplies
memory, command submission and sync from what ps5vk has proved. The shader compiler
this driver uses already *is* RADV's, every conformance gap listed below is a
subsystem RADV already implements for this GPU family, and RADV in the Mesa release
pinned here reports Vulkan 1.4 conformance. A short spike of eight console probes
decides whether the console accepts RADV's command stream; if it does not, the
fallback is the same work done inside ps5vk, in the order given at the end.

## Where the driver stands

Read from the code at `c1f82d8` (R95), not from earlier notes.

| | Today |
| --- | --- |
| Reported version | 1.1 (instance and device, `PS5VK_*_API_VERSION`) |
| Features on | 4: `robustBufferAccess`, `multiview`, `samplerAnisotropy`, `dualSrcBlend` |
| Device extensions | 3: `VK_KHR_swapchain`, `VK_KHR_sampler_mirror_clamp_to_edge`, `VK_EXT_memory_budget` |
| Queues | one family (graphics, compute, transfer), one queue |
| Shader stages | vertex, fragment, compute; subgroups in compute only, basic operations |
| Memory | one heap, two types (device-local; device-local + host-visible + host-coherent) |
| Barriers | `vkCmdPipelineBarrier2` records nothing; the driver infers render-to-texture hazards and inserts its own GPU barrier (R70) |
| Transfers | CPU work at submission split points (copies, fills, updates, clears, uploads, readbacks); tiled-to-tiled copies through `vk_meta` |
| Descriptors | CPU records; every draw and dispatch writes its sets' tables |
| Images | two layouts, rows (non-attachments) and 64 KiB tiles (attachments); each shape is used only once a probe measured it |
| Sync | CPU binary syncs; a submission waits for its semaphores on the calling thread; no timeline; events are CPU work at split points |
| Run-time refusals | about 150 named sites (`ps5vk_draw.c` 68, `ps5vk_image.c` 46, `ps5vk_pipeline.c` 14, the rest in commands, queries, compute and descriptors) |
| CTS | pinned `vulkan-cts-1.3.8.4`; host runs only (`dEQP-VK.api.info.*`: 2539 pass, 1342 not supported, 5 fail); no console run yet |

### What the CTS will find in today's claim

These are not 1.4 work. They are places where what the device reports today is not
yet what it does, and a console CTS run will count each as a failure:

1. **Several colour attachments.** `maxColorAttachments` is 4, Vulkan 1.0's minimum,
   but a rendering into more than one is refused: writes past the first do not land
   (`v0-mrt`, R7 step 1b).
2. **Compressed textures.** Vulkan 1.0 requires one of the BC, ETC2 or ASTC LDR
   families. None is reported; the host CTS's `format_properties.compressed_formats`
   fails on it.
3. **Robust buffer access.** The feature is on because an indexed draw's count is
   clamped to its index buffer. The guarantee covers every shader access to a buffer
   and every vertex fetch, which on this GPU comes from descriptor bounds.
4. **Barriers.** With `vkCmdPipelineBarrier2` empty, a dispatch that reads what the
   previous one wrote, or a draw that reads what a dispatch wrote, depends on caches
   nobody invalidated.
5. **Occlusion queries.** The driver reads one 8-byte counter and multiplies by 16. The
   recorded evidence points to one counter per render backend: a `ZPASS_DONE` write
   left counter words across a 0xcc-byte range of a scratch block (M5_PHASE_C.md,
   2026-09-18, V0-query's timestamp probe), and the counts for a full and a half screen
   divide evenly by 16. If that holds, a small draw can read 0, and each query's write
   spills into the queries after it.
6. **Host coherence.** Type 1 says host-coherent, and the driver's own paths evict CPU
   cache lines before reading what the GPU wrote. Only colour targets and query pools
   are evicted around submissions, so a storage buffer a shader wrote can be read stale
   through a mapping. The direction CPU-write, GPU-read has not been measured either.
7. **Events and semaphores.** A device-side wait on an event is CPU work at a split
   point, and a submission that waits for a semaphore blocks the thread that submitted
   it, so waiting before the signal is submitted cannot work.
8. **Refused shapes that are mandatory.** Some refusals are for features the device
   does not report, which is correct. Others are core behaviour: layered rendering
   without a view mask, many copy, readback and clear shapes, array and 3D images. A
   refusal at `vkEndCommandBuffer` is a CTS failure, not "not supported".

## What Vulkan 1.4 requires

From the registry `vk-v1.4.354.xml` and `features-v1.4.354.adoc`:

- **Features.** Unconditional: 7 from 1.2 (`timelineSemaphore`,
  `imagelessFramebuffer`, `uniformBufferStandardLayout`,
  `shaderSubgroupExtendedTypes`, `separateDepthStencilLayouts`, `hostQueryReset`,
  `subgroupBroadcastDynamicId`), 16 from 1.3 (`dynamicRendering`, `synchronization2`,
  `maintenance4`, `bufferDeviceAddress`, `vulkanMemoryModel` and its device scope,
  `inlineUniformBlock`, `robustImageAccess`, `privateData`,
  `pipelineCreationCacheControl`, `shaderTerminateInvocation`,
  `shaderDemoteToHelperInvocation`, `shaderZeroInitializeWorkgroupMemory`,
  `shaderIntegerDotProduct`, `subgroupSizeControl`, `computeFullSubgroups`) and 41
  from 1.4 (every one in its list except `pipelineProtectedAccess`, which only comes
  with protected memory). Today one of the 1.4 list is on (`samplerAnisotropy`), and
  `samplerMirrorClampToEdge` works through its extension.
- **Host image copy.** A device whose only transfer-capable family is its graphics
  family must support `hostImageCopy`. That is this device.
- **SPIR-V** 1.0 to 1.6, and the subgroup rotate operations.
- **Limits** (limits-v1.4.354.adoc), against today's values:

  | Limit | Today | 1.4 |
  | --- | --- | --- |
  | `maxImageDimension3D` | 256 | 512 |
  | `maxImageArrayLayers` | 256 | 2048 |
  | `maxUniformBufferRange` | 16384 | 65536 |
  | `maxPushConstantsSize` | 128 | 256 |
  | `maxBoundDescriptorSets` | 4 | 7 |
  | `maxPerStageDescriptorUniformBuffers` | 12 | 15 |
  | `maxPerStageResources` | 44 | 200 |
  | `maxDescriptorSetUniformBuffers` / `StorageBuffers` / `StorageImages` | 36 / 12 / 12 | 90 / 96 / 144 |
  | `maxFragmentCombinedOutputResources` | 4 | 16 |
  | `maxComputeWorkGroupInvocations` / size | 128 / (128,128,64) | 256 / (256,256,64) |
  | `subTexelPrecisionBits` / `mipmapPrecisionBits` | 4 / 4 | 8 / 6 |
  | `maxViewportDimensions` / `maxFramebufferWidth`,`Height` | 16384 | 7680 (met) |
  | `maxColorAttachments` | 4 (one works) | 8 |
  | `pointSizeRange` / granularity, `lineWidthGranularity` | 1.0 / 0, 0 | up to 256 / 0.125, 0.5 |
  | `standardSampleLocations` | false | true |

  The GPU can do every one of these; RADV reports all of them on this family. What the
  console adds is the 4 GiB window that 32-bit shader pointers reach, which bounds
  descriptor and push-constant memory, not images or buffers (R86-R88).

## The choice

**A. Grow ps5vk.** Replace, one at a time, the barrier model, the CPU transfers, the
CPU descriptors, the two image layouts, the sync objects and the queries, then add the
1.2-1.4 features, the shader capabilities and the limits. Each replacement is a large
share of what RADV already is, rewritten against ps5vk's structures, and then proved
case by case.

**B. RADV on the console.** Build Mesa's RADV for the PS5 with a new winsys, keep
ps5vk shipping until the new driver passes the same titles, then switch.

I recommend **B**, for five reasons found in this analysis:

- **The compiler is already RADV.** libpsbc is Mesa 26.2.0's RADV shader pipeline
  (`radv_shader_spirv_to_nir`, `radv_shader_nir_to_asm`, ACO) for `CHIP_NAVI21`,
  GFX10.3. ps5vk reaches it through a narrow wrapper that needs a patch script per
  capability (ten in `tooling/psbc/` so far) and enables seven SPIR-V capabilities. RADV
  drives the same code with its full capability table and pipeline keys.
- **Every gap above is a RADV subsystem for this GPU family.** Its GFX10 cache flushes
  and barriers, meta operations on the GPU (copies, blits, clears, resolves, fills),
  descriptor sets in GPU memory with update-after-bind, AddrLib image layouts,
  per-render-backend occlusion queries, timeline semaphores and host image copy (on by
  default for GFX10.3). The AddrLib pinned here already agrees with every tile map
  measured on the console (AGC_UPSTREAM_NOTES.md).
- **The residual is known.** RADV in Mesa 26.2.0 reports CTS 1.4.5.3 conformance, and
  Mesa's own CI expects 92 failing cases on navi21, all in
  `dEQP-VK.api.copy_and_blit.core` (`src/amd/ci/radv-navi21-fails.txt`). A case that
  fails on the console and not on that list is the port's, which makes triage direct.
- **The console's rules fit the winsys interface.** About 40 callbacks cover buffers,
  command streams, submission and sync. RADV can run without command-buffer chaining
  (`chain_ib` false), which is what a console where `INDIRECT_BUFFER` faulted needs, and
  it already separates buffers that 32-bit pointers must reach
  (`RADEON_FLAG_32BIT`), which is the address window.
- **It carries the later targets.** Eden needs a broad modern Vulkan (extended dynamic
  state, descriptor indexing, transform feedback, geometry and tessellation shaders),
  and PS2 at 4K60 benefits from RADV's performance work (DCC and HTILE compression, NGG
  culling). Upstream fixes then arrive with a Mesa update instead of a new round.

What B costs:

- The console has to accept RADV's command stream: direct register packets where ps5vk
  uses AGC's indirect register tables, RADV's state preamble, and graphics shaders at
  raw addresses without `sceAgcCreateShader`. The spike settles this first.
- The hardware facts Linux reads from the kernel (compute units, render backends,
  shader engines, the address configuration) have to be measured on the console.
- RADV has to build with the PS5 toolchain. Most of Mesa's util layer already does
  (libpsbc, the Vulkan runtime); the gaps go into the SDK's shared platform layer, not
  into the Mesa fork.
- Two drivers exist for a while. RetroArch links one archive or the other, and ps5vk
  stays the default until the new one passes.

What moves from ps5vk into the winsys, unchanged in substance: direct-memory
allocation and placement (the address window and the 256 GiB device-memory region),
submission through `sceAgcDriverSubmitDcb` with `sceAgcSuspendPoint` and the rising
marker (R68, R69), the CPU cache discipline, the VideoOut presentation path
(`ps5vk_wsi.c`, including the output-mode check), the measured tile and format maps as
cross-checks, the runner, the goldens and every hardware finding.

## Phase 0: the spike (go or no-go)

Eight probes, each a runner case with its golden, like every other step. They are
ordered so the first two decide the route.

| Probe | What it proves |
| --- | --- |
| S1 packets | The M2 triangle drawn with RADV's direct `SET_CONTEXT_REG`, `SET_SH_REG` and `SET_UCONFIG_REG` packets, no AGC register tables |
| S2 shader address | Vertex and pixel stages run from raw addresses in `SPI_SHADER_PGM_LO/HI` without AGC shader objects (compute already runs this way) |
| S3 preamble | RADV's graphics and compute preamble in front of S1's draw; a fault is bisected to the register that causes it |
| S4 caches | RADV's GFX10 barrier (`ACQUIRE_MEM` with the GCR fields, CS and PS partial flushes): a dispatch reads what the previous one wrote while old contents sit in the caches |
| S5 chaining | `INDIRECT_BUFFER` in RADV's form, into memory allocated like the submission buffer. If it faults again, the winsys copies streams as ps5vk does |
| S6 render backends | `ZPASS_DONE`'s layout: how many counters, at what stride, and which one a one-pixel draw lands on |
| S7 coherence | CPU writes read by the GPU and GPU writes read by the CPU, with and without evictions, on the mapping ps5vk uses; decides which memory types are coherent and which are cached |
| S8 build | RADV and the winsys built with the PS5 toolchain and linked into the runner |

**Go** if S1 to S4 pass; S5 to S7 shape the winsys but do not block. **No-go** if the
console refuses direct register packets or raw shader addresses in a way the exported
AGC helpers cannot stand in for; then route A applies, with the order below.

S6 and S7 are worth running whatever the route: they test suspected defects in the
shipping driver (items 5 and 6 above).

## Phase 1: RADV on the console

In a Mesa fork pinned by revision, like the SDK and LRPS2 forks, not a patch series:

1. **Winsys.** Buffers as direct-memory allocations, placed in the window when RADV
   asks for 32-bit reach and in the device-memory region otherwise. Command streams
   copied into the submission buffer, or chained if S5 allows it. Submission, the
   suspend point and the marker as ps5vk does them. Syncs backed by the marker, with
   Mesa's timeline emulation and threaded submission so a wait can be submitted before
   its signal.
2. **Device facts** from S3, S6 and S7, measured on my console, never read from the
   firmware.
3. **Presentation.** The VideoOut path from `ps5vk_wsi.c` as the new driver's
   swapchain.
4. **Gate.** The runner's goldens compared by pixels (the packets will differ), then
   vkQuake, and RetroArch with PPSSPP, Dolphin and LRPS2, on the console. After that the
   titles switch archives.

## Phase 2: the CTS on the console

This does not wait for Phase 1; its first target is ps5vk, which also gives the
before-and-after for the switch.

- **Pin a 1.4 CTS.** The 1.3.8.4 pin cannot test 1.4. RADV here reports 1.4.5.3, so a
  `vulkan-cts-1.4.5.x` tag is the matched one.
- **A CTS title.** `deqp-vk` built for the console and linked statically with the
  driver archive; a title cannot load libraries, so the CTS gets
  `vkGetInstanceProcAddr` through its own platform layer.
- **Crash-proof runs.** Case lists as queue files; one result per case appended to a
  file in the title's directory (reachable over FTP, 0666); a relaunch resumes after
  the case that crashed; a watchdog for hangs; image and shader-source logging off. The
  console is checked idle before every launch, as for every run.
- **Host runs** keep the API and reporting groups on the host model, several processes
  at once.
- **Three tiers.** A smoke fraction on every driver change; the failing cases and their
  groups on every fix; the full mustpass at each version gate. The vk-default list at the
  current pin has 2,718,289 cases, and about 1.1 million of them are in groups keyed to
  extensions a core 1.4 device need not expose (shader objects, pipeline libraries,
  fragment shading rate, transform feedback, mesh shaders, ray tracing). The manifest
  excludes a case by the capability it needs, with the evidence line, as CTS.md
  already requires.
- **Triage by cluster.** Group failures by test group and message, fix the largest
  cluster first, and add the runner regression case before the fix. With RADV, diff
  each run against Mesa's navi21 expectations first.

## Phase 3: the version climb

One commit per version, each gated by a full mustpass run for everything that version
reports (M5_REFERENCE.md rule 1): 1.2, then 1.3, then 1.4. With RADV the climb is
mostly exposure and evidence; the console-specific parts are the limits the address
window touches, host image copy against the measured tile maps, global priority on a
single queue, and protected memory reported off.

## Phase 4: closure

**What "100% CTS" means here.** Every case of the pinned 1.4 CTS's vk-default mustpass
runs; none is Fail, Crash or Timeout; every NotSupported names the reporting line that
excludes it; and two consecutive full runs of the same build agree. That is the
engineering standard. Formal Khronos conformance is a separate submission through the
Khronos Adopters Program, which this project does not attempt (CTS.md), and nothing
here claims it.

## Beyond the required set

"All of 1.4" also means its optional features. RADV exposes on this GPU family the
ones the titles want: geometry and tessellation shaders, `multiDrawIndirect`,
`shaderFloat64`, wide lines, extended dynamic state 3, descriptor buffers, transform
feedback, and later mesh shaders and ray queries. Each is exposed in a batch with its
CTS groups clean, in the order the titles need them: what Dolphin, LRPS2 and PPSSPP
use first, then what Eden needs.

## Risks

| Risk | Answer |
| --- | --- |
| The console refuses part of RADV's stream | S1 to S3 first; bisect a fault to its packet; a register that has to go through an exported AGC helper goes through it in the winsys |
| The GPU differs from navi21 | ACO already targets it (every psbc shader runs); the unit counts and address configuration are measured, and the goldens compare pixels |
| Title size | RADV with ACO and AddrLib replaces ps5vk plus libpsbc, which already carries ACO and NIR (29.8 MB stripped); measured at S8 |
| CTS time on one console | the tiers and manifests above; the full list only at gates |
| A CTS case hangs the GPU | the watchdog and a quarantine list with the case named; never while I might be playing |
| Upstream drift | the fork follows Mesa releases, not the main branch |

## If the spike says no: route A's order

The same subsystems, ported from RADV into ps5vk, in the order that removes the most
CTS failures per step:

1. Barriers and caches (GFX10 cache flushes), which also retires the render-to-texture
   hazard tracking and most submission splits.
2. Transfers on the GPU (`vk_meta` and CP DMA), which removes the remaining splits.
3. Descriptor sets in GPU memory, with update-after-bind and push descriptors.
4. AddrLib layouts for every image type, level, layer and sample count.
5. Timeline semaphores, threaded submission and events on the GPU.
6. Per-backend occlusion queries and the coherence fix (S6, S7).
7. Several colour attachments, then independent blending and eight attachments.
8. The shader interface: the full SPIR-V capability table and RADV's pipeline key in
   place of the per-feature patch scripts.
9. The 1.4 limits, the remaining features, host image copy.
