import logging
from abc import ABC, abstractmethod


class Plugin(ABC):
    def __init__(self, config: dict):
        self.config = config

    @property
    def required_keys(self) -> list[str]:
        return []

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__name__)

    def is_configured(self) -> bool:
        return all(
            self.config.get(key) not in (None, "")
            for key in self.required_keys
        )

    @abstractmethod
    async def run(self, *args, **kwargs): ...