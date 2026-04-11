from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tavern.engine.quest_descriptions import (
    get_quest_display_name,
    get_quest_status_description,
    should_notify,
)
from tavern.engine.effects import _render_quest_notifications
from tavern.engine.modes.exploring import (
    _find_expiring_quests,
    _render_expiry_warnings,
    _render_onboarding_hint,
    _ONBOARDING_HINTS,
)
from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import StateDiff, WorldState


def _make_state(turn: int = 0, quests: dict | None = None) -> WorldState:
    player = Character(
        id="player", name="Hero", role=CharacterRole.PLAYER, location_id="tavern",
    )
    location = Location(
        id="tavern", name="Tavern", description="A cozy tavern.",
        npcs=(), items=(), exits={}, atmosphere="warm",
    )
    return WorldState(
        turn=turn, player_id="player",
        characters={"player": player},
        locations={"tavern": location},
        quests=quests or {},
    )


class TestQuestDescriptions:
    def test_get_known_quest_name(self):
        assert get_quest_display_name("traveler_quest") == "寻找护身符"

    def test_get_unknown_quest_name_falls_back(self):
        assert get_quest_display_name("unknown_quest") == "unknown_quest"

    def test_get_status_description(self):
        desc = get_quest_status_description("traveler_quest", "active")
        assert "护身符" in desc

    def test_get_missing_status_returns_empty(self):
        assert get_quest_status_description("traveler_quest", "xyz") == ""

    def test_should_notify_active(self):
        assert should_notify("traveler_quest", "active") is True

    def test_should_notify_completed(self):
        assert should_notify("traveler_quest", "completed") is True

    def test_should_not_notify_internal(self):
        assert should_notify("some_node", "_story_status") is False

    def test_should_notify_known_custom_status(self):
        assert should_notify("traveler_quest", "amulet_found") is True


class TestRenderQuestNotifications:
    def test_renders_on_status_change(self):
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        old_state = _make_state(quests={})
        diff = StateDiff(quest_updates={"traveler_quest": {"status": "active"}}, turn_increment=0)
        _render_quest_notifications(diff, old_state, ctx)
        renderer.render_quest_notification.assert_called_once()
        args = renderer.render_quest_notification.call_args[0]
        assert args[0] == "寻找护身符"
        assert args[1] == "active"

    def test_skips_when_status_unchanged(self):
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        old_state = _make_state(quests={"traveler_quest": {"status": "active"}})
        diff = StateDiff(quest_updates={"traveler_quest": {"status": "active"}}, turn_increment=0)
        _render_quest_notifications(diff, old_state, ctx)
        renderer.render_quest_notification.assert_not_called()

    def test_skips_internal_story_status(self):
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        old_state = _make_state(quests={})
        diff = StateDiff(quest_updates={"node1": {"_story_status": "completed"}}, turn_increment=0)
        _render_quest_notifications(diff, old_state, ctx)
        renderer.render_quest_notification.assert_not_called()


class TestFindExpiringQuests:
    def test_warns_within_window(self):
        state = _make_state(turn=18, quests={
            "q1": {"status": "active", "activated_at": 2},
        })
        result = _find_expiring_quests(state)
        assert len(result) == 1
        assert result[0] == ("q1", 4)

    def test_no_warn_outside_window(self):
        state = _make_state(turn=10, quests={
            "q1": {"status": "active", "activated_at": 2},
        })
        assert _find_expiring_quests(state) == []

    def test_no_warn_at_zero_remaining(self):
        state = _make_state(turn=22, quests={
            "q1": {"status": "active", "activated_at": 2},
        })
        assert _find_expiring_quests(state) == []

    def test_render_expiry_warnings_calls_renderer(self):
        state = _make_state(turn=17, quests={
            "traveler_quest": {"status": "active", "activated_at": 1},
        })
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        _render_expiry_warnings(state, ctx)
        renderer.render_quest_expiry_warning.assert_called_once()
        args = renderer.render_quest_expiry_warning.call_args[0]
        assert args[0] == "寻找护身符"
        assert args[1] == 4


class TestOnboardingHint:
    def test_hint_on_turn_1(self):
        state = _make_state(turn=1)
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        _render_onboarding_hint(state, ctx)
        renderer.render_onboarding_hint.assert_called_once()
        assert "聊天" in renderer.render_onboarding_hint.call_args[0][0]

    def test_hint_on_turn_2(self):
        state = _make_state(turn=2)
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        _render_onboarding_hint(state, ctx)
        renderer.render_onboarding_hint.assert_called_once()
        assert "/status" in renderer.render_onboarding_hint.call_args[0][0]

    def test_no_hint_on_turn_3(self):
        state = _make_state(turn=3)
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        _render_onboarding_hint(state, ctx)
        renderer.render_onboarding_hint.assert_not_called()

    def test_no_hint_on_turn_0(self):
        state = _make_state(turn=0)
        renderer = MagicMock()
        ctx = MagicMock()
        ctx.renderer = renderer
        _render_onboarding_hint(state, ctx)
        renderer.render_onboarding_hint.assert_not_called()
