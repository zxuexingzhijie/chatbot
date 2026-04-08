from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from tavern.world.skills import ActivationCondition


def _make_state(player_location="tavern", inventory=()):
    state = MagicMock()
    state.player_id = "player"
    state.characters = {
        "player": MagicMock(location_id=player_location, inventory=inventory)
    }
    return state


def _make_timeline(event_ids=()):
    tl = MagicMock()
    tl.has = lambda eid: eid in event_ids
    return tl


def _make_relationships(value=0):
    rel = MagicMock()
    rel.value = value
    rg = MagicMock()
    rg.get = lambda src, tgt: rel
    return rg


def test_location_condition_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="location", event_id="cellar")
    state = _make_state(player_location="cellar")
    result = CONDITION_REGISTRY["location"](cond, state, None, None)
    assert result is True


def test_location_condition_no_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="location", event_id="cellar")
    state = _make_state(player_location="tavern")
    result = CONDITION_REGISTRY["location"](cond, state, None, None)
    assert result is False


def test_inventory_condition_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="inventory", event_id="rusty_key")
    state = _make_state(inventory=("rusty_key", "torch"))
    result = CONDITION_REGISTRY["inventory"](cond, state, None, None)
    assert result is True


def test_relationship_condition():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(
        type="relationship",
        source="player", target="bartender_grim",
        attribute="trust", operator=">=", value=30,
    )
    relationships = _make_relationships(value=35)
    result = CONDITION_REGISTRY["relationship"](cond, None, None, relationships)
    assert result is True


def test_event_condition_exists():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="event", event_id="cellar_entered", check="exists")
    timeline = _make_timeline(event_ids=("cellar_entered",))
    result = CONDITION_REGISTRY["event"](cond, None, timeline, None)
    assert result is True


def test_quest_condition():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="quest", event_id="cellar_mystery", check="discovered")
    state = MagicMock()
    state.quests = {"cellar_mystery": {"status": "discovered"}}
    result = CONDITION_REGISTRY["quest"](cond, state, None, None)
    assert result is True
