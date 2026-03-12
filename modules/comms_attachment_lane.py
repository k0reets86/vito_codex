from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT


async def on_attachment(agent: Any, update: Any, context: Any) -> None:
    """Приём файлов/фото/видео от владельца и запуск document_agent."""
    if await agent._reject_stranger(update):
        return
    if not update.message:
        return
    if not agent._agent_registry:
        await update.message.reply_text("AgentRegistry не подключён.", reply_markup=agent._main_keyboard())
        return

    attachment_dir = PROJECT_ROOT / "input" / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)

    file_path = None
    task_type = "document_parse"

    try:
        if update.message.document:
            doc = update.message.document
            tg_file = await doc.get_file()
            safe_name = doc.file_name or f"document_{doc.file_unique_id}"
            file_path = attachment_dir / safe_name
            await tg_file.download_to_drive(custom_path=str(file_path))
            task_type = "document_parse"
        elif update.message.photo:
            photo = update.message.photo[-1]
            tg_file = await photo.get_file()
            file_path = attachment_dir / f"photo_{photo.file_unique_id}.jpg"
            await tg_file.download_to_drive(custom_path=str(file_path))
            task_type = "image_ocr"
        elif update.message.video:
            video = update.message.video
            tg_file = await video.get_file()
            file_path = attachment_dir / f"video_{video.file_unique_id}.mp4"
            await tg_file.download_to_drive(custom_path=str(file_path))
            task_type = "video_extract"

        if not file_path:
            await update.message.reply_text("Не удалось определить тип вложения.", reply_markup=agent._main_keyboard())
            return

        await update.message.reply_text(
            f"Файл получен: {file_path.name}\nНачинаю анализ.",
            reply_markup=agent._main_keyboard(),
        )

        result = await agent._agent_registry.dispatch(task_type, path=str(file_path))
        if not result or not result.success:
            err = getattr(result, "error", "Ошибка обработки")
            await update.message.reply_text(f"Ошибка обработки: {err}", reply_markup=agent._main_keyboard())
            return

        output = result.output or {}
        extracted = ""
        if isinstance(output, dict):
            if "text" in output:
                extracted = output.get("text") or ""
            elif "json" in output:
                extracted = json.dumps(output.get("json"), ensure_ascii=False)[:8000]
            elif "rows" in output:
                extracted = "\n".join([", ".join(row) for row in output.get("rows", [])])
        elif isinstance(output, str):
            extracted = output

        extracted = extracted.strip()
        caption = (update.message.caption or "").strip()
        if not extracted and caption:
            extracted = caption
        elif caption:
            extracted = caption + "\n\n" + extracted
        if not extracted:
            await update.message.reply_text("Извлечённый текст пуст.", reply_markup=agent._main_keyboard())
            return
        agent._log_owner_request(extracted[:2000], source=f"attachment:{file_path.name}")

        out_dir = PROJECT_ROOT / "output" / "attachments"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{Path(file_path).stem}_extracted.txt"
        out_path.write_text(extracted, encoding="utf-8", errors="ignore")

        preview = extracted[:3000]
        if len(extracted) > 3000:
            preview += f"\n\n(Полный текст сохранён в {out_path.relative_to(PROJECT_ROOT)})"
        await update.message.reply_text(preview, reply_markup=agent._main_keyboard())

        if await agent._maybe_brainstorm_from_text(update, extracted):
            return

        if agent._conversation_engine:
            try:
                if hasattr(agent._conversation_engine, "set_session"):
                    sid = str(update.effective_chat.id) if update and update.effective_chat else "telegram_owner"
                    agent._conversation_engine.set_session(sid)
                await agent._conversation_engine.process_message(
                    f"[Вложение:{file_path.name}]\n{extracted[:4000]}"
                )
            except Exception:
                pass
        agent._logger.info(
            "Вложение обработано",
            extra={"event": "attachment_processed", "context": {"file": file_path.name, "task_type": task_type}},
        )
    except Exception as e:
        agent._logger.error("Ошибка обработки вложения", extra={"event": "attachment_error"}, exc_info=True)
        await update.message.reply_text(f"Ошибка обработки вложения: {e}", reply_markup=agent._main_keyboard())
