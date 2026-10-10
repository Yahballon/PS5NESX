#version 450
// PS5 Vulkan - RADV smoke test: positions from generic control points, and a
// colour for the fragment shader.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(quads, equal_spacing, ccw) in;
layout(location = 0) in vec2 corner[];
layout(location = 0) out vec4 colour;
void main()
{
    const vec2 bottom = mix(corner[0], corner[1], gl_TessCoord.x);
    const vec2 top = mix(corner[3], corner[2], gl_TessCoord.x);
    gl_Position = vec4(mix(bottom, top, gl_TessCoord.y), 0.0, 1.0);
    colour = vec4(1.0, 0.0, 0.0, 1.0);
}
