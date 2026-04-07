# Phase 2a — NPC Dialogue System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-turn NPC dialogue system where relationship values (trust) dynamically influence NPC tone, with LLM-generated responses and post-dialogue summaries persisted to game state.

**Architecture:** New `src/tavern/dialogue/` module (context.py → prompts.py → manager.py) sits between the RulesEngine and GameApp. RulesEngine validates TALK/PERSUADE actions, GameApp routes conversation turns through DialogueManager which owns the dialogue lifecycle. WorldState is updated immutably on dialogue end via StateDiff.

**Tech Stack:** Python 3.12+, Pydantic v2 frozen models, existing LLMService/OpenAIAdapter infrastructure, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-07-npc-dialogue-system-design.md`

---

## File Map

| Operation | File | Responsibility |
|-----------|------|---------------|
| Create | `src/tavern/dialogue/__init__.py` | Package root |
| Create | `src/tavern/dialogue/context.py` | Frozen dataclasses: Message, DialogueContext, DialogueResponse, DialogueSummary |
| Create | `src/tavern/dialogue/prompts.py` | `resolve_tone()`, `build_dialogue_prompt()`, `build_summary_prompt()`, TONE_TEMPLATES |
| Create | `src/tavern/dialogue/manager.py` | DialogueManager: start / respond / end lifecycle |
| Modify | `src/tavern/llm/service.py` | Add `generate_dialogue()` and `generate_summary()` methods |
| Modify | `src/tavern/engine/rules.py` | Register `_handle_talk` for TALK and PERSUADE |
| Modify | `src/tavern/engine/actions.py` | Add TALK and PERSUADE to ActionType enum |
| Modify | `src/tavern/cli/renderer.py` | Add `render_dialogue_start()`, `render_dialogue()`, `render_dialogue_end()`, `get_dialogue_input()` |
| Modify | `src/tavern/cli/app.py` | Integrate DialogueManager; route dialogue turns in `run()` |
| Create | `tests/dialogue/__init__.py` | Test package |
| Create | `tests/dialogue/test_context.py` | Frozen model tests |
| Create | `tests/dialogue/test_prompts.py` | Tone resolution and prompt assembly tests |
| Create | `tests/dialogue/test_manager.py` | DialogueManager unit tests with mocked LLMService |
| Modify | `tests/engine/test_rules.py` | TALK/PERSUADE handler tests |
| Create | `tests/cli/test_app_dialogue.py` | Full dialogue flow integration tests |

---

## Task 1: Extend ActionType with TALK and PERSUADE

**Files:**
- Modify: `src/tavern/engine/actions.py`

- [ ] **Step 1: Read the current file**

```bash
cat src/tavern/engine/actions.py
```

- [ ] **Step 2: Add TALK and PERSUADE to the enum**

Open `src/tavern/engine/actions.py`. It currently has entries like `MOVE`, `LOOK`, `TAKE`, etc. Add two new entries:

```python
TALK = "talk"
PERSUADE = "persuade"
```

Place them after `SEARCH` and before `TRADE` (or at the end of the existing actions).

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
pytest tests/ -x -q
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/tavern/engine/actions.py
git commit -m "feat: add TALK and PERSUADE to ActionType"
```

---

## Task 2: Dialogue data models

**Files:**
- Create: `src/tavern/dialogue/__init__.py`
- Create: `src/tavern/dialogue/context.py`
- Create: `tests/dialogue/__init__.py`
- Create: `tests/dialogue/test_context.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dialogue/__init__.py` (empty) and `tests/dialogue/test_context.py`:

```python
import pytest
from tavern.dialogue.context import (
    DialogueContext,
    DialogueResponse,
    DialogueSummary,
    Message,
)


class TestMessage:
    def test_creation(self):
        msg = Message(role="player", content="你好", trust_delta=0, turn=1)
        assert msg.role == "player"
        assert msg.content == "你好"
        assert msg.trust_delta == 0
        assert msg.turn == 1

    def test_immutable(self):
        msg = Message(role="npc", content="...", trust_delta=2, turn=1)
        with pytest.raises(Exception):
            msg.content = "changed"  # type: ignore[misc]


class TestDialogueContext:
    def test_creation(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善",),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        assert ctx.npc_id == "traveler"
        assert ctx.tone == "neutral"
        assert ctx.messages == ()

    def test_immutable(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=(),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        with pytest.raises(Exception):
            ctx.trust = 99  # type: ignore[misc]


class TestDialogueResponse:
    def test_creation(self):
        resp = DialogueResponse(
            text="欢迎！", trust_delta=1, mood="friendly", wants_to_end=False
        )
        assert resp.text == "欢迎！"
        assert resp.trust_delta == 1
        assert not resp.wants_to_end

    def test_immutable(self):
        resp = DialogueResponse(text="...", trust_delta=0, mood="neutral", wants_to_end=False)
        with pytest.raises(Exception):
            resp.text = "changed"  # type: ignore[misc]


class TestDialogueSummary:
    def test_creation(self):
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="玩家与旅行者聊了旅行。",
            total_trust_delta=3,
            key_info=("旅行者来自北方",),
            turns_count=2,
        )
        assert summary.npc_id == "traveler"
        assert summary.total_trust_delta == 3
        assert len(summary.key_info) == 1

    def test_immutable(self):
        summary = DialogueSummary(
            npc_id="x", summary_text="x", total_trust_delta=0,
            key_info=(), turns_count=1,
        )
        with pytest.raises(Exception):
            summary.npc_id = "y"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dialogue/test_context.py -v
```

Expected: `ModuleNotFoundError: No module named 'tavern.dialogue'`

- [ ] **Step 3: Create the package and models**

Create `src/tavern/dialogue/__init__.py` (empty):

```python
```

