from __future__ import annotations

import os
from typing import AsyncIterator, TypeVar

try:
    import anthropic
except ImportError:
    anthropic = None
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tavern.llm.adapter import LLMConfig

T = TypeVar("T", bound=BaseModel)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract all system messages and join them; return (system_str, remaining_messages)."""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    remaining = [m for m in messages if m.get("role") != "system"]
    return "\n".join(system_parts), remaining


class AnthropicAdapter:
    def __init__(self, config: LLMConfig) -> None:
        if anthropic is None:
            raise ImportError(
                "anthropic 包未安装。请运行: pip install tavern[anthropic]"
            )
        self._config = config
        api_key = config.api_key or (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        base = config.base_url.rstrip("/") if config.base_url else None
        if base and base.endswith("/v1"):
            base = base[:-3]
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base,
            timeout=config.timeout,
            max_retries=0,  # tenacity handles retry
        )
        self._retryer = retry(
            retry=retry_if_exception_type(
                (anthropic.RateLimitError, anthropic.APIConnectionError)
            ),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(self._config.max_retries),
            reraise=True,
        )

    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        return await self._retryer(self._complete)(messages, response_format)

    async def _complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        system, user_messages = _split_system(messages)

        if response_format is not None:
            suffix = "Respond with valid JSON only."
            system = (system + "\n" + suffix) if system else suffix

        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens if self._config.max_tokens is not None else 8192,
            "temperature": self._config.temperature,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        content = response.content[0].text

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        system, user_messages = _split_system(messages)
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens if self._config.max_tokens is not None else 8192,
            "temperature": self._config.temperature,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as s:
            async for chunk in s.text_stream:
                yield chunk
