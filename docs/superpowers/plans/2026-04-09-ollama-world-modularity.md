# Ollama Adapter + World Modularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ollama LLM adapter (httpx direct) and world modularity (scenario metadata, validation, scaffolding CLI).

**Architecture:** OllamaAdapter implements existing `LLMAdapter` Protocol via httpx. New `scenario.py` module handles metadata loading, validation, and template generation. `__main__.py` gets argparse subcommand dispatch.

**Tech Stack:** Python 3.14, httpx, tenacity, PyYAML, argparse, pytest

**Spec:** `docs/superpowers/specs/2026-04-09-ollama-world-modularity-design.md`

---

### Task 1: Add `LLMError` to `adapter.py` and `httpx` to Dependencies

**Files:**
- Modify: `src/tavern/llm/adapter.py:1-52`
- Modify: `pyproject.toml`

**Context:**
- `adapter.py` contains `LLMConfig`, `LLMAdapter` Protocol, `LLMRegistry`.
- No `LLMError` exists anywhere in the codebase.
- `pyproject.toml` dependencies (line 6-13) need `httpx>=0.27`.

- [ ] **Step 1: Add `LLMError` to `adapter.py`**

In `src/tavern/llm/adapter.py`, add after the `T = TypeVar(...)` line (after line 7):

```python

class LLMError(Exception):
    """LLM adapter error."""
```

- [ ] **Step 2: Add httpx dependency**

In `pyproject.toml`, add `"httpx>=0.27",` to the `dependencies` list after the `"tenacity>=8.0"` line:

```
    "httpx>=0.27",
```

- [ ] **Step 3: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: httpx installed successfully

- [ ] **Step 4: Commit**

```bash
git add src/tavern/llm/adapter.py pyproject.toml
git commit -m "feat: add LLMError exception and httpx dependency"
```

---

### Task 2: OllamaAdapter — `complete` with Retry

**Files:**
- Create: `src/tavern/llm/ollama_llm.py`
- Test: `tests/llm/test_ollama_llm.py`

**Context:**
- Must implement `LLMAdapter` Protocol: `complete(messages, response_format?) -> T | str` and `stream(messages) -> AsyncIterator[str]`.
- AnthropicAdapter (anthropic_llm.py) uses `self._retryer = retry(...)` pattern. Ollama mirrors this for `complete` only.
- Ollama Chat API: POST `/api/chat` with `{"model": ..., "messages": [...], "stream": false}`. Response: `{"message": {"content": "..."}}`.
- When `response_format` is set: add `"format": "json"` to body and append JSON instruction to system message.

- [ ] **Step 1: Write failing tests for `_append_json_instruction`**

```python
# Create tests/llm/test_ollama_llm.py

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.llm.adapter import LLMConfig, LLMRegistry, LLMError
from tavern.world.models import ActionRequest
from tavern.engine.actions import ActionType


def test_append_json_instruction_modifies_last_system():
    from tavern.llm.ollama_llm import _append_json_instruction
    messages = [
        {"role": "system", "content": "First system."},
        {"role": "system", "content": "Second system."},
        {"role": "user", "content": "hello"},
    ]
    result = _append_json_instruction(messages)
    assert result[0] == {"role": "system", "content": "First system."}
    assert result[1]["content"].endswith("Respond with valid JSON only.")
    assert result[2] == {"role": "user", "content": "hello"}
    # Original not modified
    assert messages[1]["content"] == "Second system."


def test_append_json_instruction_no_system_inserts_one():
    from tavern.llm.ollama_llm import _append_json_instruction
    messages = [{"role": "user", "content": "hello"}]
    result = _append_json_instruction(messages)
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert "Respond with valid JSON only." in result[0]["content"]
    assert result[1] == {"role": "user", "content": "hello"}
```

- [ ] **Step 2: Write failing tests for `complete`**

