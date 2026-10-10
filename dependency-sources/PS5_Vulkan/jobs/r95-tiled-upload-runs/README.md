# R95: uploads into tiled images, a run at a time

An upload into a tiled image (vkCmdCopyBufferToImage into an attachment) is
written by the CPU at a submission split point, and it placed every texel with
its own call to the image's map. Dolphin, decoding textures on the CPU, uploads
a full-screen 1.1 MiB texture sixty times a second in a GameCube game
(`cpu_copies=upload:600/675000` a 10 s window), and those per-texel addresses
were the largest single driver cost on its GPU thread.

The map keeps the bytes of a run contiguous (`ps5vk_copy_side_run_bytes`: 16
bytes for a colour map -- four 4-byte texels -- 8 for the one-byte map, two
texels of a depth map), so a run aligned to its size is one address and one
copy. A side whose level offset (`tile_xor`) touches the bits inside a run keeps
a texel at a time.

- `driver/tests/vk_r95_tiled_upload_test.c` uploads four regions -- the whole
  image, one from (3, 5), one texel, one across a tile's edge -- into 300x200
  attachment images of 1, 2, 4, 8 and 16-byte texels, and checks every texel of
  each at the offset the driver's own map gives (R91's
  `ps5vk_debug_image_texel_offset`) and that the texel past a region's edge is
  unchanged: 16 of 16. `tools/check-driver.sh` PASS.
- On the console (title db2f6363, the game from boot, Dolphin decoding on the
  CPU): the samples of the GPU thread in tiled uploads fell from 4,897 to 1,350
  over the same 200 s.

The game's speed did not move with it (the attract sequence still 71-87% for
stretches): with the uploads cheaper, the GPU thread waits more, not less. The
game runs with Dolphin's full MMU emulation ("MMU = True, strictly required" in
Dolphin's GameSettings/GSW.ini) and CPU culling, and in the slow stretches
Dolphin's two threads take turns waiting on each other; what is left there is
Dolphin's, not the driver's.

Moving the CPU's transfers to the GPU -- CP DMA for linear ones, which Dolphin's
GPU texture decoding produces (copies between two row-stored images) -- remains
the driver's larger lever for every core, and changes how submissions split, so
the golden comparisons move with it: its own round.
