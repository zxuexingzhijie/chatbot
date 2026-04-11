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
