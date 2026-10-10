#version 450
// PS5 Vulkan - RADV smoke test: test_triangle's triangle, each vertex naming
// itself (its index plus one) in an output the fragment shader reads per
// vertex; with the specialisation constant set its last two corners swap, so
// it winds the other way.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(constant_id = 0) const bool other_winding = false;
layout(location = 0) out uint vertex_id;
void main()
{
    const vec2 corners[3] = vec2[](vec2(-1.0, -1.0), vec2(0.0, -1.0), vec2(-1.0, 1.0));
    const int corner = other_winding && gl_VertexIndex > 0 ? 3 - gl_VertexIndex : gl_VertexIndex;
    gl_Position = vec4(corners[corner], 0.0, 1.0);
    vertex_id = uint(gl_VertexIndex) + 1u;
}
