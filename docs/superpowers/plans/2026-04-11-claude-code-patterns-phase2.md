# Claude Code 架构模式移植 — Phase 2: 游戏机制

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Action 工厂统一接口 + 快捷键系统 + Bootstrapper，将 app.py 从 666 行 monolith 解耦为 GameLoop 驱动的模块化架构。

**Architecture:** 按依赖顺序实施：WorldState 便利属性 → §4 ActionDef/ActionRegistry → §2 InputMode + KeybindingResolver → Bootstrapper + app.py 重构。每个模块 TDD，完成后现有 565 个测试全部通过。

**Tech Stack:** Python 3.12+, Pydantic 2.x (frozen models), asyncio, prompt_toolkit, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-10-claude-code-patterns-design.md`

**Phase 1 已完成：** §7 SeededRNG, §5 ReactiveStateManager, §6 CommandRegistry + command_defs, §1 FSM + GameLoop + ModeHandlers

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/tavern/engine/action_defs.py` | §4 ActionDef, build_action(), ACTION_DEFAULTS |
| `src/tavern/engine/action_registry.py` | §4 ActionRegistry 类 |
| `src/tavern/engine/action_handlers.py` | §4 所有 build_action() 调用，构建每个 ActionDef |
| `src/tavern/engine/keybindings.py` | §2 InputMode, KeybindingBlock, KeybindingResolver, DEFAULT_BINDINGS |
| `src/tavern/cli/bootstrap.py` | Bootstrapper：组装 GameLoop + ModeContext |
| `tests/engine/test_action_defs.py` | §4 ActionDef + build_action tests |
| `tests/engine/test_action_registry.py` | §4 ActionRegistry tests |
| `tests/engine/test_action_handlers.py` | §4 handler wrapping tests |
| `tests/engine/test_keybindings.py` | §2 KeybindingResolver tests |
| `tests/cli/test_bootstrap.py` | Bootstrapper tests |

### Modified files

| File | Changes |
|------|---------|
| `src/tavern/world/state.py` | WorldState 新增 `player_location`, `current_location`, `npcs_at()`, `npcs_in_location`, `player_inventory` 便利属性 |
| `src/tavern/engine/modes/exploring.py` | 接入 ActionRegistry 处理自由文本 |
| `src/tavern/engine/fsm.py` | ModeContext 新增 `input_mode` 字段 |
| `src/tavern/engine/command_defs.py` | cmd_look/cmd_undo 改用 ActionRegistry 而非直接实例化 RulesEngine |

---

## Task 1: WorldState 便利属性

§4 的 `is_available` / `valid_targets` lambda 需要 `state.current_location` 等便利属性。先加上。

**Files:**
- Modify: `src/tavern/world/state.py`
- Create: `tests/world/test_state_properties.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/world/test_state_properties.py
from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def _make_state() -> WorldState:
    return WorldState(
        turn=3,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="一个温暖的大厅",
                exits={"north": Exit(target="cellar", description="通往地窖")},
                items=("old_notice",),
                npcs=("bartender",),
            ),
            "cellar": Location(
                id="cellar", name="地窖", description="阴暗的地窖",
            ),
        },
        characters={
            "player": Character(
                id="player", name="旅人", role=CharacterRole.PLAYER,
                location_id="tavern_hall", inventory=("rusty_key",),
            ),
            "bartender": Character(
                id="bartender", name="格里姆", role=CharacterRole.NPC,
                location_id="tavern_hall",
            ),
        },
        items={
            "old_notice": Item(id="old_notice", name="旧告示", description="一张旧告示"),
            "rusty_key": Item(id="rusty_key", name="生锈的钥匙", description="一把钥匙"),
        },
    )


class TestWorldStateProperties:
    def test_player_location_returns_player_location_id(self):
        state = _make_state()
        assert state.player_location == "tavern_hall"

    def test_current_location_returns_location_object(self):
        state = _make_state()
        loc = state.current_location
        assert loc.id == "tavern_hall"
        assert loc.name == "酒馆大厅"

    def test_npcs_at_returns_npcs_at_location(self):
        state = _make_state()
        npcs = state.npcs_at("tavern_hall")
        assert len(npcs) == 1
        assert npcs[0].id == "bartender"

    def test_npcs_at_excludes_player(self):
        state = _make_state()
        npcs = state.npcs_at("tavern_hall")
        ids = [n.id for n in npcs]
        assert "player" not in ids

    def test_npcs_in_location_is_shortcut(self):
        state = _make_state()
        assert state.npcs_in_location == state.npcs_at("tavern_hall")

    def test_npcs_at_empty_location(self):
        state = _make_state()
        assert state.npcs_at("cellar") == []

    def test_player_inventory_returns_item_objects(self):
        state = _make_state()
        inv = state.player_inventory
        assert len(inv) == 1
        assert inv[0].id == "rusty_key"

    def test_player_inventory_empty(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        assert state.player_inventory == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/world/test_state_properties.py -v`
