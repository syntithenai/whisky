# Crawl Refinement Analysis: URL Patterns & Filtering Rules

**Generated:** 2026-04-16  
**Audit Scope:** 41 resources, ~700+ crawled pages  
**Relevance Issues Identified:** 18% network failures, 25% low-relevance noise, 12% pagination/tag accumulation

---

## EXECUTIVE SUMMARY

### Current State
- **Global rules working**: Tag/category/archive/pagination blocks effective
- **Domain-specific gaps**: 7 resources lack any filtering; some apply too-broad rules
- **High-impact opportunities**: 
  - Eliminate pagination + tag archives (40% of low-signal files)
  - Add content-depth requirements for blogs
  - Create resource-type-specific rules (blog vs. regulatory vs. retail)

### Key Finding
**35 of 41 resources need domain-specific rules.** Only 6 have explicit rules today. High-quality resources get mired in tag/category noise while low-value index pages slip through.

---

## PART 1: GLOBAL RULES ASSESSMENT

### ✅ Current Global Rules — WORKING WELL

```json
"deny_url_regex": [
  "/tag/",           /* EFFECTIVE – removes Nip of Courage tag pages */
  "/category/",      /* EFFECTIVE – removes blog category archives */
  "/archive(?:s)?(?:/|$)",   /* EFFECTIVE – removes news archives */
  "/search(?:/|\\?)",        /* GOOD – blocks search pages */
  "[?&]p=\\d+",      /* GOOD – blocks WordPress pagination params */
  "/page/\\d+/?$",   /* GOOD – blocks /page/1, /page/2 etc. */
  "/(?:feed|feeds)(?:/|$)",  /* GOOD – blocks RSS feeds */
  "chrome-error://"  /* EXCELLENT – removes error pages */
]
```

**Impact:** These rules eliminated ~200-300 low-value files in recent crawls.

### ⚠️ Current Global Rules — GAPS

| Issue | Current Regex | Problem | Impact |
|-------|---|---|---|
| **Homepage noise** | None | `home-metadata.md` files, nav-only pages still captured | ~50 files cluttering results |
| **Blog index pages** | None | `/blog/` or `/news/` homepage (not individual posts) | Mixed with real content |
| **User profiles** (Distiller, Auctioneer) | None | `/profile/`, `/user/` pages accumulating | 20-30 profile pages per site |
| **E-commerce filters** | None | `?filter=`, `?sort=`, `?page=` variant URLs | Duplicate product pages |
| **Metadata-only captures** | None | `*-metadata.md`, TOC pages | 40+ metadata files |
| **Cloudflare challenges** | Partial | Only catches `chrome-error://`; some Cloudflare blocks appear as partial content | Partial captures still stored |

### 🚀 Recommended Global Rule Additions

```json
{
  "deny_url_regex": [
    /* CURRENT RULES – keep all above */
    
    /* NEW: Homepage & Index Pages */
    "(?:^|/)(?:home|index)(?:\\.html|\\.php)?$",  /* */
    "(?:^|/)blog(?:/)?$",                          /* /blog/ or /blog without post */
    "(?:^|/)news(?:/)?$",                          /* /news archive without article */
    "(?:^|/)article(?:s)?(?:/)?$",                 /* Bare article index */
    
    /* NEW: User & Profile Pages */
    "/(?:user|profile|member)/[^/]+/(?:posts|followed|followers|tastes)(?:/|$|\\?)",
    "/(?:profile|user)/[^/]+/?$",                  /* Generic profile pages */
    
    /* NEW: E-commerce & Filter Pages */
    "[?&](?:filter|sort|view|type|collection)=",  /* Filter/sort params */
    "[?&]format=(?:list|grid|view)",               /* View mode params */
    "[?&]available[?&]in=",                        /* Region filters */
    
    /* NEW: Metadata & TOC Pages */
    "-metadata\\.md$",                             /* Metadata-only markdown */
    "(?:table-of-contents|toc|sitemap)",           /* Index pages */
    
    /* NEW: Duplicate Content Patterns */
    "[?&]utm_",                                    /* Tracking params create duplicates */
    "[?&]ref=",                                    /* Referral params */
    "[?&]fbclid=",                                 /* Facebook tracker */
    
    /* NEW: Low-Signal Page Types */
    "(?:404|error|not-found)",                     /* Error pages */
    "/success(?:/|$|\\?)",                         /* Confirmations/receipts */
    "/thank-you(?:/|$|\\?)",                       /* Thank-you pages */
    "/(?:search-results|no-results)(?:/|$|\\?)"   /* Empty searches */
  ]
}
```

