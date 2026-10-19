// NES cover art from the user-selected Libretro public thumbnail directory.
// The directory listing is parsed ONCE on the cover worker thread, so a
// collection of hundreds of ROMs does not issue thousands of guessed 404s.
// This returns actual .png names from the provider's index, not arbitrary URLs.
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "fe_covers.h"
#include "cover_urls.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <string>
#include <unordered_map>
#include <vector>

namespace fe::libretro
{
inline constexpr const char* kBase =
    "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%20Entertainment%20System/Named_Boxarts/";

struct Entry
{
    std::string filename; // actual decoded filename from the listing
    std::string relative; // relative URI, percent encoded
};
using Index = std::unordered_map<std::string, std::vector<Entry>>;

inline int HexDigit(char c)
{
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;
}
inline std::string DecodeHref(std::string s)
{
    // Directory HTML may escape literal & as &amp;, but URL encoding
    // (%26) is more common. Only decode the expected common entity.
    for(size_t at=0;(at=s.find("&amp;",at))!=std::string::npos;)
        s.replace(at,5,"&");
    std::string decoded;
    for(size_t i=0;i<s.size();++i)
    {
        if(s[i]=='%' && i+2<s.size())
        {
            const int a=HexDigit(s[i+1]),b=HexDigit(s[i+2]);
            if(a>=0&&b>=0)
            {
                const char c=static_cast<char>(a*16+b);
                if(c=='/'||c=='\\'||c=='\0'||static_cast<unsigned char>(c)<0x20)
                    return {}; // no traversal, injected controls or nested paths
                decoded+=c;i+=2;continue;
            }
        }
        decoded+=s[i];
        if(decoded.size()>512)return {};
    }
    if(decoded.find('/')!=std::string::npos ||
       decoded.find('\\')!=std::string::npos ||
       decoded.find("..")!=std::string::npos ||
       decoded.empty() || decoded[0]=='.')
        return {};
    return decoded;
}
inline Index ParseDirectory(const std::string& html)
{
    Index index;
    if(html.size()<100 || html.size()>12u*1024u*1024u)return index;
    size_t at=0,count=0;
    while(count<30000)
    {
        at=html.find("href=",at);
        if(at==std::string::npos)break;
        at+=5;
        if(at>=html.size())break;
        const char quote=html[at];
        if(quote!='"' && quote!='\'')continue;
        const size_t end=html.find(quote,++at);
        if(end==std::string::npos)break;
        const std::string encoded=html.substr(at,end-at);
        at=end+1;
        if(encoded.size()>1536 || encoded.find('/')!=std::string::npos ||
           encoded.find('?')!=std::string::npos ||
           encoded.find('#')!=std::string::npos)continue;
        const std::string file=DecodeHref(encoded);
        if(file.size()<5 || file.substr(file.size()-4)!=".png")continue;
        const std::string key=nes::CoverKey(file.substr(0,file.size()-4));
        if(key.empty())continue;
        index[key].push_back({file,nes::CoverEncode(file)});
        ++count;
    }
    return index;
}
inline int Score(const Entry& e,const std::string& region)
{
    const std::string& name=e.filename;
    int score=0;
    if(region=="USA" && name.find("(USA)")!=std::string::npos)score+=100;
    if(region=="Japan" && name.find("(Japan)")!=std::string::npos)score+=100;
    if(region=="Europe" && name.find("(Europe)")!=std::string::npos)score+=100;
    if(region.empty() && name.find("(USA)")!=std::string::npos)score+=45;
    if(name.find("(Rev ")!=std::string::npos)score-=8;
    if(name.find("[b")!=std::string::npos || name.find("[h")!=std::string::npos ||
       name.find("[t")!=std::string::npos || name.find("[o")!=std::string::npos)
        score-=55;
    if(name.find("(19")!=std::string::npos || name.find("(20")!=std::string::npos)
        score-=15; // prefer region-named rather than dated alternate dumps
    return score;
}
inline std::string Match(const Index& index,const GameInfo& game)
{
    const std::string key=nes::CoverKey(game.title.empty()?game.stem:game.title);
    const auto it=index.find(key);
    if(it==index.end())return {};
    const Entry* best=nullptr;
    int score=-999999;
    for(const auto& e:it->second)
    {
        const int n=Score(e,game.region);
        if(n>score){best=&e;score=n;}
    }
    return best?std::string(kBase)+best->relative:std::string();
}
inline std::string Lookup(const GameInfo& game,const DownloadFn& download,
                          const std::atomic<bool>* stop=nullptr)
{
    static thread_local bool tried=false;
    static thread_local Index index;
    if(!tried)
    {
        tried=true;
        if(stop && *stop)return {};
        std::vector<uint8_t> body;
        const int status=download(kBase,body);
        if(status==200 && body.size()<=12u*1024u*1024u)
        {
            const std::string html(body.begin(),body.end());
            index=ParseDirectory(html);
        }
        std::printf("[covers] Libretro index: HTTP %d, %zu bytes, %zu distinct game titles\n",
                    status,body.size(),index.size());
    }
    return Match(index,game);
}
} // namespace fe::libretro
