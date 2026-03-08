import json

from modules.telegram_nlu_router import route_owner_dialogue


def test_route_owner_dialogue_handles_numeric_research_choice():
    active = {
        "research_options_json": json.dumps(
            [
                {"title": "Prompt Pack", "score": 88, "platform": "gumroad"},
                {"title": "Planner", "score": 81, "platform": "etsy"},
            ],
            ensure_ascii=False,
        )
    }
    result = route_owner_dialogue("2", active)
    assert result is not None
    assert result["intent"] == "question"
    assert "Зафиксировал вариант 2" in result["response"]
    assert result["selected"]["title"] == "Planner"


def test_route_owner_dialogue_handles_platform_create_from_selected_research():
    active = {
        "research_options_json": json.dumps(
            [
                {"title": "Prompt Pack", "score": 88, "platform": "gumroad"},
                {"title": "Planner", "score": 81, "platform": "etsy"},
            ],
            ensure_ascii=False,
        ),
        "selected_research_json": json.dumps({"title": "Planner", "score": 81, "platform": "etsy"}, ensure_ascii=False),
        "selected_research_title": "Planner",
    }
    result = route_owner_dialogue("создавай на etsy", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["etsy"]
    assert "Собираю и запускаю работу на etsy" in result["response"]
    assert result["actions"][0]["action"] == "run_product_pipeline"


def test_route_owner_dialogue_handles_platform_summary():
    active = {"selected_research_title": "Planner"}
    result = route_owner_dialogue("сделай короткую сводку по платформам", active)
    assert result is not None
    assert result["intent"] == "question"
    assert "Etsy" in result["response"]
    assert "Gumroad" in result["response"]
    assert "KDP" in result["response"]
