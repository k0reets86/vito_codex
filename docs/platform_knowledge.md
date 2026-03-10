# Platform Knowledge Base (VITO)

Updated: 2026-02-23

## Amazon KDP — Paperback/Hardcover
- Use official KDP cover calculator/templates to derive full cover size (back+spine+front) and spine width.
- Paperback cover PDF must include bleed: images to edge must extend 0.125" (3.2mm) beyond trim on all sides; safe text/images at least 0.25" (6.4mm) from edge.
- Spine text only if >79 pages; leave margin around spine text.
- Hardcover cover requires wrap: extend 0.51" (15mm) beyond edge; keep text/images 0.635" (16mm) from edge; hinge margin 0.4" (10mm).
- Hardcover browser-first runbook update (2026-03-07):
  - exact live fork is the Bookshelf button `+ Create hardcover`
  - live route opens as:
    - `/en_US/title-setup/hardcover/new/details?existing=<ebook_id>&item=<paperback_item_id>`
  - `Hardcover Pricing` route is:
    - `/en_US/title-setup/hardcover/new/pricing?existing=<ebook_id>&item=<paperback_item_id>`
  - pricing page uses real fields:
    - `input[name='data[print_book][amazon_channel][us][price_vat_exclusive]']`
    - same pattern for `uk/de/fr/es/it/nl/pl/se/be/ie`
  - current external blocker:
    - hidden modal `Title creation limit exceeded`
    - text: `You have reached the weekly title creation limit for this format.`
  - do not report hardcover creation as available until this KDP weekly limit clears

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

### Ko-fi — verified browser create/publish runbook (2026-03-08)
- Headless/browser-guess path is unreliable; use screenshot-first headed flow.
- Confirmed exact path:
  - `https://ko-fi.com/shop/settings?productType=0`
  - accept cookie banner if present
  - click `Add Product`
  - modal step:
    - set `#Name`
    - set hidden `#Description`
    - set `#Type='DIGITAL'`
    - click `#shopModalNextStep`
  - editor step on `/shop/items/add`:
    - fill visible `Description`
    - fill `Product summary`
    - preview image goes through the first hidden file input
    - buyer asset file must be uploaded via `Upload a file` file chooser path, not by filling file inputs blindly
    - fill price
    - hidden checkbox `#agreeWithShopTerms` must be set programmatically
    - final submit is exact input `#saveAndPublishButton`
- Confirmed published object:
  - `https://ko-fi.com/s/c6c9031adb`
- Evidence:
  - `runtime/kofi_publish_exact3/01_before_submit.png`
  - `runtime/kofi_publish_exact3/02_after_submit.png`
  - `runtime/kofi_publish_exact3/03_settings_reload.png`
  - `runtime/kofi_publish_exact3/04_public_verify.png`
  - `runtime/kofi_publish_exact3/result.json`
- Anti-patterns:
  - do not trust headless-only Cloudflare results as final truth
  - do not treat generic `Save`/`Publish` button scans as enough on Ko-fi
  - do not treat plain file inputs as the asset uploader; exact `Upload a file` chooser path is required

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
- Official Reddit spam policy treats repeated or unsolicited posting for exposure/financial gain as spam.
- Practical posting rules for VITO:
  - do not use profile posting as the primary distribution route for product promotion
  - prefer real target communities where the content is on-topic and allowed by local rules
  - vary copy and avoid repetitive mass-posting across communities
  - respect subreddit-specific flair, title, link, and media rules before publish
  - expect Automoderator/spam filters to remove commercial-looking first posts even when technically accepted
  - if a community is restricted or approval-limited, approved-user/mod settings may be required before posting
- Verified Reddit blocker for current profile route:
  - new composer reaches GraphQL successfully
  - `CreateProfilePost` fails with `PROFILE_SUBREDDIT_NOEXIST`
  - old.reddit profile/community route can fail with `That was a tricky one. Why don't you try that again.`
  - when this exact combination is present, stop retrying profile posting and switch to community posting runbook
- Verified community-first browser runbook (`r/sideprojects`, 2026-03-08):
  - use subreddit route, not profile route:
    - `https://www.reddit.com/r/sideprojects/submit/?type=TEXT`
  - subreddit rules confirmed in sidebar:
    - `Project Posts Must Include Details`
    - `No Spam or Excessive Self-Promotion`
    - `Flair Appropriately`
  - title field is shadow DOM:
    - host `faceplate-textarea-input[name='title']`
    - real input `#innerTextArea` inside `shadowRoot`
  - body field:
    - `shreddit-composer#post-composer_bodytext [contenteditable='true']`
  - exact flair path:
    - click `#reddit-post-flair-button`
    - click `#view-all-flairs-button`
    - select `#post-flair-radio-input-4` = `Showcase: Purchase Required`
    - click `#post-flair-modal-apply-button`
  - exact submit path:
    - inner shadow button `#inner-post-submit-button`
  - successful GraphQL mutation:
    - `CreatePost`
    - response `ok=true`
    - permalink:
      `https://www.reddit.com/r/sideprojects/comments/1rob46e/built_a_creator_swipefile_kit_and_want_feedback/`
  - anti-patterns:
    - do not use profile posting as main route
    - do not rely on host attribute writes for title/flair
    - do not trust `ValidateCreatePostInput` as success; require final `CreatePost ok=true`

### Operational Rules for VITO
- Always run auth probe before live publish (`authenticate` + lightweight read endpoint).
- Prefer dry-run for new integrations; require explicit owner approval for first live action on each platform.
- Treat browser automation as fallback for unavailable/blocked APIs, not as a method to bypass platform security controls.

## Mega test task

Stub response: operational output.

## 2026-03-06 Field Matrix (Browser-First Runtime)

Цель этого блока: дать VITO практичные требования для заполнения листингов/постов в live-сценариях.

### Etsy (digital listing)
- Заголовок: до 140 символов, теги: до 13 шт., каждый тег до 20 символов.
- Фото листинга: рекомендовано не меньше 2000 px по ширине.
- Digital files: до 5 файлов на листинг, до 20 MB каждый.
- Источники:
  - https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings
  - https://help.etsy.com/hc/en-us/articles/360000344908-How-to-Add-Photos-and-Video-to-Your-Listings

### Etsy — verified browser runbook (draft 4468093570)
- Без явного `target_listing_id` и explicit owner intent не редактировать опубликованные листинги.
- Рабочий режим для цифрового товара: `draft_only=true`, один active draft на задачу.
- Подтвержденные поля/ветки:
  - `title`
  - `description`
  - `price`
  - `digital / instant download`
  - `category`
  - `tags`
  - `materials`
  - `digitalFiles`
  - `listingImages`
- Подтвержденный путь для digital file:
  - editor `#details`
  - блок `Цифровые файлы`
  - hidden generic `input[type=file]`
  - после save в server-state появляется `digitalFiles[].name`
