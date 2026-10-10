#version 450
// PS5 Vulkan - RADV smoke test: each point becomes a strip of 128 vertices
// across its row, a quarter of the target high.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(points) in;
layout(triangle_strip, max_vertices = 128) out;
void main()
{
    const float step = 2.0 / float(128 / 2 - 1);
    for (int i = 0; i < 128 / 2; i++) {
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.0, 0.0, 0.0);
        EmitVertex();
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.5, 0.0, 0.0);
        EmitVertex();
    }
}
