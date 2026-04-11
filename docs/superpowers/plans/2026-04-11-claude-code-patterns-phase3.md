# Phase 3: FSM 集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Phase 1-2 architecture (GameLoop, ModeHandler, ActionRegistry, Effects) into the actual game so `GameApp` delegates to `GameLoop.run()` and players can explore + dialogue through the new FSM.

**Architecture:** Bottom-up integration — unify types first, implement effect executors, migrate handler logic from `app.py`, then swap `GameApp.run()` to call `GameLoop`. Each layer is independently testable.

**Tech Stack:** Python 3.14, Pydantic, pytest, pytest-asyncio, unittest.mock

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/tavern/engine/commands.py` | Delete `CommandContext`, update `handle_command` signature |
| Modify | `src/tavern/engine/command_defs.py` | All command fns: `CommandContext` → `ModeContext` |
| Modify | `src/tavern/engine/fsm.py` | `ModeContext.action_registry` type: `Any` → `ActionRegistry \| None` |
| Modify | `src/tavern/engine/effects.py` | Implement `exec_start_dialogue`, `exec_end_dialogue`, `exec_apply_trust`, `exec_emit_event` |
| Modify | `src/tavern/engine/modes/exploring.py` | Free-text input → intent parse → action → narrator → SideEffects |
| Modify | `src/tavern/engine/modes/dialogue.py` | Constructor injection, LLM dialogue → trust → exit detection |
| Modify | `src/tavern/cli/bootstrap.py` | Pass `dialogue_manager` to `DialogueModeHandler`, add `intent_parser` to `ModeContext` |
| Modify | `src/tavern/cli/app.py` | Thin shell: `__init__` + `bootstrap()` → `GameLoop.run()` |
| Create | `tests/engine/test_command_defs.py` | Tests for command functions with `ModeContext` |
| Modify | `tests/engine/test_effects.py` | Tests for real executor logic |
| Modify | `tests/engine/test_modes_exploring.py` | Tests for free-text flow |
| Modify | `tests/engine/test_modes_dialogue.py` | Tests for dialogue flow |
| Modify | `tests/cli/test_bootstrap.py` | Update for `DialogueModeHandler` constructor change |

---

### Task 1: Delete CommandContext, unify to ModeContext

**Files:**
- Modify: `src/tavern/engine/commands.py:1-76`
- Modify: `src/tavern/engine/command_defs.py:1-142`
- Modify: `src/tavern/engine/fsm.py:61-72`
- Create: `tests/engine/test_command_defs.py`

- [ ] **Step 1: Add `ActionRegistry | None` type to ModeContext**

In `src/tavern/engine/fsm.py`, change the `action_registry` field and add the import:

```python
# fsm.py — add to TYPE_CHECKING block
if TYPE_CHECKING:
    from tavern.engine.action_registry import ActionRegistry
    from tavern.engine.commands import CommandRegistry
    from tavern.world.state import ReactiveStateManager, WorldState

# fsm.py — ModeContext dataclass
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
    action_registry: ActionRegistry | None
    logger: Any
```

- [ ] **Step 2: Delete CommandContext from commands.py**

Replace the entire `commands.py` with `CommandContext` removed. `handle_command` now takes `ModeContext`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext


@dataclass(frozen=True)
class GameCommand:
    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    is_hidden: bool = False
    available_in: tuple = ()
    is_available: Callable[[Any], bool] = lambda _: True
    execute: Callable[[str, ModeContext], Awaitable[None]] = field(default=None)


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
        self, raw: str, mode: Any, ctx: ModeContext
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

- [ ] **Step 3: Update command_defs.py to use ModeContext**

Replace all `CommandContext` references with `ModeContext`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.engine.commands import CommandRegistry, GameCommand
from tavern.engine.fsm import GameMode
from tavern.world.models import ActionRequest

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext


async def cmd_look(args: str, ctx: ModeContext) -> None:
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


async def cmd_inventory(args: str, ctx: ModeContext) -> None:
    ctx.renderer.render_inventory(ctx.state_manager.state)


async def cmd_status(args: str, ctx: ModeContext) -> None:
    relationships = ctx.memory.get_player_relationships(
        ctx.state_manager.state.player_id
    )
    ctx.renderer.render_status(ctx.state_manager.state, relationships)


async def cmd_hint(args: str, ctx: ModeContext) -> None:
    ctx.renderer.console.print(
        "\n[dim italic]尝试和酒馆里的人聊聊天，也许能发现什么线索...[/]\n"
    )


async def cmd_undo(args: str, ctx: ModeContext) -> None:
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


async def cmd_help(args: str, ctx: ModeContext) -> None:
    ctx.renderer.render_help()


async def cmd_save(args: str, ctx: ModeContext) -> None:
    slot = args.strip() if args.strip() else "auto"
    try:
        new_state = ctx.memory.sync_to_state(ctx.state_manager.state)
        path = ctx.persistence.save(new_state, slot)
        ctx.renderer.render_save_success(slot, path)
    except OSError as e:
        ctx.renderer.console.print(f"\n[red]存档失败：{e}[/]\n")


async def cmd_saves(args: str, ctx: ModeContext) -> None:
    saves = ctx.persistence.list_saves()
    ctx.renderer.render_saves_list(saves)


async def cmd_load(args: str, ctx: ModeContext) -> None:
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


async def cmd_quit(args: str, ctx: ModeContext) -> None:
    raise SystemExit(0)


_ALL_MODES = tuple(GameMode)
_EXPLORING = (GameMode.EXPLORING,)


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

- [ ] **Step 4: Write tests for command functions with ModeContext**

Create `tests/engine/test_command_defs.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from tavern.engine.command_defs import (
    cmd_help,
    cmd_hint,
    cmd_inventory,
    cmd_look,
    cmd_quit,
    cmd_save,
    cmd_saves,
    cmd_load,
    cmd_status,
    cmd_undo,
    register_all_commands,
)
from tavern.engine.commands import CommandRegistry
from tavern.engine.fsm import ModeContext
from tavern.world.models import ActionResult
from tavern.engine.actions import ActionType


