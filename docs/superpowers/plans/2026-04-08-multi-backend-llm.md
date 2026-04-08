# Multi-Backend LLM Adapters (Phase 4b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `AnthropicAdapter` so the game can use Claude as the LLM backend, and document Ollama support (which works via existing `OpenAIAdapter` + `base_url` config with zero new code).

**Architecture:** New `src/tavern/llm/anthropic_llm.py` implements the `LLMAdapter` Protocol using `anthropic.AsyncAnthropic`, registers itself as `"anthropic"` at import time — exactly the same pattern as `openai_llm.py`. The `AnthropicAdapter.complete()` method extracts all `system`-role messages, joins them with `"\n"`, and passes them as Anthropic's top-level `system` parameter. When `response_format` is provided it appends `"Respond with valid JSON only."` to the system text and calls `response_format.model_validate_json()` on the result — matching `OpenAIAdapter` behavior. Retry is handled by tenacity (not the SDK's built-in retry).

**Tech Stack:** Python 3.12, `anthropic` SDK (`AsyncAnthropic`), `tenacity`, `pytest-asyncio`, `unittest.mock`

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/tavern/llm/anthropic_llm.py` | `AnthropicAdapter` + `_split_system` helper, registers `"anthropic"` |
| Modify | `src/tavern/cli/app.py` line 17 | `import AnthropicAdapter  # noqa: F401` to trigger registration |
| Modify | `config.yaml` | Add Ollama config comment block |
| Create | `tests/llm/test_anthropic_llm.py` | 8 unit tests for `AnthropicAdapter` |

---

## Task 1: AnthropicAdapter — core complete() and stream()

**Files:**
- Create: `src/tavern/llm/anthropic_llm.py`
- Create: `tests/llm/test_anthropic_llm.py`

### Background

`OpenAIAdapter` (in `src/tavern/llm/openai_llm.py`) is the model to follow. Key differences for Anthropic:
- Uses `anthropic.AsyncAnthropic` instead of `openai.AsyncOpenAI`
- `system` messages are extracted from `messages` list and passed as a separate `system=` kwarg
- Streaming uses `client.messages.stream()` context manager, yields from `.text_stream`
- Retry errors: `anthropic.RateLimitError`, `anthropic.APIConnectionError`

- [ ] **Step 1: Write failing tests**

```python
# tests/llm/test_anthropic_llm.py
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.anthropic_llm import AnthropicAdapter, _split_system
from tavern.world.models import ActionRequest
from tavern.engine.actions import ActionType


# ── _split_system helper ───────────────────────────────────────────────────

def test_split_system_no_system_messages():
    messages = [{"role": "user", "content": "hello"}]
    system, remaining = _split_system(messages)
    assert system == ""
    assert remaining == messages


def test_split_system_single_system_message():
    messages = [
        {"role": "system", "content": "You are a bartender."},
        {"role": "user", "content": "hello"},
    ]
    system, remaining = _split_system(messages)
    assert system == "You are a bartender."
    assert remaining == [{"role": "user", "content": "hello"}]


def test_split_system_multiple_system_messages_joined():
    messages = [
        {"role": "system", "content": "Part A."},
        {"role": "system", "content": "Part B."},
        {"role": "user", "content": "hello"},
    ]
    system, remaining = _split_system(messages)
    assert system == "Part A.\nPart B."
    assert len(remaining) == 1


# ── AnthropicAdapter.complete() ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_returns_text():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="The tavern is dark.")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    result = await adapter.complete([{"role": "user", "content": "describe"}])
    assert result == "The tavern is dark."


@pytest.mark.asyncio
async def test_complete_with_response_format_returns_parsed_model():
    json_str = '{"action": "move", "target": "cellar", "detail": "go down", "confidence": 0.9}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json_str)]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    result = await adapter.complete(
        [{"role": "user", "content": "go cellar"}],
        response_format=ActionRequest,
    )
    assert isinstance(result, ActionRequest)
    assert result.action == ActionType.MOVE
    assert result.target == "cellar"


@pytest.mark.asyncio
async def test_complete_with_response_format_appends_json_instruction():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"action": "look", "confidence": 1.0}')]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    messages = [
        {"role": "system", "content": "You are a game assistant."},
        {"role": "user", "content": "look around"},
    ]
    await adapter.complete(messages, response_format=ActionRequest)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Respond with valid JSON only." in call_kwargs["system"]


@pytest.mark.asyncio
async def test_complete_no_system_omits_system_kwarg():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    await adapter.complete([{"role": "user", "content": "hi"}])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" not in call_kwargs


# ── AnthropicAdapter.stream() ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_yields_chunks():
    async def fake_text_stream():
        yield "Hello"
        yield " world"

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.text_stream = fake_text_stream()

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    chunks = []
    async for chunk in adapter.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]


# ── API key / registry ─────────────────────────────────────────────────────

def test_api_key_env_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = MagicMock()
        adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307", api_key=None))
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs["api_key"] == "env-key-123"


def test_registry_registers_anthropic():
    config = LLMConfig(provider="anthropic", model="claude-3-haiku-20240307", api_key="test")
    with patch("anthropic.AsyncAnthropic"):
        adapter = LLMRegistry.create(config)
    assert isinstance(adapter, AnthropicAdapter)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/llm/test_anthropic_llm.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'tavern.llm.anthropic_llm'`

