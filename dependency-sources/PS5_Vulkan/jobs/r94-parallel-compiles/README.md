# R94: pipelines compile on several threads at once

Every compile -- cache hits included -- ran under one global lock, which also
covered AGC's shader creation and linking. An emulator's asynchronous shader
compiler (Dolphin's ubershader and pipeline workers, PPSSPP's) therefore had its
threads take turns, and a draw that linked its pipeline waited behind whichever
compile held the lock: on the console, Dolphin's GPU thread spent 148 samples of
one 10 s window in that `mtx_lock`, behind compiles of 77-121 ms, with Rogue
Leader in Dolphin's Async (UberShaders) mode.

- **Compiles run side by side.** psbc's own state is a reference-counted
  initialisation under its mutex and options made once; NIR and ACO work in
  per-compile arenas, as RADV's parallel compiles do. A compile takes one of
  `PS5VK_PARALLEL_COMPILES` (6) slots, which bounds the memory concurrent
  compiles hold (each runs on its own 32 MiB stack), not their order.
- **AGC's calls take turns alone.** `sceAgcCreateShader` and `sceAgcLinkShaders`
  are not known to be reentrant, so they have a lock of their own, held for
  those calls only; a draw linking its pipeline never waits behind a compile.
- **The abort guard is per thread.** The compiler's aborts and traps were caught
  with process-wide handlers installed per compile and one global jump buffer.
  The handlers are now installed while any compile runs and restored when the
  last one ends; the jump buffer and the "compiling" flag are thread-local, and
  a signal on a thread that is not compiling goes to the handler the process had
  before.
- The shader cache's one-time directory setup, which relied on the old lock, is
  a `pthread_once`.

`driver/tests/vk_r94_parallel_compiles_test.c`: four threads create twenty-four
compute pipelines from two shaders at once; every one succeeds, and every
parallel compile's code is byte for byte the serial compile's (direct build). On
the PC the parallel batch ran at 0.4-0.6 ms a compile against 1.8-1.9 ms alone.
`tools/check-driver.sh` PASS.

On the console (RetroArch title 47dbc031, Dolphin with a GameCube game from boot, Async
UberShaders, 6x, 16x AF, GPU texture decoding, each driver starting from an empty
shader cache): the first 10 s window 82% against 77% on the previous driver
(title 870bd1bb), the worst frames 232/127/194 ms against 267/144/188 ms. The
remaining compiles on the GPU thread are Dolphin's own synchronous ubershader
pipelines, made when one it needs is not ready. The attract sequence's slow
stretches (73-85%) are the same with every shader cached: they are not
compilation but the driver's transfers done by the CPU at a submission split
(uploads into tiled images, image copies) and Dolphin's own emulation -- R95.
