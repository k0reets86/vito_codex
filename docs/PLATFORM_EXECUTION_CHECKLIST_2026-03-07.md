# Live Platform Checklist — 2026-03-07

Rule:
- Один активный платформенный блок за раз.
- Статусы только такие: `done`, `active`, `paused_blocked`, `not_done`.
- Шаг считается подтвержденным только если совпали `screenshot + URL + DOM/state`.
- Опубликованные объекты не трогаются без явного target от owner.
- В рамках одной задачи использовать один рабочий объект, не плодить дубликаты.

## Current Active Block
- `active`: `Gumroad social continuation`

## Done

### Gumroad live package
- Status: `done`
- Working object:
  - draft -> published product `zrvfrg`
  - product id `EAmYSYLXn0XXHCqMZaYTwg==`
- Confirmed:
  - duplicate drafts removed, only one working Gumroad product remains
  - one main PDF attached and survives reload
  - top public hero-cover visible above the title
  - public cover/gallery updated with new generated visuals
  - dedicated thumbnail uploader path confirmed and thumbnail replaced after reload
  - stale square image removed from description editor; public page no longer shows the old blank/white block above the title
  - description and summary survive reload
  - category/tags survive reload
  - product is published
  - public page opens with title, price, description, image and CTA
- Evidence:
  - `runtime/gumroad_products_after_cleanup.json`
  - `runtime/gumroad_zrvfrg_ui_recover.json`
  - `runtime/gumroad_zrvfrg_desc_after_savecontinue.json`
  - `runtime/gumroad_zrvfrg_public_probe.json`
  - `runtime/gumroad_visual_apply/result.json`
  - `runtime/gumroad_thumb_replace_exact/result.json`
  - `runtime/gumroad_public_img_map.json`
  - `runtime/gumroad_remove_old_desc_image_ui/result.json`
  - `runtime/gumroad_cover_exact_input2/result.json`

### Etsy existing draft
- Status: `done`
- Working object:
  - `listing_id = 4468240834`
- Confirmed:
  - draft editor opens
  - title/description/price exist
  - file attached
  - images present
  - linked browser evidence captured
- Evidence:
  - `runtime/etsy_4468240834_current_probe.png`
  - `runtime/etsy_4468240834_current_probe.html`

### Printful -> Etsy linked flow
- Status: `done`
- Working object:
  - Printful product/template path on `99888631`
  - linked Etsy draft `4468240834`
- Confirmed:
  - browser flow proved
  - linked Etsy draft exists
  - adapter accepts linked Etsy success
- Evidence:
  - `runtime/printful_linked_current_probe.png`
  - `runtime/printful_linked_current_probe.html`
  - `runtime/linked_platform_current_probe.json`
- Commits:
  - `3470fe0`
  - `e567541`

### KDP hardcover
- Status: `done`
- Working object:
  - `document_id = A8T0ZQ5CNS6`
- Confirmed:
  - one existing hardcover draft reused; no new hardcover drafts created
  - `Details` saved and survive reload:
    - title `AI Side Hustle Prompt Journal`
    - subtitle `A guided workbook for digital product ideas, offers, and launch planning`
    - author `Editorial Team`
    - 7 keyword slots filled
  - `Content` saved and survive reload:
    - hardcover manuscript uploaded successfully
    - hardcover wrap cover rebuilt from KDP Cover Calculator dimensions and uploaded successfully
    - print previewer opened and approval path completed
  - `Pricing` saved and survives reload:
    - `US price = 18.99`
    - no `earlier page issue` remains after preview approval
  - Bookshelf still shows the same hardcover draft object
- Evidence:
  - `runtime/remote_auth/hardcover_error_probe/result.json`
  - `runtime/remote_auth/kdp_cover_calc_submit/result.json`
  - `runtime/remote_auth/hardcover_processing_wait/result.json`
  - `runtime/remote_auth/hardcover_previewer_approve/04_after_approve.png`
  - `runtime/remote_auth/hardcover_details_fix/result.json`
  - `runtime/remote_auth/hardcover_pricing_typepath/result.json`
  - `runtime/remote_auth/hardcover_final_verify/result.json`

