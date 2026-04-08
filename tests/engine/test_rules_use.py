from __future__ import annotations
import pytest
from tavern.world.models import Character, CharacterRole, Exit, EventSpec, Item, Location, UseEffect
from tavern.world.state import StateDiff, WorldState
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest


def _use(target, detail=None):
    return ActionRequest(action=ActionType.USE, target=target, detail=detail)


# ── validation failures ───────────────────────────────────────────────────

def test_use_item_not_in_inventory_or_location(use_state):
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("nonexistent"), use_state)
    assert result.success is False
    assert "没有" in result.message
    assert diff is None


def test_use_item_no_effects(use_state):
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("inert_item"), use_state)
    assert result.success is False
    assert "无法使用" in result.message


def test_use_item_usable_with_no_detail(use_state):
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("cellar_key", detail=None), use_state)
    assert result.success is False
    assert "用在什么上" in result.message


def test_use_item_usable_with_wrong_target(use_state):
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("cellar_key", detail="wrong_target"), use_state)
    assert result.success is False
    assert "不能用在这里" in result.message


# ── success cases ─────────────────────────────────────────────────────────

def test_use_item_correct_target_succeeds(use_state):
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), use_state)
    assert result.success is True
    assert diff is not None


def test_use_item_no_usable_with_succeeds_without_detail(use_state):
    """Items with empty usable_with don't require a detail target."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("rusty_box"), use_state)
    assert result.success is True
    assert diff is not None


def test_use_cellar_key_unlocks_door_and_consumes(use_state):
    """unlock + consume effects both applied: exit unlocked and key removed from inventory."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), use_state)
    assert result.success is True

    new_state = use_state.apply(diff)
    assert new_state.locations["bar_area"].exits["down"].locked is False
    assert "cellar_key" not in new_state.characters["player"].inventory


def test_use_message_combined(use_state):
    """Message includes text from effects that return one."""
    from tavern.engine.rules import RulesEngine
    engine = RulesEngine()
    result, diff = engine.validate(_use("cellar_key", detail="cellar_door"), use_state)
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


def test_merge_diffs_deep_merges_same_location():
    """Two effects targeting same location different fields don't overwrite each other."""
    from tavern.engine.rules import _merge_diffs
    from tavern.world.models import Exit

    exit_unlocked = Exit(target="cellar", locked=False, description="铁门")
    a = StateDiff(updated_locations={"bar_area": {"exits": {"down": exit_unlocked}}})
    b = StateDiff(updated_locations={"bar_area": {"items": ("spare_key",)}})
    merged = _merge_diffs(a, b)

    assert "exits" in merged.updated_locations["bar_area"]
    assert "items" in merged.updated_locations["bar_area"]


def test_merge_diffs_recursive_depth():
    """Deep merge works at depth-3: two effects both modify exits of same location."""
    from tavern.engine.rules import _merge_diffs
    from tavern.world.models import Exit

    exit_a = Exit(target="cellar", locked=False, description="铁门")
    exit_b = Exit(target="backyard", locked=False, description="后门")
    a = StateDiff(updated_locations={"bar_area": {"exits": {"down": exit_a}}})
    b = StateDiff(updated_locations={"bar_area": {"exits": {"west": exit_b}}})
    merged = _merge_diffs(a, b)

    assert "down" in merged.updated_locations["bar_area"]["exits"]
    assert "west" in merged.updated_locations["bar_area"]["exits"]


def test_unlock_and_consume_merge(use_state):
    """Unlock + consume effects produce a merged diff with both updates."""
    from tavern.engine.use_effects import USE_EFFECT_REGISTRY
    from tavern.engine.rules import _merge_diffs

    eff_unlock = UseEffect(type="unlock", location="bar_area", exit_direction="down")
    eff_consume = UseEffect(type="consume")

    diff_a, _ = USE_EFFECT_REGISTRY["unlock"](eff_unlock, "cellar_key", use_state)
    state2 = use_state.apply(diff_a)
    diff_b, _ = USE_EFFECT_REGISTRY["consume"](eff_consume, "cellar_key", state2)

    combined = _merge_diffs(diff_a, diff_b)
    assert "bar_area" in combined.updated_locations
    assert "player" in combined.updated_characters
    new_inv = combined.updated_characters["player"]["inventory"]
    assert "cellar_key" not in new_inv
