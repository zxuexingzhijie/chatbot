# Item Use System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the USE action so players can use items to unlock doors, consume items, spawn new items, and trigger story events.

**Architecture:** Four layers top-to-bottom: (1) `world/models.py` — `EventSpec` and `UseEffect` data models added to `Item`; (2) `engine/use_effects.py` — `USE_EFFECT_REGISTRY` with four registered effect functions; (3) `engine/rules.py` — `_handle_use` handler + `_merge_diffs` helper wired into `_ACTION_HANDLERS`; (4) `world/loader.py` + `world.yaml` + `llm/service.py` — loading and parsing. Effects are applied sequentially to a running `current_state` so each effect sees results of the previous one; their diffs are merged into a single `StateDiff` returned to the caller.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, pytest, pytest-asyncio

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/tavern/world/models.py` | Add `EventSpec`, `UseEffect`; add `use_effects` to `Item` |
| Create | `src/tavern/engine/use_effects.py` | `USE_EFFECT_REGISTRY` + four effect functions |
| Modify | `src/tavern/engine/rules.py` | `_merge_diffs`, `_handle_use`, wire into `_ACTION_HANDLERS` |
| Modify | `src/tavern/world/loader.py` | Parse `use_effects` from YAML |
| Modify | `data/scenarios/tavern/world.yaml` | Add `use_effects` to `cellar_key`, `rusty_box` |
| Modify | `src/tavern/llm/service.py` | Add USE examples to `INTENT_SYSTEM_PROMPT` |
| Create | `tests/world/test_models_use_effect.py` | Pydantic serialization roundtrip tests |
| Create | `tests/engine/test_use_effects.py` | Effect function unit tests |
| Create | `tests/engine/test_rules_use.py` | `_handle_use` integration tests |

---

## Task 1: Data models — EventSpec, UseEffect, Item.use_effects

**Files:**
- Modify: `src/tavern/world/models.py`
- Create: `tests/world/test_models_use_effect.py`

### Background

`models.py` uses `BaseModel(frozen=True)` for all types. `Exit` nested inside `Location.exits` is the reference pattern for nested models. `Item` currently has no `use_effects` field. `EventSpec` is structurally identical to `NewEventSpec` in `engine/story.py` but is a `BaseModel` to be consistent with the models layer.

- [ ] **Step 1: Write failing tests**

```python
# tests/world/test_models_use_effect.py
from __future__ import annotations
import pytest
from tavern.world.models import EventSpec, UseEffect, Item


def test_event_spec_roundtrip():
    spec = EventSpec(id="box_opened", type="story", description="铁盒被打开了", actor="player")
    data = spec.model_dump()
    restored = EventSpec(**data)
    assert restored == spec


def test_event_spec_actor_optional():
    spec = EventSpec(id="evt1", type="story", description="something")
    assert spec.actor is None


def test_use_effect_unlock_roundtrip():
    eff = UseEffect(type="unlock", location="bar_area", exit_direction="down")
    data = eff.model_dump()
    restored = UseEffect(**data)
    assert restored == eff


def test_use_effect_with_event_roundtrip():
    eff = UseEffect(
        type="story_event",
        event=EventSpec(id="box_opened", type="story", description="铁盒打开了"),
    )
    data = eff.model_dump()
    restored = UseEffect(**data)
    assert restored.event is not None
    assert restored.event.id == "box_opened"


def test_item_with_use_effects_roundtrip():
    item = Item(
        id="cellar_key",
        name="地下室钥匙",
        description="一把钥匙",
        use_effects=(
            UseEffect(type="unlock", location="bar_area", exit_direction="down"),
            UseEffect(type="consume"),
        ),
    )
    data = item.model_dump()
    restored = Item(**data)
    assert len(restored.use_effects) == 2
    assert restored.use_effects[0].type == "unlock"
    assert restored.use_effects[1].type == "consume"


def test_item_use_effects_default_empty():
    item = Item(id="x", name="X", description="d")
    assert item.use_effects == ()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/world/test_models_use_effect.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'EventSpec' from 'tavern.world.models'`

- [ ] **Step 3: Add EventSpec, UseEffect, update Item in models.py**

In `src/tavern/world/models.py`, add after the `_freeze_dicts` function (before `CharacterRole`):

```python
class EventSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    description: str
    actor: str | None = None


