#include "fe_arcadeartwork.h"
#include "fe_navigation.h"
#include <cassert>
#include <iostream>
#include <string>

int main()
{
    using namespace fe;
    using namespace fe::arcadeartwork;
    // Real Piwigo-like gallery response, including nested derivatives and
    // UTF8-escaped slashes. Do not rely on HTML pages or category redirects.
    const std::string json=R"({
      "stat":"ok","result":{"images":[
        {"id":4132,"name":"Super-Mario-Bros.-3--USA-",
         "derivatives":{"thumb":{"url":"https:\/\/www.arcadeartwork.org\/thumb.jpg"},
                        "medium":{"url":"https:\/\/www.arcadeartwork.org\/_data\/i\/games\/smb3-me.jpg"}},
         "element_url":"https:\/\/www.arcadeartwork.org\/galleries\/smb3.png"},
        {"id":4200,"name":"Rockman-1--Japan-",
         "element_url":"https:\/\/www.arcadeartwork.org\/galleries\/rockman.png"},
        {"id":4201,"name":"Unsafe",
         "element_url":"https:\/\/example.invalid\/malicious.jpg"}
      ]}})";
    std::unordered_map<std::string,std::string> entries;
    AddPage(json,entries);
    GameInfo mario;
    mario.title="Super Mario Bros. 3";
    GameInfo rock;
    rock.title="022 Rockman 1";
    GameInfo other;
    other.title="Unknown";
    assert(entries.size()==2);
    assert(Match(entries,mario)=="https://www.arcadeartwork.org/_data/i/games/smb3-me.jpg");
    assert(Match(entries,rock)=="https://www.arcadeartwork.org/galleries/rockman.png");
    assert(Match(entries,other).empty());
    assert(!IsGalleryImage("https://other.example/evil.jpg"));
    assert(WrappedGameIndex(22,1,23)==0);
    int called=0;
    DownloadFn mock=[&](const std::string& url,std::vector<uint8_t>& out) {
        ++called;
        if(url.find("cat_id=547")==std::string::npos)return 404;
        if(url.find("page=0")!=std::string::npos) {
            out.assign(json.begin(),json.end());return 200;
        }
        return 404;
    };
    assert(Lookup(mario,mock)=="https://www.arcadeartwork.org/_data/i/games/smb3-me.jpg");
    const int after=called;
    assert(Lookup(rock,mock)=="https://www.arcadeartwork.org/galleries/rockman.png");
    assert(called==after); // gallery index loaded once, even for 23 games
    std::cout<<"PASS: gallery JSON, safe host, matching, single cached index and wrap\n";
}
