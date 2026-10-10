#version 450
// PS5 Vulkan - RADV smoke test: a private array too large for registers, so
// the compiler keeps it in scratch memory, written and read at indices that
// depend on the texel. Its size is the specialisation constant (a power of
// two).
// Copyright (C) 2026 Mihawk-99
// SPDX-License-Identifier: GPL-3.0-or-later
layout(constant_id = 0) const int N = 256;
layout(location = 0) out vec4 colour;
void main()
{
    float a[N];
    int x = int(gl_FragCoord.x), y = int(gl_FragCoord.y);
    for (int i = 0; i < N; i++)
        a[(i * 3 + x) & (N - 1)] = float((i * 7 + x) & 15);
    int s = 0;
    for (int i = 0; i < N; i++)
        s += int(a[(i * 5 + y) & (N - 1)]);
    colour = vec4(float(s & 255) / 255.0, float((s >> 8) & 255) / 255.0, 0.0, 1.0);
}