Create `src/tavern/dialogue/context.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    role: str           # "player" | "npc"
    content: str
    trust_delta: int    # delta for this turn (player messages are always 0)
    turn: int


@dataclass(frozen=True)
class DialogueContext:
    npc_id: str
    npc_name: str
    npc_traits: tuple[str, ...]
    trust: int
    tone: str           # "hostile" | "neutral" | "friendly"
    messages: tuple[Message, ...]
    location_id: str
    turn_entered: int


@dataclass(frozen=True)
class DialogueResponse:
    text: str
    trust_delta: int
    mood: str
    wants_to_end: bool


@dataclass(frozen=True)
class DialogueSummary:
    npc_id: str
    summary_text: str
    total_trust_delta: int
    key_info: tuple[str, ...]
    turns_count: int
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dialogue/test_context.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/dialogue/ tests/dialogue/
git commit -m "feat: add dialogue data models (Message, DialogueContext, DialogueResponse, DialogueSummary)"
```

---

## Task 3: Prompt assembly

**Files:**
- Create: `src/tavern/dialogue/prompts.py`
- Create: `tests/dialogue/test_prompts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dialogue/test_prompts.py`:

```python
from tavern.dialogue.prompts import TONE_TEMPLATES, build_dialogue_prompt, resolve_tone
from tavern.dialogue.context import DialogueContext


class TestResolveTone:
    def test_hostile_threshold(self):
        assert resolve_tone(-20) == "hostile"
        assert resolve_tone(-100) == "hostile"

    def test_neutral_range(self):
        assert resolve_tone(-19) == "neutral"
        assert resolve_tone(0) == "neutral"
        assert resolve_tone(19) == "neutral"

    def test_friendly_threshold(self):
        assert resolve_tone(20) == "friendly"
        assert resolve_tone(100) == "friendly"


class TestToneTemplates:
    def test_all_tones_defined(self):
        assert "hostile" in TONE_TEMPLATES
        assert "neutral" in TONE_TEMPLATES
        assert "friendly" in TONE_TEMPLATES

    def test_templates_are_non_empty_strings(self):
        for tone, template in TONE_TEMPLATES.items():
            assert isinstance(template, str)
            assert len(template) > 10, f"Tone template for '{tone}' is too short"


class TestBuildDialoguePrompt:
    def test_prompt_contains_npc_name(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善", "健谈"),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        location_name = "酒馆大厅"
        prompt = build_dialogue_prompt(ctx, location_name, history_summaries=())
        assert "旅行者" in prompt

    def test_prompt_contains_tone_instruction(self):
        ctx = DialogueContext(
            npc_id="bartender",
            npc_name="格里姆",
            npc_traits=("沉默",),
            trust=-30,
            tone="hostile",
            messages=(),
            location_id="bar_area",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "吧台区", history_summaries=())
        assert TONE_TEMPLATES["hostile"] in prompt

    def test_prompt_contains_json_format(self):
        ctx = DialogueContext(
            npc_id="npc1",
            npc_name="NPC",
            npc_traits=(),
            trust=0,
            tone="neutral",
            messages=(),
            location_id="loc1",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "某地", history_summaries=())
        assert "trust_delta" in prompt
        assert "wants_to_end" in prompt

    def test_prompt_includes_history_summary(self):
        ctx = DialogueContext(
            npc_id="npc1",
            npc_name="NPC",
            npc_traits=(),
            trust=5,
            tone="neutral",
            messages=(),
            location_id="loc1",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(
            ctx, "某地", history_summaries=("上次聊到了宝藏",)
        )
        assert "上次聊到了宝藏" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dialogue/test_prompts.py -v
```

Expected: `ModuleNotFoundError: No module named 'tavern.dialogue.prompts'`

- [ ] **Step 3: Implement prompts module**

Create `src/tavern/dialogue/prompts.py`:

```python
from __future__ import annotations

from tavern.dialogue.context import DialogueContext

TONE_TEMPLATES: dict[str, str] = {
    "hostile": (
        "你对玩家持有敌意或强烈不信任。回答简短冷淡，不主动提供任何信息。"
        "若玩家继续骚扰，你会明确表示想结束对话。"
    ),
    "neutral": (
        "你对玩家态度中立。回答基本问题，但不会主动分享秘密或隐私。"
        "保持礼貌但有距离感。"
    ),
    "friendly": (
        "你对玩家非常友好，热情健谈。愿意分享你知道的信息，包括秘密和线索。"
        "乐于帮助玩家。"
    ),
}


def resolve_tone(trust: int) -> str:
    if trust <= -20:
        return "hostile"
    if trust >= 20:
        return "friendly"
    return "neutral"


def build_dialogue_prompt(
    ctx: DialogueContext,
    location_name: str,
    history_summaries: tuple[str, ...],
) -> str:
    traits_desc = "、".join(ctx.npc_traits) if ctx.npc_traits else "普通人"
    tone_instruction = TONE_TEMPLATES[ctx.tone]

    trust_label = (
        "非常不信任" if ctx.trust <= -20
        else "友好" if ctx.trust >= 20
        else "中立"
    )

    history_section = ""
    if history_summaries:
        history_lines = "\n".join(f"- {s}" for s in history_summaries)
        history_section = f"\n\n【历史对话记录】\n{history_lines}"

    return (
        f"你扮演角色：{ctx.npc_name}\n"
        f"性格特征：{traits_desc}\n"
        f"当前地点：{location_name}\n\n"
        f"【语气指令】\n{tone_instruction}\n\n"
        f"【关系状态】\n"
        f"当前信任值：{ctx.trust}（{trust_label}）"
        f"{history_section}\n\n"
        "【回复格式】\n"
        "必须以JSON格式回复，字段：\n"
        '- "text": 你的回复内容（2-4句话）\n'
        '- "trust_delta": 本轮关系变化，整数，范围 [-5, +5]。'
        "玩家友好、提供有用信息时为正；无理、骚扰时为负；普通对话为0\n"
        '- "mood": 你当前情绪，如 "平静"、"警惕"、"开心"、"不耐烦"\n'
        '- "wants_to_end": 布尔值，当你想结束对话时为 true（玩家反复骚扰、超出话题范围等）\n\n'
        "保持角色一致性，不要脱离角色。"
    )


def build_summary_prompt(npc_name: str, messages: list[dict]) -> str:
    dialogue_text = "\n".join(
        f"{'玩家' if m['role'] == 'user' else npc_name}: {m['content']}"
        for m in messages
        if m["role"] in ("user", "assistant")
    )
    return (
        f"以下是玩家与{npc_name}的对话记录：\n\n{dialogue_text}\n\n"
        "请用1-2句话总结关键信息，重点记录：\n"
        "- 玩家获得的重要线索\n"
        "- NPC透露的秘密\n"
        "- 关系变化的关键转折点\n\n"
        "同时提取关键信息点。\n\n"
        "以JSON格式回复：\n"
        '{"summary": "摘要文本", "key_info": ["信息点1", "信息点2"]}'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dialogue/test_prompts.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/dialogue/prompts.py tests/dialogue/test_prompts.py
git commit -m "feat: add dialogue prompt assembly (resolve_tone, build_dialogue_prompt)"
```