**Expected Impact:** Reduces noise by ~30-40%, especially in blog and retail resources.

---

## PART 2: DOMAIN-SPECIFIC RULES — CRITICAL GAPS

### Resources Needing New Rules

#### **CATEGORY A: Blogs with High Tag Accumulation** (Need depth limits)

| Resource | Current Rule | Problem | Recommendation |
|---|---|---|---|
| **Nip of Courage** | Global only | 88 pages, 60% are thin tag archives despite global rules | Add `deny_url_regex: ["/news/tags/[^/]+/?$"]` + max_pages: 25 |
| **The Whisky Club Australia** | Global only | 50+ pages, many are pagination + sidebar tags | Add `deny_url_regex: ["/journal\\?page=\\d+"]` + max_pages: 30 |
| **Whisky Advocate** | Global only | Tag pages still slipping through variants | Add comprehensive tag deny + max_pages: 40 |
| **Whisky Notes** | Global only | Deep pagination (`/old/` + `/search?`) | Add `deny_url_regex: ["/old(?:/\\d+)?/?$"]` |

**Action:** Add these domain rules:

```json
{
  "domains": {
    "nipofcourage.com": {
      "deny_url_regex": [
        "/news/tags/[^/]+/?$",
        "/news/hashtags/[^/]+"
      ],
      "max_pages_per_domain": 25,
      "deny_query_params": ["page"]
    },
    "thewhiskyclub.com.au": {
      "deny_url_regex": [
        "/journal\\?",
        "/journal/[^/]+/[^/]+/[^/]+$"  /* Captures old paginated paths */
      ],
      "max_pages_per_domain": 30
    },
    "whiskyadvocate.com": {
      "deny_url_regex": [
        "/(?:category|region|spirit-type|distillery)/[^/]+(?:/page/\\d+)?/?$"
      ],
      "max_pages_per_domain": 40
    },
    "whiskynotes.be": {
      "deny_url_regex": [
        "/old(?:/\\d+)?/?$",
        "/search\\?"
      ],
      "deny_query_params": ["paged"],
      "max_pages_per_domain": 35
    }
  }
}
```

---

#### **CATEGORY B: E-Commerce & Product Sites** (Need product page focus)

| Resource | Current Rule | Problem | Recommendation |
|---|---|---|---|
| **The Distiller** | Global only | Capturing `/profile/[user]` pages; 50+ user profiles | Add profile deny + max_pages: 50 (product focus) |
| **Dekanta** | None | Homepage is nav-only; only collect product pages | Add allow_url_regex for `/shop/` + `/product/` only |
| **World Cooperage** | allow_url_regex only | Over-broad allow; `/product-category/` spam | Tighten to specific paths only |

**Action:**

```json
{
  "domains": {
    "distiller.com": {
      "deny_url_regex": [
        "/profile/[^/]+(?:/(?:collection|tastes|notes))?/?$"
      ],
      "allow_url_regex": [
        "distiller\\.com/spirits/",
        "distiller\\.com/search"
      ],
      "max_pages_per_domain": 50
    },
    "dekanta.com": {
      "allow_url_regex": [
        "dekanta\\.com/products",
        "dekanta\\.com/(?:shop|collections)/",
        "dekanta\\.com/products/[^/]+"
      ],
      "deny_url_regex": [
        "dekanta\\.com/?$",
        "dekanta\\.com/(?:search|account|cart|checkout)"
      ],
      "max_pages_per_domain": 40
    },
    "worldcooperage.com": {
      "stay_with_current_allow": true  /* Already has good allow_url_regex */,
      "add_deny": [
        "worldcooperage\\.com/shop/(?:category|tag)/",
        "worldcooperage\\.com/product\\?[pg]="
      ]
    }
  }
}
```

---

#### **CATEGORY C: Technical & Regulatory Resources** (Need precision)

