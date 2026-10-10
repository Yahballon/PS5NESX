# Geometry shaders the hardware cannot run (RADV, route B)

_Design, 2026-09-27. Slices 1 to 3 and the pipeline library half of slice 4
done on the Mesa fork's branch ps5-gs-compute (f300ac5); open items at the
end._

## Why

A geometry shader on this GPU always runs as NGG: a legacy GS needs rings
whose registers AGC owns and no exported function sets
(HARDWARE_FINDINGS.md, 2026-09-26 and 2026-09-27). NGG covers every GS but two
kinds, and both are part of what I report:

1. **Transform feedback from a GS.** NGG streamout before GFX11 orders its
   buffer writes with GDS ordered counts, which a title cannot reach. Every
   dEQP-VK.transform_feedback case that captures from a GS fails (run xfb-1);
   capture from a vertex or tessellation evaluation shader passes, through
   legacy hardware VS streamout.
2. **A tessellated GS amplifying past 256 vertices** (4 invocations of 256
   vertices, or 32 invocations: Vulkan's minimum limits). One NGG subgroup
   holds 256 output vertices, and the per-instance mode that splits a
   primitive's invocations across subgroups hangs with tessellation on
   GFX10-class hardware (dEQP-VK.tessellation.geometry_interaction.limits).

Not reporting transform feedback, tessellation or geometry shaders would be
conformant too, but each is real on this GPU in every other case, and Eden
(the Switch emulator, a later target) uses all three.

## How

Run exactly those pipelines' pre-rasterization stages as compute, the way
Mesa's Asahi driver runs every GS (its hardware has none), with the shared
lowering in `src/poly` (also KosmicKrisp's):

- the vertex stage, or VS, TCS, the tessellator and TES for case 2, as
  compute writing their outputs to memory (`poly_nir_lower_vs_before_gs`,
  `poly_nir_lower_tcs`/`tes`, poly's software tessellator);
- a count pass when the GS's output count is not static, which keeps the
  GS's memory side effects so that they happen once (with static counts the
  GS proper keeps them instead);
- a prefix sum over the counts, which gives each input primitive its place
  in the transform feedback buffers and the index buffer in API order;
- the GS proper, writing transform feedback and the vertices to rasterize;
- an indexed indirect draw with a pass-through vertex shader reading them.

Every other pipeline keeps the hardware path. Queries (primitives generated,
transform feedback, pipeline statistics) take their counts from the compute
passes.

## Build

poly's kernels are OpenCL C compiled at build time by `mesa_clc` and
`vtn_bindgen2`, host tools built from the same Mesa revision (the host's LLVM
and Clang 22, libclc, the SPIR-V LLVM translator and SPIRV-Tools; a native
build of the two tools takes about 30 s). The PS5 cross build then uses them
with `-Dmesa-clc=system` and builds poly for RADV. Checked: the fork's poly
kernels compile to SPIR-V and bind with those tools (2026-09-27).

## Shape in RADV

Follow poly's model whole, as Asahi does: the vertex stage runs as a compute
dispatch over the unrolled vertex stream (poly's GS reads its inputs by
position in that stream, which a hardware VS, seeing only index values, cannot
give), then the GS count pass, the prefix sum, the pre-GS setup and the GS
proper as compute, all fed the graphics state's descriptors, push constants
and vertex buffers. The pipeline's hardware vertex stage becomes poly's
rasterization copy shader, reading the GS output, with the application's
fragment shader. Direct draws size poly's parameter blocks and buffers on the
CPU from the command buffer's upload pool; indirect draws use a GPU heap and
a setup kernel.

Built in vertical slices, each proved on the console before the next:

1. A VS and GS pipeline, direct non-indexed draws, forced through compute by
   a debug switch and checked by the smoke title's geometry checks (known
   answers from the NGG path).
2. Indexed, instanced and indirect draws; primitive restart.
3. Transform feedback and its queries (the target).
4. Graphics pipeline libraries and shader objects.
5. Tessellation, with poly's tessellator.

## Order of work

1. Host tools script, pinned like tools/build-radv.sh; poly enabled in the
   PS5 cross build.
2. Case 1 for a VS feeding a GS (the bulk of the failing cases).
3. Case 2 and case 1 behind tessellation, with poly's tessellator.
4. Queries and pipeline statistics; the transform_feedback, geometry and
   tessellation groups whole on the console.

## Slice 1 (2026-09-27)

Done: VS and GS pipelines, vkCmdDraw and vkCmdDrawIndexed, behind
`RADV_PS5_GS_COMPUTE=1`. Each draw dispatches the vertex shader, the count
pass and the GS proper with the graphics descriptor sets, push constants and
vertex buffers, then draws poly's output through the rasterization copy. The
smoke title passes 61 of 61 on the console with every GS forced through this
path: strips with a count chosen per primitive, early return, varyings,
primitive IDs, and a GS recording its invocations in a storage buffer.

Found on the way:

- RADV's dynamic topology holds the hardware primitive type, not the Vulkan
  enum; poly needs the latter.
- Invocations past poly's grid fault the GPU: every pass but the pre-GS setup
  checks its grid.
- With static counts poly makes no count pass and stripped the GS's memory
  writes from the GS proper, the only full run left. The fork's poly strips
  them only when a count pass keeps them (fde2cc2).

## Slice 2 (2026-09-27)

Every draw command handles such a pipeline. Multi-draws run one draw each.
A draw whose counts live in memory (indirect, indirect count, byte count)
is sized on the GPU by a meta pass: it reads the arguments, writes poly's
vertex and geometry parameters, allocates the vertex outputs, counts and
output indices from a heap each command buffer owns, and writes the
workgroup counts of the indirect dispatches that follow; the rasterization
copy draws indirectly. An indexed draw with primitive restart is first
unrolled on the GPU into an indexed draw of the decomposed list topology. A
draw too large for 32-bit counts or for the heap draws nothing rather than
write out of bounds. These passes are RADV's own OpenCL
(`src/amd/vulkan/cl/radv_gs_compute.cl`), turned into NIR builder functions
the way poly's are.

The smoke title's draw checks (indexed with a vertex offset, indexed
indirect, indirect, indirect count, restart direct and indirect) pass on the
NGG path and with every geometry shader forced through compute: 73 of 73.

