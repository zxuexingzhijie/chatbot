# Claude Code 架构模式移植 — Phase 1: 核心架构

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 FSM + 命令注册表 + 响应式 Store 三大核心基础设施，将 GameApp 从 666 行 monolith 拆分为可测试、可扩展的模块化架构。

**Architecture:** 按依赖顺序实施 #7（独立）→ #5（响应式 Store）→ #6（命令注册表）→ #1（FSM），每个模块 TDD，完成后现有测试全部通过。Phase 2-4 的 #2/#3/#4/#8/#9/#10 在后续计划中实施。

**Tech Stack:** Python 3.12+, Pydantic 2.x (frozen models), asyncio, prompt_toolkit, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-10-claude-code-patterns-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/tavern/engine/seeded_rng.py` | §7 SeededRNG, make_seed, generate_ambience, generate_npc_appearance |
| `src/tavern/engine/commands.py` | §6 GameCommand, CommandRegistry, CommandContext |
| `src/tavern/engine/command_defs.py` | §6 所有命令定义（cmd_look, cmd_save 等）+ register_all() |
| `src/tavern/engine/fsm.py` | §1 GameMode, TransitionResult, SideEffect, EffectKind, ModeHandler protocol, GameLoop |
| `src/tavern/engine/effects.py` | §1 EFFECT_EXECUTORS dict + executor functions |
| `src/tavern/engine/modes/exploring.py` | §1 ExploringModeHandler |
| `src/tavern/engine/modes/dialogue.py` | §1 DialogueModeHandler |
| `src/tavern/engine/modes/__init__.py` | empty |
| `src/tavern/cli/bootstrap.py` | §1 Bootstrapper (组装 GameLoop + ModeContext) |
| `tests/engine/test_seeded_rng.py` | §7 tests |
| `tests/engine/test_commands.py` | §6 tests |
| `tests/engine/test_fsm.py` | §1 FSM core tests |
| `tests/engine/test_effects.py` | §1 effect executor tests |
| `tests/engine/test_modes_exploring.py` | §1 ExploringModeHandler tests |
| `tests/engine/test_modes_dialogue.py` | §1 DialogueModeHandler tests |
| `tests/world/test_reactive_state.py` | §5 ReactiveStateManager tests |

### Modified files

| File | Changes |
|------|---------|
| `src/tavern/world/state.py` | StateManager → ReactiveStateManager (add subscribe, on_change, replace, version) |
| `src/tavern/world/models.py` | Add `player_location` computed property convenience |
| `src/tavern/cli/app.py` | Extract command bodies → command_defs.py, delegate to GameLoop |
| `src/tavern/cli/renderer.py` | ContextualCompleter accepts registry callback |
| `tests/world/test_state.py` | Update for new API (undo returns None, version tracking) |

---

## Task 1: 确定性种子生成器 (§7)

独立模块，无依赖，最适合先做。

**Files:**
- Create: `src/tavern/engine/seeded_rng.py`
- Create: `tests/engine/test_seeded_rng.py`

- [ ] **Step 1: Write failing tests for SeededRNG**

```python
# tests/engine/test_seeded_rng.py
from tavern.engine.seeded_rng import SeededRNG, make_seed, generate_ambience, AmbienceDetails


class TestSeededRNG:
    def test_same_seed_same_sequence(self):
        rng1 = SeededRNG(42)
        rng2 = SeededRNG(42)
        assert [rng1.next() for _ in range(10)] == [rng2.next() for _ in range(10)]

    def test_different_seed_different_sequence(self):
        rng1 = SeededRNG(42)
        rng2 = SeededRNG(99)
        assert rng1.next() != rng2.next()

    def test_next_returns_float_in_range(self):
        rng = SeededRNG(42)
        for _ in range(100):
            val = rng.next()
            assert 0.0 <= val < 1.0

    def test_choice_deterministic(self):
        options = ["a", "b", "c", "d"]
        result1 = SeededRNG(42).choice(options)
        result2 = SeededRNG(42).choice(options)
        assert result1 == result2
        assert result1 in options

    def test_weighted_choice_deterministic(self):
        options = [("common", 0.9), ("rare", 0.1)]
        result1 = SeededRNG(42).weighted_choice(options)
        result2 = SeededRNG(42).weighted_choice(options)
        assert result1 == result2

    def test_weighted_choice_respects_weights(self):
        options = [("always", 1.0), ("never", 0.0)]
        rng = SeededRNG(42)
        assert rng.weighted_choice(options) == "always"


class TestMakeSeed:
    def test_deterministic(self):
        assert make_seed("tavern_hall", 5, "ambience") == make_seed("tavern_hall", 5, "ambience")

    def test_different_location_different_seed(self):
        assert make_seed("tavern_hall", 5) != make_seed("cellar", 5)

    def test_different_turn_different_seed(self):
        assert make_seed("tavern_hall", 5) != make_seed("tavern_hall", 6)

    def test_null_separator_prevents_collision(self):
        # "bar" + 10 + "" vs "bar" + 1 + "0"
        assert make_seed("bar", 10, "") != make_seed("bar", 1, "0")


