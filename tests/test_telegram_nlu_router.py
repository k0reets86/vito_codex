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


def test_route_owner_dialogue_handles_noisy_research_request():
    result = route_owner_dialogue("проведи глуюокое исслдование ниш цыфровых тваров", {})
    assert result is not None
    assert result["intent"] == "system_action"
    assert "исслед" in result["response"].lower()


def test_route_owner_dialogue_handles_short_platform_switch_and_draft_guard():
    active = {
        "research_options_json": json.dumps(
            [{"title": "Planner", "score": 81, "platform": "etsy"}],
            ensure_ascii=False,
        ),
        "selected_research_json": json.dumps({"title": "Planner", "score": 81, "platform": "etsy"}, ensure_ascii=False),
        "selected_research_title": "Planner",
    }
    result = route_owner_dialogue("а на амаз? но не публикуй пока", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["amazon_kdp"]
    assert "черновик" in result["response"].lower()
    assert "не запускаю" in result["response"].lower()


def test_route_owner_dialogue_handles_owner_need_question():
    result = route_owner_dialogue("что от меня надо?", {})
    assert result is not None
    assert result["intent"] == "question"
    assert "ничего" in result["response"].lower()


def test_route_owner_dialogue_handles_followup_platform_shortcut():
    active = {"text": "Printable Planner Bundle"}
    result = route_owner_dialogue("давай на етси", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["etsy"]
    assert "etsy" in result["response"].lower()
    assert "draft" in result["response"].lower()


def test_route_owner_dialogue_handles_followup_draft_only_without_platform():
    active = {"text": "Printable Planner Bundle"}
    result = route_owner_dialogue("не, стоп. тока черновик", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert "черновик" in result["response"].lower()
    assert "без публикации" in result["response"].lower()


def test_route_owner_dialogue_handles_followup_recommended():
    active = {
        "text": "Printable Planner Bundle",
        "selected_research_platform": "etsy",
    }
    result = route_owner_dialogue("мм не это. давай рекомндованый", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert "рекоменд" in result["response"].lower()
    assert "etsy" in result["response"].lower()


def test_route_owner_dialogue_handles_followup_recommended_without_topic():
    active = {}
    result = route_owner_dialogue("мм не это. давай рекомндованый", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert "рекоменд" in result["response"].lower()
    assert "draft" in result["response"].lower()


def test_route_owner_dialogue_explicit_platform_request_overrides_old_active_topic():
    active = {
        "text": "создай черновик товара на гумроад и заполни все поля, теги, описание и файлы",
    }
    result = route_owner_dialogue("создай черновик листинга на этси и заполни все поля, теги, описание и файл", active)
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["etsy"]
    assert "гумроад" not in result["response"].lower()
    assert "этси" not in result["response"].lower() or "etsy" in result["response"].lower()
    assert "printable product starter kit" in result["response"].lower()


def test_route_owner_dialogue_platform_create_without_meaningful_topic_uses_clean_default():
    result = route_owner_dialogue("создай черновик товара на гумроад и заполни все поля, теги, описание и файлы", {})
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["gumroad"]
    assert "товара все поля" not in result["response"].lower()
    assert "digital product starter kit" in result["response"].lower()


def test_route_owner_dialogue_printful_followup_does_not_echo_garbage_topic():
    result = route_owner_dialogue("создай принт через принтфул и проверь связку с этси", {})
    assert result is not None
    assert result["intent"] == "system_action"
    assert result["platforms"] == ["etsy", "printful"]
    assert "принт с" not in result["response"].lower()


def test_route_owner_dialogue_handles_noisy_gumroad_login_shortcut():
    result = route_owner_dialogue("зайди на гумр", {})
    assert result is not None
    assert "gumroad" in result["response"].lower()


def test_route_owner_dialogue_handles_noisy_pinterest_and_twitter_publish_requests():
    pin = route_owner_dialogue("опублкй тест пин в пинтрест с сылкой", {})
    tw = route_owner_dialogue("опублкй тест пост в твитер с кртинкой ссылкой и тгами", {})
    assert pin is not None
    assert tw is not None
    assert pin["intent"] == "system_action"
    assert tw["intent"] == "system_action"
    assert "pinterest" in pin["response"].lower()
    assert "twitter" in tw["response"].lower()