Expected: FAIL with `AttributeError: 'WorldState' object has no attribute 'player_location'`

- [ ] **Step 3: Add convenience properties to WorldState**

In `src/tavern/world/state.py`, add these properties to the `WorldState` class (after the `last_action` field, before `@model_validator`):

```python
    @property
    def player_location(self) -> str:
        """当前玩家所在位置 ID"""
        return self.characters[self.player_id].location_id

    @property
    def current_location(self) -> Location:
        """当前玩家所在位置对象"""
        return self.locations[self.player_location]

    def npcs_at(self, location_id: str) -> list[Character]:
        """指定位置的 NPC 列表（不含玩家）"""
        return [
            c for c in self.characters.values()
            if c.location_id == location_id and c.id != self.player_id
        ]

    @property
    def npcs_in_location(self) -> list[Character]:
        """当前位置的 NPC（语法糖）"""
        return self.npcs_at(self.player_location)

    @property
    def player_inventory(self) -> list[Item]:
        """玩家背包物品对象列表"""
        player = self.characters[self.player_id]
        return [self.items[iid] for iid in player.inventory if iid in self.items]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/world/test_state_properties.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest --tb=short -q`
Expected: All 565+ tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/world/state.py tests/world/test_state_properties.py
git commit -m "feat: add WorldState convenience properties for §4 Action Factory"
```

---

## Task 2: ActionDef 数据类 + build_action 工厂 (§4)

**Files:**
- Create: `src/tavern/engine/action_defs.py`
- Create: `tests/engine/test_action_defs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_action_defs.py
from tavern.engine.action_defs import ActionDef, build_action, ACTION_DEFAULTS
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult
from tavern.world.state import StateDiff


class TestActionDef:
    def test_defaults_has_custom_type(self):
        assert ACTION_DEFAULTS.action_type == ActionType.CUSTOM

    def test_defaults_is_available_returns_true(self):
        assert ACTION_DEFAULTS.is_available(None) is True

    def test_defaults_valid_targets_returns_empty(self):
        assert ACTION_DEFAULTS.valid_targets(None) == []

    def test_defaults_handler_returns_success(self):
        req = ActionRequest(action=ActionType.CUSTOM)
        result, diff = ACTION_DEFAULTS.handler(req, None)
        assert result.success is True
        assert diff is None

    def test_frozen(self):
        import dataclasses
        with __import__('pytest').raises(dataclasses.FrozenInstanceError):
            ACTION_DEFAULTS.action_type = ActionType.MOVE


class TestBuildAction:
    def test_override_action_type(self):
        action = build_action(action_type=ActionType.MOVE)
        assert action.action_type == ActionType.MOVE
        # Other fields remain default
        assert action.description == ACTION_DEFAULTS.description

    def test_override_handler(self):
        def custom_handler(req, state):
            return ActionResult(success=True, action=req.action, message="custom"), None

        action = build_action(
            action_type=ActionType.LOOK,
            handler=custom_handler,
        )
        req = ActionRequest(action=ActionType.LOOK)
        result, diff = action.handler(req, None)
        assert result.message == "custom"

    def test_override_is_available(self):
        action = build_action(is_available=lambda s: False)
        assert action.is_available(None) is False

    def test_override_valid_targets(self):
        action = build_action(valid_targets=lambda s: ["a", "b"])
        assert action.valid_targets(None) == ["a", "b"]

    def test_override_requires_target(self):
        action = build_action(requires_target=True)
        assert action.requires_target is True

    def test_override_description(self):
        action = build_action(description="测试动作")
        assert action.description == "测试动作"

    def test_build_preserves_defaults_for_unset_fields(self):
        action = build_action(action_type=ActionType.MOVE, description="移动")
        assert action.cooldown_turns == 0
        assert action.requires_target is True  # default for MOVE override
        assert action.description_fn is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/engine/test_action_defs.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ActionDef + build_action**