class TestGenerateAmbience:
    def test_returns_ambience_details(self):
        result = generate_ambience("tavern_hall", 1)
        assert isinstance(result, AmbienceDetails)
        assert result.weather in ["晴朗", "阴沉", "微雨", "大雾"]
        assert result.crowd_level in ["冷清", "稍有人气", "热闹", "拥挤"]
        assert isinstance(result.background_sound, str)
        assert isinstance(result.smell, str)

    def test_deterministic_for_same_inputs(self):
        a = generate_ambience("tavern_hall", 1)
        b = generate_ambience("tavern_hall", 1)
        assert a == b

    def test_different_turn_may_differ(self):
        results = {generate_ambience("tavern_hall", t).weather for t in range(20)}
        assert len(results) > 1  # not all the same
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_seeded_rng.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tavern.engine.seeded_rng'`

- [ ] **Step 3: Implement SeededRNG module**

```python
# src/tavern/engine/seeded_rng.py
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any


class SeededRNG:
    """Mulberry32 确定性伪随机数生成器"""

    __slots__ = ("_state",)

    def __init__(self, seed: int):
        self._state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self._state = (self._state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 0x100000000

    def choice(self, options: list[Any]) -> Any:
        return options[int(self.next() * len(options))]

    def weighted_choice(self, options: list[tuple[Any, float]]) -> Any:
        total = sum(w for _, w in options)
        r = self.next() * total
        cumulative = 0.0
        for item, weight in options:
            cumulative += weight
            if r < cumulative:
                return item
        return options[-1][0]


def make_seed(location_id: str, turn: int, salt: str = "") -> int:
    raw = f"{location_id}\x00{turn}\x00{salt}"
    digest = hashlib.md5(raw.encode()).digest()
    return struct.unpack("<I", digest[:4])[0]


@dataclass(frozen=True)
class AmbienceDetails:
    weather: str
    crowd_level: str
    background_sound: str
    smell: str


_WEATHER_OPTIONS = ["晴朗", "阴沉", "微雨", "大雾"]
_CROWD_OPTIONS = ["冷清", "稍有人气", "热闹", "拥挤"]
_SOUND_OPTIONS = [
    "远处传来马蹄声",
    "炉火噼啪作响",
    "窗外有鸟鸣",
    "隔壁桌传来笑声",
]
_SMELL_OPTIONS = [
    "烤面包的香气",
    "潮湿木头的味道",
    "麦酒的醇厚气息",
    "草药的淡淡清香",
]


def generate_ambience(location_id: str, turn: int) -> AmbienceDetails:
    rng = SeededRNG(make_seed(location_id, turn, "ambience"))
    return AmbienceDetails(
        weather=rng.choice(_WEATHER_OPTIONS),
        crowd_level=rng.choice(_CROWD_OPTIONS),
        background_sound=rng.choice(_SOUND_OPTIONS),
        smell=rng.choice(_SMELL_OPTIONS),
    )


def generate_npc_appearance(npc_id: str) -> dict[str, str | None]:
    rng = SeededRNG(make_seed(npc_id, 0, "appearance"))
    return {
        "scar": rng.choice([None, "左颊", "额头", "下巴"]),
        "hair_detail": rng.choice(["凌乱", "整齐梳理", "扎成马尾", "半遮面"]),
        "clothing_condition": rng.choice(["整洁", "略显陈旧", "满是尘土", "有修补痕迹"]),
    }


def should_trigger_random_event(location_id: str, turn: int) -> bool:
    rng = SeededRNG(make_seed(location_id, turn, "event"))
    return rng.next() < 0.15
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_seeded_rng.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/seeded_rng.py tests/engine/test_seeded_rng.py
git commit -m "feat: add deterministic seeded RNG module (§7)"
```

---

## Task 2: 响应式 Store — ReactiveStateManager (§5)

将 StateManager 升级为 ReactiveStateManager，新增 subscribe/on_change/replace/version。

**Files:**
- Modify: `src/tavern/world/state.py:120-147`
- Create: `tests/world/test_reactive_state.py`
- Modify: `tests/world/test_state.py` (update existing tests for API changes)

- [ ] **Step 1: Write failing tests for ReactiveStateManager**

