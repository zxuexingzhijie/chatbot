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


def test_check_condition_false_node_not_triggered():
    from tavern.engine.story_conditions import CONDITION_REGISTRY, register_condition
    from tavern.world.skills import ActivationCondition

    @register_condition("always_false_test")
    def always_false(cond, state, timeline, relationships):
        return False

    cond = ActivationCondition(type="always_false_test")
    node = _make_node("n1", conditions=[cond])
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    assert results == []

    CONDITION_REGISTRY.pop("always_false_test", None)


def test_fail_forward_skips_node_without_fail_forward():
    node = _make_node("n1", fail_forward=None)
    engine = _make_engine([node])
    state = _make_state(turn=100, story_active_since={"n1": 0})
    results = engine.check_fail_forward(state)
    assert results == []


# ---------------------------------------------------------------------------
# load_story_nodes
# ---------------------------------------------------------------------------

def test_load_story_nodes_parses_valid_yaml(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: test_node
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: location
          event_id: cellar
    effects:
      quest_updates:
        cellar_mystery: { status: discovered }
      new_events:
        - id: entered
          type: story
          description: "entered cellar"
    narrator_hint: "spooky"
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "test_node" in nodes
    node = nodes["test_node"]
    assert node.act == "act1"
    assert node.trigger_mode == "passive"
    assert len(node.conditions) == 1
    assert node.conditions[0].event_id == "cellar"
    assert node.effects.quest_updates["cellar_mystery"]["status"] == "discovered"
    assert len(node.effects.new_events) == 1
    assert node.narrator_hint == "spooky"


def test_load_story_nodes_skips_malformed_node(tmp_path, caplog):
    import logging
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: good_node
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates: {}
      new_events: []
  - this_is_not_a_mapping: 123
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        nodes = load_story_nodes(path)
    assert "good_node" in nodes
    assert len(nodes) == 1


def test_load_story_nodes_with_fail_forward(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: ff_node
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    fail_forward:
      after_turns: 5
      hint_event:
        description: "hint text"
        actor: npc1
    effects:
      quest_updates: {}
      new_events: []
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "ff_node" in nodes
    ff = nodes["ff_node"].fail_forward
    assert ff is not None
    assert ff.after_turns == 5
    assert ff.hint_event.actor == "npc1"


# ---------------------------------------------------------------------------
# Extended effects: add_items, remove_items, character_stat_deltas
# ---------------------------------------------------------------------------

def test_build_result_add_items_to_inventory():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement, NewEventSpec
    effects = StoryEffects(
        quest_updates={"q1": {"status": "done"}},
        new_events=(),
        add_items=(ItemPlacement(item_id="map_fragment", to="inventory"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert "player" in diff.updated_characters
    inv = diff.updated_characters["player"]["inventory"]
    assert "map_fragment" in inv


def test_build_result_add_items_to_location():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        add_items=(ItemPlacement(item_id="lost_amulet", to="backyard"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    backyard = MagicMock()
    backyard.items = ()
    state.locations = {"tavern": MagicMock(items=()), "backyard": backyard}
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert "backyard" in diff.updated_locations
    assert "lost_amulet" in diff.updated_locations["backyard"]["items"]


def test_build_result_remove_items_from_inventory():
    from tavern.engine.story import StoryEffects, StoryNode, ItemRemoval
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        remove_items=(ItemRemoval(item_id="lost_amulet", from_="inventory"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    state.characters["player"].inventory = ("lost_amulet", "old_notice")
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    inv = diff.updated_characters["player"]["inventory"]
    assert "lost_amulet" not in inv
    assert "old_notice" in inv


def test_build_result_character_stat_deltas():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        character_stat_deltas={"traveler": {"trust": 20}},
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.character_stat_deltas == {"traveler": {"trust": 20}}


def test_load_story_nodes_with_extended_effects(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: test_extended
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates:
        q1: { status: done }
      new_events:
        - id: ev1
          type: story
          description: "something happened"
      add_items:
        - item_id: map_fragment
          to: inventory
        - item_id: lost_amulet
          to: backyard
      remove_items:
        - item_id: old_key
          from: inventory
      character_stat_deltas:
        traveler:
          trust: 20
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "test_extended" in nodes
    effects = nodes["test_extended"].effects
    assert len(effects.add_items) == 2
    assert effects.add_items[0].item_id == "map_fragment"
    assert effects.add_items[0].to == "inventory"
    assert effects.add_items[1].to == "backyard"
    assert len(effects.remove_items) == 1
    assert effects.remove_items[0].item_id == "old_key"
    assert effects.remove_items[0].from_ == "inventory"
    assert effects.character_stat_deltas == {"traveler": {"trust": 20}}


def test_build_result_multiple_add_items_same_location():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        add_items=(
            ItemPlacement(item_id="item_a", to="backyard"),
            ItemPlacement(item_id="item_b", to="backyard"),
        ),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    backyard = MagicMock()
    backyard.items = ()
    state.locations = {"tavern": MagicMock(items=()), "backyard": backyard}
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    loc_items = diff.updated_locations["backyard"]["items"]
    assert "item_a" in loc_items
    assert "item_b" in loc_items


def test_build_result_location_only_no_spurious_inventory():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        add_items=(ItemPlacement(item_id="lost_amulet", to="backyard"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    backyard = MagicMock()
    backyard.items = ()
    state.locations = {"tavern": MagicMock(items=()), "backyard": backyard}
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.updated_characters == {}


# ---------------------------------------------------------------------------
# trigger_ending
# ---------------------------------------------------------------------------

def test_build_result_trigger_ending():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={"main_story": {"status": "good_ending"}},
        new_events=(),
        trigger_ending="good_ending",
    )
    node = StoryNode(
        id="ending_good", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint="温暖收束", fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.new_endings == ("good_ending",)


def test_build_result_no_trigger_ending():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={"q1": {"status": "done"}},
        new_events=(),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.new_endings == ()


def test_load_story_nodes_with_trigger_ending(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: ending_good
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates:
        main_story: { status: good_ending }
      new_events:
        - id: ending_good_reached
          type: ending
          description: "好结局达成"
      trigger_ending: good_ending
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "ending_good" in nodes
    assert nodes["ending_good"].effects.trigger_ending == "good_ending"


def test_load_story_nodes_without_trigger_ending(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: normal_node
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates: {}
      new_events: []
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert nodes["normal_node"].effects.trigger_ending is None


def test_load_tavern_story_yaml_includes_endings():
    from tavern.data import get_bundled_scenario
    from tavern.engine.story import load_story_nodes
    path = get_bundled_scenario("tavern") / "story.yaml"
    if not path.exists():
        pytest.skip("tavern story.yaml not found")
    nodes = load_story_nodes(path)
    assert "ending_good" in nodes
    assert "ending_bad" in nodes
    assert "ending_neutral" in nodes
    assert "betray_guest" in nodes
    assert nodes["ending_good"].effects.trigger_ending == "good_ending"
    assert nodes["ending_bad"].effects.trigger_ending == "bad_ending"
    assert nodes["ending_neutral"].effects.trigger_ending == "neutral_ending"
    assert nodes["betray_guest"].effects.trigger_ending is None