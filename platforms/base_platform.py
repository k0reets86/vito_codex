"""BasePlatform — абстрактный базовый класс для платформенных интеграций."""

from abc import ABC, abstractmethod
from typing import Any


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