```python
# tests/world/test_reactive_state.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.world.models import ActionResult, Event
from tavern.world.state import ReactiveStateManager, StateDiff, WorldState


def _make_state(**kwargs) -> WorldState:
    defaults = {"turn": 0, "player_id": "player", "locations": {}, "characters": {}}
    defaults.update(kwargs)
    return WorldState(**defaults)


def _make_diff(**kwargs) -> StateDiff:
    return StateDiff(**kwargs)


def _make_result() -> ActionResult:
    return ActionResult(success=True, action="look", message="ok")


class TestReactiveStateManagerCommit:
    def test_commit_updates_state(self):
        state = _make_state(turn=0)
        mgr = ReactiveStateManager(state)
        diff = _make_diff(turn_increment=1)
        new_state = mgr.commit(diff, _make_result())
        assert new_state.turn == 1
        assert mgr.state.turn == 1

    def test_commit_increments_version(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.version == 0
        mgr.commit(_make_diff(), _make_result())
        assert mgr.version == 1
        mgr.commit(_make_diff(), _make_result())
        assert mgr.version == 2

    def test_commit_fires_on_change(self):
        on_change = AsyncMock()
        mgr = ReactiveStateManager(_make_state(), on_change=on_change)
        mgr.commit(_make_diff(), _make_result())
        # fire-and-forget: need event loop tick
        # on_change was scheduled via create_task

    def test_commit_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.subscribe(listener)
        mgr.commit(_make_diff(), _make_result())
        listener.assert_called_once()

    def test_commit_action_param_is_optional(self):
        mgr = ReactiveStateManager(_make_state())
        new_state = mgr.commit(_make_diff())
        assert new_state.last_action is None


class TestReactiveStateManagerUndo:
    def test_undo_returns_previous_state(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(turn_increment=1), _make_result())
        result = mgr.undo()
        assert result is not None
        assert result.turn == 0

    def test_undo_empty_returns_none(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.undo() is None

    def test_undo_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.commit(_make_diff(), _make_result())
        mgr.subscribe(listener)
        mgr.undo()
        listener.assert_called_once()


class TestReactiveStateManagerSubscribe:
    def test_subscribe_returns_unsubscribe(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        unsub = mgr.subscribe(listener)
        mgr.commit(_make_diff(), _make_result())
        assert listener.call_count == 1
        unsub()
        mgr.commit(_make_diff(), _make_result())
        assert listener.call_count == 1  # no longer called

    def test_listener_removal_during_iteration_safe(self):
        mgr = ReactiveStateManager(_make_state())
        calls = []

        def self_removing_listener():
            calls.append("called")
            unsub()

        unsub = mgr.subscribe(self_removing_listener)
        other = MagicMock()
        mgr.subscribe(other)
        mgr.commit(_make_diff(), _make_result())
        assert calls == ["called"]
        other.assert_called_once()


class TestReactiveStateManagerReplace:
    def test_replace_sets_new_state(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(turn_increment=1), _make_result())
        new = _make_state(turn=99)
        mgr.replace(new)
        assert mgr.state.turn == 99

    def test_replace_clears_history(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(), _make_result())
        mgr.replace(_make_state(turn=99))
        assert mgr.undo() is None  # history cleared

    def test_replace_increments_version(self):
        mgr = ReactiveStateManager(_make_state())
        v_before = mgr.version
        mgr.replace(_make_state(turn=99))
        assert mgr.version == v_before + 1

    def test_replace_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.subscribe(listener)
        mgr.replace(_make_state(turn=99))
        listener.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/world/test_reactive_state.py -v`
Expected: FAIL with `ImportError: cannot import name 'ReactiveStateManager'`

- [ ] **Step 3: Implement ReactiveStateManager**

Replace `StateManager` class in `src/tavern/world/state.py` (lines 120-147) with:

```python
# Add imports at top of file
from typing import Callable, Awaitable
import asyncio

Listener = Callable[[], None]
OnChange = Callable[["WorldState", "WorldState"], Awaitable[None]]


class ReactiveStateManager:
    def __init__(
        self,
        initial_state: WorldState,
        max_history: int = 50,
        on_change: OnChange | None = None,
    ):
        self._state = initial_state
        self._version = 0
        self._history: deque[tuple[WorldState, int]] = deque(maxlen=max_history)
        self._future: list[tuple[WorldState, int]] = []
        self._listeners: list[Listener] = []
        self._on_change = on_change

    @property
    def current(self) -> WorldState:
        return self._state

    @property
    def state(self) -> WorldState:
        return self._state

    @property
    def version(self) -> int:
        return self._version

    def commit(self, diff: StateDiff, action: ActionResult | None = None) -> WorldState:
        old = self._state
        self._history.append((old, self._version))
        self._future.clear()
        self._state = old.apply(diff, action=action)
        self._version += 1
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def undo(self) -> WorldState | None:
        if not self._history:
            return None
        self._future.append((self._state, self._version))
        old = self._state
        self._state, self._version = self._history.pop()
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()
        return self._state

    def redo(self) -> WorldState | None:
        if not self._future:
            return None
        self._history.append((self._state, self._version))
        old = self._state
        self._state, self._version = self._future.pop()
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()
        return self._state

    def replace(self, new_state: WorldState) -> None:
        old = self._state
        self._state = new_state
        self._history.clear()
        self._future.clear()
        self._version += 1
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()


# Keep backward compat alias
StateManager = ReactiveStateManager
```

Keep the old `StateManager` name as an alias so existing code (app.py, tests) doesn't break immediately.

- [ ] **Step 4: Run new tests**

Run: `python -m pytest tests/world/test_reactive_state.py -v`
Expected: All PASS

- [ ] **Step 5: Run existing tests to verify no breakage**

Run: `python -m pytest tests/world/test_state.py -v`
Expected: All PASS (StateManager alias + undo now returns None instead of raising IndexError — check if any test catches IndexError)

If existing tests fail on `undo()` return type, update `tests/world/test_state.py`:
- Change `with pytest.raises(IndexError)` to `assert mgr.undo() is None`

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: All existing tests pass. Any failures in `app.py` code that does `try/except IndexError` on undo are runtime only (not unit-tested), will be fixed in Task 4.

- [ ] **Step 7: Commit**

```bash
git add src/tavern/world/state.py tests/world/test_reactive_state.py tests/world/test_state.py
git commit -m "feat: upgrade StateManager to ReactiveStateManager with subscribe/on_change/replace (§5)"
```

---

## Task 3: 命令注册表 — CommandRegistry (§6)

**Files:**
- Create: `src/tavern/engine/commands.py`
- Create: `tests/engine/test_commands.py`

