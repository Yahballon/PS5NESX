#version 450
// PS5 Vulkan - RADV smoke test: the four corners of the whole target, as the
// control points of one quad patch.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
void main()
{
    const vec2 corners[4] = vec2[](vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(1.0, 1.0), vec2(-1.0, 1.0));
    gl_Position = vec4(corners[gl_VertexIndex], 0.0, 1.0);
}
