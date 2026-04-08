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


def test_consume_effect_item_not_in_inventory_skips():
    from tavern.engine.use_effects import effect_consume
    eff = UseEffect(type="consume")
    state = _make_state(player_inventory=("other_item",))
    diff, msg = effect_consume(eff, "cellar_key", state)
    assert diff.updated_characters == {}
    assert msg is None


def test_story_event_uses_explicit_actor():
    from tavern.engine.use_effects import effect_story_event
    eff = UseEffect(
        type="story_event",
        event=EventSpec(id="evt", type="story", description="d", actor="npc_bartender"),
    )
    state = _make_state()
    diff, msg = effect_story_event(eff, "box", state)
    assert diff.new_events[0].actor == "npc_bartender"


def test_spawn_item_to_location_none_skips():
    from tavern.engine.use_effects import effect_spawn_item
    eff = UseEffect(type="spawn_item", item_id="spare_key", spawn_to_inventory=False, location=None)
    state = _make_state()
    diff, msg = effect_spawn_item(eff, "box", state)
    assert diff.updated_locations == {}
    assert msg is None