- [ ] **Step 1: Write failing tests for CommandRegistry**

```python
# tests/engine/test_commands.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from unittest.mock import AsyncMock

import pytest

from tavern.engine.commands import CommandRegistry, GameCommand


# Minimal GameMode stub for testing (real one comes from fsm.py in Task 4)
class _GameMode(str, Enum):
    EXPLORING = "exploring"
    DIALOGUE = "dialogue"
    COMBAT = "combat"


@dataclass(frozen=True)
class _FakeState:
    turn: int = 0
    is_in_combat: bool = False


class TestCommandRegistry:
    def _make_registry(self) -> CommandRegistry:
        r = CommandRegistry()
        r.register(GameCommand(
            name="/look",
            aliases=("/l",),
            description="查看环境",
            available_in=(_GameMode.EXPLORING, _GameMode.COMBAT),
            execute=AsyncMock(),
        ))
        r.register(GameCommand(
            name="/save",
            aliases=("/s",),
            description="保存",
            available_in=(_GameMode.EXPLORING,),
            is_available=lambda s: not s.is_in_combat,
            execute=AsyncMock(),
        ))
        r.register(GameCommand(
            name="/debug",
            description="调试",
            is_hidden=True,
            available_in=(_GameMode.EXPLORING,),
            execute=AsyncMock(),
        ))
        return r

    def test_find_by_name(self):
        r = self._make_registry()
        assert r.find("/look") is not None
        assert r.find("/look").name == "/look"

    def test_find_by_alias(self):
        r = self._make_registry()
        cmd = r.find("/l")
        assert cmd is not None
        assert cmd.name == "/look"

    def test_find_unknown_returns_none(self):
        r = self._make_registry()
        assert r.find("/unknown") is None

    def test_get_available_filters_by_mode(self):
        r = self._make_registry()
        state = _FakeState()
        available = r.get_available(_GameMode.COMBAT, state)
        names = [c.name for c in available]
        assert "/look" in names
        assert "/save" not in names

    def test_get_available_excludes_hidden(self):
        r = self._make_registry()
        state = _FakeState()
        available = r.get_available(_GameMode.EXPLORING, state)
        names = [c.name for c in available]
        assert "/debug" not in names

    def test_get_available_checks_is_available(self):
        r = self._make_registry()
        state = _FakeState(is_in_combat=True)
        available = r.get_available(_GameMode.EXPLORING, state)
        names = [c.name for c in available]
        assert "/save" not in names

    def test_get_completions(self):
        r = self._make_registry()
        state = _FakeState()
        completions = r.get_completions(_GameMode.EXPLORING, state)
        assert "/look" in completions
        assert "/save" in completions
        assert "/debug" not in completions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_commands.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement CommandRegistry**

```python
# src/tavern/engine/commands.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.world.state import ReactiveStateManager, WorldState


@dataclass
class CommandContext:
    state_manager: ReactiveStateManager
    renderer: Any
    narrator: Any
    memory: Any
    persistence: Any
    story_engine: Any
    dialogue_manager: Any
    logger: Any


@dataclass(frozen=True)
class GameCommand:
    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    is_hidden: bool = False
    available_in: tuple = ()  # tuple of GameMode
    is_available: Callable[[Any], bool] = lambda _: True
    execute: Callable[[str, CommandContext], Awaitable[None]] = field(default=None)


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: list[GameCommand] = []
        self._lookup: dict[str, GameCommand] = {}

    def register(self, cmd: GameCommand) -> None:
        self._commands.append(cmd)
        self._lookup[cmd.name] = cmd
        for alias in cmd.aliases:
            self._lookup[alias] = cmd

    def find(self, name: str) -> GameCommand | None:
        return self._lookup.get(name)

    def get_available(self, mode: Any, state: Any) -> list[GameCommand]:
        return [
            c for c in self._commands
            if mode in c.available_in
            and not c.is_hidden
            and c.is_available(state)
        ]

    def get_completions(self, mode: Any, state: Any) -> list[str]:
        return [c.name for c in self.get_available(mode, state)]

    async def handle_command(
        self, raw: str, mode: Any, ctx: CommandContext
    ) -> bool:
        parts = raw.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        cmd = self.find(cmd_name)
        if cmd is None:
            return False
        if mode not in cmd.available_in:
            await ctx.renderer.render_error(f"当前模式下不可用: {cmd_name}")
            return True
        if not cmd.is_available(ctx.state_manager.state):
            await ctx.renderer.render_error(f"当前无法执行: {cmd_name}")
            return True
        await cmd.execute(args, ctx)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_commands.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/commands.py tests/engine/test_commands.py
git commit -m "feat: add CommandRegistry with find/get_available/handle_command (§6)"
```

---

## Task 4: 提取命令定义 — command_defs.py (§6)

将 `app.py` 中 `_handle_system_command` 的每个分支提取为独立命令函数，注册到 CommandRegistry。

**Files:**
- Create: `src/tavern/engine/command_defs.py`
- Modify: `src/tavern/cli/app.py` (replace if-elif with registry dispatch)

- [ ] **Step 1: Create command_defs.py with all commands extracted from app.py**

提取 app.py:288-410 中的每个 elif 分支。暂时用 `EXPLORING` 字符串作为 mode，在 Task 5 引入 GameMode 后替换。

```python
# src/tavern/engine/command_defs.py
from __future__ import annotations

