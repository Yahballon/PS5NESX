#version 450
// PS5 Vulkan - RADV smoke test: the triangle is red.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out vec4 colour;
void main()
{
    colour = vec4(1.0, 0.0, 0.0, 1.0);
}
