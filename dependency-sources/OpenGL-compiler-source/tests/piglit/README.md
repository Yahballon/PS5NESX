# Focused Piglit coverage

This is a native PS5 adaptation layer, not a port of Piglit's desktop runner.
It pins upstream Piglit commit `db0cf385b514bc107d0c66810689fe39b74d4474`
and selects edge cases that complement the Khronos CTS and existing native
stress gates.

`egl_public_gl46_piglit.c` adapts
`tests/spec/arb_compute_shader/execution/basic-ssbo.shader_test`: six ordered
dispatches verify SSBO writes, atomic-counter observations, barriers, and the
final 256-word payload. `subset.tsv` maps the remaining selected Piglit cases
to the stronger native gates that already cover them.

Piglit source: <https://gitlab.freedesktop.org/mesa/piglit>

The adapted Piglit test logic retains Piglit's [standard MIT terms](LICENSE).
The PS5 harness remains GPL-3.0-or-later.
