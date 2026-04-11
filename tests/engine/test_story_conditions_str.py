from __future__ import annotations

import pytest

from tavern.engine.story_conditions import parse_condition_str, evaluate_condition_str
from tavern.world.memory import EventTimeline, RelationshipGraph, RelationshipDelta
from tavern.world.models import Character, Event, Location
from tavern.world.state import WorldState


def _make_timeline(event_ids: list[str]) -> EventTimeline:
    events = tuple(
        Event(id=eid, type="test", description="", actor="player", turn=1)
        for eid in event_ids
    )
    return EventTimeline(events)


def _make_state() -> WorldState:
    return WorldState(
        player_id="player",
        characters={
            "player": Character(
                id="player", name="冒险者", location_id="tavern_hall",
                role="player", traits=[], stats={}, inventory=(),
            ),
        },
        locations={
            "tavern_hall": Location(
                id="tavern_hall", name="酒馆大厅", description="大厅",
                atmosphere="warm", exits={}, items=(), npcs=(),
            ),
        },
    )


def test_parse_event_condition():
    cond = parse_condition_str("event:cellar_secret_revealed")
    assert cond.type == "event"
    assert cond.event_id == "cellar_secret_revealed"
    assert cond.check == "exists"


def test_parse_event_exists_explicit():
    cond = parse_condition_str("event_exists:cellar_entered")
    assert cond.type == "event"
    assert cond.event_id == "cellar_entered"
    assert cond.check == "exists"


def test_parse_event_not_exists():
    cond = parse_condition_str("event_not_exists:cellar_entered")
    assert cond.type == "event"
    assert cond.event_id == "cellar_entered"
    assert cond.check == "not_exists"


def test_parse_relationship_condition():
    cond = parse_condition_str("relationship:bartender_grim >= 30")
    assert cond.type == "relationship"
    assert cond.source == "player"
    assert cond.target == "bartender_grim"
    assert cond.operator == ">="
    assert cond.value == 30


def test_parse_inventory_condition():
    cond = parse_condition_str("inventory:cellar_key")
    assert cond.type == "inventory"
    assert cond.event_id == "cellar_key"


def test_parse_quest_condition():
    cond = parse_condition_str("quest:main_quest:completed")
    assert cond.type == "quest"
    assert cond.event_id == "main_quest"
    assert cond.check == "completed"


def test_parse_location_condition():
    cond = parse_condition_str("location:tavern_hall")
    assert cond.type == "location"
    assert cond.event_id == "tavern_hall"


def test_parse_invalid_empty():
    with pytest.raises(ValueError, match="Cannot parse"):
        parse_condition_str("")


def test_parse_invalid_no_colon():
    with pytest.raises(ValueError, match="Cannot parse"):
        parse_condition_str("nocolon")


def test_evaluate_event_exists():
    state = _make_state()
    timeline = _make_timeline(["cellar_secret_revealed"])
    graph = RelationshipGraph()
    assert evaluate_condition_str("event:cellar_secret_revealed", state, timeline, graph) is True


def test_evaluate_event_not_found():
    state = _make_state()
    timeline = _make_timeline([])
    graph = RelationshipGraph()
    assert evaluate_condition_str("event:cellar_secret_revealed", state, timeline, graph) is False


def test_evaluate_relationship_ge():
    state = _make_state()
    graph = RelationshipGraph()
    graph.update(RelationshipDelta(src="player", tgt="bartender_grim", delta=35))
    timeline = _make_timeline([])
    assert evaluate_condition_str("relationship:bartender_grim >= 30", state, timeline, graph) is True


def test_evaluate_relationship_lt():
    state = _make_state()
    graph = RelationshipGraph()
    graph.update(RelationshipDelta(src="player", tgt="bartender_grim", delta=10))
    timeline = _make_timeline([])
    assert evaluate_condition_str("relationship:bartender_grim >= 30", state, timeline, graph) is False


def test_evaluate_location():
    state = _make_state()
    timeline = _make_timeline([])
    graph = RelationshipGraph()
    assert evaluate_condition_str("location:tavern_hall", state, timeline, graph) is True
    assert evaluate_condition_str("location:bar_area", state, timeline, graph) is False
