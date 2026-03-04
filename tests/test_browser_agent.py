"""Тесты BrowserAgent — OOM protection + core functionality."""

import os
import platform
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agents.base_agent import TaskResult


class TestBrowserAgent:
    @pytest.fixture
    def agent(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        from agents.browser_agent import BrowserAgent
        # Reset singleton for test isolation
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        BrowserAgent._lock = None
        return BrowserAgent(
            llm_router=mock_llm_router,
            memory=mock_memory,
            finance=mock_finance,
            comms=mock_comms,
        )

    def test_init(self, agent):
        assert agent.name == "browser_agent"
        assert "browse" in agent.capabilities
        assert "web_scrape" in agent.capabilities
        assert "form_fill" in agent.capabilities

    @pytest.mark.asyncio
    async def test_start_stop(self, agent):
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_factory = MagicMock()
        mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)

        with patch("playwright.async_api.async_playwright", mock_pw_factory), \
             patch("agents.browser_agent._kill_orphan_headless_shells", return_value=0), \
             patch("agents.browser_agent._set_memory_limit"):
            await agent.start()
        status = agent.get_status()
        assert status["status"] == "idle"

        with patch("agents.browser_agent._kill_orphan_headless_shells", return_value=0):
            await agent.stop()
        assert agent.get_status()["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_navigate(self, agent):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=MagicMock(status=200))
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.url = "https://example.com"
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context
        with patch.object(agent, '_ensure_browser', new_callable=AsyncMock):
            result = await agent.navigate("https://example.com")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_extract_text(self, agent):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="Page content here")
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context
        with patch.object(agent, '_ensure_browser', new_callable=AsyncMock):
            result = await agent.extract_text("https://example.com")
            assert result.success is True
            assert "Page content" in result.output

    @pytest.mark.asyncio
    async def test_execute_task_browse(self, agent):
        with patch.object(agent, 'navigate', new_callable=AsyncMock) as mock_nav:
            mock_nav.return_value = TaskResult(success=True, output="navigated")
            result = await agent.execute_task("browse", url="https://example.com")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_task_unknown(self, agent):
        result = await agent.execute_task("unknown_task")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_register_with_email_verify_mode(self, agent):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.url = "https://example.com/register"
        mock_page.close = AsyncMock()
        mock_page.screenshot = AsyncMock()
        loc = MagicMock()
        loc.count = AsyncMock(return_value=1)
        mock_page.locator = MagicMock(return_value=loc)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context

        with patch.object(agent, "_ensure_browser", new_callable=AsyncMock):
            res = await agent.register_with_email(
                url="https://example.com/register",
                form={"#email": "a@b.com"},
                submit_selector="#submit",
                verify_selectors=["#dashboard"],
                require_verify=True,
            )
            assert res.success is True
            assert res.output.get("verified") is True


