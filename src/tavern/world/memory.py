from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tavern.world.models import Event

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryContext:
    recent_events: str
    relationship_summary: str
    active_skills_text: str


@dataclass(frozen=True)
class RelationshipDelta:
    src: str
    tgt: str
    delta: int


@dataclass(frozen=True)
class Relationship:
    src: str
    tgt: str
    value: int  # clamped to [-100, 100]


class EventTimeline:
    __slots__ = ("_events",)

    def __init__(self, events: tuple[Event, ...]) -> None:
        self._events = events

    def recent(self, n: int = 5) -> list[Event]:
        return list(self._events[-n:]) if n > 0 else []

    def query(
        self,
        actor: str | None = None,
        event_type: str | None = None,
        after_turn: int | None = None,
    ) -> list[Event]:
        result = list(self._events)
        if actor is not None:
            result = [e for e in result if e.actor == actor]
        if event_type is not None:
            result = [e for e in result if e.type == event_type]
        if after_turn is not None:
            result = [e for e in result if e.turn > after_turn]
        return result

    def summarize(self) -> str:
        if not self._events:
            return "（尚无历史事件）"
        recent = list(self._events[-5:])
        older_count = max(0, len(self._events) - 5)
        parts: list[str] = []
        if older_count > 0:
            parts.append(f"[已省略{older_count}条早期事件]")
        for e in recent:
            parts.append(e.description)
        return "\n".join(parts)

    def has(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._events)
