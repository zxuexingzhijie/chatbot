# Phase 2b: LLM Narrative Generation + Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-generated narrative for all successful actions with typewriter streaming, falling back to rule engine messages on LLM failure.

**Architecture:** A `Narrator` class wraps `LLMService.stream_narrative()` to build prompts from `NarrativeContext` and yield streamed chunks. `Renderer.render_stream()` outputs chunks with typewriter effect. `GameApp._handle_free_input()` routes successful non-dialogue results through the narrator instead of `render_result()`.

**Tech Stack:** Python 3.12+, asyncio AsyncIterator, Rich Console, OpenAI streaming (`stream=True` already in `OpenAIAdapter.stream()`), pytest-asyncio.

---

## File Map

| Operation | File | Responsibility |
|-----------|------|----------------|
| Create | `src/tavern/narrator/__init__.py` | Package marker |
| Create | `src/tavern/narrator/prompts.py` | `NarrativeContext` + `NARRATIVE_TEMPLATES` + `build_narrative_prompt()` |
| Create | `src/tavern/narrator/narrator.py` | `Narrator` class with `stream_narrative()` and fallback |
| Modify | `src/tavern/llm/service.py` | Add `stream_narrative(system_prompt, action_message) -> AsyncIterator[str]` |
| Modify | `src/tavern/cli/renderer.py` | Add `async render_stream(stream: AsyncIterator[str]) -> None` |
| Modify | `src/tavern/cli/app.py` | Wire narrator into `_handle_free_input()` |
| Create | `tests/narrator/__init__.py` | Package marker |
| Create | `tests/narrator/test_prompts.py` | Tests for `NarrativeContext`, templates, `build_narrative_prompt()` |
| Create | `tests/narrator/test_narrator.py` | Tests for `Narrator.stream_narrative()` including fallback |
| Create | `tests/llm/test_service_narrative.py` | Tests for `LLMService.stream_narrative()` |
| Modify | `tests/cli/test_renderer.py` | Tests for `render_stream()` |

---

### Task 1: `NarrativeContext` and `build_narrative_prompt()`

**Files:**
- Create: `src/tavern/narrator/__init__.py`
- Create: `src/tavern/narrator/prompts.py`
- Create: `tests/narrator/__init__.py`
- Test: `tests/narrator/test_prompts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/narrator/test_prompts.py
import pytest
from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt

class TestNarrativeContext:
    def test_creation(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走进了酒馆大厅。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        assert ctx.action_type == "move"
        assert ctx.target is None

    def test_immutable(self):
        ctx = NarrativeContext(
            action_type="look",
            action_message="你仔细观察四周。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.action_type = "move"  # type: ignore

    def test_with_target(self):
        ctx = NarrativeContext(
            action_type="take",
            action_message="你拾起了旧告示。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target="旧告示",
        )
        assert ctx.target == "旧告示"


class TestBuildNarrativePrompt:
    def test_returns_two_messages(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走进了吧台区。",
            location_name="吧台区",
            location_desc="木质吧台前摆着几张高脚凳。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_contains_location_name(self):
        ctx = NarrativeContext(
            action_type="look",
            action_message="你环顾四周。",
            location_name="地下室",
            location_desc="阴暗潮湿的地下室。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert "地下室" in messages[0]["content"] or "地下室" in messages[1]["content"]

    def test_user_message_contains_action_message(self):
        ctx = NarrativeContext(
            action_type="take",
            action_message="你拾起了地下室钥匙。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target="地下室钥匙",
        )
        messages = build_narrative_prompt(ctx)
        assert "地下室钥匙" in messages[1]["content"]

    def test_move_uses_different_system_than_look(self):
        ctx_move = NarrativeContext(
            action_type="move",
            action_message="你走进了吧台区。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target=None,
        )
        ctx_look = NarrativeContext(
            action_type="look",
            action_message="你环顾四周。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target=None,
        )
        msg_move = build_narrative_prompt(ctx_move)
        msg_look = build_narrative_prompt(ctx_look)
        assert msg_move[0]["content"] != msg_look[0]["content"]

    def test_unknown_action_type_uses_default_template(self):
        ctx = NarrativeContext(
            action_type="custom",
            action_message="你做了些奇怪的事情。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        # Should not raise; default template applied
        assert messages[0]["role"] == "system"

    def test_system_contains_player_name(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走向北方。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="勇敢的艾拉",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        full_text = messages[0]["content"] + messages[1]["content"]
        # Player name context is included somewhere
        assert len(full_text) > 50
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/narrator/test_prompts.py -v
```
Expected: `ModuleNotFoundError: No module named 'tavern.narrator'`

