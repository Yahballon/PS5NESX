#version 450
// PS5 Vulkan - RADV smoke test: a strip of 100 vertices per point, in the
// colour the vertex shader gave.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(points) in;
layout(triangle_strip, max_vertices = 100) out;
layout(location = 0) in vec4 colour_in[];
layout(location = 0) out vec4 colour_out;
void main()
{
    const float step = 2.0 / 49.0;
    for (int i = 0; i < 50; i++) {
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.0, 0.0, 0.0);
        colour_out = colour_in[0];
        EmitVertex();
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.5, 0.0, 0.0);
        colour_out = colour_in[0];
        EmitVertex();
    }
}
