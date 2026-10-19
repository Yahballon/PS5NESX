// Host regression tests for PS5NESX's circular navigation and online covers.
#include "fe_navigation.h"
#include "cover_urls.h"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

static bool HasUrl(const std::vector<std::string>& urls, const std::string& needle)
{
    return std::any_of(urls.begin(), urls.end(),
        [&](const std::string& url) { return url.find(needle) != std::string::npos; });
}
int main()
{
    using fe::WrappedGameIndex;
    assert(WrappedGameIndex(22,1,23)==0);  // last -> first
    assert(WrappedGameIndex(0,-1,23)==22); // first -> last
    assert(WrappedGameIndex(22,5,23)==4);  // R1 can wrap too
    assert(WrappedGameIndex(0,-5,23)==18);
    assert(WrappedGameIndex(1,1,23)==2);
    assert(WrappedGameIndex(0,0,1)==0);
    assert(WrappedGameIndex(0,1,0)==0);
    assert(nes::CoverKey("022 Rockman 1 (Japan)")=="rockman1");
    assert(nes::CoverKey("Super Mario Bros. 3 (USA)")=="supermariobros3");
    fe::GameInfo indexed;
    indexed.title="022 Rockman 1"; indexed.stem="022 Rockman 1"; indexed.region="USA";
    const auto urls=nes::CoverUrls(indexed);
    assert(HasUrl(urls,"Rockman%201%20%28USA%29.png"));
    assert(HasUrl(urls,"/Named_Boxarts/"));
    fe::GameInfo mario;
    mario.title="Super Mario Bros. 3"; mario.stem=mario.title; mario.region="USA";
    const auto candidates=nes::CoverUrls(mario);
    assert(!candidates.empty());
    assert(HasUrl(candidates,"Super%20Mario%20Bros.%203"));
    std::cout << "PASS: wrap in both directions, R1/L1 skips, numbered ROM title, automatic artwork URL candidates\n";
}
