from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx

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


class RelationshipGraph:
    def __init__(self, snapshot: dict | None = None) -> None:
        if snapshot is not None:
            try:
                self._g: nx.DiGraph = nx.node_link_graph(snapshot, directed=True, edges="links")
            except Exception:
                logger.warning("RelationshipGraph: snapshot corrupt, initializing empty graph")
                self._g = nx.DiGraph()
        else:
            self._g = nx.DiGraph()

    def get(self, src: str, tgt: str) -> Relationship:
        value = self._g.edges.get((src, tgt), {}).get("value", 0)
        return Relationship(src=src, tgt=tgt, value=value)

    def update(self, delta: RelationshipDelta) -> Relationship:
        current = self.get(delta.src, delta.tgt).value
        new_value = max(-100, min(100, current + delta.delta))
        self._g.add_edge(delta.src, delta.tgt, value=new_value)
        return Relationship(src=delta.src, tgt=delta.tgt, value=new_value)

    def get_all_for(self, char_id: str) -> list[Relationship]:
        return [
            Relationship(src=char_id, tgt=tgt, value=data.get("value", 0))
            for tgt, data in self._g[char_id].items()
        ] if char_id in self._g else []

    def describe_for_prompt(self, char_id: str) -> str:
        rels = self.get_all_for(char_id)
        if not rels:
            return f"（{char_id}尚无记录的关系）"
        lines: list[str] = []
        for r in rels:
            if r.value >= 60:
                label = "非常友好"
            elif r.value >= 20:
                label = "友好"
            elif r.value <= -60:
                label = "非常敌对"
            elif r.value <= -20:
                label = "敌对"
            else:
                label = "中立"
            lines.append(f"{char_id}对{r.tgt}的信任: {r.value}（{label}）")
        return "\n".join(lines)

    def to_snapshot(self) -> dict:
        return nx.node_link_data(self._g, edges="links")
