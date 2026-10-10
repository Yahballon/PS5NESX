#version 450
// PS5 Vulkan - RADV smoke test: generic control points pass through, at the
// tessellation level the specialisation constant gives.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(vertices = 4) out;
layout(constant_id = 0) const float level = 2.0;
layout(location = 0) in vec2 corner_in[];
layout(location = 0) out vec2 corner_out[];
void main()
{
    corner_out[gl_InvocationID] = corner_in[gl_InvocationID];
    gl_TessLevelInner[0] = level;
    gl_TessLevelInner[1] = level;
    gl_TessLevelOuter[0] = level;
    gl_TessLevelOuter[1] = level;
    gl_TessLevelOuter[2] = level;
    gl_TessLevelOuter[3] = level;
}
