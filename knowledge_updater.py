"""KnowledgeUpdater — еженедельное обновление знаний VITO.

- Обновление цен моделей через Perplexity
- Уплотнение старых воспоминаний в ChromaDB
- Перерасчёт паттернов (confidence decay)
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from config.logger import get_logger
from llm_router import LLMRouter, TaskType, MODEL_REGISTRY

logger = get_logger("knowledge_updater", agent="knowledge_updater")


class KnowledgeUpdater:
    def __init__(self, llm_router: LLMRouter, memory):
        self.llm_router = llm_router
        self.memory = memory
        logger.info("KnowledgeUpdater инициализирован", extra={"event": "init"})

    async def run_weekly_update(self) -> dict[str, Any]:
        """Полный еженедельный цикл обновления знаний."""
        logger.info("Начало еженедельного обновления знаний", extra={"event": "weekly_update_start"})
        results = {}

        # 1. Обновление цен моделей
        try:
            prices_updated = await self.update_model_prices()
            results["model_prices"] = prices_updated
        except Exception as e:
            logger.warning(f"Ошибка обновления цен: {e}", extra={"event": "prices_update_error"})
            results["model_prices"] = False

        # 2. Уплотнение воспоминаний
        try:
            compacted = self.compact_memories()
            results["memories_compacted"] = compacted
        except Exception as e:
            logger.warning(f"Ошибка уплотнения памяти: {e}", extra={"event": "compact_error"})
            results["memories_compacted"] = 0

        # 3. Перерасчёт паттернов
        try:
            patterns = self.recalculate_patterns()
            results["patterns_updated"] = patterns
        except Exception as e:
            logger.warning(f"Ошибка перерасчёта паттернов: {e}", extra={"event": "patterns_error"})
            results["patterns_updated"] = 0

        logger.info(
            f"Еженедельное обновление завершено: {results}",
            extra={"event": "weekly_update_done", "context": results},
        )
        return results

    async def update_model_prices(self) -> bool:
        """Запрашивает актуальные цены LLM через Perplexity и обновляет MODEL_REGISTRY в runtime."""
        prompt = (
            "Дай актуальные цены API (USD per 1K tokens) для следующих моделей:\n"
            "1. Claude Sonnet 4 (Anthropic) — input и output\n"
            "2. Claude Opus 4 (Anthropic) — input и output\n"
            "3. Claude Haiku 4.5 (Anthropic) — input и output\n"
            "4. OpenAI o3 — input и output\n"
            "5. Perplexity Sonar Pro — input и output\n\n"
            "Ответь строго в JSON формате:\n"
            '{"claude-sonnet": {"input": 0.003, "output": 0.015}, '
            '"claude-opus": {"input": 0.015, "output": 0.075}, '
            '"claude-haiku": {"input": 0.0008, "output": 0.004}, '
            '"gpt-o3": {"input": 0.01, "output": 0.04}, '
            '"perplexity": {"input": 0.003, "output": 0.015}}'
        )

        try:
            response = await self.llm_router.call_llm(
                task_type=TaskType.RESEARCH,
                prompt=prompt,
                estimated_tokens=500,
            )
            if not response:
                return False

            # Парсим JSON
            text = response.strip()
            if "```" in text:
                for block in text.split("```"):
                    block = block.strip()
                    if block.startswith("json"):
                        block = block[4:].strip()
                    if block.startswith("{"):
                        text = block
                        break

            prices = json.loads(text)

            # Обновляем MODEL_REGISTRY в runtime (не файл!)
            updated = 0
            for model_key, price_data in prices.items():
                if model_key in MODEL_REGISTRY:
                    model = MODEL_REGISTRY[model_key]
                    old_input = model.cost_per_1k_input
                    old_output = model.cost_per_1k_output
                    model.cost_per_1k_input = float(price_data.get("input", model.cost_per_1k_input))
                    model.cost_per_1k_output = float(price_data.get("output", model.cost_per_1k_output))
                    if model.cost_per_1k_input != old_input or model.cost_per_1k_output != old_output:
                        updated += 1
                        logger.info(
                            f"Цены обновлены для {model_key}: "
                            f"input ${old_input}→${model.cost_per_1k_input}, "
                            f"output ${old_output}→${model.cost_per_1k_output}",
                            extra={"event": "price_updated", "context": {"model": model_key}},
                        )

            logger.info(
                f"Обновлено {updated} моделей",
                extra={"event": "prices_update_done", "context": {"updated": updated}},
            )
            return updated > 0

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Ошибка парсинга цен: {e}", extra={"event": "prices_parse_error"})
            return False

    def compact_memories(self) -> int:
        """Уплотняет старые записи в ChromaDB (>30 дней, distance<0.15 → мерж)."""
        try:
            collection = self.memory._get_chroma()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

            # Получаем все документы
            all_docs = collection.get(include=["documents", "metadatas"])
            if not all_docs or not all_docs["ids"]:
                return 0

            # Находим старые записи
            old_ids = []
            for i, doc_id in enumerate(all_docs["ids"]):
                meta = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
                stored_at = meta.get("stored_at", "")
                if stored_at and stored_at < cutoff:
                    old_ids.append(i)

            if len(old_ids) < 2:
                return 0

            # Группируем похожие (используем query для поиска ближайших)
            compacted = 0
            processed = set()

            for idx in old_ids:
                if idx in processed:
                    continue

                doc_text = all_docs["documents"][idx]
                doc_id = all_docs["ids"][idx]

                # Ищем похожие
                results = collection.query(query_texts=[doc_text], n_results=3)
                if not results or not results["ids"][0]:
                    continue

                to_merge = []
                for j, rid in enumerate(results["ids"][0]):
                    if rid == doc_id:
                        continue
                    dist = results["distances"][0][j] if results["distances"] else 1.0
                    if dist < 0.15:
                        # Находим индекс в all_docs
                        if rid in all_docs["ids"]:
                            ridx = all_docs["ids"].index(rid)
                            if ridx in old_ids and ridx not in processed:
                                to_merge.append((rid, ridx, results["documents"][0][j]))

                if to_merge:
                    # Мержим: объединяем тексты, удаляем дубли
                    merged_text = doc_text
                    ids_to_delete = []
                    for mid, midx, mtext in to_merge:
                        merged_text += f"\n---\n{mtext}"
                        ids_to_delete.append(mid)
                        processed.add(midx)

                    # Обновляем основной документ
                    collection.update(
                        ids=[doc_id],
                        documents=[merged_text[:5000]],
                        metadatas=[{"stored_at": datetime.now(timezone.utc).isoformat(), "compacted": True}],
                    )

                    # Удаляем смерженные
                    if ids_to_delete:
                        collection.delete(ids=ids_to_delete)
                        compacted += len(ids_to_delete)

                processed.add(idx)

            logger.info(
                f"Уплотнено {compacted} воспоминаний",
                extra={"event": "memories_compacted", "context": {"count": compacted}},
            )
            return compacted

        except Exception as e:
            logger.warning(f"Ошибка уплотнения: {e}", extra={"event": "compact_error"}, exc_info=True)
            return 0

    def recalculate_patterns(self) -> int:
        """Перерасчёт confidence паттернов: повышение для успешных, decay для неиспользуемых."""
        try:
            conn = self.memory._get_sqlite()
            cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

            # Повышение confidence для часто используемых (times_applied > 5)
            conn.execute(
                """UPDATE patterns SET confidence = MIN(confidence + 0.05, 1.0)
                   WHERE times_applied > 5 AND confidence < 1.0"""
            )

            # Decay для неиспользуемых >30 дней
            conn.execute(
                """UPDATE patterns SET confidence = MAX(confidence - 0.1, 0.1)
                   WHERE created_at < ? AND times_applied <= 1""",
                (cutoff_30d,),
            )

            # Удаление паттернов с confidence < 0.15
            deleted = conn.execute(
                "DELETE FROM patterns WHERE confidence < 0.15"
            ).rowcount

            conn.commit()

            total_updated = conn.execute("SELECT COUNT(*) as cnt FROM patterns").fetchone()["cnt"]

            logger.info(
                f"Паттерны пересчитаны: {total_updated} активных, {deleted} удалено",
                extra={
                    "event": "patterns_recalculated",
                    "context": {"active": total_updated, "deleted": deleted},
                },
            )
            return total_updated

        except Exception as e:
            logger.warning(f"Ошибка перерасчёта паттернов: {e}", extra={"event": "patterns_error"})
            return 0