def _make_ctx(**overrides) -> ModeContext:
    state = MagicMock()
    state.player_id = "player"
    sm = MagicMock()
    type(sm).state = PropertyMock(return_value=state)
    defaults = dict(
        state_manager=sm,
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=None,
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


class TestCmdLook:
    @pytest.mark.asyncio
    async def test_uses_action_registry_when_present(self):
        ar = MagicMock()
        ar.validate_and_execute.return_value = (
            ActionResult(success=True, action=ActionType.LOOK, message="ok"), None,
        )
        ctx = _make_ctx(action_registry=ar)
        await cmd_look("", ctx)
        ar.validate_and_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_rules_engine(self):
        ctx = _make_ctx(action_registry=None)
        await cmd_look("", ctx)
        ctx.renderer.render_result.assert_called_once()


class TestCmdInventory:
    @pytest.mark.asyncio
    async def test_renders_inventory(self):
        ctx = _make_ctx()
        await cmd_inventory("", ctx)
        ctx.renderer.render_inventory.assert_called_once()


class TestCmdStatus:
    @pytest.mark.asyncio
    async def test_renders_status(self):
        ctx = _make_ctx()
        await cmd_status("", ctx)
        ctx.renderer.render_status.assert_called_once()


class TestCmdUndo:
    @pytest.mark.asyncio
    async def test_undo_no_history(self):
        ctx = _make_ctx()
        ctx.state_manager.undo.return_value = None
        await cmd_undo("", ctx)
        ctx.renderer.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_undo_success(self):
        ctx = _make_ctx()
        ctx.state_manager.undo.return_value = MagicMock()
        await cmd_undo("", ctx)
        ctx.renderer.render_result.assert_called_once()


class TestCmdSave:
    @pytest.mark.asyncio
    async def test_save_default_slot(self):
        ctx = _make_ctx()
        await cmd_save("", ctx)
        ctx.persistence.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_named_slot(self):
        ctx = _make_ctx()
        await cmd_save("slot1", ctx)
        ctx.persistence.save.assert_called_once()


class TestCmdLoad:
    @pytest.mark.asyncio
    async def test_load_blocks_during_dialogue(self):
        dm = MagicMock()
        dm.is_active = True
        ctx = _make_ctx(dialogue_manager=dm)
        await cmd_load("", ctx)
        ctx.persistence.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_success(self):
        dm = MagicMock()
        dm.is_active = False
        ctx = _make_ctx(dialogue_manager=dm)
        ctx.persistence.load.return_value = (MagicMock(), "2026-01-01")
        await cmd_load("", ctx)
        ctx.state_manager.replace.assert_called_once()


class TestCmdQuit:
    @pytest.mark.asyncio
    async def test_raises_system_exit(self):
        ctx = _make_ctx()
        with pytest.raises(SystemExit):
            await cmd_quit("", ctx)


class TestRegisterAllCommands:
    def test_registers_all_commands(self):
        registry = CommandRegistry()
        register_all_commands(registry)
        expected = {"/look", "/inventory", "/status", "/hint", "/undo",
                    "/help", "/save", "/saves", "/load", "/quit"}
        for name in expected:
            assert registry.find(name) is not None, f"Missing: {name}"
```

- [ ] **Step 5: Run tests to verify**

Run: `pytest tests/engine/test_command_defs.py tests/engine/test_commands.py tests/engine/test_modes_exploring.py tests/engine/test_modes_dialogue.py tests/cli/test_bootstrap.py -v`

Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`

Expected: All 624+ tests pass, 0 failures

- [ ] **Step 7: Commit**

```bash
git add src/tavern/engine/commands.py src/tavern/engine/command_defs.py src/tavern/engine/fsm.py tests/engine/test_command_defs.py
git commit -m "refactor: delete CommandContext, unify to ModeContext (§1)"
```

---

### Task 2: Implement effect executors for Exploring + Dialogue

**Files:**
- Modify: `src/tavern/engine/effects.py:1-69`
- Modify: `tests/engine/test_effects.py:1-12`

- [ ] **Step 1: Write failing tests for effect executors**

Replace `tests/engine/test_effects.py` with comprehensive tests:

```python
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from tavern.engine.effects import (
    EFFECT_EXECUTORS,
    exec_apply_diff,
    exec_apply_trust,
    exec_emit_event,
    exec_end_dialogue,
    exec_start_dialogue,
)
from tavern.engine.fsm import EffectKind, ModeContext
from tavern.world.models import Character, CharacterRole


def _make_ctx(**overrides) -> ModeContext:
    state = MagicMock()
    sm = MagicMock()
    type(sm).state = PropertyMock(return_value=state)
    defaults = dict(
        state_manager=sm,
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=None,
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


class TestEffectExecutors:
    def test_all_effect_kinds_have_executors(self):
        for kind in EffectKind:
            assert kind in EFFECT_EXECUTORS, f"Missing executor for {kind}"

    def test_all_executors_are_callable(self):
        for kind, executor in EFFECT_EXECUTORS.items():
            assert callable(executor), f"Executor for {kind} is not callable"


class TestExecStartDialogue:
    @pytest.mark.asyncio
    async def test_raises_on_unknown_npc(self):
        ctx = _make_ctx()
        ctx.state_manager.state.characters = {}
        with pytest.raises(ValueError, match="NPC not found"):
            await exec_start_dialogue({"npc_id": "unknown"}, ctx)

    @pytest.mark.asyncio
    async def test_calls_dialogue_manager_start_context(self):
        npc = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern",
        )
        ctx = _make_ctx()
        ctx.state_manager.state.characters = {"grim": npc}
        dm = MagicMock()
        ctx.dialogue_manager = dm
        await exec_start_dialogue({"npc_id": "grim"}, ctx)
        dm.set_active_npc.assert_called_once_with("grim")


class TestExecEndDialogue:
    @pytest.mark.asyncio
    async def test_calls_dialogue_manager_reset(self):
        ctx = _make_ctx()
        dm = MagicMock()
        ctx.dialogue_manager = dm
        await exec_end_dialogue({"npc_id": "grim"}, ctx)
        dm.reset.assert_called_once()


class TestExecApplyTrust:
    @pytest.mark.asyncio
    async def test_commits_trust_diff(self):
        npc = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats=MappingProxyType({"trust": 10}),
        )
        ctx = _make_ctx()
        ctx.state_manager.state.characters = {"grim": npc}
        ctx.state_manager.state.player_id = "player"
        await exec_apply_trust({"npc_id": "grim", "delta": 5}, ctx)
        ctx.state_manager.commit.assert_called_once()
        call_args = ctx.state_manager.commit.call_args
        diff = call_args[0][0]
        assert "grim" in diff.updated_characters

    @pytest.mark.asyncio
    async def test_clamps_trust_to_range(self):
        npc = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats=MappingProxyType({"trust": 95}),
        )
        ctx = _make_ctx()
        ctx.state_manager.state.characters = {"grim": npc}
        ctx.state_manager.state.player_id = "player"
        await exec_apply_trust({"npc_id": "grim", "delta": 20}, ctx)
        call_args = ctx.state_manager.commit.call_args
        diff = call_args[0][0]
        new_stats = diff.updated_characters["grim"]["stats"]
        assert new_stats["trust"] == 100


class TestExecEmitEvent:
    @pytest.mark.asyncio
    async def test_calls_story_engine_check(self):
        ctx = _make_ctx()
        se = MagicMock()
        se.check.return_value = []
        ctx.story_engine = se
        await exec_emit_event({"event": "quest_started"}, ctx)
        se.check.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_story_engine(self):
        ctx = _make_ctx(story_engine=None)
        await exec_emit_event({"event": "quest_started"}, ctx)


class TestExecApplyDiff:
    @pytest.mark.asyncio
    async def test_commits_diff(self):
        ctx = _make_ctx()
        diff = MagicMock()
        await exec_apply_diff({"diff": diff, "action": "test"}, ctx)
        ctx.state_manager.commit.assert_called_once_with(diff, "test")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_effects.py -v`

Expected: `TestExecStartDialogue`, `TestExecEndDialogue`, `TestExecApplyTrust`, `TestExecEmitEvent` FAIL (executor methods don't have the real logic yet)

- [ ] **Step 3: Implement effect executors**

Replace `src/tavern/engine/effects.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import EffectExecutor, EffectKind
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext

logger = logging.getLogger(__name__)


async def exec_start_dialogue(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        raise ValueError(f"NPC not found: {npc_id}")
    if hasattr(ctx.dialogue_manager, "set_active_npc"):
        ctx.dialogue_manager.set_active_npc(npc_id)
    logger.info("Starting dialogue with %s", npc_id)


async def exec_end_dialogue(payload: dict, ctx: ModeContext) -> None:
    if hasattr(ctx.dialogue_manager, "reset"):
        ctx.dialogue_manager.reset()
    logger.info("Ending dialogue")


async def exec_apply_diff(payload: dict, ctx: ModeContext) -> None:
    diff = payload["diff"]
    action = payload.get("action")
    ctx.state_manager.commit(diff, action)


async def exec_emit_event(payload: dict, ctx: ModeContext) -> None:
    event = payload["event"]
    logger.info("Event emitted: %s", event)
    if ctx.story_engine is not None and hasattr(ctx.story_engine, "check"):
        state = ctx.state_manager.state
        memory = ctx.memory
        timeline = memory._timeline if hasattr(memory, "_timeline") else ()
        rel_graph = memory._relationship_graph if hasattr(memory, "_relationship_graph") else {}
        ctx.story_engine.check(state, event, timeline, rel_graph)


async def exec_apply_trust(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    delta = payload["delta"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        logger.warning("exec_apply_trust: NPC %s not found", npc_id)
        return
    old_trust = int(npc.stats.get("trust", 0))
    new_trust = max(-100, min(100, old_trust + delta))
    new_stats = {**dict(npc.stats), "trust": new_trust}
    trust_diff = StateDiff(
        updated_characters={npc_id: {"stats": new_stats}},
        relationship_changes=(
            {"src": state.player_id, "tgt": npc_id, "delta": delta},
        ),
        turn_increment=0,
    )
    ctx.state_manager.commit(trust_diff, None)


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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_effects.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/effects.py tests/engine/test_effects.py
git commit -m "feat: implement effect executors for dialogue + trust + events (§2)"
```

---

### Task 3: Add intent_parser to ModeContext

**Files:**
- Modify: `src/tavern/engine/fsm.py:61-72`
- Modify: `src/tavern/cli/bootstrap.py:1-53`
- Modify: `tests/cli/test_bootstrap.py`
- Modify: `tests/engine/test_modes_exploring.py` (update `_make_context` helper)
- Modify: `tests/engine/test_modes_dialogue.py` (update `_make_context` helper)

The ExploringModeHandler needs an `intent_parser` to parse free text. We need to add it to `ModeContext` and `bootstrap()`.

- [ ] **Step 1: Add intent_parser field to ModeContext**

In `src/tavern/engine/fsm.py`:

```python
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
    action_registry: ActionRegistry | None
    intent_parser: Any
    logger: Any
```

- [ ] **Step 2: Update bootstrap() to accept and pass intent_parser**

In `src/tavern/cli/bootstrap.py`:

```python
def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    intent_parser: Any,
    logger: Any,
) -> GameLoop:
    command_registry = CommandRegistry()
    register_all_commands(command_registry)

    action_registry = ActionRegistry(build_all_actions())

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
        intent_parser=intent_parser,
        logger=logger,
    )

    handlers = {
        GameMode.EXPLORING: ExploringModeHandler(),
        GameMode.DIALOGUE: DialogueModeHandler(dialogue_manager=dialogue_manager),
    }

    return GameLoop(
        handlers=handlers,
        context=context,
        effect_executors=dict(EFFECT_EXECUTORS),
    )
```

- [ ] **Step 3: Update test helpers to include intent_parser**

In `tests/cli/test_bootstrap.py`, update `_make_deps`:

```python
def _make_deps() -> dict:
    return dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        intent_parser=MagicMock(),
        logger=MagicMock(),
    )
```

In `tests/engine/test_modes_exploring.py` and `tests/engine/test_modes_dialogue.py`, add `intent_parser=MagicMock()` to the `_make_context` defaults dict.

In `tests/engine/test_command_defs.py`, add `intent_parser=MagicMock()` to the `_make_ctx` defaults dict.

In `tests/engine/test_effects.py`, add `intent_parser=MagicMock()` to the `_make_ctx` defaults dict.

- [ ] **Step 4: Run tests**

Run: `pytest tests/cli/test_bootstrap.py tests/engine/test_modes_exploring.py tests/engine/test_modes_dialogue.py tests/engine/test_command_defs.py tests/engine/test_effects.py -v`

Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/fsm.py src/tavern/cli/bootstrap.py tests/
git commit -m "feat: add intent_parser to ModeContext and bootstrap (§3 prep)"
```

---

### Task 4: Migrate ExploringModeHandler free-text logic

**Files:**
- Modify: `src/tavern/engine/modes/exploring.py:1-58`
- Modify: `tests/engine/test_modes_exploring.py`

- [ ] **Step 1: Write failing tests for free-text flow**

Add tests to `tests/engine/test_modes_exploring.py`:

```python
class TestExploringFreeText:
    @pytest.mark.asyncio
    async def test_parse_and_execute_action(self):
        """Free text → intent parser → action registry → side effects."""
        parser = AsyncMock()
        parser.parse.return_value = ActionRequest(
            action=ActionType.MOVE, target="north",
        )
        ar = MagicMock()
        diff = MagicMock()
        ar.validate_and_execute.return_value = (
            ActionResult(success=True, action=ActionType.MOVE, message="moved"),
            diff,
        )
        narrator = MagicMock()
        narrator.stream_narrative = AsyncMock(return_value=_async_gen(["You walk north."]))
        renderer = MagicMock()
        renderer.render_stream = AsyncMock()
        renderer.render_status_bar = MagicMock()

        state = _make_state(
            characters={"player": Character(
                id="player", name="Player", role=CharacterRole.PLAYER,
                location_id="tavern",
            )},
            locations={"tavern": Location(
                id="tavern", name="Tavern", description="A tavern",
            )},
        )
        ctx = _make_context(
            intent_parser=parser,
            action_registry=ar,
            narrator=narrator,
            renderer=renderer,
        )
        handler = ExploringModeHandler()
        result = await handler.handle_input("go north", state, ctx)

        parser.parse.assert_awaited_once()
        ar.validate_and_execute.assert_called_once()
        assert any(
            e.kind == EffectKind.APPLY_DIFF for e in result.side_effects
        )

    @pytest.mark.asyncio
    async def test_talk_action_triggers_dialogue_transition(self):
        """TALK action → START_DIALOGUE effect + next_mode=DIALOGUE."""
        parser = AsyncMock()
        parser.parse.return_value = ActionRequest(
            action=ActionType.TALK, target="grim",
        )
        ar = MagicMock()
        ar.validate_and_execute.return_value = (
            ActionResult(success=True, action=ActionType.TALK, message="ok", target="grim"),
            None,
        )
        narrator = MagicMock()
        narrator.stream_narrative = AsyncMock(return_value=_async_gen(["talking"]))
        renderer = MagicMock()
        renderer.render_stream = AsyncMock()
        renderer.render_status_bar = MagicMock()

        state = _make_state(
            characters={
                "player": Character(
                    id="player", name="Player", role=CharacterRole.PLAYER,
                    location_id="tavern",
                ),
                "grim": Character(
                    id="grim", name="Grim", role=CharacterRole.NPC,
                    location_id="tavern",
                ),
            },
            locations={"tavern": Location(
                id="tavern", name="Tavern", description="A tavern",
                npcs=("grim",),
            )},
        )
        ctx = _make_context(
            intent_parser=parser,
            action_registry=ar,
            narrator=narrator,
            renderer=renderer,
        )
        handler = ExploringModeHandler()
        result = await handler.handle_input("talk to grim", state, ctx)

        assert result.next_mode == GameMode.DIALOGUE
        assert any(
            e.kind == EffectKind.START_DIALOGUE for e in result.side_effects
        )

    @pytest.mark.asyncio
    async def test_failed_action_renders_result_no_effects(self):
        """Failed action → render result, no side effects."""
        parser = AsyncMock()
        parser.parse.return_value = ActionRequest(
            action=ActionType.MOVE, target="nowhere",
        )
        ar = MagicMock()
        ar.validate_and_execute.return_value = (
            ActionResult(success=False, action=ActionType.MOVE, message="no exit"),
            None,
        )
        renderer = MagicMock()
        renderer.render_result = MagicMock()

        state = _make_state(
            characters={"player": Character(
                id="player", name="Player", role=CharacterRole.PLAYER,
                location_id="tavern",
            )},
            locations={"tavern": Location(
                id="tavern", name="Tavern", description="A tavern",
            )},
        )
        ctx = _make_context(
            intent_parser=parser,
            action_registry=ar,
            renderer=renderer,
        )
        handler = ExploringModeHandler()
        result = await handler.handle_input("go nowhere", state, ctx)

        assert result.side_effects == ()
        renderer.render_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_intent_renders_error(self):
        """Parser returns CUSTOM with is_fallback → render error message."""
        parser = AsyncMock()
        parser.parse.return_value = ActionRequest(
            action=ActionType.CUSTOM, detail="gibberish",
            confidence=0.1, is_fallback=True,
        )
        ar = MagicMock()
        ar.validate_and_execute.return_value = (
            ActionResult(success=True, action=ActionType.CUSTOM, message="ok"),
            None,
        )
        renderer = MagicMock()
        renderer.render_result = MagicMock()

        state = _make_state(
            characters={"player": Character(
                id="player", name="Player", role=CharacterRole.PLAYER,
                location_id="tavern",
            )},
            locations={"tavern": Location(
                id="tavern", name="Tavern", description="A tavern",
            )},
        )
        ctx = _make_context(
            intent_parser=parser,
            action_registry=ar,
            renderer=renderer,
        )
        handler = ExploringModeHandler()
        result = await handler.handle_input("asdfghjkl", state, ctx)

        assert result.next_mode is None
```

Add at the top of the test file these imports and helper:

```python
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult, Character, Location, CharacterRole


async def _async_gen(items):
    for item in items:
        yield item
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_modes_exploring.py::TestExploringFreeText -v`

Expected: FAIL (free text still returns empty TransitionResult)

- [ ] **Step 3: Implement ExploringModeHandler free-text logic**

Replace `src/tavern/engine/modes/exploring.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    Keybinding,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)

if TYPE_CHECKING:
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)


class ExploringModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.EXPLORING

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()
        if not stripped:
            return TransitionResult()

        if stripped.startswith("/"):
            handled = await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            if not handled:
                await context.renderer.render_error(
                    f"未知命令: {stripped.split()[0]}"
                )
            return TransitionResult()

        return await self._handle_free_text(stripped, state, context)

    async def _handle_free_text(
        self,
        text: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        request = await context.intent_parser.parse(
            text,
            location_id=player.location_id,
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
            state=state,
        )

        result, diff = context.action_registry.validate_and_execute(request, state)

        if not result.success:
            context.renderer.render_result(result)
            return TransitionResult()

        effects: list[SideEffect] = []

        if diff is not None:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": diff, "action": result},
            ))

        is_talk = request.action in (ActionType.TALK, ActionType.PERSUADE)
        if is_talk and result.target:
            effects.append(SideEffect(
                kind=EffectKind.START_DIALOGUE,
                payload={"npc_id": result.target},
            ))

        memory_ctx = context.memory.build_context(
            actor=result.target or state.player_id,
            state=state,
        )
        narrative_stream = context.narrator.stream_narrative(
            result, state, memory_ctx,
        )
        await context.renderer.render_stream(
            narrative_stream,
            atmosphere=location.atmosphere,
        )

        story_results = context.story_engine.check(
            state, "passive",
            context.memory._timeline if hasattr(context.memory, "_timeline") else (),
            context.memory._relationship_graph if hasattr(context.memory, "_relationship_graph") else {},
        )
        for sr in (story_results or []):
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": sr.diff, "action": None},
            ))
            if sr.narrator_hint:
                effects.append(SideEffect(
                    kind=EffectKind.EMIT_EVENT,
                    payload={"event": f"story:{sr.node_id}"},
                ))

        context.renderer.render_status_bar(state)

        next_mode = GameMode.DIALOGUE if (is_talk and result.target) else None
        return TransitionResult(
            next_mode=next_mode,
            side_effects=tuple(effects),
        )

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

