(function () {
  const cfg = window.WHISKY_ANALYTICS_CONFIG || {};
  const ga4MeasurementId = String(cfg.ga4MeasurementId || "").trim();
  const adsenseClientId = String(cfg.adsenseClientId || "").trim();
  const adsenseSlotInContent = String(cfg.adsenseSlotInContent || "").trim();
  const adsenseSlotMidContent = String(cfg.adsenseSlotMidContent || "").trim();

  const CONSENT_KEY = "whiskyConsentV1";
  const SCROLL_THRESHOLDS = [25, 50, 75, 90];

  let gtagInitialized = false;
  let gtagConfigured = false;
  let adScriptLoaded = false;
  let currentPath = normalizePath(window.location.pathname || "/");
  let firedScrollThresholds = new Set();

  function normalizePath(pathname) {
    if (!pathname) {
      return "/";
    }
    if (pathname.length > 1 && pathname.endsWith("/")) {
      return pathname.slice(0, -1);
    }
    return pathname;
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function getStoredConsent() {
    try {
      const parsed = JSON.parse(localStorage.getItem(CONSENT_KEY) || "null");
      if (!parsed || typeof parsed !== "object") {
        return null;
      }
      return {
        analytics: !!parsed.analytics,
        ads: !!parsed.ads,
        updatedAt: String(parsed.updatedAt || ""),
      };
    } catch (_err) {
      return null;
    }
  }

  function saveConsent(consent) {
    localStorage.setItem(
      CONSENT_KEY,
      JSON.stringify({
        analytics: !!consent.analytics,
        ads: !!consent.ads,
        updatedAt: nowIso(),
      })
    );
  }

  function hasAnsweredConsent() {
    return !!getStoredConsent();
  }

  function ensureDataLayer() {
    window.dataLayer = window.dataLayer || [];
    if (!window.gtag) {
      window.gtag = function gtag() {
        window.dataLayer.push(arguments);
      };
    }
  }

  function updateConsentMode(consent) {
    if (!window.gtag) {
      return;
    }
    window.gtag("consent", "update", {
      analytics_storage: consent.analytics ? "granted" : "denied",
      ad_storage: consent.ads ? "granted" : "denied",
      ad_user_data: consent.ads ? "granted" : "denied",
      ad_personalization: consent.ads ? "granted" : "denied",
    });
  }

  function ensureGtag() {
    if (!ga4MeasurementId) {
      return;
    }
    ensureDataLayer();

    if (!gtagInitialized) {
      window.gtag("js", new Date());
      window.gtag("consent", "default", {
        analytics_storage: "denied",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
      });
      gtagInitialized = true;

      const gtagScript = document.createElement("script");
      gtagScript.async = true;
      gtagScript.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ga4MeasurementId);
      document.head.appendChild(gtagScript);
    }

    const consent = getStoredConsent();
    if (consent) {
      updateConsentMode(consent);
      if (consent.analytics && !gtagConfigured) {
        window.gtag("config", ga4MeasurementId, {
          anonymize_ip: true,
          send_page_view: false,
        });
        gtagConfigured = true;
      }
    }
  }

  function analyticsEnabled() {
    const consent = getStoredConsent();
    return !!(consent && consent.analytics && ga4MeasurementId);
  }

  function adsEnabled() {
    const consent = getStoredConsent();
    return !!(consent && consent.ads && adsenseClientId);
  }

  function trackEvent(name, params) {
    if (!analyticsEnabled()) {
      return;
    }
    ensureGtag();
    if (!window.gtag) {
      return;
    }
    window.gtag("event", name, params || {});
  }

  function contentMeta(pathname) {
    const path = normalizePath(pathname || currentPath);
    const parts = path.split("/").filter(Boolean);
    let contentType = "page";
    let contentId = "";

    if (path === "/whisky-lessons" || path === "/the-whisky-course" || /^\/phase-\d+$/.test(path)) {
      contentType = "phase";
      contentId = parts[0] || "whisky-lessons";
    } else if (path.startsWith("/resources")) {
      contentType = "resource";
      contentId = parts[1] || "resources";
    } else if (path.startsWith("/distillery")) {
      contentType = "distillery";
      contentId = parts[1] || "distillery";
    } else if (path.startsWith("/glossary")) {
      contentType = "glossary";
      contentId = "glossary";
    } else if (path.startsWith("/quizzes")) {
      contentType = "quiz";
      contentId = "quizzes";
    } else if (path.startsWith("/products")) {
      contentType = "product";
      contentId = parts[1] || "products";
    }

    return {
      contentType: contentType,
      contentId: contentId,
      slug: parts[parts.length - 1] || "home",
      path: path,
    };
  }

  function trackPage(pathname, pageTitle) {
    const meta = contentMeta(pathname);
    trackEvent("page_view", {
      page_title: pageTitle || document.title,
      page_path: meta.path,
      page_location: window.location.href,
    });
    trackEvent("content_view", {
      content_type: meta.contentType,
      content_id: meta.contentId,
      slug: meta.slug,
      section: meta.path,
    });
  }

  function installOutboundClickTracking() {
    document.addEventListener(
      "click",
      function (event) {
        const link = event.target && event.target.closest ? event.target.closest("a[href]") : null;
        if (!link) {
          return;
        }
        let targetUrl;
        try {
          targetUrl = new URL(link.href, window.location.href);
        } catch (_err) {
          return;
        }
        if (targetUrl.origin === window.location.origin) {
          return;
        }
        trackEvent("resource_outbound_click", {
          target_domain: targetUrl.hostname,
          target_url: targetUrl.href,
          source_page: currentPath,
        });

        if (currentPath.startsWith("/distillery/")) {
          const actionType = /google\.[^/]+\/maps|maps\./i.test(targetUrl.href) ? "map_click" : "website_click";
          trackEvent("distillery_profile_engagement", {
            distillery_id: currentPath.split("/")[2] || "",
            action_type: actionType,
          });
        }
      },
      true
    );
  }

  function installSiteSearchTracking() {
    document.addEventListener(
      "submit",
      function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) {
          return;
        }
        const maybeSearchInput =
          form.querySelector('input[name="q"]') ||
          form.querySelector('input[name="name"]') ||
          form.querySelector('input[type="search"]') ||
          form.querySelector("input");

        if (!maybeSearchInput) {
          return;
        }

        const searchTerm = String(maybeSearchInput.value || "").trim();
        if (!searchTerm) {
          return;
        }

        const resourcesRows = document.querySelectorAll("#resourcesBody tr");
        const dbRows = document.querySelectorAll("#resultsBody tr");
        const resultCount = resourcesRows.length > 0 ? resourcesRows.length : dbRows.length;

        trackEvent("site_search", {
          search_term: searchTerm,
          results_count: resultCount,
          source_page: currentPath,
        });
      },
      true
    );
  }

  function installQuizTracking() {
    document.addEventListener(
      "change",
      function (event) {
        const input = event.target;
        if (!(input instanceof HTMLInputElement)) {
          return;
        }
        if (!input.classList.contains("quiz-option-input")) {
          return;
        }
        const quizId = input.getAttribute("data-quiz") || "";
        trackEvent("quiz_interaction", {
          quiz_id: quizId,
          action_type: "answer_select",
        });
      },
      true
    );

    document.addEventListener(
      "click",
      function (event) {
        const button = event.target && event.target.closest ? event.target.closest("[data-quiz-reset]") : null;
        if (!button) {
          return;
        }
        const quizId = button.getAttribute("data-quiz-reset") || "";
        trackEvent("quiz_interaction", {
          quiz_id: quizId,
          action_type: "reset",
        });
      },
      true
    );
  }

  function updateScrollTrackingForRoute(pathname) {
    currentPath = normalizePath(pathname || currentPath);
    firedScrollThresholds = new Set();
  }

  function installScrollTracking() {
    window.addEventListener(
      "scroll",
      function () {
        const doc = document.documentElement;
        const total = Math.max(1, doc.scrollHeight - window.innerHeight);
        const pct = Math.floor((window.scrollY / total) * 100);
        const meta = contentMeta(currentPath);
        SCROLL_THRESHOLDS.forEach(function (threshold) {
          if (pct >= threshold && !firedScrollThresholds.has(threshold)) {
            firedScrollThresholds.add(threshold);
            trackEvent("content_scroll_depth", {
              content_type: meta.contentType,
              content_id: meta.contentId,
              scroll_percent: threshold,
            });
          }
        });
      },
      { passive: true }
    );
  }

  function isAdEligiblePath(pathname) {
    const path = normalizePath(pathname || currentPath);
    if (path.startsWith("/phase-") || path === "/whisky-lessons" || path === "/the-whisky-course") {
      return true;
    }
    if (path.startsWith("/resources") || path.startsWith("/glossary")) {
      return true;
    }
    return false;
  }

  function ensureAdScript() {
    if (!adsEnabled() || adScriptLoaded) {
      return;
    }
    const script = document.createElement("script");
    script.async = true;
    script.crossOrigin = "anonymous";
    script.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(adsenseClientId);
    document.head.appendChild(script);
    adScriptLoaded = true;
  }

  function pushAd(ins) {
    if (!ins || !window.adsbygoogle) {
      return;
    }
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (_err) {
      // Ignore ad push race errors.
    }
  }

  function createAdSlot(slotId) {
    if (!slotId) {
      return null;
    }
    const wrap = document.createElement("div");
    wrap.className = "whisky-ad-slot";
    const ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", adsenseClientId);
    ins.setAttribute("data-ad-slot", slotId);
    ins.setAttribute("data-ad-format", "auto");
    ins.setAttribute("data-full-width-responsive", "true");
    wrap.appendChild(ins);
    return { wrap: wrap, ins: ins };
  }

  function clearAdSlots() {
    document.querySelectorAll(".whisky-ad-slot").forEach(function (el) {
      el.remove();
    });
  }

  function renderAdSlots(pathname) {
    clearAdSlots();
    if (!adsEnabled() || !isAdEligiblePath(pathname)) {
      return;
    }
    ensureAdScript();

    const wrap = document.querySelector(".wrap");
    if (!wrap) {
      return;
    }

    const blocks = Array.from(wrap.querySelectorAll("section, article, .panel, .markdown-panel, .course-phase"));

    const topSlot = createAdSlot(adsenseSlotInContent);
    if (topSlot) {
      const anchor = blocks[1] || blocks[0] || wrap.firstElementChild;
      if (anchor && anchor.parentNode) {
        anchor.parentNode.insertBefore(topSlot.wrap, anchor.nextSibling);
      } else {
        wrap.appendChild(topSlot.wrap);
      }
      pushAd(topSlot.ins);
    }

    if (blocks.length >= 3) {
      const midSlot = createAdSlot(adsenseSlotMidContent);
      if (midSlot) {
        const midIndex = Math.floor(blocks.length / 2);
        const midAnchor = blocks[midIndex];
        if (midAnchor && midAnchor.parentNode) {
          midAnchor.parentNode.insertBefore(midSlot.wrap, midAnchor);
        } else {
          wrap.appendChild(midSlot.wrap);
        }
        pushAd(midSlot.ins);
      }
    }
  }

  function setupConsentUi() {
    const banner = document.getElementById("consentBanner");
    const acceptBtn = document.getElementById("consentAcceptAll");
    const rejectBtn = document.getElementById("consentRejectAll");
    if (!banner || !acceptBtn || !rejectBtn) {
      return;
    }

    function hideBanner() {
      banner.setAttribute("hidden", "");
    }

    function showBanner() {
      banner.removeAttribute("hidden");
    }

    function applyConsent(consent) {
      saveConsent(consent);
      ensureGtag();
      updateConsentMode(consent);
      if (consent.analytics && !gtagConfigured && ga4MeasurementId) {
        window.gtag("config", ga4MeasurementId, {
          anonymize_ip: true,
          send_page_view: false,
        });
        gtagConfigured = true;
      }
      routeChanged(currentPath, { pageTitle: document.title });
      hideBanner();
    }

    acceptBtn.addEventListener("click", function () {
      applyConsent({ analytics: true, ads: true });
    });

    rejectBtn.addEventListener("click", function () {
      applyConsent({ analytics: false, ads: false });
    });

    if (!hasAnsweredConsent()) {
      showBanner();
    } else {
      hideBanner();
    }
  }

  function routeChanged(pathname, options) {
    const path = normalizePath(pathname || window.location.pathname || "/");
    currentPath = path;
    updateScrollTrackingForRoute(path);
    if (analyticsEnabled()) {
      trackPage(path, options && options.pageTitle ? options.pageTitle : document.title);
    }
    renderAdSlots(path);
  }

  function init() {
    ensureGtag();
    setupConsentUi();
    installOutboundClickTracking();
    installSiteSearchTracking();
    installQuizTracking();
    installScrollTracking();
  }

  init();

  window.whiskyAnalytics = {
    routeChanged: routeChanged,
    trackEvent: trackEvent,
    getConsent: getStoredConsent,
  };
})();
