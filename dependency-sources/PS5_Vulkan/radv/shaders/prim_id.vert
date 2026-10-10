#version 450
// PS5 Vulkan - RADV smoke test: two triangles splitting the target, left and
// right (dEQP-VK.pipeline.*.misc.implicit_primitive_id's geometry).
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
void main()
{
    const vec2 corners[6] = vec2[](vec2(-3.0, -1.0), vec2(0.0, 3.0), vec2(0.0, -1.0),
                                   vec2(0.0, -1.0), vec2(3.0, -1.0), vec2(0.0, 3.0));
    gl_Position = vec4(corners[gl_VertexIndex], 0.0, 1.0);
}
