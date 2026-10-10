#version 450
// PS5 Vulkan - RADV smoke test: positions from the control points the
// control shader wrote, covering the whole target.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(quads, equal_spacing, ccw) in;
void main()
{
    const vec4 bottom = mix(gl_in[0].gl_Position, gl_in[1].gl_Position, gl_TessCoord.x);
    const vec4 top = mix(gl_in[3].gl_Position, gl_in[2].gl_Position, gl_TessCoord.x);
    gl_Position = mix(bottom, top, gl_TessCoord.y);
}
