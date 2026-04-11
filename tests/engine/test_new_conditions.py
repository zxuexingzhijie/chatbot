from __future__ import annotations

import pytest

from tavern.engine.story_conditions import (
    eval_all_npc_trust_below,
    eval_quest_none_active,
    eval_visited_locations_count,
)
from tavern.world.models import Character, CharacterRole, Event, Location
from tavern.world.skills import ActivationCondition
from tavern.world.state import WorldState


def _make_state(
    turn: int = 0,
    quests: dict | None = None,
    characters: dict | None = None,
    locations: dict | None = None,
    timeline: tuple = (),
) -> WorldState:
    player = Character(
        id="player", name="Hero", role=CharacterRole.PLAYER, location_id="tavern",
    )
    default_chars = {"player": player}
    if characters:
        default_chars.update(characters)
    location = Location(
        id="tavern", name="Tavern", description="A cozy tavern.",
        npcs=(), items=(), exits={}, atmosphere="warm",
    )
    default_locs = {"tavern": location}
    if locations:
        default_locs.update(locations)
    return WorldState(
        turn=turn,
        player_id="player",
        characters=default_chars,
        locations=default_locs,
        quests=quests or {},
        timeline=timeline,
    )


class TestQuestNoneActive:
    def test_no_quests_returns_true(self):
        state = _make_state()
        cond = ActivationCondition(type="quest_none_active")
        assert eval_quest_none_active(cond, state, (), {}) is True

    def test_all_completed_returns_true(self):
        state = _make_state(quests={
            "q1": {"status": "completed"},
            "q2": {"status": "abandoned"},
        })
        cond = ActivationCondition(type="quest_none_active")
        assert eval_quest_none_active(cond, state, (), {}) is True

    def test_one_active_returns_false(self):
        state = _make_state(quests={
            "q1": {"status": "completed"},
            "q2": {"status": "active"},
        })
        cond = ActivationCondition(type="quest_none_active")
        assert eval_quest_none_active(cond, state, (), {}) is False

    def test_discovered_not_active(self):
        state = _make_state(quests={
            "q1": {"status": "discovered"},
        })
        cond = ActivationCondition(type="quest_none_active")
        assert eval_quest_none_active(cond, state, (), {}) is True


class TestAllNpcTrustBelow:
    def test_no_npcs_returns_true(self):
        state = _make_state()
        cond = ActivationCondition(type="all_npc_trust_below", value=15)
        assert eval_all_npc_trust_below(cond, state, (), {}) is True

    def test_all_below_returns_true(self):
        npc1 = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats={"trust": 10},
        )
        npc2 = Character(
            id="traveler", name="Traveler", role=CharacterRole.NPC,
            location_id="tavern", stats={"trust": 5},
        )
        state = _make_state(characters={"grim": npc1, "traveler": npc2})
        cond = ActivationCondition(type="all_npc_trust_below", value=15)
        assert eval_all_npc_trust_below(cond, state, (), {}) is True

    def test_one_at_threshold_returns_false(self):
        npc1 = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats={"trust": 15},
        )
        state = _make_state(characters={"grim": npc1})
        cond = ActivationCondition(type="all_npc_trust_below", value=15)
        assert eval_all_npc_trust_below(cond, state, (), {}) is False

    def test_one_above_returns_false(self):
        npc1 = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats={"trust": 20},
        )
        state = _make_state(characters={"grim": npc1})
        cond = ActivationCondition(type="all_npc_trust_below", value=15)
        assert eval_all_npc_trust_below(cond, state, (), {}) is False

    def test_missing_value_returns_false(self):
        state = _make_state()
        cond = ActivationCondition(type="all_npc_trust_below")
        assert eval_all_npc_trust_below(cond, state, (), {}) is False

    def test_npc_without_trust_stat_defaults_zero(self):
        npc1 = Character(
            id="grim", name="Grim", role=CharacterRole.NPC,
            location_id="tavern", stats={},
        )
        state = _make_state(characters={"grim": npc1})
        cond = ActivationCondition(type="all_npc_trust_below", value=15)
        assert eval_all_npc_trust_below(cond, state, (), {}) is True


class TestVisitedLocationsCount:
    def test_current_location_counts(self):
        state = _make_state(turn=5)
        cond = ActivationCondition(type="visited_locations_count", operator=">=", value=1)
        assert eval_visited_locations_count(cond, state, (), {}) is True

    def test_missing_operator_returns_false(self):
        state = _make_state()
        cond = ActivationCondition(type="visited_locations_count", value=1)
        assert eval_visited_locations_count(cond, state, (), {}) is False

    def test_missing_value_returns_false(self):
        state = _make_state()
        cond = ActivationCondition(type="visited_locations_count", operator=">=")
        assert eval_visited_locations_count(cond, state, (), {}) is False