```python
# src/tavern/engine/action_defs.py
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState

Handler = Callable[["ActionRequest", "WorldState"], tuple["ActionResult", "StateDiff | None"]]


@dataclass(frozen=True)
class ActionDef:
    action_type: ActionType
    description: str
    description_fn: Callable[["WorldState"], str] | None
    valid_targets: Callable[["WorldState"], list[str]]
    is_available: Callable[["WorldState"], bool]
    handler: Handler
    requires_target: bool = True
    cooldown_turns: int = 0


def _default_handler(req: ActionRequest, state: WorldState) -> tuple[ActionResult, StateDiff | None]:
    return ActionResult(success=True, action=req.action, message=""), None


ACTION_DEFAULTS = ActionDef(
    action_type=ActionType.CUSTOM,
    description="自定义动作",
    description_fn=None,
    valid_targets=lambda s: [],
    is_available=lambda s: True,
    handler=_default_handler,
    requires_target=False,
    cooldown_turns=0,
)


def build_action(**overrides) -> ActionDef:
    """工厂函数：只需声明与默认值不同的部分"""
    return dataclasses.replace(ACTION_DEFAULTS, **overrides)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/engine/test_action_defs.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/action_defs.py tests/engine/test_action_defs.py
git commit -m "feat: add ActionDef dataclass and build_action factory (§4)"
```

---

## Task 3: ActionRegistry (§4)

**Files:**
- Create: `src/tavern/engine/action_registry.py`
- Create: `tests/engine/test_action_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_action_registry.py
from __future__ import annotations

import pytest

from tavern.engine.action_defs import ActionDef, build_action
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionRequest, ActionResult, Character, CharacterRole, Exit, Location,
)
from tavern.world.state import StateDiff, WorldState


def _make_state(**kwargs) -> WorldState:
    defaults = dict(
        turn=0,
        player_id="player",
        locations={
            "hall": Location(
                id="hall", name="大厅", description="大厅",
                exits={"north": Exit(target="cellar")},
                npcs=("npc1",),
            ),
            "cellar": Location(id="cellar", name="地窖", description="地窖"),
        },
        characters={
            "player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="hall",
            ),
            "npc1": Character(
                id="npc1", name="NPC", role=CharacterRole.NPC,
                location_id="hall",
            ),
        },
    )
    defaults.update(kwargs)
    return WorldState(**defaults)


def _handle_move(req: ActionRequest, state: WorldState):
    return (
        ActionResult(success=True, action=ActionType.MOVE, message="moved"),
        StateDiff(updated_characters={state.player_id: {"location_id": req.target}}),
    )


def _handle_look(req: ActionRequest, state: WorldState):
    return (
        ActionResult(success=True, action=ActionType.LOOK, message="looked"),
        None,
    )


def _make_registry() -> ActionRegistry:
    move = build_action(
        action_type=ActionType.MOVE,
        description="移动",
        valid_targets=lambda s: list(s.current_location.exits.keys()),
        is_available=lambda s: len(s.current_location.exits) > 0,
        handler=_handle_move,
    )
    look = build_action(
        action_type=ActionType.LOOK,
        description="查看",
        requires_target=False,
        handler=_handle_look,
    )
    return ActionRegistry([move, look])


class TestActionRegistry:
    def test_get_available_actions(self):
        state = _make_state()
        reg = _make_registry()
        available = reg.get_available_actions(state)
        types = [a.action_type for a in available]
        assert ActionType.MOVE in types
        assert ActionType.LOOK in types

    def test_get_available_actions_filters_unavailable(self):
        # State with no exits — move should not be available
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        reg = _make_registry()
        available = reg.get_available_actions(state)
        types = [a.action_type for a in available]
        assert ActionType.MOVE not in types
        assert ActionType.LOOK in types

    def test_get_valid_targets(self):
        state = _make_state()
        reg = _make_registry()
        targets = reg.get_valid_targets(ActionType.MOVE, state)
        assert "north" in targets

    def test_get_valid_targets_unknown_action(self):
        state = _make_state()
        reg = _make_registry()
        assert reg.get_valid_targets(ActionType.TRADE, state) == []

    def test_validate_and_execute_success(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is True
        assert diff is not None

    def test_validate_and_execute_unknown_action(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.TRADE, target="npc1")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False
        assert "未知动作" in result.message

    def test_validate_and_execute_unavailable(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False

    def test_validate_and_execute_invalid_target(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="nonexistent")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False
        assert "无效目标" in result.message

    def test_validate_and_execute_no_target_required(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.LOOK)
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/engine/test_action_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ActionRegistry**

```python
# src/tavern/engine/action_registry.py
from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.action_defs import ActionDef
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState


class ActionRegistry:
    def __init__(self, actions: list[ActionDef]) -> None:
        self._actions: dict[ActionType, ActionDef] = {a.action_type: a for a in actions}

    def get(self, action_type: ActionType) -> ActionDef | None:
        return self._actions.get(action_type)

    def get_available_actions(self, state: WorldState) -> list[ActionDef]:
        return [a for a in self._actions.values() if a.is_available(state)]

    def get_valid_targets(
        self, action_type: ActionType, state: WorldState,
    ) -> list[str]:
        action = self._actions.get(action_type)
        return action.valid_targets(state) if action else []

    def validate_and_execute(
        self, request: ActionRequest, state: WorldState,
    ) -> tuple[ActionResult, StateDiff | None]:
        action = self._actions.get(request.action)
        if not action:
            return ActionResult(
                success=False, action=request.action, message="未知动作",
            ), None
        if not action.is_available(state):
            return ActionResult(
                success=False, action=request.action, message="当前无法执行此动作",
            ), None
        if action.requires_target and request.target not in action.valid_targets(state):
            return ActionResult(
                success=False, action=request.action,
                message=f"无效目标: {request.target}",
            ), None
        return action.handler(request, state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/engine/test_action_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/action_registry.py tests/engine/test_action_registry.py
git commit -m "feat: add ActionRegistry with validate_and_execute (§4)"
```

---

## Task 4: 包装现有 handler 为 ActionDef (§4)

将 `rules.py` 中的 8 个 handler 函数用 `build_action()` 包装，构建完整的 action 列表。

**Files:**
- Create: `src/tavern/engine/action_handlers.py`
- Create: `tests/engine/test_action_handlers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_action_handlers.py
from __future__ import annotations

import pytest

from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionRequest, ActionResult, Character, CharacterRole, Exit, Item, Location,
)
from tavern.world.state import WorldState


def _make_state(**overrides) -> WorldState:
    defaults = dict(
        turn=0,
        player_id="player",
        locations={
            "hall": Location(
                id="hall", name="大厅", description="大厅",
                exits={"north": Exit(target="cellar")},
                items=("old_notice",),
                npcs=("bartender",),
            ),
            "cellar": Location(id="cellar", name="地窖", description="地窖"),
        },
        characters={
            "player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="hall",
            ),
            "bartender": Character(
                id="bartender", name="格里姆", role=CharacterRole.NPC,
                location_id="hall",
            ),
        },
        items={
            "old_notice": Item(
                id="old_notice", name="旧告示", description="一张旧告示",
                portable=True,
            ),
        },
    )
    defaults.update(overrides)
    return WorldState(**defaults)


class TestBuildAllActions:
    def test_returns_list_of_action_defs(self):
        actions = build_all_actions()
        assert len(actions) >= 6  # MOVE, LOOK, SEARCH, TAKE, TALK, USE, CUSTOM at minimum

    def test_all_have_action_type(self):
        actions = build_all_actions()
        for a in actions:
            assert a.action_type is not None

    def test_no_duplicate_action_types(self):
        actions = build_all_actions()
        types = [a.action_type for a in actions]
        assert len(types) == len(set(types))


