#include "game_viewport.h"
#include <cassert>
#include <cmath>
#include <iostream>
using nes::CalcGameViewport;
static bool close(float a,float b) {return std::fabs(a-b)<0.01f;}
int main(){
    for(const auto& [w,h]:{std::pair{1920.f,1080.f},{3840.f,2160.f}}){
        auto full=CalcGameViewport(w,h,256,240,"16:9");
        assert(close(full.x,0)&&close(full.y,0)&&close(full.width,w)&&close(full.height,h));
        auto classic=CalcGameViewport(w,h,256,240,"4:3");
        assert(classic.x>0&&close(classic.width,h*4.0f/3.0f)&&close(classic.height,h));
        auto integer=CalcGameViewport(w,h,256,240,"Integer");
        assert(integer.x>=0&&integer.y>=0&&integer.width<=w&&integer.height<=h);
        assert(close(integer.width/256,std::floor(integer.width/256)));
        assert(close(integer.height/240,std::floor(integer.height/240)));
        // HDPack frames are allowed to render fullscreen as well.
        auto hd=CalcGameViewport(w,h,2048,1920,"16:9");
        assert(close(hd.width,w)&&close(hd.height,h)&&close(hd.x,0));
    }
    // Safe fractional downscale only for oversized source images.
    auto down=CalcGameViewport(1280,720,2560,2400,"Integer");
    assert(down.width<=1280&&down.height<=720);
    std::cout<<"PASS NESYX fullscreen fills the entire output; legacy 4:3 and integer still work\n";
}
