from __future__ import annotations

import re
from pathlib import Path

from config.paths import PROJECT_ROOT
from config.settings import settings


class NotificationRouter:
    """Outbound owner-facing messaging policy and delivery helpers."""

    def __init__(self, agent, broadcast_queue) -> None:
        self._agent = agent
        self._queue = broadcast_queue

    def inline_file_paths(self, text: str) -> str:
        root_rx = re.escape(str(PROJECT_ROOT))
        file_pattern = re.compile(rf"({root_rx}/\S+\.(?:txt|md|json|py|csv|log))")
        found = file_pattern.findall(text)
        if not found:
            return text

        result = text
        for fp in found:
            path = Path(fp)
            replacement = ""
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rel_path = fp.replace(str(PROJECT_ROOT) + "/", "")
                        if len(content) <= 500:
                            replacement = f"\n{content}\n"
                        else:
                            replacement = f"\n{content[:500]}...\n(полный текст: {rel_path})\n"
                except Exception:
                    pass
            result = result.replace(f"\U0001f4ce {fp}", replacement)
            result = result.replace(fp, replacement)
        return "\n".join(line for line in result.split("\n") if line.strip())

    def should_send(self, text: str, level: str) -> bool:
        import os

        if (level or "").lower() == "cron":
            if not bool(getattr(settings, "TELEGRAM_CRON_ENABLED", False)):
                return False
            try:
                if self._agent._cancel_state and self._agent._cancel_state.is_cancelled():
                    return False
            except Exception:
                pass
            return True
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        mode = (self._agent._notify_mode or "minimal").lower()
        if mode == "all":
            return True
        if level in ("critical", "approval", "result"):
            return True
        if any(kw in text.lower() for kw in ["отчёт", "report", "готово", "готов", "результат"]):
            return True
        return False

    def guard_outgoing(self, text: str) -> str:
        lower = str(text or "").lower()
        safe_owner_controls = (
            "правило зафиксировано",
            "старые и опубликованные объекты не трогаются",
            "все текущие задачи снял",
            "остановил текущую работу",
            "продолжаю работу",
            "сейчас от тебя ничего не нужно",
            "ок, отменил текущий запрос",
            "ок, отложил",
        )
        if any(tok in lower for tok in safe_owner_controls):
            return str(text or "")
        try:
            from modules.fact_gate import gate_outgoing_claim

            decision = gate_outgoing_claim(text, evidence_hours=24)
            if not decision.allowed:
                return decision.text
        except Exception:
            risky = ("опублик", "загрузил", "загружен", "создан", "готов и", "is live", "published")
            if any(tok in lower for tok in risky):
                return "Это было предложение/план, а не подтверждённый факт выполнения. Нужна команда на запуск?"
            return str(text or "")
        return text

    def strip_technical_paths(self, text: str) -> str:
        s = str(text or "")
        if not s:
            return s
        root_rx = re.escape(str(PROJECT_ROOT))
        s = re.sub(rf"{root_rx}/\S+", "[внутренний файл]", s)
        s = re.sub(r"/tmp/\S+", "[временный файл]", s)
        return s

    def humanize_owner_text(self, text: str) -> str:
        s = str(text or "").strip()
        if not s:
            return s
        skip_tokens = (
            "request_id",
            "task_id",
            "job_id",
            "goal_id",
            "trace_id",
            "session_id",
            "workflow_id",
            "active task fixed",
            "активная задача зафиксирована",
            "workflow_session",
            "pending_approvals",
            "contract_invalid",
            "publisher_queue",
            "tooling_contract_failed",
            "traceback",
        )
        cleaned: list[str] = []
        for line in s.splitlines():
            ln = line.strip()
            low = ln.lower()
            if low.startswith(("план действий:", "вот план, что думаешь", "план:", "принял:")):
                continue
            if low.startswith("код получен.") and "подтверждаю вход" in low:
                continue
            if any(tok in low for tok in skip_tokens):
                continue
            if low.startswith("{") or low.startswith("[{") or low.startswith('"id"'):
                continue
            cleaned.append(line)
        out = "\n".join(cleaned).strip()
        out = re.sub(r"\n{3,}", "\n\n", out)
        if not out:
            return "Принял задачу в работу. Дам краткий прогресс и вернусь с результатом."
        return out

    async def send_message(self, text: str, level: str = "info") -> bool:
        agent = self._agent
        if not agent._bot:
            agent._logger.warning("Бот не запущен — сообщение не отправлено", extra={"event": "send_no_bot"})
            try:
                from modules.owner_inbox import write_outbox

                write_outbox(text)
                return True
            except Exception:
                return False
        try:
            if not self.should_send(text, level):
                agent._logger.debug("Сообщение подавлено политикой уведомлений", extra={"event": "message_suppressed"})
                return True
            guarded = self.guard_outgoing(text)
            inline_paths = bool(getattr(settings, "TELEGRAM_INLINE_FILE_CONTENT", False))
            clean = self.inline_file_paths(guarded) if inline_paths else self.humanize_owner_text(self.strip_technical_paths(guarded))
            if len(clean) > 4000:
                clean = clean[:4000] + "..."

            async def _send() -> None:
                await agent._bot.send_message(chat_id=agent._owner_id, text=clean)

            await self._queue.run(_send)
            agent._append_telegram_trace("out", clean, {"chat_id": int(agent._owner_id), "level": str(level or "info")})
            agent._logger.info(
                f"Сообщение отправлено ({len(clean)} символов)",
                extra={"event": "message_sent", "context": {"length": len(clean)}},
            )
            return True
        except Exception as e:
            agent._logger.error(f"Ошибка отправки: {e}", extra={"event": "send_failed"}, exc_info=True)
            try:
                from modules.telegram_fallback import send_message as fb_send

                token = getattr(agent._bot, "token", "") if agent._bot else ""
                if token and agent._owner_id:
                    ok = fb_send(token, str(agent._owner_id), clean if "clean" in locals() else text)
                    if ok:
                        agent._logger.info("Fallback Telegram send ok", extra={"event": "send_fallback_ok"})
                        return True
            except Exception:
                pass
            try:
                from modules.owner_inbox import write_outbox

                write_outbox(clean if "clean" in locals() else text)
                return True
            except Exception:
                pass
            return False

    async def send_file(self, file_path: str, caption: str = "") -> bool:
        agent = self._agent
        if not agent._bot:
            try:
                from modules.owner_inbox import write_outbox

                write_outbox(f"Файл готов: {file_path}\n{caption}")
                return True
            except Exception:
                return False
        path = Path(file_path)
        if not path.exists():
            agent._logger.error(f"Файл не найден: {file_path}", extra={"event": "file_not_found"})
            return False
        try:
            safe_caption = self.guard_outgoing(caption) if caption else ""

            async def _send() -> None:
                with open(path, "rb") as f:
                    await agent._bot.send_document(chat_id=agent._owner_id, document=f, caption=safe_caption[:1024])

            await self._queue.run(_send)
            agent._logger.info(
                f"Файл отправлен: {path.name}",
                extra={"event": "file_sent", "context": {"file": path.name}},
            )
            return True
        except Exception as e:
            agent._logger.error(f"Ошибка отправки файла: {e}", extra={"event": "file_send_failed"}, exc_info=True)
            try:
                from modules.telegram_fallback import send_document as fb_doc

                token = getattr(agent._bot, "token", "") if agent._bot else ""
                if token and agent._owner_id:
                    safe_caption = self.guard_outgoing(caption) if caption else ""
                    ok = fb_doc(token, str(agent._owner_id), str(path), caption=safe_caption[:1024])
                    if ok:
                        agent._logger.info("Fallback Telegram file ok", extra={"event": "file_send_fallback_ok"})
                        return True
            except Exception:
                pass
            try:
                from modules.owner_inbox import write_outbox

                write_outbox(f"Файл готов: {file_path}\n{caption}")
                return True
            except Exception:
                pass
            return False

    async def send_response(self, update, text: str) -> None:
        text = self.guard_outgoing(text)
        inline_paths = bool(getattr(settings, "TELEGRAM_INLINE_FILE_CONTENT", False))
        if not inline_paths:
            clean_text = self.humanize_owner_text(self.strip_technical_paths(text))
            clean_text = "\n".join(line for line in clean_text.split("\n") if line.strip())
            if clean_text:
                if len(clean_text) > 4000:
                    clean_text = clean_text[:4000] + "..."
                await update.message.reply_text(clean_text, reply_markup=self._agent._main_keyboard())
            return

        root_rx = re.escape(str(PROJECT_ROOT))
        bin_pattern = re.compile(rf"(/(?:{root_rx}|tmp)/\S+\.(?:png|jpg|jpeg|webp|gif|pdf))")
        found_bins = bin_pattern.findall(text)
        clean_text = text
        for fp in found_bins:
            path = Path(fp)
            if path.exists():
                try:
                    await self.send_file(fp, caption=f"Файл: {path.name}")
                except Exception:
                    pass
            clean_text = clean_text.replace(f"\U0001f4ce {fp}", "")
            clean_text = clean_text.replace(fp, "")

        file_pattern = re.compile(rf"({root_rx}/\S+\.(?:txt|md|json|py|csv|log))")
        found_files = file_pattern.findall(clean_text)
        for fp in found_files:
            path = Path(fp)
            replacement = ""
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        rel_path = fp.replace(str(PROJECT_ROOT) + "/", "")
                        if len(content) <= 500:
                            replacement = f"\n{content}\n"
                        else:
                            replacement = f"\n{content[:500]}...\n(полный текст: {rel_path})\n"
                except Exception:
                    pass
            clean_text = clean_text.replace(f"\U0001f4ce {fp}", replacement)
            clean_text = clean_text.replace(fp, replacement)

        clean_text = "\n".join(line for line in clean_text.split("\n") if line.strip())
        if clean_text:
            if len(clean_text) > 4000:
                clean_text = clean_text[:4000] + "..."
            await update.message.reply_text(clean_text, reply_markup=self._agent._main_keyboard())
