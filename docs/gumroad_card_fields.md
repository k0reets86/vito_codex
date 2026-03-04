# Gumroad Product Card Fields (VITO)

This note captures the verified structure from the Gumroad “What are you creating?” flow and the edit page.

## Creation Flow (Products/New)
- Page title: "What are you creating?"
- Required fields:
  - Product type buttons (`button[data-type="digital"]`, `button[data-type="ebook"]`, etc.)
  - Name input (`input[id^="name-"]`)
  - Price input (`input[id^="price-"]`)
  - Next button: `button[type="submit"][form^="new-product-form"]` ("Next: Customize")

## Edit Page (Products/<slug>/edit)
Embedded JSON on the edit page provides authoritative state:
- Script element: `script[data-component-name="ProductEditPage"]`
- Key fields:
  - `unique_permalink` (slug)
  - `id` (product_id)
  - `product.tags` (array)
  - `product.taxonomy_id` (category)
  - `product.description`, `product.custom_summary`, `product.price_cents`

## Media (Cover + Thumbnail) — UI Specs
From the Product tab UI (verified in-app):
- Cover: “Images should be horizontal, at least 1280x720px, and 72 DPI.”
- Thumbnail: “Your image should be square, at least 600x600px, and JPG, PNG or GIF.”

## Share Tab (Category + Tags)
- Category input: `label: Category` → `input[role="combobox"]` (first)
- Tags input: `label: Tags` → `input[role="combobox"]` (second)

## Content Upload
- Content tab URL: `/products/<slug>/edit/content`
- Upload button: `button:has-text("Upload your files")`
- File input: `input[type="file"]` (non-image/non-audio for PDF)

## Publish Evidence
- Public URL format: `https://gumroad.com/l/<slug>`
- Public URL may respond with 200 or 302

## Notes
- Product state must be read after save via embedded JSON to verify tags/taxonomy.
- Publish confirmation should be based on public URL availability and screenshot evidence.

## Verified Working Flow (2026-03-04, target slug `yupwt`)
Use this exact order for stable execution on an existing test listing:
1. Open `/products/<slug>/edit` (target-only mode, no fallback to other listings).
2. Fill Product tab fields:
   - Title (`name`)
   - Short summary (`custom_summary`)
   - Long description (`description`)
   - Price (`price_cents`)
3. Upload cover/thumbnail on Product tab.
4. Open Share tab and set:
   - Category via first `input[role="combobox"]` (pick from suggestions)
   - Up to 5 tags via second `input[role="combobox"]` (pick from suggestions)
5. Open Content tab and ensure product has at least:
   - 1 PDF file
   - 2 image files (preview/gallery)
6. Save and re-read `ProductEditPage` JSON for validation:
   - `product.taxonomy_id` is present
   - `len(product.tags) >= 5`
   - `custom_summary` + `description` are non-empty
   - `existing_files` includes required file types for this product
7. For profile work mode, keep listing in draft:
   - click `Unpublish` (UI) and/or call API disable fallback
8. For live publish test:
   - publish (enable) -> verify public URL + `is_published=true`
   - return to draft (disable) after test if requested

### Important
- Category/tags are editable in draft mode (published state is not required).
- Final proof should include both:
  - browser state (`ProductEditPage` JSON),
  - API state (`/v2/products`) for cross-check.