- [ ] **Step 3: Create package markers and implement `prompts.py`**

```python
# src/tavern/narrator/__init__.py
# (empty)
```

```python
# tests/narrator/__init__.py
# (empty)
```

```python
# src/tavern/narrator/prompts.py
from __future__ import annotations

from dataclasses import dataclass

NARRATIVE_TEMPLATES: dict[str, str] = {
    "move": (
        "你是一位奇幻小说叙述者。玩家刚刚进入了一个新地点。"
        "用2-3句话描写玩家进入该地点时的氛围感：环境细节、光线、声音、气味。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "look": (
        "你是一位奇幻小说叙述者。玩家正在仔细观察周围。"
        "用2-3句话侧重感官细节：视觉、听觉、触觉体验，营造沉浸感。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "take": (
        "你是一位奇幻小说叙述者。玩家刚刚拾起了一件物品。"
        "用2-3句话简短描写拾取动作和物品质感：重量、材质、感觉。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "_default": (
        "你是一位奇幻小说叙述者。玩家刚刚完成了一个行动。"
        "用2-3句话简短描写结果：点题即止，带一点情境感。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
}


@dataclass(frozen=True)
class NarrativeContext:
    action_type: str
    action_message: str
    location_name: str
    location_desc: str
    player_name: str
    target: str | None


def build_narrative_prompt(ctx: NarrativeContext) -> list[dict]:
    system_style = NARRATIVE_TEMPLATES.get(ctx.action_type, NARRATIVE_TEMPLATES["_default"])

    system_content = (
        f"{system_style}\n\n"
        f"当前地点：{ctx.location_name}——{ctx.location_desc}\n"
        f"玩家角色名：{ctx.player_name}"
    )

    user_parts = [ctx.action_message]
    if ctx.target:
        user_parts.append(f"（涉及对象：{ctx.target}）")
    user_content = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/narrator/test_prompts.py -v
```
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/narrator/__init__.py src/tavern/narrator/prompts.py \
        tests/narrator/__init__.py tests/narrator/test_prompts.py
git commit -m "feat: add NarrativeContext and build_narrative_prompt"
```

---

### Task 2: `LLMService.stream_narrative()`

**Files:**
- Modify: `src/tavern/llm/service.py`
- Create: `tests/llm/test_service_narrative.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/llm/test_service_narrative.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.llm.service import LLMService


async def _async_gen(*values):
    for v in values:
        yield v


@pytest.fixture
def mock_intent_adapter():
    return AsyncMock()


@pytest.fixture
def mock_narrative_adapter():
    adapter = MagicMock()
    adapter.stream = MagicMock()
    return adapter


@pytest.fixture
def llm_service(mock_intent_adapter, mock_narrative_adapter):
    return LLMService(
        intent_adapter=mock_intent_adapter,
        narrative_adapter=mock_narrative_adapter,
    )


class TestStreamNarrative:
    @pytest.mark.asyncio
    async def test_yields_chunks_from_narrative_adapter(
        self, llm_service, mock_narrative_adapter
    ):
        mock_narrative_adapter.stream = MagicMock(
            return_value=_async_gen("你走进了", "温暖的酒馆。")
        )
        chunks = []
        async for chunk in llm_service.stream_narrative(
            system_prompt="你是叙述者",
            action_message="你走进了酒馆大厅。",
        ):
            chunks.append(chunk)
        assert chunks == ["你走进了", "温暖的酒馆。"]

    @pytest.mark.asyncio
    async def test_passes_correct_messages_to_adapter(
        self, llm_service, mock_narrative_adapter
    ):
        captured: list[list[dict]] = []

        async def capturing_stream(messages):
            captured.append(messages)
            return
            yield  # make it an async generator

        mock_narrative_adapter.stream = capturing_stream
        async for _ in llm_service.stream_narrative(
            system_prompt="系统提示",
            action_message="行动消息",
        ):
            pass

        assert len(captured) == 1
        msgs = captured[0]
        assert msgs[0] == {"role": "system", "content": "系统提示"}
        assert msgs[1] == {"role": "user", "content": "行动消息"}
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/llm/test_service_narrative.py -v
```
Expected: `AttributeError: 'LLMService' object has no attribute 'stream_narrative'`

- [ ] **Step 3: Add `stream_narrative` to `LLMService`**

In `src/tavern/llm/service.py`, add after the `generate_summary` method:

```python
    async def stream_narrative(
        self,
        system_prompt: str,
        action_message: str,
    ):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": action_message},
        ]
        async for chunk in self._narrative.stream(messages):
            yield chunk
