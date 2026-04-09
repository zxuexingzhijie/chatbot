from __future__ import annotations

import pytest
from tavern.world.memory import (
    EventTimeline,
    MemoryContext,
    MemorySystem,
    RelationshipDelta,
    Relationship,
)
from tavern.world.models import Event


def _make_event(id: str, turn: int, actor: str = "player", type: str = "move") -> Event:
    return Event(
        id=id,
        turn=turn,
        type=type,
        actor=actor,
        description=f"事件{id}发生了",
        consequences=(),
    )


class TestMemoryContext:
    def test_creation(self):
        ctx = MemoryContext(
            recent_events="最近：移动到吧台",
            relationship_summary="旅行者对你信任20",
            active_skills_text="",
        )
        assert ctx.recent_events == "最近：移动到吧台"
        assert ctx.active_skills_text == ""

    def test_immutable(self):
        ctx = MemoryContext(
            recent_events="test",
            relationship_summary="test",
            active_skills_text="",
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.recent_events = "changed"  # type: ignore


class TestEventTimeline:
    def test_recent_returns_last_n_events(self):
        events = tuple(_make_event(str(i), i) for i in range(10))
        timeline = EventTimeline(events)
        recent = timeline.recent(3)
        assert len(recent) == 3
        assert recent[-1].id == "9"

    def test_recent_returns_all_if_fewer(self):
        events = (_make_event("a", 1), _make_event("b", 2))
        timeline = EventTimeline(events)
        assert len(timeline.recent(10)) == 2

    def test_query_by_actor(self):
        events = (
            _make_event("e1", 1, actor="player"),
            _make_event("e2", 2, actor="bartender"),
            _make_event("e3", 3, actor="player"),
        )
        timeline = EventTimeline(events)
        result = timeline.query(actor="player")
        assert len(result) == 2
        assert all(e.actor == "player" for e in result)

    def test_query_by_type(self):
        events = (
            Event(id="e1", turn=1, type="move", actor="player", description="移动", consequences=()),
            Event(id="e2", turn=2, type="talk", actor="player", description="对话", consequences=()),
        )
        timeline = EventTimeline(events)
        result = timeline.query(event_type="talk")
        assert len(result) == 1
        assert result[0].id == "e2"

    def test_query_after_turn(self):
        events = tuple(_make_event(str(i), i) for i in range(5))
        timeline = EventTimeline(events)
        result = timeline.query(after_turn=2)
        assert all(e.turn > 2 for e in result)

    def test_summarize_empty_timeline(self):
        timeline = EventTimeline(())
        text = timeline.summarize()
        assert isinstance(text, str)

    def test_summarize_includes_recent_descriptions(self):
        events = (
            _make_event("e1", 1),
            _make_event("e2", 2),
        )
        timeline = EventTimeline(events)
        text = timeline.summarize()
        assert "事件e1发生了" in text or "事件e2发生了" in text

    def test_summarize_omits_old_events_with_placeholder(self):
        events = tuple(_make_event(str(i), i) for i in range(7))
        timeline = EventTimeline(events)
        text = timeline.summarize()
        assert "省略" in text or "早期" in text

    def test_has_event_by_id(self):
        events = (_make_event("quest_started", 1),)
        timeline = EventTimeline(events)
        assert timeline.has("quest_started") is True
        assert timeline.has("nonexistent") is False


class TestRelationshipGraph:
    def test_get_nonexistent_edge_returns_zero(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        rel = g.get("player", "traveler")
        assert rel.value == 0
        assert rel.src == "player"
        assert rel.tgt == "traveler"

    def test_update_adds_edge(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        rel = g.update(RelationshipDelta(src="player", tgt="traveler", delta=20))
        assert rel.value == 20

    def test_update_clamps_upper(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=90))
        rel = g.update(RelationshipDelta(src="a", tgt="b", delta=90))
        assert rel.value == 100

    def test_update_clamps_lower(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=-90))
        rel = g.update(RelationshipDelta(src="a", tgt="b", delta=-90))
        assert rel.value == -100

    def test_get_all_for_returns_outgoing(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="traveler", tgt="player", delta=10))
        g.update(RelationshipDelta(src="traveler", tgt="grim", delta=-5))
        g.update(RelationshipDelta(src="player", tgt="traveler", delta=15))
        rels = g.get_all_for("traveler")
        assert len(rels) == 2
        assert all(r.src == "traveler" for r in rels)

    def test_describe_for_prompt_contains_char(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="traveler", tgt="player", delta=25))
        text = g.describe_for_prompt("traveler")
        assert "traveler" in text or "player" in text
        assert "25" in text or "友好" in text

    def test_snapshot_round_trip(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=30))
        snapshot = g.to_snapshot()
        g2 = RelationshipGraph(snapshot=snapshot)
        assert g2.get("a", "b").value == 30

    def test_init_from_none_snapshot(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph(snapshot=None)
        assert g.get("x", "y").value == 0

    def test_corrupt_snapshot_logs_warning_and_initializes_empty(self, caplog):
        from tavern.world.memory import RelationshipGraph
        import logging
        with caplog.at_level(logging.WARNING, logger="tavern.world.memory"):
            g = RelationshipGraph(snapshot={"this_is": "not_a_valid_graph"})
        assert g.get("x", "y").value == 0
        assert any("corrupt" in r.message.lower() or "snapshot" in r.message.lower()
                   for r in caplog.records)


class TestMemorySystem:
    def _make_state(self, trust: int = 0):
        from tavern.world.models import Character, CharacterRole, Location
        from tavern.world.state import WorldState
        return WorldState(
            turn=3,
            player_id="player",
            locations={"hall": Location(id="hall", name="大厅", description="大厅", npcs=("traveler",))},
            characters={
                "player": Character(
                    id="player", name="冒险者", role=CharacterRole.PLAYER,
                    stats={"hp": 100}, location_id="hall",
                ),
                "traveler": Character(
                    id="traveler", name="旅行者", role=CharacterRole.NPC,
                    stats={"trust": trust}, location_id="hall",
                ),
            },
            items={},
            timeline=(
                Event(id="e1", turn=1, type="move", actor="player", description="进入酒馆", consequences=()),
            ),
        )

    def test_build_context_returns_memory_context(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state)
        ctx = mem.build_context("traveler", state)
        assert isinstance(ctx, MemoryContext)
        assert isinstance(ctx.recent_events, str)
        assert isinstance(ctx.relationship_summary, str)
        assert isinstance(ctx.active_skills_text, str)

    def test_build_context_recent_events_contains_event(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state)
        ctx = mem.build_context("traveler", state)
        assert "进入酒馆" in ctx.recent_events

    def test_apply_diff_syncs_relationship(self):
        from tavern.world.memory import MemorySystem
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)

        diff = StateDiff(
            relationship_changes=(
                {"src": "traveler", "tgt": "player", "delta": 30},
            ),
        )
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)

        ctx = mem.build_context("traveler", new_state)
        assert "30" in ctx.relationship_summary or "traveler" in ctx.relationship_summary

    def test_apply_diff_empty_relationship_changes_is_noop(self):
        from tavern.world.memory import MemorySystem
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)
        diff = StateDiff(turn_increment=1)
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)  # should not raise

    def test_apply_diff_rebuilds_timeline(self):
        from tavern.world.memory import MemorySystem
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)
        new_event = Event(id="e2", turn=4, type="talk", actor="traveler",
                          description="旅行者谈起北方", consequences=())
        diff = StateDiff(new_events=(new_event,))
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)
        ctx = mem.build_context("traveler", new_state)
        assert "旅行者谈起北方" in ctx.recent_events

    def test_sync_to_state_writes_snapshot(self):
        from tavern.world.memory import MemorySystem, RelationshipGraph
        state = self._make_state()
        mem = MemorySystem(state=state)
        mem._relationship_graph.update(RelationshipDelta(src="a", tgt="b", delta=10))
        new_state = mem.sync_to_state(state)
        g2 = RelationshipGraph(snapshot=dict(new_state.relationships_snapshot))
        assert g2.get("a", "b").value == 10

    def test_init_with_no_skills_dir(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state, skills_dir=None)
        ctx = mem.build_context("traveler", state)
        assert ctx.active_skills_text == ""


class TestGetPlayerRelationships:
    def test_returns_relationships_for_player(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="traveler", delta=25))
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="bartender_grim", delta=-10))

        rels = memory.get_player_relationships()

        assert len(rels) == 2
        ids = {r.tgt for r in rels}
        assert ids == {"traveler", "bartender_grim"}

    def test_returns_empty_list_when_no_relationships(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)

        rels = memory.get_player_relationships()

        assert rels == []

    def test_returns_relationship_type(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="traveler", delta=40))

        rels = memory.get_player_relationships()

        assert len(rels) == 1
        assert isinstance(rels[0], Relationship)
        assert rels[0].src == "player"
        assert rels[0].tgt == "traveler"
        assert rels[0].value == 40