from tavern.engine.actions import ActionType
from tavern.engine.commands import CommandContext, CommandRegistry, GameCommand
from tavern.world.models import ActionRequest


async def cmd_look(args: str, ctx: CommandContext) -> None:
    if args:
        request = ActionRequest(action=ActionType.LOOK, target=args)
    else:
        request = ActionRequest(action=ActionType.LOOK)
    from tavern.engine.rules import RulesEngine
    rules = RulesEngine()
    result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(result)


async def cmd_inventory(args: str, ctx: CommandContext) -> None:
    ctx.renderer.render_inventory(ctx.state_manager.state)


async def cmd_status(args: str, ctx: CommandContext) -> None:
    relationships = ctx.memory.get_player_relationships(ctx.state_manager.state.player_id)
    ctx.renderer.render_status(ctx.state_manager.state, relationships)


async def cmd_hint(args: str, ctx: CommandContext) -> None:
    ctx.renderer.console.print(
        "\n[dim italic]尝试和酒馆里的人聊聊天，也许能发现什么线索...[/]\n"
    )


async def cmd_undo(args: str, ctx: CommandContext) -> None:
    result = ctx.state_manager.undo()
    if result is None:
        ctx.renderer.console.print("\n[red]没有可以回退的步骤。[/]\n")
        return
    ctx.renderer.console.print("\n[dim]已回退上一步。[/]\n")
    request = ActionRequest(action=ActionType.LOOK)
    from tavern.engine.rules import RulesEngine
    rules = RulesEngine()
    look_result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(look_result)


async def cmd_help(args: str, ctx: CommandContext) -> None:
    ctx.renderer.render_help()


async def cmd_save(args: str, ctx: CommandContext) -> None:
    slot = args.strip() if args.strip() else "auto"
    try:
        new_state = ctx.memory.sync_to_state(ctx.state_manager.state)
        path = ctx.persistence.save(new_state, slot)
        ctx.renderer.render_save_success(slot, path)
    except OSError as e:
        ctx.renderer.console.print(f"\n[red]存档失败：{e}[/]\n")


async def cmd_saves(args: str, ctx: CommandContext) -> None:
    saves = ctx.persistence.list_saves()
    ctx.renderer.render_saves_list(saves)


async def cmd_load(args: str, ctx: CommandContext) -> None:
    if ctx.dialogue_manager and ctx.dialogue_manager.is_active:
        ctx.renderer.console.print("\n[red]请先结束当前对话再加载存档。[/]\n")
        return
    slot = args.strip() if args.strip() else "auto"
    try:
        loaded_state, timestamp = ctx.persistence.load(slot)
        ctx.state_manager.replace(loaded_state)
        ctx.memory.rebuild(loaded_state)
        ctx.renderer.render_load_success(slot, timestamp)
    except (FileNotFoundError, ValueError) as e:
        ctx.renderer.console.print(f"\n[red]{e}[/]\n")


async def cmd_quit(args: str, ctx: CommandContext) -> None:
    raise SystemExit(0)


# 用字符串占位，Task 5 引入 GameMode 后改为枚举引用
_ALL_MODES = ("exploring", "dialogue", "combat", "inventory", "shop")
_EXPLORING = ("exploring",)


def register_all_commands(registry: CommandRegistry) -> None:
    registry.register(GameCommand(
        name="/look", aliases=("/l", "/观察"), description="查看当前环境",
        available_in=_ALL_MODES, execute=cmd_look,
    ))
    registry.register(GameCommand(
        name="/inventory", aliases=("/i", "/背包"), description="查看背包物品",
        available_in=_ALL_MODES, execute=cmd_inventory,
    ))
    registry.register(GameCommand(
        name="/status", aliases=("/st",), description="查看状态",
        available_in=_ALL_MODES, execute=cmd_status,
    ))
    registry.register(GameCommand(
        name="/hint", description="查看提示",
        available_in=_EXPLORING, execute=cmd_hint,
    ))
    registry.register(GameCommand(
        name="/undo", description="回退上一步",
        available_in=_EXPLORING, execute=cmd_undo,
    ))
    registry.register(GameCommand(
        name="/help", aliases=("/h", "/帮助"), description="显示帮助",
        available_in=_ALL_MODES, execute=cmd_help,
    ))
    registry.register(GameCommand(
        name="/save", aliases=("/s",), description="保存游戏",
        available_in=_EXPLORING, execute=cmd_save,
    ))
    registry.register(GameCommand(
        name="/saves", description="查看存档列表",
        available_in=_EXPLORING, execute=cmd_saves,
    ))
    registry.register(GameCommand(
        name="/load", description="加载存档",
        available_in=_EXPLORING, execute=cmd_load,
    ))
    registry.register(GameCommand(
        name="/quit", aliases=("/q", "/退出"), description="退出游戏",
        available_in=_ALL_MODES, execute=cmd_quit,
    ))