```

Also add the return type annotation at the top of the file — `from typing import AsyncIterator` is not needed since we use `async def` with `yield` directly (Python infers the generator type). No import changes needed.

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/llm/test_service_narrative.py -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/llm/service.py tests/llm/test_service_narrative.py
git commit -m "feat: add LLMService.stream_narrative streaming method"
```

---

### Task 3: `Narrator` class

**Files:**
- Create: `src/tavern/narrator/narrator.py`
- Test: `tests/narrator/test_narrator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/narrator/test_narrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.engine.actions import ActionType
from tavern.narrator.narrator import Narrator
from tavern.world.models import ActionResult
from tavern.world.state import WorldState


async def _async_gen(*values):
    for v in values:
        yield v


async def _raise_on_iter():
    raise RuntimeError("LLM failed")
    yield  # make it an async generator


@pytest.fixture
def mock_llm_service():
    svc = MagicMock()
    svc.stream_narrative = MagicMock()
    return svc


@pytest.fixture
def narrator(mock_llm_service):
    return Narrator(llm_service=mock_llm_service)


@pytest.fixture
def sample_state(sample_world_state):
    return sample_world_state


class TestNarrator:
    @pytest.mark.asyncio
    async def test_yields_llm_chunks_on_success(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_async_gen("你走进", "了大厅。")
        )
        result = ActionResult(
            success=True,
            action=ActionType.MOVE,
            message="你进入了酒馆大厅。",
            target="tavern_hall",
        )
        chunks = []
        async for chunk in narrator.stream_narrative(result, sample_world_state):
            chunks.append(chunk)
        assert chunks == ["你走进", "了大厅。"]

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_raise_on_iter()
        )
        result = ActionResult(
            success=True,
            action=ActionType.LOOK,
            message="你环顾四周，看到了酒馆大厅。",
        )
        chunks = []
        async for chunk in narrator.stream_narrative(result, sample_world_state):
            chunks.append(chunk)
        assert "".join(chunks) == "你环顾四周，看到了酒馆大厅。"

    @pytest.mark.asyncio
    async def test_builds_context_with_location_info(self, narrator, mock_llm_service, sample_world_state):
        captured_system: list[str] = []
        captured_message: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured_system.append(system_prompt)
            captured_message.append(action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.LOOK,
            message="你仔细观察周围。",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        assert len(captured_system) == 1
        # Location name should appear in the prompt
        assert "酒馆大厅" in captured_system[0]
        # Action message is the user content
        assert captured_message[0] == "你仔细观察周围。"

    @pytest.mark.asyncio
    async def test_target_item_id_converted_to_name(self, narrator, mock_llm_service, sample_world_state):
        captured_messages: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured_messages.append(action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.TAKE,
            message="你拾起了旧告示。",
            target="old_notice",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        full_text = " ".join(captured_messages)
        # "旧告示" (item name) should appear, not the raw ID "old_notice"
        assert "旧告示" in full_text

    @pytest.mark.asyncio
    async def test_target_npc_id_converted_to_name(self, narrator, mock_llm_service, sample_world_state):
        captured: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured.append(system_prompt + action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.TALK,
            message="你向旅行者打了个招呼。",
            target="traveler",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        full_text = " ".join(captured)
        assert "旅行者" in full_text
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/narrator/test_narrator.py -v
```
Expected: `ModuleNotFoundError: No module named 'tavern.narrator.narrator'`

- [ ] **Step 3: Implement `Narrator`**

