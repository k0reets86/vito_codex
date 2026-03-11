"""TranslationAgent — Agent 08: перевод и локализация. Языки: EN/DE/UA/PL."""

import time

from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.translation_runtime import (
    build_consistency_checks,
    build_listing_localization_notes,
    build_translation_route,
)
from modules.weak_agent_runtime import translation_recovery_hints

logger = get_logger("translation_agent", agent="translation_agent")
SUPPORTED_LANGS = ["en", "de", "ua", "pl"]


class TranslationAgent(BaseAgent):
    NEEDS = {
        "translate": ["glossary_memory", "listing_context"],
        "localize": ["listing_context", "seo_context"],
        "*": ["language_rules"],
    }

    def __init__(self, **kwargs):
        super().__init__(name="translation_agent", description="Перевод и локализация: EN, DE, UA, PL", **kwargs)
        self._cache: dict[str, str] = {}

    @property
    def capabilities(self) -> list[str]:
        return ["translate", "localize"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "translate":
                result = await self.translate(kwargs.get("text", kwargs.get("step", "")), kwargs.get("source_lang", "en"), kwargs.get("target_lang", "de"))
            elif task_type == "localize":
                result = await self.localize_listing(kwargs.get("listing_data", {}), kwargs.get("target_lang", "de"))
            elif task_type == "detect_language":
                result = await self.detect_language(kwargs.get("text", ""))
            else:
                result = await self.translate(kwargs.get("step", task_type), "en", "de")
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def translate(self, text: str, source_lang: str, target_lang: str) -> TaskResult:
        src = self._normalize_lang(source_lang)
        tgt = self._normalize_lang(target_lang)
        raw_text = (text or "").strip()
        route = build_translation_route(src, tgt, raw_text)
        if src == tgt:
            return TaskResult(success=True, output=raw_text, metadata={"mode": "identity", **route, **self.get_skill_pack()})

        cache_key = f"translate::{src}->{tgt}::{raw_text.lower()}"
        if cache_key in self._cache:
            return TaskResult(success=True, output=self._cache[cache_key], metadata={"cached": True, **self.get_skill_pack()})

        local = self._local_translate(raw_text, src, tgt)
        if not self.llm_router:
            quality_checks = build_consistency_checks(raw_text, local, route["glossary_terms"])
            self._cache[cache_key] = local
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "mode": "local_fallback",
                    "source_lang": src,
                    "target_lang": tgt,
                    "translation_quality_hint": "dictionary_or_prefix_fallback",
                    "quality_checks": quality_checks,
                    "recovery_hints": translation_recovery_hints(quality_checks),
                    **route,
                    **self.get_skill_pack(),
                },
            )

        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=(
                f"Переведи с {src} на {tgt}. Сохрани стиль и тон. "
                "Верни только перевод без пояснений.\n\n"
                f"Текст:\n{raw_text}"
            ),
            estimated_tokens=2000,
        )
        output = response or local
        cost = 0.0
        if response:
            cost = 0.01
            self._record_expense(cost, f"Translate {src}->{tgt}")
        quality_checks = build_consistency_checks(raw_text, output, route["glossary_terms"])
        self._cache[cache_key] = output
        return TaskResult(
            success=True,
            output=output,
            cost_usd=cost,
            metadata={
                "source_lang": src,
                "target_lang": tgt,
                "translation_quality_hint": "llm_translation_with_local_fallback",
                "quality_checks": quality_checks,
                "recovery_hints": translation_recovery_hints(quality_checks),
                **route,
                **self.get_skill_pack(),
            },
        )

    async def localize_listing(self, listing_data: dict, target_lang: str) -> TaskResult:
        tgt = self._normalize_lang(target_lang)
        local = self._local_localize_listing(listing_data, tgt)
        notes = build_listing_localization_notes(listing_data, tgt)
        quality_checks = build_consistency_checks(
            str(listing_data.get("title", "")).strip(),
            str(local),
            notes.get("seo_keywords") or [],
        )
        if not self.llm_router:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "mode": "local_fallback",
                    "quality_checks": quality_checks,
                    "recovery_hints": translation_recovery_hints(quality_checks),
                    **notes,
                    **self.get_skill_pack(),
                },
            )

        text = "\n".join(f"{k}: {v}" for k, v in listing_data.items())
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Локализуй листинг на {tgt}. Адаптируй для местного рынка.\n\n{text}",
            estimated_tokens=2000,
        )
        if not response:
            return TaskResult(
                success=True,
                output=local,
                metadata={
                    "mode": "local_fallback",
                    "quality_checks": quality_checks,
                    "recovery_hints": translation_recovery_hints(quality_checks),
                    **notes,
                    **self.get_skill_pack(),
                },
            )
        llm_checks = build_consistency_checks(
            str(listing_data.get("title", "")).strip(),
            str(response),
            notes.get("seo_keywords") or [],
        )
        return TaskResult(
            success=True,
            output=response,
            cost_usd=0.01,
            metadata={
                "localized_lang": tgt,
                "quality_checks": llm_checks,
                "recovery_hints": translation_recovery_hints(llm_checks),
                **notes,
                **self.get_skill_pack(),
            },
        )

    async def detect_language(self, text: str) -> TaskResult:
        sample = (text or "")[:500]
        local_lang = self._local_detect_language(sample)
        if not self.llm_router:
            return TaskResult(success=True, output=local_lang, metadata={"mode": "local_fallback", **self.get_skill_pack()})

        response = await self._call_llm(
            task_type=TaskType.ROUTINE,
            prompt=f"Определи язык текста. Ответь одним кодом (en/de/ua/pl/ru/other):\n{sample}",
            estimated_tokens=100,
        )
        if not response:
            return TaskResult(success=True, output=local_lang, metadata={"mode": "local_fallback", **self.get_skill_pack()})
        return TaskResult(success=True, output=self._normalize_lang(response.strip().lower()[:5]), metadata=self.get_skill_pack())

    def _normalize_lang(self, lang: str) -> str:
        val = (lang or "").strip().lower()
        aliases = {"uk": "ua", "ua-ua": "ua", "de-de": "de", "en-us": "en", "en-gb": "en", "pl-pl": "pl"}
        normalized = aliases.get(val, val)
        return normalized if normalized in {"en", "de", "ua", "pl", "ru"} else "en"

    def _local_detect_language(self, text: str) -> str:
        sample = (text or "").lower()
        if not sample:
            return "en"
        if any(ch in sample for ch in "ąćęłńóśźż"):
            return "pl"
        if any(ch in sample for ch in "äöüß"):
            return "de"
        if any(ch in sample for ch in "іїєґ"):
            return "ua"
        if any("а" <= ch <= "я" or ch == "ё" for ch in sample):
            return "ru"
        return "en"

    def _local_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text:
            return ""
        tiny_dict = {
            ("hello", "en", "de"): "hallo",
            ("hello", "en", "pl"): "czesc",
            ("hello", "en", "ua"): "privit",
            ("world", "en", "de"): "welt",
            ("world", "en", "pl"): "swiat",
            ("thank you", "en", "de"): "danke",
            ("thank you", "en", "pl"): "dziekuje",
            ("digital planner", "en", "de"): "digitaler planer",
            ("digital planner", "en", "pl"): "cyfrowy planer",
        }
        normalized = text.strip().lower()
        direct = tiny_dict.get((normalized, source_lang, target_lang))
        if direct:
            return direct
        return f"[{target_lang}] {text}"

    def _local_localize_listing(self, listing_data: dict, target_lang: str) -> str:
        title = str(listing_data.get("title", "")).strip()
        description = str(listing_data.get("description", "")).strip()
        tags = listing_data.get("tags", [])
        localized_title = self._local_translate(title, "en", target_lang) if title else ""
        localized_description = self._local_translate(description, "en", target_lang) if description else ""
        tags_str = ", ".join(str(t).strip() for t in tags if str(t).strip())
        lines = [f"localized_lang: {target_lang}"]
        if localized_title:
            lines.append(f"title: {localized_title}")
        if localized_description:
            lines.append(f"description: {localized_description}")
        if tags_str:
            lines.append(f"tags: {tags_str}")
        return "\n".join(lines)
