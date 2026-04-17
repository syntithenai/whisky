# Distillery Remediation Priority List

Generated: 2026-04-17 (with live URL probe)

## Coverage Snapshot
- Distilleries with official URLs in source: 82
- Distilleries with successful crawl coverage: 15
- Remaining unresolved distilleries: 67

## Probe Bucket Counts
- P0_URL_DNS: 7
- P0_URL_SSL: 1
- P1_BLOCKED_403: 5
- P1_TIMEOUT_OR_WAF: 1
- P1_LINK_QUALITY_404: 3
- P2_REACHABLE_RUN_CRAWL: 46
- P3_UNKNOWN_NEEDS_MANUAL: 4

## Priority Guidance
1. Fix P0 buckets first (bad domains/certs)
2. Then P1 (blocked/timeouts) with CDP/browser retries
3. Run bulk crawl on P2 reachable sites to increase coverage quickly

## P0_URL_DNS
1. Chief's Son Distillery
   - URL: https://www.chiefssondistillery.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: www.chiefssondistillery.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Chief's Son Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
2. Corowa Distilling Co.
   - URL: https://corowadistilling.com/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: corowadistilling.com
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Corowa Distilling Co." --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
3. Joadja Distillery
   - URL: https://joadja.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: joadja.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Joadja Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
4. Killara Distillery
   - URL: https://killaradistillery.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:05 --:--:--     0curl: (6) Could not resolve host: killaradistillery.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Killara Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
5. Smith's Angaston Distillery
   - URL: https://www.smithsangaston.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: www.smithsangaston.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Smith's Angaston Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
6. The Grove Distillery
   - URL: https://www.grovedistillery.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: www.grovedistillery.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "The Grove Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
7. Wild River Distillery
   - URL: https://wildriverdistillery.com.au/
   - Probe: http_code=none; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0curl: (6) Could not resolve host: wildriverdistillery.com.au
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Wild River Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P0_URL_SSL
1. Hobart Whisky
   - URL: https://hobartwhisky.com/
   - Probe: http_code=none; signal=how to fix it, please visit the webpage mentioned above.
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Hobart Whisky" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P1_BLOCKED_403
1. Highland Park
   - URL: https://www.highlandparkwhisky.com/
   - Probe: http_code=403; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Highland Park" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
2. Jameson
   - URL: https://www.jamesonwhiskey.com/
   - Probe: http_code=403; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Jameson" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
3. Redbreast
   - URL: https://www.redbreastwhiskey.com/
   - Probe: http_code=403; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Redbreast" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
4. Springbank
   - URL: https://www.springbank.scot/
   - Probe: http_code=403; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Springbank" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
5. The Macallan
   - URL: https://www.themacallan.com/
   - Probe: http_code=403; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "The Macallan" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P1_TIMEOUT_OR_WAF
1. The Gospel Whisky
   - URL: https://thegospelwhisky.com/
   - Probe: http_code=none; signal=curl: (28) Connection timed out after 12002 milliseconds
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "The Gospel Whisky" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P1_LINK_QUALITY_404
1. Jack Daniel's
   - URL: https://www.jackdaniels.com/
   - Probe: http_code=404; signal=  0  135k    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Jack Daniel's" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
2. Miyagikyo
   - URL: https://www.nikka.com/eng/brands/miyagikyo/
   - Probe: http_code=404; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Miyagikyo" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
3. Yoichi
   - URL: https://www.nikka.com/eng/brands/yoichi/
   - Probe: http_code=404; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Yoichi" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P2_REACHABLE_RUN_CRAWL
1. Buffalo Trace Distillery
   - URL: https://www.buffalotracedistillery.com/
   - Probe: http_code=200; signal=  0  183k    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Buffalo Trace Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
2. Bushmills
   - URL: https://bushmills.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Bushmills" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
3. Callington Mill Distillery
   - URL: https://callingtonmilldistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Callington Mill Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
4. Cauldron Distillery
   - URL: https://www.cauldrondistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Cauldron Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
5. Crown Royal
   - URL: https://www.crownroyal.com/
   - Probe: http_code=200; signal=  0  683k    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Crown Royal" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
6. Fleurieu Distillery
   - URL: https://fleurieudistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:03 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Fleurieu Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
7. Forty Creek
   - URL: https://fortycreekwhisky.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Forty Creek" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
8. Furneaux Distillery
   - URL: https://furneauxdistillery.com.au/
   - Probe: http_code=200; signal=  0 31523    0     0    0     0      0      0 --:--:--  0:00:02 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Furneaux Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
9. Geographe Distillery (Bellwether)
   - URL: https://www.geographewine.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Geographe Distillery (Bellwether)" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
10. Glen Scotia
   - URL: https://www.glenscotia.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Glen Scotia" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
