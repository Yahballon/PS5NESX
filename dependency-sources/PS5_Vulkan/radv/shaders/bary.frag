#version 450
#extension GL_EXT_fragment_shader_barycentric : require
// PS5 Vulkan - RADV smoke test: the three vertices' values of an input read
// per vertex (VK_KHR_fragment_shader_barycentric), as the red, green and blue
// bytes.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(location = 0) pervertexEXT in uint vertex_id[];
layout(location = 0) out vec4 colour;
void main()
{
    colour = vec4(float(vertex_id[0]), float(vertex_id[1]), float(vertex_id[2]), 255.0) / 255.0;
}
