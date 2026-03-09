import pytest


class TestTranslationAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.translation_agent import TranslationAgent
        return TranslationAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    @pytest.mark.asyncio
    async def test_translate_local_fallback_includes_skill_pack(self, agent):
        agent.llm_router = None
        result = await agent.translate("hello", "en", "de")
        assert result.success is True
        assert result.metadata["mode"] == "local_fallback"
        assert "skills" in result.metadata
        assert "quality_checks" in result.metadata
        assert "glossary_terms" in result.metadata

    @pytest.mark.asyncio
    async def test_detect_language_identity_metadata(self, agent):
        agent.llm_router = None
        result = await agent.detect_language("Hallo welt")
        assert result.success is True
        assert "skills" in result.metadata

    @pytest.mark.asyncio
    async def test_localize_listing_includes_locale_notes(self, agent):
        agent.llm_router = None
        result = await agent.localize_listing({"title": "AI Etsy SEO Guide", "description": "Sell better on Etsy"}, "de")
        assert result.success is True
        assert result.metadata["locale_profile"]["currency"] == "EUR"