Run: `pytest tests/engine/test_modes_exploring.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/modes/exploring.py tests/engine/test_modes_exploring.py
git commit -m "feat: ExploringModeHandler handles free-text via intent parser + ActionRegistry (§3)"
```

---

### Task 5: Migrate DialogueModeHandler with constructor injection

**Files:**
- Modify: `src/tavern/engine/modes/dialogue.py:1-51`
- Modify: `tests/engine/test_modes_dialogue.py`

- [ ] **Step 1: Write failing tests for dialogue flow**

Add to `tests/engine/test_modes_dialogue.py`:

```python
from tavern.engine.actions import ActionType
from tavern.world.models import Character, CharacterRole, Location
from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary


def _make_state(**kwargs) -> WorldState:
    return WorldState(turn=0, player_id="player", **kwargs)


class TestDialogueFlow:
    @pytest.mark.asyncio
    async def test_sends_message_and_renders(self):
        dm = AsyncMock()
        dm.respond.return_value = (
            MagicMock(),
            DialogueResponse(text="Hello!", trust_delta=2, mood="friendly", wants_to_end=False),
        )
        dm._active = DialogueContext(
            npc_id="grim", npc_name="Grim", npc_traits=(),
            trust=10, tone="neutral", messages=(),
            location_id="tavern", turn_entered=0,
        )
        renderer = MagicMock()
        renderer.render_dialogue_with_typewriter = AsyncMock()
        ctx = _make_context(dialogue_manager=dm, renderer=renderer)
        state = _make_state()

        handler = DialogueModeHandler(dialogue_manager=dm)
        result = await handler.handle_input("你好", state, ctx)

        dm.respond.assert_awaited_once()
        assert any(e.kind == EffectKind.APPLY_TRUST for e in result.side_effects)

    @pytest.mark.asyncio
    async def test_wants_to_end_transitions_to_exploring(self):
        dm = AsyncMock()
        dm.respond.return_value = (
            MagicMock(),
            DialogueResponse(text="Goodbye", trust_delta=0, mood="neutral", wants_to_end=True),
        )
        dm._active = DialogueContext(
            npc_id="grim", npc_name="Grim", npc_traits=(),
            trust=10, tone="neutral", messages=(),
            location_id="tavern", turn_entered=0,
        )
        dm.end = AsyncMock(return_value=DialogueSummary(
            npc_id="grim", summary_text="chat", total_trust_delta=0,
            key_info=(), turns_count=1,
        ))
        renderer = MagicMock()
        renderer.render_dialogue_with_typewriter = AsyncMock()
        renderer.render_dialogue_end = MagicMock()
        ctx = _make_context(dialogue_manager=dm, renderer=renderer)
        state = _make_state()

        handler = DialogueModeHandler(dialogue_manager=dm)
        result = await handler.handle_input("再见", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
        assert any(e.kind == EffectKind.END_DIALOGUE for e in result.side_effects)

    @pytest.mark.asyncio
    async def test_escape_input_ends_dialogue(self):
        dm = AsyncMock()
        dm._active = DialogueContext(
            npc_id="grim", npc_name="Grim", npc_traits=(),
            trust=10, tone="neutral", messages=(),
            location_id="tavern", turn_entered=0,
        )
        dm.end = AsyncMock(return_value=DialogueSummary(
            npc_id="grim", summary_text="chat", total_trust_delta=0,
            key_info=(), turns_count=1,
        ))
        renderer = MagicMock()
        renderer.render_dialogue_end = MagicMock()
        ctx = _make_context(dialogue_manager=dm, renderer=renderer)
        state = _make_state()

        handler = DialogueModeHandler(dialogue_manager=dm)
        result = await handler.handle_input("\x1b", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
        assert any(e.kind == EffectKind.END_DIALOGUE for e in result.side_effects)

    @pytest.mark.asyncio
    async def test_no_active_dialogue_renders_error(self):
        dm = MagicMock()
        dm._active = None
        renderer = MagicMock()
        renderer.render_error = AsyncMock()
        ctx = _make_context(dialogue_manager=dm, renderer=renderer)
        state = _make_state()

        handler = DialogueModeHandler(dialogue_manager=dm)
        result = await handler.handle_input("hello", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
```

