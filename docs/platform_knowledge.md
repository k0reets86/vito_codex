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

## Threads API
- Threads API uses OAuth via Meta and requires an Instagram account for access; supported endpoints are limited. citeturn6search0

---

Next platforms queued: Amazon Seller Central, Etsy, eBay (full), Shopify GraphQL Admin details, Gumroad, Ko‑fi, Payhip, Lemon Squeezy, Pinterest, TikTok, Instagram, Threads, YouTube, Reddit, Substack, Medium, Discord, LinkedIn, WooCommerce.
