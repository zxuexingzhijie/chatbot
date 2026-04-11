from __future__ import annotations

import pytest

from tavern.world.memory import MemoryEntry, MemoryType
from tavern.world.memory_extractor import (
    EXTRACTION_RULES,
    MemoryExtractionRule,
    MemoryExtractor,
)
from tavern.world.models import Event


def _make_event(
    *,
    id: str = "e1",
    turn: int = 1,
    type: str = "unknown",
    actor: str = "player",
    description: str = "something happened",
) -> Event:
    return Event(
        id=id,
        turn=turn,
        type=type,
        actor=actor,
        description=description,
    )


@pytest.fixture()
def extractor() -> MemoryExtractor:
    return MemoryExtractor(EXTRACTION_RULES)


class TestDialogueSummary:
    def test_has_secret_importance_8(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="dialogue_summary_innkeeper")
        object.__setattr__(event, "data", {"has_secret": True, "summary_text": "秘密对话"})
        result = extractor.extract(event, turn=5)
        assert result is not None
        assert result.memory_type is MemoryType.LORE
        assert result.importance == 8
        assert result.content == "秘密对话"

    def test_no_secret_importance_4(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="dialogue_summary_merchant")
        result = extractor.extract(event, turn=3)
        assert result is not None
        assert result.memory_type is MemoryType.LORE
        assert result.importance == 4
        assert result.content == "something happened"


class TestQuest:
    def test_quest_event(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="quest_started", id="q1")
        object.__setattr__(event, "data", {"quest_id": "find_gem", "status": "active"})
        result = extractor.extract(event, turn=2)
        assert result is not None
        assert result.memory_type is MemoryType.QUEST
        assert result.importance == 7
        assert result.content == "任务 find_gem: active"
        assert result.id == "mem_q1"


class TestRelationship:
    def test_big_delta_importance_6(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="relationship_changed")
        object.__setattr__(event, "data", {"npc_name": "老王", "delta": 15})
        result = extractor.extract(event, turn=4)
        assert result is not None
        assert result.memory_type is MemoryType.RELATIONSHIP
        assert result.importance == 6
        assert result.content == "老王 信任度 +15"

    def test_small_delta_importance_3(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="relationship_changed")
        object.__setattr__(event, "data", {"npc_name": "小李", "delta": 3})
        result = extractor.extract(event, turn=4)
        assert result is not None
        assert result.importance == 3
        assert result.content == "小李 信任度 +3"


class TestDiscovery:
    def test_search_event(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="search", description="发现了一个隐藏的通道")
        result = extractor.extract(event, turn=6)
        assert result is not None
        assert result.memory_type is MemoryType.DISCOVERY
        assert result.importance == 2
        assert result.content == "发现了一个隐藏的通道"

    def test_look_detail_event(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="look_detail", description="仔细观察了墙壁")
        result = extractor.extract(event, turn=7)
        assert result is not None
        assert result.memory_type is MemoryType.DISCOVERY
        assert result.importance == 2


class TestNoMatch:
    def test_unknown_event_returns_none(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="combat_started")
        result = extractor.extract(event, turn=1)
        assert result is None

    def test_empty_rules_returns_none(self) -> None:
        extractor = MemoryExtractor([])
        event = _make_event(type="dialogue_summary_npc")
        result = extractor.extract(event, turn=1)
        assert result is None


class TestMemoryEntryFields:
    def test_id_and_turn_fields(self, extractor: MemoryExtractor) -> None:
        event = _make_event(type="quest_completed", id="ev99")
        result = extractor.extract(event, turn=42)
        assert result is not None
        assert result.id == "mem_ev99"
        assert result.created_turn == 42
        assert result.last_relevant_turn == 42
