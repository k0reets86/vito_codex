"""DocumentAgent — Agent 19: документация, отчёты, база знаний."""

import csv
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from agents.base_agent import AgentStatus, BaseAgent, TaskResult
from config.logger import get_logger
from llm_router import TaskType
from modules.growth_research_operational import build_document_operational_pack
from modules.research_family_runtime import build_document_runtime_profile

logger = get_logger("document_agent", agent="document_agent")


class DocumentAgent(BaseAgent):
    NEEDS = {
        "documentation": ["research"],
        "knowledge_base": ["documentation"],
        "report": ["analytics"],
        "default": [],
    }

    def __init__(self, **kwargs):
        super().__init__(name="document_agent", description="Документация: создание, отчёты, база знаний", **kwargs)

    @property
    def capabilities(self) -> list[str]:
        return ["documentation", "knowledge_base", "document_parse", "image_ocr", "video_extract"]

    async def execute_task(self, task_type: str, **kwargs) -> TaskResult:
        self._status = AgentStatus.RUNNING
        start = time.monotonic()
        try:
            if task_type == "documentation":
                result = await self.create_doc(kwargs.get("title", kwargs.get("step", "")), kwargs.get("content_type", "technical"), kwargs.get("context", {}))
            elif task_type == "knowledge_base":
                result = await self.update_knowledge_base(kwargs.get("topic", ""), kwargs.get("content", kwargs.get("step", "")))
            elif task_type == "document_parse":
                result = await self.parse_document(kwargs.get("path") or kwargs.get("file_path") or "")
            elif task_type == "image_ocr":
                result = await self.ocr_image(kwargs.get("path") or kwargs.get("file_path") or "")
            elif task_type == "video_extract":
                result = await self.extract_video_text(kwargs.get("path") or kwargs.get("file_path") or "")
            elif task_type == "report":
                result = await self.generate_report(kwargs.get("report_type", "general"), kwargs.get("data", {}))
            else:
                result = await self.create_doc(kwargs.get("step", task_type), "general", {})
            result.duration_ms = int((time.monotonic() - start) * 1000)
            self._track_result(result)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            self._status = AgentStatus.IDLE

    async def parse_document(self, path: str) -> TaskResult:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            runtime_profile = build_document_runtime_profile(str(file_path), "document_parse")
            op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=False, extracted_kind="missing_source")
            return TaskResult(
                success=True,
                output={"status": "source_missing", "path": str(file_path), "next_actions": runtime_profile["next_actions"]},
                metadata={"document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()},
            )
        suffix = file_path.suffix.lower()
        try:
            if suffix in {".txt", ".md", ".log"}:
                op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=True, extracted_kind="text")
                return TaskResult(success=True, output={"text": file_path.read_text(errors="ignore"), "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "document_parse"), "operational_pack": op_pack, **self.get_skill_pack()})
            if suffix == ".json":
                data = json.loads(file_path.read_text(errors="ignore"))
                op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=True, extracted_kind="json")
                return TaskResult(success=True, output={"json": data, "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "document_parse"), "operational_pack": op_pack, **self.get_skill_pack()})
            if suffix == ".csv":
                with file_path.open(newline="", encoding="utf-8", errors="ignore") as f:
                    reader = csv.reader(f)
                    rows = [row for row in reader][:1000]
                op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=True, extracted_kind="csv_rows")
                return TaskResult(success=True, output={"rows": rows, "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "document_parse"), "operational_pack": op_pack, **self.get_skill_pack()})
            if suffix == ".docx":
                try:
                    import docx  # python-docx
                except Exception:
                    return TaskResult(success=False, error="python-docx не установлен")
                doc = docx.Document(str(file_path))
                text = "\n".join(p.text for p in doc.paragraphs)
                op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=True, extracted_kind="docx_text")
                return TaskResult(success=True, output={"text": text, "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "document_parse"), "operational_pack": op_pack, **self.get_skill_pack()})
            if suffix == ".pdf":
                try:
                    from pypdf import PdfReader
                except Exception:
                    return TaskResult(success=False, error="pypdf не установлен")
                reader = PdfReader(str(file_path))
                pages = []
                for page in reader.pages[:50]:
                    pages.append(page.extract_text() or "")
                op_pack = build_document_operational_pack(path=str(file_path), capability="document_parse", source_exists=True, extracted_kind="pdf_text")
                return TaskResult(success=True, output={"text": "\n".join(pages), "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "document_parse"), "operational_pack": op_pack, **self.get_skill_pack()})
            if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
                return await self.ocr_image(str(file_path))
            if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                return await self.extract_video_text(str(file_path))
            return TaskResult(success=False, error=f"Неподдерживаемый формат: {suffix}")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def ocr_image(self, path: str) -> TaskResult:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            runtime_profile = build_document_runtime_profile(str(file_path), "image_ocr")
            op_pack = build_document_operational_pack(path=str(file_path), capability="image_ocr", source_exists=False, extracted_kind="missing_source")
            return TaskResult(
                success=True,
                output={"status": "source_missing", "path": str(file_path), "next_actions": runtime_profile["next_actions"]},
                metadata={"document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()},
            )
        try:
            from PIL import Image
        except Exception:
            return TaskResult(success=False, error="PIL не установлен")
        try:
            img = Image.open(str(file_path))
            # Prefer pytesseract if available; fallback to tesserocr
            try:
                import pytesseract

                text = pytesseract.image_to_string(img)
                op_pack = build_document_operational_pack(path=str(file_path), capability="image_ocr", source_exists=True, extracted_kind="ocr_text")
                return TaskResult(success=True, output={"text": text, "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "image_ocr"), "operational_pack": op_pack, **self.get_skill_pack()})
            except Exception:
                try:
                    from tesserocr import PyTessBaseAPI

                    with PyTessBaseAPI() as api:
                        api.SetImage(img)
                        text = api.GetUTF8Text()
                    op_pack = build_document_operational_pack(path=str(file_path), capability="image_ocr", source_exists=True, extracted_kind="ocr_text")
                    return TaskResult(success=True, output={"text": text, "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "image_ocr"), "operational_pack": op_pack, **self.get_skill_pack()})
                except Exception:
                    return TaskResult(success=False, error="OCR недоступен (нет pytesseract или tesserocr)")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def extract_video_text(self, path: str) -> TaskResult:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            runtime_profile = build_document_runtime_profile(str(file_path), "video_extract")
            op_pack = build_document_operational_pack(path=str(file_path), capability="video_extract", source_exists=False, extracted_kind="missing_source")
            return TaskResult(
                success=True,
                output={"status": "source_missing", "path": str(file_path), "next_actions": runtime_profile["next_actions"]},
                metadata={"document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()},
            )
        if not shutil.which("ffmpeg"):
            return TaskResult(success=False, error="ffmpeg не установлен")
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="vito_frames_"))
            # Extract 1 frame every 5 seconds, max ~20 frames
            cmd = [
                "ffmpeg",
                "-i",
                str(file_path),
                "-vf",
                "fps=1/5",
                str(tmp_dir / "frame_%03d.jpg"),
                "-hide_banner",
                "-loglevel",
                "error",
            ]
            subprocess.run(cmd, check=True)
            frames = sorted(tmp_dir.glob("frame_*.jpg"))[:20]
            if not frames:
                return TaskResult(success=False, error="Не удалось извлечь кадры")
            texts = []
            for frame in frames:
                res = await self.ocr_image(str(frame))
                if res.success and res.output:
                    txt = res.output.get("text", "")
                    if txt.strip():
                        texts.append(txt.strip())
            op_pack = build_document_operational_pack(path=str(file_path), capability="video_extract", source_exists=True, extracted_kind="video_ocr_text")
            return TaskResult(success=True, output={"text": "\n".join(texts), "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(str(file_path), "video_extract"), "operational_pack": op_pack, **self.get_skill_pack()})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
        finally:
            try:
                if "tmp_dir" in locals():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    async def create_doc(self, title: str, content_type: str = "technical", context: dict = None) -> TaskResult:
        runtime_profile = build_document_runtime_profile(str(title or "document"), "documentation")
        op_pack = build_document_operational_pack(path=str(title or "document"), capability="documentation", source_exists=True, extracted_kind="generated_document")
        if not self.llm_router:
            local = self._local_doc(title, content_type, context)
            local["used_skills"] = op_pack["used_skills"]
            local["evidence"] = op_pack["evidence"]
            local["next_actions"] = op_pack["next_actions"]
            local["recovery_hints"] = op_pack["recovery_hints"]
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()})
        context_text = ""
        if context:
            context_text = "\nКонтекст:\n" + "\n".join(f"- {k}: {v}" for k, v in context.items())
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Создай документ.\nНазвание: {title}\nТип: {content_type}{context_text}\nФормат: Markdown с заголовками, списками, примерами кода если нужно.",
            estimated_tokens=3000,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Doc: {title[:50]}")
        return TaskResult(success=True, output=response, cost_usd=0.02, metadata={"document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()})

    async def generate_report(self, report_type: str = "general", data: dict = None) -> TaskResult:
        runtime_profile = build_document_runtime_profile(str(report_type or "report"), "report")
        op_pack = build_document_operational_pack(path=str(report_type or "report"), capability="report", source_exists=True, extracted_kind="generated_report")
        if not self.llm_router:
            local = self._local_report(report_type, data)
            local["used_skills"] = op_pack["used_skills"]
            local["evidence"] = op_pack["evidence"]
            local["next_actions"] = op_pack["next_actions"]
            local["recovery_hints"] = op_pack["recovery_hints"]
            return TaskResult(success=True, output=local, metadata={"mode": "local_fallback", "document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()})
        data_text = ""
        if data:
            data_text = "\nДанные:\n" + "\n".join(f"- {k}: {v}" for k, v in data.items())
        response = await self._call_llm(
            task_type=TaskType.CONTENT,
            prompt=f"Сгенерируй отчёт типа: {report_type}{data_text}\nВключи: резюме, ключевые метрики, выводы, рекомендации.",
            estimated_tokens=2500,
        )
        if not response:
            return TaskResult(success=False, error="LLM не вернул ответ")
        self._record_expense(0.02, f"Report: {report_type}")
        return TaskResult(success=True, output=response, cost_usd=0.02, metadata={"document_runtime_profile": runtime_profile, "operational_pack": op_pack, **self.get_skill_pack()})

    async def update_knowledge_base(self, topic: str, content: str) -> TaskResult:
        if not self.memory:
            return TaskResult(success=False, error="Memory Manager недоступен")
        self.memory.store_knowledge(
            doc_id=f"kb_{hash(topic) % 100000}",
            text=f"{topic}: {content}",
            metadata={"type": "knowledge_base", "topic": topic},
        )
        logger.info(f"База знаний обновлена: {topic}", extra={"event": "kb_updated"})
        op_pack = build_document_operational_pack(path=topic, capability="knowledge_base", source_exists=True, extracted_kind="knowledge_entry")
        return TaskResult(success=True, output={"topic": topic, "status": "stored", "used_skills": op_pack["used_skills"], "evidence": op_pack["evidence"], "next_actions": op_pack["next_actions"], "recovery_hints": op_pack["recovery_hints"]}, metadata={"document_runtime_profile": build_document_runtime_profile(topic, "knowledge_base"), "operational_pack": op_pack, **self.get_skill_pack()})

    def _local_doc(self, title: str, content_type: str, context: dict | None) -> dict[str, Any]:
        return {
            "title": (title or "Untitled document").strip(),
            "content_type": content_type,
            "sections": ["Summary", "Context", "Actions", "Risks", "Next steps"],
            "context_keys": sorted(list((context or {}).keys())),
            "review_checklist": [
                "title_present",
                "sections_present",
                "context_keys_extracted",
            ],
            "handoff_targets": ["quality_judge", "research_agent", "security_agent"],
            "manifest": {"sections": 5, "attachments": []},
        }

    def _local_report(self, report_type: str, data: dict | None) -> dict[str, Any]:
        payload = dict(data or {})
        return {
            "report_type": report_type,
            "summary": f"Structured {report_type} report generated from {len(payload)} input fields.",
            "metrics": payload,
            "recommendations": ["Review highest-risk items first", "Convert this report into runbook updates if stable"],
            "review_checklist": [
                "summary_present",
                "metrics_present",
                "recommendations_present",
            ],
            "handoff_targets": ["analytics_agent", "quality_judge", "hr_agent"],
            "manifest": {"metric_count": len(payload), "attachments": []},
        }
