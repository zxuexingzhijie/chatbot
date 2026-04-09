from __future__ import annotations

from typing import AsyncIterator, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """LLM adapter error."""


class LLMConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.5
    max_tokens: int = 500
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 30.0
    max_retries: int = 3


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str: ...

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...


class LLMRegistry:
    _providers: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type) -> None:
        cls._providers[name] = adapter_cls

    @classmethod
    def create(cls, config: LLMConfig) -> LLMAdapter:
        if config.provider not in cls._providers:
            raise ValueError(
                f"Unknown LLM provider: '{config.provider}'."
                f" Available: {list(cls._providers.keys())}"
            )
        return cls._providers[config.provider](config=config)

    @classmethod
    def reset(cls) -> None:
        """Clear all registered providers. Intended for test isolation."""
        cls._providers.clear()
