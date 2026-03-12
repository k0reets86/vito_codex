from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from modules.owner_model import OwnerPreferenceModel


def apply_llm_mode(agent, mode: str) -> tuple[bool, str]:
    m = str(mode or "").strip().lower()
    if m in {"free", "test", "gemini", "flash"}:
        agent._set_env_values(
            {
                "LLM_ROUTER_MODE": "free",
                "LLM_FORCE_GEMINI_FREE": "true",
                "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                "LLM_ENABLED_MODELS": "gemini-2.5-flash",
                "LLM_DISABLED_MODELS": "claude-haiku-4-5-20251001,gpt-4o-mini,claude-sonnet-4-6,o3,gpt-4o-strategic,claude-opus-4-6,sonar-pro",
                "GEMINI_ENABLE_GROUNDING_SEARCH": "true",
                "GEMINI_ENABLE_URL_CONTEXT": "true",
                "GEMINI_EMBEDDINGS_ENABLED": "true",
                "GEMINI_EMBED_MODEL": "gemini-embedding-001",
                "GEMINI_ENABLE_IMAGEN": "true",
                "GEMINI_LIVE_API_ENABLED": "true",
                "IMAGE_ROUTER_PREFER_GEMINI": "true",
                "GEMINI_FREE_MAX_RPM": "15",
                "GEMINI_FREE_TEXT_RPD": "1000",
                "GEMINI_FREE_SEARCH_RPD": "1500",
                "MODEL_ACTIVE_PROFILE": "gemini_free",
            }
        )
        return True, (
            "LLM режим: FREE (тест)\n"
            "- Все задачи идут через Gemini 2.5 Flash\n"
            "- Платные модели отключены\n"
            "- Grounding Search + URL Context включены\n"
            "- Embeddings + Imagen + Live API включены (если есть доступ)\n"
            "- Перезапуск не обязателен, но желателен для чистого цикла"
        )
    if m in {"prod", "production", "battle", "боевой"}:
        agent._set_env_values(
            {
                "LLM_ROUTER_MODE": "prod",
                "LLM_FORCE_GEMINI_FREE": "false",
                "LLM_FORCE_GEMINI_MODEL": "gemini-2.5-flash",
                "LLM_ENABLED_MODELS": "",
                "LLM_DISABLED_MODELS": "",
                "IMAGE_ROUTER_PREFER_GEMINI": "false",
                "MODEL_ACTIVE_PROFILE": "balanced",
            }
        )
        return True, (
            "LLM режим: PROD (боевой)\n"
            "- ROUTINE: Gemini -> 4o-mini -> Haiku\n"
            "- CONTENT: Sonnet -> Haiku -> Gemini\n"
            "- CODE/SELF_HEAL: o3 -> Sonnet -> GPT-5\n"
            "- RESEARCH: Perplexity -> Gemini -> Sonnet\n"
            "- STRATEGY: Opus -> GPT-5 -> Sonnet"
        )
    if m in {"status", "show", "current", "текущий"}:
        free = bool(getattr(settings, "LLM_FORCE_GEMINI_FREE", False))
        enabled = str(getattr(settings, "LLM_ENABLED_MODELS", "") or "")
        disabled = str(getattr(settings, "LLM_DISABLED_MODELS", "") or "")
        model = str(getattr(settings, "LLM_FORCE_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash")
        router_mode = str(getattr(settings, "LLM_ROUTER_MODE", "prod") or "prod")
        embed = bool(getattr(settings, "GEMINI_EMBEDDINGS_ENABLED", False))
        img = bool(getattr(settings, "GEMINI_ENABLE_IMAGEN", False))
        live = bool(getattr(settings, "GEMINI_LIVE_API_ENABLED", False))
        mode_name = "FREE (Gemini-only)" if free else "PROD (task-based)"
        return True, (
            f"LLM режим сейчас: {mode_name}\n"
            f"LLM_ROUTER_MODE={router_mode}\n"
            f"LLM_FORCE_GEMINI_MODEL={model}\n"
            f"GEMINI_EMBEDDINGS_ENABLED={str(embed).lower()} | GEMINI_ENABLE_IMAGEN={str(img).lower()} | GEMINI_LIVE_API_ENABLED={str(live).lower()}\n"
            f"LLM_ENABLED_MODELS={enabled or '(empty)'}\n"
            f"LLM_DISABLED_MODELS={disabled or '(empty)'}"
        )
    return False, "Использование: /llm_mode free | /llm_mode prod | /llm_mode status"


async def run_kdp_variants(variants: list[list[str]], timeout_sec: int) -> tuple[int, str]:
    last_code = 1
    last_out = ""
    for cmd in variants:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            output = (out_b or b"").decode("utf-8", errors="ignore")
            code = int(proc.returncode or 0)
            last_code, last_out = code, output
            if code == 0:
                return code, output
        except Exception as exc:  # pragma: no cover
            last_code, last_out = 1, str(exc)
    return last_code, last_out


async def run_kdp_auto_login(otp_code: str = "") -> tuple[int, str]:
    storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
    base = [
        "python3",
        "scripts/kdp_auth_helper.py",
        "auto-login",
        "--timeout-sec",
        "180",
        "--storage-path",
        storage,
    ]
    if otp_code:
        base.extend(["--otp-code", otp_code])
    variants = [base, ["xvfb-run", "-a", *base]]
    return await run_kdp_variants(variants, timeout_sec=220)


async def run_kdp_prepare_otp() -> tuple[int, str]:
    base = [
        "python3",
        "scripts/kdp_auth_helper.py",
        "prepare-otp",
        "--timeout-sec",
        "120",
        "--preauth-state-path",
        "runtime/kdp_preauth_state.json",
        "--preauth-meta-path",
        "runtime/kdp_preauth_meta.json",
    ]
    variants = [base, ["xvfb-run", "-a", *base]]
    return await run_kdp_variants(variants, timeout_sec=180)


async def run_kdp_submit_otp(otp_code: str) -> tuple[int, str]:
    storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
    base = [
        "python3",
        "scripts/kdp_auth_helper.py",
        "submit-otp",
        "--timeout-sec",
        "120",
        "--preauth-state-path",
        "runtime/kdp_preauth_state.json",
        "--preauth-meta-path",
        "runtime/kdp_preauth_meta.json",
        "--storage-path",
        storage,
        "--otp-code",
        str(otp_code or "").strip(),
    ]
    variants = [base, ["xvfb-run", "-a", *base]]
    return await run_kdp_variants(variants, timeout_sec=180)


async def run_etsy_auto_login() -> tuple[int, str]:
    cmd = [
        "python3",
        "scripts/etsy_auth_helper.py",
        "oauth-auto",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=220)
    output = (out_b or b"").decode("utf-8", errors="ignore")
    return int(proc.returncode or 0), output


def log_owner_request(project_root: Path, text: str, source: str = "text") -> None:
    try:
        ts = datetime.now(timezone.utc).isoformat()
        log_path = project_root / "runtime" / "owner_requirements_log.md"
        entry = f"- [{ts}] ({source}) {text.strip()}\n"
        if not log_path.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("# Owner Requests & Requirements Log\n\n", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def auto_detect_preference(text: str) -> None:
    raw = (text or "").strip()
    lower = raw.lower()
    if "пиши кратко" in lower or lower == "кратко":
        OwnerPreferenceModel().record_signal(
            key="style.verbosity",
            value="concise",
            signal_type="observation",
            source="owner",
            confidence_delta=0.1,
            notes="auto_detect",
        )
    if "пиши подробно" in lower or "подробно" == lower:
        OwnerPreferenceModel().record_signal(
            key="style.verbosity",
            value="verbose",
            signal_type="observation",
            source="owner",
            confidence_delta=0.1,
            notes="auto_detect",
        )
    if "на английском" in lower or "по-английски" in lower or "english only" in lower:
        OwnerPreferenceModel().record_signal(
            key="content.language",
            value="en",
            signal_type="observation",
            source="owner",
            confidence_delta=0.08,
            notes="auto_detect",
        )
    if "на русском" in lower or "по-русски" in lower:
        OwnerPreferenceModel().record_signal(
            key="content.language",
            value="ru",
            signal_type="observation",
            source="owner",
            confidence_delta=0.08,
            notes="auto_detect",
        )
    if "сначала тесты" in lower or "после тестов" in lower:
        OwnerPreferenceModel().record_signal(
            key="workflow.tests_first",
            value=True,
            signal_type="observation",
            source="owner",
            confidence_delta=0.08,
            notes="auto_detect",
        )


def load_auth_state(agent) -> None:
    path = agent._auth_state_path
    try:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        confirmed = payload.get("service_auth_confirmed", {})
        if isinstance(confirmed, dict):
            agent._service_auth_confirmed = {
                str(k).strip().lower(): str(v)
                for k, v in confirmed.items()
                if str(k).strip()
            }
        agent._last_service_context = str(payload.get("last_service_context", "") or "").strip().lower()
        agent._last_service_context_at = str(payload.get("last_service_context_at", "") or "").strip()
    except Exception:
        pass


def save_auth_state(agent) -> None:
    path = agent._auth_state_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "service_auth_confirmed": agent._service_auth_confirmed,
            "last_service_context": agent._last_service_context,
            "last_service_context_at": agent._last_service_context_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_auth_done_text(text: str) -> bool:
    s = str(text or "").strip().lower()
    if not s:
        return False
    return any(
        token in s
        for token in ("я вошел", "я вошёл", "вошел", "вошёл", "готово", "ok", "ок", "done", "авторизовался", "авторизовалась")
    )


def is_auth_issue_prompt(text: str) -> bool:
    s = str(text or "").strip().lower()
    if not s:
        return False
    return any(
        token in s
        for token in (
            "почему не заходит",
            "не заходит",
            "не входит",
            "не могу войти",
            "не получается войти",
            "why can",
            "why not login",
            "login issue",
        )
    )


def parse_remote_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in str(text or "").splitlines():
        s = line.strip()
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def kdp_prepare_has_mfa_evidence(output: str) -> bool:
    low = str(output or "").lower()
    return ("otp_ready" in low) or ("/ap/mfa" in low) or ("mfa.arb" in low)


def kdp_preauth_ready(project_root: Path) -> bool:
    st = project_root / "runtime" / "kdp_preauth_state.json"
    meta = project_root / "runtime" / "kdp_preauth_meta.json"
    if not st.exists():
        return False
    if not meta.exists():
        return True
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        url = str(data.get("url") or "").lower()
        return ("/ap/mfa" in url) or ("mfa.arb" in url) or bool(data.get("prepared", False))
    except Exception:
        return True


def reset_kdp_auth_state_files(project_root: Path) -> None:
    paths = [
        project_root / "runtime" / "kdp_preauth_state.json",
        project_root / "runtime" / "kdp_preauth_meta.json",
        project_root / "runtime" / "kdp_storage_state.json",
    ]
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


async def run_kdp_probe() -> tuple[int, str]:
    storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
    base = [
        "python3",
        "scripts/kdp_auth_helper.py",
        "probe",
        "--storage-path",
        storage,
        "--headless",
    ]
    variants = [base, ["xvfb-run", "-a", *base]]
    return await run_kdp_variants(variants, timeout_sec=120)


async def run_kdp_probe_stable() -> tuple[int, str]:
    rc, out = await run_kdp_probe()
    if rc == 0:
        return rc, out
    await asyncio.sleep(0.8)
    return await run_kdp_probe()


async def run_kdp_inventory_probe() -> tuple[int, str]:
    storage = str(getattr(settings, "KDP_STORAGE_STATE_FILE", "runtime/kdp_storage_state.json") or "runtime/kdp_storage_state.json")
    base = [
        "python3",
        "scripts/kdp_auth_helper.py",
        "inventory",
        "--storage-path",
        storage,
        "--headless",
    ]
    variants = [base, ["xvfb-run", "-a", *base]]
    return await run_kdp_variants(variants, timeout_sec=150)


async def run_etsy_remote_session(action: str = "status") -> tuple[int, str]:
    cmd = ["bash", "scripts/etsy_remote_session.sh", str(action or "status")]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    output = (out_b or b"").decode("utf-8", errors="ignore")
    return int(proc.returncode or 0), output


async def run_remote_auth_session(service: str, action: str = "status") -> tuple[int, str]:
    cmd = [
        "bash",
        "scripts/remote_auth_session.sh",
        str(service or "").strip().lower(),
        str(action or "status"),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    output = (out_b or b"").decode("utf-8", errors="ignore")
    return int(proc.returncode or 0), output


def manual_capture_hint(service: str) -> str:
    svc = str(service or "").strip().lower()
    if svc == "etsy":
        return (
            "Требуется обновление серверной сессии Etsy: "
            "`python3 scripts/etsy_auth_helper.py browser-capture --storage-path runtime/etsy_storage_state.json`"
        )
    return "Нужен ручной вход в серверной browser-сессии и сохранение storage_state."


def service_needs_session_refresh_text(service: str, title: str, detail: str) -> str:
    base = f"{title}: нужно обновить серверную сессию."
    d = str(detail or "").strip()
    if d:
        return f"{base}\nДеталь: {d}"
    return base
