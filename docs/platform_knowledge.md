# Platform Knowledge Base (VITO)

Updated: 2026-02-23

## Amazon KDP — Paperback/Hardcover
- Use official KDP cover calculator/templates to derive full cover size (back+spine+front) and spine width.
- Paperback cover PDF must include bleed: images to edge must extend 0.125" (3.2mm) beyond trim on all sides; safe text/images at least 0.25" (6.4mm) from edge.
- Spine text only if >79 pages; leave margin around spine text.
- Hardcover cover requires wrap: extend 0.51" (15mm) beyond edge; keep text/images 0.635" (16mm) from edge; hinge margin 0.4" (10mm).

## Amazon KDP — eBook Cover
- Format: JPEG or TIFF.
- Ideal size: 2560 px height x 1600 px width; recommended ~2500 px height for quality.

## Shopify
- Shopify is moving to GraphQL as the definitive Admin API; REST Admin is legacy.
- New public apps submitted after April 1, 2025 must use GraphQL (REST legacy for existing apps).

## eBay
- eBay Developer Program requires creating keysets (Sandbox/Production) in the Application Keys page.
- OAuth uses client_id + client_secret (Basic auth) to obtain tokens; token generation can be done in the Developer Portal UI.

## Etsy (Open API v3)
- Uses OAuth 2.0 Authorization Code grant (with PKCE). Apps must request scopes per endpoint (e.g., listings_w for listing creation). citeturn0search1
- Personal access is default; commercial access requires review and compliance with API terms (no scraping, proper branding notice, caching policy). citeturn0search2

## Shopify Admin API (GraphQL)
- All GraphQL Admin API requests require a valid access token; include `X-Shopify-Access-Token` header. citeturn0search5turn0search6
- Public/custom apps use OAuth via the Dev/Partner dashboard; custom apps in the Shopify admin are authenticated in admin. citeturn0search5turn0search6

## TikTok API (Content Posting / Display)
- Posting requires `video.publish` scope approval and user authorization; unaudited clients’ content is private until audit. citeturn1search0
- Display API requires Login Kit authorization and scopes like `user.info.basic` and `video.list` for access tokens. citeturn1search3

## Pinterest (Developer Policy)
- Access to accounts requires user authorization via access tokens; do not collect login credentials or session cookies. citeturn1search2turn2search2
- Must have a privacy policy when applying for API access; follow policy enforcement and technical docs. citeturn1search2turn2search2

## Printful API
- Legacy API keys are deprecated; use API tokens (private token or public app) with OAuth 2.0. citeturn2search3
- Legacy keys stopped working; new tokens improve security and support scoped permissions. citeturn2search3

## Amazon KDP (Cover & Bleed)
- Paperback cover uses full-cover size with 0.125" (3.2 mm) bleed on all sides; keep content at least 0.25" (6.4 mm) from edges. citeturn0search0turn0search3
- Spine text only for books with more than 79 pages; leave safe margin around spine text. citeturn0search0turn0search3

## Lemon Squeezy API
- REST API at `https://api.lemonsqueezy.com/v1/`, JSON:API headers required (`Accept`/`Content-Type`), uses Bearer API keys. citeturn0search2turn0search3
- Rate limit: 300 requests/min; License API is separate with 60 requests/min. citeturn0search0turn0search1

## Payhip API
- Public API currently limited (coupons, license keys); more endpoints planned. citeturn0search5
- API reference linked from Payhip help center. citeturn0search5

## Gumroad API (third‑party sources; official docs hard to access)
- OAuth API is REST and returns JSON; requires registering an OAuth app for access tokens. citeturn3search0turn3search1
- API base commonly referenced as `https://api.gumroad.com/v2/` with Bearer token. citeturn3search1turn3search5
- Webhook “Ping” configured in Gumroad Settings → Advanced. citeturn3search0turn3search4

### Gumroad Digital Product Specs (official + verified)
- **Send‑to‑Kindle**: Gumroad can send **PDF/MOBI** to Kindle, but **ePub is not supported** for Kindle send; **Send‑to‑Kindle file size limit is 16 MB**. citeturn0search0turn1search0
- **Audio metadata**: Gumroad automatically applies metadata for **MP3/WAV/FLAC/OGG** using product/file name + creator name; the **first uploaded cover image (PNG/JPG)** is encoded as track cover if files lack metadata. citeturn0search1turn1search9
- **Supported browsers**: Gumroad supports the **last four major updates** of Edge/Safari/Chrome/Firefox; outdated browsers may cause upload/purchase issues. citeturn1search8
- **Large file downloads**: Gumroad notes that some ISPs/timeouts can affect large downloads; recommends faster connections or Dropbox send for big files. citeturn1search10

