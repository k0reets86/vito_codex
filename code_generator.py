"""CodeGenerator — мост между LLM и SelfUpdater.

Генерирует unified diff патчи через LLM (TaskType.CODE → дешёвые модели),
затем безопасно применяет через SelfUpdater (backup → apply → test → rollback).

Механизмы защиты:
  - PROTECTED_FILES: comms_agent.py, main.py, .env, config/settings.py
  - MAX_PATCH_SIZE: 10000 символов — предотвращает случайную перезапись
  - Каждое изменение → Telegram уведомление владельцу
"""

from pathlib import Path
from typing import Any, Optional

from config.logger import get_logger
from llm_router import LLMRouter, TaskType

logger = get_logger("code_generator", agent="code_generator")

PROJECT_ROOT = Path(__file__).parent

PROTECTED_FILES = frozenset({
    "comms_agent.py",
    "main.py",
    ".env",
    "config/settings.py",
})

MAX_PATCH_SIZE = 10000  # символов


class CodeGenerator:
    def __init__(self, llm_router: LLMRouter, self_updater, comms):
        self.llm_router = llm_router
        self.self_updater = self_updater
        self.comms = comms
        logger.info("CodeGenerator инициализирован", extra={"event": "init"})

    async def generate_patch(self, target_file: str, instruction: str,
                             context: str = "") -> Optional[str]:
        """Генерирует unified diff для target_file через LLM.

        Returns:
            Patch string или None если генерация не удалась.
        """
        # 1. Проверка PROTECTED_FILES
        normalized = target_file.replace("\\", "/")
        for protected in PROTECTED_FILES:
            if normalized == protected or normalized.endswith(f"/{protected}"):
                logger.warning(
                    f"Попытка изменить защищённый файл: {target_file}",
                    extra={"event": "protected_file_blocked", "context": {"file": target_file}},
                )
                return None

        # 2. Прочитать текущий код
        file_path = PROJECT_ROOT / target_file
        if not file_path.exists():
            logger.error(f"Файл не найден: {file_path}", extra={"event": "file_not_found"})
            return None

        try:
            current_code = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Ошибка чтения {file_path}: {e}", extra={"event": "file_read_error"})
            return None

        if len(current_code) > 50000:
            logger.warning(f"Файл слишком большой: {len(current_code)} символов", extra={"event": "file_too_large"})
            return None

        # 3. Вызвать LLM
        prompt = (
            f"Generate a unified diff (git diff format) for the following change.\n\n"
            f"File: {target_file}\n"
            f"Instruction: {instruction}\n"
        )
        if context:
            prompt += f"Context: {context}\n"
        prompt += (
            f"\n--- Current code ---\n{current_code}\n--- End code ---\n\n"
            f"IMPORTANT:\n"
            f"- Output ONLY the unified diff, no explanations\n"
            f"- Use correct --- a/ and +++ b/ headers\n"
            f"- Include sufficient context lines (3+)\n"
            f"- Make minimal changes to accomplish the instruction\n"
        )

        response = await self.llm_router.call_llm(
            task_type=TaskType.CODE,
            prompt=prompt,
            estimated_tokens=2000,
        )

        if not response:
            logger.warning("LLM не вернул патч", extra={"event": "patch_generation_failed"})
            return None

        # 4. Извлечь diff из ответа
        patch = self._extract_diff(response)
        if not patch:
            logger.warning("Не удалось извлечь diff из ответа LLM", extra={"event": "diff_extraction_failed"})
            return None

        # 5. Валидировать размер
        if len(patch) > MAX_PATCH_SIZE:
            logger.warning(
                f"Патч слишком большой: {len(patch)} > {MAX_PATCH_SIZE}",
                extra={"event": "patch_too_large"},
            )
            return None

        logger.info(
            f"Патч сгенерирован для {target_file}: {len(patch)} символов",
            extra={"event": "patch_generated", "context": {"file": target_file, "size": len(patch)}},
        )
        return patch

    async def apply_change(self, target_file: str, instruction: str,
                           context: str = "", notify: bool = True) -> dict[str, Any]:
        """Генерирует и применяет изменение: generate_patch → apply_patch → notify."""
        logger.info(
            f"Применение изменения: {target_file} — {instruction[:80]}",
            extra={"event": "apply_change_start", "context": {"file": target_file}},
        )

        # 1. Генерация
        patch = await self.generate_patch(target_file, instruction, context)
        if not patch:
            return {"success": False, "error": "Не удалось сгенерировать патч"}

        # 2. Применение через SelfUpdater (backup → apply → test → rollback)
        result = await self.self_updater.apply_patch(patch, source=f"code_generator:{target_file}")

        # 3. Telegram уведомление
        if notify and self.comms:
            status = "успешно" if result.get("success") else "откат"
            tests_info = ""
            if result.get("tests"):
                t = result["tests"]
                tests_info = f"\nТесты: {t.get('passed', 0)} passed, {t.get('failed', 0)} failed"
            try:
                await self.comms.send_message(
                    f"VITO CodeGenerator | Изменение {status}\n\n"
                    f"Файл: {target_file}\n"
                    f"Что: {instruction[:200]}{tests_info}"
                )
            except Exception as e:
                logger.debug(f"Ошибка уведомления: {e}", extra={"event": "notify_error"})

        logger.info(
            f"Изменение {'применено' if result.get('success') else 'откачено'}: {target_file}",
            extra={"event": "apply_change_done", "context": {"file": target_file, "success": result.get("success")}},
        )
        return result

    @staticmethod
    def _extract_diff(response: str) -> Optional[str]:
        """Извлекает unified diff из ответа LLM."""
        # Ищем в code blocks
        if "```" in response:
            blocks = response.split("```")
            for i, block in enumerate(blocks):
                if i % 2 == 1:  # внутри code block
                    content = block.strip()
                    if content.startswith("diff"):
                        content = content[4:].strip()
                    if content.startswith("---") or content.startswith("@@"):
                        return content
            # Попробуем самый большой code block
            for i, block in enumerate(blocks):
                if i % 2 == 1 and len(block.strip()) > 20:
                    return block.strip()

        # Ищем diff напрямую
        lines = response.split("\n")
        diff_start = None
        for i, line in enumerate(lines):
            if line.startswith("---") or line.startswith("diff --git"):
                diff_start = i
                break
        if diff_start is not None:
            return "\n".join(lines[diff_start:])

        return None
