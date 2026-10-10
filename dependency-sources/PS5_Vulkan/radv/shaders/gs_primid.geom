#version 450
// PS5 Vulkan - RADV smoke test: point 0 becomes a strip of 10 vertices and
// every other point one of 100, chosen from gl_PrimitiveIDIn.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(points) in;
layout(triangle_strip, max_vertices = 100) out;
void main()
{
    const int count = gl_PrimitiveIDIn == 0 ? 10 : 100;
    const float step = 2.0 / float(count / 2 - 1);
    for (int i = 0; i < count / 2; i++) {
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.0, 0.0, 0.0);
        EmitVertex();
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.5, 0.0, 0.0);
        EmitVertex();
    }
}
