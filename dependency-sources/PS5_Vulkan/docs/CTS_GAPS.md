# CTS gaps before the next full run

Every case main-1 did not pass, and every reason it gave for "not supported",
has an owner here. The next full CTS run happens only once each item is
closed: fixed and proved by a targeted run of the groups behind it, or
recorded with the reason it cannot be offered. A "not supported" that the
port caused is open work, not an acceptable result.

The reference for "the port caused it" is upstream RADV itself: the same
Mesa revision built for Linux, faking a Navi21 with the amdgpu DRM shim, was
compared with the PS5 winsys's description through `vulkaninfo --json`
(2026-09-27). Upstream reports 22 extensions and 40 features the port does
not, and four more queue families. Everything else the CTS reports as not
supported, upstream reports the same way.

main-1 ended on 2026-09-27 with 2,786,062 cases: 1,098,388 pass, 43 quality
warnings, 1,675,626 not supported, and 12,005 that did not pass (11,909
failures, 66 crashes, 26 lost devices, 4 resource errors).

## Failures

final-targets-1 (2026-09-28, ps5-port b381f60, debug archive) reran every
case main-1 or merged-1 did not pass, 12,085 of them: 1,750 pass, 10,326 are
not supported with a reason below (fragment barycentrics 4,856, fragment
shading rate 4,741, device-generated commands 725, performance queries 4),
no crash and no lost device. What remained were the eight sparse descriptor
buffer cases at 32 buffers, which time out in the debug build's NIR
validation, and dEQP-VK.info.device_mandatory_features, which failed because
that build reported mesh shaders without task shaders (fixed in b0a175c).
final-targets-rel-1, those nine on the release archive at b0a175c: 9 pass.
The table below is how each of main-1's failures got there.

Of main-1's 12,005, 1,435 pass in later runs (fixes made during main-1),
10,560 belong to features switched off during main-1 (variable-rate shading
4,701, fragment barycentrics 4,850, capture and replay addresses 1,010), and
the rest are below.

| Item | Cases | Status |
| --- | --- | --- |
| The switched-off features' cases | 10,560 | a targeted rerun on the merged driver must show them not supported |
| conditional_rendering.transform_feedback | 9 | fixed on ps5-gs-compute (b26797e): a geometry shader's push constants now reach its rasterization copy (gsc-pc-gate-1) |
| descriptor_indexing.*_minNonUniform, rasterization.culling.primitive_id | 7 | pass on 3057cb5 (triage-untriaged-1); they failed on builds from before the fixes made during main-1 |
| memory.map_placed | 5 | placed maps implemented on ps5-gaps (a2dc2fc); 8 more cases need memfd_create, now in the platform layer (SDK fork 71f2494), to be proved together |
| tessellation.geometry_interaction.limits | 2 | tessellation as compute with poly's tessellator, merged into ps5-port (ebaf6bc): s5-gate-1 passes them, and s5-regress-2 (every geometry shader as compute) and s5-default-1 run 13,455 cases each with no failure |
| descriptor_buffer.sparse_*_buffer.multiple.*buffers32* | 8 | not a sparse defect: the test's compute pipeline takes 7.9 s in spirv_to_nir's optimisation loop at 16 buffers, and four times that at 32, in the development build (assertions and NIR validation after every pass); a release archive (b_ndebug) passes all 8 (sparse-db-32-rel-1). The acceptance run uses the release archive |
| shader_object.misc.*.geometry_streams.enabled | 2 | compute passes built when the draw binds the objects, on ps5-gs-objects (a3fb747); console gate queued |
| descriptor_heap.basic.fragment.input_attachment | 1 | a CTS bug: the test's subpass dependency made nothing visible to the input attachment; the fix upstream made after 1.4.6.2 (c8ff9475c5) is in the CTS fork (4615d988e2) and the case passes |
| ray_tracing_pipeline (acceleration structures, builtin) | 5 | with ray tracing pipelines, below |

## Not supported: gaps the port caused

Upstream RADV offers these on Navi21; the port does not yet.