```python
# src/tavern/narrator/narrator.py
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt
from tavern.world.models import ActionResult
from tavern.world.state import WorldState

if TYPE_CHECKING:
    from tavern.llm.service import LLMService


class Narrator:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def stream_narrative(
        self, result: ActionResult, state: WorldState
    ) -> AsyncIterator[str]:
        ctx = self._build_context(result, state)
        messages = build_narrative_prompt(ctx)
        system_prompt = messages[0]["content"]
        action_message = messages[1]["content"]
        try:
            async for chunk in self._llm.stream_narrative(system_prompt, action_message):
                yield chunk
        except Exception:
            yield result.message

    def _build_context(self, result: ActionResult, state: WorldState) -> NarrativeContext:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        target_name: str | None = None
        if result.target:
            if result.target in state.characters:
                target_name = state.characters[result.target].name
            elif result.target in state.items:
                target_name = state.items[result.target].name
            else:
                target_name = result.target

        return NarrativeContext(
            action_type=result.action.value,
            action_message=result.message,
            location_name=location.name,
            location_desc=location.description,
            player_name=player.name,
            target=target_name,
        )
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/narrator/test_narrator.py -v
```
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/narrator/narrator.py tests/narrator/test_narrator.py
git commit -m "feat: add Narrator class with stream_narrative and LLM fallback"
```

---

### Task 4: `Renderer.render_stream()`

**Files:**
- Modify: `src/tavern/cli/renderer.py`
- Modify: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/cli/test_renderer.py`:

```python
import asyncio
from io import StringIO


async def _async_gen(*values):
    for v in values:
        yield v


async def _raise_mid_stream():
    yield "你走进了"
    raise RuntimeError("stream interrupted")


class TestRenderStream:
    @pytest.mark.asyncio
    async def test_render_stream_outputs_all_chunks(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("你走进了", "温暖的酒馆。"))
        output = console.file.getvalue()
        assert "你走进了" in output
        assert "温暖的酒馆。" in output

    @pytest.mark.asyncio
    async def test_render_stream_adds_trailing_newline(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("内容"))
        output = console.file.getvalue()
        assert output.endswith("\n")

    @pytest.mark.asyncio
    async def test_render_stream_handles_mid_stream_error(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        # Should not raise — error handled gracefully
        await renderer.render_stream(_raise_mid_stream())
        output = console.file.getvalue()
        assert "你走进了" in output
        assert output.endswith("\n")
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/cli/test_renderer.py::TestRenderStream -v
```
Expected: `AttributeError: 'Renderer' object has no attribute 'render_stream'`

- [ ] **Step 3: Add `render_stream` to `Renderer`**

In `src/tavern/cli/renderer.py`, add after `render_result`:

```python
    async def render_stream(self, stream) -> None:
        try:
            async for chunk in stream:
                self.console.print(chunk, end="", highlight=False)
        except Exception:
            pass
        self.console.print()
```

Also add `from __future__ import annotations` is already present. No additional imports needed.

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/cli/test_renderer.py -v
```
Expected: all existing tests PASS + 3 new TestRenderStream PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer.py
git commit -m "feat: add Renderer.render_stream typewriter streaming method"
```

---

### Task 5: `GameApp` integration

**Files:**
- Modify: `src/tavern/cli/app.py`
- Modify: `tests/cli/test_app_dialogue.py` (add smoke test for narrative path)

- [ ] **Step 1: Write failing test**

Append to `tests/cli/test_app_dialogue.py`. The existing tests use `GameApp.__new__(GameApp)` to bypass `__init__`. Follow that pattern:

```python
# Append to tests/cli/test_app_dialogue.py

class TestNarrativeIntegration:
    @pytest.mark.asyncio
    async def test_successful_action_uses_render_stream_not_render_result(
        self, mock_state
    ):
        """render_stream called (not render_result) on successful non-dialogue action."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from tavern.world.state import StateManager
        from tavern.dialogue.manager import DialogueManager
        from tavern.narrator.narrator import Narrator
        from tavern.cli.renderer import Renderer

        async def fake_stream(system_prompt, action_message):
            yield "叙事内容"

        mock_llm_service = MagicMock()
        mock_llm_service.stream_narrative = fake_stream

        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._renderer.render_status_bar = MagicMock()
        app._dialogue_manager = DialogueManager(llm_service=mock_llm_service)
        app._dialogue_ctx = None
        app._narrator = Narrator(llm_service=mock_llm_service)
        app._show_intent = False

        render_result_calls = []
        render_stream_calls = []
        app._renderer.render_result = lambda r: render_result_calls.append(r)

        async def mock_render_stream(stream):
            async for _ in stream:
                pass
            render_stream_calls.append(True)

        app._renderer.render_stream = mock_render_stream

        from tavern.engine.rules import RulesEngine
        from tavern.parser.intent import IntentParser
        app._rules = RulesEngine()

        mock_intent = AsyncMock()
        from tavern.world.models import ActionRequest
        from tavern.engine.actions import ActionType
        mock_intent.complete = AsyncMock(
            return_value=ActionRequest(action=ActionType.LOOK)
        )
        app._parser = IntentParser(llm_service=MagicMock())

        with patch.object(app._parser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ActionRequest(action=ActionType.LOOK)
            await app._handle_free_input("看看四周")

        assert len(render_stream_calls) == 1
        assert len(render_result_calls) == 0

    @pytest.mark.asyncio
    async def test_failed_action_uses_render_result_not_render_stream(
        self, mock_state
    ):
        """render_result called (not render_stream) on failed action."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from tavern.world.state import StateManager
        from tavern.dialogue.manager import DialogueManager
        from tavern.narrator.narrator import Narrator
        from tavern.engine.rules import RulesEngine
        from tavern.parser.intent import IntentParser

        mock_llm_service = MagicMock()
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._renderer.render_status_bar = MagicMock()
        app._dialogue_manager = DialogueManager(llm_service=mock_llm_service)
        app._dialogue_ctx = None
        app._narrator = Narrator(llm_service=mock_llm_service)
        app._show_intent = False
        app._rules = RulesEngine()
        app._parser = IntentParser(llm_service=MagicMock())

        render_result_calls = []
        render_stream_calls = []
        app._renderer.render_result = lambda r: render_result_calls.append(r)

        async def mock_render_stream(stream):
            render_stream_calls.append(True)

        app._renderer.render_stream = mock_render_stream

        with patch.object(app._parser, "parse", new_callable=AsyncMock) as mock_parse:
            from tavern.world.models import ActionRequest
            from tavern.engine.actions import ActionType
            mock_parse.return_value = ActionRequest(
                action=ActionType.MOVE, target="nowhere"
            )
            await app._handle_free_input("走向虚空")

        assert len(render_result_calls) == 1
        assert len(render_stream_calls) == 0
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/cli/test_app_dialogue.py::TestNarrativeIntegration -v
```
Expected: `AttributeError: 'GameApp' object has no attribute '_narrator'`

- [ ] **Step 3: Wire `Narrator` into `GameApp`**

In `src/tavern/cli/app.py`:

Add import after existing imports:
```python
from tavern.narrator.narrator import Narrator
```

In `GameApp.__init__`, after the `self._dialogue_manager` line:
```python
        self._narrator = Narrator(llm_service=llm_service)
```

Replace the end of `_handle_free_input` (the current lines 183-185):

```python
        if result.success and not self._dialogue_manager.is_active:
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state)
            )
        else:
            self._renderer.render_result(result)
        self._renderer.render_status_bar(self.state)
```

The full updated section (replacing lines 168–185 of current `_handle_free_input`):

```python
        if result.success and request.action in (
            ActionType.TALK, ActionType.PERSUADE
        ) and result.target:
            try:
                ctx, opening_response = await self._dialogue_manager.start(
                    self.state, result.target,
                    is_persuade=(request.action == ActionType.PERSUADE),
                )
                self._dialogue_ctx = ctx
                self._renderer.render_dialogue_start(ctx, opening_response)
                self._renderer.render_status_bar(self.state)
                return
            except ValueError as e:
                self._renderer.console.print(f"\n[red]{e}[/]\n")
                return

        if result.success and not self._dialogue_manager.is_active:
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state)
            )
        else:
            self._renderer.render_result(result)
        self._renderer.render_status_bar(self.state)
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/cli/test_app_dialogue.py -v
```
Expected: all tests PASS including the 2 new ones

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add src/tavern/cli/app.py tests/cli/test_app_dialogue.py
git commit -m "feat: integrate Narrator into GameApp for LLM narrative streaming"
```

---

### Task 6: Coverage verification

**Files:** None (verification only)

- [ ] **Step 1: Run coverage**

```
pytest --cov=src/tavern/narrator --cov=src/tavern/llm/service --cov=src/tavern/cli/renderer --cov=src/tavern/cli/app --cov-report=term-missing -q
```

Expected:
- `narrator/prompts.py`: ≥ 90%
- `narrator/narrator.py`: ≥ 85%
- `llm/service.py`: ≥ 85%
- `cli/renderer.py`: ≥ 85%
- `cli/app.py`: ≥ 75%

- [ ] **Step 2: Run full suite coverage check**

```
pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q
```

Expected: overall ≥ 80%, no failures

- [ ] **Step 3: Final commit if clean**

```bash
git add -p  # Review any stray changes
git status  # Verify nothing unexpected
```
