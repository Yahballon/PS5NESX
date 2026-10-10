# R93: the device's tracked lists under a lock, and an output that is really 120 Hz

A tester's trace (the RetroArch title's PHASE_LOG, 2026-09-26, build ad98b960)
had two driver-side failures.

- **vkDestroyBuffer crashed twice in PPSSPP**, once from the frontend's menu
  freeing its font buffer and once from the core, each reading a `next` field
  of 0x2 and 0x80 while walking the device's list of live buffers. The device
  keeps three lists for the runner's capture -- live buffers, command-buffer
  table chunks, pipelines with stage mappings -- and changed them with no lock,
  while Vulkan lets an application create and destroy those objects from any
  thread without synchronising the device. Two threads' changes lost a link and
  a later walk followed a freed object's reused memory.

  The lists are Mesa `list_head`s now, removal is O(1) instead of a walk, and
  every change and every walk holds the device's `tracked_lock`
  (driver/ps5vk_private.h). `driver/tests/vk_r93_threads_test.c` has four
  threads create, bind and destroy 4,000 buffers each on one device, then checks
  the device lists exactly the 64 still alive and none after they go. On the
  unlocked driver the test never finished: three worker threads spun at full
  CPU for ten minutes, walking a list that had become a cycle, while the main
  thread waited to join them. On this driver it passes loader, direct and PS5
  link, and a watchdog now fails it instead of hanging.

- **Every core ran at exactly half speed with V-Sync on.** The trace's audio
  windows played 240,000 of every 480,000 frames with V-Sync on and all of them
  with it off, and each swapchain handover came 15-17 ms after the previous
  present where mine mostly come within 8 ms: the console had accepted 119.88 Hz and
  its display was refreshing at 60 Hz, so RetroArch, told 119.88 Hz, showed
  each frame twice at 60 Hz. The driver now times six vblanks after it
  configures the high-frame-rate output (the median of six intervals, the first
  wait only finding the phase) and restores 59.94 Hz when a vblank comes more
  than 12.5 ms apart, halfway between the two periods R92 measured, before any
  mode is reported. The trace line says which: on my console
  `119.88 Hz selected, a vblank every 8.345 ms` (8.341 and 8.347 in later
  runs). The fallback itself has not run on a display that stays at 60 Hz yet:
  that needs the tester's console, or my display's 120 Hz output turned off,
  which is a setting of the console I leave alone.

The battery (regression/queue.txt, PID 290) reruns R90's cases with R90's and
R91's own: 31 of 31 pass (regression/readback.txt). `tools/check-driver.sh`
passes with the new test (181 checks).
