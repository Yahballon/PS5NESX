// (AI-assisted) Simulate internal PS5 mounts: path metadata denied, readdir/open/fstat allowed.
#include "games.h"
#include "library_cache.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <dirent.h>
#include <sys/stat.h>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <unistd.h>
static std::string internal;static bool deny_descriptor=false;
extern "C" int __real_fstat(int,struct stat*);
extern "C" int __wrap_fstat(int fd,struct stat* info){char name[64],target[2048];std::snprintf(name,sizeof(name),"/proc/self/fd/%d",fd);auto n=readlink(name,target,sizeof(target)-1);if(n>=0){target[n]=0;if(deny_descriptor&&std::string(target).starts_with(internal)){errno=EPERM;return -1;}}return __real_fstat(fd,info);}
extern "C" int __real_stat(const char*,struct stat*);
extern "C" int __wrap_stat(const char* path,struct stat* info){if(std::string(path).starts_with(internal)){errno=EPERM;return -1;}return __real_stat(path,info);}
extern "C" int __wrap_lstat(const char*,struct stat*){errno=EPERM;return -1;}
extern "C" dirent* __real_readdir(DIR*);
extern "C" dirent* __wrap_readdir(DIR* d){auto* e=__real_readdir(d);if(e)e->d_type=DT_UNKNOWN;return e;}
int main(int argc,char**argv){assert(argc==2);namespace fs=std::filesystem;internal=std::string(argv[1])+"/internal";auto usb=std::string(argv[1])+"/usb";fs::create_directories(internal+"/games/nested");fs::create_directories(usb);std::ofstream(internal+"/games/Local.NES")<<(std::string("NES\x1a",4)+std::string(12,'\0'));std::ofstream(internal+"/games/nested/Second.nes")<<(std::string("NES\x1a",4)+std::string(12,'\0'));std::ofstream(internal+"/games/._Mac.nes")<<"ignored";std::ofstream(usb+"/Usb.nes")<<(std::string("NES\x1a",4)+std::string(12,'\0'));auto games=nes::Scan({internal+"/games",usb});assert(games.size()==3);unsigned local=0;for(auto& g:games)if(g.path.starts_with(internal))++local;assert(local==2);std::ofstream(internal+"/games/New.nes")<<(std::string("NES\x1a",4)+std::string(12,'\0'));assert(nes::Scan({internal+"/games",usb}).size()==4);fs::remove(internal+"/games/Local.NES");assert(nes::Scan({internal+"/games",usb}).size()==3);deny_descriptor=true;assert(nes::Scan({internal+"/games",usb}).size()==3);std::vector<uint8_t> data;std::string error;assert(nes::ReadRom(internal+"/games/New.nes",data,error)&&data.size()==16);auto cache=internal+"/cache.bin";assert(nes::WriteLibrary(cache,nes::Scan({internal+"/games"})));std::vector<nes::Game> cached;assert(nes::ReadLibrary(cache,{internal+"/games"},cached)&&cached.size()==2);std::cout<<"PASS denied internal stat/lstat and unknown dirent types: nested/uppercase NES detection, USB preserved, new/deleted files and Mac resource-fork filtering\n";}
