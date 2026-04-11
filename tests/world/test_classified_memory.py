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


def test_build_context_updates_last_relevant_turn():
    state = _make_state(turn=10)
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="古老的秘密", importance=8,
        created_turn=1, last_relevant_turn=1,
    ))
    mem.build_context(actor="player", state=state)
    entries = mem._classified[MemoryType.LORE]
    refreshed = [e for e in entries if e.id == "m1"]
    assert refreshed
    assert refreshed[0].last_relevant_turn == 10


def test_recency_score_uses_last_relevant_turn():
    state = _make_state(turn=100)
    mem = ClassifiedMemorySystem(state=state)
    old = MemoryEntry(id="old", memory_type=MemoryType.LORE, content="x", importance=5, created_turn=1, last_relevant_turn=1)
    refreshed = MemoryEntry(id="new", memory_type=MemoryType.LORE, content="y", importance=5, created_turn=1, last_relevant_turn=90)
    assert mem._recency_score(refreshed, 100) > mem._recency_score(old, 100)


def test_summarize_custom_n():
    events = tuple(
        Event(id=f"e{i}", type="test", description=f"事件{i}", actor="player", turn=i)
        for i in range(10)
    )
    tl = EventTimeline(events)
    summary_3 = tl.summarize(n=3)
    assert "事件7" in summary_3
    assert "事件8" in summary_3
    assert "事件9" in summary_3
    assert "已省略7条早期事件" in summary_3

    summary_default = tl.summarize()
    assert "已省略5条早期事件" in summary_default


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


# --- Phase 2: MemoryExtractor wiring tests ---

from tavern.world.memory_extractor import EXTRACTION_RULES, MemoryExtractor


def test_apply_diff_extracts_dialogue_memory():
    state = _make_state()
    extractor = MemoryExtractor(EXTRACTION_RULES)
    mem = ClassifiedMemorySystem(state=state, extractor=extractor)
    dialogue_event = Event(
        id="e_dlg", turn=1, type="dialogue_summary_innkeeper",
        actor="player", description="和旅店老板聊天",
        data={"has_secret": True, "summary_text": "旅店老板透露了地窖秘密"},
    )
    diff = StateDiff(new_events=(dialogue_event,), turn_increment=1)
    new_state = state.apply(diff)
    mem.apply_diff(diff, new_state)
    ctx = mem.build_context(actor="player", state=new_state)
    assert "旅店老板透露了地窖秘密" in ctx.active_skills_text


def test_apply_diff_extracts_quest_memory():
    state = _make_state()
    extractor = MemoryExtractor(EXTRACTION_RULES)
    mem = ClassifiedMemorySystem(state=state, extractor=extractor)
    quest_event = Event(
        id="e_q", turn=2, type="quest_started",
        actor="player", description="任务开始",
        data={"quest_id": "find_gem", "status": "active"},
    )
    diff = StateDiff(new_events=(quest_event,), turn_increment=1)
    new_state = state.apply(diff)
    mem.apply_diff(diff, new_state)
    ctx = mem.build_context(actor="player", state=new_state)
    assert "find_gem" in ctx.recent_events


def test_apply_diff_no_extraction_when_no_extractor():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    dialogue_event = Event(
        id="e_dlg2", turn=1, type="dialogue_summary_innkeeper",
        actor="player", description="和旅店老板聊天",
        data={"summary_text": "秘密信息"},
    )
    diff = StateDiff(new_events=(dialogue_event,), turn_increment=1)
    new_state = state.apply(diff)
    mem.apply_diff(diff, new_state)
    ctx = mem.build_context(actor="player", state=new_state)
    assert "秘密信息" not in ctx.active_skills_text


# --- Phase 3: Classified memory persistence tests ---


def test_classified_to_snapshot_round_trip():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="地窖的秘密", importance=8,
        created_turn=1, last_relevant_turn=1,
    ))
    mem.add_memory(MemoryEntry(
        id="m2", memory_type=MemoryType.QUEST,
        content="寻找宝石", importance=7,
        created_turn=2, last_relevant_turn=2,
    ))
    snapshot = mem.classified_to_snapshot()
    restored = ClassifiedMemorySystem._entries_from_snapshot(snapshot)
    assert len(restored[MemoryType.LORE]) == 1
    assert restored[MemoryType.LORE][0].content == "地窖的秘密"
    assert len(restored[MemoryType.QUEST]) == 1
    assert restored[MemoryType.QUEST][0].content == "寻找宝石"


def test_sync_to_state_includes_classified_memories():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.DISCOVERY,
        content="隐藏通道", importance=3,
        created_turn=1, last_relevant_turn=1,
    ))
    synced = mem.sync_to_state(state)
    assert "discovery" in synced.classified_memories_snapshot
    assert len(synced.classified_memories_snapshot["discovery"]) == 1


def test_rebuild_restores_classified_memories():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="格林的秘密", importance=8,
        created_turn=1, last_relevant_turn=1,
    ))
    synced = mem.sync_to_state(state)

    mem2 = ClassifiedMemorySystem(state=synced)
    mem2.rebuild(synced)
    ctx = mem2.build_context(actor="player", state=synced)
    assert "格林的秘密" in ctx.active_skills_text


def test_rebuild_with_empty_classified_snapshot():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    mem.add_memory(MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="旧记忆", importance=5,
        created_turn=1, last_relevant_turn=1,
    ))
    mem.rebuild(state)
    ctx = mem.build_context(actor="player", state=state)
    assert "旧记忆" not in ctx.active_skills_text
