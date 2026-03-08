# Live Platform Checklist — 2026-03-07

Rule:
- Один активный платформенный блок за раз.
- Статусы только такие: `done`, `active`, `paused_blocked`, `not_done`.
- Шаг считается подтвержденным только если совпали `screenshot + URL + DOM/state`.
- Опубликованные объекты не трогаются без явного target от owner.
- В рамках одной задачи использовать один рабочий объект, не плодить дубликаты.

## Current Active Block
- `active`: `none`

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
  - `runtime/gumroad_repair_verify/products.png`
  - `runtime/gumroad_repair_verify/public.png`
  - `runtime/gumroad_after_sim_abort/result.json`

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

### TG stress test after platform closure
- Status: `done`
- Mode:
  - safe local owner simulator
  - no live create/publish side effects
- Confirmed:
  - owner research chain passed end-to-end
  - expanded owner stress scenario passed `12/12`
  - simulator now has deterministic safe intercepts for owner follow-ups like current work status, Berlin weather/time and simple recipe requests
- Evidence:
  - `reports/VITO_TG_OWNER_SIM_phase_owner_research_chain_2026-03-08_1305UTC.json`
  - `reports/VITO_TG_OWNER_SIM_phase_owner_stress_safe_2026-03-08_1307UTC.json`

### Ko-fi
- Status: `done`
- Working object:
  - published product `https://ko-fi.com/s/c6c9031adb`
- Confirmed:
  - challenge-free entry to Ko-fi home/manage in headed browser mode
  - `Add Product` modal opens
  - exact modal path works:
    - `#Name`
    - hidden `#Description`
    - `#Type = DIGITAL`
    - `#shopModalNextStep`
  - item editor opens on `/shop/items/add`
  - preview image upload works through the first file input
  - asset PDF upload works only through `Upload a file` file chooser path
  - required terms checkbox is hidden and must be set via `#agreeWithShopTerms`
  - final commit button is exact input `#saveAndPublishButton`
  - publish lands on the public product URL with share modal
  - product survives reload in shop settings and public page
- Evidence:
  - `runtime/kofi_reprobe/01.png`
  - `runtime/kofi_reprobe/02.png`
  - `runtime/kofi_reprobe/03.png`
  - `runtime/kofi_publish_exact3/01_before_submit.png`
  - `runtime/kofi_publish_exact3/02_after_submit.png`
  - `runtime/kofi_publish_exact3/03_settings_reload.png`
  - `runtime/kofi_publish_exact3/04_public_verify.png`
  - `runtime/kofi_publish_exact3/result.json`

### Reddit social package
- Status: `done`
- Working object:
  - live community post in `r/sideprojects`
  - permalink: `https://www.reddit.com/r/sideprojects/comments/1rob46e/built_a_creator_swipefile_kit_and_want_feedback/`
- Confirmed:
  - profile posting routes are rejected and must not be used as primary path
  - community-first route `r/sideprojects/submit/?type=TEXT` works
  - exact live browser flow required:
    - fill title through shadow textarea `faceplate-textarea-input[name='title'] -> #innerTextArea`
    - fill body through `shreddit-composer#post-composer_bodytext [contenteditable='true']`
    - open flair dialog via `#reddit-post-flair-button`
    - click `#view-all-flairs-button`
    - choose `#post-flair-radio-input-4` (`Showcase: Purchase Required`)
    - click `#post-flair-modal-apply-button`
    - submit through inner shadow button `#inner-post-submit-button`
  - server returns GraphQL `CreatePost` with `ok=true`
  - permalink opens and contains title/body text after reload
- Evidence:
  - `runtime/reddit_sideprojects_createpost_final/result.json`
  - `runtime/reddit_sideprojects_post_verify2/result.json`
  - `runtime/reddit_sideprojects_ui_flair_real/result.json`
  - `runtime/reddit_sideprojects_createpost_response2/result.json`
  - `runtime/reddit_graphql_probe/events.json`
  - `runtime/reddit_old_profile_link/result.json`

## Paused Blocked

### KDP paperback from published ebook
- Status: `paused_blocked`
- Blocker:
  - the exact owner-canonical create path can no longer be replayed safely because the linked paperback already exists and is already in review
- Confirmed:
  - Bookshelf exposes the existing paperback directly with pricing/edit links
  - no fresh `Create paperback` fork entry remains for this item
  - replaying the create path now would require deleting or unlinking the current print object, which violates the safety rule against damaging existing work without explicit owner instruction
- Current working object:
  - `document_id = A8T0ZQ5CNS6`
- Evidence:
  - `runtime/remote_auth/paperback_canonical_reprobe/result.json`
  - `runtime/remote_auth/paperback_previewer_after_approve_click.png`
  - `runtime/remote_auth/paperback_pricing_all_markets_after_save.png`
- Commit:
  - `5445436`

## Done

### X/Twitter social package
- Status: `done`
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
- Confirmed:
  - public Etsy-source post exists:
    - `https://x.com/bot_vito/status/2030350266571141526`
  - public Gumroad-source post exists:
    - `https://x.com/bot_vito/status/2030627652764090711`
  - image, SEO-style text, hashtags and product link are present
- Evidence:
  - `runtime/twitter_gumroad_verify/profile.png`

### Pinterest social package
- Status: `done`
- Required:
  - properly оформленный pin
  - нормальный visual
  - title/description
  - outbound link to current product
  - screenshot evidence
  - reusable runbook for future products/platforms
- Confirmed:
  - one live working pin remains:
    - `https://www.pinterest.com/pin/1134203487424108921`
  - duplicate live pins were removed through owner edit flow:
    - `1134203487424140507`
    - `1134203487424108589`
    - `1134203487424138402`
  - final pin page shows real description block
  - final pin page shows outbound Etsy product link button
  - profile now exposes only the single remaining live pin plus its analytics route
- publish state stores the intended title/description/url
- Evidence:
  - `runtime/pinterest_pin_verify_8921.json`
  - `runtime/pinterest_delete_duplicate_0507/result.json`
  - `runtime/pinterest_delete_1134203487424108589/result.json`
  - `runtime/pinterest_delete_1134203487424138402/result.json`
  - `runtime/pinterest_after_cleanup_verify/result.json`

## Commit Log For This Checklist Wave
- `5445436` — KDP paperback runbook and pricing flow
- `e567541` — Printful linked Etsy success accepted in adapter
- `fd5f55a` — Ko-fi screenshot-first Cloudflare gate recorded
