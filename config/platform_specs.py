"""Platform product specifications — knowledge base for all VITO agents.

Contains detailed specs for creating products on each platform.
Agents (content_creator, publisher, ecommerce, designer) reference this
to ensure products meet all platform requirements.
"""

GUMROAD_SPEC = """
=== GUMROAD PRODUCT SPECIFICATION ===

1. SELLER PROFILE (one-time setup)
- Username: URL = username.gumroad.com
- Logo/Avatar: min 200×200 px, PNG/JPG
- Bio: short description
- Colors: background + accent (6 font options)

2. REQUIRED PRODUCT FIELDS
- name: product title (clear, with keyword) [REQUIRED]
- description: full description, HTML supported, bullet points, CTA [REQUIRED]
- price: in CENTS (1700 = $17.00). 0 = pay-what-you-want [REQUIRED]
- summary: 1-2 sentences shown under price [RECOMMENDED]
- custom_permalink: slug for URL (no special chars) [RECOMMENDED]
- call_to_action: "I want this!" / "Buy this" / "Pay" [OPTIONAL]
- published: true/false [OPTIONAL]

3. PRICING OPTIONS
- Fixed price: price in cents (e.g. 1700 = $17)
- Pay-what-you-want: price=0 + suggested_price
- Minimum + PWYW: price=500 + allow_pwyw toggle

4. SETTINGS
- Sales limit (number of copies)
- Allow quantity selection
- Show sales counter
- Mark as e-publication (for EU VAT)
- Custom refund policy text

5. MEDIA FILES

Cover Image:
- Size: 1280×720 px (16:9) — OFFICIAL STANDARD
- Format: PNG, JPEG, GIF, MOV (video)
- Max: up to 8 covers
- YouTube/Vimeo links accepted instead of files
- ALL covers must be same height
- CANNOT use PDF as cover
- CANNOT use #, $, _, +, &, ;, :, % in filename

Thumbnail:
- Size: min 600×600 px (square)
- Used in: buyer library, Discover, profile
- AUTO-CROP: Gumroad crops center of 1280×720 cover → square
- DESIGN RULE: keep key content in center ~720×720 zone of cover

6. PRODUCT CONTENT (what buyer receives)
- Max file size: 16 GB (for $1+ products)
- Max for $0 products: 25 MB
- Formats: any (PDF, ZIP, MP4, PSD, etc.)
- Multiple files: YES
- Content page: text blocks, headers, buttons, links, images, multiple pages/tabs
- License keys: supported (for software)

7. DISCOVERY / SEO
- Category: one of 18 (3D, Audio, Books, Comedy, Comics, Crafts, Dance, Design,
  Education, Fiction, Film, Games, Music, Photography, Podcasts,
  Self-improvement, Software, Templates)
- Tags: multiple tags, shown on profile if 9+ products
- NSFW toggle: for adult content
- Rating: 1-5 stars (must enable for Discover visibility)
- Boosted Discover: extra commission → higher in search (only charged on Discover sales)

8. VARIANTS
- Multiple price tiers per product
- Different content per tier
- Example: Basic $9 / Pro $29 / VIP $79

9. API
- POST /v2/products — create (returns 404, removed from source code)
- PUT /v2/products/:id — update (returns 404, removed from source code)
- GET /v2/products — list products
- PATCH /v2/products/:id/enable — publish
- PATCH /v2/products/:id/disable — unpublish
- DELETE /v2/products/:id — delete
- FILE UPLOAD: API does NOT support direct upload — use Playwright

10. COMMISSIONS
- Gumroad fee: 10% per sale
- Stripe/PayPal: 2.9% + $0.30
- Discover boost: additional % (optional)

11. INTEGRATIONS
- Facebook Pixel, Google Analytics, Custom JS on checkout
- Zapier, Circle/Discord (auto-invite), Webhooks (Ping API)

=== CHECKLIST FOR PERFECT PRODUCT ===
□ name — clear, with target keyword
□ description — HTML, bullet points, CTA, benefits-focused
□ summary — 1-2 sentences under price
□ price — in cents (1700 = $17)
□ cover — 1280×720 PNG, key content centered
□ thumbnail — 600×600 (or center crop of cover)
□ file — PDF/ZIP, uploaded via web UI
□ category — one of 18
□ tags — 5-10 relevant
□ custom_permalink — clean slug, no special chars
□ published — true
□ rating display — enabled (for Discover visibility)
"""

# Platform specs dict — agents can look up specs by platform name
PLATFORM_SPECS = {
    "gumroad": GUMROAD_SPEC,
}


def get_platform_spec(platform: str) -> str:
    """Get product specification for a platform. Returns empty string if unknown."""
    return PLATFORM_SPECS.get(platform.lower(), "")