---

## Task 4: Extend LLMService with dialogue methods

**Files:**
- Modify: `src/tavern/llm/service.py`
- Modify: `tests/llm/test_adapter.py` (or create `tests/llm/test_service_dialogue.py`)

- [ ] **Step 1: Write failing tests**

Create `tests/llm/test_service_dialogue.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.dialogue.context import DialogueResponse, DialogueSummary
from tavern.llm.service import LLMService


@pytest.fixture
def mock_intent_adapter():
    return AsyncMock()


@pytest.fixture
def mock_narrative_adapter():
    return AsyncMock()


@pytest.fixture
def llm_service(mock_intent_adapter, mock_narrative_adapter):
    return LLMService(
        intent_adapter=mock_intent_adapter,
        narrative_adapter=mock_narrative_adapter,
    )


class TestGenerateDialogue:
    @pytest.mark.asyncio
    async def test_returns_dialogue_response(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "你好，冒险者。", "trust_delta": 1, "mood": "平静", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[{"role": "user", "content": "你好"}],
        )
        assert isinstance(result, DialogueResponse)
        assert result.text == "你好，冒险者。"
        assert result.trust_delta == 1
        assert result.mood == "平静"
        assert result.wants_to_end is False

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(return_value="不是JSON")
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[{"role": "user", "content": "你好"}],
        )
        assert isinstance(result, DialogueResponse)
        assert result.trust_delta == 0
        assert result.wants_to_end is False

    @pytest.mark.asyncio
    async def test_clamps_trust_delta(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "...", "trust_delta": 99, "mood": "x", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[],
        )
        assert result.trust_delta == 5

    @pytest.mark.asyncio
    async def test_clamps_negative_trust_delta(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "...", "trust_delta": -99, "mood": "x", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[],
        )
        assert result.trust_delta == -5


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_returns_summary_dict(self, llm_service, mock_intent_adapter):
        mock_intent_adapter.complete = AsyncMock(
            return_value='{"summary": "旅行者分享了北方的传说。", "key_info": ["北方有宝藏"]}'
        )
        result = await llm_service.generate_summary(
            dialogue_messages=[{"role": "user", "content": "聊天内容"}],
            summary_prompt="请总结",
        )
        assert result["summary"] == "旅行者分享了北方的传说。"
        assert "北方有宝藏" in result["key_info"]

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, llm_service, mock_intent_adapter):
        mock_intent_adapter.complete = AsyncMock(return_value="不是JSON")
        result = await llm_service.generate_summary(
            dialogue_messages=[],
            summary_prompt="请总结",
        )
        assert "summary" in result
        assert "key_info" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/llm/test_service_dialogue.py -v
```

Expected: `AttributeError: 'LLMService' object has no attribute 'generate_dialogue'`

- [ ] **Step 3: Implement the two new methods in LLMService**

Open `src/tavern/llm/service.py` and add after the existing `classify_intent` method:

```python
import json
from tavern.dialogue.context import DialogueResponse


    async def generate_dialogue(
        self,
        system_prompt: str,
        messages: list[dict],
    ) -> DialogueResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        raw = await self._narrative.complete(full_messages)
        try:
            data = json.loads(raw if isinstance(raw, str) else str(raw))
            trust_delta = max(-5, min(5, int(data.get("trust_delta", 0))))
            return DialogueResponse(
                text=str(data.get("text", "...沉默不语")),
                trust_delta=trust_delta,
                mood=str(data.get("mood", "neutral")),
                wants_to_end=bool(data.get("wants_to_end", False)),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return DialogueResponse(
                text="...沉默不语",
                trust_delta=0,
                mood="neutral",
                wants_to_end=False,
            )

    async def generate_summary(
        self,
        dialogue_messages: list[dict],
        summary_prompt: str,
    ) -> dict:
        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": "请生成摘要。"},
        ]
        raw = await self._intent.complete(messages)
        try:
            return json.loads(raw if isinstance(raw, str) else str(raw))
        except (json.JSONDecodeError, ValueError):
            return {"summary": f"进行了一段对话", "key_info": []}
```

Also add `import json` at the top of `service.py` if not already present.

**Important:** The `from tavern.dialogue.context import DialogueResponse` import must be added at the top of `service.py`, not inside the method. The full updated top of `service.py` looks like:

```python
from __future__ import annotations

import json

from tavern.dialogue.context import DialogueResponse
from tavern.llm.adapter import LLMAdapter
from tavern.world.models import ActionRequest
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/llm/test_service_dialogue.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Run all tests to confirm nothing regressed**

```bash
pytest tests/ -x -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/tavern/llm/service.py tests/llm/test_service_dialogue.py
git commit -m "feat: add generate_dialogue and generate_summary to LLMService"
```

---

## Task 5: DialogueManager

**Files:**
- Create: `src/tavern/dialogue/manager.py`
- Create: `tests/dialogue/test_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dialogue/test_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary, Message
from tavern.dialogue.manager import DialogueManager
from tavern.world.models import Character, CharacterRole, Location, Exit
from tavern.world.state import WorldState


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.generate_dialogue = AsyncMock(
        return_value=DialogueResponse(
            text="欢迎，冒险者！",
            trust_delta=1,
            mood="平静",
            wants_to_end=False,
        )
    )
    service.generate_summary = AsyncMock(
        return_value={"summary": "进行了友好交谈。", "key_info": ["旅行者来自北方"]}
    )
    return service


@pytest.fixture
def sample_state():
    return WorldState(
        turn=5,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            )
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="tavern_hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者",
                role=CharacterRole.NPC,
                traits=("友善", "健谈"),
                stats={"trust": 10},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


