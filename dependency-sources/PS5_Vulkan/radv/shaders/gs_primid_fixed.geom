#version 450
// PS5 Vulkan - RADV smoke test: a strip of 100 vertices per point, whatever
// gl_PrimitiveIDIn is, which the shader still reads.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(points) in;
layout(triangle_strip, max_vertices = 100) out;
void main()
{
    if (gl_PrimitiveIDIn > 1000000)
        return;
    const float step = 2.0 / 49.0;
    for (int i = 0; i < 50; i++) {
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.0, 0.0, 0.0);
        EmitVertex();
        gl_Position = gl_in[0].gl_Position + vec4(float(i) * step, 0.5, 0.0, 0.0);
        EmitVertex();
    }
}