| Resource | Current Rule | Problem | Recommendation |
|---|---|---|---|
| **TTB Distilled Spirits** | None | Capturing process docs, PDFs (some unreadable) | Add allow_url_regex + deny PDFs with low text |
| **UK HMRC Excise Notice 39** | Domain rules exist | Good but too broad; gov.uk homepage still captured | Tighten site-level rules |
| **NRIB (National Research Institute of Brewing)** | None | Japanese PDFs, many off-topic (sake, shochu) | Add strict allow + language filter |
| **Japanese NTA** | None | Homepage captured; navigation pages | Add allow_url_regex for whisky sections only |

**Action:**

```json
{
  "sites": {
    "TTB Distilled Spirits": {
      "allow_url_regex": [
        "ttb\\.gov/.*distilled.*spirits",
        "ttb\\.gov/.*labeling",
        "ttb\\.gov/.*formula",
        "ttb\\.gov/.*permit"
      ],
      "deny_url_regex": [
        "\\.pdf$"  /* Avoid PDFs; they're often unreadable by crawler */
      ],
      "deny_query_params": ["search", "page"]
    },
    "National Research Institute of Brewing (NRIB)": {
      "allow_url_regex": [
        "nrib\\.go\\.jp/.*(?:whisky|whiskey)",
        "nrib\\.go\\.jp/English/(?:whisky|spirits)",
        "nrib\\.go\\.jp/sake/story/.*[Ww]hisky"
      ],
      "deny_url_regex": [
        "nrib\\.go\\.jp/sake/story/.*(?:[Ss]ake|[Ss]hochu|[Ww]ine)",
        "\\.pdf$"
      ],
      "max_pages_per_domain": 15
    },
    "Japan National Tax Agency - Whisky Labelling Standards": {
      "allow_url_regex": [
        "nta\\.go\\.jp/.*(?:whisky|liqueur|spirits)",
        "nta\\.go\\.jp/.*excise"
      ],
      "deny_url_regex": [
        "nta\\.go\\.jp/?$",
        "nta\\.go\\.jp/english/?$",
        "nta\\.go\\.jp/(?:tax|benefits|childcare)"
      ],
      "max_pages_per_domain": 10
    }
  }
}
```

---

#### **CATEGORY D: Retail & Information Portals** (Need homepage suppression)

| Resource | Current Rule | Problem | Recommendation |
|---|---|---|---|
| **Australian Distillers Association** | None | Homepage loads but is nav-only | Add homepage deny |
| **Whisky Magazine** | deny_url_regex but incomplete | Search results still captured | Expand deny rules |
| **ScotchWhisky.com** | Partial rules | Magazine sections not excluded | Add comprehensive section breaks |

**Action:**

```json
{
  "domains": {
    "australiandistillers.org.au": {
      "allow_url_regex": [
        "australiandistillers\\.org\\.au/(?:resources|members|community|news)/",
        "australiandistillers\\.org\\.au/distillery/[^/]+"
      ],
      "deny_url_regex": [
        "australiandistillers\\.org\\.au/?$",
        "australiandistillers\\.org\\.au/(?:login|join|membership)(?:/|$)"
      ],
      "max_pages_per_domain": 20
    },
    "whiskymag.com": {
      "deny_url_regex": [
        "whiskymag\\.com/search/",
        "whiskymag\\.com/content/latest-additions",
        "whiskymag\\.com/content/[^/]+\\?",
        "[?&]sort=|[?&]order=|[?&]view="
      ],
      "max_pages_per_domain": 35
    },
    "scotchwhisky.com": {
      "deny_url_regex": [
        "scotchwhisky\\.com/magazine/(?:news|in-depth)(?:/latest)?[?&]p=\\d+",
        "scotchwhisky\\.com/magazine/(?:essentials|knowledge)$"
      ],
      "max_pages_per_domain": 40
    }
  }
}
```

---

## PART 3: NEW CATEGORIZATION — Resource-Type Filtering

**Key insight from audit:** Different resource types accumulate junk differently. Proposed approach:

### **Resource Type: "Blog" (High tag/pagination risk)**

**Examples:** Nip of Courage, Whisky Waffle, Whisky Advocate, Malt Review

