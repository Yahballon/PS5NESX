#version 450
// PS5 Vulkan - RADV smoke test: positions from the tessellation coordinates
// alone, covering the whole target.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(quads, equal_spacing, ccw) in;
void main()
{
    gl_Position = vec4(gl_TessCoord.xy * 2.0 - 1.0, 0.0, 1.0);
}
