from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tavern.world.memory import EventTimeline, RelationshipDelta, RelationshipGraph
from tavern.world.models import Character, CharacterRole, Event, Location
from tavern.world.state import WorldState


def _minimal_state(trust: int = 10) -> WorldState:
    return WorldState(
        turn=5,
        player_id="player",
        locations={
            "hall": Location(id="hall", name="大厅", description="大厅", npcs=("bartender",)),
        },
        characters={
            "player": Character(
                id="player", name="冒险者", role=CharacterRole.PLAYER,
                stats={"hp": 100}, location_id="hall",
            ),
            "bartender": Character(
                id="bartender", name="格里姆", role=CharacterRole.NPC,
                stats={"trust": trust}, location_id="hall",
            ),
        },
        items={},
        quests={"main_quest": {"status": "active"}},
    )


def _make_timeline(*event_ids: str) -> EventTimeline:
    events = tuple(
        Event(id=eid, turn=i, type="custom", actor="player",
              description=f"事件{eid}", consequences=())
        for i, eid in enumerate(event_ids)
    )
    return EventTimeline(events)


def _make_graph(src: str, tgt: str, value: int) -> RelationshipGraph:
    g = RelationshipGraph()
    g.update(RelationshipDelta(src=src, tgt=tgt, delta=value))
    return g


SKILL_YAML = textwrap.dedent("""\
    id: gossip_unlock
    character: bartender
    priority: high
    activation:
      - type: relationship
        source: bartender
        target: player
        attribute: trust
        operator: ">="
        value: 20
    facts:
      - "格里姆知道地下室藏有秘密"
    behavior:
      tone: "神秘"
      reveal_strategy: "暗示"
""")

SKILL_EVENT_YAML = textwrap.dedent("""\
    id: after_quest_started
    character: bartender
    priority: normal
    activation:
      - type: event
        event_id: quest_started
        check: exists
    facts:
      - "格里姆见过寻宝者"
    behavior:
      tone: "警觉"
""")