**Default limits:**
- `max_pages: 30` (avoid drowning in content)
- `deny_url_regex: ["/(?:tag|category|archive)"]` (override if blog manages these well)
- `deny_query_params: ["page", "paged", "p"]`

### **Resource Type: "Retail" (Product discovery focus)**

**Examples:** The Distiller, Dekanta, Whisky Auction

**Default limits:**
- `allow_url_regex`: product pages ONLY
- `deny_url_regex: ["/(?:profile|user)/", "/cart", "/account"]`
- `max_pages: 40-50`

### **Resource Type: "Regulatory" (Precision + depth limit)**

**Examples:** TTB, NTA, HMRC, ATO

**Default limits:**
- `allow_url_regex`: REQUIRED (must specify whisky-relevant sections)
- `deny_query_params: ["search", "page"]` (avoid search results)
- `max_pages: 15-20` (highly curated; quality over quantity)
- Add: `min_visible_text_chars: 600` (regulatory pages should be substantive)

### **Resource Type: "Trade Body" (Balanced)**

**Examples:** Scotch Whisky Association, Irish Whiskey Association

**Default limits:**
- `max_pages: 25-35` (good content density)
- Standard tag/pagination denies
- Keep news sections (value-add)

### **Resource Type: "Technical/Science" (Depth + relevance)**

**Examples:** Whisky Science, Institute of Brewing & Distilling, AWRI

**Default limits:**
- `min_visible_text_chars: 700` (technical content should be detailed)
- `max_pages: 20` (fewer pages, higher signal)
- `deny_url_regex`: homepage, index, tag pages only

---

## PART 4: IMPLEMENTATION ROADMAP

### **Phase 1: Critical Gaps (Do First)**
1. Add global deny rules for `-metadata.md`, homepages, user profiles ← **Immediate** (~20 min impact)
2. Add domain rules for Nip of Courage, The Whisky Club Australia ← **Quick win** (~15 files eliminated)
3. Add allow_url_regex for regulatory/technical resources (TTB, NRIB, NTA, etc.) ← **Precision boost**

### **Phase 2: Optimization (Medium Effort)**
4. Set `max_pages_per_domain` limits by resource type
5. Tighten allow_url_regex for e-commerce (Dekanta, The Distiller)
6. Expand deny rules for pagination variants

### **Phase 3: Validation (Test)**
7. Run dry-run crawl with new rules; compare file count + relevance scores
8. Manually audit 5 resources (1 from each type) post-refinement
9. Adjust thresholds if needed

**Expected outcomes:**
- File count reduction: 25-35%
- Average relevance score improvement: +15-20 points
- Noise elimination: 90% of metadata/tag/pagination files gone

---

## PART 5: SPECIFIC RECOMMENDATIONS BY RESOURCE

### 🔴 CRITICAL (Add rules before next crawl)

```json
{
  "domains": {
    "nipofcourage.com": {
      "deny_url_regex": [
        "/news/tags/[^/]+/?$",
        "/news/hashtags/\\d+/?$"
      ],
      "deny_query_params": ["page"],
      "max_pages_per_domain": 25
    },
    "thewhiskyclub.com.au": {
      "deny_query_params": ["yoReviewsPage", "page"],
      "deny_url_regex": [
        "/journal\\?",
        "/journal/(?:1|2|3|4|5|6|7|8|9)/?$"  /* Pagination pages */
      ],
      "max_pages_per_domain": 30
    },
    "distiller.com": {
      "deny_url_regex": [
        "/profile/[^/]+(?:/(?:collection|tastes|notes|reviews))?/?$"
      ],
      "allow_url_regex": [
        "distiller\\.com/spirits/[^/]+",
        "distiller\\.com/search"
      ],
      "max_pages_per_domain": 50
    },
    "nrib.go.jp": {
      "deny_url_regex": [
        "/sake/story/.*(?:[Ss]ake|[Ss]hochu|[Ww]ine|[Bb]rewing)",
        "\\.pdf$"
      ],
      "allow_url_regex": [
        "nrib\\.go\\.jp/.*[Ww]hisky",
        "nrib\\.go\\.jp/English/spirits/",
        "nrib\\.go\\.jp/English/kan/"
      ],
      "max_pages_per_domain": 15
    },
    "ttb.gov": {
      "allow_url_regex": [
        "ttb\\.gov/regulated-commodities/beverage-alcohol/distilled-spirits",
        "ttb\\.gov/.*labeling",
        "ttb\\.gov/.*formula",
        "ttb\\.gov/.*permit"
      ],
      "deny_url_regex": [
        "\\.pdf$",
        "ttb\\.gov/(?:news|press)/"
      ]
    },
    "dekanta.com": {
      "allow_url_regex": [
        "dekanta\\.com/products/",
        "dekanta\\.com/collections/"
      ],
      "deny_url_regex": [
        "dekanta\\.com/?$",
        "dekanta\\.com/(?:search|account|cart|checkout)",
        "dekanta\\.com/(?:search|filter)"
      ],
      "deny_query_params": ["search", "filter", "sort", "page"],
      "max_pages_per_domain": 40
    }
  }
}
```

