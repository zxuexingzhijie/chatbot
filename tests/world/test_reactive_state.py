import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult, Event
from tavern.world.state import ReactiveStateManager, StateDiff, WorldState


def _make_state(**kwargs) -> WorldState:
    defaults = {"turn": 0, "player_id": "player", "locations": {}, "characters": {}}
    defaults.update(kwargs)
    return WorldState(**defaults)


def _make_diff(**kwargs) -> StateDiff:
    return StateDiff(**kwargs)


def _make_result() -> ActionResult:
    return ActionResult(success=True, action=ActionType.LOOK, message="ok")


class TestReactiveStateManagerCommit:
    def test_commit_updates_state(self):
        state = _make_state(turn=0)
        mgr = ReactiveStateManager(state)
        diff = _make_diff(turn_increment=1)
        new_state = mgr.commit(diff, _make_result())
        assert new_state.turn == 1
        assert mgr.state.turn == 1

    def test_commit_increments_version(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.version == 0
        mgr.commit(_make_diff(), _make_result())
        assert mgr.version == 1
        mgr.commit(_make_diff(), _make_result())
        assert mgr.version == 2

    @pytest.mark.asyncio
    async def test_commit_fires_on_change(self):
        on_change = AsyncMock()
        mgr = ReactiveStateManager(_make_state(), on_change=on_change)
        mgr.commit(_make_diff(), _make_result())
        await asyncio.sleep(0)
        on_change.assert_called_once()

    def test_commit_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.subscribe(listener)
        mgr.commit(_make_diff(), _make_result())
        listener.assert_called_once()

    def test_commit_action_param_is_optional(self):
        mgr = ReactiveStateManager(_make_state())
        new_state = mgr.commit(_make_diff())
        assert new_state.last_action is None


class TestReactiveStateManagerUndo:
    def test_undo_returns_previous_state(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(turn_increment=1), _make_result())
        result = mgr.undo()
        assert result is not None
        assert result.turn == 0

    def test_undo_empty_returns_none(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.undo() is None

    def test_undo_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.commit(_make_diff(), _make_result())
        mgr.subscribe(listener)
        mgr.undo()
        listener.assert_called_once()


class TestReactiveStateManagerRedo:
    def test_redo_after_undo(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(turn_increment=1), _make_result())
        mgr.undo()
        result = mgr.redo()
        assert result is not None
        assert result.turn == 1

    def test_redo_empty_returns_none(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.redo() is None

    def test_redo_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.commit(_make_diff(), _make_result())
        mgr.undo()
        mgr.subscribe(listener)
        mgr.redo()
        listener.assert_called_once()


class TestReactiveStateManagerSubscribe:
    def test_subscribe_returns_unsubscribe(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        unsub = mgr.subscribe(listener)
        mgr.commit(_make_diff(), _make_result())
        assert listener.call_count == 1
        unsub()
        mgr.commit(_make_diff(), _make_result())
        assert listener.call_count == 1

    def test_listener_removal_during_iteration_safe(self):
        mgr = ReactiveStateManager(_make_state())
        calls = []

        def self_removing_listener():
            calls.append("called")
            unsub()

        unsub = mgr.subscribe(self_removing_listener)
        other = MagicMock()
        mgr.subscribe(other)
        mgr.commit(_make_diff(), _make_result())
        assert calls == ["called"]
        other.assert_called_once()


class TestReactiveStateManagerReplace:
    def test_replace_sets_new_state(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(turn_increment=1), _make_result())
        new = _make_state(turn=99)
        mgr.replace(new)
        assert mgr.state.turn == 99

    def test_replace_clears_history(self):
        mgr = ReactiveStateManager(_make_state(turn=0))
        mgr.commit(_make_diff(), _make_result())
        mgr.replace(_make_state(turn=99))
        assert mgr.undo() is None

    def test_replace_increments_version(self):
        mgr = ReactiveStateManager(_make_state())
        v_before = mgr.version
        mgr.replace(_make_state(turn=99))
        assert mgr.version == v_before + 1

    def test_replace_notifies_listeners(self):
        listener = MagicMock()
        mgr = ReactiveStateManager(_make_state())
        mgr.subscribe(listener)
        mgr.replace(_make_state(turn=99))
        listener.assert_called_once()


class TestReactiveStateManagerVersion:
    def test_version_tracks_through_undo_redo(self):
        mgr = ReactiveStateManager(_make_state())
        assert mgr.version == 0
        mgr.commit(_make_diff(), _make_result())
        assert mgr.version == 1
        mgr.undo()
        assert mgr.version == 0
        mgr.redo()
        assert mgr.version == 1

    def test_state_property_aliases_current(self):
        mgr = ReactiveStateManager(_make_state(turn=5))
        assert mgr.state is mgr.current
