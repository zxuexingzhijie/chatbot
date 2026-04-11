from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
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


class MemoryType(Enum):
    LORE = "lore"
    QUEST = "quest"
    RELATIONSHIP = "relationship"
    DISCOVERY = "discovery"


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    memory_type: MemoryType
    content: str
    importance: int
    created_turn: int
    last_relevant_turn: int


@dataclass(frozen=True)
class MemoryBudget:
    lore: int = 200
    quest: int = 300
    relationship: int = 150
    discovery: int = 100


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

    def summarize(self, n: int = 5) -> str:
        if not self._events:
            return "（尚无历史事件）"
        recent = list(self._events[-n:])
        older_count = max(0, len(self._events) - n)
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
        # Mutation exception: RelationshipGraph owns its internal adjacency dict.
        # It is the single source of truth for relationships; snapshots are
        # derived via to_snapshot() and sync_to_state(), so in-place mutation
        # here is safe and intentional.
        current = self._g.get(delta.src, {}).get(delta.tgt, 0)
        new_value = max(-100, min(100, current + delta.delta))
        self._g.setdefault(delta.src, {})[delta.tgt] = new_value
        return Relationship(src=delta.src, tgt=delta.tgt, value=new_value)

    def get_all_for(self, char_id: str) -> list[Relationship]:
        results: list[Relationship] = []
        for tgt, val in self._g.get(char_id, {}).items():
            results.append(Relationship(src=char_id, tgt=tgt, value=val))
        for src, targets in self._g.items():
            if src == char_id:
                continue
            if char_id in targets:
                results.append(Relationship(src=src, tgt=char_id, value=targets[char_id]))
        return results

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
            other = r.tgt if r.src == char_id else r.src
            if r.src == char_id:
                lines.append(f"{char_id}对{other}的信任: {r.value}（{label}）")
            else:
                lines.append(f"{other}对{char_id}的信任: {r.value}（{label}）")
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


_DECAY_RATES: dict[MemoryType, float] = {
    MemoryType.LORE: 0.01,
    MemoryType.QUEST: 0.05,
    MemoryType.RELATIONSHIP: 0.08,
    MemoryType.DISCOVERY: 0.2,
}


