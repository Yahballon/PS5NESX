#version 450
#extension GL_EXT_fragment_shading_rate : require
// PS5 Vulkan - RADV smoke test: counts its invocations and records the
// shading rates they report, so a coarse rate shows as fewer invocations.
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(set = 0, binding = 0, std430) buffer Counts
{
    uint invocations;
    uint rates;
};
layout(location = 0) out vec4 colour;
void main()
{
    atomicAdd(invocations, 1u);
    atomicOr(rates, 1u << uint(gl_ShadingRateEXT));
    colour = vec4(1.0, 0.0, 0.0, 1.0);
}
