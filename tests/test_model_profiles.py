from modules.model_profiles import ModelProfiles


def test_model_profiles_seed_and_list(tmp_path):
    db = str(tmp_path / "profiles.db")
    mp = ModelProfiles(sqlite_path=db)
    rows = mp.list_profiles(limit=20)
    names = {r["profile_name"] for r in rows}
    assert "balanced" in names
    assert "economy" in names
    assert "quality" in names


def test_model_profiles_save_apply_delete(tmp_path):
    db = str(tmp_path / "profiles.db")
    mp = ModelProfiles(sqlite_path=db)
    out = mp.save_profile(
        profile_name="night_ops",
        default_model="openai/gpt-4o-mini",
        enabled_models="openai/gpt-4o-mini",
        disabled_models="anthropic/claude-opus-4-1",
        notes="overnight low-cost profile",
    )
    assert out["ok"] is True
    updates = mp.profile_updates("night_ops")
    assert updates["OPENROUTER_DEFAULT_MODEL"] == "openai/gpt-4o-mini"
    assert "LLM_DISABLED_MODELS" in updates
    deleted = mp.delete_profile("night_ops")
    assert deleted is True
