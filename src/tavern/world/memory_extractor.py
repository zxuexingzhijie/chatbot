from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from tavern.world.memory import MemoryEntry, MemoryType

if TYPE_CHECKING:
    from tavern.world.models import Event


@dataclass(frozen=True)
class MemoryExtractionRule:
    event_type_pattern: str
    memory_type: MemoryType
    importance_fn: Callable[[Event], int]
    content_fn: Callable[[Event], str]


class MemoryExtractor:
    def __init__(self, rules: list[MemoryExtractionRule]) -> None:
        self._rules: list[tuple[re.Pattern, MemoryExtractionRule]] = [
            (re.compile(r.event_type_pattern), r) for r in rules
        ]

    def extract(self, event: Event, turn: int) -> MemoryEntry | None:
        for pattern, rule in self._rules:
            if pattern.match(event.type):
                return MemoryEntry(
                    id=f"mem_{event.id}",
                    memory_type=rule.memory_type,
                    content=rule.content_fn(event),
                    importance=rule.importance_fn(event),
                    created_turn=turn,
                    last_relevant_turn=turn,
                )
        return None


def _dialogue_importance(e: Event) -> int:
    data = getattr(e, "data", None) or {}
    return 8 if data.get("has_secret") else 4


def _dialogue_content(e: Event) -> str:
    data = getattr(e, "data", None) or {}
    return data.get("summary_text", e.description)


def _quest_content(e: Event) -> str:
    data = getattr(e, "data", None) or {}
    return f"任务 {data.get('quest_id', 'unknown')}: {data.get('status', 'unknown')}"


def _relationship_importance(e: Event) -> int:
    data = getattr(e, "data", None) or {}
    return 6 if abs(data.get("delta", 0)) >= 10 else 3


def _relationship_content(e: Event) -> str:
    data = getattr(e, "data", None) or {}
    return f"{data.get('npc_name', 'unknown')} 信任度 {data.get('delta', 0):+d}"


def _discovery_content(e: Event) -> str:
    data = getattr(e, "data", None) or {}
    return data.get("description", e.description)


EXTRACTION_RULES: list[MemoryExtractionRule] = [
    MemoryExtractionRule(
        event_type_pattern=r"dialogue_summary_.*",
        memory_type=MemoryType.LORE,
        importance_fn=_dialogue_importance,
        content_fn=_dialogue_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"quest_.*",
        memory_type=MemoryType.QUEST,
        importance_fn=lambda e: 7,
        content_fn=_quest_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"relationship_changed",
        memory_type=MemoryType.RELATIONSHIP,
        importance_fn=_relationship_importance,
        content_fn=_relationship_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"search|look_detail",
        memory_type=MemoryType.DISCOVERY,
        importance_fn=lambda e: 2,
        content_fn=_discovery_content,
    ),
]
