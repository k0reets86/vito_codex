# Platform Execution Checklist — 2026-03-07

Rule:
- Every live platform step must be confirmed screenshot-first: full page before action, full page after action, then URL + DOM + screenshot must agree.

## Active order
1. Etsy existing draft
2. Printful -> Etsy browser flow
3. KDP paperback from published ebook
4. Ko-fi
5. Gumroad

## 1. Etsy existing draft
- [x] reuse one existing draft only
- [x] no new drafts
- [x] title/description/price/type filled
- [x] digital file attached
- [x] photos/previews attached
- [x] tags/SEO/required attributes filled
- [x] evidence captured
- [x] runbook written to knowledge
- [x] commit

## 2. Printful -> Etsy browser flow
- [x] no false API success
- [x] create product in Printful browser flow
- [x] fill product card
- [x] send/publish to Etsy
- [x] verify Etsy draft created
- [x] runbook written to knowledge
- [x] commit
- Evidence:
  - Printful template/product path proved on `99888631`
  - Linked Etsy draft: `4468240834`
  - Adapter acceptance fixed in commit `e567541`

## 3. KDP paperback from published ebook
- [ ] start from published ebook
- [ ] use exact UI fork Publish -> Create paperback
- [ ] create fresh paperback draft
- [x] fill paperback draft
- [x] evidence captured
- [x] runbook written to knowledge
- [x] commit
- Current working paperback object:
  - `A8T0ZQ5CNS6`
- Current state:
  - Content approved via previewer
  - Print pricing persisted on `print-setup/paperback/<doc>/pricing`
  - Package committed in `5445436`
- Remaining gap:
  - Re-run exact owner-required fork from published ebook UI and recreate paperback once more as canonical runbook

## 4. Ko-fi
- [x] verify real browser flow
- [x] confirm whether Cloudflare is bypassable
- [ ] if yes: create real draft/post
- [x] if no: honest gate + login runbook
- [x] knowledge
- [ ] commit
- Current state:
  - screenshot-first probe confirms `Just a moment...` on both home and shop manage
  - evidence: `runtime/kofi_screenshot_probe.json`, `runtime/kofi_screenshot_probe_home.png`, `runtime/kofi_screenshot_probe_manage.png`

## 5. Gumroad
- [ ] wait for fresh valid draft after limit reset
- [ ] attach product file
- [ ] attach cover/preview
- [ ] set tags/category
- [ ] publish/share
- [ ] knowledge
- [ ] commit