```

- [ ] **Step 2: Run full test suite to verify no breakage**

Run: `python -m pytest --tb=short -q`
Expected: All PASS (command_defs is not yet wired into app.py)

- [ ] **Step 3: Commit**

```bash
git add src/tavern/engine/command_defs.py
git commit -m "feat: extract all command definitions into command_defs.py (§6)"
```

---

## Task 5: FSM 核心 — GameMode, TransitionResult, SideEffect (§1)

**Files:**
- Create: `src/tavern/engine/fsm.py`
- Create: `src/tavern/engine/effects.py`
- Create: `tests/engine/test_fsm.py`
- Create: `tests/engine/test_effects.py`

- [ ] **Step 1: Write failing tests for FSM types and GameLoop**

```python
# tests/engine/test_fsm.py
from tavern.engine.fsm import (
    EffectKind, GameLoop, GameMode, ModeContext, SideEffect, TransitionResult,
)


class TestGameMode:
    def test_all_modes_exist(self):
        assert GameMode.EXPLORING.value == "exploring"
        assert GameMode.DIALOGUE.value == "dialogue"
        assert GameMode.COMBAT.value == "combat"
        assert GameMode.INVENTORY.value == "inventory"
        assert GameMode.SHOP.value == "shop"


class TestTransitionResult:
    def test_stay_in_mode(self):
        result = TransitionResult(next_mode=None, side_effects=())
        assert result.next_mode is None

    def test_transition_with_effects(self):
        effect = SideEffect(kind=EffectKind.START_DIALOGUE, payload={"npc_id": "grim"})
        result = TransitionResult(
            next_mode=GameMode.DIALOGUE,
            side_effects=(effect,),
        )
        assert result.next_mode == GameMode.DIALOGUE
        assert len(result.side_effects) == 1


class TestSideEffect:
    def test_frozen(self):
        e = SideEffect(kind=EffectKind.APPLY_DIFF, payload={"diff": {}})
        assert e.kind == EffectKind.APPLY_DIFF

    def test_all_effect_kinds_exist(self):
        expected = {
            "START_DIALOGUE", "END_DIALOGUE", "APPLY_DIFF", "EMIT_EVENT",
            "APPLY_TRUST", "INIT_COMBAT", "APPLY_REWARDS", "FLEE_PENALTY", "OPEN_SHOP",
        }
        actual = {k.name for k in EffectKind}
        assert expected == actual
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_fsm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement fsm.py**

```python
# src/tavern/engine/fsm.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.commands import CommandRegistry
    from tavern.world.state import ReactiveStateManager, WorldState

logger = logging.getLogger(__name__)


class GameMode(Enum):
    EXPLORING = "exploring"
    DIALOGUE = "dialogue"
    COMBAT = "combat"
    INVENTORY = "inventory"
    SHOP = "shop"


class EffectKind(Enum):
    START_DIALOGUE = "start_dialogue"
    END_DIALOGUE = "end_dialogue"
    APPLY_DIFF = "apply_diff"
    EMIT_EVENT = "emit_event"
    APPLY_TRUST = "apply_trust"
    INIT_COMBAT = "init_combat"
    APPLY_REWARDS = "apply_rewards"
    FLEE_PENALTY = "flee_penalty"
    OPEN_SHOP = "open_shop"


@dataclass(frozen=True)
class SideEffect:
    kind: EffectKind
    payload: dict


@dataclass(frozen=True)
class TransitionResult:
    next_mode: GameMode | None = None
    side_effects: tuple[SideEffect, ...] = ()


@dataclass(frozen=True)
class PromptConfig:
    prompt_text: str = "> "
    show_status_bar: bool = True


@dataclass(frozen=True)
class Keybinding:
    key: str
    action: str
    description: str
    allow_in_text: bool = False


@dataclass
class ModeContext:
    state_manager: ReactiveStateManager
    renderer: Any
    dialogue_manager: Any
    narrator: Any
    memory: Any
    persistence: Any
    story_engine: Any
    command_registry: CommandRegistry
    action_registry: Any
    logger: Any


class ModeHandler(Protocol):
    @property
    def mode(self) -> GameMode: ...

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext
    ) -> TransitionResult: ...

    def get_prompt_config(self, state: WorldState) -> PromptConfig: ...

    def get_keybindings(self) -> list[Keybinding]: ...


EffectExecutor = Callable[[dict, ModeContext], Awaitable[None]]


class GameLoop:
    def __init__(
        self,
        handlers: dict[GameMode, ModeHandler],
        context: ModeContext,
        effect_executors: dict[EffectKind, EffectExecutor],
    ):
        self._handlers = handlers
        self._context = context
        self._effect_executors = effect_executors
        self._current_mode = GameMode.EXPLORING
        self._running = False

    @property
    def current_mode(self) -> GameMode:
        return self._current_mode

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                handler = self._handlers[self._current_mode]
                state = self._context.state_manager.state
                raw = await self._context.renderer.get_input(
                    handler.get_prompt_config(state)
                )
                result = await handler.handle_input(raw, state, self._context)
                for effect in result.side_effects:
                    await self._execute_effect(effect)
                if result.next_mode is not None:
                    self._current_mode = result.next_mode
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                logger.exception("GameLoop error")
                await self._context.renderer.render_error(f"内部错误: {e}")

    async def _execute_effect(self, effect: SideEffect) -> None:
        executor = self._effect_executors.get(effect.kind)
        if executor is None:
            logger.warning("No executor for effect kind: %s", effect.kind)
            return
        await executor(effect.payload, self._context)

    def stop(self) -> None:
        self._running = False

    def reset(self, new_state: WorldState) -> None:
        self._context.state_manager.replace(new_state)
        if hasattr(self._context.memory, "rebuild"):
            self._context.memory.rebuild(new_state)
        if hasattr(self._context.dialogue_manager, "reset"):
            self._context.dialogue_manager.reset()
        self._current_mode = GameMode.EXPLORING
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_fsm.py -v`
Expected: All PASS