## Slice 3 (2026-09-27)

A geometry shader with transform feedback outputs now always runs as
compute. Its draws continue from the offsets hardware streamout holds: they
go to memory, poly's pre-GS pass places each draw's output after a prefix sum
of the counts and advances them, the GS proper writes the buffers, and the
offsets go back to the hardware before the next draw, so hardware and
compute capture mix freely within one transform feedback. The rasterization
copy draws with streamout suspended and no shader query counting.

Primitives generated and written per stream count into memory counters each
command buffer owns. Transform feedback and primitives generated query
pools grow by a pair of snapshots of those counters, taken after the
hardware's at the beginning and the end, and their results add them in.

On the console, the 6685-case transform_feedback sample of run xfb-1 goes
from 1291 passing and 4529 failing to 5818 passing and 2 failing (run
xfb-gsc-3; both failures use graphics pipeline libraries, which slice 4
routes). Nothing that passed fails.

## Slice 4, pipeline libraries (2026-09-27)

A pre-rasterization library is compiled without the vertex input state, so
its transform feedback geometry shader cannot run as compute there. Such a
library keeps its shaders, and a pipeline fast-linked from it compiles its
vertex and geometry shaders again with the whole state while importing the
other libraries' binaries. Every sampled transform_feedback simple_fast_gpl
and simple_optimized_gpl case now passes or is not supported, and the
sampled pipeline_library and fast_linked_library cases with a geometry
shader are unchanged (run gsc-regress-1: 8885 cases, 6870 pass, 2013 not
supported, 2 quality warnings the pinned driver gives too, run
qw-baseline-1).

## Push constants in the rasterization copy (2026-09-27)

