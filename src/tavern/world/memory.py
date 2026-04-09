from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
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


class RelationshipGraph:
    def __init__(self, snapshot: dict | None = None) -> None:
        self._g: dict[str, dict[str, int]] = {}
        if snapshot is not None:
            try:
                for link in snapshot["links"]:
                    src, tgt = link["source"], link["target"]
                    self._g.setdefault(src, {})[tgt] = link["value"]
            except Exception:
                logger.warning("RelationshipGraph: snapshot corrupt, initializing empty graph")
                self._g = {}

    def get(self, src: str, tgt: str) -> Relationship:
        value = self._g.get(src, {}).get(tgt, 0)
        return Relationship(src=src, tgt=tgt, value=value)

    def update(self, delta: RelationshipDelta) -> Relationship:
        current = self._g.get(delta.src, {}).get(delta.tgt, 0)
        new_value = max(-100, min(100, current + delta.delta))
        self._g.setdefault(delta.src, {})[delta.tgt] = new_value
        return Relationship(src=delta.src, tgt=delta.tgt, value=new_value)

    def get_all_for(self, char_id: str) -> list[Relationship]:
        return [
            Relationship(src=char_id, tgt=tgt, value=val)
            for tgt, val in self._g.get(char_id, {}).items()
        ]

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
        nodes: set[str] = set()
        links: list[dict] = []
        for src, targets in self._g.items():
            nodes.add(src)
            for tgt, value in targets.items():
                nodes.add(tgt)
                links.append({"source": src, "target": tgt, "value": value})
        return {
            "directed": True,
            "multigraph": False,
            "graph": {},
            "nodes": [{"id": n} for n in sorted(nodes)],
            "links": links,
        }


class MemorySystem:
    def __init__(self, state: WorldState, skills_dir: Path | None = None) -> None:
        from tavern.world.skills import SkillManager  # lazy to avoid circular
        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("MemorySystem: failed to restore RelationshipGraph, using empty")
            self._relationship_graph = RelationshipGraph()
        self._skill_manager = SkillManager()
        if skills_dir is not None:
            self._skill_manager.load_skills(skills_dir)

    def apply_diff(self, diff: StateDiff, new_state: WorldState) -> None:
        for change in diff.relationship_changes:
            if isinstance(change, dict):
                delta = RelationshipDelta(
                    src=change["src"], tgt=change["tgt"], delta=change["delta"]
                )
            else:
                delta = change
            self._relationship_graph.update(delta)
        self._timeline = EventTimeline(new_state.timeline)

    def build_context(
        self,
        actor: str,
        state: WorldState,
        max_tokens: int = 2000,
    ) -> MemoryContext:
        recent_events = self._timeline.summarize()
        relationship_summary = self._relationship_graph.describe_for_prompt(actor)
        max_chars = max(100, max_tokens * 3 // 4)
        active_skills = self._skill_manager.get_active_skills(
            actor, state, self._timeline, self._relationship_graph
        )
        active_skills_text = self._skill_manager.inject_to_prompt(
            active_skills, max_chars=max_chars
        )
        return MemoryContext(
            recent_events=recent_events,
            relationship_summary=relationship_summary,
            active_skills_text=active_skills_text,
        )

    def get_player_relationships(self) -> list[Relationship]:
        return self._relationship_graph.get_all_for("player")

    def sync_to_state(self, state: WorldState) -> WorldState:
        snapshot = self._relationship_graph.to_snapshot()
        return state.model_copy(update={"relationships_snapshot": snapshot})
