#version 450
// PS5 Vulkan - RADV smoke test: point i at the left edge of row i of four.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
void main()
{
    gl_Position = vec4(-1.0, -1.0 + 0.5 * float(gl_VertexIndex), 0.0, 1.0);
}
