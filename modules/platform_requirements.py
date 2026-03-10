from __future__ import annotations

from typing import Any

RUNBOOK_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "etsy": {
        "required_artifacts": ["title", "description", "price", "category", "tags", "main_file", "images"],
        "verify_points": ["editor_reload", "file_attached", "image_count", "tags_confirmed", "materials_confirmed"],
        "preferred_actions": ["create_once", "fill_details", "attach_file", "attach_images", "reload_verify"],
    },
    "gumroad": {
        "required_artifacts": ["title", "summary", "description", "category", "tags", "main_file", "cover", "thumbnail", "preview_gallery"],
        "verify_points": ["draft_confirmed", "main_file_attached", "cover_confirmed", "preview_confirmed", "thumbnail_confirmed", "public_page"],
        "preferred_actions": ["create_once", "content_pdf", "cover_upload", "thumbnail_upload", "save_and_continue", "reload_verify"],
    },
    "amazon_kdp": {
        "required_artifacts": ["details", "description", "keywords", "categories", "manuscript", "cover", "pricing"],
        "verify_points": ["bookshelf", "content_reload", "manuscript_uploaded", "cover_uploaded", "pricing_persisted"],
        "preferred_actions": ["resume_existing", "fill_details", "upload_content", "save_draft", "pricing_reload_verify"],
    },
    "printful": {
        "required_artifacts": ["design_file", "template", "mockups", "details", "sync_target"],
        "verify_points": ["template_saved", "publish_wizard", "etsy_edit_url"],
        "preferred_actions": ["open_product_page", "upload_design", "apply_design", "save_template", "publish_to_etsy"],
    },
    "kofi": {
        "required_artifacts": ["title", "description", "price", "file_or_link"],
        "verify_points": ["shop_settings_reload", "public_product_url"],
        "preferred_actions": ["authenticate", "open_shop_settings", "fill_product", "save_verify"],
    },
    "twitter": {
        "required_artifacts": ["text", "media_or_link"],
        "verify_points": ["permalink"],
        "preferred_actions": ["compose", "post", "verify_permalink"],
    },
    "pinterest": {
        "required_artifacts": ["title", "description", "image", "link"],
        "verify_points": ["pin_page", "description", "outbound_link"],
        "preferred_actions": ["create_pin", "fill_fields", "publish", "verify_pin_page"],
    },
    "reddit": {
        "required_artifacts": ["community", "title", "body_or_link", "image_optional", "flair_if_required"],
        "verify_points": ["submit_result", "post_url"],
        "preferred_actions": ["read_rules", "open_submit", "fill_form", "submit", "verify_post"],
    },
}
