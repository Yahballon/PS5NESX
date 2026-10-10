#version 450
// PS5 Vulkan - RADV smoke test: the colour the previous stage gave.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) in vec4 colour_in;
layout(location = 0) out vec4 colour;
void main()
{
    colour = colour_in;
}