### Gumroad Images (unofficial community standards — use with caution)
These sizes are **not official** Gumroad docs, but commonly used in creator templates:
- **Cover**: 1280×720 px; **Thumbnail**: 600×600 px. citeturn0search3turn0search4turn0search6turn1search3turn1search5
Use these as defaults unless Gumroad UI indicates different requirements.

## YouTube Data API
- Requires API key or OAuth 2.0; uses Google API Console for credentials and quotas. citeturn4search0
- Uploading and managing content requires OAuth 2.0 with scopes like `youtube.upload`. citeturn4search0

## Reddit API
- OAuth 2.0 required for most endpoints; use “installed app” or “web app” credentials. citeturn4search1
- Rate limits are enforced and documented in API rules. citeturn4search1

## Discord API
- Bot access requires creating an application and bot token; permissions are granted via OAuth2. citeturn4search2
- Rate limits are enforced globally and per-route. citeturn4search2

## LinkedIn API
- Most APIs require application approval + OAuth 2.0; marketing/content publishing is gated by product access. citeturn4search3

## WordPress REST API
- WordPress provides REST API endpoints for posts, pages, media, etc. Authentication typically via application passwords or OAuth. citeturn5search0

## WooCommerce API
- WooCommerce exposes a REST API; use consumer key/secret with OAuth 1.0a-style signature or HTTPS basic auth. citeturn5search1

## Medium API
- Publishing via Medium requires OAuth access token and user ID; use official Medium API. citeturn5search2

## Instagram Graph API
- Publishing requires Instagram Business/Creator account connected to a Facebook Page; use Graph API and permissions. citeturn5search3

## Gumroad — Digital Product Policy
- Gumroad keeps a prohibited-products list (age-restricted goods, reselling private-label rights, adult content, financial services, weapons/ammunition, certain services such as bail bonds or telemarketing); violations can trigger removal per the Terms of Service. citeturn4search0turn4search2
- Gumroad’s Risk team may review accounts for high-risk or fraudulent behavior before enabling payouts; repeated policy breaches, suspicious chargebacks, or disallowed content can lead to suspension without payout. citeturn4search2
- Content protection features include unique-to-purchaser download links, optional streaming-only video delivery, and PDF stamping that prints buyer email/date on every page for copyright control. citeturn4search3

## Etsy — Digital Listings
- Instant-download listings honor five files per listing, each capped at 20 MB; supported file types include documents, images, ZIP archives, EPUB, MOBI, video, audio, and printable templates. File names are locked at 70 characters post-upload. citeturn5search0
- Listing photos must be at least 2000 px wide (square 1:1 preferred), use JPG/PNG/GIF in sRGB, and remain below 10 MB; you can add up to 10 images plus one video per listing. citeturn5search5
- Video assets must stay between 5 and 15 seconds, under 100 MB, at 1080p in MP4 format; Etsy removes audio during processing, so keep narration optional. citeturn5search7

## Shopify — Digital Downloads
- The Digital Downloads app lets merchants attach multiple assets per product, each upload limited to 5 GB; variants inherit download assets and you can cap download attempts per order (default unlimited). citeturn6search0
- General admin files (images, PDFs) are limited to 20 MB per file and 20 MP resolution, so compress large imagery before uploading to avoid upload failures. citeturn6search5
- Community reports show a 50-file-per-product ceiling inside the Digital Downloads app even if each file is under 5 GB, so bundle large catalogs into ZIP archives when possible. citeturn6search2

## Ko-fi — Shop Assets and Content Guidelines
- Free Ko-fi creators get 25 GB total asset storage with 2 GB per item; Contributors have 200 GB storage with 5 GB per item and can schedule inventory, control taxes, and add post-purchase messages inside Shop settings. citeturn7search2
- Free posts are limited to 25 MB per image, while Contributors may embed audio up to 200 MB and rely on external video hosts (YouTube, Vimeo, TikTok) for video content. citeturn7search0
- Ko-fi enforces payment-provider rules (PayPal/Stripe), so anything disallowed by those partners—unlicensed goods, prohibited services, or trademark violations—risks removal or account suspension; review Ko-fi’s content policy before publishing. citeturn7search8

