from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config.logger import get_logger

logger = get_logger("patch_generator", agent="patch_generator")


class PatchGenerator:
    def __init__(self, llm_router, project_root: Path):
        self.llm = llm_router
        self.root = Path(project_root)

    async def generate(self, error: Exception, traceback_str: str, context: dict[str, Any] | None = None) -> dict[str, str]:
        files = self._extract_from_traceback(traceback_str)
        patch_files: dict[str, str] = {}
        if not files or self.llm is None:
            return patch_files
        try:
            from config.llm_router import TaskType
        except Exception:
            TaskType = None
        for rel in files[:3]:
            path = self.root / rel
            if not path.exists() or not path.is_file():
                continue
            try:
                src = path.read_text(encoding="utf-8")[:4000]
            except Exception:
                continue
            prompt = (
                f"Исправь Python-ошибку.\n"
                f"Ошибка: {type(error).__name__}: {error}\n"
                f"Traceback:\n{traceback_str[-2000:]}\n\n"
                f"Файл: {rel}\n"
                f"Текущий код:\n{src}\n\n"
                f"Верни только полный исправленный текст файла без пояснений."
            )
            try:
                if TaskType is not None:
                    fixed = await self.llm.call_llm(task_type=TaskType.CODE, prompt=prompt, system_prompt="")
                else:
                    fixed = await self.llm.call_llm(task_type="code", prompt=prompt, system_prompt="")
            except Exception as e:
                logger.warning(f"patch_generate_failed:{rel}:{e}")
                continue
            fixed_text = str(fixed or "").strip()
            if fixed_text:
                patch_files[rel] = fixed_text
        return patch_files

    def _extract_from_traceback(self, tb: str) -> list[str]:
        paths = re.findall(r'File "([^"]+\\.py)"', str(tb or ""))
        result: list[str] = []
        for p in paths:
            if "site-packages" in p:
                continue
            try:
                rel = Path(p).resolve().relative_to(self.root.resolve())
            except Exception:
                try:
                    rel = Path(p)
                except Exception:
                    continue
            s = rel.as_posix()
            if s not in result:
                result.append(s)
        return result
