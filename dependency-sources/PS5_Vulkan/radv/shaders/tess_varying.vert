#version 450
// PS5 Vulkan - RADV smoke test: the quad patch's corners as a generic output.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out vec2 corner;
void main()
{
    const vec2 corners[4] = vec2[](vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(1.0, 1.0), vec2(-1.0, 1.0));
    corner = corners[gl_VertexIndex];
}