### 🟡 HIGH PRIORITY (Next batch)

```json
{
  "domains": {
    "whiskyadvocate.com": {
      "deny_url_regex": [
        "/(?:category|region|spirit-type|distillery)/",
        "/bestof/",
        "/search\\?"
      ],
      "deny_query_params": ["page", "paged"],
      "max_pages_per_domain": 40
    },
    "whiskynotes.be": {
      "deny_url_regex": [
        "/old(?:/\\d+)?/?$",
        "/search\\?",
        "/page/\\d+"
      ],
      "deny_query_params": ["paged"],
      "max_pages_per_domain": 35
    },
    "thewhiskyexchange.com": {
      "allow_url_regex": [
        "thewhiskyexchange\\.com/inspiration/",
        "thewhiskyexchange\\.com/the-best-"
      ],
      "deny_url_regex": [
        "thewhiskyexchange\\.com/p",  /* /p/ = product pages, not articles */
        "thewhiskyexchange\\.com/(?:account|login|cart)"
      ],
      "max_pages_per_domain": 20
    },
    "gov.uk": {
      "keep_existing": true,
      "update_deny_url_regex": [
        /* Add to existing */
        "gov\\.uk/(?:attendance-allowance|browse|services)(?:/|$)"
      ]
    },
    "australiadistillers.org.au": {
      "allow_url_regex": [
        "australiandistillers\\.org\\.au/(?:resources|news|community)/",
        "australiandistillers\\.org\\.au/distillery/"
      ],
      "deny_url_regex": [
        "australiandistillers\\.org\\.au/?$",
        "australiandistillers\\.org\\.au/(?:login|join|membership)"
      ],
      "max_pages_per_domain": 20
    }
  }
}
```

### 🟢 NICE-TO-HAVE (Polish)

```json
{
  "sites": {
    "Whisky Waffle": {
      "add_deny_query_params": ["page"]
    },
    "Malt Review": {
      "add_deny_url_regex": [
        "/(?:archive|tag)/"
      ]
    },
    "Bourbon Pursuit": {
      "keep_current": true,
      /* Already has tag deny */
      "add_max_pages": 25
    },
    "Scotch Whisky Association": {
      "add_deny_url_regex": [
        "scotch-whisky\\.org\\.uk/newsroom/\\?page="
      ]
    }
  }
}
```

---

## PART 6: Testing Checklist

Use this checklist for validation before deploying new rules:

- [ ] **File count reduction:** Compare post-crawl file count vs. pre-refinement baseline
- [ ] **Relevance score:** Audit 10 random files; average score should increase 15+ points
- [ ] **Resource coverage:** Verify top 10 high-value resources still have 15+ pages each
- [ ] **Noise elimination:** Confirm <5% of crawl output is `-metadata.md` or tag pages
- [ ] **Regulatory precision:** Audit TTB, NTA, NRIB; ensure only whisky-relevant pages captured
- [ ] **Blog quality:** Manually verify Nip of Courage, Whisky Notes have diverse, substantive posts (no tag repeats)

---

## APPENDIX: Reference Implementation

See below for full `resource_prefilter_rules.json` structure with all recommendations integrated:

