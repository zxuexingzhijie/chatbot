from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


def _make_app():
    from tavern.cli.app import GameApp
    app = GameApp.__new__(GameApp)
    # Minimal state mock
    state = MagicMock()
    state.turn = 1
    state.player_id = "player"
    state.characters = {"player": MagicMock(location_id="tavern", inventory=())}
    state.quests = {}
    state.story_active_since = {}

    mgr = MagicMock()
    mgr.current = state
    mgr.commit = MagicMock(return_value=state)

    app._state_manager = mgr
    app._memory = MagicMock()
    app._memory._timeline = MagicMock()
    app._memory._relationship_graph = MagicMock()
    app._memory.build_context = MagicMock(return_value=MagicMock(
        recent_events="", relationship_summary="", active_skills_text=""
    ))
    app._renderer = MagicMock()
    app._renderer.render_stream = AsyncMock()
    app._narrator = MagicMock()
    app._narrator.stream_narrative = MagicMock(return_value=AsyncMock())
    app._rules = MagicMock()
    app._parser = MagicMock()
    app._dialogue_manager = MagicMock()
    app._dialogue_manager.is_active = False
    app._dialogue_ctx = None
    app._save_manager = MagicMock()
    app._show_intent = False
    app._pending_story_hints = []
    app._ending_triggered = None
    app._game_over = False
    app._story_engine = MagicMock()
    app._story_engine.check = MagicMock(return_value=[])
    app._story_engine.check_fail_forward = MagicMock(return_value=[])
    app._story_engine.get_active_nodes = MagicMock(return_value=set())
    return app, state


def test_passive_check_after_action():
    app, state = _make_app()
    from tavern.engine.actions import ActionType
    from tavern.world.models import ActionResult
    from tavern.world.state import StateDiff

    result = ActionResult(success=True, action=ActionType.MOVE, message="移动成功", target="cellar")
    diff = StateDiff()
    app._rules.validate = MagicMock(return_value=(result, diff))
    app._parser.parse = AsyncMock(return_value=MagicMock(action=ActionType.MOVE))
    app._state_manager.commit = MagicMock(return_value=state)

    asyncio.run(app._handle_free_input("go cellar"))

    app._story_engine.check.assert_called_once()
    call_args = app._story_engine.check.call_args
    assert call_args[0][1] == "passive"


def test_continue_command_triggers_story():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    fake_result = StoryResult(
        node_id="n1",
        diff=StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0),
        narrator_hint=None,
    )
    app._story_engine.check = MagicMock(return_value=[fake_result])

    asyncio.run(app._handle_system_command("continue"))

    app._story_engine.check.assert_called_once()
    call_args = app._story_engine.check.call_args
    assert call_args[0][1] == "continue"


def test_continue_no_results_prints_message():
    app, state = _make_app()
    app._story_engine.check = MagicMock(return_value=[])
    asyncio.run(app._handle_system_command("continue"))
    app._renderer.console.print.assert_called()
    printed = app._renderer.console.print.call_args[0][0]
    assert "没有新的剧情" in printed


def test_apply_story_results_commits_diff():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint=None)]
    asyncio.run(app._apply_story_results(results))
    app._state_manager.commit.assert_called_once()
    committed_diff = app._state_manager.commit.call_args[0][0]
    assert committed_diff.quest_updates["n1"]["_story_status"] == "completed"


def test_active_since_updated_after_apply():
    app, state = _make_app()
    # Two active nodes, only "n1" already in story_active_since
    app._story_engine.get_active_nodes = MagicMock(return_value={"n1", "n2"})
    state.story_active_since = {"n1": 0}
    state.turn = 3

    app._update_story_active_since()

    # commit should be called with story_active_since_updates = {"n2": 3}
    app._state_manager.commit.assert_called_once()
    committed_diff = app._state_manager.commit.call_args[0][0]
    assert "n2" in committed_diff.story_active_since_updates
    assert "n1" not in committed_diff.story_active_since_updates


def test_apply_story_results_accumulates_narrator_hint():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint="spooky hint")]
    asyncio.run(app._apply_story_results(results))
    assert app._pending_story_hints == ["spooky hint"]


def test_apply_story_results_calls_memory_apply_diff():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint=None)]
    asyncio.run(app._apply_story_results(results))
    app._memory.apply_diff.assert_called_once_with(diff, app.state)


def test_pending_story_hints_cleared_after_handle_free_input():
    app, state = _make_app()
    from tavern.engine.actions import ActionType
    from tavern.world.models import ActionResult
    from tavern.world.state import StateDiff

    # Pre-populate hints (simulates a previous turn that didn't clear)
    app._pending_story_hints = ["leftover hint"]

    result = ActionResult(success=False, action=ActionType.MOVE, message="失败")
    diff = None
    app._rules.validate = MagicMock(return_value=(result, diff))
    app._parser.parse = AsyncMock(return_value=MagicMock(action=ActionType.MOVE))

    asyncio.run(app._handle_free_input("go nowhere"))

    assert app._pending_story_hints == []


def test_apply_story_results_detects_ending():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(
        new_endings=("good_ending",),
        quest_updates={"ending_good": {"_story_status": "completed"}},
        turn_increment=0,
    )
    results = [StoryResult(node_id="ending_good", diff=diff, narrator_hint="温暖收束")]
    asyncio.run(app._apply_story_results(results))
    assert app._ending_triggered is not None
    assert app._ending_triggered == ("good_ending", "温暖收束")


def test_apply_story_results_no_ending():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint="some hint")]
    asyncio.run(app._apply_story_results(results))
    assert app._ending_triggered is None


def test_game_over_flag_set_after_ending():
    app, state = _make_app()
    from tavern.engine.actions import ActionType
    from tavern.engine.story import StoryResult
    from tavern.world.models import ActionResult
    from tavern.world.state import StateDiff

    result = ActionResult(success=True, action=ActionType.MOVE, message="移动成功", target="cellar")
    diff = StateDiff()
    app._rules.validate = MagicMock(return_value=(result, diff))
    app._parser.parse = AsyncMock(return_value=MagicMock(action=ActionType.MOVE))
    app._state_manager.commit = MagicMock(return_value=state)

    ending_diff = StateDiff(
        new_endings=("good_ending",),
        quest_updates={"ending_good": {"_story_status": "completed"}},
        turn_increment=0,
    )
    ending_result = StoryResult(node_id="ending_good", diff=ending_diff, narrator_hint="温暖收束")
    app._story_engine.check = MagicMock(return_value=[ending_result])

    asyncio.run(app._handle_free_input("go cellar"))
    assert app._game_over is True


def test_app_import_registers_anthropic_provider():
    """Importing tavern.cli.app registers both openai and anthropic providers."""
    from tavern.llm.adapter import LLMRegistry
    import tavern.cli.app  # noqa: F401 — triggers registration side-effects
    assert "openai" in LLMRegistry._providers
    assert "anthropic" in LLMRegistry._providers