11. Glenfarclas
   - URL: https://www.glenfarclas.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:05 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Glenfarclas" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
12. Glenfiddich
   - URL: https://www.glenfiddich.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Glenfiddich" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
13. Great Southern Distilling Company (Limeburners)
   - URL: https://www.limeburners.com/
   - Probe: http_code=200; signal=  0   438    0     0    0     0      0      0 --:--:--  0:00:02 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Great Southern Distilling Company (Limeburners)" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
14. Hakushu
   - URL: https://house.suntory.com/hakushu-whisky
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Hakushu" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
15. Headlands Distilling Co.
   - URL: https://headlands.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Headlands Distilling Co." --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
16. Hellyers Road
   - URL: https://hellyersroaddistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Hellyers Road" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
17. Kavalan
   - URL: https://www.kavalanwhisky.com/en/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Kavalan" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
18. Kinglake Distillery
   - URL: https://www.kinglakedistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Kinglake Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
19. Kitty Hawk Distillery
   - URL: https://www.kittyhawkdistillery.com.au/
   - Probe: http_code=200; signal=  0 21492    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Kitty Hawk Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
20. Laphroaig
   - URL: https://www.laphroaig.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Laphroaig" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
21. Lark Distillery
   - URL: https://larkdistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Lark Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
22. Launceston Distillery
   - URL: https://launcestondistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:02 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Launceston Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
23. Lawrenny Estate Distillery
   - URL: https://lawrenny.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:03 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Lawrenny Estate Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
24. Maker's Mark
   - URL: https://www.makersmark.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Maker's Mark" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
25. Manly Spirits Co.
   - URL: https://manlyspirits.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Manly Spirits Co." --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
26. McHenry Distillery
   - URL: https://mchenrydistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "McHenry Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
27. McRobert Distillery
   - URL: https://www.mcrobertdistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "McRobert Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
28. Morris Whisky
   - URL: https://morriswhisky.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Morris Whisky" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
29. Mt Uncle Distillery
   - URL: https://mtuncle.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Mt Uncle Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
30. Nant Distillery
   - URL: https://nant.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Nant Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
31. Noosa Heads Distillery
   - URL: https://noosaheadsdistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Noosa Heads Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
32. Nullaki Distillery
   - URL: https://www.nullakidistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Nullaki Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
33. Old Kempton Distillery
   - URL: https://oldkempton.com.au/
   - Probe: http_code=405; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Old Kempton Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
34. Overeem
   - URL: https://overeem.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Overeem" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
35. Reedy Swamp Distillery
   - URL: https://www.reedyswampdistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Reedy Swamp Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
36. Spring Bay Distillery
   - URL: https://springbaydistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Spring Bay Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
37. Starward
   - URL: https://starward.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Starward" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
38. Sullivans Cove
   - URL: https://sullivanscove.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Sullivans Cove" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
39. Teeling
   - URL: https://www.teelingwhiskey.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Teeling" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
40. Timboon Railway Shed Distillery
   - URL: https://www.timboondistillery.com.au/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Timboon Railway Shed Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
41. Uncle Nearest
   - URL: https://unclenearest.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Uncle Nearest" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
42. Waubs Harbour Whisky
   - URL: https://waubsharbourwhisky.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Waubs Harbour Whisky" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
43. Whipper Snapper Distillery
   - URL: https://whippersnapper.com.au/
   - Probe: http_code=405; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Whipper Snapper Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
44. Wild Turkey
   - URL: https://www.wildturkeybourbon.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Wild Turkey" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
45. Woodlands Distillery
   - URL: https://www.woodlandsdistillery.com/
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Woodlands Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
46. Yamazaki
   - URL: https://house.suntory.com/yamazaki-whisky
   - Probe: http_code=200; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Yamazaki" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

## P3_UNKNOWN_NEEDS_MANUAL
1. Iniquity Whisky (Tin Shed Distilling)
   - URL: https://iniquity.com.au/
   - Probe: http_code=none; signal=curl: (35) TLS connect error: error:0A0000C6:SSL routines::packet length too long
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Iniquity Whisky (Tin Shed Distilling)" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
2. Lagavulin
   - URL: https://www.malts.com/en-row/products/single-malt-whisky/lagavulin
   - Probe: http_code=500; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Lagavulin" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
3. Oban
   - URL: https://www.malts.com/en-row/products/single-malt-whisky/oban
   - Probe: http_code=500; signal=  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Oban" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless
4. Shene Distillery
   - URL: https://shenedistillery.com.au/
   - Probe: http_code=429; signal=  0  6959    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
   - Retry command: python3 scripts/crawl_whisky_sites.py --site-types distillery --filter-name "Shene Distillery" --max-sites 1 --max-pages-per-site 60 --force-rescrape --parallel-page-loads 2 --no-distillery-sync --headless

