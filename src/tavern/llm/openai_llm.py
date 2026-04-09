from __future__ import annotations

import os
from typing import AsyncIterator, TypeVar

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from tavern.llm.adapter import LLMConfig, LLMRegistry

T = TypeVar("T", bound=BaseModel)


class OpenAIAdapter:
    def __init__(self, config: LLMConfig) -> None:
        if AsyncOpenAI is None:
            raise ImportError(
                "openai 包未安装。请运行: pip install tavern[openai]"
            )
        self._config = config
        api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        self._client = AsyncOpenAI(
            api_key=api_key or "not-configured",
            base_url=config.base_url,
            timeout=config.timeout,
        )

    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        retryer = retry(
            stop=stop_after_attempt(self._config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        return await retryer(self._complete)(messages, response_format)

    async def _complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        kwargs: dict = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}
            if messages and messages[0]["role"] == "system":
                messages = list(messages)
                messages[0] = {
                    **messages[0],
                    "content": messages[0]["content"]
                    + "\n\nRespond with valid JSON only.",
                }
            kwargs["messages"] = messages

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


LLMRegistry.register("openai", OpenAIAdapter)