| Item | Cases | What closes it |
| --- | --- | --- |
| Queue families: one graphics family only (upstream adds four compute queues and a sparse family). Exclusive compute queue, compute-only statistics, multi-queue synchronization, concurrent sharing | 253,171 | A compute and transfer family of four queues whose submissions go to the graphics ring through sceAgcDriverSubmitDcb, as upstream's family looks but without concurrency, which Vulkan does not promise. Merged into ps5-port (506ec2f): queues-gate-1, 25,318 cases, 20,390 pass and no failure; the rest are the CTS's own or need a second graphics queue, as on desktop RADV. Real concurrency is in the backlog, below |
| Ray tracing: acceleration structures and ray queries | part of 116,323 | Reported on ps5-port (057d577, rq-full-1) |
| Ray tracing pipelines, maintenance1, position fetch, pipeline library group handles | rest of 116,323 | Reported on ps5-port (729a983, rtp-sample-1); callees' spills restored the scratch base 4 GiB low until 8b2a6d9 (rt-spill-1: every subgroups ray tracing case passes or is not supported). Group handle capture and replay reported since ecf916d: the shader arenas it places go in a range at the top of the shaders' window the port keeps for them (rt-replay-1: the 165 cases that need it pass) |
| Sparse binding and residency, sparse atomics, image2DViewOf3DSparse, aliased residency | 36,666 | Reported on ps5-port (8abff82, dfc3fcf, 7848a74); descriptor buffers in sparse ranges since 400560e, and no dedicated sparse queue family without native timelines since a6bdf1a. shaderResourceResidency is not reported: no exported function sets PRT bits |
| Mesh and task shaders | 59,923 | RADV's mesh path on GFX10.3 exports per-primitive attributes through the parameter cache, which this GPU does not have, and runs task shaders on an asynchronous compute queue with the CP's task and mesh dispatch packets, which the PS5 does not offer (HARDWARE_FINDINGS.md). Both merged into ps5-port and reported (179f88d): each primitive gets vertices of its own carrying its outputs flat, in parts of 256 vertices, the first part running the workgroup once and publishing its outputs to the others through a device ring (b381f60); indirect mesh draws go through ordinary indirect draws of records a compute pass writes; task shaders run on the graphics ring in chunks of as many task workgroups as the task rings hold at the pipeline's payload size: the task shader as a compute dispatch writing the rings as ordinary buffers, the records prepass turning their draw entries into the mesh workgroups' records, and their draw. The smoke title's mesh tickets and task payloads pass (100 of 100). taskmesh-1, every main-1 case naming mesh or task shaders (83,681): 23,057 pass, 12 quality warnings, no failure; its 4 descriptor heap crashes pass since 69d7d30 (task-heap-1). Not supported, as upstream on this GPU: mesh shader queries (24,672) and inherited conditional rendering |
| Capture and replay addresses (buffer device address, descriptor buffer and heap, acceleration structures) | about 1,000 | Reported on ps5-port (397a324; replay-2) |
| Memory types: no host-cached type, no non-device-local type | 19,368 + 9,126 + 2,650 | The coherence probe measured the CPU mapping cached and coherent both ways (HARDWARE_FINDINGS.md): the port describes an integrated GPU with host-cached types. Merged into ps5-port (20fe8ae): memtypes-gate-1, 50,014 cases, 44,993 pass, 8 quality warnings (map_placed: no /proc/self/maps to verify against) and no failure; 2,114 transient attachments ask for lazily allocated memory, which desktop RADV does not offer either |
| Calibrated timestamps, present timing | 1,299 | Reported on ps5-port (425b404, 53fed7f; ts-2) |
| External host memory (VK_EXT_external_memory_host) | 11 | Anonymous memory takes GPU access through sceKernelMprotect (the smoke title's host pointer check); merged with the memory types (20fe8ae) |
| Video (VK_KHR_video_*) | 11,149 | Not offered, with a reason (below) |
| Window system: no surface or swapchain for the CTS (headless) | part of 32,544 | The CTS fork's PS5 platform offers headless displays (971a27e); merged-1 measures RADV's headless surfaces. VK_KHR_display on VideoOut is on ps5-wsi: the smoke title presents 60 frames to the display, the last 50 in exactly 50 refresh periods, and replaces its swapchain; the CTS's display cases pass on the host model |
| The sparse-binding bit on the only queue family, with no sparse support | honesty | Removed on ps5-gaps (a2dc2fc) |
| conformanceVersion reports upstream's 1.4.5.3 | honesty | 0.0.0.0 on ps5-gaps (a2dc2fc) until the full run passes |

## Not supported: with a reason

No work, each reason recorded where it was measured.

- **Hardware** (the GPU's fixed-function blocks are GC 10.1.3's,
  HARDWARE_FINDINGS.md): variable-rate shading (96,530), fragment
  barycentrics (8,313), RGB9E5 as a colour target, accelerated dot products
  and VK_VALVE_shader_mixed_float_dot_product.
- **Platform**: device-generated commands (238; B8, command fetch in the
  system context), performance queries (13; no exported stable power state),
  Linux file descriptors, dma-buf and DRM (52,824), other window systems,
  Win32 and Fuchsia handles. Video (11,149): the exported decoder
  (libSceVideodec2, as ProsperoLight uses it) takes a whole access unit and
  returns a decoded frame, keeping its own reference pictures, where Vulkan
  Video is stateless, the application parsing the stream and naming every
  reference picture; RADV drives the video engine through its own ring, which
  no exported function reaches. Shader resource residency: no exported
  function sets the page table's PRT bits.
- **Not offered by RADV for GFX10.3 either**: formats and sample counts
  (464,417: ASTC, ETC2, D24S8 and others), other vendors' and newer
  generations' extensions (187,331: cooperative matrices and vectors, NV and
  ARM extensions, tile images, opacity micromaps, data graphs), inherited
  conditional rendering (482), advanced blend operations, fragment density
  maps, partitioned subgroups, multisampled render to single sampled, unified
  image layouts, protected memory, mesh shader queries.

## Backlog

Not needed to close a gap, and revisited later.

- **Concurrent compute queues.** The compute family runs on the graphics
  ring, in turn with graphics. Running it alongside needs AGC's asynchronous
  compute queues: sceAgcDriverSubmitAcb (the AnyPS5 emulator models a title's
  queues as 0x20 to 0x57) or a queue from sceAgcDriverCreateQueue, whose
  arguments are unknown. The console probe that would establish either was
  blocked by the auto-mode classifier on 2026-09-27 and needs my approval.
  Mesa keeps GFX1013's compute queue off for a threadgroup bug RADV already
  works around (has_async_compute_threadgroup_bug). Task shaders, which RADV
  runs on that queue, wait on it or on their own emulation on the graphics
  ring.

## Order

1. Merge ps5-rt, ps5-gs-compute (with b26797e), the GFX1013 traits and
   ps5-gaps (with memfd_create), then the targeted rerun: every main-1 case
   that did not pass, the whole transform_feedback group, and the groups the
   branches touch.
2. Ray tracing pipelines, the shader object streams, slice 5.
3. Compute queues (the largest gap), capture and replay, sparse, memory types,
   timestamps and host memory.
4. Mesh shaders, the headless WSI and the VideoOut swapchain, the video
   investigation.
5. The full CTS run, on the release archive (b_ndebug), which the titles
   ship.
