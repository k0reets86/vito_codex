"""Anti-captcha solver module for VITO.

Singleton module that solves reCAPTCHA v2/v3, hCaptcha, and image captchas
via the anti-captcha.com API. Logs every solve attempt to SQLite.

Usage:
    solver = CaptchaSolver.get_instance()
    token = solver.solve_recaptcha_v2(site_key, page_url)
"""

import base64
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("vito.captcha_solver")

DB_PATH = Path(__file__).resolve().parent.parent / "memory" / "vito_local.db"
ANTICAPTCHA_KEY = os.getenv("ANTICAPTCHA_KEY", "")


class CaptchaSolver:
    """Singleton captcha solver using anti-captcha.com."""

    _instance: Optional["CaptchaSolver"] = None
    _lock = threading.Lock()

    def __init__(self):
        if not ANTICAPTCHA_KEY:
            raise RuntimeError("ANTICAPTCHA_KEY not set in .env")
        self._api_key = ANTICAPTCHA_KEY
        self._init_db()

    @classmethod
    def get_instance(cls) -> "CaptchaSolver":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _init_db(self):
        """Create captcha_logs table if not exists."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS captcha_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                type TEXT NOT NULL,
                site TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0.0,
                error TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _log(self, captcha_type: str, site: str, success: bool, cost: float = 0.0, error: str = ""):
        """Log solve attempt to DB."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                "INSERT INTO captcha_logs (timestamp, type, site, success, cost, error) VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), captcha_type, site, int(success), cost, error),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log captcha solve: {e}")

    def get_balance(self) -> float:
        """Check anti-captcha account balance."""
        from anticaptchaofficial.antinetworking import antiNetworking

        client = antiNetworking()
        client.client_key = self._api_key
        balance = client.get_balance()
        if balance is None:
            err = client.err_string
            logger.error(f"Balance check failed: {err}")
            return 0.0
        try:
            bal = float(balance)
        except Exception:
            return 0.0
        if bal < 0:
            logger.warning(f"Anti-captcha returned negative balance: {bal}")
            return 0.0
        return bal

    def solve_recaptcha_v2(self, site_key: str, page_url: str, invisible: bool = False) -> Optional[str]:
        """Solve reCAPTCHA v2 and return the g-recaptcha-response token."""
        from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless

        solver = recaptchaV2Proxyless()
        solver.set_verbose(0)
        solver.set_key(self._api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)
        if invisible:
            solver.set_is_invisible(1)

        logger.info(f"Solving reCAPTCHA v2 for {page_url}")
        token = solver.solve_and_return_solution()

        if token:
            cost = solver.task_cost if hasattr(solver, "task_cost") else 0.002
            self._log("recaptcha_v2", page_url, True, cost)
            logger.info(f"reCAPTCHA v2 solved, token={token[:40]}...")
            return token
        else:
            err = solver.err_string
            self._log("recaptcha_v2", page_url, False, 0.0, err)
            logger.error(f"reCAPTCHA v2 failed: {err}")
            return None

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify", min_score: float = 0.7) -> Optional[str]:
        """Solve reCAPTCHA v3 and return the token."""
        from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless

        solver = recaptchaV3Proxyless()
        solver.set_verbose(0)
        solver.set_key(self._api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)
        solver.set_page_action(action)
        solver.set_min_score(min_score)

        logger.info(f"Solving reCAPTCHA v3 for {page_url} action={action}")
        token = solver.solve_and_return_solution()

        if token:
            cost = solver.task_cost if hasattr(solver, "task_cost") else 0.002
            self._log("recaptcha_v3", page_url, True, cost)
            logger.info(f"reCAPTCHA v3 solved, token={token[:40]}...")
            return token
        else:
            err = solver.err_string
            self._log("recaptcha_v3", page_url, False, 0.0, err)
            logger.error(f"reCAPTCHA v3 failed: {err}")
            return None

    def solve_hcaptcha(self, site_key: str, page_url: str) -> Optional[str]:
        """Solve hCaptcha and return the token."""
        from anticaptchaofficial.hcaptchaproxyless import hCaptchaProxyless

        solver = hCaptchaProxyless()
        solver.set_verbose(0)
        solver.set_key(self._api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)

        logger.info(f"Solving hCaptcha for {page_url}")
        token = solver.solve_and_return_solution()

        if token:
            cost = solver.task_cost if hasattr(solver, "task_cost") else 0.002
            self._log("hcaptcha", page_url, True, cost)
            logger.info(f"hCaptcha solved, token={token[:40]}...")
            return token
        else:
            err = solver.err_string
            self._log("hcaptcha", page_url, False, 0.0, err)
            logger.error(f"hCaptcha failed: {err}")
            return None

    def solve_turnstile(self, site_key: str, page_url: str) -> Optional[str]:
        """Solve Cloudflare Turnstile and return the token."""
        from anticaptchaofficial.turnstileproxyless import turnstileProxyless

        solver = turnstileProxyless()
        solver.set_verbose(0)
        solver.set_key(self._api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)

        logger.info(f"Solving Turnstile for {page_url}")
        token = solver.solve_and_return_solution()
        if token:
            cost = solver.task_cost if hasattr(solver, "task_cost") else 0.003
            self._log("turnstile", page_url, True, cost)
            logger.info(f"Turnstile solved, token={token[:40]}...")
            return token
        err = solver.err_string
        self._log("turnstile", page_url, False, 0.0, err)
        logger.error(f"Turnstile failed: {err}")
        return None

    def solve_image_captcha(self, image_path: str) -> Optional[str]:
        """Solve an image captcha and return the text."""
        from anticaptchaofficial.imagecaptcha import imagecaptcha

        solver = imagecaptcha()
        solver.set_verbose(0)
        solver.set_key(self._api_key)

        path = Path(image_path)
        if not path.exists():
            self._log("image", image_path, False, 0.0, "File not found")
            return None

        logger.info(f"Solving image captcha: {path.name}")
        token = solver.solve_and_return_solution(str(path))

        if token:
            cost = solver.task_cost if hasattr(solver, "task_cost") else 0.001
            self._log("image", str(path), True, cost)
            logger.info(f"Image captcha solved: {token}")
            return token
        else:
            err = solver.err_string
            self._log("image", str(path), False, 0.0, err)
            logger.error(f"Image captcha failed: {err}")
            return None

    async def solve_playwright_recaptcha(self, page) -> Optional[str]:
        """Detect and solve reCAPTCHA on a Playwright page.

        Extracts the sitekey from the page, solves via API,
        and injects the token into the page.
        Returns the token or None.
        """
        # Extract sitekey from reCAPTCHA iframe or div
        site_key = await page.evaluate("""() => {
            // Try data-sitekey attribute
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');
            // Try iframe src parameter
            const iframe = document.querySelector('iframe[src*="recaptcha"]');
            if (iframe) {
                const m = iframe.src.match(/[?&]k=([^&]+)/);
                if (m) return m[1];
            }
            return null;
        }""")

        if not site_key:
            logger.warning("No reCAPTCHA sitekey found on page")
            return None

        page_url = page.url
        logger.info(f"Found reCAPTCHA sitekey={site_key[:20]}... on {page_url}")

        # Solve
        token = self.solve_recaptcha_v2(site_key, page_url)
        if not token:
            return None

        # Inject token into page
        await page.evaluate(f"""(token) => {{
            // Set textarea value
            const textarea = document.getElementById('g-recaptcha-response');
            if (textarea) {{
                textarea.value = token;
                textarea.style.display = 'block';
            }}
            // Also try all textareas with that name
            document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {{
                el.value = token;
            }});
            // Trigger callback if exists
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                const clients = ___grecaptcha_cfg.clients;
                if (clients) {{
                    Object.keys(clients).forEach(key => {{
                        const client = clients[key];
                        // Find callback in client tree
                        const findCallback = (obj, depth) => {{
                            if (depth > 5 || !obj) return;
                            Object.keys(obj).forEach(k => {{
                                if (typeof obj[k] === 'function' && k.length < 3) {{
                                    try {{ obj[k](token); }} catch(e) {{}}
                                }} else if (typeof obj[k] === 'object') {{
                                    findCallback(obj[k], depth + 1);
                                }}
                            }});
                        }};
                        findCallback(client, 0);
                    }});
                }}
            }}
        }}""", token)

        logger.info("reCAPTCHA token injected into page")
        return token