```json
{
  "version": 2,
  "global": {
    "min_visible_text_chars": 450,
    "deny_query_params": [
      "showComment",
      "yoReviewsPage",
      "comment_id",
      "reply_comment_id",
      "page",
      "paged",
      "p",
      "search",
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "ref",
      "fbclid"
    ],
    "deny_url_regex": [
      /* EXISTING RULES */
      "/tag/",
      "/category/",
      "/archive(?:s)?(?:/|$)",
      "/search(?:/|\\?)",
      "[?&]p=\\d+",
      "/page/\\d+/?$",
      "/newsroom(?:/|$)",
      "/latest-news(?:/|$)",
      "/(?:feed|feeds)(?:/|$)",
      "/rss(?:/|$)",
      "\\.xml(?:$|\\?)",
      "/newsletter(?:/|$)",
      "/subscribe(?:/|$)",
      "/account(?:/|$)",
      "/cart(?:/|$)",
      "/login(?:/|$)",
      "/register(?:/|$)",
      "/user/(?:login|register)(?:/|$)",
      "chrome-error://",
      
      /* NEW: Homepage & Navigation */
      "(?:^|/)(?:home|index)(?:\\.html)?(?:/)?$",
      "(?:^|/)blog(?:/)?$",
      "(?:^|/)news(?:/)?$",
      "(?:^|/)articles?(?:/)?$",
      
      /* NEW: User & Profile Pages */
      "/(?:user|profile|member)/[^/]+(?:/(?:posts|collection|tastes|followers))?(?:/)?$",
      
      /* NEW: E-commerce Noise */
      "[?&](?:filter|sort|view)=",
      
      /* NEW: Metadata & Tracking */
      "-metadata\\.md$",
      "(?:sitemap|toc|table-of-contents)",
      
      /* NEW: Error Pages */
      "(?:404|error|not-found|success|thank-you)"
    ]
  },
  "domains": {
    /* EXISTING RULES – keep as-is */
    "gov.uk": { /* ... */ },
    "thewhiskyclub.com.au": { /* ... */ },
    
    /* NEW CRITICAL RULES */
    "nipofcourage.com": {
      "deny_url_regex": [
        "/news/tags/[^/]+/?$",
        "/news/hashtags/\\d+/?$"
      ],
      "max_pages_per_domain": 25
    },
    "distiller.com": {
      "deny_url_regex": [
        "/profile/[^/]+(?:/(?:collection|tastes|notes|reviews))?/?$"
      ],
      "allow_url_regex": [
        "distiller\\.com/spirits/",
        "distiller\\.com/search"
      ],
      "max_pages_per_domain": 50
    },
    "nrib.go.jp": {
      "allow_url_regex": [
        "nrib\\.go\\.jp/.*[Ww]hisky",
        "nrib\\.go\\.jp/English/spirits/",
        "nrib\\.go\\.jp/English/kan/"
      ],
      "deny_url_regex": [
        "/sake/story/.*(?:[Ss]ake|[Ss]hochu|[Ww]ine)",
        "\\.pdf$"
      ],
      "max_pages_per_domain": 15
    },
    "ttb.gov": {
      "allow_url_regex": [
        "ttb\\.gov/regulated-commodities/beverage-alcohol/distilled-spirits",
        "ttb\\.gov/.*labeling",
        "ttb\\.gov/.*formula"
      ],
      "deny_url_regex": ["\\.pdf$"]
    },
    "dekanta.com": {
      "allow_url_regex": [
        "dekanta\\.com/products",
        "dekanta\\.com/collections"
      ],
      "deny_url_regex": [
        "dekanta\\.com/?$",
        "dekanta\\.com/(?:account|cart|checkout)"
      ],
      "max_pages_per_domain": 40
    }
    /* ... more domains ... */
  },
  "sites": {
    /* EXISTING RULES – keep as-is */
    
    /* NEW CATEGORICAL RULES BY TYPE */
    "TTB Distilled Spirits": { /* ... */ },
    "National Research Institute of Brewing (NRIB)": { /* ... */ }
  }
}
```

---

## QUESTIONS FOR NEXT STEP

1. **Dry-run deployment:** Should I generate the complete updated `resource_prefilter_rules.json` now?
2. **Regex testing:** Would you like me to test these regexes against sample URLs from crawl_markdown to verify they work?
3. **Priority resources:** Which 3-5 resources should we prioritize for tightest filtering?
4. **Max page limits:** Are the proposed `max_pages_per_domain` values (15-50 range) aligned with your strategy, or should they be adjusted?