class UseEffect(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str                           # unlock | consume | spawn_item | story_event
    location: str | None = None         # unlock: exit's location ID; spawn_item(no inventory): target location ID
    exit_direction: str | None = None   # unlock only: which direction
    item_id: str | None = None          # spawn_item only: which item to spawn
    spawn_to_inventory: bool = True     # spawn_item: True→player inventory, False→location
    event: EventSpec | None = None      # story_event only
```

Then update the `Item` class to add `use_effects`:

```python
class Item(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    portable: bool = True
    usable_with: tuple[str, ...] = ()
    use_effects: tuple[UseEffect, ...] = ()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/world/test_models_use_effect.py -v
```

Expected: 6 tests PASSED

- [ ] **Step 5: Run full suite to check no regressions**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/world/models.py tests/world/test_models_use_effect.py
git commit -m "feat: add EventSpec, UseEffect models; add use_effects field to Item"
```

---

## Task 2: USE_EFFECT_REGISTRY and four effect functions

**Files:**
- Create: `src/tavern/engine/use_effects.py`
- Create: `tests/engine/test_use_effects.py`

### Background

`engine/story_conditions.py` is the reference for the registry pattern (`CONDITION_REGISTRY`, `@register_condition`). Each effect function signature: `(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]`. All effect diffs use `turn_increment=0` (turn increment is handled by the caller in `_handle_use`). Effects chain via `current_state` so each sees updated state.

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_use_effects.py
from __future__ import annotations
import pytest
from unittest.mock import patch
from tavern.world.models import Character, CharacterRole, Exit, EventSpec, Item, Location, UseEffect
from tavern.world.state import StateDiff, WorldState


def _make_state(
    player_inventory=("cellar_key",),
    exit_locked=True,
    location_items=(),
) -> WorldState:
    exits = {"down": Exit(target="cellar", locked=exit_locked, description="铁门")}
    return WorldState(
        turn=3,
        player_id="player",
        locations={
            "bar_area": Location(id="bar_area", name="吧台区", description=".", exits=exits, items=location_items),
            "cellar": Location(id="cellar", name="地下室", description="."),
        },
        characters={
            "player": Character(
                id="player", name="玩家",
                role=CharacterRole.PLAYER,
                location_id="bar_area",
                inventory=player_inventory,
            )
        },
        items={
            "cellar_key": Item(id="cellar_key", name="地下室钥匙", description="一把钥匙"),
            "spare_key": Item(id="spare_key", name="备用钥匙", description="备用"),
        },
    )


# ── unlock ────────────────────────────────────────────────────────────────

def test_unlock_effect_sets_locked_false():
    from tavern.engine.use_effects import effect_unlock
    eff = UseEffect(type="unlock", location="bar_area", exit_direction="down")
    state = _make_state(exit_locked=True)
    diff, msg = effect_unlock(eff, "cellar_key", state)
    assert diff.updated_locations["bar_area"]["exits"]["down"].locked is False
    assert "打开了" in msg


def test_unlock_effect_missing_location_skips():
    from tavern.engine.use_effects import effect_unlock
    eff = UseEffect(type="unlock", location=None, exit_direction="down")
    state = _make_state()
    diff, msg = effect_unlock(eff, "cellar_key", state)
    assert diff.updated_locations == {}
    assert msg is None


def test_unlock_effect_unknown_exit_skips():
    from tavern.engine.use_effects import effect_unlock
    eff = UseEffect(type="unlock", location="bar_area", exit_direction="north")
    state = _make_state()
    diff, msg = effect_unlock(eff, "cellar_key", state)
    assert diff.updated_locations == {}


# ── consume ───────────────────────────────────────────────────────────────

def test_consume_effect_removes_from_inventory():
    from tavern.engine.use_effects import effect_consume
    eff = UseEffect(type="consume")
    state = _make_state(player_inventory=("cellar_key", "old_notice"))
    diff, msg = effect_consume(eff, "cellar_key", state)
    new_inv = diff.updated_characters["player"]["inventory"]
    assert "cellar_key" not in new_inv
    assert "old_notice" in new_inv
    assert msg is None


# ── spawn_item ────────────────────────────────────────────────────────────

def test_spawn_item_to_inventory():
    from tavern.engine.use_effects import effect_spawn_item
    eff = UseEffect(type="spawn_item", item_id="spare_key", spawn_to_inventory=True)
    state = _make_state(player_inventory=())
    diff, msg = effect_spawn_item(eff, "rusty_box", state)
    new_inv = diff.updated_characters["player"]["inventory"]
    assert "spare_key" in new_inv
    assert "获得" in msg


def test_spawn_item_to_location():
    from tavern.engine.use_effects import effect_spawn_item
    eff = UseEffect(type="spawn_item", item_id="spare_key", spawn_to_inventory=False, location="bar_area")
    state = _make_state(location_items=())
    diff, msg = effect_spawn_item(eff, "rusty_box", state)
    new_items = diff.updated_locations["bar_area"]["items"]
    assert "spare_key" in new_items


def test_spawn_item_unknown_item_id_skips():
    from tavern.engine.use_effects import effect_spawn_item
    eff = UseEffect(type="spawn_item", item_id="nonexistent", spawn_to_inventory=True)
    state = _make_state()
    diff, msg = effect_spawn_item(eff, "box", state)
    assert diff.updated_characters == {}
    assert msg is None


# ── story_event ───────────────────────────────────────────────────────────

def test_story_event_effect_creates_event():
    from tavern.engine.use_effects import effect_story_event
    eff = UseEffect(
        type="story_event",
        event=EventSpec(id="box_opened", type="story", description="铁盒打开了"),
    )
    state = _make_state()
    diff, msg = effect_story_event(eff, "rusty_box", state)
    assert len(diff.new_events) == 1
    assert diff.new_events[0].type == "story"
    assert "铁盒打开了" in diff.new_events[0].description
    assert msg is None


def test_story_event_uses_player_id_as_default_actor():
    from tavern.engine.use_effects import effect_story_event
    eff = UseEffect(
        type="story_event",
        event=EventSpec(id="evt", type="story", description="something"),
    )
    state = _make_state()
    diff, msg = effect_story_event(eff, "box", state)
    assert diff.new_events[0].actor == "player"


# ── unknown type ──────────────────────────────────────────────────────────

def test_unknown_effect_type_not_in_registry():
    from tavern.engine.use_effects import USE_EFFECT_REGISTRY
    assert "unknown_type_xyz" not in USE_EFFECT_REGISTRY


# ── multiple effects + merge ──────────────────────────────────────────────

def test_unlock_and_consume_merge():
    """Unlock + consume effects produce a merged diff with both updates."""
    from tavern.engine.use_effects import USE_EFFECT_REGISTRY
    from tavern.engine.rules import _merge_diffs

    state = _make_state(player_inventory=("cellar_key",), exit_locked=True)

    eff_unlock = UseEffect(type="unlock", location="bar_area", exit_direction="down")
    eff_consume = UseEffect(type="consume")

    diff_a, _ = USE_EFFECT_REGISTRY["unlock"](eff_unlock, "cellar_key", state)
    state2 = state.apply(diff_a)
    diff_b, _ = USE_EFFECT_REGISTRY["consume"](eff_consume, "cellar_key", state2)

    combined = _merge_diffs(diff_a, diff_b)
    assert "bar_area" in combined.updated_locations
    assert "player" in combined.updated_characters
    new_inv = combined.updated_characters["player"]["inventory"]
    assert "cellar_key" not in new_inv
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/engine/test_use_effects.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'tavern.engine.use_effects'`

- [ ] **Step 3: Create use_effects.py**

```python
# src/tavern/engine/use_effects.py
from __future__ import annotations

import logging
import uuid
from typing import Callable

from tavern.world.models import Event, UseEffect
from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)

UseEffectFn = Callable[[UseEffect, str, WorldState], tuple[StateDiff, str | None]]

USE_EFFECT_REGISTRY: dict[str, UseEffectFn] = {}


def register_effect(type_name: str):
    def decorator(fn: UseEffectFn) -> UseEffectFn:
        USE_EFFECT_REGISTRY[type_name] = fn
        return fn
    return decorator


@register_effect("unlock")
def effect_unlock(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.location is None or eff.exit_direction is None:
        logger.warning("unlock effect missing location or exit_direction (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    location = state.locations.get(eff.location)
    if location is None:
        logger.warning("unlock effect: location %r not found (item: %s)", eff.location, item_id)
        return StateDiff(turn_increment=0), None

    exit_ = location.exits.get(eff.exit_direction)
    if exit_ is None:
        logger.warning("unlock effect: exit %r not found in %r (item: %s)", eff.exit_direction, eff.location, item_id)
        return StateDiff(turn_increment=0), None

    new_exits = {**dict(location.exits), eff.exit_direction: exit_.model_copy(update={"locked": False})}
    diff = StateDiff(
        updated_locations={eff.location: {"exits": new_exits}},
        turn_increment=0,
    )
    target_loc = state.locations.get(exit_.target)
    target_name = target_loc.name if target_loc else exit_.target
    return diff, f"门被打开了，通往{target_name}。"


@register_effect("consume")
def effect_consume(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    player = state.characters[state.player_id]
    new_inventory = tuple(i for i in player.inventory if i != item_id)
    diff = StateDiff(
        updated_characters={state.player_id: {"inventory": new_inventory}},
        turn_increment=0,
    )
    return diff, None


@register_effect("spawn_item")
def effect_spawn_item(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.item_id is None:
        logger.warning("spawn_item effect missing item_id (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    if eff.item_id not in state.items:
        logger.warning("spawn_item effect: item_id %r not in state.items (item: %s)", eff.item_id, item_id)
        return StateDiff(turn_increment=0), None

    spawned = state.items[eff.item_id]

    if eff.spawn_to_inventory:
        player = state.characters[state.player_id]
        new_inventory = player.inventory + (eff.item_id,)
        diff = StateDiff(
            updated_characters={state.player_id: {"inventory": new_inventory}},
            turn_increment=0,
        )
    else:
        if eff.location is None:
            logger.warning("spawn_item effect: spawn_to_inventory=False but no location (item: %s)", item_id)
            return StateDiff(turn_increment=0), None
        loc = state.locations.get(eff.location)
        if loc is None:
            logger.warning("spawn_item effect: location %r not found (item: %s)", eff.location, item_id)
            return StateDiff(turn_increment=0), None
        new_items = loc.items + (eff.item_id,)
        diff = StateDiff(
            updated_locations={eff.location: {"items": new_items}},
            turn_increment=0,
        )

    return diff, f"你获得了「{spawned.name}」。"


@register_effect("story_event")
def effect_story_event(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.event is None:
        logger.warning("story_event effect missing event spec (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    actor = eff.event.actor or state.player_id
    event = Event(
        id=f"{eff.event.id}_{uuid.uuid4().hex[:6]}",
        turn=state.turn,
        type=eff.event.type,
        actor=actor,
        description=eff.event.description,
    )
    diff = StateDiff(new_events=(event,), turn_increment=0)
    return diff, None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/engine/test_use_effects.py -v
```

Expected: all tests PASSED (note: `test_unlock_and_consume_merge` imports `_merge_diffs` from `rules` — add a stub first if needed, or skip this test temporarily)

The `_merge_diffs` test will fail because `_merge_diffs` doesn't exist yet. That is expected — it will pass after Task 3. For now, verify all other tests pass:

```bash
python -m pytest tests/engine/test_use_effects.py -v -k "not merge"
```

Expected: all non-merge tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/use_effects.py tests/engine/test_use_effects.py
git commit -m "feat: add USE_EFFECT_REGISTRY with unlock/consume/spawn_item/story_event effects"
```

---

## Task 3: _handle_use and _merge_diffs in rules.py

**Files:**
- Modify: `src/tavern/engine/rules.py`
- Create: `tests/engine/test_rules_use.py`

### Background

`rules.py` currently handles `USE` via `_handle_custom` (fallback). `_ACTION_HANDLERS` at the bottom maps `ActionType` to handler functions. `_handle_use` returns `(ActionResult, StateDiff | None)`. `_merge_diffs` merges two `StateDiff` instances: for overlapping character/location keys, later value wins (it was applied to updated state); for sequences (`new_events`, `removed_items`), concatenate; for `turn_increment`, sum.

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_rules_use.py
from __future__ import annotations
import pytest
from tavern.world.models import Character, CharacterRole, Exit, EventSpec, Item, Location, UseEffect
from tavern.world.state import StateDiff, WorldState
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest


def _make_state() -> WorldState:
    exits = {"down": Exit(target="cellar", locked=True, description="铁门")}
    return WorldState(
        turn=1,
        player_id="player",
        locations={
            "bar_area": Location(id="bar_area", name="吧台区", description=".", exits=exits),
            "cellar": Location(id="cellar", name="地下室", description="."),
        },
        characters={
            "player": Character(
                id="player", name="玩家", role=CharacterRole.PLAYER,
                location_id="bar_area",
                inventory=("cellar_key",),
            )
        },
        items={
            "cellar_key": Item(
                id="cellar_key", name="地下室钥匙", description="一把钥匙",
                usable_with=("cellar_door",),
                use_effects=(
                    UseEffect(type="unlock", location="bar_area", exit_direction="down"),
                    UseEffect(type="consume"),
                ),
            ),
            "rusty_box": Item(
                id="rusty_box", name="铁盒", description="生锈的盒子",
                use_effects=(
                    UseEffect(type="spawn_item", item_id="spare_key", spawn_to_inventory=True),
                ),
            ),
            "spare_key": Item(id="spare_key", name="备用钥匙", description="备用"),
            "inert_item": Item(id="inert_item", name="无用物品", description="什么都不能做"),
        },
    )


def _use(target, detail=None):
    return ActionRequest(action=ActionType.USE, target=target, detail=detail)


# ── validation failures ───────────────────────────────────────────────────

def test_use_item_not_in_inventory_or_location():
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("nonexistent"), state)
    assert result.success is False
    assert "没有" in result.message
    assert diff is None


def test_use_item_no_effects():
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("inert_item"), state)
    assert result.success is False
    assert "无法使用" in result.message


def test_use_item_usable_with_no_detail():
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("cellar_key", detail=None), state)
    assert result.success is False
    assert "用在什么上" in result.message


def test_use_item_usable_with_wrong_target():
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("cellar_key", detail="wrong_target"), state)
    assert result.success is False
    assert "不能用在这里" in result.message


# ── success cases ─────────────────────────────────────────────────────────

def test_use_item_correct_target_succeeds():
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), state)
    assert result.success is True
    assert diff is not None


def test_use_item_no_usable_with_succeeds_without_detail():
    """Items with empty usable_with don't require a detail target."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("rusty_box"), state)
    assert result.success is True
    assert diff is not None


def test_use_cellar_key_unlocks_door_and_consumes():
    """unlock + consume effects both applied: exit unlocked and key removed from inventory."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), state)
    assert result.success is True

    new_state = state.apply(diff)
    # Door is unlocked
    assert new_state.locations["bar_area"].exits["down"].locked is False
    # Key consumed from inventory
    assert "cellar_key" not in new_state.characters["player"].inventory


def test_use_message_combined():
    """Message includes text from effects that return one."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    state = _make_state()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), state)
    assert "打开了" in result.message


# ── _merge_diffs ──────────────────────────────────────────────────────────

def test_merge_diffs_combines_fields():
    from tavern.engine.rules import _merge_diffs
    from tavern.world.models import Event

    a = StateDiff(
        updated_characters={"player": {"inventory": ()}},
        turn_increment=1,
    )
    b = StateDiff(
        updated_locations={"bar_area": {"exits": {}}},
        new_events=(Event(id="e1", turn=1, type="t", actor="p", description="d"),),
        turn_increment=0,
    )
    merged = _merge_diffs(a, b)
    assert "player" in merged.updated_characters
    assert "bar_area" in merged.updated_locations
    assert len(merged.new_events) == 1
    assert merged.turn_increment == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/engine/test_rules_use.py -v 2>&1 | head -20
```

Expected: test failures (no `_handle_use` or `_merge_diffs` yet)

- [ ] **Step 3: Add _merge_diffs and _handle_use to rules.py**

Add `_merge_diffs` near the bottom of `src/tavern/engine/rules.py`, before `_ACTION_HANDLERS`:

```python
def _merge_diffs(a: StateDiff, b: StateDiff) -> StateDiff:
    return StateDiff(
        updated_characters={**a.updated_characters, **b.updated_characters},
        updated_locations={**a.updated_locations, **b.updated_locations},
        added_items={**a.added_items, **b.added_items},
        removed_items=a.removed_items + b.removed_items,
        new_events=a.new_events + b.new_events,
        turn_increment=a.turn_increment + b.turn_increment,
    )


def _handle_use(request: ActionRequest, state: WorldState):
    from tavern.engine.use_effects import USE_EFFECT_REGISTRY

    item_id = request.target

    if item_id is None:
        return (
            ActionResult(success=False, action=ActionType.USE, message="你想使用什么？"),
            None,
        )

    player = _get_player(state)
    location = _get_player_location(state)
    if item_id not in player.inventory and item_id not in location.items:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message="你没有那个物品。", target=item_id),
            None,
        )

    if item_id not in state.items:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message=f"未知物品: {item_id}", target=item_id),
            None,
        )

    item = state.items[item_id]

    if item.usable_with:
        if request.detail is None:
            return (
                ActionResult(success=False, action=ActionType.USE,
                             message="你想把它用在什么上？", target=item_id),
                None,
            )
        if request.detail not in item.usable_with:
            return (
                ActionResult(success=False, action=ActionType.USE,
                             message="该物品不能用在这里。", target=item_id),
                None,
            )

    if not item.use_effects:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message=f"「{item.name}」无法使用。", target=item_id),
            None,
        )

    combined_diff = StateDiff(turn_increment=1)
    messages = []
    current_state = state
    for eff in item.use_effects:
        fn = USE_EFFECT_REGISTRY.get(eff.type)
        if fn is None:
            logger.warning("未知 use_effect 类型: %s（物品: %s）", eff.type, item_id)
            continue
        diff, msg = fn(eff, item_id, current_state)
        combined_diff = _merge_diffs(combined_diff, diff)
        current_state = current_state.apply(diff)
        if msg:
            messages.append(msg)

    final_message = "\n".join(messages) if messages else f"你使用了「{item.name}」。"
    return (
        ActionResult(success=True, action=ActionType.USE,
                     message=final_message, target=item_id),
        combined_diff,
    )
```

Also add `logger = logging.getLogger(__name__)` near the top of `rules.py` (after imports) if not already present, and add `import logging` to imports.

- [ ] **Step 4: Wire _handle_use into _ACTION_HANDLERS**

Find `_ACTION_HANDLERS` at the bottom of `rules.py` and add:

```python
_ACTION_HANDLERS = {
    ActionType.MOVE: _handle_move,
    ActionType.LOOK: _handle_look,
    ActionType.SEARCH: _handle_look,
    ActionType.TAKE: _handle_take,
    ActionType.TALK: _handle_talk,
    ActionType.PERSUADE: _handle_talk,
    ActionType.USE: _handle_use,
    ActionType.CUSTOM: _handle_custom,
}
```

- [ ] **Step 5: Run all use-related tests**

```bash
python -m pytest tests/engine/test_rules_use.py tests/engine/test_use_effects.py -v
```

Expected: all tests PASSED (including the previously skipped merge test)

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/tavern/engine/rules.py tests/engine/test_rules_use.py
git commit -m "feat: add _handle_use and _merge_diffs to RulesEngine; wire USE into action handlers"
```

---

## Task 4: Loader + world.yaml

**Files:**
- Modify: `src/tavern/world/loader.py`
- Modify: `data/scenarios/tavern/world.yaml`

### Background

`loader._build_items` currently constructs `Item` without `use_effects`. Need to parse the `use_effects` list from YAML, constructing `UseEffect` (and nested `EventSpec`) objects.

- [ ] **Step 1: Write failing test**

```python
# Add to tests/world/test_models_use_effect.py (or create tests/world/test_loader_use_effects.py)
# Add this test at the bottom of tests/world/test_models_use_effect.py:

def test_loader_builds_item_with_use_effects(tmp_path):
    from tavern.world.loader import _build_items
    raw = {
        "cellar_key": {
            "name": "地下室钥匙",
            "description": "一把钥匙",
            "portable": True,
            "usable_with": ["cellar_door"],
            "use_effects": [
                {"type": "unlock", "location": "bar_area", "exit_direction": "down"},
                {"type": "consume"},
            ],
        }
    }
    items = _build_items(raw)
    key = items["cellar_key"]
    assert len(key.use_effects) == 2
    assert key.use_effects[0].type == "unlock"
    assert key.use_effects[0].location == "bar_area"
    assert key.use_effects[1].type == "consume"


def test_loader_builds_item_with_story_event_effect(tmp_path):
    from tavern.world.loader import _build_items
    raw = {
        "rusty_box": {
            "name": "铁盒",
            "description": "生锈的盒子",
            "use_effects": [
                {
                    "type": "story_event",
                    "event": {
                        "id": "box_opened",
                        "type": "story",
                        "description": "铁盒打开了",
                    },
                }
            ],
        }
    }
    items = _build_items(raw)
    box = items["rusty_box"]
    assert len(box.use_effects) == 1
    assert box.use_effects[0].event is not None
    assert box.use_effects[0].event.id == "box_opened"
```

- [ ] **Step 2: Run to verify fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/world/test_models_use_effect.py::test_loader_builds_item_with_use_effects -v 2>&1 | tail -10
```

Expected: FAIL — `_build_items` doesn't parse `use_effects` yet

- [ ] **Step 3: Update loader._build_items**

Replace the `_build_items` function in `src/tavern/world/loader.py`:

```python
def _build_items(raw: dict) -> dict[str, Item]:
    from tavern.world.models import EventSpec, UseEffect
    items: dict[str, Item] = {}
    for item_id, data in raw.items():
        use_effects = []
        for eff_data in data.get("use_effects", []):
            event_data = eff_data.get("event")
            event = EventSpec(**event_data) if event_data else None
            use_effects.append(UseEffect(
                type=eff_data["type"],
                location=eff_data.get("location"),
                exit_direction=eff_data.get("exit_direction"),
                item_id=eff_data.get("item_id"),
                spawn_to_inventory=eff_data.get("spawn_to_inventory", True),
                event=event,
            ))
        items[item_id] = Item(
            id=item_id,
            name=data["name"],
            description=data["description"],
            portable=data.get("portable", True),
            usable_with=tuple(data.get("usable_with", [])),
            use_effects=tuple(use_effects),
        )
    return items
```

- [ ] **Step 4: Update world.yaml**

In `data/scenarios/tavern/world.yaml`, update the `cellar_key` and `rusty_box` items:

```yaml
  cellar_key:
    name: 地下室钥匙
    description: 一把生锈的铁钥匙，上面刻着一个小小的龙形标记
    portable: true
    usable_with:
      - cellar_door
    use_effects:
      - type: unlock
        location: bar_area
        exit_direction: down
      - type: consume

  rusty_box:
    name: 生锈铁盒
    description: 从马车下找到的铁盒，里面有一把备用钥匙
    portable: false
    use_effects:
      - type: spawn_item
        item_id: spare_key
        spawn_to_inventory: true
      - type: story_event
        event:
          id: box_opened
          type: story
          description: "玩家打开了铁盒，找到了备用钥匙"
```

- [ ] **Step 5: Run loader tests**

```bash
python -m pytest tests/world/test_models_use_effect.py -v
```

Expected: all 8 tests PASSED

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/tavern/world/loader.py data/scenarios/tavern/world.yaml tests/world/test_models_use_effect.py
git commit -m "feat: parse use_effects in loader; add use_effects to cellar_key and rusty_box in world.yaml"
```

---

## Task 5: Parser prompt — USE examples

**Files:**
- Modify: `src/tavern/llm/service.py`

### Background

`INTENT_SYSTEM_PROMPT` currently has examples for move/look/take/talk but none for USE. Without a USE example, the LLM may put the target object ID in `target` instead of `detail`, or vice versa. The required convention: `target` = item being used, `detail` = object it's used on (null if no target required). No separate test needed — the prompt change is verified by the existing `test_service_dialogue.py` and `test_service_narrative.py` running without regression.

- [ ] **Step 1: Add USE examples to INTENT_SYSTEM_PROMPT**

In `src/tavern/llm/service.py`, find the `INTENT_SYSTEM_PROMPT` examples section. It currently ends with the `talk` example. Add two lines after it:

Find:
```python
- 输入: "和旅行者聊聊" -> {{"action": "talk", "target": "traveler", \
"detail": "与旅行者对话", "confidence": 0.9}}
"""
```

Replace with:
```python
- 输入: "和旅行者聊聊" -> {{"action": "talk", "target": "traveler", \
"detail": "与旅行者对话", "confidence": 0.9}}
- 输入: "用钥匙开地下室的门" -> {{"action": "use", "target": "cellar_key", \
"detail": "cellar_door", "confidence": 0.95}}
- 输入: "使用铁盒" -> {{"action": "use", "target": "rusty_box", \
"detail": null, "confidence": 0.9}}
"""
```

- [ ] **Step 2: Run full suite**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add src/tavern/llm/service.py
git commit -m "feat: add USE action examples to intent parser system prompt"
```

---

## Verification

After all tasks:

```bash
python -m pytest tests/ -q
```

Expected: all tests pass. Check coverage on new files:

```bash
python -m pytest tests/engine/test_use_effects.py tests/engine/test_rules_use.py \
  --cov=tavern.engine.use_effects --cov=tavern.engine.rules \
  --cov-report=term-missing 2>&1 | tail -20
```

Expected: `use_effects.py` ≥ 90%, `rules.py` ≥ 85%.
