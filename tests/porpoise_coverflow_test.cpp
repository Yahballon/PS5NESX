#include "fe_coverflow_layout.h"
#include <cassert>
#include <cmath>
#include <iostream>

static float x_of(const fe::Mat4& m) { return (m * fe::Vec4(0,0,0,1)).x; }
static float y_of(const fe::Mat4& m, float y) { return (m * fe::Vec4(0,y,0,1)).y; }

int main()
{
    using namespace fe;
    const auto center = PorpoiseCoverflowPose(0,0);
    const auto left = PorpoiseCoverflowPose(-1,0);
    const auto right = PorpoiseCoverflowPose(1,0);
    const auto far = PorpoiseCoverflowPose(3,0);
    assert(center.scale > left.scale && left.scale > far.scale);
    assert(std::fabs(x_of(left.model) + x_of(right.model)) < 0.0001f);
    assert(far.brightness < right.brightness);
    assert(std::fabs(left.model.m[8] * right.model.m[8]) < 0.06f);
    assert(left.model.m[8] * right.model.m[8] < 0.0f);
    for(float d=-6;d<=6;d+=0.025f) {
        const auto pose=PorpoiseCoverflowPose(d,1.0f);
        const float floor=y_of(pose.model,-kClassicCaseHalfHeight);
        assert(std::fabs(floor + kClassicCaseHalfHeight) <= 0.041f);
        assert(std::isfinite(pose.scale) && pose.scale > 0.0f);
        if(d<5.99f) {
            const auto next=PorpoiseCoverflowPose(d+0.001f,1.0f);
            assert(std::fabs(x_of(pose.model)-x_of(next.model)) < 0.012f);
            assert(std::fabs(pose.scale-next.scale) < 0.004f);
        }
    }
    std::cout << "PASS: Porpoise-inspired 3D layout, floor and scrolling\n";
}
