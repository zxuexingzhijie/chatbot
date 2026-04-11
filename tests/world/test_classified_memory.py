from __future__ import annotations

import pytest

from tavern.world.memory import MemoryBudget, MemoryEntry, MemoryType


def test_memory_type_values():
    assert MemoryType.LORE.value == "lore"
    assert MemoryType.QUEST.value == "quest"
    assert MemoryType.RELATIONSHIP.value == "relationship"
    assert MemoryType.DISCOVERY.value == "discovery"


def test_memory_entry_frozen():
    entry = MemoryEntry(
        id="m1",
        memory_type=MemoryType.LORE,
        content="格林透露了地窖秘密",
        importance=8,
        created_turn=5,
        last_relevant_turn=5,
    )
    assert entry.importance == 8
    with pytest.raises(AttributeError):
        entry.importance = 10


def test_memory_entry_fields():
    entry = MemoryEntry(
        id="m2",
        memory_type=MemoryType.DISCOVERY,
        content="桌下什么也没有",
        importance=2,
        created_turn=3,
        last_relevant_turn=3,
    )
    assert entry.memory_type == MemoryType.DISCOVERY
    assert entry.content == "桌下什么也没有"


def test_memory_budget_defaults():
    budget = MemoryBudget()
    assert budget.lore == 200
    assert budget.quest == 300
    assert budget.relationship == 150
    assert budget.discovery == 100


def test_memory_budget_custom():
    budget = MemoryBudget(lore=500, quest=200, relationship=100, discovery=50)
    assert budget.lore == 500
    assert budget.quest == 200


# --- ClassifiedMemorySystem tests ---

from tavern.world.memory import (
    ClassifiedMemorySystem,
    EventTimeline,
    MemoryContext,
    RelationshipGraph,
    RelationshipDelta,
)
from tavern.world.models import Character, Event, Location
from tavern.world.state import WorldState, StateDiff


def _make_state(**overrides):
    defaults = {
        "player_id": "player",
        "characters": {
            "player": Character(
                id="player", name="冒险者", role="player",
                location_id="tavern_hall", traits=[], stats={"hp": 100}, inventory=(),
            ),
        },
        "locations": {
            "tavern_hall": Location(
                id="tavern_hall", name="酒馆大厅", description="大厅",
                atmosphere="warm", exits={}, items=(), npcs=(),
            ),
        },
        "timeline": (),
    }
    defaults.update(overrides)
    return WorldState(**defaults)


def test_classified_memory_build_context_returns_memory_context():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    ctx = mem.build_context(actor="player", state=state)
    assert isinstance(ctx, MemoryContext)
    assert isinstance(ctx.recent_events, str)
    assert isinstance(ctx.relationship_summary, str)
    assert isinstance(ctx.active_skills_text, str)


def test_add_lore_appears_in_skills_text():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="格林透露了秘密", importance=8,
        created_turn=1, last_relevant_turn=1,
    ))
    ctx = mem.build_context(actor="player", state=state)
    assert "格林透露了秘密" in ctx.active_skills_text


def test_add_discovery_appears_in_recent_events():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m2", memory_type=MemoryType.DISCOVERY,
        content="桌下什么也没有", importance=2,
        created_turn=1, last_relevant_turn=1,
    ))
    ctx = mem.build_context(actor="player", state=state)
    assert "桌下什么也没有" in ctx.recent_events


def test_add_quest_appears_in_recent_events():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m3", memory_type=MemoryType.QUEST,
        content="地窖任务已开始", importance=7,
        created_turn=1, last_relevant_turn=1,
    ))
    ctx = mem.build_context(actor="player", state=state)
    assert "地窖任务" in ctx.recent_events


def test_add_relationship_appears_in_summary():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m4", memory_type=MemoryType.RELATIONSHIP,
        content="格林信任度+15", importance=6,
        created_turn=1, last_relevant_turn=1,
    ))
    ctx = mem.build_context(actor="player", state=state)
    assert "格林信任度" in ctx.relationship_summary


def test_lore_decays_slower_than_discovery():
    state = _make_state(turn=100)
    mem = ClassifiedMemorySystem(state=state)
    lore = MemoryEntry(id="l", memory_type=MemoryType.LORE, content="x", importance=5, created_turn=1, last_relevant_turn=1)
    disc = MemoryEntry(id="d", memory_type=MemoryType.DISCOVERY, content="y", importance=5, created_turn=1, last_relevant_turn=1)
    assert mem._recency_score(lore, 100) > mem._recency_score(disc, 100)


def test_budget_truncation():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state, budget=MemoryBudget(discovery=20))
    for i in range(20):
        mem.add_memory(MemoryEntry(
            id=f"d{i}", memory_type=MemoryType.DISCOVERY,
            content=f"发现{i}：" + "x" * 50, importance=2,
            created_turn=i, last_relevant_turn=i,
        ))
    ctx = mem.build_context(actor="player", state=state)
    assert len(ctx.recent_events) < 2000


def test_get_player_relationships():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    rels = mem.get_player_relationships("player")
    assert isinstance(rels, list)


def test_apply_diff_updates_relationships():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    diff = StateDiff(
        relationship_changes=(
            {"src": "player", "tgt": "bartender_grim", "delta": 10},
        ),
    )
    mem.apply_diff(diff, state)
    rels = mem.get_player_relationships("player")
    values = [r.value for r in rels if r.tgt == "bartender_grim"]
    assert values == [10]


def test_sync_to_state():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    new_state = mem.sync_to_state(state)
    assert hasattr(new_state, "relationships_snapshot")


def test_timeline_property():
    events = (Event(id="e1", type="test", description="事件1", actor="player", turn=1),)
    state = _make_state(timeline=events)
    mem = ClassifiedMemorySystem(state=state)
    assert mem.timeline.has("e1")


def test_relationship_graph_property():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    assert mem.relationship_graph is not None


def test_rebuild_clears_classified():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="old", importance=5, created_turn=1, last_relevant_turn=1,
    ))
    mem.rebuild(state)
    ctx = mem.build_context(actor="player", state=state)
    assert "old" not in ctx.active_skills_text


def test_backward_compat_alias():
    from tavern.world.memory import MemorySystem
    assert MemorySystem is ClassifiedMemorySystem
