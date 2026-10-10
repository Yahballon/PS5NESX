#version 450
// PS5 Vulkan - RADV smoke test: the primitive ID no earlier stage writes, as
// a colour: even red, odd green.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) out vec4 colour;
void main()
{
    colour = (gl_PrimitiveID % 2 == 0) ? vec4(1.0, 0.0, 0.0, 1.0) : vec4(0.0, 1.0, 0.0, 1.0);
}
