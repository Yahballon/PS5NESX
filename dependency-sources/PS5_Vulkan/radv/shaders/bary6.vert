#version 450
// PS5 Vulkan - RADV smoke test: two triangles over the whole target, the
// right-hand corners at w = 16 (dEQP-VK.fragment_shading_barycentric's
// triangle list), each vertex naming itself (its index plus one).
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out uint vertex_id;
void main()
{
    const vec4 corners[6] = vec4[](vec4(-1.0, -1.0, 0.0, 1.0), vec4(-1.0, 1.0, 0.0, 1.0),
                                   vec4(16.0, 16.0, 0.0, 16.0), vec4(16.0, 16.0, 0.0, 16.0),
                                   vec4(16.0, -16.0, 0.0, 16.0), vec4(-1.0, -1.0, 0.0, 1.0));
    gl_Position = corners[gl_VertexIndex];
    vertex_id = uint(gl_VertexIndex) + 1u;
}