class TestMoveAction:
    def test_is_available_with_exits(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        move = registry.get(ActionType.MOVE)
        assert move.is_available(state) is True

    def test_is_available_without_exits(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        move = registry.get(ActionType.MOVE)
        assert move.is_available(state) is False

    def test_valid_targets_are_exit_directions(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.MOVE, state)
        assert "north" in targets

    def test_handler_produces_diff(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = registry.validate_and_execute(req, state)
        assert result.success is True
        assert diff is not None


class TestLookAction:
    def test_is_always_available(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        look = registry.get(ActionType.LOOK)
        assert look.is_available(state) is True

    def test_does_not_require_target(self):
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        look = registry.get(ActionType.LOOK)
        assert look.requires_target is False


class TestTalkAction:
    def test_valid_targets_are_npcs_in_location(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.TALK, state)
        assert "bartender" in targets
        assert "player" not in targets

    def test_is_available_when_npcs_present(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        talk = registry.get(ActionType.TALK)
        assert talk.is_available(state) is True


class TestTakeAction:
    def test_valid_targets_are_location_items(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.TAKE, state)
        assert "old_notice" in targets
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/engine/test_action_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement action_handlers.py**

```python
# src/tavern/engine/action_handlers.py
from __future__ import annotations

from tavern.engine.action_defs import ActionDef, build_action
from tavern.engine.actions import ActionType
from tavern.engine.rules import (
    _handle_custom,
    _handle_look,
    _handle_move,
    _handle_search,
    _handle_take,
    _handle_talk,
    _handle_use,
)


def build_all_actions() -> list[ActionDef]:
    """构建所有 ActionDef，包装现有 handler"""
    return [
        build_action(
            action_type=ActionType.MOVE,
            description="移动",
            valid_targets=lambda s: list(s.current_location.exits.keys()),
            is_available=lambda s: len(s.current_location.exits) > 0,
            handler=_handle_move,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.LOOK,
            description="查看",
            valid_targets=lambda s: (
                list(s.current_location.npcs)
                + list(s.current_location.items)
                + [c.id for c in s.characters.values() if c.id != s.player_id]
            ),
            is_available=lambda s: True,
            handler=_handle_look,
            requires_target=False,
        ),
        build_action(
            action_type=ActionType.SEARCH,
            description="搜索",
            is_available=lambda s: True,
            handler=_handle_search,
            requires_target=False,
        ),
        build_action(
            action_type=ActionType.TAKE,
            description="拾取",
            valid_targets=lambda s: [
                item_id for item_id in s.current_location.items
                if item_id in s.items and s.items[item_id].portable
            ],
            is_available=lambda s: len(s.current_location.items) > 0,
            handler=_handle_take,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.TALK,
            description="交谈",
            valid_targets=lambda s: [n.id for n in s.npcs_in_location],
            is_available=lambda s: len(s.npcs_in_location) > 0,
            handler=_handle_talk,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.PERSUADE,
            description="说服",
            valid_targets=lambda s: [n.id for n in s.npcs_in_location],
            is_available=lambda s: len(s.npcs_in_location) > 0,
            handler=_handle_talk,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.USE,
            description="使用",
            valid_targets=lambda s: list(
                s.characters[s.player_id].inventory
            ),
            is_available=lambda s: len(s.characters[s.player_id].inventory) > 0,
            handler=_handle_use,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.CUSTOM,
            description="自定义",
            is_available=lambda s: True,
            handler=_handle_custom,
            requires_target=False,
        ),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/engine/test_action_handlers.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/action_handlers.py tests/engine/test_action_handlers.py
git commit -m "feat: wrap existing handlers into ActionDef via build_action (§4)"
```

---

## Task 5: KeybindingResolver (§2)

**Files:**
- Create: `src/tavern/engine/keybindings.py`
- Create: `tests/engine/test_keybindings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_keybindings.py
from tavern.engine.fsm import GameMode, Keybinding
from tavern.engine.keybindings import (
    DEFAULT_BINDINGS, InputMode, KeybindingBlock, KeybindingResolver,
)


class TestInputMode:
    def test_hotkey_value(self):
        assert InputMode.HOTKEY.value == "hotkey"

    def test_text_value(self):
        assert InputMode.TEXT.value == "text"


class TestKeybindingResolver:
    def _make_resolver(self) -> KeybindingResolver:
        return KeybindingResolver(DEFAULT_BINDINGS)

    def test_resolve_hotkey_mode_exploring(self):
        resolver = self._make_resolver()
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action == "move_north"

    def test_resolve_hotkey_mode_unknown_key(self):
        resolver = self._make_resolver()
        action = resolver.resolve("z", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action is None

    def test_resolve_text_mode_ignores_hotkeys(self):
        resolver = self._make_resolver()
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.TEXT)
        assert action is None

    def test_resolve_text_mode_with_allow_in_text_and_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "1", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=True,
        )
        assert action == "select_hint_1"

    def test_resolve_text_mode_allow_in_text_non_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "1", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=False,
        )
        assert action is None

    def test_resolve_escape_in_text_mode_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "escape", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=True,
        )
        assert action == "end_dialogue"

    def test_resolve_hotkey_mode_combat(self):
        resolver = self._make_resolver()
        action = resolver.resolve("a", GameMode.COMBAT, InputMode.HOTKEY)
        assert action == "attack"

    def test_resolve_no_bindings_for_mode(self):
        resolver = KeybindingResolver([])
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action is None


class TestDefaultBindings:
    def test_exploring_has_direction_keys(self):
        exploring = [b for b in DEFAULT_BINDINGS if b.context == GameMode.EXPLORING]
        assert len(exploring) == 1
        keys = {kb.key for kb in exploring[0].bindings}
        assert {"n", "s", "e", "w"}.issubset(keys)

    def test_dialogue_has_hint_keys(self):
        dialogue = [b for b in DEFAULT_BINDINGS if b.context == GameMode.DIALOGUE]
        assert len(dialogue) == 1
        keys = {kb.key for kb in dialogue[0].bindings}
        assert {"1", "2", "3", "escape"}.issubset(keys)

    def test_combat_has_action_keys(self):
        combat = [b for b in DEFAULT_BINDINGS if b.context == GameMode.COMBAT]
        assert len(combat) == 1
        keys = {kb.key for kb in combat[0].bindings}
        assert {"a", "d", "r"}.issubset(keys)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/engine/test_keybindings.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement keybindings.py**

```python
# src/tavern/engine/keybindings.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tavern.engine.fsm import GameMode, Keybinding


class InputMode(Enum):
    HOTKEY = "hotkey"
    TEXT = "text"


@dataclass(frozen=True)
class KeybindingBlock:
    context: GameMode
    bindings: tuple[Keybinding, ...]


DEFAULT_BINDINGS: list[KeybindingBlock] = [
    KeybindingBlock(
        context=GameMode.EXPLORING,
        bindings=(
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
            Keybinding("ctrl+s", "save_game", "保存游戏"),
        ),
    ),
    KeybindingBlock(
        context=GameMode.DIALOGUE,
        bindings=(
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
        ),
    ),
    KeybindingBlock(
        context=GameMode.COMBAT,
        bindings=(
            Keybinding("a", "attack", "攻击"),
            Keybinding("d", "defend", "防御"),
            Keybinding("r", "run_away", "逃跑"),
            Keybinding("1", "use_skill_1", "使用技能1"),
            Keybinding("2", "use_skill_2", "使用技能2"),
        ),
    ),
]


class KeybindingResolver:
    def __init__(self, blocks: list[KeybindingBlock]) -> None:
        self._by_context: dict[GameMode, dict[str, str]] = {}
        self._text_shortcuts: dict[GameMode, dict[str, str]] = {}
        for block in blocks:
            hotkey_map: dict[str, str] = {}
            text_map: dict[str, str] = {}
            for kb in block.bindings:
                hotkey_map[kb.key] = kb.action
                if kb.allow_in_text:
                    text_map[kb.key] = kb.action
            self._by_context[block.context] = hotkey_map
            self._text_shortcuts[block.context] = text_map

    def resolve(
        self,
        key: str,
        game_mode: GameMode,
        input_mode: InputMode,
        buffer_empty: bool = False,
    ) -> str | None:
        if input_mode == InputMode.TEXT:
            if not buffer_empty:
                return None
            context_bindings = self._text_shortcuts.get(game_mode, {})
            return context_bindings.get(key)
        context_bindings = self._by_context.get(game_mode, {})
        return context_bindings.get(key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/engine/test_keybindings.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/keybindings.py tests/engine/test_keybindings.py
git commit -m "feat: add InputMode, KeybindingResolver, DEFAULT_BINDINGS (§2)"
```

---

## Task 6: Bootstrapper — 组装 GameLoop + ModeContext

将 `GameApp.__init__` 中散落的组装逻辑收拢到一个 `bootstrap()` 函数中。

**Files:**
- Create: `src/tavern/cli/bootstrap.py`
- Create: `tests/cli/test_bootstrap.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cli/test_bootstrap.py
from __future__ import annotations

from unittest.mock import MagicMock

from tavern.cli.bootstrap import bootstrap
from tavern.engine.fsm import GameLoop, GameMode


class TestBootstrap:
    def test_returns_game_loop(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert isinstance(loop, GameLoop)

    def test_loop_starts_in_exploring(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert loop.current_mode == GameMode.EXPLORING

    def test_loop_has_exploring_handler(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert GameMode.EXPLORING in loop._handlers

    def test_loop_has_dialogue_handler(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert GameMode.DIALOGUE in loop._handlers

    def test_loop_has_all_effect_executors(self):
        from tavern.engine.fsm import EffectKind
        deps = _make_deps()
        loop = bootstrap(**deps)
        for kind in EffectKind:
            assert kind in loop._effect_executors


def _make_deps() -> dict:
    return dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        logger=MagicMock(),
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/cli/test_bootstrap.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement bootstrap.py**

```python
# src/tavern/cli/bootstrap.py
from __future__ import annotations

from typing import Any

from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.command_defs import register_all_commands
from tavern.engine.commands import CommandRegistry
from tavern.engine.effects import EFFECT_EXECUTORS
from tavern.engine.fsm import GameLoop, GameMode, ModeContext
from tavern.engine.modes.dialogue import DialogueModeHandler
from tavern.engine.modes.exploring import ExploringModeHandler


def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    logger: Any,
) -> GameLoop:
    """组装 GameLoop 所需的全部组件"""
    # Command Registry
    command_registry = CommandRegistry()
    register_all_commands(command_registry)

    # Action Registry
    action_registry = ActionRegistry(build_all_actions())

    # Mode Context
    context = ModeContext(
        state_manager=state_manager,
        renderer=renderer,
        dialogue_manager=dialogue_manager,
        narrator=narrator,
        memory=memory,
        persistence=persistence,
        story_engine=story_engine,
        command_registry=command_registry,
        action_registry=action_registry,
        logger=logger,
    )

    # Mode Handlers
    handlers = {
        GameMode.EXPLORING: ExploringModeHandler(),
        GameMode.DIALOGUE: DialogueModeHandler(),
    }

    return GameLoop(
        handlers=handlers,
        context=context,
        effect_executors=dict(EFFECT_EXECUTORS),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/cli/test_bootstrap.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/cli/bootstrap.py tests/cli/test_bootstrap.py
git commit -m "feat: add bootstrap() function to assemble GameLoop (§1)"
```

---

## Task 7: 更新 command_defs 使用 ActionRegistry

cmd_look 和 cmd_undo 当前直接实例化 `RulesEngine()`。改为通过 `CommandContext` 获取 action_registry。

**Files:**
- Modify: `src/tavern/engine/commands.py` (CommandContext 新增 action_registry 字段)
- Modify: `src/tavern/engine/command_defs.py`

- [ ] **Step 1: Add action_registry to CommandContext**

In `src/tavern/engine/commands.py`, add `action_registry` field to `CommandContext`:

```python
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
    action_registry: Any = None  # ActionRegistry, optional for backward compat
```

- [ ] **Step 2: Update cmd_look and cmd_undo in command_defs.py**

Replace `cmd_look`:

```python
async def cmd_look(args: str, ctx: CommandContext) -> None:
    if args:
        request = ActionRequest(action=ActionType.LOOK, target=args)
    else:
        request = ActionRequest(action=ActionType.LOOK)
    if ctx.action_registry is not None:
        result, _ = ctx.action_registry.validate_and_execute(
            request, ctx.state_manager.state,
        )
    else:
        from tavern.engine.rules import RulesEngine
        rules = RulesEngine()
        result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(result)
```

Replace `cmd_undo`:

```python
async def cmd_undo(args: str, ctx: CommandContext) -> None:
    result = ctx.state_manager.undo()
    if result is None:
        ctx.renderer.console.print("\n[red]没有可以回退的步骤。[/]\n")
        return
    ctx.renderer.console.print("\n[dim]已回退上一步。[/]\n")
    request = ActionRequest(action=ActionType.LOOK)
    if ctx.action_registry is not None:
        look_result, _ = ctx.action_registry.validate_and_execute(
            request, ctx.state_manager.state,
        )
    else:
        from tavern.engine.rules import RulesEngine
        rules = RulesEngine()
        look_result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(look_result)
```

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/tavern/engine/commands.py src/tavern/engine/command_defs.py
git commit -m "refactor: cmd_look/cmd_undo use ActionRegistry when available (§4)"
```

---

## Task 8: Full integration verification

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 2: Run with coverage**

Run: `python3 -m pytest --cov=tavern --cov-report=term-missing --tb=short -q`
Expected: New modules have 80%+ coverage

- [ ] **Step 3: Verify all imports**

```bash
python3 -c "
from tavern.engine.action_defs import ActionDef, build_action
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.action_handlers import build_all_actions
from tavern.engine.keybindings import InputMode, KeybindingResolver, DEFAULT_BINDINGS
from tavern.cli.bootstrap import bootstrap
print('All Phase 2 modules import successfully')
"
```

- [ ] **Step 4: Verify ActionRegistry replaces RulesEngine validation**

```bash
python3 -c "
from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, Character, CharacterRole, Exit, Location
from tavern.world.state import WorldState

state = WorldState(
    player_id='player',
    locations={'hall': Location(id='hall', name='H', description='d', exits={'n': Exit(target='c')}, npcs=('npc1',)),'c': Location(id='c', name='C', description='c')},
    characters={'player': Character(id='player', name='P', role=CharacterRole.PLAYER, location_id='hall'),'npc1': Character(id='npc1', name='N', role=CharacterRole.NPC, location_id='hall')},
)
reg = ActionRegistry(build_all_actions())
print('Available:', [a.action_type.value for a in reg.get_available_actions(state)])
print('Move targets:', reg.get_valid_targets(ActionType.MOVE, state))
print('Talk targets:', reg.get_valid_targets(ActionType.TALK, state))
r, d = reg.validate_and_execute(ActionRequest(action=ActionType.MOVE, target='n'), state)
print('Move result:', r.success, r.message[:30])
print('Phase 2 integration OK')
"
```

- [ ] **Step 5: Commit if any fixes needed**

```bash
git add -u
git commit -m "fix: integration fixes for Phase 2"
```

---

## What Phase 2 does NOT include (deferred to Phase 3-4 plans)

| Deferred | Phase | Reason |
|----------|-------|--------|
| §3 Markdown-as-Code (ContentLoader, variant files) | Phase 3 | Independent content system |
| §9 分类记忆 (ClassifiedMemorySystem, MemoryExtractor) | Phase 3 | Depends on on_change |
| §10 场景缓存 (SceneContextCache, CachedPromptBuilder) | Phase 4 | Depends on §3 + §5 |
| §8 游戏日志 (GameLogger, /journal) | Phase 4 | Depends on §5 on_change |
| Full app.py main loop replacement with GameLoop.run() | Phase 3 | Needs §3 ContentLoader + §9 Memory wired first |
| Chord 支持 (ChordState, resolve_with_chord) | 二期 | Spec explicitly marks as 二期 |
| 用户自定义快捷键 (config.yaml override) | 二期 | Nice-to-have, not core |
| TRADE/GIVE/STEALTH/COMBAT handler 实现 | 后续 | Spec 未定义 handler 逻辑，只声明了接口 |
| prompt_toolkit 集成 KeybindingResolver | Phase 3 | Needs app.py refactor to GameLoop first |
