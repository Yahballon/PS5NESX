// Optional, single-session ArcadeArtwork Piwigo album #547 fallback.
// Uses the site's documented Piwigo category API. Never guesses image paths,
// never downloads gallery HTML as a cover, and never contacts a foreign host.
// If Piwigo blocks access or changes format, existing artwork providers remain.
#pragma once
#include "fe_covers.h"
#include "cover_urls.h"
#include <algorithm>
#include <cstdio>
#include <string>
#include <unordered_map>
#include <utility>

namespace fe::arcadeartwork
{
inline std::string JsonString(const std::string& object, const char* field)
{
    const std::string key = std::string("\"") + field + "\"";
    size_t start=object.find(key);
    while(start!=std::string::npos)
    {
        size_t colon=object.find(':',start+key.size());
        if(colon==std::string::npos)return {};
        size_t at=object.find_first_not_of(" \t\r\n",colon+1);
        if(at!=std::string::npos&&object[at]=='"')
        {
            std::string out;
            for(++at;at<object.size();++at)
            {
                const char ch=object[at];
                if(ch=='"')return out;
                if(ch=='\\'&&at+1<object.size())
                {
                    const char next=object[++at];
                    if(next=='n')out+='\n';
                    else if(next=='t')out+='\t';
                    else if(next=='r')out+='\r';
                    else if(next=='"'||next=='\\'||next=='/')out+=next;
                    else if(next=='u'&&at+4<object.size())at+=4;
                }
                else out+=ch;
                if(out.size()>2048)return {};
            }
        }
        start=object.find(key,start+key.size());
    }
    return {};
}
inline bool IsGalleryImage(const std::string& url)
{
    return (url.rfind("https://www.arcadeartwork.org/",0)==0 ||
            url.rfind("https://arcadeartwork.org/",0)==0) &&
            url.size()<2048 && url.find('#')==std::string::npos;
}
inline std::string PictureUrl(const std::string& object)
{
    // Piwigo's medium derivative is appropriate for 3D covers, with the
    // original "element_url" as a fallback for older Piwigo installations.
    const auto medium=object.find("\"medium\"");
    if(medium!=std::string::npos)
    {
        const auto sub=object.substr(medium,400);
        const std::string url=JsonString(sub,"url");
        if(IsGalleryImage(url))return url;
    }
    const std::string raw=JsonString(object,"element_url");
    return IsGalleryImage(raw)?raw:std::string();
}
inline void AddPage(const std::string& json,std::unordered_map<std::string,std::string>& index)
{
    // Defensively walk array entries (nested derivatives and categories
    // may contain JSON objects too); only store named image objects.
    if(json.size()>4u*1024u*1024u || json.find("\"stat\":\"ok\"")==std::string::npos)
        return;
    size_t pos=json.find("\"images\"");
    if(pos==std::string::npos)return;
    pos=json.find('[',pos+8);
    if(pos==std::string::npos)return;
    bool quoted=false,escape=false;
    int depth=0;
    size_t start=0;
    for(size_t i=pos+1;i<json.size();++i)
    {
        const char c=json[i];
        if(quoted)
        {
            if(escape)escape=false;
            else if(c=='\\')escape=true;
            else if(c=='"')quoted=false;
            continue;
        }
        if(c=='"'){quoted=true;continue;}
        if(c=='['&&depth==0)break; // no nested arrays outside image objects
        if(c==']'&&depth==0)break;
        if(c=='{')
        {
            if(depth++==0)start=i;
        }
        else if(c=='}'&&depth>0)
        {
            if(--depth==0 && i-start<100000)
            {
                const std::string item=json.substr(start,i-start+1);
                const std::string title=JsonString(item,"name");
                const std::string url=PictureUrl(item);
                if(!title.empty()&&!url.empty())
                {
                    const std::string key=nes::CoverKey(title);
                    if(!key.empty())index.emplace(key,url);
                }
            }
        }
    }
}
inline std::string Match(const std::unordered_map<std::string,std::string>& index,
                         const GameInfo& game)
{
    const std::string name=nes::CoverKey(game.title.empty()?game.stem:game.title);
    if(name.empty())return {};
    // Exact title first, then well-defined country abbreviations. Do not
    // match prefixes like "Mario 1" against "Mario 10".
    for(const char* suffix : {"", "usa", "u", "japan", "j", "europe", "e", "uk"})
    {
        auto it=index.find(name+suffix);
        if(it!=index.end())return it->second;
    }
    return {};
}
inline std::string Lookup(const GameInfo& game,const DownloadFn& download,
                          const std::atomic<bool>* stop=nullptr)
{
    static thread_local bool loaded=false;
    static thread_local std::unordered_map<std::string,std::string> index;
    if(!loaded)
    {
        loaded=true;
        // One bounded catalogue download per session (two pages maximum),
        // rather than 23 HTML scrapes or one request for every ROM.
        for(int page=0;page<2;++page)
        {
            if(stop && *stop)break;
            const std::string url=
                "https://www.arcadeartwork.org/ws.php?format=json&method=pwg.categories.getImages&cat_id=547&per_page=400&page="
                +std::to_string(page);
            std::vector<uint8_t> body;
            const int status=download(url,body);
            if(status!=200 || body.empty() || body.size()>4u*1024u*1024u)
            {
                std::printf("[covers] ArcadeArtwork API unavailable: HTTP %d, page %d\n",status,page);
                break;
            }
            const auto before=index.size();
            AddPage(std::string(body.begin(),body.end()),index);
            std::printf("[covers] ArcadeArtwork category 547 page %d: %zu indexed\n",
                        page,index.size()-before);
            if(index.size()==before)break;
        }
    }
    return Match(index,game);
}
} // namespace fe::arcadeartwork
