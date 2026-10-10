// (AI-assisted) NES controller mapping and edge-triggered emulator shortcuts.
#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <string>
namespace nes {
struct ButtonDefinition {const char* key;const char* label;const char* fallback;unsigned nes_id;};
inline constexpr ButtonDefinition buttons[]={
    {"NES/ButtonA","NES A","Cross",8},{"NES/ButtonB","NES B","Circle",0},
    {"NES/ButtonStart","NES Start","Options",3},{"NES/ButtonSelect","NES Select","Touchpad/Create",2},
    {"NES/ButtonUp","NES Up","Up",4},{"NES/ButtonDown","NES Down","Down",5},
    {"NES/ButtonLeft","NES Left","Left",6},{"NES/ButtonRight","NES Right","Right",7}
};
struct Source {const char* name;const char* label;uint32_t mask;bool all;};
inline constexpr Source sources[]={
    {"None","None",0,false},{"Cross","Cross",0x4000,false},{"Circle","Circle",0x2000,false},
    {"Square","Square",0x8000,false},{"Triangle","Triangle",0x1000,false},
    {"Options","Options",8,false},{"Touchpad","Touchpad click",0x40100000,false},{"Create","Create",1,false},
    {"Touchpad/Create","Touchpad / Create",0x40100001,false},
    {"L1","L1",0x400,false},{"R1","R1",0x800,false},{"L2","L2",0x100,false},{"R2","R2",0x200,false},
    {"L3","L3",2,false},{"R3","R3",4,false},{"Up","D-pad Up",0x10,false},{"Down","D-pad Down",0x40,false},
    {"Left","D-pad Left",0x80,false},{"Right","D-pad Right",0x20,false},
    {"L3R3","L3 + R3",6,true},{"L1R1","L1 + R1",0xc00,true}
};
struct ShortcutDefinition {const char* name;const char* label;std::array<const char*,3> fallback;};
inline constexpr ShortcutDefinition shortcuts[]={
    {"Save","Save state",{"L3R3","Up","None"}},
    {"Load","Load state",{"L3R3","Down","None"}},
    {"Menu","Back to menu",{"L1","R1","Touchpad"}}
};
struct ControllerFrame {uint16_t joypad=0;bool save=false,load=false,menu=false;};
class ControllerBindings {
public:
    void Load(const std::map<std::string,std::string>& settings);
    ControllerFrame Update(uint32_t raw,double now);
    bool left_stick_dpad=true;
private:
    std::array<Source,8> mapping{};
    std::array<std::array<Source,3>,3> chords{};
    std::array<bool,3> previous{};
    bool initialized=false;
    double emergency_since=-1;
};
}
