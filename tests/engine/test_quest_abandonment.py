from __future__ import annotations

import pytest

from tavern.engine.modes.exploring import _find_abandoned_quests
from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState


def _make_state(turn: int = 0, quests: dict | None = None, **kwargs) -> WorldState:
    player = Character(
        id="player", name="Hero", role=CharacterRole.PLAYER, location_id="tavern",
    )
    location = Location(
        id="tavern", name="Tavern", description="A cozy tavern.",
        npcs=(), items=(), exits={}, atmosphere="warm",
    )
    return WorldState(
        turn=turn,
        player_id="player",
        characters={"player": player},
        locations={"tavern": location},
        quests=quests or {},
        **kwargs,
    )


class TestFindAbandonedQuests:
    def test_no_quests_returns_empty(self):
        state = _make_state(turn=50)
        assert _find_abandoned_quests(state) == {}

    def test_active_quest_within_threshold_not_abandoned(self):
        state = _make_state(turn=15, quests={
            "q1": {"status": "active", "activated_at": 5},
        })
        assert _find_abandoned_quests(state, threshold=20) == {}

    def test_active_quest_at_threshold_is_abandoned(self):
        state = _make_state(turn=25, quests={
            "q1": {"status": "active", "activated_at": 5},
        })
        result = _find_abandoned_quests(state, threshold=20)
        assert result == {"q1": {"status": "abandoned"}}

    def test_active_quest_past_threshold_is_abandoned(self):
        state = _make_state(turn=50, quests={
            "q1": {"status": "active", "activated_at": 10},
        })
        result = _find_abandoned_quests(state, threshold=20)
        assert result == {"q1": {"status": "abandoned"}}

    def test_completed_quest_not_abandoned(self):
        state = _make_state(turn=50, quests={
            "q1": {"status": "completed", "activated_at": 5},
        })
        assert _find_abandoned_quests(state, threshold=20) == {}

    def test_discovered_quest_not_abandoned(self):
        state = _make_state(turn=50, quests={
            "q1": {"status": "discovered", "activated_at": 5},
        })
        assert _find_abandoned_quests(state, threshold=20) == {}

    def test_active_quest_without_activated_at_not_abandoned(self):
        state = _make_state(turn=50, quests={
            "q1": {"status": "active"},
        })
        assert _find_abandoned_quests(state, threshold=20) == {}

    def test_multiple_quests_mixed(self):
        state = _make_state(turn=30, quests={
            "q1": {"status": "active", "activated_at": 5},
            "q2": {"status": "active", "activated_at": 25},
            "q3": {"status": "completed", "activated_at": 1},
        })
        result = _find_abandoned_quests(state, threshold=20)
        assert result == {"q1": {"status": "abandoned"}}

    def test_custom_threshold(self):
        state = _make_state(turn=15, quests={
            "q1": {"status": "active", "activated_at": 5},
        })
        result = _find_abandoned_quests(state, threshold=10)
        assert result == {"q1": {"status": "abandoned"}}
