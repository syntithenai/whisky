# Google Analytics & AdSense Admin Setup Guide

**Date:** 16 April 2026  
**Purpose:** Complete setup instructions for Google admin infrastructure required before code implementation  
**Status:** Ready for execution

---

## Table of Contents

1. [Overview & Prerequisites](#overview--prerequisites)
2. [Phase 1: Google Account & Domain Setup](#phase-1-google-account--domain-setup)
3. [Phase 2: Google Analytics 4 (GA4) Configuration](#phase-2-google-analytics-4-ga4-configuration)
4. [Phase 3: Google AdSense Account Setup](#phase-3-google-adsense-account-setup)
5. [Phase 4: Google Consent Mode Configuration](#phase-4-google-consent-mode-configuration)
6. [Phase 5: GA4 Event Tracking & Conversions](#phase-5-ga4-event-tracking--conversions)
7. [Phase 6: AdSense Ad Units & Placement](#phase-6-adsense-ad-units--placement)
8. [Phase 7: Validation & Testing](#phase-7-validation--testing)
9. [Reference: IDs and Credentials to Save](#reference-ids-and-credentials-to-save)
10. [Troubleshooting & Common Issues](#troubleshooting--common-issues)

---

## Overview & Prerequisites

### What We're Setting Up

- **Google Analytics 4 (GA4)**: Tracks page views, engagement, custom events, and user behavior
- **Google AdSense**: Monetization via targeted ads on eligible pages
- **Google Consent Mode**: Privacy-compliant data collection gate-keepn
- **Site Verification**: Proves you own the domain for both GA4 and AdSense

### Prerequisites

- Google Account (personal or workspace) with admin access
- Domain ownership (for site verification)
- DNS or file upload access to verify domain ownership
- GitHub Pages or hosting setup (to host verification files if needed)

### Important Notes

- **Use your primary Google Account** for both GA4 and AdSense — they should be linked to the same account
- **Save all IDs as you generate them** — refer to the [Reference section](#reference-ids-and-credentials-to-save) at the end
- **Do NOT share credentials** — these are sensitive and should be stored securely (use environment variables in your deployment)
- **Timeline:** Expect 2–4 hours for full setup; AdSense approval may take 1-3 weeks

---

## Phase 1: Google Account & Domain Setup

### Step 1.1: Prepare Your Google Account

1. Sign in to your Google Account (or create one at [accounts.google.com](https://accounts.google.com))
   - Use a professional or primary account that you'll keep long-term
   - **Never use a throwaway account** — if you lose access, you lose all analytics and ad revenue

2. Enable 2-Step Verification (highly recommended):
   - Go to [myaccount.google.com/security](https://myaccount.google.com/security)
   - Click "2-Step Verification" → "Get Started"
   - Follow the prompts to secure your account

3. Create a **Gmail label or folder** to organize notifications:
   - Label: `Google Services` (or similar)
   - You'll receive important alerts from GA4 and AdSense here

### Step 1.2: Verify Domain Ownership

This is required for both GA4 and AdSense to trust your domain.

#### Option A: DNS TXT Record (Recommended for Production)

1. Go to [Google Search Console](https://search.google.com/search-console)
2. Click **"Add Property"** → select **"URL Prefix"** → enter `https://yourdomain.com`
3. Click **"Continue"** → select **"DNS record"** verification method
4. Google will show a TXT record like:
   ```
   google-site-verification=abc123def456ghi789jkl...
   ```
5. Log into your domain registrar (GoDaddy, Namecheap, Route 53, etc.) and add this TXT record to DNS:
   - Host: `@` or `yourdomain.com`
   - Type: `TXT`
   - Value: `google-site-verification=abc123def456ghi789jkl...`
6. Wait 5–30 minutes for DNS propagation
7. Return to Search Console and click **"Verify"**
8. ✅ You'll see "Verification successful"

#### Option B: HTML File Upload (For GitHub Pages or similar)

1. Go to [Google Search Console](https://search.google.com/search-console) → **"Add Property"**
2. Select **"URL Prefix"** → enter your domain
3. Choose **"HTML file"** verification method
4. Download the file: `google[verification-code].html`
5. Upload it to your website root:
   - For GitHub Pages: add to `build/github-pages/` or equivalent
   - Ensure it's accessible at: `https://yourdomain.com/google[verification-code].html`
6. Return to Search Console and click **"Verify"**

**Save:** Your domain is now verified with Google Search Console.

---

## Phase 2: Google Analytics 4 (GA4) Configuration

### Step 2.1: Create a Google Analytics Account

1. Go to [analytics.google.com](https://analytics.google.com)
2. Click **"Start measuring"** (if new) or **"Admin"** (if existing)
3. In the **Admin** panel, click **"Create Account"**
4. Fill in the account details:
   - **Account name:** `Whisky Lessons` (or your site name)
   - **Data sharing settings:** Check all boxes (improves recommendations)
   - Click **"Next"**
5. Create a **property**:
   - **Property name:** `Whisky Lessons - Production`
   - **Reporting time zone:** UTC or your preferred timezone
   - **Currency:** USD (or your primary revenue currency)
   - Click **"Next"**
6. Set up **data stream**:
   - **Select platform:** `Web`
   - **Website URL:** `https://yourdomain.com` (prod domain)
   - **Stream name:** `Production Web Stream`
   - Click **"Create stream"**

**Save:** Note the **Measurement ID** displayed (format: `G-XXXXXXXXXX`)

### Step 2.2: Create a Staging Property (Recommended)

Repeat Step 2.1 for a staging environment if you want to test without polluting production data:

- **Property name:** `Whisky Lessons - Staging`
- **Data stream URL:** `http://localhost:8080` or your staging domain
- **Stream name:** `Staging Web Stream`

**Save:** Staging Measurement ID

### Step 2.3: Configure Data Retention

1. In GA4, go to **Admin** → **Account Settings** → **Data Retention**
2. Set retention to **14 months** (maximum for free tier) or as needed for compliance
3. Ensure **"Reset on new engagement"** is ON for accurate session tracking

### Step 2.4: Set Up Internal Traffic Filters

To avoid polluting analytics with your own test traffic:

1. Go to **Admin** → **Data Streams** → **Web Stream Settings** → **Tagging Settings** → **Internal Traffic Filtering**
2. In **Admin** → **Data Filters**, create a filter:
   - **Filter name:** `Internal traffic - Office`
   - **Filter type:** `Internal traffic`
   - **Traffic type:** Select `Internal traffic`
   - **IP address:** Add your office/home IP or internal network range
   - **Enable filter:** Turn ON for testing, OFF before production launch

**Note:** You can check your IP at [whatismyipaddress.com](https://www.whatismyipaddress.com)

---

## Phase 3: Google AdSense Account Setup

### Step 3.1: Create AdSense Account

1. Go to [adsense.google.com](https://adsense.google.com)
2. Click **"Sign in"** or **"Get started"**
3. Use the **same Google Account** as your GA4 setup
4. Fill in the form:
   - **Website URL:** `https://yourdomain.com`
   - **Email address:** Your primary Google account email
   - **Country:** Where you reside
   - **Accept terms:** Check all boxes
5. Click **"Create account"**

### Step 3.2: Verify Domain Ownership in AdSense

Google may automatically detect your Search Console verification. If not:

1. In AdSense, go to **Account** → **Settings** → **Account Information**
2. Look for **"Verified sites"** section
3. Click **"Add site"** and enter `https://yourdomain.com`
4. Choose verification method:
   - **Automatic** (if Search Console is already verified)
   - **Manual** (add the verification meta tag to your page template)

**For manual verification:**
- Google provides a meta tag like: `<meta name="google-site-verification" content="abc123def456...">`
- Add this to the `<head>` of your site template *temporarily*
- Click **"Verify"** in AdSense
- Remove the tag once verified

### Step 3.3: Wait for AdSense Approval

1. Multiple reviews occur:
   - **Initial review (1–3 days):** Google checks your site content and policies
   - **Ads review (up to 3 weeks):** Google reviews ad format compliance
   - **Payment setup (optional):** Requires tax form if earnings exceed $100/year

2. Monitor AdSense email for updates and any policy issues

**Important:** Do NOT place ad code on your site until you receive "Approval confirmed" email

### Step 3.4: Complete Payment & Tax Setup (After Approval)

1. In AdSense, go to **Payments** → **Payment settings**
2. Click **"Add payee name and address"** and fill in your details
3. Click **"Tax info"** → **"Set up now"**
4. Follow the tax form (W-9 for US, equivalent for your country)
5. Set up a **Google AdSense PIN** for security

---

## Phase 4: Google Consent Mode Configuration

Google Consent Mode allows you to comply with privacy regulations (GDPR, CCPA) while still collecting useful analytics.

### Step 4.1: Understand Consent Mode States

There are **two core consent types** in GA4:

| Consent Type | Meaning | Impact |
|---|---|---|
| `analytics_storage` | User allows analytics tracking | Full event collection |
| `ad_storage` | User allows ad cookies | Targeted ads, conversion tracking |

**Default state** (before user consent):
- `analytics_storage`: `'denied'` (don't collect analytics until user opts in)
- `ad_storage`: `'denied'` (don't serve targeted ads)

### Step 4.2: Implement Consent Mode in GA4

1. Go to GA4 → **Admin** → **Account Settings** → **Data Collection and Privacy**
2. Enable **"Consent settings"**:
   - Click **"Enable consent settings"**
   - Check **"Analytics storage"**
   - Check **"Ad storage"**
3. Set default to **"User consent required"** for both

### Step 4.3: Create Your Consent Banner Configuration

Decide your consent strategy:

**Option A: Consent Banner Required (Full GDPR/CCPA Compliance)**
- Show banner before any tracking
- User must actively accept for analytics and ads
- Set GA4 defaults to `'denied'`
- Use a consent management platform (CMP) like Cookiebot, OneTrust, or open-source Plausible
- **See Phase 9 for implementation details**

**Option B: Consent-Mode Implied (Privacy Policy + Opt-Out)**
- Show privacy policy notice
- Set GA4 defaults to `'granted'` with opt-out link
- *Note: May not satisfy GDPR/CCPA in all contexts*

**Recommendation for whisky site:** Use Option A (Consent Banner Required) given international audience potential.

---

## Phase 5: GA4 Event Tracking & Conversions

### Step 5.1: Define Conversion Events

Conversions are key actions you want to track. For the whisky site:

1. Go to GA4 → **Admin** → **Conversions**
2. Click **"New conversion event"** for each:

#### Conversion 1: Quiz Completion
- **Event name to convert:** `quiz_complete`
- **Description:** `User completed a quiz`
- Save

#### Conversion 2: External Resource Click
- **Event name to convert:** `resource_outbound_click`
- **Description:** `User clicked on external learning resource`
- Save

#### Conversion 3: High Engagement Session
- **Event name to convert:** `high_engagement_session`
- **Description:** `Session with 5+ min on page`
- Save (this will be auto-triggered by custom code)

#### Conversion 4: Search Query
- **Event name to convert:** `site_search`
- **Description:** `User performed site search`
- Save

### Step 5.2: Create Custom Events (In GA4)

GA4 will automatically recognize these events once your code fires them. Pre-create them in GA4 for reporting:

1. In GA4 → **Admin** → **Custom Definitions** → **Custom Events**
2. For each custom event (create if not auto-detected):
   - `content_view`
   - `content_scroll_depth`
   - `resource_outbound_click`
   - `site_search`
   - `quiz_interaction`
   - `distillery_profile_engagement`

3. For each, fill in:
   - **Event name:** (as listed above)
   - **Description:** Purpose of the event
   - **Matching conditions:** Leave as "matches exactly"

### Step 5.3: Create Custom User Properties (Optional but Recommended)

Track custom user attributes for better segmentation:

1. Go to **Admin** → **Custom Definitions** → **Custom User Properties**
2. Create these optional properties:
   - `user_engagement_level` (high/medium/low)
   - `content_category` (phase/resource/distillery/quiz)
   - `is_returning_user` (true/false)

---

## Phase 6: AdSense Ad Units & Placement

**⚠️ Only proceed after receiving "Approval confirmed" email from AdSense**

### Step 6.1: Create Ad Units

Ad units are containers for ads that you'll place on specific routes.

1. Go to AdSense → **Ads** → **By code** → **Ad units**
2. Click **"New ad unit"**
3. Create ads for each placement:

#### Ad Unit 1: In-Content (Phase Pages)
- **Ad unit name:** `Phase In-Content`
- **Ad size:** `Responsive (recommended)` or `300x250` (medium rectangle)
- **Ad type:** `Display ads`
- **Platform:** `Web`
- Click **"Create"**
- **Save:** Copy the **Ad code** (format: `<script type="text/javascript">...</script>`)

#### Ad Unit 2: Mid-Content (Long-form)
- **Ad unit name:** `Mid-Content`
- **Ad size:** `728x90` (leaderboard) or `300x250`
- **Ad type:** `Display ads`
- Click **"Create"**
- **Save:** Copy the **Ad code**

#### Ad Unit 3: Glossary (Light Placement)
- **Ad unit name:** `Glossary Sidebar`
- **Ad size:** `300x250`
- **Ad type:** `Display ads`
- Click **"Create"**
- **Save:** Copy the **Ad code**

#### (Optional) Ad Unit 4: Sticky Mobile
- **Ad unit name:** `Mobile Sticky`
- **Ad size:** `320x50` (mobile banner) or `300x50`
- **Ad type:** `Display ads`
- Click **"Create"**
- **Save:** Copy the **Ad code**

### Step 6.2: Configure Ad Serving & Filtering

1. In AdSense → **Ads** → **Ad review center**:
   - Review and approve/block advertiser categories as needed
   - Block sensitive ads if they conflict with your audience

2. In **Ads** → **Settings**:
   - **Personalization:** Ensure ads are personalized where consent allows
   - **Competitive ads:** Disable competitors if applicable

### Step 6.3: Enable Ads on Specific Pages (Route Targeting)

AdSense does **not** support built-in route/path exclusion at the ad level. **You must manage this in code** by:

- Only inserting the ad code on approved routes
- OR conditional rendering based on route type

**Route Policy (from plan):**

**Ads ENABLED on:**
- Phase/lesson pages (`/phase/*`)
- Resource pages (`/resources/*`)
- Glossary pages (`/glossary/*` - light placement only)

**Ads DISABLED on:**
- Quiz flow pages (`/quiz/*`)
- Cart pages (`/cart/*`)
- Privacy/policy pages (`/privacy`, `/terms`, `/cookie-policy`)
- Home page (optional)

---

## Phase 7: Validation & Testing

### Step 7.1: Validate GA4 Measurement ID

Before deploying code:

1. Go to GA4 → **Admin** → **Data Streams** → **Web Stream**
2. Confirm:
   - **Measurement ID:** `G-XXXXXXXXXX` (copy for code)
   - **Stream URL:** Matches your domain
   - **Status:** "Collecting data" (will show after code is deployed)

### Step 7.2: Test GA4 Events (Using DebugView)

Once code is deployed:

1. Go to GA4 → **Configure** → **DebugView**
2. Open your site in a browser and perform test actions:
   - Load a page → check for `page_view` event
   - Scroll → check for `scroll` event
   - Click outbound link → check for `resource_outbound_click`
   - Submit search → check for `site_search`
3. Events should appear in DebugView within 1–2 seconds
4. If no events appear:
   - Check browser console for JavaScript errors
   - Verify Measurement ID is correct in code
   - Verify Consent Mode allows `analytics_storage`

### Step 7.3: Test AdSense Ad Display

Once ad code is deployed:

1. Go to an approved route (e.g., phase page)
2. Open browser **DevTools** → **Console**
3. Type: `console.log(document.querySelectorAll('[data-ad-client]'))`
4. Should show the ad containers
5. Verify:
   - Ad is visible and styled correctly
   - No layout shift (Cumulative Layout Shift < 0.1 is good)
   - Ad loads within 2–3 seconds

**Do NOT repeatedly click ads during testing** (violates AdSense policies)

### Step 7.4: Test Consent Mode Functionality

1. Open your site's consent banner
2. **Test Deny:** Click "Reject all"
   - Refresh page
   - Check GA4 DebugView → no events should appear
   - Ad should show non-personalized ads only
3. **Test Accept:** Click "Accept all"
   - Refresh page
   - Check GA4 DebugView → events should appear
   - Ad should show personalized ads

---

## Phase 8: Real-Time Monitoring & QA Checklist

### Step 8.1: Live Monitoring Dashboard

1. Create a **GA4 Real-Time Report** for launch day:
   - Go to GA4 → **Reports** → **Realtime**
   - Monitor active users and events in real-time
   - Set up alerts for anomalies

2. Go to AdSense → **Performance reports**:
   - Monitor impressions, clicks, and RPM hourly
   - Watch for sudden drops (indicates ad serving issues)

### Step 8.2: QA Checklist Before Production Launch

- [ ] GA4 Measurement ID is correct and events appear in DebugView
- [ ] AdSense approval email received and ad units created
- [ ] Ad code deployed only on approved routes
- [ ] Consent mode tests pass (deny/accept both work)
- [ ] Internal traffic filter is applied (to exclude your test traffic)
- [ ] All conversion events are defined in GA4
- [ ] Privacy policy is updated with analytics and ad language
- [ ] Consent banner is styled and functional
- [ ] No JavaScript errors in browser console
- [ ] Layout Shift is acceptable (CLS < 0.1)
- [ ] Mobile responsiveness verified for ads

---

## Phase 9: Create Dashboards (Optional but Recommended)

### Step 9.1: GA4 Custom Reports

Create these reports in GA4 for ongoing monitoring:

1. **Content Popularity Report:**
   - Dimensions: Page Title, Page Path
   - Metrics: Users, Sessions, Engagement Rate, Average Session Duration
   - Filter: Exclude test traffic

2. **Engagement Quality Report:**
   - Dimensions: Event Name
   - Metrics: Event Count, Unique Events
   - Event filter: `content_scroll_depth`, `resource_outbound_click`, `quiz_*`

3. **Conversion Report:**
   - Dimensions: Conversion Event Name
   - Metrics: Conversion Count, Conversion Rate

---

## Reference: IDs and Credentials to Save

**Save these securely (use environment variables, never hardcode in public repos):**

- [ ] **Google Account Email:** `_______________________`
- [ ] **GA4 Measurement ID (Production):** `G-_______________________`
- [ ] **GA4 Measurement ID (Staging):** `G-_______________________`
- [ ] **GA4 Property ID (Production):** `_______________________`
- [ ] **GA4 Property ID (Staging):** `_______________________`
- [ ] **AdSense Client ID:** `ca-pub-_______________________`
- [ ] **AdSense Site Verification ID:** `_______________________`
- [ ] **Verified Domain:** `_______________________`
- [ ] **Google Search Console URL:** `_______________________`

### Where to Store These

**Environment Variables** (.env file - NOT committed to git):
```
GA4_MEASUREMENT_ID_PROD=G-XXXXXXXXXX
GA4_MEASUREMENT_ID_STAGING=G-XXXXXXXXXX
ADSENSE_CLIENT_ID=ca-pub-XXXXXXXXXX
```

**Secure Vault** (e.g., 1Password, LastPass, AWS Secrets Manager):
- Store Google Account recovery codes
- Store AdSense verification details
- Document access procedures for team

---

## Troubleshooting & Common Issues

### Issue: GA4 Not Collecting Events

**Symptoms:** DebugView shows no events despite code being deployed

**Solutions:**
1. Verify Measurement ID matches the one in GA4 property
2. Check browser console for JavaScript errors
3. Confirm consent status allows `analytics_storage`
4. Wait 5–10 minutes (data takes time to appear)
5. Verify domain matches GA4 web stream domain
6. Check AdBlocker extensions (temporarily disable for testing)

### Issue: AdSense Approval Takes Too Long

**Symptoms:** "Review of your site is in progress" message after 3+ weeks

**Solutions:**
1. Verify domain ownership in Search Console
2. Ensure sufficient content on site (minimum 10–20 pages)
3. Check Privacy Policy is published and complete
4. Verify no policy violations (malware, adult content, etc.)
5. Contact AdSense support if delayed beyond 3 weeks

### Issue: Ads Not Displaying

**Symptoms:** Ad slots are empty or showing blank space

**Solutions:**
1. Verify AdSense approval email received
2. Check ad code is correctly inserted in approved routes only
3. Disable AdBlocker extensions temporarily
4. Clear browser cache and cookies
5. Test in a private/incognito browser window
6. Check AdSense → **Performance reports** for "Impressions" metric (if 0, ads aren't serving)

### Issue: Consent Banner Not Blocking Tracking

**Symptoms:** GA4 events appear even after clicking "Reject All"

**Solutions:**
1. Verify `dataLayer.push()` is called with correct consent object
2. Check Google Tag Manager (if used) has correct trigger settings
3. Verify `window.gtag` function checks consent state
4. Reload page after changing consent settings
5. Test in different browser/device

### Issue: AdSense Ads Causing Layout Shift

**Symptoms:** Page jumps or shifts when ads load (high CLS)

**Solutions:**
1. Reserve space for ad unit (use fixed height div with `min-height` or `aspect-ratio`)
2. Use lazy loading for ads (`loading="lazy"`)
3. Reduce ad unit count on page
4. Test in Google PageSpeed Insights and check CLS metric
5. Consider sticky positioning only for mobile (not desktop)

---

## Final Checklist Before Deployment

- [ ] Read and approved the event taxonomy (Phase 5)
- [ ] Decided on consent mode strategy (Phase 4)
- [ ] Completed domain verification (Phase 1)
- [ ] GA4 account created and Measurement ID saved (Phase 2)
- [ ] AdSense account approved and ad units created (Phase 3 & 6)
- [ ] Privacy policy updated with analytics and ad language
- [ ] Conversion events defined in GA4 (Phase 5)
- [ ] Ad placement strategy documented (ads disabled on quiz/cart/policy pages)
- [ ] All IDs saved securely in environment (Reference section)
- [ ] QA checklist completed (Phase 8)
- [ ] Ready for code implementation (next phase)

---

## Next Steps

Once all admin setup is complete:

1. Notify dev team that GA4 Measurement ID and AdSense Client ID are ready
2. Move to **Code Implementation Phase:**
   - Inject GA4 script in page template
   - Add event firing for custom actions
   - Add consent banner logic
   - Insert ad code on approved routes
   - Test in staging environment first
3. Monitor launch day with real-time dashboards
4. Collect first week of data and adjust ad placement if needed

---

**Document Status:** Ready for execution  
**Last Updated:** 16 April 2026  
**Maintained By:** [Your Name/Team]
