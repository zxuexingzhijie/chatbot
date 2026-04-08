from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from tavern.world.skills import ActivationCondition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    turn=1,
    player_location="tavern",
    quests=None,
    story_active_since=None,
):
    state = MagicMock()
    state.turn = turn
    state.player_id = "player"
    state.characters = {
        "player": MagicMock(location_id=player_location, inventory=())
    }
    state.quests = quests or {}
    state.story_active_since = story_active_since or {}
    return state


def _make_node(
    node_id="n1",
    act="act1",
    requires=(),
    repeatable=False,
    trigger_mode="passive",
    conditions=(),
    quest_updates=None,
    new_events=(),
    narrator_hint=None,
    fail_forward=None,
):
    from tavern.engine.story import (
        StoryEffects, StoryNode, NewEventSpec, FailForward, HintEvent
    )
    effects = StoryEffects(
        quest_updates=quest_updates or {},
        new_events=tuple(new_events),
    )
    return StoryNode(
        id=node_id,
        act=act,
        requires=tuple(requires),
        repeatable=repeatable,
        trigger_mode=trigger_mode,
        conditions=tuple(conditions),
        effects=effects,
        narrator_hint=narrator_hint,
        fail_forward=fail_forward,
    )


def _make_engine(nodes):
    from tavern.engine.story import StoryEngine
    return StoryEngine({n.id: n for n in nodes})


# ---------------------------------------------------------------------------
# get_active_nodes
# ---------------------------------------------------------------------------

def test_get_active_nodes_no_requires():
    node = _make_node("n1", requires=())
    engine = _make_engine([node])
    state = _make_state(quests={})
    assert "n1" in engine.get_active_nodes(state)


def test_get_active_nodes_requires_not_met():
    node = _make_node("n2", requires=("n1",))
    engine = _make_engine([node])
    state = _make_state(quests={})
    assert "n2" not in engine.get_active_nodes(state)


def test_get_active_nodes_requires_met():
    node = _make_node("n2", requires=("n1",))
    engine = _make_engine([node])
    state = _make_state(quests={"n1": {"_story_status": "completed"}})
    assert "n2" in engine.get_active_nodes(state)


def test_get_active_nodes_repeatable_stays():
    node = _make_node("n1", requires=(), repeatable=True)
    engine = _make_engine([node])
    # completed but repeatable → stays active
    state = _make_state(quests={"n1": {"_story_status": "completed"}})
    assert "n1" in engine.get_active_nodes(state)


def test_get_active_nodes_non_repeatable_removed():
    node = _make_node("n1", requires=(), repeatable=False)
    engine = _make_engine([node])
    state = _make_state(quests={"n1": {"_story_status": "completed"}})
    assert "n1" not in engine.get_active_nodes(state)


# ---------------------------------------------------------------------------
# check — trigger mode filtering
# ---------------------------------------------------------------------------

def test_check_passive_triggers():
    node = _make_node("n1", trigger_mode="passive", conditions=())
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    assert len(results) == 1
    assert results[0].node_id == "n1"


def test_check_continue_not_triggered_by_passive():
    node = _make_node("n1", trigger_mode="continue", conditions=())
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    assert results == []


def test_check_both_triggers_in_either_mode():
    node = _make_node("n1", trigger_mode="both", conditions=())
    engine = _make_engine([node])
    state = _make_state()
    results_p = engine.check(state, "passive", MagicMock(), MagicMock())
    results_c = engine.check(state, "continue", MagicMock(), MagicMock())
    assert len(results_p) == 1
    assert len(results_c) == 1


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------

def test_build_result_marks_completed():
    node = _make_node("n1", quest_updates={"cellar": {"status": "found"}})
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    assert results[0].diff.quest_updates["n1"]["_story_status"] == "completed"


def test_build_result_effects_applied():
    from tavern.engine.story import NewEventSpec
    ev = NewEventSpec(id="ev1", type="story", description="desc")
    node = _make_node(
        "n1",
        quest_updates={"q1": {"status": "done"}},
        new_events=[ev],
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.quest_updates["q1"]["status"] == "done"
    assert len(diff.new_events) == 1
    assert diff.new_events[0].id == "ev1"


# ---------------------------------------------------------------------------
# fail_forward
# ---------------------------------------------------------------------------

def test_fail_forward_no_trigger_before_timeout():
    from tavern.engine.story import FailForward, HintEvent
    ff = FailForward(after_turns=8, hint_event=HintEvent(description="hint", actor="npc"))
    node = _make_node("n1", fail_forward=ff)
    engine = _make_engine([node])
    # active since turn 0, current turn 5 → not yet 8
    state = _make_state(turn=5, story_active_since={"n1": 0})
    results = engine.check_fail_forward(state)
    assert results == []


def test_fail_forward_triggers_after_timeout():
    from tavern.engine.story import FailForward, HintEvent
    ff = FailForward(after_turns=8, hint_event=HintEvent(description="npc says hi", actor="npc"))
    node = _make_node("n1", fail_forward=ff)
    engine = _make_engine([node])
    # turn 10, since 0 → diff = 10 >= 8 → triggers
    state = _make_state(turn=10, story_active_since={"n1": 0})
    results = engine.check_fail_forward(state)
    assert len(results) == 1
    assert results[0].node_id == "n1"
    assert len(results[0].diff.new_events) == 1
    assert results[0].diff.new_events[0].type == "hint"


def test_fail_forward_resets_since():
    from tavern.engine.story import FailForward, HintEvent
    ff = FailForward(after_turns=8, hint_event=HintEvent(description="d", actor="a"))
    node = _make_node("n1", fail_forward=ff)
    engine = _make_engine([node])
    state = _make_state(turn=10, story_active_since={"n1": 0})
    results = engine.check_fail_forward(state)
    # story_active_since_updates should reset to current turn
    assert results[0].diff.story_active_since_updates == {"n1": 10}


def test_fail_forward_no_infinite_repeat():
    from tavern.engine.story import FailForward, HintEvent
    ff = FailForward(after_turns=8, hint_event=HintEvent(description="d", actor="a"))
    node = _make_node("n1", fail_forward=ff)
    engine = _make_engine([node])
    # After reset: since=10, turn=12 → diff=2 < 8
    state = _make_state(turn=12, story_active_since={"n1": 10})
    results = engine.check_fail_forward(state)
    assert results == []


def test_empty_nodes_returns_empty():
    from tavern.engine.story import StoryEngine
    engine = StoryEngine({})
    state = _make_state()
    assert engine.check(state, "passive", MagicMock(), MagicMock()) == []
    assert engine.check_fail_forward(state) == []


def test_unknown_condition_type_skips_node(caplog):
    import logging
    cond = ActivationCondition(type="unknown_xyz")
    node = _make_node("n1", conditions=[cond])
    engine = _make_engine([node])
    state = _make_state()
    with caplog.at_level(logging.WARNING):
        results = engine.check(state, "passive", MagicMock(), MagicMock())
    assert results == []
    assert "unknown_xyz" in caplog.text
