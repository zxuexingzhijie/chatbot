from __future__ import annotations

import json
from typing import AsyncIterator, TypeVar

try:
    import httpx
except ImportError:
    httpx = None
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tavern.llm.adapter import LLMConfig, LLMError, LLMRegistry

T = TypeVar("T", bound=BaseModel)


def _append_json_instruction(messages: list[dict]) -> list[dict]:
    """Append a JSON-only instruction to the last system message.

    If no system message exists, insert one at position 0.
    Returns a new list; the original is not mutated.
    """
    suffix = "Respond with valid JSON only."
    found = False
    result: list[dict] = []
    for msg in reversed(messages):
        if msg.get("role") == "system" and not found:
            result.append({**msg, "content": msg["content"] + "\n" + suffix})
            found = True
        else:
            result.append(msg)
    result.reverse()
    if not found:
        result.insert(0, {"role": "system", "content": suffix})
    return result


class OllamaAdapter:
    def __init__(self, config: LLMConfig) -> None:
        if httpx is None:
            raise ImportError(
                "httpx 包未安装。请运行: pip install tavern[ollama]"
            )
        self._config = config
        base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout,
        )
        self._retryer = retry(
            retry=retry_if_exception_type(
                (httpx.ConnectError, httpx.TimeoutException),
            ),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(config.max_retries),
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
        body: dict = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
            },
        }
        if response_format is not None:
            body["format"] = "json"
            body["messages"] = _append_json_instruction(messages)

        try:
            resp = await self._client.post("/api/chat", json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Ollama API error: {exc.response.status_code}") from exc

        data = resp.json()
        content: str = data["message"]["content"]

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        body: dict = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self._config.temperature,
            },
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk_data = json.loads(line)
                    content = chunk_data.get("message", {}).get("content", "")
                    if content:
                        yield content
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama stream failed: {exc}") from exc


LLMRegistry.register("ollama", OllamaAdapter)