## Active

### Social package for current product source
- Status: `active`
- Current product source:
  - Etsy listing `4468093584`
- Goal:
  - X/Twitter post with image, SEO text, tags, product link
  - Reddit post with image, SEO text, tags, product link
  - Pinterest pin with visible metadata, image, outbound product link
  - reusable runbook for any future product source
- Current confirmed state:
  - X has a real public post
  - Pinterest pin has confirmed outbound Etsy link and description, but title is still not закреплен как надо
  - Reddit submit still hits anti-abuse style reject after media upload
- Evidence:
  - `runtime/twitter_profile_probe.json`
  - `runtime/social_current_probe.json`
  - `runtime/pinterest_pin_verify_8921.json`
  - `runtime/reddit_submit_real_after.txt`

## Paused Blocked

### Ko-fi
- Status: `paused_blocked`
- Blocker:
  - anti-bot / Cloudflare gate
- Confirmed:
  - home page and manage/shop page both land on `Just a moment...`
- Evidence:
  - `runtime/kofi_screenshot_probe.json`
  - `runtime/kofi_screenshot_probe_home.png`
  - `runtime/kofi_screenshot_probe_manage.png`
- Next unblock condition:
  - challenge-free entry to Ko-fi home/manage with screenshots

## Not Done

### Reddit post for Etsy product
- Status: `not_done`
- Required:
  - social package must support posting for any current product source:
    - Etsy
    - Amazon KDP
    - Gumroad
    - future platforms
  - post with image
  - SEO title/description
  - tags
  - correct product link
  - screenshot evidence
- Current blocker:
  - anti-abuse style reject on submit after correct old.reddit profile path, media upload and final submit:
    - `That was a tricky one. Why don't you try that again.`
  - browser path is fully localized, but bypass is not found yet

### X/Twitter social package
- Status: `not_done`
- Required:
  - social package must support posting for any current product source:
    - Etsy
    - Amazon KDP
    - Gumroad
    - future platforms
  - post with image
  - SEO text
  - tags
  - correct product link
  - screenshot evidence
- Already confirmed:
  - public post exists:
    - `https://x.com/bot_vito/status/2030350266571141526`
  - remaining work:
    - fold this into generic reusable social runbook, not one-off proof only

### Pinterest social package
- Status: `not_done`
- Required:
  - properly оформленный pin
  - нормальный visual
  - title/description
  - outbound link to current product
  - screenshot evidence
  - reusable runbook for future products/platforms
- Already confirmed:
  - live pin exists:
    - `https://www.pinterest.com/pin/1134203487424108921`
  - publish-state confirms saved title:
    - `AI Side Hustle Starter Kit for Creators`
  - outbound Etsy link confirmed
  - description visible on pin page confirmed
- Remaining blocker:
  - title on final pin page is still rendered as `Vito`, not as product title heading

### KDP paperback from published ebook
- Status: `not_done`
- Reason:
  - technical paperback package is mostly solved
  - but owner-required canonical path is still not replayed from exact UI fork
- Owner-required remaining path:
  - start from already published ebook
  - click exact UI path `Publish -> Create paperback`
  - create/reconfirm paperback through that fork
- Current working object:
  - `document_id = A8T0ZQ5CNS6`
- Already confirmed:
  - content complete
  - preview approve complete
  - print pricing persisted
  - runbook written
  - package committed
- Evidence:
  - `runtime/remote_auth/paperback_previewer_after_approve_click.png`
  - `runtime/remote_auth/paperback_pricing_all_markets_after_save.png`
- Commit:
  - `5445436`

### Gumroad social continuation
- Status: `active`
- Required after Gumroad listing exists:
  - X/Twitter post with image/tags/link
  - Reddit post with image/tags/link
  - Pinterest pin with image/link

## Commit Log For This Checklist Wave
- `5445436` — KDP paperback runbook and pricing flow
- `e567541` — Printful linked Etsy success accepted in adapter
- `fd5f55a` — Ko-fi screenshot-first Cloudflare gate recorded