- Подтвержденный путь для media:
  - первый `listing-media-upload`
  - после save изображение появляется в `listingImages[]` / `formattedListingImages[]`
- Runtime правило:
  - не считать отсутствие явного визуального “thumbnail change” доказательством провала
  - сначала проверять SSR/server-state на `digitalFiles` и `listingImages`
- Для товаров с вариациями использовать отдельную ветку:
  - если товар не digital-only и Etsy разрешает варианты, включать `Варианты`
  - заполнять option names (`color`, `size`, etc.)
  - затем quantity / SKU / per-variant price
  - для digital-only listings ветка вариантов не используется
- Дополнительные обязательные проверки:
  - `listingType == download`
  - `coreDetails.digitalFulfillment == 0`
  - `category.id` присутствует
  - `price` сохранен в `formFields.price`

### Amazon KDP
- Keyword-поля: 7 keyword slots (использовать как обязательный минимум при подготовке метаданных).
- Cover/bleed правила и шаблоны — только по официальному калькулятору KDP.
- Источники:
  - https://kdp.amazon.com/en_US/help/topic/G201298500
  - https://kdp.amazon.com/en_US/help/topic/G201113520

### Gumroad
- Runtime правило: при browser-flow не трогать старые листинги без явного target id/slug.
- Для digital delivery опираться на upload main file + cover + preview assets + tags/category через редактор.
- Источники:
  - https://gumroad.com/help
  - https://gumroad.com/terms

### Ko-fi Shop
- Для тестов: title + description + price + media/file, затем проверка URL товара/страницы.
- Учитывать ограничения, зависящие от тарифного плана (storage/file size).
- Источник:
  - https://help.ko-fi.com/hc/en-us

### Pinterest
- Базовый runtime-flow: title + description + target URL + image (если доступна), затем publish/save.
- Для креативов использовать вертикальные изображения (рекомендованный аспект 2:3).
- Источник:
  - https://help.pinterest.com/en/business/article/create-pins

### X (Twitter) / Reddit
- X: API-публикация зависит от уровня доступа приложения; при ограничениях держать browser fallback.
- Reddit: при ограниченном API держать browser-only режим для публикации/исследования.
- Источники:
  - https://developer.x.com/en/docs
  - https://www.reddit.com/dev/api/

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- google_trends, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 38c64845d0ea -> cb718551a234.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"7484da3c2b944da4a658c5bae24f7d01","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- reddit

## Confidence Score (0-100)
- 60 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: cb718551a234 -> 9572182ab292.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"643fd914910c4f8ca12272c11bc3f9ba","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- reddit

## Confidence Score (0-100)
- 60 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 9572182ab292 -> ca0b9dbf4bde.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"422e767f6647460cbcba2e75ddd758be","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- reddit

## Confidence Score (0-100)
- 60 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: ca0b9dbf4bde -> 2deaff64f3e4.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"14ad3b449b2a4983984ae911a363c0ff","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## gumroad lesson

