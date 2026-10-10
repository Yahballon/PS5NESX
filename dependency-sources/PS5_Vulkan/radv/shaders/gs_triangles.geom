#version 450
// PS5 Vulkan - RADV smoke test: each triangle passes through.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;
void main()
{
    for (int i = 0; i < 3; i++) {
        gl_Position = gl_in[i].gl_Position;
        EmitVertex();
    }
}
