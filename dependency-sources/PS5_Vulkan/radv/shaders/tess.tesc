#version 450
// PS5 Vulkan - RADV smoke test: the patch passes through, tessellated in two
// by two.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(vertices = 4) out;
void main()
{
    gl_out[gl_InvocationID].gl_Position = gl_in[gl_InvocationID].gl_Position;
    if (gl_InvocationID == 0) {
        gl_TessLevelInner[0] = 2.0;
        gl_TessLevelInner[1] = 2.0;
        gl_TessLevelOuter[0] = 2.0;
        gl_TessLevelOuter[1] = 2.0;
        gl_TessLevelOuter[2] = 2.0;
        gl_TessLevelOuter[3] = 2.0;
    }
}