class TestOOMProtection:
    """Tests for OOM protection mechanisms."""

    def test_kill_orphan_headless_shells_under_limit(self):
        """No kills when process count is within limit."""
        from agents.browser_agent import _kill_orphan_headless_shells, MAX_HEADLESS_PROCESSES

        with patch("agents.browser_agent.platform") as mock_platform, \
             patch("agents.browser_agent.subprocess") as mock_subprocess:
            mock_platform.system.return_value = "Linux"
            # Only 1 process running — under the limit
            mock_subprocess.run.return_value = MagicMock(stdout="12345\n")
            killed = _kill_orphan_headless_shells()
            assert killed == 0

    def test_kill_orphan_headless_shells_over_limit(self):
        """Kills excess processes when over limit."""
        from agents.browser_agent import _kill_orphan_headless_shells, MAX_HEADLESS_PROCESSES

        with patch("agents.browser_agent.platform") as mock_platform, \
             patch("agents.browser_agent.subprocess") as mock_subprocess, \
             patch("agents.browser_agent.os") as mock_os:
            mock_platform.system.return_value = "Linux"
            # 5 processes — should kill 3 (keep MAX_HEADLESS_PROCESSES=2 newest)
            mock_subprocess.run.return_value = MagicMock(stdout="100\n200\n300\n400\n500\n")
            mock_os.kill = MagicMock()

            killed = _kill_orphan_headless_shells()
            assert killed == 3
            # Should kill the 3 lowest PIDs (oldest)
            mock_os.kill.assert_any_call(100, 9)
            mock_os.kill.assert_any_call(200, 9)
            mock_os.kill.assert_any_call(300, 9)

    def test_kill_orphan_headless_shells_not_linux(self):
        """Watchdog is a no-op on non-Linux."""
        from agents.browser_agent import _kill_orphan_headless_shells

        with patch("agents.browser_agent.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            killed = _kill_orphan_headless_shells()
            assert killed == 0

    def test_kill_orphan_headless_shells_pgrep_not_found(self):
        """Handles missing pgrep gracefully."""
        from agents.browser_agent import _kill_orphan_headless_shells

        with patch("agents.browser_agent.platform") as mock_platform, \
             patch("agents.browser_agent.subprocess.run", side_effect=FileNotFoundError("pgrep not found")):
            mock_platform.system.return_value = "Linux"
            killed = _kill_orphan_headless_shells()
            assert killed == 0

    def test_set_memory_limit_logs_info(self):
        """Memory limit function logs info (no RLIMIT_AS, relies on systemd cgroup)."""
        from agents.browser_agent import _set_memory_limit
        # Should not raise — just logs
        _set_memory_limit()

    def test_singleton_pattern(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        """Only one BrowserAgent instance exists."""
        from agents.browser_agent import BrowserAgent
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        BrowserAgent._lock = None

        a = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)
        b = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)
        assert a is b

    def test_chrome_launch_args_include_single_process(self):
        """Verify constrained launch args include safe low-resource flags."""
        from agents.browser_agent import _chromium_launch_args
        args = _chromium_launch_args()
        assert "--single-process" in args
        assert "--disable-dev-shm-usage" in args
        assert "--no-sandbox" in args

    def test_chrome_launch_args_without_constrained_mode(self, monkeypatch):
        from agents.browser_agent import _chromium_launch_args
        monkeypatch.setattr("agents.browser_agent.settings.BROWSER_CONSTRAINED_MODE", False, raising=False)
        args = _chromium_launch_args()
        assert "--single-process" not in args
        assert "--no-zygote" not in args

    @pytest.mark.asyncio
    async def test_page_close_on_navigate_error(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        """Page is closed even when navigation throws."""
        from agents.browser_agent import BrowserAgent
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        BrowserAgent._lock = None

        agent = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Network error"))
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        agent._context = mock_context

        with patch.object(agent, '_ensure_browser', new_callable=AsyncMock):
            result = await agent.navigate("https://example.com")
            assert result.success is False
            assert "Network error" in result.error
            mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_cleanup(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        """_force_cleanup closes all resources without raising."""
        from agents.browser_agent import BrowserAgent
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        BrowserAgent._lock = None

        agent = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)

        # Set up mocks that raise on close
        agent._context = AsyncMock()
        agent._context.close = AsyncMock(side_effect=Exception("context close error"))
        BrowserAgent._browser = AsyncMock()
        BrowserAgent._browser.close = AsyncMock(side_effect=Exception("browser close error"))
        BrowserAgent._playwright_inst = AsyncMock()
        BrowserAgent._playwright_inst.stop = AsyncMock(side_effect=Exception("playwright stop error"))

        # Should not raise despite all close() calls failing
        await agent._force_cleanup()

        assert agent._context is None
        assert BrowserAgent._browser is None
        assert BrowserAgent._playwright_inst is None

    @pytest.mark.asyncio
    async def test_start_calls_watchdog_and_memory_limit(self, mock_llm_router, mock_memory, mock_finance, mock_comms):
        """start() calls watchdog and memory limit before launching browser."""
        from agents.browser_agent import BrowserAgent
        BrowserAgent._instance = None
        BrowserAgent._browser = None
        BrowserAgent._playwright_inst = None
        BrowserAgent._lock = None

        agent = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)

        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_factory = MagicMock()
        mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)

        with patch("playwright.async_api.async_playwright", mock_pw_factory), \
             patch("agents.browser_agent._kill_orphan_headless_shells", return_value=0) as mock_watchdog, \
             patch("agents.browser_agent._set_memory_limit") as mock_memlimit:
            await agent.start()
            mock_watchdog.assert_called_once()
            mock_memlimit.assert_called_once()


@pytest.mark.asyncio
async def test_detect_challenge_by_url(mock_llm_router, mock_memory, mock_finance, mock_comms):
    from agents.browser_agent import BrowserAgent
    BrowserAgent._instance = None
    BrowserAgent._browser = None
    BrowserAgent._playwright_inst = None
    BrowserAgent._lock = None
    agent = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)
    page = AsyncMock()
    page.url = "https://example.com/captcha/challenge"
    page.inner_text = AsyncMock(return_value="")
    blocked, reason = await agent._detect_challenge(page, page.url)
    assert blocked is True
    assert "url=" in reason


@pytest.mark.asyncio
async def test_detect_challenge_by_body_text(mock_llm_router, mock_memory, mock_finance, mock_comms):
    from agents.browser_agent import BrowserAgent
    BrowserAgent._instance = None
    BrowserAgent._browser = None
    BrowserAgent._playwright_inst = None
    BrowserAgent._lock = None
    agent = BrowserAgent(llm_router=mock_llm_router, memory=mock_memory, finance=mock_finance, comms=mock_comms)
    page = AsyncMock()
    page.url = "https://example.com/login"
    page.inner_text = AsyncMock(return_value="Please verify you are human before continue")
    blocked, reason = await agent._detect_challenge(page, page.url)
    assert blocked is True
    assert "keyword=" in reason
