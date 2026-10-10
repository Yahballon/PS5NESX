#version 460
/*
 * PS5 Vulkan - RADV smoke test: a per-primitive colour from a mesh shader.
 * Copyright (C) 2026 Mihawk-99
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#extension GL_EXT_mesh_shader : require

layout(location = 0) perprimitiveEXT in vec4 colour;
layout(location = 0) out vec4 result;

void main()
{
    result = colour;
}