class TestSkillLoading:
    def test_load_skills_from_directory(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "gossip_unlock.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        skills = list(manager._skills.values())
        assert len(skills) == 1
        assert skills[0].id == "gossip_unlock"
        assert skills[0].character == "bartender"
        assert skills[0].priority == "high"

    def test_load_skips_invalid_yaml(self, tmp_path: Path, caplog):
        from tavern.world.skills import SkillManager
        (tmp_path / "bad.yaml").write_text("invalid: [unclosed", encoding="utf-8")
        manager = SkillManager()
        with caplog.at_level("WARNING"):
            manager.load_skills(tmp_path)
        assert len(manager._skills) == 0

    def test_load_empty_directory(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        manager = SkillManager()
        manager.load_skills(tmp_path)
        assert len(manager._skills) == 0

    def test_skill_facts_and_behavior(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "gossip.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        skill = manager._skills["gossip_unlock"]
        assert "格里姆知道地下室藏有秘密" in skill.facts
        assert skill.behavior["tone"] == "神秘"


class TestConditionEvaluator:
    def test_relationship_condition_passes(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(
            type="relationship",
            source="bartender", target="player",
            attribute="trust", operator=">=", value=20,
        )
        g = _make_graph("bartender", "player", 25)
        assert ConditionEvaluator.evaluate(cond, _minimal_state(), _make_timeline(), g) is True

    def test_relationship_condition_fails(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(
            type="relationship",
            source="bartender", target="player",
            attribute="trust", operator=">=", value=20,
        )
        g = _make_graph("bartender", "player", 10)
        assert ConditionEvaluator.evaluate(cond, _minimal_state(), _make_timeline(), g) is False

    def test_event_exists_condition(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(type="event", event_id="quest_started", check="exists")
        timeline = _make_timeline("quest_started")
        g = RelationshipGraph()
        assert ConditionEvaluator.evaluate(cond, _minimal_state(), timeline, g) is True

    def test_event_not_exists_condition(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(type="event", event_id="quest_started", check="not_exists")
        timeline = _make_timeline()
        g = RelationshipGraph()
        assert ConditionEvaluator.evaluate(cond, _minimal_state(), timeline, g) is True

    def test_quest_condition(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(type="quest", event_id="main_quest", check="active")
        state = _minimal_state()
        g = RelationshipGraph()
        timeline = _make_timeline()
        assert ConditionEvaluator.evaluate(cond, state, timeline, g) is True

    def test_inventory_condition(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(type="inventory", event_id="cellar_key")
        state = WorldState(
            turn=0,
            player_id="player",
            locations={"hall": Location(id="hall", name="大厅", description="大厅")},
            characters={
                "player": Character(
                    id="player", name="冒险者", role=CharacterRole.PLAYER,
                    stats={}, inventory=("cellar_key",), location_id="hall",
                ),
            },
            items={},
        )
        g = RelationshipGraph()
        assert ConditionEvaluator.evaluate(cond, state, _make_timeline(), g) is True

    def test_inventory_condition_missing(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        cond = ActivationCondition(type="inventory", event_id="cellar_key")
        g = RelationshipGraph()
        assert ConditionEvaluator.evaluate(cond, _minimal_state(), _make_timeline(), g) is False


class TestGetActiveSkills:
    def test_returns_skills_matching_char_and_conditions(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "gossip.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        g = _make_graph("bartender", "player", 25)
        timeline = _make_timeline()
        skills = manager.get_active_skills("bartender", _minimal_state(), timeline, g)
        assert len(skills) == 1
        assert skills[0].id == "gossip_unlock"

    def test_excludes_skills_for_other_characters(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "gossip.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        g = _make_graph("bartender", "player", 25)
        skills = manager.get_active_skills("traveler", _minimal_state(), _make_timeline(), g)
        assert len(skills) == 0

    def test_excludes_skills_when_conditions_fail(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "gossip.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        g = _make_graph("bartender", "player", 5)
        skills = manager.get_active_skills("bartender", _minimal_state(), _make_timeline(), g)
        assert len(skills) == 0

    def test_priority_ordering(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        low_yaml = textwrap.dedent("""\
            id: low_priority_skill
            character: bartender
            priority: low
            activation:
              - type: relationship
                source: bartender
                target: player
                attribute: trust
                operator: ">="
                value: 20
            facts:
              - "低优先级信息"
            behavior:
              tone: "普通"
        """)
        (tmp_path / "high.yaml").write_text(SKILL_YAML, encoding="utf-8")
        (tmp_path / "low.yaml").write_text(low_yaml, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        g = _make_graph("bartender", "player", 25)
        skills = manager.get_active_skills("bartender", _minimal_state(), _make_timeline(), g)
        assert skills[0].priority == "high"
        assert skills[-1].priority == "low"


class TestInjectToPrompt:
    def test_inject_empty_returns_empty_string(self):
        from tavern.world.skills import SkillManager
        manager = SkillManager()
        text = manager.inject_to_prompt([])
        assert text == ""

    def test_inject_includes_facts(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        (tmp_path / "s.yaml").write_text(SKILL_YAML, encoding="utf-8")
        manager = SkillManager()
        manager.load_skills(tmp_path)
        skill = manager._skills["gossip_unlock"]
        text = manager.inject_to_prompt([skill])
        assert "格里姆知道地下室藏有秘密" in text

    def test_inject_truncates_low_priority(self):
        from tavern.world.skills import SkillManager, Skill, ActivationCondition
        skills = [
            Skill(
                id=f"skill_{i}",
                character="bartender",
                priority="low",
                activation=(),
                facts=(f"事实{i}" * 50,),
                behavior={"tone": "neutral"},
            )
            for i in range(20)
        ]
        manager = SkillManager()
        text = manager.inject_to_prompt(skills, max_chars=100)
        assert len(text) <= 200
