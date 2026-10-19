// NESYX "PIXEL REACTOR": an original animated, texture-free boot scene.
// Built from signed-distance-field text and native UI quads; runs while the
// library is scanned asynchronously on the PS5, including remote NFS shares.
// No borrowed animation assets, videos, external files or shader changes.
#include "loading.h"
#include "ps5nes_build_version.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

namespace nes {
namespace {
constexpr float kTau = 6.28318530718f;
constexpr uint32_t Color(uint8_t r, uint8_t g, uint8_t b, uint8_t a=255) {
    return uint32_t(r) | (uint32_t(g)<<8) | (uint32_t(b)<<16) | (uint32_t(a)<<24);
}
// Stable, allocation-free pseudo-random points: same stars each frame.
uint32_t Hash(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7feb352dU;
    x ^= x >> 15;
    x *= 0x846ca68bU;
    return x ^ (x >> 16);
}
float Unit(uint32_t x) { return float(Hash(x) & 0xffffU) / 65535.0f; }
float Wave(float t) { return 0.5f + 0.5f * std::sin(t); }
float Saturate(float x) { return std::clamp(x, 0.0f, 1.0f); }
} // namespace

void BuildLoadingFrame(fe::FrameDesc& frame, const fe::Fonts& fonts, unsigned width,
                       unsigned height, const ScanProgress& progress, double elapsed, bool done) {
    frame=fe::FrameDesc{};
    if (!width || !height) return;
    const float W=float(width), H=float(height), k=H/2160.0f;
    const float t=static_cast<float>(elapsed);
    const float cx=W*0.5f, cy=H*0.427f;
    const float breathe=Wave(t*2.4f);
    // PS5 native background shader receives time and neon colors for a
    // subtle breathing purple/cyan backdrop behind the foreground geometry.
    const float top[4]={0.004f,0.009f,0.042f,1.f};
    const float mid[4]={0.027f,0.009f,0.087f,1.f};
    const float bottom[4]={0.004f,0.007f,0.028f,1.f};
    std::copy(top,top+4,frame.bg.top);
    std::copy(mid,mid+4,frame.bg.mid);
    std::copy(bottom,bottom+4,frame.bg.bottom);
    frame.bg.glow_color[0]=0.11f + 0.05f*breathe;
    frame.bg.glow_color[1]=0.37f;
    frame.bg.glow_color[2]=0.88f;
    frame.bg.glow_color[3]=0.42f;
    frame.bg.glow_pos[0]=0.48f;
    frame.bg.glow_pos[1]=0.44f;
    frame.bg.glow_pos[2]=0.62f;
    frame.bg.glow_pos[3]=0.48f;
    frame.bg.floor_glow[0]=0.89f;
    frame.bg.floor_glow[1]=0.11f;
    frame.bg.floor_glow[2]=1.f;
    frame.bg.floor_glow[3]=0.07f;
    frame.bg.misc[0]=W/H;
    frame.bg.misc[1]=0.87f;
    frame.bg.misc[2]=0.53f;
    frame.bg.misc[3]=t;
    frame.time=t;

    auto& ui=frame.ui;
    // Stay under ~2400 vertices so even a busy NFS scan remains responsive.
    ui.reserve(2100);
    const uint32_t cyan=Color(49,219,255),pink=Color(250,70,224);
    const uint32_t white=Color(245,248,255),muted=Color(165,182,225);
    auto rect=[&](float x,float y,float w,float h,float r,uint32_t color) {
        if (w>0 && h>0) fe::Fonts::AddRoundedRect(ui,x,y,w,h,r,color);
    };
    auto label=[&](const std::string& text,float x,float baseline,float sz,uint32_t color,
                   float bold=0.f,fe::Fonts::Align align=fe::Fonts::Left) {
        fonts.AddText(ui,text.c_str(),x,baseline,sz*k,color,bold,align);
    };

    // An animated starfield of small, discrete pixels, never a scrolling video.
    // Sparse larger stars add depth and twinkle using per-star phases.
    for (unsigned i=0;i<70;++i) {
        const float x=W*(0.035f+0.93f*Unit(i*37U+31U));
        const float y=H*(0.06f+0.77f*Unit(i*53U+907U));
        const float flicker=Wave(t*(0.7f+Unit(i+63U)*1.6f)+float(i)*2.1f);
        const float size=(i%13==0?7.f:3.2f)*k;
        const uint8_t a=uint8_t(28.f+95.f*flicker);
        rect(x,y,size,size,0,i%4==0?Color(240,64,241,a):Color(45,162,254,a));
    }
    // Wide, converging synth-grid rail accents connect to the existing shelf.
    const float floorTop=H*0.81f;
    for (int i=0;i<7;++i) {
        const float y=floorTop+(H-floorTop)*(float(i*i)/36.f);
        rect(0,y,W,1.3f*k,0,Color(81,67,223,28));
    }
    for (int i=-8;i<=8;++i) {
        const float px=cx+float(i)*W*0.19f;
        for (int s=0;s<11;++s) {
            const float q=float(s)/11.f, y=floorTop+(H-floorTop)*q;
            const float x=cx+(px-cx)*q;
            rect(x,y,1.3f*k,(H-floorTop)/11.f,0,i%2==0?Color(25,147,255,18):Color(238,54,215,15));
        }
    }
    // A top scanlight travels the width of the display, plus a paired accent.
    rect(0,0,W,5*k,0,Color(20,99,206,190));
    const float sweepX=std::fmod(t*450.f*k,W+520*k)-260*k;
    rect(sweepX,0,255*k,7*k,2*k,Color(34,229,255,230));
    rect(sweepX+180*k,0,125*k,7*k,2*k,Color(254,57,224,220));

    // Distinct NESYX identity and dynamically generated version. Content
    // remains visible from the very first frame, before ScanGames starts.
    rect(91*k,111*k,10*k,125*k,4*k,cyan);
    label("NESYX",136*k,200*k,103,white,0.74f);
    label(std::string("by YAHBALLON   /   v")+nes_build::kVersion,
          140*k,255*k,37,Color(175,190,247),0.18f);
    const float right=W-119*k;
    label("NEON BOOT SEQUENCE",right,157*k,33,Color(129,195,249),0.36f,fe::Fonts::Right);
    label(done?"SYSTEM ONLINE":"SCANNING LIBRARY",right,214*k,35,
          done?cyan:pink,0.40f,fe::Fonts::Right);

    // ORBIT A: segmented cyan/violet telemetry ring. Breathe and rotate in
    // opposite directions; the orbit is not tied to scan percentage.
    for (int i=0;i<60;++i) {
        const float a=kTau*float(i)/60.f+t*0.34f;
        const float r=(320.f+9.f*breathe)*k;
        const float x=cx+std::cos(a)*r;
        const float y=cy+std::sin(a)*r;
        const float flicker=Wave(t*1.2f+float(i)*0.33f);
        const int al=45+int(148.f*flicker);
        rect(x-5*k,y-9*k,10*k,18*k,2*k,
             i%5==0?Color(246,60,229,uint8_t(al)):Color(25,197,252,uint8_t(al)));
    }
    // ORBIT B: 40 smaller pixels orbit in the reverse direction. Brightness
    // fills based on real folder counts; unknown totals are indeterminate.
    const bool known=progress.sources_total!=0;
    const float ratio=done?1.f:(known?Saturate(float(progress.sources_done)/
                                             float(progress.sources_total)):0.f);
    for(int i=0;i<40;++i) {
        const float a=kTau*float(i)/40.f-t*0.52f;
        const float r=259*k;
        const float x=cx+std::cos(a)*r,y=cy+std::sin(a)*r;
        const bool lit=done||(known?float(i)/40.f<ratio:i%7==int(t*8)%7);
        rect(x-6*k,y-6*k,12*k,12*k,0,
             lit?Color(250,72,224,227):Color(84,75,188,58));
    }
    // Outer faint octagon formed from a small set of circuit nodes.
    for(int i=0;i<8;++i) {
        const float a=kTau*(float(i)+0.5f)/8.f;
        const float r=391*k;
        const float x=cx+std::cos(a)*r,y=cy+std::sin(a)*r;
        rect(x-11*k,y-11*k,22*k,22*k,3*k,
             i%2?Color(245,56,222,123):Color(52,198,255,130));
    }
    // Pixel trails float upward through the ring, with deterministic motion.
    for(unsigned i=0;i<25;++i) {
        const float phase=Unit(i*19U+71U);
        const float v=std::fmod(t*(0.1f+Unit(i+22U)*0.11f)+phase,1.f);
        const float x=cx+(Unit(i*79U+6U)*2.f-1.f)*230.f*k;
        const float y=cy+235*k-v*470*k;
        const uint8_t a=uint8_t(100.f*std::sin(kTau*v*0.5f));
        const float size=(4.f+6.f*Unit(i+91U))*k;
        rect(x,y,size,size,0,i%3==0?Color(250,70,224,a):Color(55,219,255,a));
    }

    // THE REACTOR: a cartridge-shaped silicon heart with a custom 7x9 pixel
    // glyph ("N" for NESYX). It pulses instead of using downloaded imagery.
    const float chipW=218*k,chipH=254*k;
    const float chipX=cx-chipW*0.5f,chipY=cy-chipH*0.5f;
    const uint8_t aura=uint8_t(43.f+40.f*breathe);
    rect(chipX-19*k,chipY-19*k,chipW+38*k,chipH+38*k,27*k,Color(18,214,255,aura));
    rect(chipX-8*k,chipY-8*k,chipW+16*k,chipH+16*k,20*k,Color(72,179,255,172));
    rect(chipX,chipY,chipW,chipH,17*k,Color(8,17,53,250));
    rect(chipX+19*k,chipY+17*k,chipW-38*k,8*k,3*k,Color(47,186,255,213));
    rect(chipX+19*k,chipY+chipH-26*k,chipW-38*k,8*k,3*k,Color(246,62,224,180));
    // 7 columns * 9 rows. Color shifts smoothly from cyan to pink across N.
    const float pxSize=19.f*k,gap=4.f*k;
    const float gx=cx-(7.f*pxSize+6.f*gap)*0.5f;
    const float gy=cy-(9.f*pxSize+8.f*gap)*0.5f;
    for(int row=0;row<9;++row) {
        const int diagonal=1+row*4/8;
        for(int col=0;col<7;++col) {
            const bool active=col==0||col==6||col==diagonal;
            if(!active)continue;
            const float v=float(row)/8.f;
            const uint8_t rr=uint8_t(40.f+201.f*v);
            const uint8_t gg=uint8_t(213.f-147.f*v);
            const uint8_t bb=uint8_t(255.f-24.f*v);
            const float scale=0.90f+0.10f*breathe;
            rect(gx+col*(pxSize+gap),gy+row*(pxSize+gap),pxSize*scale,pxSize*scale,
                 1*k,Color(rr,gg,bb,240));
        }
    }

    // Lower readout: clean typography, real scan counts, never a fake 0-100%.
    const float headlineY=H*0.702f;
    label(done?"LIBRARY ONLINE":"INITIALIZING CARTRIDGES",
          cx,headlineY/k,72,white,0.55f,fe::Fonts::Center);
    const std::string tally=std::to_string(progress.games)+" GAMES FOUND  /  "+
                            std::to_string(progress.entries)+" ENTRIES READ";
    label(tally,cx,headlineY/k+68,35,muted,0.20f,fe::Fonts::Center);
    const float barW=std::min(W-220*k,1550*k);
    const float bx=cx-barW*0.5f,by=H*0.779f;
    rect(bx,by,barW,15*k,7*k,Color(55,63,122,172));
    if(done || known) {
        if(ratio>0)
            rect(bx,by,barW*ratio,15*k,7*k,done?cyan:Color(55,196,255,238));
        if(!done && ratio>0.01f) {
            const float px=bx+barW*ratio;
            rect(px-15*k,by-4*k,30*k,23*k,6*k,Color(255,80,222,184));
        }
    } else {
        const float pos=Wave(t*2.8f);
        rect(bx+pos*(barW-250*k),by,250*k,15*k,6*k,cyan);
    }
    // Reading the actual directory makes network progress debuggable without
    // rendering an enormous NFS path across the whole display.
    std::string directory=progress.directory.empty()?"Detecting ROM sources...":progress.directory;
    if(directory.size()>88)directory="..."+directory.substr(directory.size()-85);
    label(directory,cx,H*0.825f/k,31,Color(167,180,226),0.08f,fe::Fonts::Center);
    const std::string folders="FOLDERS  "+std::to_string(progress.sources_done)+
                              " / "+std::to_string(progress.sources_total);
    label(folders,cx,H*0.883f/k,34,done?cyan:Color(182,144,238),0.32f,fe::Fonts::Center);

    // Original per-frame telemetry animation: a gently scrolling signal line.
    const float telemetryW=720*k,telemetryX=cx-telemetryW*0.5f,telemetryY=H*0.912f;
    for(int i=0;i<44;++i) {
        const float s=0.5f+0.5f*std::sin(float(i)*0.59f-t*5.7f);
        const float power=5.f+25.f*s*s;
        rect(telemetryX+i*(telemetryW/44.f),telemetryY-power*k,
             9*k,power*k,2*k,i%3==0?Color(244,65,223,113):Color(49,219,255,98));
    }
    label("NESYX  /  NATIVE 8-BIT ENGINE",W-107*k,H*0.966f/k,26,
          Color(109,139,192),0.22f,fe::Fonts::Right);
}
} // namespace nes