- [ ] **Step 3: Implement AnthropicAdapter**

```python
# src/tavern/llm/anthropic_llm.py
from __future__ import annotations

import os
from typing import AsyncIterator, TypeVar

import anthropic
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tavern.llm.adapter import LLMConfig, LLMRegistry

T = TypeVar("T", bound=BaseModel)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract all system messages and join them; return (system_str, remaining_messages)."""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    remaining = [m for m in messages if m.get("role") != "system"]
    return "\n".join(system_parts), remaining


class AnthropicAdapter:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=0,  # tenacity handles retry
        )

    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        retryer = retry(
            retry=retry_if_exception_type(
                (anthropic.RateLimitError, anthropic.APIConnectionError)
            ),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(self._config.max_retries),
            reraise=True,
        )
        return await retryer(self._complete)(messages, response_format)

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
            "max_tokens": self._config.max_tokens,
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
            "max_tokens": self._config.max_tokens,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as s:
            async for chunk in s.text_stream:
                yield chunk


LLMRegistry.register("anthropic", AnthropicAdapter)
```

- [ ] **Step 4: Install anthropic SDK if not present**

```bash
cd /Users/makoto/Downloads/work/chatbot
pip show anthropic 2>&1 | head -3
```

If not installed:
```bash
pip install anthropic
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
python -m pytest tests/llm/test_anthropic_llm.py -v
```

Expected: 10 tests PASSED

- [ ] **Step 6: Commit**

```bash
git add src/tavern/llm/anthropic_llm.py tests/llm/test_anthropic_llm.py
git commit -m "feat: add AnthropicAdapter with complete/stream and tenacity retry"
```

---

## Task 2: GameApp integration + Ollama config docs

**Files:**
- Modify: `src/tavern/cli/app.py` (line 17 area)
- Modify: `config.yaml`

### Background

`app.py` currently has this import block:

```python
from tavern.llm.openai_llm import OpenAIAdapter  # noqa: F401 — triggers registration
```

Adding an equivalent import for `AnthropicAdapter` ensures it registers itself when the game starts, even if the user config doesn't reference it yet. This mirrors the existing `OpenAIAdapter` import.

- [ ] **Step 1: Write the failing test (registry not populated without import)**

Add this test to `tests/llm/test_anthropic_llm.py`:

```python
def test_anthropic_registered_after_import():
    """Importing anthropic_llm registers 'anthropic' in the global registry."""
    # Re-import to ensure registration ran (module may already be cached)
    import importlib
    import tavern.llm.anthropic_llm  # noqa: F401
    importlib.reload(tavern.llm.anthropic_llm)  # force re-registration
    assert "anthropic" in LLMRegistry._providers
```

Run to confirm it passes (registration already happened in Task 1):

```bash
python -m pytest tests/llm/test_anthropic_llm.py::test_anthropic_registered_after_import -v
```

Expected: PASS (the import in Task 1 already registered it)

- [ ] **Step 2: Add import to app.py**

In `src/tavern/cli/app.py`, find this line (currently line 17):

```python
from tavern.llm.openai_llm import OpenAIAdapter  # noqa: F401 — triggers registration
```

Add the Anthropic import immediately after:

```python
from tavern.llm.openai_llm import OpenAIAdapter  # noqa: F401 — triggers registration
from tavern.llm.anthropic_llm import AnthropicAdapter  # noqa: F401 — triggers registration
```

- [ ] **Step 3: Run full test suite to check no regressions**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 4: Add Ollama config comment to config.yaml**

In `config.yaml`, add the following block after the existing `llm:` section (after the `narrative:` subsection ends, before `game:`):

```yaml
# ── Ollama (local) ──────────────────────────────────────────────────────────
# Ollama is OpenAI-compatible. Use provider: openai with a custom base_url.
# Start Ollama locally: https://ollama.com
# Example:
#
# llm:
#   intent:
#     provider: openai
#     model: llama3.2
#     base_url: http://localhost:11434/v1
#     api_key: ollama        # Ollama requires a non-empty string; value is ignored
#     temperature: 0.1
#     max_tokens: 200
#   narrative:
#     provider: openai
#     model: llama3.2
#     base_url: http://localhost:11434/v1
#     api_key: ollama
#     temperature: 0.8
#     max_tokens: 500
# ───────────────────────────────────────────────────────────────────────────
```

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/app.py config.yaml tests/llm/test_anthropic_llm.py
git commit -m "feat: register AnthropicAdapter in GameApp; add Ollama config docs"
```

---

## Verification

After both tasks are complete, run the full test suite:

```bash
python -m pytest tests/ -q
```

Expected: all tests pass (no regressions). Then check coverage on the new file:

```bash
python -m pytest tests/llm/test_anthropic_llm.py --cov=tavern.llm.anthropic_llm --cov-report=term-missing
```

Expected: 90%+ coverage on `anthropic_llm.py`.
