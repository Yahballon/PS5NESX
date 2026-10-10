#version 450
// PS5 Vulkan - RADV smoke test: each point passes through, and its geometry
// shader invocation records the primitive and invocation IDs it was given.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(points) in;
layout(points, max_vertices = 1) out;
layout(std430, set = 0, binding = 0) buffer Record
{
    uint count;
    uint values[];
} record;
void main()
{
    const uint slot = atomicAdd(record.count, 1u);
    record.values[2u * slot] = uint(gl_PrimitiveIDIn);
    record.values[2u * slot + 1u] = uint(gl_InvocationID);
    gl_Position = gl_in[0].gl_Position;
    EmitVertex();
}
