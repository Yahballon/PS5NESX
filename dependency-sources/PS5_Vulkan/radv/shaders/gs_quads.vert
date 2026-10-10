#version 450
// PS5 Vulkan - RADV smoke test: vertices 4q to 4q + 3 are the corners of a
// strip covering row 2q of four, for drawing triangle strips with restarts.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
void main()
{
    const int corner = gl_VertexIndex % 4;
    const float top = -1.0 + float(gl_VertexIndex / 4) * 1.0;
    gl_Position = vec4(corner < 2 ? -1.0 : 1.0, top + ((corner & 1) != 0 ? 0.5 : 0.0), 0.0, 1.0);
}
