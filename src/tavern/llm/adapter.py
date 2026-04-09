from __future__ import annotations

from typing import AsyncIterator, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, field_validator

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

    @field_validator("provider", "model", "base_url", "api_key", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str: ...

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...


class LLMRegistry:
    _providers: dict[str, type | tuple[str, str]] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type) -> None:
        cls._providers[name] = adapter_cls

    @classmethod
    def register_lazy(cls, name: str, module_path: str, class_name: str) -> None:
        cls._providers[name] = (module_path, class_name)

    @classmethod
    def create(cls, config: LLMConfig) -> LLMAdapter:
        entry = cls._providers.get(config.provider)
        if entry is None:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unknown LLM provider: '{config.provider}'."
                f" Available: {available}"
            )
        if isinstance(entry, tuple):
            module_path, class_name = entry
            import importlib
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)
            cls._providers[config.provider] = adapter_cls
        else:
            adapter_cls = entry
        return adapter_cls(config=config)

    @classmethod
    def reset(cls) -> None:
        """Clear all registered providers. Intended for test isolation."""
        cls._providers.clear()


LLMRegistry.register_lazy("openai", "tavern.llm.openai_llm", "OpenAIAdapter")
LLMRegistry.register_lazy("anthropic", "tavern.llm.anthropic_llm", "AnthropicAdapter")
LLMRegistry.register_lazy("ollama", "tavern.llm.ollama_llm", "OllamaAdapter")
