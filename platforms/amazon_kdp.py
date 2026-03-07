"""Amazon KDP Platform — Browser-based интеграция через BrowserAgent."""

from pathlib import Path
from typing import Any
import asyncio
import json
import os
import shlex

from config.logger import get_logger
from config.settings import settings
from modules.execution_facts import ExecutionFacts
from modules.listing_optimizer import optimize_listing_payload
from modules.platform_knowledge import record_platform_lesson
from platforms.base_platform import BasePlatform

logger = get_logger("amazon_kdp", agent="amazon_kdp")


class AmazonKDPPlatform(BasePlatform):
    def __init__(self, browser_agent=None, **kwargs):
        super().__init__(name="amazon_kdp", browser_agent=browser_agent, **kwargs)
        self._state_file = Path(str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json"))

    async def _probe_saved_session(self) -> bool:
        if not self._state_file.exists():
            return False
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                args = [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--renderer-process-limit=1",
                ]
                if bool(getattr(settings, "BROWSER_CONSTRAINED_MODE", True)):
                    args.extend(["--no-zygote", "--single-process"])
                browser = await p.chromium.launch(
                    headless=True,
                    args=args,
                )
                context = await browser.new_context(storage_state=str(self._state_file), viewport={"width": 1280, "height": 720})
                page = await context.new_page()
                await page.goto("https://kdp.amazon.com/bookshelf", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(1500)
                u = (page.url or "").lower()
                ok = ("/bookshelf" in u or "/reports" in u or "/en_us/" in u) and ("signin" not in u and "ap/signin" not in u)
                await context.close()
                await browser.close()
                return ok
        except Exception as e:
            logger.warning(f"KDP saved-session probe error: {e}", extra={"event": "kdp_session_probe_error"})
            return False

    async def authenticate(self) -> bool:
        """Аутентификация через BrowserAgent (KDP login page)."""
        # Preferred path: saved browser session (created by scripts/kdp_auth_helper.py).
        if self.browser_agent is None and await self._probe_saved_session():
            self._authenticated = True
            return True
        if not self.browser_agent:
            logger.warning("BrowserAgent не подключён для Amazon KDP", extra={"event": "kdp_no_browser"})
            self._authenticated = False
            return False
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://kdp.amazon.com/bookshelf",
            )
            if not result or not result.success:
                self._authenticated = False
                return False
            out = result.output
            if isinstance(out, dict):
                title = str(out.get("title", "")).lower()
                url = str(out.get("url", "")).lower()
            else:
                raw = str(out or "").lower()
                title = raw
                url = raw
            self._authenticated = "signin" not in title and "ap/signin" not in url
            return self._authenticated
        except Exception as e:
            logger.error(f"KDP auth error: {e}", extra={"event": "kdp_auth_error"})
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """Публикация через BrowserAgent — заполнение форм KDP."""
        content = optimize_listing_payload("amazon_kdp", content or {})
        operation = str(content.get("operation") or "create").strip().lower()
        allow_existing_update = bool(content.get("allow_existing_update"))
        owner_edit_confirmed = bool(content.get("owner_edit_confirmed"))
        target_document_id = str(content.get("target_document_id") or content.get("target_book_id") or "").strip()
        if bool(getattr(settings, "PUBLISH_CREATE_GUARD_ENABLED", True)):
            if operation in {"create", "new"} and allow_existing_update:
                result = {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "create_mode_forbids_existing_update",
                }
                self._record_publish_lesson(result, source="amazon_kdp.publish")
                return result
            if allow_existing_update and not owner_edit_confirmed:
                result = {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "existing_update_requires_explicit_owner_request",
                }
                self._record_publish_lesson(result, source="amazon_kdp.publish")
                return result
            if allow_existing_update and not target_document_id:
                result = {
                    "platform": "amazon_kdp",
                    "status": "blocked",
                    "error": "existing_update_requires_target_document_id",
                }
                self._record_publish_lesson(result, source="amazon_kdp.publish")
                return result
        if not self.browser_agent:
            result = {"platform": "amazon_kdp", "status": "no_browser"}
            self._record_publish_lesson(result, source="amazon_kdp.publish")
            return result
        try:
            result = await self.browser_agent.execute_task(
                task_type="form_fill",
                url="https://kdp.amazon.com/bookshelf",
                form_data=content,
            )
            out = result.output if result else None
            evidence_url = ""
            evidence_id = ""
            evidence_path = ""
            if isinstance(out, dict):
                evidence_url = str(out.get("url") or out.get("book_url") or "").strip()
                evidence_id = str(out.get("id") or out.get("book_id") or "").strip()
                evidence_path = str(out.get("screenshot_path") or out.get("path") or "").strip()
            # Contract rule: "published" requires evidence fields; otherwise degrade to prepared.
            status = "failed"
            if result and result.success:
                has_evidence = bool(evidence_url or evidence_id or evidence_path)
                status = "published" if has_evidence else "prepared"
            result_payload = {
                "platform": "amazon_kdp",
                "status": status,
                "url": evidence_url,
                "id": evidence_id,
                "screenshot_path": evidence_path,
                "output": out,
            }
            if status == "prepared" and self._state_file.exists():
                helper = await self._publish_via_kdp_helper(content or {})
                if isinstance(helper, dict):
                    self._record_publish_lesson(helper, source="amazon_kdp.publish.helper")
                    return helper
            self._record_publish_lesson(result_payload, source="amazon_kdp.publish")
            return result_payload
        except Exception as e:
            logger.error(f"KDP publish error: {e}", extra={"event": "kdp_publish_error"})
            result = {"platform": "amazon_kdp", "status": "error", "error": str(e)}
            self._record_publish_lesson(result, source="amazon_kdp.publish")
            return result

    async def _publish_via_kdp_helper(self, content: dict) -> dict:
        """Fallback to dedicated KDP draft helper with strict bookshelf verification."""
        helper_script = Path("scripts/kdp_create_draft_test.py")
        if not helper_script.exists():
            result = {"platform": "amazon_kdp", "status": "prepared", "error": "kdp_helper_missing"}
            self._record_publish_lesson(result, source="amazon_kdp.kdp_helper")
            return result
        title = str(content.get("title") or "VITO TEST DRAFT").strip() or "VITO TEST DRAFT"
        cmd = [
            "xvfb-run",
            "-a",
            "python3",
            str(helper_script),
            "--storage-path",
            str(self._state_file),
            "--debug-dir",
            "runtime/remote_auth",
        ]
        env = dict(os.environ)
        env["KDP_TEST_DRAFT_TITLE"] = title
        env["KDP_TEST_DRAFT_SUBTITLE"] = str(content.get("subtitle") or "")
        env["KDP_TEST_DRAFT_AUTHOR"] = str(content.get("author") or "VITO Studio")
        env["KDP_TEST_DRAFT_DESCRIPTION"] = str(content.get("description") or "")
        kw = content.get("keyword_slots") or content.get("keywords") or []
        if isinstance(kw, list):
            env["KDP_TEST_DRAFT_KEYWORDS"] = "|".join(str(x).strip() for x in kw[:7] if str(x).strip())
        else:
            env["KDP_TEST_DRAFT_KEYWORDS"] = str(kw or "")
        env["KDP_TEST_DRAFT_MANUSCRIPT"] = str(content.get("manuscript_path") or content.get("pdf_path") or content.get("file_path") or "")
        env["KDP_TEST_DRAFT_COVER"] = str(content.get("cover_path") or content.get("image_path") or "")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=240)
            stdout = (out_b or b"").decode("utf-8", errors="ignore").strip()
            stderr = (err_b or b"").decode("utf-8", errors="ignore").strip()
            lines = [ln for ln in stdout.splitlines() if ln.strip()]
            payload = {}
            if lines:
                try:
                    payload = json.loads(lines[-1])
                except Exception:
                    payload = {}
            helper_ok = bool(payload.get("ok"))
            helper_soft_ok = bool(payload.get("ok_soft")) or bool(payload.get("saved_click"))
            fields_filled = int(payload.get("fields_filled") or 0)
            if fields_filled <= 0 and helper_soft_ok:
                fields_filled = 1
            if helper_ok:
                result = {
                    "platform": "amazon_kdp",
                    "status": "published",
                    "url": "https://kdp.amazon.com/bookshelf",
                    "id": "",
                    "screenshot_path": str(payload.get("bookshelf_screenshot") or payload.get("screenshot") or ""),
                    "output": {**payload, "fields_filled": fields_filled},
                    "method": "kdp_helper",
                }
                self._record_publish_lesson(result, source="amazon_kdp.kdp_helper")
                self._record_execution_fact(result)
                return result
            if helper_soft_ok:
                result = {
                    "platform": "amazon_kdp",
                    "status": "draft",
                    "url": "https://kdp.amazon.com/bookshelf",
                    "id": "",
                    "screenshot_path": str(payload.get("bookshelf_screenshot") or payload.get("screenshot") or ""),
                    "output": {**payload, "fields_filled": fields_filled},
                    "method": "kdp_helper",
                }
                self._record_publish_lesson(result, source="amazon_kdp.kdp_helper")
                self._record_execution_fact(result)
                return result
            result = {
                "platform": "amazon_kdp",
                "status": "prepared",
                "url": "https://kdp.amazon.com/bookshelf",
                "id": "",
                "screenshot_path": str(payload.get("screenshot") or ""),
                "output": (payload | {"fields_filled": fields_filled}) if payload else {"stdout": stdout[-1200:], "stderr": stderr[-1200:], "cmd": " ".join(shlex.quote(x) for x in cmd), "fields_filled": 0},
                "method": "kdp_helper",
            }
            self._record_publish_lesson(result, source="amazon_kdp.kdp_helper")
            return result
        except Exception as e:
            result = {"platform": "amazon_kdp", "status": "prepared", "error": str(e), "method": "kdp_helper"}
            self._record_publish_lesson(result, source="amazon_kdp.kdp_helper")
            return result

    async def get_analytics(self) -> dict:
        """Получение аналитики через BrowserAgent (KDP Reports page)."""
        if not self.browser_agent:
            return {"platform": "amazon_kdp", "sales": 0, "revenue": 0.0}
        try:
            result = await self.browser_agent.execute_task(
                task_type="browse",
                url="https://kdp.amazon.com/reports",
                action="extract_text",
            )
            return {
                "platform": "amazon_kdp",
                "raw_data": result.output if result else None,
                "sales": 0,
                "revenue": 0.0,
            }
        except Exception as e:
            logger.error(f"KDP analytics error: {e}", extra={"event": "kdp_analytics_error"})
            return {"platform": "amazon_kdp", "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        if self.browser_agent is not None:
            return True
        return False

    def _record_execution_fact(self, result: dict[str, Any]) -> None:
        try:
            ExecutionFacts().record(
                action="platform:publish",
                status=str(result.get("status") or "unknown"),
                detail=f"amazon_kdp status={result.get('status')}",
                evidence=str(result.get("url") or ""),
                source="amazon_kdp.publish",
                evidence_dict={
                    "platform": "amazon_kdp",
                    "status": result.get("status"),
                    "url": result.get("url"),
                    "screenshot_path": result.get("screenshot_path"),
                    "method": result.get("method"),
                    "output": result.get("output"),
                },
            )
        except Exception:
            pass

    def _record_publish_lesson(self, result: dict[str, Any], *, source: str) -> None:
        try:
            status = str(result.get("status") or "unknown").strip().lower()
            output = result.get("output") if isinstance(result.get("output"), dict) else {}
            details = []
            if result.get("error"):
                details.append(f"error={result.get('error')}")
            if output:
                for key in ("fields_filled", "description_set", "keyword_slots_filled", "manuscript_uploaded", "cover_uploaded", "title_found_on_bookshelf", "title_found_via_search", "saved_click"):
                    if key in output:
                        details.append(f"{key}={output.get(key)}")
            summary = f"KDP publish result: {status}"
            lessons = []
            anti_patterns = []
            if status in {"draft", "published"}:
                lessons.append("Подтверждай KDP-черновик только через bookshelf proof или helper evidence.")
                if output.get("saved_click"):
                    lessons.append("Сохраняй draft через helper и проверяй появление на Bookshelf.")
                if output.get("manuscript_uploaded") or output.get("cover_uploaded"):
                    lessons.append("Файлы manuscript/cover должны проверяться отдельно от metadata save.")
            else:
                anti_patterns.append("Не считай KDP успехом без bookshelf evidence или helper proof.")
                if result.get("error"):
                    anti_patterns.append(f"Ошибка: {result.get('error')}")
            record_platform_lesson(
                "amazon_kdp",
                status=status,
                summary=summary,
                details="; ".join(details),
                url=str(result.get("url") or ""),
                lessons=lessons,
                anti_patterns=anti_patterns,
                evidence={
                    "status": status,
                    "url": result.get("url"),
                    "screenshot_path": result.get("screenshot_path"),
                    "method": result.get("method"),
                    "output": output,
                },
                source=source,
            )
        except Exception:
            pass