The nine conditional_rendering.transform_feedback cases captured nothing on
any stream. They were not about conditional rendering: with the passes forced
to run unpredicated (a debug switch, run condxfb-nopred-2), the first draw
captured nothing either. A one-shot capture of each draw's parameters
(run on the console, then removed) showed the passes right: pre-GS sized
stream 1 at 6 vertices and advanced its buffer by 24 bytes. The capture
itself happens in the rasterization copy, which runs the geometry shader
again for each output vertex, and that copy is the vertex stage's shader.
The test's geometry shader picks its stream from a push constant pushed for
the geometry stage alone, and RADV emits a stage's constants to that stage's
shader: with no hardware geometry shader, they went nowhere, and the copy kept
the values from when the pipeline was bound (stream 0). Geometry-stage
constants now go to the vertex stage too while such a pipeline is bound
(PS5_Mesa ps5-gs-compute b26797e). Run gsc-pc-gate-1: the 9 pass, and the
8,885 cases of gsc-regress-1 are unchanged.

## Slice 5, tessellation (2026-09-27)

A tessellated geometry shader amplifying past one NGG subgroup, or one with
transform feedback, now runs its tessellation as compute too, the way Asahi
does with poly (Mesa fork ps5-gs-tess):

- a setup pass sizes the draw's patches (whole patches only) and allocates,
  from the command buffer's heap, the vertex outputs, the control shader's
  outputs and the tessellator's per-patch buffers;
- the vertex shader, then the control shader (one workgroup per patch,
  `poly_nir_lower_tcs`) run as compute;
- poly's tessellator (the D3D11 reference tessellator) counts each patch's
  indices, a prefix sum places them and allocates the index buffer, and it
  writes them with the domain points;
- the evaluation shader (`poly_nir_lower_tes`) is the vertex stage of the
  geometry shader's passes, over a draw of the tessellator's output.

Shader objects take the same route: tessellation control and evaluation
objects keep their passes and the part of the tessellation state their stage
fixes, and a draw that binds them with such a geometry object assembles
them. With multiview, the passes run once per view with the view in their
draw block, and each view rasterizes alone.

Three things came up on the way. vtn_bindgen2 lowered every indirect access
of a large scratch array to an if-else tree, which took the quad tessellator
from 6,764 instructions to about three million and the generated bindings
past a gigabyte: only arrays of up to 16 elements get trees now. poly's heap
allocations abort when the heap is full, which RADV's shaders cannot:
`POLY_HEAP_GUARD` gives such an allocation a guard behind the heap, and the
draw draws nothing. And a GS reading gl_ViewIndex in a pass had no view to
read.

s5-gate-1 (tessellation.geometry_interaction whole and the shader object
stream cases): 24 pass, 2 not supported (extendedDynamicState3RasterizationStream,
which upstream RADV does not report here either). The two
tessellation.geometry_interaction.limits cases that lost the device pass.

With every geometry shader forced through compute (RADV_PS5_GS_COMPUTE=1),
the geometry, tessellation and transform feedback groups (13,455 cases,
s5-regress-1) failed 7, all in the rasterization copy's draw:

- RADV drops gl_PointSize from the last stage when the pipeline's topology is
  static and not points; the copy draws the geometry shader's points whatever
  the application's topology, so points rendered one pixel wide. The copy's
  topology decides now.
- poly matches strips that are each one primitive long to a list, and the
  copy's draw took every mode but points and line strips for a triangle
  strip: those lists were drawn as strips, bridging each primitive into the
  next and onto its neighbour's layer or primitive ID. Each output mode has
  its hardware topology now.

s5-regress-2 (forced) and s5-default-1 (the default path): 11,721 pass, no
failure. Merged into ps5-port (ebaf6bc).

## Open

- **Shader objects** and **dynamic vertex input**: done on ps5-gs-objects
  (the vertex pass compiled at the draw for its vertex input), merged.
- **Pipeline statistics** during these draws: the compute passes count as
  compute invocations, and the geometry shader's invocations and primitives
  go to a sink.
- **Slice 5**: done on ps5-gs-tess, above. A geometry shader's
  gl_PrimitiveIDIn after tessellation counts the tessellator's primitives
  across the draw's instances, where Vulkan resets it per instance.
- Merged into ps5-port (ebaf6bc) with the forced and default regressions
  above.

