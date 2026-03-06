"""Shared selector bank for Gumroad browser flows (consolidated from legacy scripts)."""

from __future__ import annotations


NEXT_SELECTORS = [
    'button[type="submit"][form^="new-product-form"]',
    'button:has-text("Next: Customize")',
    'button:has-text("Next")',
]

SAVE_SELECTORS = [
    'button:has-text("Save and continue")',
    'button:has-text("Save changes")',
    'button:has-text("Save")',
]

PUBLISH_SELECTORS = [
    'button:has-text("Publish")',
    'button:has-text("Publish product")',
    'button:has-text("Make it public")',
    'button:has-text("Go live")',
    'button:has-text("Save and publish")',
    'a:has-text("Publish")',
    'label:has-text("Publish")',
]

PRODUCT_TAB_SELECTORS = [
    'button:has-text("Product")',
    'a:has-text("Product")',
]

CONTENT_TAB_SELECTORS = [
    'button:has-text("Content")',
    'a:has-text("Content")',
]

SHARE_TAB_SELECTORS = [
    'button:has-text("Share")',
    'a:has-text("Share")',
]
