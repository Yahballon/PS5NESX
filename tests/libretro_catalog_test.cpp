// Covers are matched to the official directory listing, not guessed URLs.
#include "fe_libretro_catalog.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

int main()
{
    using namespace fe::libretro;
    using fe::GameInfo;
    const std::string html =
        "<html><head><title>Index of /Nintendo - Nintendo Entertainment System/Named_Boxarts</title></head>"
        "<body>"
        "<a href=\"Super%20Mario%20Bros.%203%20%28USA%29.png\">SMB3</a>"
        "<a href=\"Super%20Mario%20Bros.%203%20%28Japan%29.png\">SMB3 JP</a>"
        "<a href=\"Rockman%201%20%28Japan%29.png\">Rockman</a>"
        "<a href=\"Super%20Mario%20Bros.%203%20%281988%29%5Bh%5D.png\">hack</a>"
        "<a href=\"..%2Fsecret.png\">unsafe</a>"
        "<a href=\"https://invalid.example/steal.png\">external</a>"
        "</body></html>";
    const auto index=ParseDirectory(html);
    assert(index.size()==2);
    GameInfo mario;
    mario.title="Super Mario Bros. 3"; mario.region="USA";
    const std::string u=Match(index,mario);
    assert(u==std::string(kBase)+"Super%20Mario%20Bros.%203%20%28USA%29.png");
    mario.region="Japan";
    assert(Match(index,mario).find("%28Japan%29.png")!=std::string::npos);
    GameInfo rockman;
    rockman.title="022 Rockman 1"; rockman.region="Japan";
    assert(Match(index,rockman).find("Rockman%201%20%28Japan%29.png")!=std::string::npos);
    GameInfo missing; missing.title="Nonexistent Family Game";
    assert(Match(index,missing).empty());
    assert(DecodeHref("..%2Fsecret.png").empty());
    assert(DecodeHref("Mario%20%26%20Luigi.png")=="Mario & Luigi.png");
    int requests=0;
    fe::DownloadFn downloader=[&](const std::string& url,std::vector<uint8_t>& out)->int
    {
        ++requests;
        assert(url==kBase);
        out.assign(html.begin(),html.end());
        return 200;
    };
    assert(Lookup(mario,downloader)==std::string(kBase)+"Super%20Mario%20Bros.%203%20%28Japan%29.png");
    assert(!Lookup(rockman,downloader).empty());
    assert(requests==1); // one directory request for entire batch
    std::cout<<"PASS: official NES archive, one-time index, regional match, safe filename, collection prefix\n";
}
