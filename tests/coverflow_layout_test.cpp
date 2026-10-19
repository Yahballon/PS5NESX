// No Vulkan SDK required: run with a normal host C++20 compiler.
#include "fe_coverflow_layout.h"
#include <cassert>
#include <cmath>
#include <iostream>

namespace
{
float world_x(const fe::Mat4& m)
{
    return (m * fe::Vec4(0, 0, 0, 1)).x;
}
float world_y(const fe::Mat4& m, float local_y)
{
    return (m * fe::Vec4(0, local_y, 0, 1)).y;
}
}
int main()
{
    using namespace fe;
    const auto picked = ClassicCoverflowPose(0.0f, 0.0f);
    const auto left = ClassicCoverflowPose(-1.0f, 0.0f);
    const auto right = ClassicCoverflowPose(1.0f, 0.0f);
    const auto distant = ClassicCoverflowPose(4.0f, 0.0f);
    assert(std::fabs(picked.scale - 1.28f) < 0.0001f);
    assert(picked.scale > right.scale && right.scale > distant.scale);
    assert(left.model.m[8] * right.model.m[8] < 0.0f);
    assert(std::fabs(world_x(left.model) + world_x(right.model)) < 0.0001f);
    assert(world_x(distant.model) > world_x(right.model));
    assert(picked.brightness > right.brightness && right.brightness > distant.brightness);
    for (float d = -7.0f; d <= 7.0f; d += 0.07f)
    {
        const auto p = ClassicCoverflowPose(d, 4.2f);
        const float floor = world_y(p.model, -kClassicCaseHalfHeight);
        assert(floor >= -kClassicCaseHalfHeight - 0.0001f);
        assert(floor <= -kClassicCaseHalfHeight + 0.041f);
        assert(std::isfinite(p.scale) && std::isfinite(p.brightness));
        assert(p.brightness >= 0.56f && p.brightness <= 1.0f);
    }
    for (float d = -2.0f; d < 2.0f; d += 0.01f)
    {
        const auto a = ClassicCoverflowPose(d, 0.0f);
        const auto b = ClassicCoverflowPose(d + 0.001f, 0.0f);
        assert(std::fabs(world_x(a.model) - world_x(b.model)) < 0.015f);
        assert(std::fabs(a.scale - b.scale) < 0.004f);
    }
    std::cout << "PASS: ClassicCoverflowPose geometry, animation, reflected floor\n";
}