## Payhip — Large Digital Files and Controls
- Payhip accepts any file format, up to 5 GB per file, with unlimited storage and bandwidth; bundles and multiple asset uploads are supported, and embed buttons extend purchases beyond the website. citeturn8search0turn8search5
- Built-in protection caps download attempts (default five, adjustable) and offers optional PDF stamping that prints buyer email/date on each page (PDFs must stay under 250 MB for stamping). citeturn8search1
- Payhip also auto-generates license keys for software, refreshes download URLs for existing customers when a product redeploys, and surfaces metadata-rich landing pages for every upload. citeturn8search3


## Threads API
- Threads API uses OAuth via Meta and requires an Instagram account for access; supported endpoints are limited. citeturn6search0

---

Next platforms queued: Amazon Seller Central, Etsy, eBay (full), Shopify GraphQL Admin details, Gumroad, Ko‑fi, Payhip, Lemon Squeezy, Pinterest, TikTok, Instagram, Threads, YouTube, Reddit, Substack, Medium, Discord, LinkedIn, WooCommerce.

## 2026-03-03 Verified Update (Official Sources)

This block supersedes older notes where they conflict.

### Etsy
- Open API v3 authentication uses OAuth 2.0 Authorization Code with PKCE; apps request explicit scopes (for example `listings_w`, `shops_r`).
- Commercial API access is reviewed and can be limited/revoked on policy violations.
- For digital listings, Etsy Help confirms upload/asset limits and supported file types for instant downloads.
- Sources:
  - https://developer.etsy.com/documentation/
  - https://developer.etsy.com/documentation/essentials/authentication/
  - https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings

### Printful
- Printful API is token-based/OAuth-based; store access and status are checked via `/stores`.
- Production operations should always validate store binding before product creation.
- Sources:
  - https://developers.printful.com/
  - https://developers.printful.com/docs/

### X (Twitter)
- Posting and account reads in this project are done through X API v2 with OAuth 1.0a credentials for user context.
- `GET /2/users/me` remains the practical auth probe for token/key validity in runtime.
- Sources:
  - https://developer.x.com/en/docs
  - https://developer.x.com/en/docs/tutorials/authenticating-with-twitter-api-for-enterprise/oauth1-0a-and-user-access-tokens

### Gumroad
- Gumroad API access is OAuth app based; product and account operations require valid token + account state.
- Content/payout restrictions are enforced via Terms and compliance review; operational flows must assume policy checks can block publish/payout.
- Sources:
  - https://gumroad.com/api
  - https://gumroad.com/help/article/289-api
  - https://gumroad.com/help/article/44-content-guidelines
  - https://gumroad.com/terms

### Amazon KDP
- KDP publishing and reporting in VITO should stay browser-based until official API access is available.
- 2FA or account-challenge flows are mandatory account-security controls and must be handled interactively by owner.
- Cover and manuscript requirements should follow current KDP help pages.
- Sources:
  - https://kdp.amazon.com/en_US/help
  - https://kdp.amazon.com/en_US/help/topic/G201113520

### YouTube
- YouTube Data API must be enabled in Google Cloud project; otherwise calls return 403 even with key present.
- Upload/publish operations require OAuth scopes (for example `youtube.upload`), not just API key.
- Sources:
  - https://developers.google.com/youtube/v3
  - https://developers.google.com/youtube/v3/guides/uploading_a_video

### Reddit
- Reddit API in this environment is intentionally disabled (`browser_only`) due owner request and current API constraints.
- Discovery/trend ingestion should use RSS/web/browser paths, not API credentials.
- Sources:
  - https://www.reddit.com/dev/api/
  - https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Overview

### Operational Rules for VITO
- Always run auth probe before live publish (`authenticate` + lightweight read endpoint).
- Prefer dry-run for new integrations; require explicit owner approval for first live action on each platform.
- Treat browser automation as fallback for unavailable/blocked APIs, not as a method to bypass platform security controls.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.

## Mega test task

Stub response: operational output.