```python
# Append to tests/llm/test_ollama_llm.py

@pytest.mark.asyncio
async def test_complete_returns_text():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": "The tavern is dark."}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    result = await adapter.complete([{"role": "user", "content": "describe"}])
    assert result == "The tavern is dark."


@pytest.mark.asyncio
async def test_complete_with_response_format_returns_parsed_model():
    from tavern.llm.ollama_llm import OllamaAdapter

    json_str = '{"action": "move", "target": "cellar", "detail": "go down", "confidence": 0.9}'
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": json_str}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    result = await adapter.complete(
        [{"role": "user", "content": "go cellar"}],
        response_format=ActionRequest,
    )
    assert isinstance(result, ActionRequest)
    assert result.action == ActionType.MOVE


@pytest.mark.asyncio
async def test_complete_sets_json_format_when_response_format():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": '{"action": "look", "confidence": 1.0}'}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    await adapter.complete(
        [{"role": "system", "content": "You are a parser."}, {"role": "user", "content": "look"}],
        response_format=ActionRequest,
    )

    call_kwargs = adapter._client.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert body["format"] == "json"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/llm/test_ollama_llm.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 4: Implement `OllamaAdapter` (complete only, stream in next task)**

Create `src/tavern/llm/ollama_llm.py`:

```python
from __future__ import annotations

import json
from typing import AsyncIterator, TypeVar

