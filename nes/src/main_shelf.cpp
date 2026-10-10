// (AI-assisted) Original PS5SX2 frontend startup, with a NES playback backend.
#include "fe_ps5.h"
#include "elevation.hpp"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
extern "C" int sceNetInit();
int main() {
    sceNetInit();
    const auto access=elevation::request(elevation::Capability::filesystem);
    std::string root="/data/PS5NES";
    if(mkdir(root.c_str(),0777)!=0&&errno!=EEXIST)root="/download0/PS5NES";
    mkdir(root.c_str(),0777);
    for(const char* dir:{"games","roms","saves","settings","covers","cache","logs"})mkdir((root+"/"+dir).c_str(),0777);
    mkdir((root+"/cache/ps5vk-shader-cache").c_str(),0777);
    setenv("PS5VK_SHADER_CACHE_DIR",(root+"/cache/ps5vk-shader-cache").c_str(),1);
    int fd=open((root+"/logs/boot.log").c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_APPEND,0666);
    if(fd>=0){dup2(fd,fileno(stdout));dup2(fd,fileno(stderr));close(fd);setvbuf(stdout,nullptr,_IOLBF,4096);}
    std::printf("[boot] PS5NES v1.0.0.9 by YAHBALLON (AI-assisted), original PS5SX2 shelf, filesystem=%u\n",unsigned(access));
    OrbisFrontendPaths paths;paths.top_dir=root;paths.games_dir=root+"/games";paths.settings_dir=root+"/settings";
    paths.gs_ini=root+"/gs.ini";paths.covers_dir=root+"/covers";paths.cache_dir=root+"/cache";
    paths.logs_dir=root+"/logs";paths.settings_log=root+"/logs/settings.log";paths.serial_cache=root+"/cache/serials.txt";
    paths.usb_list=root+"/cache/usb-games.txt";paths.allow_download=true;paths.sound=true;
    paths.report_header="PS5NES v1.0.0.9 by YAHBALLON (AI-assisted)";
    for(int i=0;i<8;++i){auto usb="/mnt/usb"+std::to_string(i);
        for(const char* folder:{"/homebrew/PS5NES/games","/homebrew/PS5NES/roms","/PS5NES/games","/PS5NES/roms","/homebrew/PPSA99204/games","/homebrew/PPSA99204/roms","/NES"})paths.usb_dirs.push_back(usb+folder);}
    for(const char* folder:{"/data/PS5NES/games","/data/PS5NES/roms","/data/NES","/data/homebrew/PPSA99204/games","/data/homebrew/PPSA99204/roms","/data/homebrew/PS5NES/games","/data/homebrew/PS5NES/roms"})paths.usb_dirs.push_back(folder);
    std::printf("[library] active data root=%s; internal ROMs=/data/PS5NES/games/ and /data/homebrew/PPSA99204/games/\n",root.c_str());
    orbis_frontend_set_language(root+"/lang");
    orbis_web_start(paths,"v1.0.0.9 by YAHBALLON");
    bool ran=false;orbis_frontend_run(paths,"v1.0.0.9 by YAHBALLON",&ran);
    for(;;)sleep(1);
}
