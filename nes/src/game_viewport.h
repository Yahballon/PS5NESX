// NESYX native picture sizes: display mode is independent of the emulated frame.
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <cmath>
#include <string_view>

namespace nes {
struct GameViewport {
    float x=0, y=0, width=0, height=0;
};
// Output sizes are Vulkan swapchain pixel dimensions; 16:9 fills all of it.
// Legacy 4:3 retains bars on wide displays. Integer uses unfiltered whole
// source-pixel multiples when possible, with downscaling only if required.
inline GameViewport CalcGameViewport(float w,float h,float sourceW,float sourceH,
                                    std::string_view aspect) {
    if(w<=0 || h<=0 || sourceW<=0 || sourceH<=0) return {};
    float width=w,height=h;
    if(aspect=="Integer") {
        const float fit=std::min(w/sourceW,h/sourceH);
        const float scale=fit>=1.0f?std::max(1.0f,std::floor(fit)):fit;
        width=sourceW*scale;
        height=sourceH*scale;
    } else if(aspect!="16:9") {
        width=std::min(w,h*4.0f/3.0f);
        height=width*3.0f/4.0f;
    }
    return {(w-width)*0.5f,(h-height)*0.5f,width,height};
}
} // namespace nes
