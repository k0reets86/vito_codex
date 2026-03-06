from modules.workflow_recipes import get_workflow_recipe, list_workflow_recipes, platform_recipe


def test_workflow_recipes_contains_required_platforms():
    names = {r["name"] for r in list_workflow_recipes()}
    assert {
        "gumroad_publish",
        "etsy_publish",
        "kdp_publish",
        "kofi_publish",
        "twitter_publish",
        "reddit_publish",
        "pinterest_publish",
    }.issubset(names)


def test_platform_recipe_lookup():
    rec = platform_recipe("amazon_kdp")
    assert rec is not None
    assert rec["name"] == "kdp_publish"
    assert "verify_bookshelf_entry" in rec["steps"]


def test_get_workflow_recipe_single():
    rec = get_workflow_recipe("twitter_publish")
    assert rec is not None
    assert rec["platform"] == "twitter"
