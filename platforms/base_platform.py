"""BasePlatform — абстрактный базовый класс для платформенных интеграций."""

from abc import ABC, abstractmethod
from typing import Any

from modules.platform_repeatability import attach_analytics_repeatability, attach_publish_repeatability


class BasePlatform(ABC):
    def __init__(self, name: str, browser_agent=None):
        self.name = name
        self.browser_agent = browser_agent
        self._authenticated = False

    @abstractmethod
    async def authenticate(self) -> bool:
        ...

    @abstractmethod
    async def publish(self, content: dict) -> dict:
        ...

    @abstractmethod
    async def get_analytics(self) -> dict:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    def _finalize_publish_result(
        self,
        result: dict[str, Any],
        *,
        mode: str,
        artifact_flags: dict[str, Any] | None = None,
        required_artifacts: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return attach_publish_repeatability(
            result,
            platform=self.name,
            mode=mode,
            artifact_flags=artifact_flags,
            required_artifacts=required_artifacts,
        )

    def _finalize_analytics_result(self, result: dict[str, Any], *, source: str) -> dict[str, Any]:
        return attach_analytics_repeatability(result, platform=self.name, source=source)