import httpx
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
        self._config = config
        base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout,
        )
        self._retryer = retry(
            retry=retry_if_exception_type(
                (httpx.ConnectError, httpx.TimeoutException)
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

        resp = await self._client.post("/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        raise NotImplementedError("stream implemented in next task")


LLMRegistry.register("ollama", OllamaAdapter)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/llm/test_ollama_llm.py -v`
Expected: all 5 PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/llm/ollama_llm.py tests/llm/test_ollama_llm.py
git commit -m "feat: add OllamaAdapter with complete method and _append_json_instruction"
```

---

### Task 3: OllamaAdapter — `stream` (No Retry)

**Files:**
- Modify: `src/tavern/llm/ollama_llm.py`
- Test: `tests/llm/test_ollama_llm.py`

**Context:**
- Ollama streaming: POST `/api/chat` with `"stream": true`. Response is NDJSON — one JSON object per line, each with `{"message": {"content": "..."}, "done": false}`.
- No tenacity retry on stream — already-yielded chunks can't be recalled.
- On HTTP error, raise `LLMError`.

- [ ] **Step 1: Write failing tests for `stream`**

```python
# Append to tests/llm/test_ollama_llm.py

@pytest.mark.asyncio
async def test_stream_yields_chunks():
    from tavern.llm.ollama_llm import OllamaAdapter

    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = AsyncMock(return_value=_async_lines(lines))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.stream = MagicMock(return_value=mock_resp)

    chunks = []
    async for chunk in adapter.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_raises_llm_error_on_http_failure():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.stream = MagicMock(return_value=mock_resp)

    with pytest.raises(LLMError, match="Ollama stream failed"):
        async for _ in adapter.stream([{"role": "user", "content": "hi"}]):
            pass


async def _async_lines(lines: list[str]):
    for line in lines:
        yield line
```

Note: `import httpx` needs to be added to the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/llm/test_ollama_llm.py::test_stream_yields_chunks tests/llm/test_ollama_llm.py::test_stream_raises_llm_error_on_http_failure -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Implement `stream`**

In `src/tavern/llm/ollama_llm.py`, replace the placeholder `stream` method:

```python
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
```

- [ ] **Step 4: Run all ollama tests**

Run: `pytest tests/llm/test_ollama_llm.py -v`
Expected: all 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/llm/ollama_llm.py tests/llm/test_ollama_llm.py
git commit -m "feat: add OllamaAdapter.stream with NDJSON parsing and LLMError"
```

---

### Task 4: Register Ollama in `app.py`

**Files:**
- Modify: `src/tavern/cli/app.py:17-18`

**Context:**
- OpenAI and Anthropic adapters are registered via side-effect imports at lines 17-18.
- Add same pattern for Ollama.

- [ ] **Step 1: Add import**

In `src/tavern/cli/app.py`, add after line 18 (`from tavern.llm.anthropic_llm import ...`):

```python
from tavern.llm.ollama_llm import OllamaAdapter  # noqa: F401 — triggers registration
```

- [ ] **Step 2: Write registry test**

```python
# Append to tests/llm/test_ollama_llm.py

def test_registry_registers_ollama():
    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = LLMRegistry.create(config)
    from tavern.llm.ollama_llm import OllamaAdapter
    assert isinstance(adapter, OllamaAdapter)
```

- [ ] **Step 3: Run test**

Run: `pytest tests/llm/test_ollama_llm.py::test_registry_registers_ollama -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/app.py tests/llm/test_ollama_llm.py
git commit -m "feat: register OllamaAdapter in app.py imports"
```

---

### Task 5: ScenarioMeta, Validation, and Loading

**Files:**
- Create: `src/tavern/world/scenario.py`
- Test: `tests/world/test_scenario.py`

**Context:**
- `scenario.yaml` lives in each scenario directory alongside `world.yaml`, `characters.yaml`.
- `validate_scenario(path)` checks: scenario.yaml exists + required fields, world.yaml + characters.yaml exist + parseable, cross-reference consistency.
- `load_scenario_meta(path)` returns `ScenarioMeta` dataclass.
- Cross-reference checks: character location_ids in locations, location npc lists in characters, exit targets are valid location IDs, key_items exist in items.

- [ ] **Step 1: Write failing tests for validation**

```python
# Create tests/world/test_scenario.py

from __future__ import annotations

from pathlib import Path
import pytest
import yaml


class TestValidateScenario:
    def test_valid_scenario_returns_no_errors(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        errors = validate_scenario(tmp_path)
        assert errors == []

    def test_missing_scenario_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "scenario.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("scenario.yaml" in e for e in errors)

    def test_missing_required_field_in_scenario_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "scenario.yaml").write_text(
            yaml.dump({"name": "Test", "description": "D"}), encoding="utf-8"
        )
        errors = validate_scenario(tmp_path)
        assert any("author" in e for e in errors)

    def test_missing_world_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "world.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("world.yaml" in e for e in errors)

    def test_missing_characters_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "characters.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("characters.yaml" in e for e in errors)

    def test_invalid_yaml_syntax(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "world.yaml").write_text("{ invalid yaml: [", encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("解析失败" in e for e in errors)

    def test_cross_ref_invalid_location_id(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        chars = yaml.safe_load((tmp_path / "characters.yaml").read_text())
        chars["player"]["location_id"] = "nonexistent_room"
        (tmp_path / "characters.yaml").write_text(yaml.dump(chars), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("nonexistent_room" in e for e in errors)

    def test_cross_ref_invalid_npc_in_location(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        world = yaml.safe_load((tmp_path / "world.yaml").read_text())
        world["locations"]["room"]["npcs"] = ["ghost"]
        (tmp_path / "world.yaml").write_text(yaml.dump(world), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("ghost" in e for e in errors)

    def test_cross_ref_invalid_exit_target(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        world = yaml.safe_load((tmp_path / "world.yaml").read_text())
        world["locations"]["room"]["exits"]["north"] = {"target": "void"}
        (tmp_path / "world.yaml").write_text(yaml.dump(world), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("void" in e for e in errors)


class TestLoadScenarioMeta:
    def test_loads_all_fields(self, tmp_path):
        from tavern.world.scenario import load_scenario_meta
        _create_valid_scenario(tmp_path)
        meta = load_scenario_meta(tmp_path)
        assert meta.name == "测试场景"
        assert meta.author == "Test"
        assert meta.version == "1.0"
        assert meta.path == tmp_path


def _create_valid_scenario(path: Path) -> None:
    (path / "scenario.yaml").write_text(yaml.dump({
        "name": "测试场景",
        "description": "一个测试用的场景",
        "author": "Test",
        "version": "1.0",
    }), encoding="utf-8")
    (path / "world.yaml").write_text(yaml.dump({
        "locations": {
            "room": {
                "name": "房间",
                "description": "一个简单的房间",
                "exits": {},
                "items": [],
                "npcs": [],
            },
        },
        "items": {},
    }), encoding="utf-8")
    (path / "characters.yaml").write_text(yaml.dump({
        "player": {
            "id": "player",
            "name": "玩家",
            "role": "player",
            "traits": [],
            "stats": {"hp": 100},
            "inventory": [],
            "location_id": "room",
        },
        "npcs": {},
    }), encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_scenario.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `scenario.py`**

Create `src/tavern/world/scenario.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_FILES = ("world.yaml", "characters.yaml")
META_FIELDS = ("name", "description", "author", "version")


@dataclass(frozen=True)
class ScenarioMeta:
    name: str
    description: str
    author: str
    version: str
    path: Path


def load_scenario_meta(path: Path) -> ScenarioMeta:
    meta_path = path / "scenario.yaml"
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    return ScenarioMeta(
        name=raw["name"],
        description=raw["description"],
        author=raw["author"],
        version=str(raw["version"]),
        path=path,
    )


def validate_scenario(path: Path) -> list[str]:
    errors: list[str] = []

    meta_path = path / "scenario.yaml"
    if not meta_path.exists():
        errors.append(f"缺少元数据文件: {meta_path}")
    else:
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                errors.append("scenario.yaml 内容不是字典")
            else:
                for field in META_FIELDS:
                    if not meta.get(field):
                        errors.append(f"scenario.yaml 缺少必需字段: {field}")
        except yaml.YAMLError as exc:
            errors.append(f"scenario.yaml 解析失败: {exc}")

    parsed: dict[str, dict] = {}
    for filename in REQUIRED_FILES:
        file_path = path / filename
        if not file_path.exists():
            errors.append(f"缺少必需文件: {filename}")
        else:
            try:
                data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
                parsed[filename] = data if isinstance(data, dict) else {}
            except yaml.YAMLError as exc:
                errors.append(f"{filename} 解析失败: {exc}")

    world_data = parsed.get("world.yaml", {})
    chars_data = parsed.get("characters.yaml", {})

    if world_data and chars_data:
        errors.extend(_cross_reference_check(world_data, chars_data))

    return errors


def _cross_reference_check(world_data: dict, chars_data: dict) -> list[str]:
    errors: list[str] = []
    locations = world_data.get("locations", {})
    items = world_data.get("items", {})
    location_ids = set(locations.keys())

    all_char_ids = set()
    player = chars_data.get("player", {})
    if player:
        all_char_ids.add(player.get("id", "player"))
    npcs = chars_data.get("npcs", {})
    if isinstance(npcs, dict):
        all_char_ids.update(npcs.keys())

    # Character location_ids must exist in locations
    if player:
        loc = player.get("location_id")
        if loc and loc not in location_ids:
            errors.append(f"角色 player 的 location_id '{loc}' 不存在于 locations 中")
    if isinstance(npcs, dict):
        for npc_id, npc_data in npcs.items():
            if isinstance(npc_data, dict):
                loc = npc_data.get("location_id")
                if loc and loc not in location_ids:
                    errors.append(f"角色 {npc_id} 的 location_id '{loc}' 不存在于 locations 中")

    # Location npcs must exist in characters
    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        for npc_id in loc_data.get("npcs", []):
            if npc_id not in all_char_ids:
                errors.append(f"地点 {loc_id} 引用了不存在的 NPC: {npc_id}")

    # Exit targets must be valid location IDs
    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        exits = loc_data.get("exits", {})
        if isinstance(exits, dict):
            for direction, exit_data in exits.items():
                target = exit_data.get("target") if isinstance(exit_data, dict) else None
                if target and target not in location_ids:
                    errors.append(f"地点 {loc_id} 的出口 {direction} 指向不存在的地点: {target}")

    # key_items must exist in items
    item_ids = set(items.keys()) if isinstance(items, dict) else set()
    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        exits = loc_data.get("exits", {})
        if isinstance(exits, dict):
            for direction, exit_data in exits.items():
                key_item = exit_data.get("key_item") if isinstance(exit_data, dict) else None
                if key_item and key_item not in item_ids:
                    errors.append(f"地点 {loc_id} 出口 {direction} 的 key_item '{key_item}' 不存在于 items 中")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/world/test_scenario.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/scenario.py tests/world/test_scenario.py
git commit -m "feat: add ScenarioMeta, validate_scenario, and load_scenario_meta"
```

---

### Task 6: Scaffold Generator and Templates

**Files:**
- Modify: `src/tavern/world/scenario.py`
- Test: `tests/world/test_scenario.py`

**Context:**
- `scaffold_scenario(name, parent)` creates a scenario directory with template files.
- Templates are minimal but valid YAML that passes `validate_scenario`.

- [ ] **Step 1: Write failing tests for scaffold**

```python
# Append to tests/world/test_scenario.py

class TestScaffoldScenario:
    def test_creates_directory_structure(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario
        result = scaffold_scenario("my_story", tmp_path)
        assert result == tmp_path / "my_story"
        assert (result / "scenario.yaml").exists()
        assert (result / "world.yaml").exists()
        assert (result / "characters.yaml").exists()
        assert (result / "story.yaml").exists()
        assert (result / "skills").is_dir()

    def test_generated_scenario_passes_validation(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario, validate_scenario
        result = scaffold_scenario("valid_test", tmp_path)
        errors = validate_scenario(result)
        assert errors == [], f"Scaffold should produce valid scenario: {errors}"

    def test_raises_if_directory_exists(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario
        (tmp_path / "existing").mkdir()
        with pytest.raises(FileExistsError):
            scaffold_scenario("existing", tmp_path)

    def test_scenario_yaml_contains_name(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario, load_scenario_meta
        scaffold_scenario("my_story", tmp_path)
        meta = load_scenario_meta(tmp_path / "my_story")
        assert meta.name == "my_story"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_scenario.py::TestScaffoldScenario -v`
Expected: FAIL with `ImportError` (function doesn't exist)

- [ ] **Step 3: Implement scaffold templates and function**

Add to the end of `src/tavern/world/scenario.py`:

```python
SCENARIO_TEMPLATE = """\
# 场景元数据
name: {name}
description: 请在此描述你的场景
author: Unknown
version: "1.0"
"""

WORLD_TEMPLATE = """\
# 世界定义 — 地点和物品
locations:
  start_room:
    name: 起始房间
    description: 这是一个空旷的房间，等待你来填充。
    exits: {{}}
    items: []
    npcs: []

items: {{}}
"""

CHARACTERS_TEMPLATE = """\
# 角色定义
player:
  id: player
  name: 冒险者
  role: player
  traits:
    - 勇敢
  stats:
    hp: 100
  inventory: []
  location_id: start_room

npcs: {{}}
"""

STORY_TEMPLATE = """\
# 剧情节点定义
nodes: []
"""


def scaffold_scenario(name: str, parent: Path) -> Path:
    target = parent / name
    if target.exists():
        raise FileExistsError(f"目录已存在: {target}")
    target.mkdir(parents=True)
    (target / "skills").mkdir()
    (target / "scenario.yaml").write_text(
        SCENARIO_TEMPLATE.format(name=name), encoding="utf-8"
    )
    (target / "world.yaml").write_text(WORLD_TEMPLATE, encoding="utf-8")
    (target / "characters.yaml").write_text(CHARACTERS_TEMPLATE, encoding="utf-8")
    (target / "story.yaml").write_text(STORY_TEMPLATE, encoding="utf-8")
    return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/world/test_scenario.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/scenario.py tests/world/test_scenario.py
git commit -m "feat: add scaffold_scenario with YAML templates"
```

---

### Task 7: Argparse Subcommands in `__main__.py`

**Files:**
- Modify: `src/tavern/__main__.py`
- Test: `tests/test_main.py`

**Context:**
- Current `__main__.py` is 12 lines: `main()` → `GameApp()` → `run()`.
- New: argparse with `run` (default) and `create-scenario` subcommands.
- `tavern` (no args) and `tavern run` both start the game.

- [ ] **Step 1: Write failing tests**

```python
# Create tests/test_main.py

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_no_args_runs_game():
    with patch("sys.argv", ["tavern"]):
        with patch("tavern.__main__._run_game") as mock_run:
            from tavern.__main__ import main
            main()
            mock_run.assert_called_once()


def test_run_subcommand_runs_game():
    with patch("sys.argv", ["tavern", "run"]):
        with patch("tavern.__main__._run_game") as mock_run:
            from tavern.__main__ import main
            main()
            mock_run.assert_called_once()


def test_create_scenario_calls_scaffold(tmp_path):
    with patch("sys.argv", ["tavern", "create-scenario", "my_test", "--dir", str(tmp_path)]):
        with patch("tavern.world.scenario.scaffold_scenario") as mock_scaffold:
            mock_scaffold.return_value = tmp_path / "my_test"
            from tavern.__main__ import main
            main()
            mock_scaffold.assert_called_once_with("my_test", Path(str(tmp_path)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL (no `_run_game` function)

- [ ] **Step 3: Implement new `__main__.py`**

Replace `src/tavern/__main__.py` entirely:

```python
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def _run_game(config_path: str = "config.yaml") -> None:
    from tavern.cli.app import GameApp
    app = GameApp(config_path=config_path)
    asyncio.run(app.run())


def main() -> None:
    parser = argparse.ArgumentParser(prog="tavern", description="CLI 互动小说游戏")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="启动游戏")
    run_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    create_parser = sub.add_parser("create-scenario", help="创建新场景模板")
    create_parser.add_argument("name", help="场景名称（用作目录名）")
    create_parser.add_argument(
        "--dir", default="data/scenarios",
        help="场景父目录（默认: data/scenarios）",
    )

    args = parser.parse_args()

    if args.command == "create-scenario":
        from tavern.world.scenario import scaffold_scenario
        target = scaffold_scenario(args.name, Path(args.dir))
        print(f"场景模板已创建: {target}")
    else:
        config_path = getattr(args, "config", "config.yaml")
        _run_game(config_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: all 3 PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/__main__.py tests/test_main.py
git commit -m "feat: add argparse subcommands — run (default) and create-scenario"
```

---

### Task 8: App Startup Validation and Tavern scenario.yaml

**Files:**
- Modify: `src/tavern/cli/app.py:40-46` (init)
- Modify: `src/tavern/cli/renderer.py:79-88` (render_welcome)
- Create: `data/scenarios/tavern/scenario.yaml`

**Context:**
- `GameApp.__init__` loads scenario at line 45-46. Add validation before `load_scenario`.
- `render_welcome` (line 79) hardcodes "醉龙酒馆". Use `ScenarioMeta.name` instead.
- Tavern scenario needs a `scenario.yaml` file.

- [ ] **Step 1: Create tavern `scenario.yaml`**

Create `data/scenarios/tavern/scenario.yaml`:

```yaml
name: 奇幻酒馆
description: 在神秘的酒馆中探索，揭开地下室的秘密。多NPC对话驱动，地下室之谜主线。
author: Tavern Team
version: "1.0"
```

- [ ] **Step 2: Add validation to `GameApp.__init__`**

In `src/tavern/cli/app.py`, add import at the top (after line 24):

```python
from tavern.world.scenario import validate_scenario, load_scenario_meta
```

Then replace lines 45-46:

Old:
```python
        scenario_path = Path(game_config.get("scenario", "data/scenarios/tavern"))
        initial_state = load_scenario(scenario_path)
```

New:
```python
        scenario_path = Path(game_config.get("scenario", "data/scenarios/tavern"))
        errors = validate_scenario(scenario_path)
        if errors:
            from rich.console import Console
            err_console = Console(stderr=True)
            for e in errors:
                err_console.print(f"[red]✗ {e}[/]")
            raise SystemExit(1)
        self._scenario_meta = load_scenario_meta(scenario_path)
        initial_state = load_scenario(scenario_path)
```

- [ ] **Step 3: Update `render_welcome` to accept scenario name**

In `src/tavern/cli/renderer.py`, replace lines 79-90 (`render_welcome`):

```python
    def render_welcome(self, state: WorldState, scenario_name: str = "醉龙酒馆") -> None:
        self.console.print(
            Panel(
                f"[bold]{scenario_name}[/]\n\n"
                "欢迎来到奇幻世界的互动小说体验。\n"
                "输入自然语言与世界互动，输入 [cyan]help[/] 查看命令列表。",
                title="🐉 Tavern",
                border_style="bright_blue",
            )
        )
        location = state.locations[state.characters[state.player_id].location_id]
        self.console.print(f"\n{location.description}\n")
```

- [ ] **Step 4: Update `render_welcome` call in `app.py`**

Find the call to `self._renderer.render_welcome(self.state)` in `app.py` (in the `run` method) and update it to:

```python
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
```

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add data/scenarios/tavern/scenario.yaml src/tavern/cli/app.py src/tavern/cli/renderer.py
git commit -m "feat: add startup validation, tavern scenario.yaml, dynamic welcome name"
```
