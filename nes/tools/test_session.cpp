// (AI-assisted) Integration test with an original, generated NROM fixture (no commercial ROMs).
#include "core_session.h"
#include "games.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <filesystem>
int main(int argc,char** argv) {
    assert(argc==3);
    std::vector<uint8_t> raw, zipped;std::string error;
    assert(nes::ReadRom(std::string(argv[1])+"/input.nes",raw,error));
    assert(nes::ReadRom(std::string(argv[1])+"/input.zip",zipped,error));
    assert(raw==zipped);
    assert(!nes::ReadRom(std::string(argv[1])+"/bad.zip",zipped,error));
    assert(zipped.empty());
    assert(!nes::ReadRom(std::string(argv[1])+"/multiple.zip",zipped,error));
    assert(!nes::ReadRom(std::string(argv[1])+"/corrupt.zip",zipped,error));
    auto list=nes::Scan({argv[1],argv[1]});
    assert(list.size()==5);
    assert(nes::MapButtons(0x4000)==(1u<<RETRO_DEVICE_ID_JOYPAD_A));
    assert(nes::MapButtons(0x2000)==(1u<<RETRO_DEVICE_ID_JOYPAD_B));
    nes::Session session(argv[2]);
    assert(!session.Load("bad.nes",std::vector<uint8_t>(8)));
    assert(session.Load("generated-input.nes",raw));
    assert(session.sample_rate==48000);
    bool heard=false;
    for(int i=0;i<6;++i){session.Run();heard|=std::any_of(session.audio.begin(),session.audio.end(),[](int16_t s){return s!=0;});}
    assert(heard);assert(session.width==256&&session.height==240);assert(session.pixels.size()==256*240);
    assert(std::all_of(session.pixels.begin(),session.pixels.end(),[](uint32_t pixel){return (pixel>>24)==255;}));
    const auto* memory=static_cast<const uint8_t*>(retro_get_memory_data(RETRO_MEMORY_SAVE_RAM));
    assert(memory&&retro_get_memory_size(RETRO_MEMORY_SAVE_RAM)>=8192);
    session.buttons[0]=nes::MapButtons(0x4000);session.Run();session.Run();assert(memory[0]==1);
    assert(session.SaveState());
    session.buttons[0]=0;session.Run();session.Run();assert(memory[0]==0);
    assert(session.LoadState());assert(memory[0]==1);
    assert(session.SaveBattery());assert(session.Unload());
    assert(session.Load("generated-input.nes",raw));
    memory=static_cast<const uint8_t*>(retro_get_memory_data(RETRO_MEMORY_SAVE_RAM));assert(memory[0]==1);
    assert(session.Unload());
    // Reloading multiple times checks that callback/content lifetimes survive menu transitions.
    for(int i=0;i<3;++i){assert(session.Load("generated-input.nes",raw));session.Run();assert(session.Unload());}
    assert(session.Load("nfs://192.0.2.1/NES/game.zip",raw));session.Run();assert(session.Unload());
    session.SetOption("fceumm_region","PAL");
    assert(session.Load("generated-input.nes",raw));assert(session.fps>49 && session.fps<51);session.Run();assert(session.Unload());
    puts("NES integration passed: memory ROM, ZIP validation, controller, frame, audio, SRAM, states and reloads (AI-assisted)");
}