Also update the existing `TestDialogueModeHandler` class — change `DialogueModeHandler()` to `DialogueModeHandler(dialogue_manager=MagicMock())` in all existing tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_modes_dialogue.py::TestDialogueFlow -v`

Expected: FAIL

- [ ] **Step 3: Implement DialogueModeHandler**

Replace `src/tavern/engine/modes/dialogue.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    Keybinding,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)

if TYPE_CHECKING:
    from tavern.dialogue.manager import DialogueManager
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

_BYE_PHRASES = frozenset({"bye", "leave", "再见", "离开", "结束对话"})


class DialogueModeHandler:
    def __init__(self, dialogue_manager: DialogueManager) -> None:
        self._dm = dialogue_manager

    @property
    def mode(self) -> GameMode:
        return GameMode.DIALOGUE

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()

        if stripped.startswith("/"):
            await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            return TransitionResult()

        if not stripped:
            return TransitionResult()

        if stripped == "\x1b":
            return await self._end_dialogue(state, context)

        active_ctx = self._dm._active
        if active_ctx is None:
            await context.renderer.render_error("没有进行中的对话")
            return TransitionResult(next_mode=GameMode.EXPLORING)

        if stripped.lower() in _BYE_PHRASES:
            return await self._end_dialogue(state, context)

        memory_ctx = context.memory.build_context(
            actor=active_ctx.npc_id,
            state=state,
        )
        new_ctx, response = await self._dm.respond(
            active_ctx, stripped, state, memory_ctx,
        )
        await context.renderer.render_dialogue_with_typewriter(
            active_ctx.npc_name, response,
        )

        effects: list[SideEffect] = []
        if response.trust_delta != 0:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_TRUST,
                payload={"npc_id": active_ctx.npc_id, "delta": response.trust_delta},
            ))

        if response.wants_to_end:
            summary = await self._dm.end(new_ctx)
            context.renderer.render_dialogue_end(summary)
            effects.append(SideEffect(
                kind=EffectKind.END_DIALOGUE,
                payload={"npc_id": active_ctx.npc_id},
            ))
            return TransitionResult(
                next_mode=GameMode.EXPLORING,
                side_effects=tuple(effects),
            )

        return TransitionResult(side_effects=tuple(effects))

    async def _end_dialogue(
        self,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        active_ctx = self._dm._active
        npc_id = active_ctx.npc_id if active_ctx else "unknown"
        if active_ctx is not None:
            summary = await self._dm.end(active_ctx)
            context.renderer.render_dialogue_end(summary)
        return TransitionResult(
            next_mode=GameMode.EXPLORING,
            side_effects=(
                SideEffect(
                    kind=EffectKind.END_DIALOGUE,
                    payload={"npc_id": npc_id},
                ),
            ),
        )

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

- [ ] **Step 4: Update existing tests for constructor change**

In `tests/engine/test_modes_dialogue.py`, update all `DialogueModeHandler()` calls in the existing `TestDialogueModeHandler` class to `DialogueModeHandler(dialogue_manager=MagicMock())`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/engine/test_modes_dialogue.py -v`

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/modes/dialogue.py tests/engine/test_modes_dialogue.py
git commit -m "feat: DialogueModeHandler with constructor injection + LLM dialogue flow (§4)"
```

---

### Task 6: Update bootstrap() for DialogueModeHandler constructor

**Files:**
- Modify: `src/tavern/cli/bootstrap.py`
- Modify: `tests/cli/test_bootstrap.py`

- [ ] **Step 1: Verify bootstrap.py already passes dialogue_manager to handler**

This was done in Task 3, Step 2. Verify that `bootstrap.py` has:

```python
handlers = {
    GameMode.EXPLORING: ExploringModeHandler(),
    GameMode.DIALOGUE: DialogueModeHandler(dialogue_manager=dialogue_manager),
}
```

- [ ] **Step 2: Run bootstrap tests**

Run: `pytest tests/cli/test_bootstrap.py -v`

Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`

Expected: All tests pass

- [ ] **Step 4: Commit (if any changes needed)**

```bash
git add src/tavern/cli/bootstrap.py tests/cli/test_bootstrap.py
git commit -m "fix: bootstrap passes dialogue_manager to DialogueModeHandler (§4)"
```

---

### Task 7: Integrate GameApp with GameLoop

**Files:**
- Modify: `src/tavern/cli/app.py:1-667`

- [ ] **Step 1: Rewrite GameApp to use bootstrap + GameLoop**

The key changes to `app.py`:

1. Import `bootstrap` from `tavern.cli.bootstrap`
2. At end of `__init__`, call `bootstrap()` and store result as `self._game_loop`
3. Replace `run()` body with `GameLoop.run()` call
4. Delete `_handle_system_command()`, `_handle_free_input()`, `_process_dialogue_input()`, `_apply_dialogue_end()`, `_apply_story_results()`, `_apply_story_results_sync()`, `_update_story_active_since()`
5. Keep `__init__`, `_load_config`, `state` property, `_generate_action_hints_from_state`, `_generate_action_hints`, `_generate_smart_hints`

Replace the `run()` method and add `bootstrap` import + call at end of `__init__`:

At the top of `app.py`, add import:
```python
from tavern.cli.bootstrap import bootstrap
```

At end of `__init__` (after `logging.getLogger("httpcore").setLevel(logging.WARNING)`), add:
```python
        self._game_loop = bootstrap(
            state_manager=self._state_manager,
            renderer=self._renderer,
            dialogue_manager=self._dialogue_manager,
            narrator=self._narrator,
            memory=self._memory,
            persistence=self._save_manager,
            story_engine=self._story_engine,
            intent_parser=self._parser,
            logger=logger,
        )
```

Replace `run()`:
```python
    async def run(self) -> None:
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
        self._renderer.render_status_bar(self.state)
        await self._game_loop.run()
```

Delete methods: `_handle_system_command`, `_handle_free_input`, `_process_dialogue_input`, `_apply_dialogue_end`, `_apply_story_results`, `_apply_story_results_sync`, `_update_story_active_since`.

Also remove unused imports: `uuid`, `DialogueContext`, `ActionType`, `ActionRequest`, `ActionResult`, `Event`, `StateDiff`, `StoryEngine`, `StoryResult`, `load_story_nodes`, and the `SYSTEM_COMMANDS` constant.

Keep these as they're still used by `__init__`: `RulesEngine` (used to create `self._rules`, though it may no longer be needed — but removing it is out of scope for this task, we just remove the methods that use it directly).

Actually — `_rules` is no longer used after removing the methods. Remove `self._rules = RulesEngine()` from `__init__` and the `RulesEngine` import if no other code references it.

Also remove: `self._dialogue_ctx`, `self._pending_story_hints`, `self._ending_triggered`, `self._game_over`, `self._last_hints`, `self._last_narrative`, `self._show_intent` — these are all state that lived in the old monolith and is now handled by mode handlers and effects.

- [ ] **Step 2: Run full test suite**

Run: `pytest --tb=short -q`

Expected: All tests pass

- [ ] **Step 3: Verify app.py line count**

Run: `wc -l src/tavern/cli/app.py`

Expected: ~150-180 lines (down from 667)

- [ ] **Step 4: Commit**

```bash
git add src/tavern/cli/app.py
git commit -m "refactor: GameApp delegates to GameLoop via bootstrap (§5)"
```

---

### Task 8: Full integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`

Expected: All tests pass, 0 failures

- [ ] **Step 2: Run test coverage**

Run: `pytest --cov=tavern --cov-report=term-missing --tb=short -q`

Expected: New modules (effects, exploring, dialogue mode handlers) at 80%+ coverage

- [ ] **Step 3: Verify no CommandContext references remain**

Run: `grep -r "CommandContext" src/ tests/`

Expected: No matches

- [ ] **Step 4: Code review**

Use superpowers:requesting-code-review skill to review all changes against the Phase 3 design spec.

- [ ] **Step 5: Final commit if code review finds fixes**

```bash
git add -A
git commit -m "fix: address Phase 3 code review findings"
```