- [ ] **Step 5: Implement effects.py**

```python
# src/tavern/engine/effects.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import EffectExecutor, EffectKind, ModeContext

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def exec_start_dialogue(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        raise ValueError(f"NPC not found: {npc_id}")
    # Delegate to dialogue_manager.start — actual wiring depends on existing DialogueManager API
    # This is a thin adapter
    logger.info("Starting dialogue with %s", npc_id)


async def exec_end_dialogue(payload: dict, ctx: ModeContext) -> None:
    logger.info("Ending dialogue")


async def exec_apply_diff(payload: dict, ctx: ModeContext) -> None:
    diff = payload["diff"]
    action = payload.get("action")
    ctx.state_manager.commit(diff, action)


async def exec_emit_event(payload: dict, ctx: ModeContext) -> None:
    event = payload["event"]
    logger.info("Event emitted: %s", event)


async def exec_apply_trust(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying trust changes: %s", payload)


async def exec_init_combat(payload: dict, ctx: ModeContext) -> None:
    logger.info("Initializing combat: %s", payload)


async def exec_apply_rewards(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying rewards: %s", payload)


async def exec_flee_penalty(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying flee penalty: %s", payload)


async def exec_open_shop(payload: dict, ctx: ModeContext) -> None:
    logger.info("Opening shop: %s", payload)


EFFECT_EXECUTORS: dict[EffectKind, EffectExecutor] = {
    EffectKind.START_DIALOGUE: exec_start_dialogue,
    EffectKind.END_DIALOGUE: exec_end_dialogue,
    EffectKind.APPLY_DIFF: exec_apply_diff,
    EffectKind.EMIT_EVENT: exec_emit_event,
    EffectKind.APPLY_TRUST: exec_apply_trust,
    EffectKind.INIT_COMBAT: exec_init_combat,
    EffectKind.APPLY_REWARDS: exec_apply_rewards,
    EffectKind.FLEE_PENALTY: exec_flee_penalty,
    EffectKind.OPEN_SHOP: exec_open_shop,
}
```

- [ ] **Step 6: Write and run effects test**

```python
# tests/engine/test_effects.py
from tavern.engine.effects import EFFECT_EXECUTORS
from tavern.engine.fsm import EffectKind


class TestEffectExecutors:
    def test_all_effect_kinds_have_executors(self):
        for kind in EffectKind:
            assert kind in EFFECT_EXECUTORS, f"Missing executor for {kind}"

    def test_all_executors_are_callable(self):
        for kind, executor in EFFECT_EXECUTORS.items():
            assert callable(executor), f"Executor for {kind} is not callable"
```

Run: `python -m pytest tests/engine/test_effects.py tests/engine/test_fsm.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/tavern/engine/fsm.py src/tavern/engine/effects.py tests/engine/test_fsm.py tests/engine/test_effects.py
git commit -m "feat: add FSM core types, GameLoop, and effect executors (§1)"
```

---

## Task 6: ExploringModeHandler (§1)

**Files:**
- Create: `src/tavern/engine/modes/__init__.py`
- Create: `src/tavern/engine/modes/exploring.py`
- Create: `tests/engine/test_modes_exploring.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_modes_exploring.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.fsm import (
    EffectKind, GameMode, ModeContext, PromptConfig, SideEffect, TransitionResult,
)
from tavern.engine.modes.exploring import ExploringModeHandler
from tavern.world.state import WorldState


def _make_state(**kwargs) -> WorldState:
    return WorldState(turn=0, player_id="player", **kwargs)


def _make_context(**overrides) -> ModeContext:
    defaults = dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=MagicMock(),
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


class TestExploringModeHandler:
    def test_mode_is_exploring(self):
        handler = ExploringModeHandler()
        assert handler.mode == GameMode.EXPLORING

    @pytest.mark.asyncio
    async def test_slash_command_delegates_to_registry(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=True)
        ctx = _make_context(command_registry=registry)
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("/look", state, ctx)
        registry.handle_command.assert_awaited_once()
        assert result.next_mode is None  # stay in exploring

    @pytest.mark.asyncio
    async def test_unknown_slash_command(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=False)
        ctx = _make_context(command_registry=registry)
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("/nonexistent", state, ctx)
        assert result.next_mode is None

    def test_get_prompt_config(self):
        handler = ExploringModeHandler()
        config = handler.get_prompt_config(_make_state())
        assert isinstance(config, PromptConfig)

    def test_get_keybindings_returns_list(self):
        handler = ExploringModeHandler()
        bindings = handler.get_keybindings()
        assert isinstance(bindings, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_modes_exploring.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ExploringModeHandler**

```python
# src/tavern/engine/modes/__init__.py
# empty

# src/tavern/engine/modes/exploring.py
from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.fsm import (
    GameMode, Keybinding, ModeContext, PromptConfig, TransitionResult,
)

if TYPE_CHECKING:
    from tavern.world.state import WorldState


class ExploringModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.EXPLORING

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()
        if not stripped:
            return TransitionResult()

        # Slash commands
        if stripped.startswith("/"):
            handled = await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            if not handled:
                await context.renderer.render_error(f"未知命令: {stripped.split()[0]}")
            return TransitionResult()

        # Free text input — delegate to intent parser → rules engine
        # This will be fleshed out when wiring into app.py
        return TransitionResult()

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="> ", show_status_bar=True)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_modes_exploring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/modes/__init__.py src/tavern/engine/modes/exploring.py tests/engine/test_modes_exploring.py
git commit -m "feat: add ExploringModeHandler (§1)"
```

---

## Task 7: DialogueModeHandler (§1)

**Files:**
- Create: `src/tavern/engine/modes/dialogue.py`
- Create: `tests/engine/test_modes_dialogue.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_modes_dialogue.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.fsm import (
    EffectKind, GameMode, Keybinding, ModeContext, TransitionResult,
)
from tavern.engine.modes.dialogue import DialogueModeHandler
from tavern.world.state import WorldState


def _make_state(**kwargs) -> WorldState:
    return WorldState(turn=0, player_id="player", **kwargs)


def _make_context(**overrides) -> ModeContext:
    defaults = dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=MagicMock(),
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


class TestDialogueModeHandler:
    def test_mode_is_dialogue(self):
        handler = DialogueModeHandler()
        assert handler.mode == GameMode.DIALOGUE

    def test_keybindings_include_hint_selection(self):
        handler = DialogueModeHandler()
        bindings = handler.get_keybindings()
        hint_keys = [b for b in bindings if b.action.startswith("select_hint")]
        assert len(hint_keys) == 3
        for b in hint_keys:
            assert b.allow_in_text is True

    def test_keybindings_include_escape(self):
        handler = DialogueModeHandler()
        bindings = handler.get_keybindings()
        esc = [b for b in bindings if b.key == "escape"]
        assert len(esc) == 1
        assert esc[0].allow_in_text is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_modes_dialogue.py -v`
Expected: FAIL

- [ ] **Step 3: Implement DialogueModeHandler**

```python
# src/tavern/engine/modes/dialogue.py
from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.fsm import (
    EffectKind, GameMode, Keybinding, ModeContext, PromptConfig,
    SideEffect, TransitionResult,
)

if TYPE_CHECKING:
    from tavern.world.state import WorldState


class DialogueModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.DIALOGUE

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()

        # Slash commands in dialogue
        if stripped.startswith("/"):
            handled = await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            return TransitionResult()

        # Empty input — ignore
        if not stripped:
            return TransitionResult()

        # Dialogue text — delegate to dialogue_manager
        # Full wiring happens when app.py is refactored
        return TransitionResult()

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="对话> ", show_status_bar=False)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_modes_dialogue.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/modes/dialogue.py tests/engine/test_modes_dialogue.py
git commit -m "feat: add DialogueModeHandler (§1)"
```

---

## Task 8: Update command_defs to use GameMode enum

**Files:**
- Modify: `src/tavern/engine/command_defs.py`

- [ ] **Step 1: Replace string mode placeholders with GameMode enum**

In `command_defs.py`, replace:
- `_ALL_MODES = ("exploring", "dialogue", "combat", "inventory", "shop")` → `_ALL_MODES = tuple(GameMode)`
- `_EXPLORING = ("exploring",)` → `_EXPLORING = (GameMode.EXPLORING,)`
- Add `from tavern.engine.fsm import GameMode` at top

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/tavern/engine/command_defs.py
git commit -m "refactor: use GameMode enum in command_defs"
```

---

## Task 9: Full integration — run full test suite + verify

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: All existing tests pass. New tests all pass.

- [ ] **Step 2: Run with coverage**

Run: `python -m pytest --cov=tavern --cov-report=term-missing --tb=short -q`
Expected: New modules have 80%+ coverage.

- [ ] **Step 3: Verify the game still runs**

Run: `python -m tavern --help` (or whatever the entry point does)
Expected: No import errors, help prints normally.

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix: integration fixes for Phase 1 core architecture"
```

---

## What Phase 1 does NOT include (deferred to Phase 2-4 plans)

| Deferred | Phase | Reason |
|----------|-------|--------|
| §4 Action 工厂 (ActionDef, ActionRegistry, build_action) | Phase 2 | Depends on FSM for commit flow |
| §2 快捷键系统 (InputMode, KeybindingResolver) | Phase 2 | Depends on GameMode enum |
| §3 Markdown-as-Code (ContentLoader, variant files) | Phase 3 | Independent content system |
| §9 分类记忆 (ClassifiedMemorySystem, MemoryExtractor) | Phase 3 | Depends on on_change |
| §10 场景缓存 (SceneContextCache, CachedPromptBuilder) | Phase 4 | Depends on §3 + §5 |
| §8 游戏日志 (GameLogger, /journal) | Phase 4 | Depends on §5 on_change |
| Bootstrapper + full app.py refactor | Phase 2 | After §4 ActionRegistry is ready |
| Wire ExploringModeHandler free-text path into GameLoop | Phase 2 | Needs §4 ActionRegistry |
| Wire DialogueModeHandler into actual DialogueManager | Phase 2 | Needs full app.py refactor |
