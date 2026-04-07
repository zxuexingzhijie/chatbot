from __future__ import annotations

import pytest
from tavern.world.memory import (
    EventTimeline,
    MemoryContext,
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
