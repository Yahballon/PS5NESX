#version 450
// PS5 Vulkan - RADV smoke test (diagnostic): the primitive ID's low 16 bits
// as red and green, blue 1.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out vec4 colour;
void main()
{
    uint id = uint(gl_PrimitiveID);
    colour = vec4(float(id & 255u) / 255.0, float((id >> 8) & 255u) / 255.0, 1.0, 1.0);
}