class ClassifiedMemorySystem:
    def __init__(
        self,
        state: WorldState,
        skills_dir: Path | None = None,
        budget: MemoryBudget | None = None,
        extractor: object | None = None,
    ) -> None:
        from tavern.world.skills import SkillManager

        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("ClassifiedMemorySystem: failed to restore RelationshipGraph, using empty")
            self._relationship_graph = RelationshipGraph()
        self._skill_manager = SkillManager()
        if skills_dir is not None:
            self._skill_manager.load_skills(skills_dir)
        self._budget = budget if budget is not None else MemoryBudget()
        self._classified: dict[MemoryType, list[MemoryEntry]] = {
            mt: [] for mt in MemoryType
        }
        self._extractor = extractor

    @property
    def timeline(self) -> EventTimeline:
        return self._timeline

    @property
    def relationship_graph(self) -> RelationshipGraph:
        return self._relationship_graph

    def add_memory(self, entry: MemoryEntry) -> None:
        self._classified[entry.memory_type].append(entry)

    def _recency_score(self, entry: MemoryEntry, current_turn: int) -> float:
        age = max(0, current_turn - entry.last_relevant_turn)
        decay_rate = _DECAY_RATES.get(entry.memory_type, 0.1)
        return 1.0 / (1.0 + age * decay_rate)

    @staticmethod
    def _refresh_entry(entry: MemoryEntry, current_turn: int) -> MemoryEntry:
        return MemoryEntry(
            id=entry.id,
            memory_type=entry.memory_type,
            content=entry.content,
            importance=entry.importance,
            created_turn=entry.created_turn,
            last_relevant_turn=current_turn,
        )

    def _truncate_to_budget(self, entries: list[MemoryEntry], budget_chars: int, current_turn: int | None = None) -> tuple[str, list[MemoryEntry]]:
        if not entries:
            return "", []
        parts: list[str] = []
        selected: list[MemoryEntry] = []
        total = 0
        for entry in entries:
            if total + len(entry.content) > budget_chars and total > 0:
                break
            parts.append(entry.content)
            total += len(entry.content)
            if current_turn is not None:
                selected.append(self._refresh_entry(entry, current_turn))
            else:
                selected.append(entry)
        return "\n".join(parts), selected

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
        if self._extractor is not None:
            for event in diff.new_events:
                entry = self._extractor.extract(event, event.turn)
                if entry is not None:
                    self.add_memory(entry)

    def build_context(
        self,
        actor: str,
        state: WorldState,
        max_tokens: int = 2000,
    ) -> MemoryContext:
        current_turn = getattr(state, "turn", 0)

        recent_events = self._timeline.summarize()
        relationship_summary = self._relationship_graph.describe_for_prompt(actor)
        max_chars = max(100, max_tokens * 3 // 4)
        active_skills = self._skill_manager.get_active_skills(
            actor, state, self._timeline, self._relationship_graph
        )
        active_skills_text = self._skill_manager.inject_to_prompt(
            active_skills, max_chars=max_chars
        )

        lore_entries = sorted(
            self._classified[MemoryType.LORE],
            key=lambda e: self._recency_score(e, current_turn),
            reverse=True,
        )
        lore_text, refreshed_lore = self._truncate_to_budget(lore_entries, self._budget.lore, current_turn)
        not_selected_lore = lore_entries[len(refreshed_lore):]
        self._classified[MemoryType.LORE] = refreshed_lore + not_selected_lore
        if lore_text:
            active_skills_text = (
                f"{active_skills_text}\n{lore_text}" if active_skills_text else lore_text
            )

        quest_entries = sorted(
            self._classified[MemoryType.QUEST],
            key=lambda e: self._recency_score(e, current_turn),
            reverse=True,
        )
        quest_text, refreshed_quest = self._truncate_to_budget(quest_entries, self._budget.quest, current_turn)
        not_selected_quest = quest_entries[len(refreshed_quest):]
        self._classified[MemoryType.QUEST] = refreshed_quest + not_selected_quest

        discovery_entries = sorted(
            self._classified[MemoryType.DISCOVERY],
            key=lambda e: self._recency_score(e, current_turn),
            reverse=True,
        )
        discovery_text, refreshed_disc = self._truncate_to_budget(discovery_entries, self._budget.discovery, current_turn)
        not_selected_disc = discovery_entries[len(refreshed_disc):]
        self._classified[MemoryType.DISCOVERY] = refreshed_disc + not_selected_disc

        extra_events_parts = [p for p in (quest_text, discovery_text) if p]
        if extra_events_parts:
            extra = "\n".join(extra_events_parts)
            recent_events = f"{recent_events}\n{extra}" if recent_events else extra

        rel_entries = sorted(
            self._classified[MemoryType.RELATIONSHIP],
            key=lambda e: self._recency_score(e, current_turn),
            reverse=True,
        )
        rel_text, refreshed_rel = self._truncate_to_budget(rel_entries, self._budget.relationship, current_turn)
        not_selected_rel = rel_entries[len(refreshed_rel):]
        self._classified[MemoryType.RELATIONSHIP] = refreshed_rel + not_selected_rel
        if rel_text:
            relationship_summary = (
                f"{relationship_summary}\n{rel_text}" if relationship_summary else rel_text
            )

        return MemoryContext(
            recent_events=recent_events,
            relationship_summary=relationship_summary,
            active_skills_text=active_skills_text,
        )

    def get_player_relationships(self, player_id: str = "player") -> list[Relationship]:
        return self._relationship_graph.get_all_for(player_id)

    def classified_to_snapshot(self) -> dict:
        result: dict[str, list[dict]] = {}
        for mt, entries in self._classified.items():
            if entries:
                result[mt.value] = [
                    {
                        "id": e.id,
                        "content": e.content,
                        "importance": e.importance,
                        "created_turn": e.created_turn,
                        "last_relevant_turn": e.last_relevant_turn,
                    }
                    for e in entries
                ]
        return result

    @staticmethod
    def _entries_from_snapshot(snapshot: dict) -> dict[MemoryType, list[MemoryEntry]]:
        classified: dict[MemoryType, list[MemoryEntry]] = {mt: [] for mt in MemoryType}
        type_map = {mt.value: mt for mt in MemoryType}
        for type_key, entry_dicts in snapshot.items():
            mt = type_map.get(type_key)
            if mt is None:
                continue
            for d in entry_dicts:
                classified[mt].append(MemoryEntry(
                    id=d["id"],
                    memory_type=mt,
                    content=d["content"],
                    importance=d["importance"],
                    created_turn=d["created_turn"],
                    last_relevant_turn=d["last_relevant_turn"],
                ))
        return classified

    def sync_to_state(self, state: WorldState) -> WorldState:
        rel_snapshot = self._relationship_graph.to_snapshot()
        cls_snapshot = self.classified_to_snapshot()
        return state.model_copy(update={
            "relationships_snapshot": rel_snapshot,
            "classified_memories_snapshot": cls_snapshot,
        })

    def rebuild(self, state: WorldState) -> None:
        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("ClassifiedMemorySystem.rebuild: failed to restore RelationshipGraph")
            self._relationship_graph = RelationshipGraph()
        cls_snap = dict(state.classified_memories_snapshot) if state.classified_memories_snapshot else {}
        if cls_snap:
            self._classified = self._entries_from_snapshot(cls_snap)
        else:
            self._classified = {mt: [] for mt in MemoryType}


MemorySystem = ClassifiedMemorySystem