Status: draft
Source: test
URL: https://gumroad.com/l/test-slug
Summary: Draft updated
Details: PDF attached, tags pending
Lessons:
- Reuse one working draft.
Anti-patterns:
- Do not create duplicate drafts.
Evidence: {"slug": "test-slug"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/euiwxw
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=euiwxw finished with status=draft. URL=https://gumroad.com/l/euiwxw. Error=none. Files=['the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'ai_side_hustle_cover_1280x720', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'ai_side_hustle_cover_1280x720', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2']
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
- Main PDF can be attached during the content/file flow and should be verified in product state.
- Cover/preview media and the main product file must be treated as separate artifact channels.
Evidence: {"slug": "euiwxw", "error": "", "files_attached": ["the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "ai_side_hustle_cover_1280x720", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "ai_side_hustle_cover_1280x720", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2"], "product_id": "u7XXhFl4mzL6RlhwNNZJsA=="}

## gumroad lesson

Status: working_runbook
Source: gumroad.publish
Summary: Validated Gumroad draft cleanup and media flow on euiwxw
Details: Use storage_state session. Save endpoint is POST /links/{slug}. Clean duplicate content embeds by updating rich_content/files in payload. Product cover flow is Upload images or videos -> Computer files. Thumbnail can be populated separately and is reflected in thumbnail.url. Draft euiwxw now holds one PDF, one content image, one product cover object, and one thumbnail.
Lessons:
- For Gumroad draft maintenance, use storage_state-backed browser session instead of cookie-only probes.
- Real save endpoint is POST /links/{slug} with JSON product payload including rich_content/files.
- Content cleanup is safer through payload rewrite than through fragile file row delete UI.
- Cover upload requires Upload images or videos -> Computer files, not direct file chooser on the first click.
- Thumbnail presence should be checked via top-level thumbnail.url; cover presence via product.covers.
Anti-patterns:
- Do not treat existing_files duplicates as proof that the storefront cover slot is filled.
- Do not rely on global Edit/Delete locators for file rows in Content; the reliable trigger is the per-row Actions menu.
- Do not use cookie-only headless probes when storage_state is available; they can falsely land on login.
Evidence: {"slug": "euiwxw", "files": ["The_AI_Side_Hustle_Playbook_v2.pdf", "ai_side_hustle_cover_1280x720.png"], "thumbnail_set": true, "cover_object_present": true}

## gumroad lesson

Status: distribution_runbook
Source: gumroad.distribution
Summary: Use Gumroad listing URL as canonical outbound sales link
Details: When a Gumroad draft/listing has a stable public URL, reuse that URL as the canonical outbound destination for social distribution. This applies to direct X posts, Reddit link posts, and future Threads multi-post funnels. Social copy can vary by platform, but the destination link should stay canonical for attribution and consistent conversion tracking.
Lessons:
- Use the Gumroad listing URL as the primary outbound sales link in X posts.
- Reuse the same Gumroad URL in Reddit link posts when the goal is traffic to the listing.
- Future Threads funnels can chain multiple posts and end with the Gumroad URL as the conversion step.
- Social routing should treat Gumroad as a destination asset, separate from the post text/media artifacts.
Anti-patterns:
- Do not generate different destination links for each platform when one canonical Gumroad listing link exists.
- Do not force platform-specific share intents when a direct social post with media and a canonical link gives better control.
Evidence: {"listing_url": "https://vitoai.gumroad.com/l/euiwxw", "x_post_url": "https://x.com/bot_vito/status/2030061517727535417", "platforms": ["twitter", "reddit", "threads_future"]}

## gumroad lesson

Status: fresh_artifact_runbook
Source: artifact_pack.runtime
Summary: Fresh-only artifact generation enabled for TG publish recipes
Details: Workflow recipes now set fresh_artifacts_only=True and run_tag. Platform artifact pack generates a new isolated runtime artifact bundle per run: pdf, cover, thumb, social image. This prevents accidental reuse of older output assets during Telegram-driven publish flows.
Lessons:
- For Telegram E2E publish tests, generate all assets inside runtime/fresh_artifacts/<run_tag>.
- Do not reuse legacy output/*.pdf or output/*.png when fresh_artifacts_only=True.
- Treat PDF, cover, thumb, and social image as a single per-run artifact bundle.
Anti-patterns:
- Do not let recipe payloads silently fall back to old test assets from output/.
- Do not mix assets from different runs in the same publish attempt.
Evidence: {"mode": "fresh_artifacts_only", "runtime_bundle_example": "runtime/fresh_artifacts/fresh_tg_test_product_tgfreshcheck2"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/euiwxw
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=euiwxw finished with status=draft. URL=https://gumroad.com/l/euiwxw. Error=missing_attached_types:pdf. Files=[]
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
Anti-patterns:
- Do not treat image uploads as proof that the main PDF product file is attached.
Evidence: {"slug": "euiwxw", "error": "missing_attached_types:pdf", "files_attached": [], "product_id": "u7XXhFl4mzL6RlhwNNZJsA==", "task_root_id": "VT2603062351227CCTASK"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/euiwxw
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=euiwxw finished with status=draft. URL=https://gumroad.com/l/euiwxw. Error=missing_attached_types:pdf. Files=[]
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
Anti-patterns:
- Do not treat image uploads as proof that the main PDF product file is attached.
Evidence: {"slug": "euiwxw", "error": "missing_attached_types:pdf", "files_attached": [], "product_id": "u7XXhFl4mzL6RlhwNNZJsA==", "task_root_id": "VT260307000404C84TASK"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/euiwxw
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=euiwxw finished with status=draft. URL=https://gumroad.com/l/euiwxw. Error=missing_attached_types:pdf. Files=[]
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
Anti-patterns:
- Do not treat image uploads as proof that the main PDF product file is attached.
Evidence: {"slug": "euiwxw", "error": "missing_attached_types:pdf", "files_attached": [], "product_id": "u7XXhFl4mzL6RlhwNNZJsA==", "task_root_id": "VT260307001003BCBTASK"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/euiwxw
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=euiwxw finished with status=draft. URL=https://gumroad.com/l/euiwxw. Error=missing_attached_types:pdf. Files=[]
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
Anti-patterns:
- Do not treat image uploads as proof that the main PDF product file is attached.
Evidence: {"slug": "euiwxw", "error": "missing_attached_types:pdf", "files_attached": [], "product_id": "u7XXhFl4mzL6RlhwNNZJsA==", "task_root_id": "VT260307001955150TASK"}

## gumroad lesson

Status: draft
Source: test
URL: https://gumroad.com/l/test-slug
Summary: Draft updated
Details: PDF attached, tags pending
Lessons:
- Reuse one working draft.
Anti-patterns:
- Do not create duplicate drafts.
Evidence: {"slug": "test-slug"}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_083636_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_083636_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_083636_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_083636_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_083636_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_083636_bookshelf.png"}}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_083735_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_083735_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_083735_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_083735_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_083735_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_083735_bookshelf.png"}}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: draft_only=True; title_inputs=0; price_inputs=0; file_inputs=0; tag_inputs=0; material_inputs=0; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 0, "price_inputs": 0, "file_inputs": 0, "tag_inputs": 0, "material_inputs": 0, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_094941_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "VITO Live Test Asset", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_094941_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_094941_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_094941_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": true, "title": "VITO Live Test Asset", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_094941_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_094941_bookshelf.png"}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095337_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "VITO KDP Live Test", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095337_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095337_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095337_bookshelf.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "VITO KDP Live Test", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095337_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095337_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095646_after_save.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095646_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095646_bookshelf.png", "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=3; description_set=False; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095646_after_save.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095646_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095646_bookshelf.png", "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=listing_id_not_detected; draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: listing_id_not_detected
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095816_after_save.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "KDP live recheck", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095816_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095816_bookshelf.png", "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=3; description_set=False; keyword_slots_filled=7; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_095816_after_save.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "title": "KDP live recheck", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": false, "before_count": 4, "after_count": 4, "fields_filled": 3, "description_set": false, "keyword_slots_filled": 7, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_095816_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_095816_bookshelf.png", "draft_visible": false}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=listing_id_not_detected; draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: listing_id_not_detected
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=editor_not_ready; draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: editor_not_ready
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=editor_not_ready; draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: editor_not_ready
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468011530
Summary: Etsy browser publish result: draft
Details: listing_id=4468011530; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468011530", "url": "https://www.etsy.com/listing/4468011530", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; description_set=True; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_105316_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": false, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 4, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_105316_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_105316_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; description_set=True; keyword_slots_filled=2; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_105316_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": false, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 4, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": false, "cover_uploaded": false, "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_105316_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_105316_bookshelf.png"}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 2deaff64f3e4 -> c9da33d7475b.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"60f945135085461eb555ac63c39789d7","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 9b0624041616 -> 6dcd13436059.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## KDP hardcover runbook

Status: draft_ready
Source: screenshot-first live verification
Summary: Existing hardcover draft `A8T0ZQ5CNS6` can be fully filled and saved without creating new objects when the flow is handled in the correct order.

Confirmed order:
- start from the existing hardcover draft only; do not create another hardcover object
- `Details` first:
  - title
  - subtitle
  - author
  - description
  - 7 keyword slots
  - save and reload verification
- `Content` second:
  - hardcover manuscript must meet print minimum page count; 24 pages fail, 80 pages worked
  - hardcover wrap cover must match KDP Cover Calculator dimensions exactly
  - direct upload is valid after choosing the print-ready PDF path
  - after file uploads, KDP can still block pricing until `Launch Previewer` is opened and approved
- `Previewer` third:
  - `Launch Previewer`
  - wait for previewer to load
  - click `Approve`
  - return to content and reload
- `Pricing` last:
  - price field path works after preview approval
  - `Save as Draft` must be verified by reload, not by click alone

Confirmed values on `A8T0ZQ5CNS6`:
- title: `AI Side Hustle Prompt Journal`
- subtitle: `A guided workbook for digital product ideas, offers, and launch planning`
- author: `Editorial Team`
- US price: `18.99`

Confirmed anti-patterns:
- do not treat `AI-generated questionnaire` as the main blocker when content page explicitly says preview approval is required
- do not use approximate hardcover cover sizes; use KDP Cover Calculator dimensions
- do not keep `Vito Bot` / bot branding in author or title fields
- do not create another hardcover draft when an existing one is already linked and editable

Evidence:
- `runtime/remote_auth/kdp_cover_calc_submit/result.json`
- `runtime/remote_auth/hardcover_previewer_approve/04_after_approve.png`
- `runtime/remote_auth/hardcover_details_fix/result.json`
- `runtime/remote_auth/hardcover_pricing_typepath/result.json`
- `runtime/remote_auth/hardcover_final_verify/result.json`

## Social package runbook

Status: mixed
Source: screenshot-first live verification
Summary: The reusable social path is now confirmed on `X` and `Pinterest`, while `Reddit` remains externally blocked on final submit.

Confirmed X path:
- browser post flow can produce a real permalink on the live profile timeline
- verify on the profile page by matching the new text probe and extracting `/status/...`
- confirmed Gumroad-source post:
  - `https://x.com/bot_vito/status/2030627652764090711`

Confirmed Pinterest path:
- publish-state accepts title, description, outbound link, and image
- final pin page must be checked by screenshot, not publish response alone
- owner-view pin page can emphasize profile name more than the product title, but the real description block and outbound link must be visible
- confirmed Gumroad-source pin:
  - `https://www.pinterest.com/pin/1134203487424140507`

Confirmed Reddit anti-pattern / blocker:
- correct browser path, media upload, and final submit can still end in:
  - `That was a tricky one. Why don't you try that again.`
- this is an anti-abuse gate, not a selector bug
- if this happens after the correct path is proven, mark Reddit as `paused_blocked` instead of faking success

Evidence:
- `runtime/twitter_gumroad_verify/profile.png`
- `runtime/pinterest_pin_verify_0507/result.json`
- `runtime/reddit_gumroad_publish_attempt.json`

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468011530
Summary: Etsy browser publish result: draft
Details: listing_id=4468011530; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468011530", "url": "https://www.etsy.com/listing/4468011530", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124618_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124618_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124618_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124618_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124854_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124854_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124854_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124854_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124938_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124938_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_124938_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_124938_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_125137_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_125137_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_125137_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_125137_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_125311_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_125311_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_125311_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_125311_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130406_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130406_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130406_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130406_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130533_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130533_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130533_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130533_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130716_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130716_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=0
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130716_resume_only_not_found.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "error": "resume_only_existing_draft_not_found", "title": "Book Toolkit", "url": "https://kdp.amazon.com/en_US/bookshelf", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130716_resume_only_not_found.png", "fields_filled": 0, "draft_visible": false}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130952_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_130952.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130952_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_130952_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_130952_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_130952.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_130952_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_130952_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_132107_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_132107.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_132107_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_132107_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_132107_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_132107.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_132107_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_132107_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_132255_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_132255.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_132255_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_132255_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_132255_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_132255.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_132255_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_132255_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_133809_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_133809.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_133809_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_133809_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_133809_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_133809.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_133809_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_133809_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134152_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134152.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_134152_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_134152_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134152_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134152.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_134152_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_134152_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=8; description_set=True; keyword_slots_filled=7; manuscript_uploaded=True; cover_uploaded=True; title_found_on_bookshelf=True; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134151_after_save.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "KDP helper probe 4", "saved_click": true, "url": "https://kdp.amazon.com/en_US/title-setup/kindle/A167ALU3N7G6TV/pricing?ref_=kdp_BS_D_p_ed_pricing", "title_found_on_bookshelf": true, "title_found_via_search": true, "draft_visible": true, "before_count": 0, "after_count": 0, "fields_filled": 8, "description_set": true, "keyword_slots_filled": 7, "manuscript_uploaded": true, "cover_uploaded": true, "pricing_page_seen": true, "pricing_saved": true, "pricing_us_set": true, "pricing_url": "https://kdp.amazon.com/en_US/title-setup/kindle/A167ALU3N7G6TV/pricing?ref_=kdp_BS_D_p_ed_pricing", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134151.epub", "note": "resume_only_direct_document_

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134337_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134337.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_134337_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_134337_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134337_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134337.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_134337_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_134337_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=8; description_set=True; keyword_slots_filled=7; manuscript_uploaded=True; cover_uploaded=True; title_found_on_bookshelf=True; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_134336_after_save.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "KDP helper probe 4", "saved_click": true, "url": "https://kdp.amazon.com/en_US/title-setup/kindle/A167ALU3N7G6TV/content", "title_found_on_bookshelf": true, "title_found_via_search": true, "draft_visible": true, "before_count": 0, "after_count": 0, "fields_filled": 8, "description_set": true, "keyword_slots_filled": 7, "manuscript_uploaded": true, "cover_uploaded": true, "pricing_page_seen": true, "pricing_saved": true, "pricing_us_set": true, "pricing_url": "https://kdp.amazon.com/en_US/title-setup/kindle/A167ALU3N7G6TV/pricing?ref_=kdp_BS_D_p_ed_pricing", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_134336.epub", "note": "resume_only_direct_document_verification", "screenshot"

## amazon_kdp lesson

Status: no_browser
Source: amazon_kdp.publish
Summary: KDP publish result: no_browser
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "no_browser", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_135657_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_135657.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_135657_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_135657_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_135657_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_135657.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_135657_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_135657_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_135907_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_135907.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_135907_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_135907_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_135907_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_135907.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_135907_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_135907_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png"}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_143022_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_143022.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_143022_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_143022_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_143022_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_143022.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_143022_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_143022_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png", "linked_formats": {}}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=1; description_set=False; keyword_slots_filled=0; manuscript_uploaded=False; cover_uploaded=False; title_found_on_bookshelf=True; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_143021_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "KDP helper probe 4", "saved_click": false, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": true, "title_found_via_search": true, "draft_visible": true, "before_count": 0, "after_count": 0, "fields_filled": 1, "description_set": false, "keyword_slots_filled": 0, "manuscript_uploaded": false, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "https://kdp.amazon.com/en_US/bookshelf", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_143021.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_143021_after_save.png", "bookshelf_screenshot": "runti

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_143123_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_143123.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_143123_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_143123_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_143123_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_143123.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_143123_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_143123_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png", "linked_formats": {}}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png", "linked_formats": {}}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468011530
Summary: Etsy browser publish result: draft
Details: listing_id=4468011530; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468011530", "url": "https://www.etsy.com/listing/4468011530", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468011530
Summary: Etsy browser publish result: draft
Details: listing_id=4468011530; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468011530", "url": "https://www.etsy.com/listing/4468011530", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468011530
Summary: Etsy browser publish result: draft
Details: listing_id=4468011530; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468011530", "url": "https://www.etsy.com/listing/4468011530", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=draft_only_requires_existing_draft
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: draft_only_requires_existing_draft
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=draft_only_requires_existing_draft
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: draft_only_requires_existing_draft
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=editor_not_ready; draft_only=False; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: editor_not_ready
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": false, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468093584
Summary: Etsy browser publish result: draft
Details: listing_id=4468093584; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468093584", "url": "https://www.etsy.com/listing/4468093584", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468093570
Summary: Etsy browser publish result: draft
Details: listing_id=4468093570; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468093570", "url": "https://www.etsy.com/listing/4468093570", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468093570
Summary: Etsy browser publish result: draft
Details: listing_id=4468093570; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468093570", "url": "https://www.etsy.com/listing/4468093570", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468240834
Summary: Etsy browser publish result: draft
Details: listing_id=4468240834; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468240834", "url": "https://www.etsy.com/listing/4468240834", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468240834
Summary: Etsy browser publish result: draft
Details: listing_id=4468240834; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468240834", "url": "https://www.etsy.com/listing/4468240834", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## printful lesson

Status: published
Source: printful.publish.browser
URL: https://www.etsy.com/your/shops/VITOKI/tools/listings/4468240834
Summary: Existing synced Printful product reused by title.
Details: My Products already contained linked Etsy item; browser adapter reused it instead of creating duplicates.
Lessons:
- Перед созданием нового Printful товара проверяй My Products по title.
- Если найден linked Etsy item с Edit in Etsy, считай связку подтвержденной и не плодить дубликаты.
Anti-patterns:
- Не пытайся создавать новый linked product, если synced item уже существует для той же задачи.
Evidence: {"platform": "printful", "status": "published", "url": "https://www.printful.com/dashboard/product-templates/published/17803130", "mode": "browser_only", "screenshot_path": "/home/vito/vito-agent/runtime/printful_browser_publish.png", "html_path": "/home/vito/vito-agent/runtime/printful_browser_publish.html", "store_type": "", "title": "AI Side Hustle Notebook", "template_id": "", "etsy_edit_url": "https://www.etsy.com/your/shops/VITOKI/tools/listings/4468240834"}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_204650_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_204650.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_204650_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_204650_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_204650_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_204650.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_204650_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_204650_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png", "linked_formats": {}}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: blocked
Source: amazon_kdp.publish
Summary: KDP publish result: blocked
Details: error=new_draft_requires_explicit_allow_new_draft
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
- Ошибка: new_draft_requires_explicit_allow_new_draft
Evidence: {"status": "blocked", "url": null, "screenshot_path": null, "method": null, "output": {}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_204808_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_204808.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_204808_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_204808_books

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.publish.helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=6; description_set=True; keyword_slots_filled=2; manuscript_uploaded=True; cover_uploaded=False; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=True
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
- Сохраняй draft через helper и проверяй появление на Bookshelf.
- Файлы manuscript/cover должны проверяться отдельно от metadata save.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/remote_auth/kdp_draft_20260307_204808_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "title": "Book Toolkit", "saved_click": true, "url": "https://kdp.amazon.com/en_US/bookshelf", "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "before_count": 4, "after_count": 4, "fields_filled": 6, "description_set": true, "keyword_slots_filled": 2, "manuscript_uploaded": true, "cover_uploaded": false, "pricing_page_seen": false, "pricing_saved": false, "pricing_us_set": false, "pricing_url": "", "price_us": "2.99", "royalty_rate": "35_PERCENT", "enroll_select": false, "manuscript_path": "runtime/remote_auth/kdp_manuscript_20260307_204808.epub", "note": "strict_bookshelf_verification", "screenshot": "runtime/remote_auth/kdp_draft_20260307_204808_after_save.png", "bookshelf_screenshot": "runtime/remote_auth/kdp_draft_20260307_204808_books

## amazon_kdp lesson

Status: prepared
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: prepared
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=False; saved_click=True
Anti-patterns:
- Не считай KDP успехом без bookshelf evidence или helper proof.
Evidence: {"status": "prepared", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_after.png", "method": "kdp_helper", "output": {"ok": false, "ok_soft": false, "saved_click": true, "title_found_on_bookshelf": false, "title_found_via_search": false, "fields_filled": 4, "screenshot": "runtime/kdp_after.png", "draft_visible": false}}

## amazon_kdp lesson

Status: draft
Source: amazon_kdp.kdp_helper
URL: https://kdp.amazon.com/bookshelf
Summary: KDP publish result: draft
Details: fields_filled=4; title_found_on_bookshelf=False; title_found_via_search=True; saved_click=False
Lessons:
- Подтверждай KDP-черновик только через bookshelf proof или helper evidence.
Evidence: {"status": "draft", "url": "https://kdp.amazon.com/bookshelf", "screenshot_path": "runtime/kdp_bookshelf.png", "method": "kdp_helper", "output": {"ok": true, "ok_soft": true, "saved_click": false, "title_found_on_bookshelf": false, "title_found_via_search": true, "draft_visible": true, "fields_filled": 4, "bookshelf_screenshot": "runtime/kdp_bookshelf.png", "linked_formats": {}}}
# Amazon KDP

## Paperback linked from existing eBook

- Source linked paperback draft:
  - `document_id = A8T0ZQ5CNS6`
- Do not create a new object when linked paperback already exists on Bookshelf.
- Existing published / in-review eBook must not be edited implicitly.
- Existing stale draft `Book Toolkit` was deleted and must not be reused.

### Confirmed routes

- Details:
  - `https://kdp.amazon.com/action/dualbookshelf.editpaperbackdetails/en_US/title-setup/paperback/A8T0ZQ5CNS6/details`
- Content:
  - `https://kdp.amazon.com/action/dualbookshelf.editpaperbackcontent/en_US/title-setup/paperback/A8T0ZQ5CNS6/content`
- Pricing:
  - `https://kdp.amazon.com/action/dualbookshelf.editpaperbackpricing/en_US/title-setup/paperback/A8T0ZQ5CNS6/pricing`
  - plain resolved URL also works after auth redirect:
    - `/en_US/title-setup/paperback/A8T0ZQ5CNS6/pricing`

### Confirmed content inputs

- Manuscript upload:
  - `#data-print-book-publisher-interior-file-upload-AjaxInput`
- Cover upload:
  - `#data-print-book-publisher-cover-file-upload-AjaxInput`
  - `#data-print-book-publisher-cover-pdf-only-file-upload-AjaxInput`
- AI questionnaire:
  - `#generative-ai-questionnaire-text`
  - `#generative-ai-questionnaire-images`
  - `#generative-ai-questionnaire-translations`

### Confirmed content status signals

- Manuscript success:
  - `#data-print-book-publisher-interior-asset-status = SUCCESS`
- Cover success:
  - `#data-print-book-publisher-cover-asset-status = SUCCESS`
  - `#data-print-book-publisher-cover-pdf-only-asset-status = SUCCESS`
- KDP page also shows:
  - `Manuscript "...pdf" uploaded successfully!`
  - `Cover uploaded successfully!`

### Confirmed content behavior

- Paperback manuscript must be print PDF, not ebook EPUB.
- One-page PDF is rejected.
- Working generator path now uses a 24-page PDF for print.
- `Save and Continue` on paperback content is long-running and should not be treated as immediate failure.
- `Launch Previewer` is available but can hang in headless flow; do not use previewer hang as proof of failure if content status fields are already `SUCCESS`.

### Confirmed pricing selectors

- Legacy pricing route selectors:
  - `#data-print-book-worldwide-rights`
  - `input[name='data[print_book][amazon_channel][us][price_vat_exclusive]']`
- Active `print-setup` pricing route selectors:
  - route:
    - `https://kdp.amazon.com/en_US/print-setup/paperback/A8T0ZQ5CNS6/pricing`
  - worldwide rights:
    - `#worldwide-rights`
  - price inputs:
    - `#price-input-usd`
    - `#price-input-cad`
    - `#price-input-jpy`
    - `#price-input-gbp`
    - `#price-input-aud`
    - `#price-input-eur` (multiple rows)
    - `#price-input-pln`
    - `#price-input-sek`
  - save button text:
    - `Save as Draft`

### Confirmed pricing behavior

- Account page was investigated via `account.kdp.amazon.com/api/payee`.
- Account identity/bank/tax are already complete enough:
  - `missingImportantFields = false`
  - `identityPageActionRequired = false`
  - `verificationCompleted = true`
- Real blocker was not account page but unapproved `Paperback Content`.
- `Print Previewer` originally failed because uploaded cover was front-only:
  - expected cover size: `12.304 x 9.250`
  - submitted file size: `6.000 x 9.000`
- After generating and uploading wrap cover PDF with paperback dimensions:
  - previewer cover error disappeared
  - `Approve` returned to content page
  - `Paperback Content = Complete`
- On the new `print-setup` pricing page KDP requires explicit prices in all marketplace rows.
- Confirmed working persisted values after reload:
  - USD `6.99`
  - CAD `9.99`
  - JPY `999`
  - GBP `7.99`
  - AUD `13.99`
  - EUR rows `9,99`
  - PLN `40.00`
  - SEK `110.00`

### Confirmed paperback runbook

1. Start from existing linked paperback draft:
   - `A8T0ZQ5CNS6`
2. Do not create a new paperback if the linked one already exists on Bookshelf.
3. `Content`:
   - upload print manuscript PDF
   - upload paperback wrap cover PDF, not front-only cover
   - wait for success statuses
   - launch `Print Previewer`
   - if previewer reports cover size mismatch, regenerate wrap cover with the exact previewer-required dimensions
   - click `Approve`
4. `Pricing`:
   - use `print-setup/paperback/<document_id>/pricing`
   - if redirected to `amazon.com/ap/signin`, enter password and return to the same route
   - select `#worldwide-rights`
   - fill all marketplace price inputs
   - click `Save as Draft`
   - verify values persist after reload

### General browser 2FA rule

- VITO enters login and password itself.
- If the platform opens a code/2FA prompt, only then it asks the owner for a code.
- After receiving the code, VITO completes login and saves refreshed browser session state.

### Anti-patterns

- Do not reuse published or in-review ebook as implicit edit target.
- Do not create a new paperback if Bookshelf already shows linked paperback draft.
- Do not assume cover failure if hidden status fields already show `SUCCESS`.
- Do not keep blaming the account page when pricing is actually blocked by incomplete/ unapproved `Content`.
- Do not leave marketplace prices empty on the new `print-setup` pricing page.


## Social package — screenshot-first findings (2026-03-07)

### Pinterest
- Confirmed live pin: `https://www.pinterest.com/pin/1134203487424108921`
- Confirmed on final pin page: outbound Etsy link and visible description text.
- Confirmed in publish-state HTML: title `AI Side Hustle Starter Kit for Creators`, description, and `WebsiteField=https://www.etsy.com/listing/4468093584`.
- Important nuance: final pin page may render profile name (`Vito`) as the visible heading even when title is saved in the creation state. Do not treat missing visible H1 title as missing metadata without checking publish-state HTML and outbound link.
- Confirmed owner cleanup path:
  - open the pin page as owner
  - click the visible top-left `Другие действия` button for the current pin, not the repeated buttons on recommended pins
  - choose `Изменить пин`
  - inside the edit state use `Удалить`
  - confirm deletion and then reopen the direct pin URL
  - successful deletion resolves to `show_error=true` / `Не удается найти эту идею`
- Do not consider Pinterest clean while multiple live pin URLs remain in the profile.
- Cleanup verification must include:
  - direct public pin URL
  - owner profile page pin links
  - final surviving pin page with description and outbound product link

### Reddit
- Correct browser path is old.reddit profile submit: `https://old.reddit.com/user/<username>/submit`.
- Correct final submit button is `button.btn[name="submit"][value="form"]`.
- Media upload can complete (`Your video has uploaded!`) and still be rejected on final submit with: `That was a tricky one. Why don't you try that again.`
- This is a confirmed anti-abuse / submit gate, not a selector or auth failure.

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/mbeihe
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=mbeihe finished with status=draft. URL=https://gumroad.com/l/mbeihe. Error=none. Files=['the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2', 'the_ai_side_hustle_playbook_v2']
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
- Main PDF can be attached during the content/file flow and should be verified in product state.
Evidence: {"slug": "mbeihe", "error": "", "files_attached": ["the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2", "the_ai_side_hustle_playbook_v2"], "product_id": "qLQ3-amBZv9-vZngcOsefw==", "task_root_id": "gumroad-mbeihe-repair"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/zrvfrg
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=zrvfrg finished with status=draft. URL=https://gumroad.com/l/zrvfrg. Error=tags_not_set. Files=['digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_cover_1280x720']
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
- Cover/preview media and the main product file must be treated as separate artifact channels.
Anti-patterns:
- Simple click on tag suggestions is not sufficient; Gumroad tag widget needs explicit commit behavior.
Evidence: {"slug": "zrvfrg", "error": "tags_not_set", "files_attached": ["digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_cover_1280x720"], "product_id": "EAmYSYLXn0XXHCqMZaYTwg==", "task_root_id": "gumroad-fresh-1772963045"}

## gumroad lesson

Status: draft
Source: gumroad.publish
URL: https://gumroad.com/l/zrvfrg
Summary: Gumroad listing run finished with status=draft
Details: Gumroad publish attempt on slug=zrvfrg finished with status=draft. URL=https://gumroad.com/l/zrvfrg. Error=tags_not_set. Files=['digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_product', 'digital_product_automation_cover_1280x720']
Lessons:
- Reuse the same working draft by explicit slug/id instead of creating a new listing.
- Cover/preview media and the main product file must be treated as separate artifact channels.
Anti-patterns:
- Simple click on tag suggestions is not sufficient; Gumroad tag widget needs explicit commit behavior.
Evidence: {"slug": "zrvfrg", "error": "tags_not_set", "files_attached": ["digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_product", "digital_product_automation_cover_1280x720"], "product_id": "EAmYSYLXn0XXHCqMZaYTwg==", "task_root_id": "gumroad-zrvfrg-restore-1772963430"}

## Gumroad — confirmed live package on zrvfrg

Status: published
Source: screenshot-first live verification
URL: https://vitoai.gumroad.com/l/zrvfrg
Summary: One fresh-only Gumroad product was created, cleaned up, completed and published on a single working object.

Confirmed required elements:
- one active working object only; duplicate drafts must be deleted before continuing work
- main deliverable must be attached on `Content`, not via product image uploaders
- `Product` tab handles cover/gallery and thumbnail image
- `Product` tab description is saved via `Save and continue`, not `Save changes`
- `Share` tab stores discovery metadata; category may resolve to a concrete child inside the chosen business branch
- public page must be verified by `screenshot + URL + DOM/state`
- working editor root is `https://gumroad.com/products/{slug}/edit`; the old `/edit/product` route can return a 404 shell and must not be treated as the live editor
- cover/gallery uploader on the Product page uses the image input with `accept=.jpeg,.jpg,.png,.gif,.webp` and `multiple=true`
- real hero-cover slot is not the same as content images: `Cover -> Upload images or videos -> Computer files` opens a dedicated image input with `accept=.jpeg,.jpg,.png,.gif,.mov,.m4v,.mpeg,.mpg,.mp4,.wmv`; this path must be used for the top public hero image
- thumbnail has its own section and its own uploader path: after clicking `Remove` in the Thumbnail section, a dedicated non-multiple image input appears and must receive the square thumb asset
- after thumbnail upload, `Save changes` + reload verification are mandatory
- old visual artifacts can also hide inside the rich-text Description as image nodes; they must be removed through the editor itself (select image node -> Backspace -> `Save and continue`), not by raw DOM surgery
- on the public page, `vr7rfc0t795evzs6vekodnhzp5if` is the seller avatar, not the product cover
- confirmed fresh visual assets on `zrvfrg`:
  - hero-cover on public page: `pviwezyd1qq5215l2vb4f6y96dr1`
  - public cover/gallery: `emriywhhmvnafmgh8n5lco2ux1eq`, `awqrc0cyxdwclu5777pu1gmeki1g`
  - thumbnail after reload: `o54mtt4thsznol64l6wwllfxh24o`

Confirmed anti-patterns:
- do not reuse old Gumroad drafts when the current mode is `fresh-only`
- do not call direct `POST /links/{slug}` with partial product JSON; it can wipe `files`, `rich_content`, `description`, `tags` and category
- do not treat repeated create after timeout as safe; first verify whether a real draft already exists
- do not confuse seller avatar with the listing cover when validating the public page

Required Gumroad checklist going forward:
- title
- summary
- description
- one main PDF
- thumbnail / preview image
- category
- tags
- public URL verification
- optional social continuation only after the live package is confirmed

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: c9da33d7475b -> 7785109a4385.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"b332cd40673b49dcbd367c19ce76db36","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 6dcd13436059 -> c908e8ba300e.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## printful lesson

Status: prepared
Source: printful.publish.browser
URL: https://www.printful.com/dashboard/product-templates/published/17803130
Summary: Browser publish finished with status=prepared.
Details: title=Nihilistic Penguin Trend Notebook template_id=n/a
Lessons:
- Если linked Etsy URL не найден, это еще не закрытый publish flow.
Anti-patterns:
- Не считай publish успешным только по открытому wizard без synced product evidence.
Evidence: {"platform": "printful", "status": "prepared", "url": "https://www.printful.com/dashboard/product-templates/published/17803130", "mode": "browser_only", "screenshot_path": "/home/vito/vito-agent/runtime/printful_browser_publish.png", "html_path": "/home/vito/vito-agent/runtime/printful_browser_publish.html", "store_type": "", "title": "My products | Printful", "template_id": "", "etsy_edit_url": ""}

## etsy lesson

Status: prepared
Source: etsy.publish.browser
URL: https://www.etsy.com/your/shops/me/tools/listings
Summary: Etsy browser publish result: prepared
Details: error=editor_not_ready; draft_only=True; title_inputs=1; price_inputs=1; file_inputs=1; tag_inputs=1; material_inputs=1; spinner_present=True
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: editor_not_ready
Evidence: {"status": "prepared", "listing_id": null, "url": "https://www.etsy.com/your/shops/me/tools/listings", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {"title_inputs": 1, "price_inputs": 1, "file_inputs": 1, "tag_inputs": 1, "material_inputs": 1, "spinner_present": true, "body_has_create": false, "title_value": "", "price_value": ""}}

## etsy lesson

Status: draft
Source: etsy.publish.browser
URL: https://www.etsy.com/listing/4468782941
Summary: Etsy browser publish result: draft
Details: listing_id=4468782941; draft_only=True
Lessons:
- Используй один рабочий listing_id и не считай create успешным без listing_id.
- Etsy browser flow должен отдельно проверять editor URL, listing_id и screenshot evidence.
Evidence: {"status": "draft", "listing_id": "4468782941", "url": "https://www.etsy.com/listing/4468782941", "screenshot_path": "/home/vito/vito-agent/runtime/etsy_browser_publish.png", "draft_only": true, "debug": {}}

## printful lesson

Status: prepared
Source: printful.publish.browser
URL: https://www.printful.com/dashboard/product-templates/published/17803130
Summary: Browser publish finished with status=prepared.
Details: title=Nihilistic Penguin Trend Notebook template_id=n/a
Lessons:
- Если linked Etsy URL не найден, это еще не закрытый publish flow.
Anti-patterns:
- Не считай publish успешным только по открытому wizard без synced product evidence.
Evidence: {"platform": "printful", "status": "prepared", "url": "https://www.printful.com/dashboard/product-templates/published/17803130", "mode": "browser_only", "screenshot_path": "/home/vito/vito-agent/runtime/printful_browser_publish.png", "html_path": "/home/vito/vito-agent/runtime/printful_browser_publish.html", "store_type": "", "title": "My products | Printful", "template_id": "", "etsy_edit_url": ""}

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 7785109a4385 -> ef79ab8603d5.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"32a74bb2660b4145834622d81f0ed49b","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: c908e8ba300e -> 8ebe53b9bd40.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## printful lesson

Status: prepared
Source: printful.publish.browser
URL: https://www.printful.com/dashboard/product-templates/published/17803130
Summary: Browser publish finished with status=prepared.
Details: title=VITO readiness Printful template_id=n/a
Lessons:
- Если linked Etsy URL не найден, это еще не закрытый publish flow.
Anti-patterns:
- Не считай publish успешным только по открытому wizard без synced product evidence.
Evidence: {"platform": "printful", "status": "prepared", "url": "https://www.printful.com/dashboard/product-templates/published/17803130", "mode": "browser_only", "screenshot_path": "/home/vito/vito-agent/runtime/printful_browser_publish.png", "html_path": "/home/vito/vito-agent/runtime/printful_browser_publish.html", "store_type": "", "title": "My products | Printful", "template_id": "", "etsy_edit_url": ""}

## etsy lesson

Status: draft
Source: test
URL: https://www.etsy.com/listing/123
Summary: Draft updated
Details: File and images attached
Lessons:
- Reuse one working draft.
- Verify file after reload.
Anti-patterns:
- Do not publish during tests.
Evidence: {"listing_id": "123", "file_attached": true}

## etsy lesson

Status: draft
Source: test
URL: https://www.etsy.com/listing/123
Summary: Draft updated
Details: File and images attached
Lessons:
- Reuse one working draft.
- Verify file after reload.
Anti-patterns:
- Do not publish during tests.
Evidence: {"listing_id": "123", "file_attached": true}

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: ef79ab8603d5 -> cb2d50896a33.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"9caaeef32ee44e54893f9de795dfff47","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 8ebe53b9bd40 -> 386fba70dfca.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- google_trends, product_hunt, reddit

## Confidence Score (0-100)
- 100 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: cb2d50896a33 -> d2139d4a4c3c.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"eda5c73fa704407e80b26320108d333a","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 386fba70dfca -> 988ae31f07ad.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: d2139d4a4c3c -> b227418c81bc.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"abcf8d9a95234ddaa20310f39ff66477","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt

## Confidence Score (0-100)
- 60 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: b227418c81bc -> 5e5668a13d59.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"c58f34dc33774e5e8567031aa57dbb37","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 5e5668a13d59 -> 775c51393536.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"4f60bd31e66c4ba1a70e5dabec45681d","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 988ae31f07ad -> 9596b06580a2.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 775c51393536 -> afa1f7fe0450.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"a6de92cf35294727abf6f3fe3b3177e8","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: afa1f7fe0450 -> 742bd22b7e80.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"040c01447a0e4760af3e732aa8a0ed5d","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: afa1f7fe0450 -> 4c72d391ed40.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"3eab924f82d14a53abccce3cc43149dc","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 4c72d391ed40 -> 3ef270d03a43.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"8459d656153f4dd6a6aec97ab22330f6","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 4c72d391ed40 -> 8951b124b51f.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"136d08567c6c45669c9f3f62b8a61692","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 3ef270d03a43 -> ad3163b5e885.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"e6180ec9f31d4ae2920b2b3d916f19c9","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 9596b06580a2 -> 6749aa7c9dfc.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 3ef270d03a43 -> 1322f92881d6.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"a18741293e93470e92ac66237c333881","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 9596b06580a2 -> 6749aa7c9dfc.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 1322f92881d6 -> bd90b4208cdd.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"4e1a5a712d904558b333743e867011a9","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 1322f92881d6 -> c1e240850923.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"77db73c43660440f91a17ec3faefb205","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: c1e240850923 -> e7db89743465.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"bb0d653ce3e641f8b2cefc51431f51d2","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: c1e240850923 -> 4026034bfbad.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"8771c7b200674c57950ff840d199633f","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 4026034bfbad -> 083ffc2b686a.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"dbd5641063674c47974df35aa6436000","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 083ffc2b686a -> e7a69744d05c.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"bf179d63364a4cf6a4fdea9f8927c971","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: e7a69744d05c -> 6bc05751e4bb.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"b4735e43a7984dc6a8381cea00a87141","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## twitter rules update

Source: https://developer.x.com/en/docs
Detected rules/content change by hash diff: 6749aa7c9dfc -> 43555004c1f3.
Excerpt: X Developer Platform - X Skip to main content X home page English Search... ⌘ K Ask AI Support Developer Console Developer Console Search... Navigation Getting Started X Developer Platform Home X API X Ads API XDKs Tutorials Use Cases Success Stories Status Changelog Developer Console Forums GitHub Getting Started Overview Fundamentals Apps Developer Console Authentication Counting Characters Rate Limits X IDs Security Partners &amp; Customers Partner Directory Customer Directory Request Access Resources Tools and Libraries Tutorials Newsletter Livestreams Billing Support Developer Terms Getting Started X Developer Platform Copy page Build with X’s real-time data and APIs Copy page Pay-per-usage pricing: Now Available Pay only for what you use. Plus, earn free xAI API credits when you purc

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 6bc05751e4bb -> ca565ab9b076.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"567a20303b6848988ec90771dd30f6fe","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## pinterest rules update

Source: https://developers.pinterest.com/docs/
Detected rules/content change by hash diff: 6bc05751e4bb -> 680528f802a0.
Excerpt: Pinterest Developers {"otaData":{"deltas":{}},"inContextTranslation":false,"initialReduxState":null,"isAppShell":null,"apps":[],"isDev":false,"isMobile":false,"user":{"unauth_id":"80ae6e5af9714306adfd32d3f73f1bb4","ip_country":"DE","ip_region":"BY"},"enableChatbot":false,"allEndpointDetails":{"pins/create":{"path":"/pins","method":"post","operationId":"pins/create","summary":"Create Pin","description":" create a pin on a board or board section owned by the operation user_account note if the current operation user_account defined by the access token has access to another user s ad accounts via pinterest business access you can modify your request to make use of the current operation_user_account s permissions to those ad accounts by including the ad_account_id in the path parameters for the

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## Mega test task

## Executive Summary
Stub response: operational output.

## Sources
- product_hunt, reddit

## Confidence Score (0-100)
- 80 (based on available live sources and evidence density)
- Topic: Find official docs, GitHub repos, and community pitfalls for service/platform: Mega test task. Provide key requirements, auth, formats, limits.

## Judge Review
Decision: accept
Score: 0/100
Stub response: operational output.

## etsy lesson

Status: needs_browser_login
Source: etsy.publish.browser
Summary: Etsy browser publish result: needs_browser_login
Details: error=Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: Etsy browser session required. Run: python3 scripts/etsy_auth_helper.py browser-capture
Evidence: {"status": "needs_browser_login", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}

## etsy lesson

Status: blocked
Source: etsy.publish.browser
Summary: Etsy browser publish result: blocked
Details: error=create_mode_forbids_existing_update
Anti-patterns:
- Не считай Etsy create успешным только по открытому editor без listing_id.
- Ошибка: create_mode_forbids_existing_update
Evidence: {"status": "blocked", "listing_id": null, "url": null, "screenshot_path": null, "draft_only": null, "debug": {}}
