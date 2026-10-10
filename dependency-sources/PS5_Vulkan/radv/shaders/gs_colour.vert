#version 450
// PS5 Vulkan - RADV smoke test: point i at the left edge of row i of four,
// with a colour for the geometry shader to pass on.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out vec4 colour;
void main()
{
    gl_Position = vec4(-1.0, -1.0 + 0.5 * float(gl_VertexIndex), 0.0, 1.0);
    colour = vec4(1.0, 0.0, 0.0, 1.0);
}