class TestDialogueManagerStart:
    @pytest.mark.asyncio
    async def test_start_returns_context_and_response(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, response = await manager.start(sample_state, "traveler")
        assert ctx.npc_id == "traveler"
        assert ctx.npc_name == "旅行者"
        assert ctx.trust == 10
        assert ctx.tone == "neutral"
        assert isinstance(response, DialogueResponse)

    @pytest.mark.asyncio
    async def test_start_sets_is_active(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        assert not manager.is_active
        await manager.start(sample_state, "traveler")
        assert manager.is_active

    @pytest.mark.asyncio
    async def test_start_npc_not_in_location_raises(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        with pytest.raises(ValueError, match="不在"):
            await manager.start(sample_state, "bartender_grim")

    @pytest.mark.asyncio
    async def test_start_unknown_npc_raises(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        with pytest.raises(ValueError):
            await manager.start(sample_state, "nonexistent_npc")


class TestDialogueManagerRespond:
    @pytest.mark.asyncio
    async def test_respond_appends_messages(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        new_ctx, response = await manager.respond(ctx, "你好", sample_state)
        assert len(new_ctx.messages) == 2  # opening NPC message + player message (NPC response added)
        assert isinstance(response, DialogueResponse)

    @pytest.mark.asyncio
    async def test_respond_updates_trust(self, mock_llm_service, sample_state):
        mock_llm_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(text="好的", trust_delta=3, mood="开心", wants_to_end=False)
        )
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        new_ctx, _ = await manager.respond(ctx, "我来帮助你", sample_state)
        assert new_ctx.trust == ctx.trust + 3

    @pytest.mark.asyncio
    async def test_respond_enforces_20_turn_limit(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        # Manually craft a context with 20 messages
        messages = tuple(
            Message(role="player", content=f"msg{i}", trust_delta=0, turn=i)
            for i in range(20)
        )
        ctx_full = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust,
            tone=ctx.tone,
            messages=messages,
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )
        _, response = await manager.respond(ctx_full, "还有吗", sample_state)
        assert response.wants_to_end is True


class TestDialogueManagerEnd:
    @pytest.mark.asyncio
    async def test_end_returns_summary(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, opening = await manager.start(sample_state, "traveler")
        ctx_with_msg = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust,
            tone=ctx.tone,
            messages=(
                Message(role="npc", content=opening.text, trust_delta=opening.trust_delta, turn=5),
                Message(role="player", content="你好", trust_delta=0, turn=5),
            ),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )
        summary = await manager.end(ctx_with_msg)
        assert isinstance(summary, DialogueSummary)
        assert summary.npc_id == "traveler"
        assert summary.summary_text == "进行了友好交谈。"

    @pytest.mark.asyncio
    async def test_end_clears_active(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        assert manager.is_active
        await manager.end(ctx)
        assert not manager.is_active

    @pytest.mark.asyncio
    async def test_end_calculates_total_trust_delta(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        ctx_with_messages = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust,
            tone=ctx.tone,
            messages=(
                Message(role="npc", content="嗨", trust_delta=2, turn=5),
                Message(role="player", content="你好", trust_delta=0, turn=5),
                Message(role="npc", content="很好", trust_delta=3, turn=5),
            ),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )
        summary = await manager.end(ctx_with_messages)
        assert summary.total_trust_delta == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dialogue/test_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'tavern.dialogue.manager'`

- [ ] **Step 3: Implement DialogueManager**

Create `src/tavern/dialogue/manager.py`:

```python
from __future__ import annotations

from tavern.dialogue.context import (
    DialogueContext,
    DialogueResponse,
    DialogueSummary,
    Message,
)
from tavern.dialogue.prompts import build_dialogue_prompt, build_summary_prompt, resolve_tone
from tavern.llm.service import LLMService
from tavern.world.state import WorldState

MAX_TURNS = 20


class DialogueManager:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service
        self._active: DialogueContext | None = None

    @property
    def is_active(self) -> bool:
        return self._active is not None

    async def start(
        self, state: WorldState, npc_id: str
    ) -> tuple[DialogueContext, DialogueResponse]:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        if npc_id not in state.characters:
            raise ValueError(f"未知角色: {npc_id}")
        if npc_id not in location.npcs:
            raise ValueError(f"{npc_id} 不在当前地点")

        npc = state.characters[npc_id]
        trust = int(npc.stats.get("trust", 0))
        tone = resolve_tone(trust)

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == npc_id
        )

        ctx = DialogueContext(
            npc_id=npc_id,
            npc_name=npc.name,
            npc_traits=npc.traits,
            trust=trust,
            tone=tone,
            messages=(),
            location_id=player.location_id,
            turn_entered=state.turn,
        )

        system_prompt = build_dialogue_prompt(ctx, location.name, history_summaries)
        response = await self._llm.generate_dialogue(system_prompt, messages=[])

        opening_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust + response.trust_delta,
            tone=resolve_tone(ctx.trust + response.trust_delta),
            messages=(opening_msg,),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = ctx
        return ctx, response

    async def respond(
        self, ctx: DialogueContext, player_input: str, state: WorldState
    ) -> tuple[DialogueContext, DialogueResponse]:
        if len(ctx.messages) >= MAX_TURNS:
            response = DialogueResponse(
                text="我觉得我们已经聊了很多了，请让我休息一下。",
                trust_delta=0,
                mood="疲惫",
                wants_to_end=True,
            )
            return ctx, response

        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == ctx.npc_id
        )

        system_prompt = build_dialogue_prompt(ctx, location.name, history_summaries)

        llm_messages = [
            {
                "role": "user" if m.role == "player" else "assistant",
                "content": m.content,
            }
            for m in ctx.messages
        ]
        llm_messages.append({"role": "user", "content": player_input})

        response = await self._llm.generate_dialogue(system_prompt, llm_messages)

        player_msg = Message(
            role="player", content=player_input, trust_delta=0, turn=state.turn
        )
        npc_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        new_trust = ctx.trust + response.trust_delta
        new_ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=new_trust,
            tone=resolve_tone(new_trust),
            messages=ctx.messages + (player_msg, npc_msg),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = new_ctx
        return new_ctx, response

    async def end(self, ctx: DialogueContext) -> DialogueSummary:
        llm_messages = [
            {
                "role": "user" if m.role == "player" else "assistant",
                "content": m.content,
            }
            for m in ctx.messages
        ]

        summary_prompt = build_summary_prompt(ctx.npc_name, llm_messages)
        summary_data = await self._llm.generate_summary(llm_messages, summary_prompt)

        total_trust_delta = sum(m.trust_delta for m in ctx.messages)

        self._active = None
        return DialogueSummary(
            npc_id=ctx.npc_id,
            summary_text=summary_data.get("summary", f"与{ctx.npc_name}进行了对话"),
            total_trust_delta=total_trust_delta,
            key_info=tuple(summary_data.get("key_info", [])),
            turns_count=len(ctx.messages),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dialogue/test_manager.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/dialogue/manager.py tests/dialogue/test_manager.py
git commit -m "feat: implement DialogueManager (start/respond/end lifecycle)"
```

---

## Task 6: RulesEngine TALK/PERSUADE handlers

**Files:**
- Modify: `src/tavern/engine/rules.py`
- Modify: `tests/engine/test_rules.py`

- [ ] **Step 1: Write failing tests**

Open `tests/engine/test_rules.py` and add a new class after the existing test classes:

```python
class TestTalkAction:
    def test_talk_npc_in_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TALK, target="traveler")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert result.target == "traveler"
        assert diff is None

    def test_talk_npc_not_in_location(self, rules_engine, sample_world_state):
        # bartender_grim is in bar_area, not tavern_hall
        request = ActionRequest(action=ActionType.TALK, target="bartender_grim")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_talk_nonexistent_target(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TALK, target="ghost")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_persuade_npc_in_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.PERSUADE, target="traveler")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert result.target == "traveler"
        assert diff is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/engine/test_rules.py::TestTalkAction -v
```

Expected: FAIL — `ActionType.TALK` may not exist yet or handler not registered. (If Task 1 is done, it exists; handler is not registered yet.)

- [ ] **Step 3: Implement TALK/PERSUADE handlers in rules.py**

Open `src/tavern/engine/rules.py`. Add two handler functions before `_handle_custom`:

```python
def _handle_talk(request: ActionRequest, state: WorldState):
    target_id = request.target
    if target_id is None:
        return (
            ActionResult(
                success=False, action=ActionType.TALK, message="你想和谁说话？"
            ),
            None,
        )

    if target_id not in state.characters:
        return (
            ActionResult(
                success=False,
                action=ActionType.TALK,
                message=f"这里没有叫「{target_id}」的人。",
                target=target_id,
            ),
            None,
        )

    location = _get_player_location(state)
    if target_id not in location.npcs:
        npc_name = state.characters[target_id].name
        return (
            ActionResult(
                success=False,
                action=ActionType.TALK,
                message=f"{npc_name}不在这里。",
                target=target_id,
            ),
            None,
        )

    npc_name = state.characters[target_id].name
    return (
        ActionResult(
            success=True,
            action=ActionType.TALK,
            message=f"你走向{npc_name}，准备交谈。",
            target=target_id,
        ),
        None,
    )
```

Then register in `_ACTION_HANDLERS` at the bottom of the file:

```python
_ACTION_HANDLERS = {
    ActionType.MOVE: _handle_move,
    ActionType.LOOK: _handle_look,
    ActionType.SEARCH: _handle_look,
    ActionType.TAKE: _handle_take,
    ActionType.TALK: _handle_talk,
    ActionType.PERSUADE: _handle_talk,   # reuses same validation logic
    ActionType.CUSTOM: _handle_custom,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/engine/test_rules.py -v
```

Expected: all tests including the new `TestTalkAction` PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/rules.py tests/engine/test_rules.py
git commit -m "feat: add TALK/PERSUADE handlers to RulesEngine"
```

---

## Task 7: Renderer dialogue methods

**Files:**
- Modify: `src/tavern/cli/renderer.py`
- Modify: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests**

Open `tests/cli/test_renderer.py` and append:

```python
from io import StringIO
from rich.console import Console
from tavern.cli.renderer import Renderer
from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary


@pytest.fixture
def renderer_with_capture():
    console = Console(file=StringIO(), width=80)
    return Renderer(console=console), console


class TestDialogueRenderer:
    def test_render_dialogue_start_outputs_npc_name(self, renderer_with_capture):
        renderer, console = renderer_with_capture
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善",),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        response = DialogueResponse(text="你好！", trust_delta=1, mood="平静", wants_to_end=False)
        renderer.render_dialogue_start(ctx, response)
        output = console.file.getvalue()
        assert "旅行者" in output

    def test_render_dialogue_shows_trust_delta(self, renderer_with_capture):
        renderer, console = renderer_with_capture
        response = DialogueResponse(text="很高兴认识你", trust_delta=2, mood="开心", wants_to_end=False)
        renderer.render_dialogue(response)
        output = console.file.getvalue()
        assert "+2" in output or "2" in output

    def test_render_dialogue_end_shows_summary(self, renderer_with_capture):
        renderer, console = renderer_with_capture
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="旅行者分享了北方的传说。",
            total_trust_delta=5,
            key_info=("北方有宝藏",),
            turns_count=3,
        )
        renderer.render_dialogue_end(summary)
        output = console.file.getvalue()
        assert "旅行者分享了北方的传说" in output

    def test_get_dialogue_input_prompt(self, renderer_with_capture):
        renderer, console = renderer_with_capture
        # get_dialogue_input uses input() internally; just verify it exists
        assert callable(renderer.get_dialogue_input)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_renderer.py::TestDialogueRenderer -v
```

Expected: `AttributeError: 'Renderer' object has no attribute 'render_dialogue_start'`

- [ ] **Step 3: Add dialogue methods to Renderer**

Open `src/tavern/cli/renderer.py`. Add the following imports at the top:

```python
from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
```

Then add these methods to the `Renderer` class after `render_help`:

```python
    def render_dialogue_start(
        self, ctx: DialogueContext, response: DialogueResponse
    ) -> None:
        tone_label = {"hostile": "敌意", "neutral": "中立", "friendly": "友好"}.get(
            ctx.tone, ctx.tone
        )
        self.console.print(
            Panel(
                f"[bold]{ctx.npc_name}[/] — 关系：{ctx.trust} ({tone_label})\n\n"
                f"{response.text}\n\n"
                "[dim]输入 bye / 再见 退出对话[/]",
                title=f"💬 {ctx.npc_name}",
                border_style="cyan",
            )
        )

    def render_dialogue(self, response: DialogueResponse) -> None:
        delta = response.trust_delta
        if delta > 0:
            delta_str = f"[green]+{delta}[/]"
        elif delta < 0:
            delta_str = f"[red]{delta}[/]"
        else:
            delta_str = "[dim]±0[/]"

        self.console.print(
            Panel(
                f"{response.text}\n\n"
                f"[dim]情绪: {response.mood}  关系变化: {delta_str}[/]",
                border_style="cyan",
            )
        )

    def render_dialogue_end(self, summary: DialogueSummary) -> None:
        delta = summary.total_trust_delta
        delta_str = f"+{delta}" if delta >= 0 else str(delta)
        key_info_text = (
            "\n".join(f"  • {info}" for info in summary.key_info)
            if summary.key_info
            else "  （无特别收获）"
        )
        self.console.print(
            Panel(
                f"[bold]对话结束[/]\n\n"
                f"{summary.summary_text}\n\n"
                f"关键信息:\n{key_info_text}\n\n"
                f"[dim]共 {summary.turns_count} 轮  |  关系变化: {delta_str}[/]",
                border_style="dim",
            )
        )

    def get_dialogue_input(self) -> str:
        try:
            return self.console.input("[bold cyan]对话▸[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            return "bye"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_renderer.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer.py
git commit -m "feat: add dialogue rendering methods to Renderer"
```

---

## Task 8: GameApp integration

**Files:**
- Modify: `src/tavern/cli/app.py`
- Create: `tests/cli/test_app_dialogue.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cli/test_app_dialogue.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.world.models import Character, CharacterRole, Location, Item, Event
from tavern.world.state import WorldState, StateManager


@pytest.fixture
def mock_state():
    return WorldState(
        turn=5,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            )
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="tavern_hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者",
                role=CharacterRole.NPC,
                traits=("友善",),
                stats={"trust": 10},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


@pytest.fixture
def mock_dialogue_ctx(mock_state):
    return DialogueContext(
        npc_id="traveler",
        npc_name="旅行者",
        npc_traits=("友善",),
        trust=10,
        tone="neutral",
        messages=(),
        location_id="tavern_hall",
        turn_entered=5,
    )


@pytest.fixture
def mock_dialogue_response():
    return DialogueResponse(text="你好！", trust_delta=1, mood="平静", wants_to_end=False)


@pytest.fixture
def mock_summary():
    return DialogueSummary(
        npc_id="traveler",
        summary_text="进行了友好交谈。",
        total_trust_delta=3,
        key_info=("旅行者来自北方",),
        turns_count=2,
    )


class TestGameAppDialogueFlow:
    """Tests for GameApp._process_dialogue_input and _apply_dialogue_end."""

    def test_apply_dialogue_end_updates_trust(
        self, mock_state, mock_summary
    ):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()

        app._apply_dialogue_end(mock_summary)

        new_state = state_manager.current
        new_trust = new_state.characters["traveler"].stats["trust"]
        assert new_trust == 10 + 3  # original trust + total_trust_delta

    def test_apply_dialogue_end_writes_summary_event(
        self, mock_state, mock_summary
    ):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()

        app._apply_dialogue_end(mock_summary)

        new_state = state_manager.current
        dialogue_events = [
            e for e in new_state.timeline if e.type == "dialogue_summary"
        ]
        assert len(dialogue_events) == 1
        assert dialogue_events[0].actor == "traveler"
        assert "进行了友好交谈" in dialogue_events[0].description

    @pytest.mark.asyncio
    async def test_process_dialogue_input_bye_ends_dialogue(
        self, mock_state, mock_dialogue_ctx, mock_summary
    ):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = AsyncMock()
        mock_dialogue_manager.end = AsyncMock(return_value=mock_summary)

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._dialogue_ctx = mock_dialogue_ctx

        await app._process_dialogue_input("bye", mock_dialogue_ctx)

        mock_dialogue_manager.end.assert_called_once_with(mock_dialogue_ctx)

    @pytest.mark.asyncio
    async def test_process_dialogue_input_normal_calls_respond(
        self, mock_state, mock_dialogue_ctx, mock_dialogue_response
    ):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = AsyncMock()
        new_ctx = mock_dialogue_ctx
        mock_dialogue_manager.respond = AsyncMock(
            return_value=(new_ctx, mock_dialogue_response)
        )

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._dialogue_ctx = mock_dialogue_ctx

        await app._process_dialogue_input("你好", mock_dialogue_ctx)

        mock_dialogue_manager.respond.assert_called_once_with(
            mock_dialogue_ctx, "你好", mock_state
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_app_dialogue.py -v
```

Expected: import errors or `AttributeError` since the methods don't exist yet.

- [ ] **Step 3: Integrate DialogueManager into GameApp**

Open `src/tavern/cli/app.py`. Make these changes:

**3a. Add imports at the top** (after the existing imports):

```python
from tavern.dialogue.manager import DialogueManager
from tavern.dialogue.context import DialogueContext
```

**3b. In `GameApp.__init__`, instantiate DialogueManager** (add after `self._parser = IntentParser(...)`):

```python
        self._dialogue_manager = DialogueManager(llm_service=llm_service)
        self._dialogue_ctx: DialogueContext | None = None
```

**3c. Replace the `run` method body** with this updated version that routes to dialogue input when active:

```python
    async def run(self) -> None:
        self._renderer.render_welcome(self.state)
        self._renderer.render_status_bar(self.state)

        while True:
            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                user_input = self._renderer.get_dialogue_input()
            else:
                user_input = self._renderer.get_input()

            if not user_input:
                continue

            command = user_input.lower().strip()

            if command == "quit":
                self._renderer.console.print("\n[dim]再见，冒险者。[/]\n")
                break

            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                await self._process_dialogue_input(user_input, self._dialogue_ctx)
                continue

            if command in SYSTEM_COMMANDS:
                self._handle_system_command(command)
                continue

            await self._handle_free_input(user_input)
```

**3d. Add `_process_dialogue_input` method**:

```python
    async def _process_dialogue_input(
        self, user_input: str, ctx: DialogueContext
    ) -> None:
        bye_phrases = {"bye", "leave", "再见", "离开", "结束对话"}
        if user_input.lower().strip() in bye_phrases:
            summary = await self._dialogue_manager.end(ctx)
            self._dialogue_ctx = None
            self._renderer.render_dialogue_end(summary)
            self._apply_dialogue_end(summary)
            self._renderer.render_status_bar(self.state)
            return

        new_ctx, response = await self._dialogue_manager.respond(
            ctx, user_input, self.state
        )
        self._dialogue_ctx = new_ctx
        self._renderer.render_dialogue(response)

        if response.wants_to_end:
            summary = await self._dialogue_manager.end(new_ctx)
            self._dialogue_ctx = None
            self._renderer.render_dialogue_end(summary)
            self._apply_dialogue_end(summary)
            self._renderer.render_status_bar(self.state)
```

**3e. Add `_apply_dialogue_end` method**:

```python
    def _apply_dialogue_end(self, summary) -> None:
        import uuid
        from tavern.world.models import Event
        from tavern.world.state import StateDiff

        state = self.state
        npc = state.characters.get(summary.npc_id)
        if npc is not None:
            old_trust = int(npc.stats.get("trust", 0))
            new_trust = max(-100, min(100, old_trust + summary.total_trust_delta))
            new_stats = {**dict(npc.stats), "trust": new_trust}
            trust_diff = StateDiff(
                updated_characters={summary.npc_id: {"stats": new_stats}},
                turn_increment=0,
            )
            from tavern.world.models import ActionResult
            from tavern.engine.actions import ActionType
            self._state_manager.commit(
                trust_diff,
                ActionResult(
                    success=True,
                    action=ActionType.TALK,
                    message=f"与{npc.name}的对话结束",
                    target=summary.npc_id,
                ),
            )

        event = Event(
            id=f"dialogue_{summary.npc_id}_{uuid.uuid4().hex[:8]}",
            turn=self.state.turn,
            type="dialogue_summary",
            actor=summary.npc_id,
            description=summary.summary_text,
            consequences=summary.key_info,
        )
        event_diff = StateDiff(new_events=(event,), turn_increment=0)
        from tavern.world.models import ActionResult
        from tavern.engine.actions import ActionType
        self._state_manager.commit(
            event_diff,
            ActionResult(
                success=True,
                action=ActionType.TALK,
                message="对话摘要已记录",
                target=summary.npc_id,
            ),
        )
```

**3f. Update `_handle_free_input`** to start dialogue when TALK/PERSUADE action succeeds:

```python
    async def _handle_free_input(self, user_input: str) -> None:
        player = self.state.characters[self.state.player_id]
        location = self.state.locations[player.location_id]

        request = await self._parser.parse(
            user_input,
            location_id=player.location_id,
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
        )

        if self._show_intent:
            self._renderer.console.print(
                f"[dim]Intent: {request.model_dump_json()}[/]"
            )

        result, diff = self._rules.validate(request, self.state)

        if diff is not None:
            self._state_manager.commit(diff, result)

        if result.success and request.action in (
            ActionType.TALK, ActionType.PERSUADE
        ) and result.target:
            try:
                ctx, opening_response = await self._dialogue_manager.start(
                    self.state, result.target
                )
                self._dialogue_ctx = ctx
                self._renderer.render_dialogue_start(ctx, opening_response)
                self._renderer.render_status_bar(self.state)
                return
            except ValueError as e:
                self._renderer.console.print(f"\n[red]{e}[/]\n")
                return

        self._renderer.render_result(result)
        self._renderer.render_status_bar(self.state)
```

Make sure `ActionType` is imported at the top of `app.py` — it already is via `from tavern.engine.actions import ActionType`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_app_dialogue.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -x -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/tavern/cli/app.py tests/cli/test_app_dialogue.py
git commit -m "feat: integrate DialogueManager into GameApp (full dialogue flow)"
```

---

## Task 9: Integration test for dialogue E2E

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Read current integration tests**

```bash
cat tests/test_integration.py
```

- [ ] **Step 2: Write failing integration test**

Add to `tests/test_integration.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.dialogue.context import DialogueResponse, DialogueSummary
from tavern.dialogue.manager import DialogueManager
from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState, StateManager, StateDiff


@pytest.fixture
def dialogue_world_state():
    return WorldState(
        turn=1,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            )
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="tavern_hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者",
                role=CharacterRole.NPC,
                traits=("友善",),
                stats={"trust": 5},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


class TestDialogueE2E:
    @pytest.mark.asyncio
    async def test_full_dialogue_lifecycle(self, dialogue_world_state):
        """Start → 2 turns → end. Verify summary has correct trust delta."""
        mock_service = MagicMock()
        mock_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(
                text="你好，旅行者！",
                trust_delta=2,
                mood="开心",
                wants_to_end=False,
            )
        )
        mock_service.generate_summary = AsyncMock(
            return_value={
                "summary": "玩家与旅行者进行了友好交谈。",
                "key_info": ["旅行者来自北方"],
            }
        )

        manager = DialogueManager(llm_service=mock_service)
        state = dialogue_world_state

        ctx, opening = await manager.start(state, "traveler")
        assert opening.text == "你好，旅行者！"
        assert manager.is_active

        ctx, resp1 = await manager.respond(ctx, "你从哪里来？", state)
        assert resp1.trust_delta == 2

        ctx, resp2 = await manager.respond(ctx, "有什么有趣的故事吗？", state)
        assert resp2.trust_delta == 2

        summary = await manager.end(ctx)
        assert not manager.is_active
        assert summary.npc_id == "traveler"
        assert summary.total_trust_delta == 2 + 2 + 2 + 2  # opening + 2 respond turns each call returns 2

    @pytest.mark.asyncio
    async def test_dialogue_state_persistence(self, dialogue_world_state):
        """After end(), trust change should be committable to WorldState."""
        mock_service = MagicMock()
        mock_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(text="!", trust_delta=5, mood="x", wants_to_end=False)
        )
        mock_service.generate_summary = AsyncMock(
            return_value={"summary": "对话完成", "key_info": []}
        )

        manager = DialogueManager(llm_service=mock_service)
        state = dialogue_world_state

        ctx, _ = await manager.start(state, "traveler")
        summary = await manager.end(ctx)

        old_trust = state.characters["traveler"].stats["trust"]
        npc = state.characters["traveler"]
        new_stats = {**dict(npc.stats), "trust": old_trust + summary.total_trust_delta}
        diff = StateDiff(
            updated_characters={"traveler": {"stats": new_stats}},
            turn_increment=0,
        )
        state_manager = StateManager(initial_state=state)
        from tavern.world.models import ActionResult
        from tavern.engine.actions import ActionType
        state_manager.commit(
            diff,
            ActionResult(success=True, action=ActionType.TALK, message="对话结束", target="traveler"),
        )
        new_trust = state_manager.current.characters["traveler"].stats["trust"]
        assert new_trust == old_trust + summary.total_trust_delta
```

- [ ] **Step 3: Run tests to verify they fail (or pass — the logic is in already-tested components)**

```bash
pytest tests/test_integration.py -v -k "TestDialogueE2E"
```

Expected: PASS (logic relies on already-tested DialogueManager).

- [ ] **Step 4: Run full test suite with coverage**

```bash
pytest tests/ --cov=src/tavern --cov-report=term-missing -q
```

Expected: ≥ 80% overall coverage, ≥ 85% for `src/tavern/dialogue/`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add E2E dialogue integration tests"
```

---

## Self-Review Checklist

After writing this plan, reviewing against spec:

- [x] `src/tavern/dialogue/` module with `__init__`, `context`, `prompts`, `manager` ✓
- [x] `Message`, `DialogueContext`, `DialogueResponse`, `DialogueSummary` frozen dataclasses ✓
- [x] `resolve_tone()` with correct thresholds (-20/+20) ✓
- [x] `build_dialogue_prompt()` with all 8 required sections ✓
- [x] `build_summary_prompt()` ✓
- [x] `DialogueManager.start()` validates NPC location, reads trust, injects history summaries ✓
- [x] `DialogueManager.respond()` enforces 20-turn limit ✓
- [x] `DialogueManager.end()` sums trust_delta from messages ✓
- [x] `LLMService.generate_dialogue()` with trust_delta clamp [-5,+5] and JSON error fallback ✓
- [x] `LLMService.generate_summary()` with fallback ✓
- [x] RulesEngine TALK/PERSUADE handlers ✓
- [x] Renderer `render_dialogue_start`, `render_dialogue`, `render_dialogue_end`, `get_dialogue_input` ✓
- [x] GameApp dialogue routing in `run()` loop ✓
- [x] Trust written back to WorldState via StateDiff on dialogue end ✓
- [x] `dialogue_summary` Event written to timeline ✓
- [x] Error handling: all spec error cases covered in LLMService fallbacks ✓
- [x] 30+ tests across all new/modified files ✓
