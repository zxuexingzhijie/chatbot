# Phase 2c Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a memory layer (EventTimeline + RelationshipGraph + SkillManager + MemorySystem) that provides contextual `MemoryContext` packets to Narrator and DialogueManager, making NPCs aware of history and relationship state.

**Architecture:** MemorySystem is a push model — GameApp builds context via `memory.build_context()` and passes a `MemoryContext` dataclass to Narrator/DialogueManager as an optional parameter. `None` leaves behavior identical to Phase 2b. RelationshipGraph runs parallel to `stats["trust"]`, synchronized via `StateDiff.relationship_changes` after every `state_manager.commit()` call.

**Tech Stack:** Python 3.12+, networkx>=3.0 (already in deps), PyYAML, pytest + pytest-asyncio, dataclasses (frozen), Pydantic v2 frozen models for WorldState/StateDiff.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/tavern/world/memory.py` | `MemoryContext`, `RelationshipDelta`, `Relationship`, `EventTimeline`, `RelationshipGraph`, `MemorySystem` |
| Create | `src/tavern/world/skills.py` | `ActivationCondition`, `Skill`, `ConditionEvaluator`, `SkillManager` |
| Modify | `src/tavern/narrator/prompts.py` | Add `memory_ctx` param to `build_narrative_prompt` |
| Modify | `src/tavern/narrator/narrator.py` | Add `memory_ctx` param to `stream_narrative` |
| Modify | `src/tavern/dialogue/prompts.py` | Add `active_skills_text` param to `build_dialogue_prompt` |
| Modify | `src/tavern/dialogue/manager.py` | Add `memory_ctx` param to `start` and `respond` |
| Modify | `src/tavern/cli/app.py` | Wire `MemorySystem`, call `build_context()`, pass `memory_ctx`, call `apply_diff` after every commit |
| Create | `data/scenarios/tavern/skills/` | Empty directory (placeholder for Phase 3 YAML files) |
| Create | `tests/world/test_memory.py` | EventTimeline + RelationshipGraph + MemorySystem tests |
| Create | `tests/world/test_skills.py` | SkillManager + ConditionEvaluator tests |
| Modify | `tests/narrator/test_prompts.py` | Add memory_ctx tests |
| Modify | `tests/dialogue/test_prompts.py` | Add active_skills_text tests |
| Modify | `tests/dialogue/test_manager.py` | Add memory_ctx passthrough tests |
| Create | `tests/cli/test_app_memory.py` | GameApp memory wiring tests |

---

## Task 1: MemoryContext dataclass + EventTimeline

**Files:**
- Create: `src/tavern/world/memory.py`
- Create: `tests/world/test_memory.py`

- [ ] **Step 1: Create `tests/world/test_memory.py` with failing EventTimeline tests**

```python
# tests/world/test_memory.py
from __future__ import annotations

import pytest
from tavern.world.memory import (
    EventTimeline,
    MemoryContext,
    RelationshipDelta,
    Relationship,
)
from tavern.world.models import Event


def _make_event(id: str, turn: int, actor: str = "player", type: str = "move") -> Event:
    return Event(
        id=id,
        turn=turn,
        type=type,
        actor=actor,
        description=f"事件{id}发生了",
        consequences=(),
    )


class TestMemoryContext:
    def test_creation(self):
        ctx = MemoryContext(
            recent_events="最近：移动到吧台",
            relationship_summary="旅行者对你信任20",
            active_skills_text="",
        )
        assert ctx.recent_events == "最近：移动到吧台"
        assert ctx.active_skills_text == ""

    def test_immutable(self):
        ctx = MemoryContext(
            recent_events="test",
            relationship_summary="test",
            active_skills_text="",
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.recent_events = "changed"  # type: ignore


class TestEventTimeline:
    def test_recent_returns_last_n_events(self):
        events = tuple(_make_event(str(i), i) for i in range(10))
        timeline = EventTimeline(events)
        recent = timeline.recent(3)
        assert len(recent) == 3
        assert recent[-1].id == "9"

    def test_recent_returns_all_if_fewer(self):
        events = (_make_event("a", 1), _make_event("b", 2))
        timeline = EventTimeline(events)
        assert len(timeline.recent(10)) == 2

    def test_query_by_actor(self):
        events = (
            _make_event("e1", 1, actor="player"),
            _make_event("e2", 2, actor="bartender"),
            _make_event("e3", 3, actor="player"),
        )
        timeline = EventTimeline(events)
        result = timeline.query(actor="player")
        assert len(result) == 2
        assert all(e.actor == "player" for e in result)

    def test_query_by_type(self):
        events = (
            Event(id="e1", turn=1, type="move", actor="player", description="移动", consequences=()),
            Event(id="e2", turn=2, type="talk", actor="player", description="对话", consequences=()),
        )
        timeline = EventTimeline(events)
        result = timeline.query(type="talk")
        assert len(result) == 1
        assert result[0].id == "e2"

    def test_query_after_turn(self):
        events = tuple(_make_event(str(i), i) for i in range(5))
        timeline = EventTimeline(events)
        result = timeline.query(after_turn=2)
        assert all(e.turn > 2 for e in result)

    def test_summarize_empty_timeline(self):
        timeline = EventTimeline(())
        text = timeline.summarize()
        assert isinstance(text, str)

    def test_summarize_includes_recent_descriptions(self):
        events = (
            _make_event("e1", 1),
            _make_event("e2", 2),
        )
        timeline = EventTimeline(events)
        text = timeline.summarize()
        assert "事件e1发生了" in text or "事件e2发生了" in text

    def test_summarize_omits_old_events_with_placeholder(self):
        # 7 events: last 5 full, 2 earlier → placeholder
        events = tuple(_make_event(str(i), i) for i in range(7))
        timeline = EventTimeline(events)
        text = timeline.summarize()
        assert "省略" in text or "早期" in text

    def test_has_event_by_id(self):
        events = (_make_event("quest_started", 1),)
        timeline = EventTimeline(events)
        assert timeline.has("quest_started") is True
        assert timeline.has("nonexistent") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python -m pytest tests/world/test_memory.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'tavern.world.memory'`

- [ ] **Step 3: Create `src/tavern/world/memory.py` with MemoryContext + EventTimeline**

```python
# src/tavern/world/memory.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tavern.world.models import Event

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryContext:
    recent_events: str
    relationship_summary: str
    active_skills_text: str


@dataclass(frozen=True)
class RelationshipDelta:
    src: str
    tgt: str
    delta: int


@dataclass(frozen=True)
class Relationship:
    src: str
    tgt: str
    value: int  # clamped to [-100, 100]


class EventTimeline:
    def __init__(self, events: tuple[Event, ...]) -> None:
        self._events = events

    def recent(self, n: int = 5) -> list[Event]:
        return list(self._events[-n:]) if n > 0 else []

    def query(
        self,
        actor: str | None = None,
        type: str | None = None,
        after_turn: int | None = None,
    ) -> list[Event]:
        result = list(self._events)
        if actor is not None:
            result = [e for e in result if e.actor == actor]
        if type is not None:
            result = [e for e in result if e.type == type]
        if after_turn is not None:
            result = [e for e in result if e.turn > after_turn]
        return result

    def summarize(self, max_tokens: int = 200) -> str:
        if not self._events:
            return "（尚无历史事件）"
        recent = list(self._events[-5:])
        older_count = max(0, len(self._events) - 5)
        parts: list[str] = []
        if older_count > 0:
            parts.append(f"[已省略{older_count}条早期事件]")
        for e in recent:
            parts.append(e.description)
        return "\n".join(parts)

    def has(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._events)
```

- [ ] **Step 4: Run EventTimeline + MemoryContext tests**

```bash
python -m pytest tests/world/test_memory.py::TestMemoryContext tests/world/test_memory.py::TestEventTimeline -v
```
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/memory.py tests/world/test_memory.py
git commit -m "feat: add MemoryContext dataclass and EventTimeline"
```

---

## Task 2: RelationshipGraph

**Files:**
- Modify: `src/tavern/world/memory.py` (add RelationshipGraph class)
- Modify: `tests/world/test_memory.py` (add TestRelationshipGraph class)

- [ ] **Step 1: Add failing RelationshipGraph tests to `tests/world/test_memory.py`**

Append to the file:

```python
class TestRelationshipGraph:
    def test_get_nonexistent_edge_returns_zero(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        rel = g.get("player", "traveler")
        assert rel.value == 0
        assert rel.src == "player"
        assert rel.tgt == "traveler"

    def test_update_adds_edge(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        rel = g.update(RelationshipDelta(src="player", tgt="traveler", delta=20))
        assert rel.value == 20

    def test_update_clamps_upper(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=90))
        rel = g.update(RelationshipDelta(src="a", tgt="b", delta=90))
        assert rel.value == 100

    def test_update_clamps_lower(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=-90))
        rel = g.update(RelationshipDelta(src="a", tgt="b", delta=-90))
        assert rel.value == -100

    def test_get_all_for_returns_outgoing(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="traveler", tgt="player", delta=10))
        g.update(RelationshipDelta(src="traveler", tgt="grim", delta=-5))
        g.update(RelationshipDelta(src="player", tgt="traveler", delta=15))
        rels = g.get_all_for("traveler")
        assert len(rels) == 2
        assert all(r.src == "traveler" for r in rels)

    def test_describe_for_prompt_contains_char(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="traveler", tgt="player", delta=25))
        text = g.describe_for_prompt("traveler")
        assert "traveler" in text or "player" in text
        assert "25" in text or "友好" in text

    def test_snapshot_round_trip(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph()
        g.update(RelationshipDelta(src="a", tgt="b", delta=30))
        snapshot = g.to_snapshot()
        g2 = RelationshipGraph(snapshot=snapshot)
        assert g2.get("a", "b").value == 30

    def test_init_from_none_snapshot(self):
        from tavern.world.memory import RelationshipGraph
        g = RelationshipGraph(snapshot=None)
        assert g.get("x", "y").value == 0
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/world/test_memory.py::TestRelationshipGraph -v 2>&1 | head -20
```
Expected: `ImportError` or `AttributeError: ... RelationshipGraph`.

- [ ] **Step 3: Add `RelationshipGraph` to `src/tavern/world/memory.py`**

Add this import at the top of the file (after existing imports):

```python
import networkx as nx
```

Then append the class after `EventTimeline`:

```python
class RelationshipGraph:
    def __init__(self, snapshot: dict | None = None) -> None:
        if snapshot is not None:
            try:
                self._g: nx.DiGraph = nx.node_link_graph(snapshot, directed=True)
            except Exception:
                logger.warning("RelationshipGraph: snapshot corrupt, initializing empty graph")
                self._g = nx.DiGraph()
        else:
            self._g = nx.DiGraph()

    def get(self, src: str, tgt: str) -> Relationship:
        value = self._g.edges.get((src, tgt), {}).get("value", 0)
        return Relationship(src=src, tgt=tgt, value=value)

    def update(self, delta: RelationshipDelta) -> Relationship:
        current = self.get(delta.src, delta.tgt).value
        new_value = max(-100, min(100, current + delta.delta))
        self._g.add_edge(delta.src, delta.tgt, value=new_value)
        return Relationship(src=delta.src, tgt=delta.tgt, value=new_value)

    def get_all_for(self, char_id: str) -> list[Relationship]:
        return [
            Relationship(src=char_id, tgt=tgt, value=data.get("value", 0))
            for tgt, data in self._g[char_id].items()
        ] if char_id in self._g else []

    def describe_for_prompt(self, char_id: str) -> str:
        rels = self.get_all_for(char_id)
        if not rels:
            return f"（{char_id}尚无记录的关系）"
        lines: list[str] = []
        for r in rels:
            if r.value >= 60:
                label = "非常友好"
            elif r.value >= 20:
                label = "友好"
            elif r.value <= -60:
                label = "非常敌对"
            elif r.value <= -20:
                label = "敌对"
            else:
                label = "中立"
            lines.append(f"{char_id}对{r.tgt}的信任: {r.value}（{label}）")
        return "\n".join(lines)

    def to_snapshot(self) -> dict:
        return nx.node_link_data(self._g)
```

- [ ] **Step 4: Run all RelationshipGraph tests**

```bash
python -m pytest tests/world/test_memory.py::TestRelationshipGraph -v
```
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/memory.py tests/world/test_memory.py
git commit -m "feat: add RelationshipGraph with clamp, snapshot round-trip"
```

---

## Task 3: SkillManager + ConditionEvaluator

**Files:**
- Create: `src/tavern/world/skills.py`
- Create: `tests/world/test_skills.py`
- Create: `data/scenarios/tavern/skills/` (empty directory via a `.gitkeep`)

- [ ] **Step 1: Create `tests/world/test_skills.py` with failing tests**

```python
# tests/world/test_skills.py
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

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
        cond = ActivationCondition(
            type="quest", event_id="main_quest",
            attribute="status", operator="==", value=None,
        )
        # quest status check: value is the expected string stored in event_id field
        # For simplicity use event_id as quest_id and check as the expected status value
        cond2 = ActivationCondition(
            type="quest", event_id="main_quest", check="active",
        )
        state = _minimal_state()
        g = RelationshipGraph()
        timeline = _make_timeline()
        assert ConditionEvaluator.evaluate(cond2, state, timeline, g) is True

    def test_inventory_condition(self):
        from tavern.world.skills import ConditionEvaluator, ActivationCondition
        from tavern.world.models import Character, CharacterRole
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
        g = _make_graph("bartender", "player", 5)  # trust=5, < 20 threshold
        skills = manager.get_active_skills("bartender", _minimal_state(), _make_timeline(), g)
        assert len(skills) == 0

    def test_priority_ordering(self, tmp_path: Path):
        from tavern.world.skills import SkillManager
        high_yaml = SKILL_YAML  # priority: high, condition: relationship >= 20
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
        (tmp_path / "high.yaml").write_text(high_yaml, encoding="utf-8")
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

    def test_inject_truncates_low_priority(self, tmp_path: Path):
        from tavern.world.skills import SkillManager, Skill, ActivationCondition
        # Build many skills manually to hit max_chars
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
        assert len(text) <= 200  # some slack for structure, but clearly truncated
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/world/test_skills.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'tavern.world.skills'`

- [ ] **Step 3: Create `src/tavern/world/skills.py`**

```python
# src/tavern/world/skills.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


@dataclass(frozen=True)
class ActivationCondition:
    type: str  # "relationship" | "event" | "quest" | "inventory"
    source: str | None = None
    target: str | None = None
    attribute: str | None = None
    operator: str | None = None
    value: int | None = None
    event_id: str | None = None
    check: str | None = None


@dataclass(frozen=True)
class Skill:
    id: str
    character: str
    priority: str  # "high" | "normal" | "low"
    activation: tuple[ActivationCondition, ...]
    facts: tuple[str, ...]
    behavior: dict[str, str]


class ConditionEvaluator:
    @staticmethod
    def evaluate(
        cond: ActivationCondition,
        state: WorldState,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
    ) -> bool:
        if cond.type == "relationship":
            return ConditionEvaluator._eval_relationship(cond, relationships)
        if cond.type == "event":
            return ConditionEvaluator._eval_event(cond, timeline)
        if cond.type == "quest":
            return ConditionEvaluator._eval_quest(cond, state)
        if cond.type == "inventory":
            return ConditionEvaluator._eval_inventory(cond, state)
        logger.warning("ConditionEvaluator: unknown condition type %r", cond.type)
        return False

    @staticmethod
    def _eval_relationship(
        cond: ActivationCondition, relationships: RelationshipGraph
    ) -> bool:
        if cond.source is None or cond.target is None or cond.operator is None or cond.value is None:
            return False
        rel = relationships.get(cond.source, cond.target)
        v = rel.value
        t = cond.value
        ops = {"==": v == t, "!=": v != t, ">": v > t, "<": v < t, ">=": v >= t, "<=": v <= t}
        return ops.get(cond.operator, False)

    @staticmethod
    def _eval_event(cond: ActivationCondition, timeline: EventTimeline) -> bool:
        if cond.event_id is None:
            return False
        exists = timeline.has(cond.event_id)
        if cond.check == "exists":
            return exists
        if cond.check == "not_exists":
            return not exists
        return False

    @staticmethod
    def _eval_quest(cond: ActivationCondition, state: WorldState) -> bool:
        if cond.event_id is None or cond.check is None:
            return False
        quest = state.quests.get(cond.event_id, {})
        return quest.get("status") == cond.check

    @staticmethod
    def _eval_inventory(cond: ActivationCondition, state: WorldState) -> bool:
        if cond.event_id is None:
            return False
        player = state.characters.get(state.player_id)
        if player is None:
            return False
        return cond.event_id in player.inventory


class SkillManager:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def load_skills(self, scenario_path: Path) -> None:
        for yaml_file in sorted(scenario_path.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or "id" not in raw:
                    logger.warning("SkillManager: skipping %s (not a valid skill dict)", yaml_file)
                    continue
                conditions = tuple(
                    ActivationCondition(**c) for c in (raw.get("activation") or [])
                )
                skill = Skill(
                    id=raw["id"],
                    character=raw.get("character", ""),
                    priority=raw.get("priority", "normal"),
                    activation=conditions,
                    facts=tuple(raw.get("facts") or []),
                    behavior=dict(raw.get("behavior") or {}),
                )
                self._skills[skill.id] = skill
            except Exception as exc:
                logger.warning("SkillManager: failed to load %s: %s", yaml_file, exc)

    def get_active_skills(
        self,
        char_id: str,
        state: WorldState,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
    ) -> list[Skill]:
        result = []
        for skill in self._skills.values():
            if skill.character != char_id:
                continue
            if all(
                ConditionEvaluator.evaluate(cond, state, timeline, relationships)
                for cond in skill.activation
            ):
                result.append(skill)
        result.sort(key=lambda s: _PRIORITY_ORDER.get(s.priority, 1))
        return result

    def inject_to_prompt(self, skills: list[Skill], max_chars: int = 800) -> str:
        if not skills:
            return ""
        parts: list[str] = []
        total = 0
        for skill in skills:
            lines = list(skill.facts) + [
                f"{k}: {v}" for k, v in skill.behavior.items()
            ]
            chunk = "\n".join(lines)
            if total + len(chunk) > max_chars and parts:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)
```

- [ ] **Step 4: Create the skills placeholder directory**

```bash
mkdir -p /Users/makoto/Downloads/work/chatbot/data/scenarios/tavern/skills
touch /Users/makoto/Downloads/work/chatbot/data/scenarios/tavern/skills/.gitkeep
```

- [ ] **Step 5: Run all skills tests**

```bash
python -m pytest tests/world/test_skills.py -v
```
Expected: All tests PASS (some quest/inventory tests may need verification — see step below if failures).

- [ ] **Step 6: Commit**

```bash
git add src/tavern/world/skills.py tests/world/test_skills.py data/scenarios/tavern/skills/.gitkeep
git commit -m "feat: add SkillManager, ConditionEvaluator, and Skill dataclass"
```

---

## Task 4: MemorySystem

**Files:**
- Modify: `src/tavern/world/memory.py` (add MemorySystem class)
- Modify: `tests/world/test_memory.py` (add TestMemorySystem class)

- [ ] **Step 1: Add failing MemorySystem tests to `tests/world/test_memory.py`**

Append to the file:

```python
class TestMemorySystem:
    def _make_state(self, trust: int = 0) -> "WorldState":
        from tavern.world.models import Character, CharacterRole, Location
        from tavern.world.state import WorldState
        return WorldState(
            turn=3,
            player_id="player",
            locations={"hall": Location(id="hall", name="大厅", description="大厅", npcs=("traveler",))},
            characters={
                "player": Character(
                    id="player", name="冒险者", role=CharacterRole.PLAYER,
                    stats={"hp": 100}, location_id="hall",
                ),
                "traveler": Character(
                    id="traveler", name="旅行者", role=CharacterRole.NPC,
                    stats={"trust": trust}, location_id="hall",
                ),
            },
            items={},
            timeline=(
                Event(id="e1", turn=1, type="move", actor="player", description="进入酒馆", consequences=()),
            ),
        )

    def test_build_context_returns_memory_context(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state)
        ctx = mem.build_context("traveler", state)
        assert isinstance(ctx, MemoryContext)
        assert isinstance(ctx.recent_events, str)
        assert isinstance(ctx.relationship_summary, str)
        assert isinstance(ctx.active_skills_text, str)

    def test_build_context_recent_events_contains_event(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state)
        ctx = mem.build_context("traveler", state)
        assert "进入酒馆" in ctx.recent_events

    def test_apply_diff_syncs_relationship(self):
        from tavern.world.memory import MemorySystem, RelationshipDelta
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)

        diff = StateDiff(
            relationship_changes=(
                {"src": "traveler", "tgt": "player", "delta": 30},
            ),
        )
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)

        rel = mem._relationship_graph.get("traveler", "player")
        assert rel.value == 30

    def test_apply_diff_empty_relationship_changes_is_noop(self):
        from tavern.world.memory import MemorySystem
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)
        diff = StateDiff(turn_increment=1)
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)  # should not raise

    def test_apply_diff_rebuilds_timeline(self):
        from tavern.world.memory import MemorySystem
        from tavern.world.state import StateDiff
        state = self._make_state()
        mem = MemorySystem(state=state)
        new_event = Event(id="e2", turn=4, type="talk", actor="traveler",
                          description="旅行者谈起北方", consequences=())
        diff = StateDiff(new_events=(new_event,))
        new_state = state.apply(diff)
        mem.apply_diff(diff, new_state)
        ctx = mem.build_context("traveler", new_state)
        assert "旅行者谈起北方" in ctx.recent_events

    def test_sync_to_state_writes_snapshot(self):
        from tavern.world.memory import MemorySystem, RelationshipDelta
        state = self._make_state()
        mem = MemorySystem(state=state)
        mem._relationship_graph.update(RelationshipDelta(src="a", tgt="b", delta=10))
        new_state = mem.sync_to_state(state)
        assert new_state.relationships_snapshot != {}

    def test_init_with_no_skills_dir(self):
        from tavern.world.memory import MemorySystem
        state = self._make_state()
        mem = MemorySystem(state=state, skills_dir=None)
        ctx = mem.build_context("traveler", state)
        assert ctx.active_skills_text == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/world/test_memory.py::TestMemorySystem -v 2>&1 | head -20
```
Expected: `ImportError` for `MemorySystem`.

- [ ] **Step 3: Add `MemorySystem` to `src/tavern/world/memory.py`**

Add this import at the top with existing TYPE_CHECKING imports:

```python
from tavern.world.skills import SkillManager
```

(Move it out of TYPE_CHECKING since MemorySystem needs it at runtime.)

Then append after `RelationshipGraph`:

```python
class MemorySystem:
    def __init__(self, state: WorldState, skills_dir: Path | None = None) -> None:
        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("MemorySystem: failed to restore RelationshipGraph, using empty")
            self._relationship_graph = RelationshipGraph()
        self._skill_manager = SkillManager()
        if skills_dir is not None:
            self._skill_manager.load_skills(skills_dir)

    def apply_diff(self, diff: StateDiff, new_state: WorldState) -> None:
        for change in diff.relationship_changes:
            if isinstance(change, dict):
                delta = RelationshipDelta(
                    src=change["src"], tgt=change["tgt"], delta=change["delta"]
                )
            else:
                delta = change
            self._relationship_graph.update(delta)
        self._timeline = EventTimeline(new_state.timeline)

    def build_context(
        self,
        actor: str,
        state: WorldState,
        current_topic: str = "",
        max_tokens: int = 2000,
    ) -> MemoryContext:
        recent_events = self._timeline.summarize()
        relationship_summary = self._relationship_graph.describe_for_prompt(actor)
        max_chars = max(100, max_tokens * 3 // 4)
        active_skills = self._skill_manager.get_active_skills(
            actor, state, self._timeline, self._relationship_graph
        )
        active_skills_text = self._skill_manager.inject_to_prompt(active_skills, max_chars=max_chars)
        return MemoryContext(
            recent_events=recent_events,
            relationship_summary=relationship_summary,
            active_skills_text=active_skills_text,
        )

    def sync_to_state(self, state: WorldState) -> WorldState:
        snapshot = self._relationship_graph.to_snapshot()
        return state.model_copy(update={"relationships_snapshot": snapshot})
```

Also update the imports at the top of `memory.py` — remove `SkillManager` from `TYPE_CHECKING` and add it as a direct import:

The full imports section of `memory.py` should look like:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx
import yaml  # not needed yet, remove if present

from tavern.world.models import Event
from tavern.world.skills import SkillManager

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState
```

Wait — `MemorySystem.__init__` uses `WorldState` and `apply_diff` uses `StateDiff` at runtime, not just type hints. Fix by importing them directly:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from tavern.world.models import Event
from tavern.world.skills import SkillManager
from tavern.world.state import StateDiff, WorldState
```

But `skills.py` imports `EventTimeline` and `RelationshipGraph` from `memory.py` inside TYPE_CHECKING (to avoid circular). And `memory.py` imports `SkillManager` from `skills.py`. This is a potential circular import — resolve by keeping `SkillManager` import inside the method bodies or using TYPE_CHECKING:

Use lazy import inside `MemorySystem` methods to avoid circular:

```python
# src/tavern/world/memory.py  — final imports section
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx

from tavern.world.models import Event

if TYPE_CHECKING:
    from tavern.world.skills import SkillManager
    from tavern.world.state import StateDiff, WorldState
```

And in `MemorySystem.__init__` do a runtime import:

```python
class MemorySystem:
    def __init__(self, state: WorldState, skills_dir: Path | None = None) -> None:
        from tavern.world.skills import SkillManager  # avoid circular
        from tavern.world.state import StateDiff, WorldState  # runtime use
        ...
```

Actually, `WorldState` and `StateDiff` are used as parameter types at runtime only for isinstance checks — since we use `from __future__ import annotations`, all annotations are strings, so we only need actual imports when we access attributes. Let's keep it clean:

The complete final `src/tavern/world/memory.py`:

```python
# src/tavern/world/memory.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx

from tavern.world.models import Event

if TYPE_CHECKING:
    from tavern.world.skills import SkillManager as _SkillManager
    from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryContext:
    recent_events: str
    relationship_summary: str
    active_skills_text: str


@dataclass(frozen=True)
class RelationshipDelta:
    src: str
    tgt: str
    delta: int


@dataclass(frozen=True)
class Relationship:
    src: str
    tgt: str
    value: int  # clamped to [-100, 100]


class EventTimeline:
    def __init__(self, events: tuple[Event, ...]) -> None:
        self._events = events

    def recent(self, n: int = 5) -> list[Event]:
        return list(self._events[-n:]) if n > 0 else []

    def query(
        self,
        actor: str | None = None,
        type: str | None = None,
        after_turn: int | None = None,
    ) -> list[Event]:
        result = list(self._events)
        if actor is not None:
            result = [e for e in result if e.actor == actor]
        if type is not None:
            result = [e for e in result if e.type == type]
        if after_turn is not None:
            result = [e for e in result if e.turn > after_turn]
        return result

    def summarize(self, max_tokens: int = 200) -> str:
        if not self._events:
            return "（尚无历史事件）"
        recent = list(self._events[-5:])
        older_count = max(0, len(self._events) - 5)
        parts: list[str] = []
        if older_count > 0:
            parts.append(f"[已省略{older_count}条早期事件]")
        for e in recent:
            parts.append(e.description)
        return "\n".join(parts)

    def has(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._events)


class RelationshipGraph:
    def __init__(self, snapshot: dict | None = None) -> None:
        if snapshot is not None:
            try:
                self._g: nx.DiGraph = nx.node_link_graph(snapshot, directed=True)
            except Exception:
                logger.warning("RelationshipGraph: snapshot corrupt, initializing empty graph")
                self._g = nx.DiGraph()
        else:
            self._g = nx.DiGraph()

    def get(self, src: str, tgt: str) -> Relationship:
        value = self._g.edges.get((src, tgt), {}).get("value", 0)
        return Relationship(src=src, tgt=tgt, value=value)

    def update(self, delta: RelationshipDelta) -> Relationship:
        current = self.get(delta.src, delta.tgt).value
        new_value = max(-100, min(100, current + delta.delta))
        self._g.add_edge(delta.src, delta.tgt, value=new_value)
        return Relationship(src=delta.src, tgt=delta.tgt, value=new_value)

    def get_all_for(self, char_id: str) -> list[Relationship]:
        return [
            Relationship(src=char_id, tgt=tgt, value=data.get("value", 0))
            for tgt, data in self._g[char_id].items()
        ] if char_id in self._g else []

    def describe_for_prompt(self, char_id: str) -> str:
        rels = self.get_all_for(char_id)
        if not rels:
            return f"（{char_id}尚无记录的关系）"
        lines: list[str] = []
        for r in rels:
            if r.value >= 60:
                label = "非常友好"
            elif r.value >= 20:
                label = "友好"
            elif r.value <= -60:
                label = "非常敌对"
            elif r.value <= -20:
                label = "敌对"
            else:
                label = "中立"
            lines.append(f"{char_id}对{r.tgt}的信任: {r.value}（{label}）")
        return "\n".join(lines)

    def to_snapshot(self) -> dict:
        return nx.node_link_data(self._g)


class MemorySystem:
    def __init__(self, state: WorldState, skills_dir: Path | None = None) -> None:
        from tavern.world.skills import SkillManager  # lazy to avoid circular
        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("MemorySystem: failed to restore RelationshipGraph, using empty")
            self._relationship_graph = RelationshipGraph()
        self._skill_manager: SkillManager = SkillManager()
        if skills_dir is not None:
            self._skill_manager.load_skills(skills_dir)

    def apply_diff(self, diff: StateDiff, new_state: WorldState) -> None:
        for change in diff.relationship_changes:
            if isinstance(change, dict):
                delta = RelationshipDelta(
                    src=change["src"], tgt=change["tgt"], delta=change["delta"]
                )
            else:
                delta = change
            self._relationship_graph.update(delta)
        self._timeline = EventTimeline(new_state.timeline)

    def build_context(
        self,
        actor: str,
        state: WorldState,
        current_topic: str = "",
        max_tokens: int = 2000,
    ) -> MemoryContext:
        recent_events = self._timeline.summarize()
        relationship_summary = self._relationship_graph.describe_for_prompt(actor)
        max_chars = max(100, max_tokens * 3 // 4)
        active_skills = self._skill_manager.get_active_skills(
            actor, state, self._timeline, self._relationship_graph
        )
        active_skills_text = self._skill_manager.inject_to_prompt(
            active_skills, max_chars=max_chars
        )
        return MemoryContext(
            recent_events=recent_events,
            relationship_summary=relationship_summary,
            active_skills_text=active_skills_text,
        )

    def sync_to_state(self, state: WorldState) -> WorldState:
        snapshot = self._relationship_graph.to_snapshot()
        return state.model_copy(update={"relationships_snapshot": snapshot})
```

- [ ] **Step 4: Run all memory tests**

```bash
python -m pytest tests/world/test_memory.py -v
```
Expected: All tests PASS (≥19 tests).

- [ ] **Step 5: Run all tests to catch regressions**

```bash
python -m pytest --tb=short -q
```
Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/tavern/world/memory.py tests/world/test_memory.py
git commit -m "feat: add MemorySystem with build_context and apply_diff"
```

---

## Task 5: Narrator integration

**Files:**
- Modify: `src/tavern/narrator/prompts.py` (+15 lines)
- Modify: `src/tavern/narrator/narrator.py` (+5 lines)
- Modify: `tests/narrator/test_prompts.py` (+~25 lines)

- [ ] **Step 1: Add failing tests to `tests/narrator/test_prompts.py`**

Append to the file:

```python
class TestBuildNarrativePromptWithMemory:
    def _make_ctx(self) -> NarrativeContext:
        return NarrativeContext(
            action_type="move",
            action_message="你走进了吧台区。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target=None,
        )

    def test_memory_ctx_none_behaves_as_before(self):
        from tavern.narrator.prompts import build_narrative_prompt
        ctx = self._make_ctx()
        messages = build_narrative_prompt(ctx, memory_ctx=None)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"

    def test_memory_ctx_recent_events_appended_to_system(self):
        from tavern.narrator.prompts import build_narrative_prompt
        from tavern.world.memory import MemoryContext
        ctx = self._make_ctx()
        memory_ctx = MemoryContext(
            recent_events="[已省略2条]\n旅行者谈起北方",
            relationship_summary="traveler对player的信任: 20（友好）",
            active_skills_text="",
        )
        messages = build_narrative_prompt(ctx, memory_ctx=memory_ctx)
        assert "旅行者谈起北方" in messages[0]["content"]

    def test_memory_ctx_relationship_appended_to_system(self):
        from tavern.narrator.prompts import build_narrative_prompt
        from tavern.world.memory import MemoryContext
        ctx = self._make_ctx()
        memory_ctx = MemoryContext(
            recent_events="（尚无历史事件）",
            relationship_summary="traveler对player的信任: 35（友好）",
            active_skills_text="",
        )
        messages = build_narrative_prompt(ctx, memory_ctx=memory_ctx)
        assert "traveler" in messages[0]["content"]
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/narrator/test_prompts.py::TestBuildNarrativePromptWithMemory -v 2>&1 | head -20
```
Expected: `TypeError: build_narrative_prompt() got an unexpected keyword argument 'memory_ctx'`

- [ ] **Step 3: Update `src/tavern/narrator/prompts.py`**

Replace the `build_narrative_prompt` function signature and body:

```python
# Add import at top of file (after existing imports):
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.world.memory import MemoryContext
```

Replace the function:

```python
def build_narrative_prompt(
    ctx: NarrativeContext,
    memory_ctx: MemoryContext | None = None,
) -> list[dict[str, str]]:
    system_style = NARRATIVE_TEMPLATES.get(ctx.action_type, NARRATIVE_TEMPLATES["_default"])

    system_content = (
        f"{system_style}\n\n"
        f"当前地点：{ctx.location_name}——{ctx.location_desc}\n"
        f"玩家角色名：{ctx.player_name}"
    )

    if memory_ctx is not None:
        if memory_ctx.recent_events:
            system_content += f"\n\n【近期历史】\n{memory_ctx.recent_events}"
        if memory_ctx.relationship_summary:
            system_content += f"\n\n【关系状态】\n{memory_ctx.relationship_summary}"

    user_parts = [ctx.action_message]
    if ctx.target:
        user_parts.append(f"（涉及对象：{ctx.target}）")
    user_content = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
```

- [ ] **Step 4: Update `src/tavern/narrator/narrator.py`**

Replace `stream_narrative` signature and its call to `build_narrative_prompt`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt
from tavern.world.models import ActionResult
from tavern.world.state import WorldState

if TYPE_CHECKING:
    from tavern.llm.service import LLMService
    from tavern.world.memory import MemoryContext


class Narrator:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def stream_narrative(
        self,
        result: ActionResult,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            ctx = self._build_context(result, state)
            messages = build_narrative_prompt(ctx, memory_ctx)
            system_prompt = messages[0]["content"]
            action_message = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, action_message):
                yield chunk
        except Exception:
            yield result.message

    def _build_context(self, result: ActionResult, state: WorldState) -> NarrativeContext:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        target_name: str | None = None
        if result.target:
            if result.target in state.characters:
                target_name = state.characters[result.target].name
            elif result.target in state.items:
                target_name = state.items[result.target].name
            else:
                target_name = result.target

        return NarrativeContext(
            action_type=result.action.value,
            action_message=result.message,
            location_name=location.name,
            location_desc=location.description,
            player_name=player.name,
            target=target_name,
        )
```

- [ ] **Step 5: Run narrator tests**

```bash
python -m pytest tests/narrator/ -v
```
Expected: All tests PASS (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add src/tavern/narrator/prompts.py src/tavern/narrator/narrator.py tests/narrator/test_prompts.py
git commit -m "feat: pass MemoryContext to build_narrative_prompt and stream_narrative"
```

---

## Task 6: Dialogue prompts integration

**Files:**
- Modify: `src/tavern/dialogue/prompts.py` (+10 lines)
- Modify: `tests/dialogue/test_prompts.py` (+~20 lines)

- [ ] **Step 1: Add failing tests to `tests/dialogue/test_prompts.py`**

Append:

```python
class TestBuildDialoguePromptWithSkills:
    def _make_ctx(self) -> "DialogueContext":
        return DialogueContext(
            npc_id="bartender",
            npc_name="格里姆",
            npc_traits=("沉默",),
            trust=0,
            tone="neutral",
            messages=(),
            location_id="bar_area",
            turn_entered=0,
        )

    def test_active_skills_text_empty_string_no_change(self):
        ctx = self._make_ctx()
        prompt = build_dialogue_prompt(ctx, "吧台区", history_summaries=(), active_skills_text="")
        assert "【NPC知识与行为】" not in prompt

    def test_active_skills_text_appended_to_prompt(self):
        ctx = self._make_ctx()
        skills_text = "格里姆知道地下室藏有秘密\ntone: 神秘"
        prompt = build_dialogue_prompt(
            ctx, "吧台区", history_summaries=(), active_skills_text=skills_text
        )
        assert "格里姆知道地下室藏有秘密" in prompt
        assert "【NPC知识与行为】" in prompt
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/dialogue/test_prompts.py::TestBuildDialoguePromptWithSkills -v 2>&1 | head -20
```
Expected: `TypeError: build_dialogue_prompt() got an unexpected keyword argument 'active_skills_text'`

- [ ] **Step 3: Update `src/tavern/dialogue/prompts.py`**

Replace the `build_dialogue_prompt` signature and add the skills section before the return:

```python
def build_dialogue_prompt(
    ctx: DialogueContext,
    location_name: str,
    history_summaries: tuple[str, ...],
    is_persuade: bool = False,
    active_skills_text: str = "",
) -> str:
    traits_desc = "、".join(ctx.npc_traits) if ctx.npc_traits else "普通人"
    tone_instruction = TONE_TEMPLATES[ctx.tone]

    trust_label = (
        "非常不信任" if ctx.trust <= -20
        else "友好" if ctx.trust >= 20
        else "中立"
    )

    history_section = ""
    if history_summaries:
        history_lines = "\n".join(f"- {s}" for s in history_summaries)
        history_section = f"\n\n【历史对话记录】\n{history_lines}"

    persuade_note = ""
    if is_persuade:
        persuade_note = "\n\n【特殊情境】\n玩家正在尝试说服你，请根据信任关系决定是否被说服。"

    skills_section = ""
    if active_skills_text:
        skills_section = f"\n\n【NPC知识与行为】\n{active_skills_text}"

    return (
        f"你扮演角色：{ctx.npc_name}\n"
        f"性格特征：{traits_desc}\n"
        f"当前地点：{location_name}\n\n"
        f"【语气指令】\n{tone_instruction}\n\n"
        f"【关系状态】\n"
        f"当前信任值：{ctx.trust}（{trust_label}）"
        f"{history_section}\n\n"
        "【回复格式】\n"
        "必须以JSON格式回复，字段：\n"
        '- "text": 你的回复内容（2-4句话）\n'
        '- "trust_delta": 本轮关系变化，整数，范围 [-5, +5]。'
        "玩家友好、提供有用信息时为正；无理、骚扰时为负；普通对话为0\n"
        '- "mood": 你当前情绪，如 "平静"、"警惕"、"开心"、"不耐烦"\n'
        '- "wants_to_end": 布尔值，当你想结束对话时为 true（玩家反复骚扰、超出话题范围等）\n\n'
        f"保持角色一致性，不要脱离角色。{persuade_note}{skills_section}"
    )
```

- [ ] **Step 4: Run dialogue prompts tests**

```bash
python -m pytest tests/dialogue/test_prompts.py -v
```
Expected: All tests PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/tavern/dialogue/prompts.py tests/dialogue/test_prompts.py
git commit -m "feat: add active_skills_text param to build_dialogue_prompt"
```

---

## Task 7: DialogueManager integration

**Files:**
- Modify: `src/tavern/dialogue/manager.py` (+10 lines)
- Modify: `tests/dialogue/test_manager.py` (+~30 lines)

- [ ] **Step 1: Add failing tests to `tests/dialogue/test_manager.py`**

Append:

```python
class TestDialogueManagerMemoryCtx:
    @pytest.mark.asyncio
    async def test_start_accepts_memory_ctx(self, mock_llm_service, sample_state):
        from tavern.world.memory import MemoryContext
        manager = DialogueManager(llm_service=mock_llm_service)
        memory_ctx = MemoryContext(
            recent_events="进入酒馆",
            relationship_summary="traveler对player信任20",
            active_skills_text="格里姆知道秘密",
        )
        ctx, response = await manager.start(sample_state, "traveler", memory_ctx=memory_ctx)
        assert ctx.npc_id == "traveler"
        assert isinstance(response, DialogueResponse)

    @pytest.mark.asyncio
    async def test_start_none_memory_ctx_still_works(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, response = await manager.start(sample_state, "traveler", memory_ctx=None)
        assert ctx.npc_id == "traveler"

    @pytest.mark.asyncio
    async def test_respond_accepts_memory_ctx(self, mock_llm_service, sample_state):
        from tavern.world.memory import MemoryContext
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        memory_ctx = MemoryContext(
            recent_events="对话历史",
            relationship_summary="信任关系",
            active_skills_text="",
        )
        new_ctx, response = await manager.respond(ctx, "你好", sample_state, memory_ctx=memory_ctx)
        assert len(new_ctx.messages) == 3

    @pytest.mark.asyncio
    async def test_skills_text_passed_to_prompt(self, mock_llm_service, sample_state):
        from tavern.world.memory import MemoryContext
        from unittest.mock import patch
        manager = DialogueManager(llm_service=mock_llm_service)
        memory_ctx = MemoryContext(
            recent_events="",
            relationship_summary="",
            active_skills_text="格里姆知道北方秘密",
        )
        with patch(
            "tavern.dialogue.manager.build_dialogue_prompt",
            wraps=__import__("tavern.dialogue.prompts", fromlist=["build_dialogue_prompt"]).build_dialogue_prompt
        ) as mock_build:
            await manager.start(sample_state, "traveler", memory_ctx=memory_ctx)
            call_kwargs = mock_build.call_args[1] if mock_build.call_args else {}
            call_args = mock_build.call_args[0] if mock_build.call_args else ()
            # active_skills_text should be passed
            all_args = str(call_args) + str(call_kwargs)
            assert "格里姆知道北方秘密" in all_args
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/dialogue/test_manager.py::TestDialogueManagerMemoryCtx -v 2>&1 | head -20
```
Expected: `TypeError: start() got an unexpected keyword argument 'memory_ctx'`

- [ ] **Step 3: Update `src/tavern/dialogue/manager.py`**

Update imports at top:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.dialogue.context import (
    DialogueContext,
    DialogueResponse,
    DialogueSummary,
    Message,
)
from tavern.dialogue.prompts import build_dialogue_prompt, build_summary_prompt, resolve_tone
from tavern.llm.service import LLMService
from tavern.world.state import WorldState

if TYPE_CHECKING:
    from tavern.world.memory import MemoryContext
```

Update `start` signature and the `build_dialogue_prompt` call inside it:

```python
    async def start(
        self,
        state: WorldState,
        npc_id: str,
        is_persuade: bool = False,
        memory_ctx: MemoryContext | None = None,
    ) -> tuple[DialogueContext, DialogueResponse]:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        if npc_id not in state.characters:
            raise ValueError(f"未知角色: {npc_id}")
        if npc_id not in location.npcs:
            raise ValueError(f"{npc_id} 不在当前地点")

        npc = state.characters[npc_id]
        trust = int(npc.stats.get("trust", 0))
        tone = resolve_tone(trust)

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == npc_id
        )

        ctx = DialogueContext(
            npc_id=npc_id,
            npc_name=npc.name,
            npc_traits=npc.traits,
            trust=trust,
            tone=tone,
            messages=(),
            location_id=player.location_id,
            turn_entered=state.turn,
        )

        active_skills_text = memory_ctx.active_skills_text if memory_ctx is not None else ""
        system_prompt = build_dialogue_prompt(
            ctx, location.name, history_summaries,
            is_persuade=is_persuade,
            active_skills_text=active_skills_text,
        )
        response = await self._llm.generate_dialogue(system_prompt, messages=[])

        opening_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        new_trust = trust + response.trust_delta
        ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=new_trust,
            tone=resolve_tone(new_trust),
            messages=(opening_msg,),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = ctx
        return ctx, response
```

Update `respond` signature and the `build_dialogue_prompt` call inside it:

```python
    async def respond(
        self,
        ctx: DialogueContext,
        player_input: str,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> tuple[DialogueContext, DialogueResponse]:
        npc_turn_count = sum(1 for m in ctx.messages if m.role == "npc")
        if npc_turn_count >= MAX_TURNS:
            response = DialogueResponse(
                text="我觉得我们已经聊了很多了，请让我休息一下。",
                trust_delta=0,
                mood="疲惫",
                wants_to_end=True,
            )
            return ctx, response

        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == ctx.npc_id
        )

        active_skills_text = memory_ctx.active_skills_text if memory_ctx is not None else ""
        system_prompt = build_dialogue_prompt(
            ctx, location.name, history_summaries, active_skills_text=active_skills_text
        )

        llm_messages = [
            {
                "role": "user" if m.role == "player" else "assistant",
                "content": m.content,
            }
            for m in ctx.messages
        ]
        llm_messages.append({"role": "user", "content": player_input})

        response = await self._llm.generate_dialogue(system_prompt, llm_messages)

        player_msg = Message(
            role="player", content=player_input, trust_delta=0, turn=state.turn
        )
        npc_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        new_trust = ctx.trust + response.trust_delta
        new_ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=new_trust,
            tone=resolve_tone(new_trust),
            messages=ctx.messages + (player_msg, npc_msg),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = new_ctx
        return new_ctx, response
```

- [ ] **Step 4: Run all dialogue tests**

```bash
python -m pytest tests/dialogue/ -v
```
Expected: All tests PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/tavern/dialogue/manager.py tests/dialogue/test_manager.py
git commit -m "feat: add memory_ctx param to DialogueManager.start and respond"
```

---

## Task 8: GameApp wiring (app.py + CLI tests)

**Files:**
- Modify: `src/tavern/cli/app.py` (+~20 lines)
- Create: `tests/cli/test_app_memory.py` (~60 lines)

- [ ] **Step 1: Create `tests/cli/test_app_memory.py` with failing tests**

```python
# tests/cli/test_app_memory.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path

from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionResult, Character, CharacterRole, Location,
)
from tavern.world.state import StateDiff, WorldState


@pytest.fixture
def minimal_state():
    return WorldState(
        turn=0,
        player_id="player",
        locations={
            "hall": Location(id="hall", name="大厅", description="大厅", npcs=("traveler",)),
        },
        characters={
            "player": Character(
                id="player", name="冒险者", role=CharacterRole.PLAYER,
                stats={"hp": 100}, location_id="hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者", role=CharacterRole.NPC,
                stats={"trust": 10}, location_id="hall",
            ),
        },
        items={},
    )


@pytest.fixture
def mock_memory(minimal_state):
    from tavern.world.memory import MemoryContext, MemorySystem
    mem = MagicMock(spec=MemorySystem)
    mem.build_context.return_value = MemoryContext(
        recent_events="进入酒馆",
        relationship_summary="traveler对player信任10",
        active_skills_text="",
    )
    mem.apply_diff = MagicMock()
    return mem


class TestGameAppMemoryInit:
    def test_memory_system_initialized_on_startup(self, tmp_path, minimal_state):
        from tavern.world.memory import MemorySystem
        with (
            patch("tavern.cli.app.load_scenario", return_value=minimal_state),
            patch("tavern.cli.app.LLMRegistry"),
            patch("tavern.cli.app.LLMService"),
            patch("tavern.cli.app.IntentParser"),
            patch("tavern.cli.app.DialogueManager"),
            patch("tavern.cli.app.Narrator"),
        ):
            from tavern.cli.app import GameApp
            app = GameApp(config_path=str(tmp_path / "nonexistent.yaml"))
            assert hasattr(app, "_memory")
            assert isinstance(app._memory, MemorySystem)


class TestGameAppApplyDiffAfterCommit:
    def test_apply_diff_called_after_free_input_commit(self, minimal_state, mock_memory):
        """apply_diff is called after state_manager.commit() in _handle_free_input."""
        from tavern.world.memory import MemorySystem
        with (
            patch("tavern.cli.app.load_scenario", return_value=minimal_state),
            patch("tavern.cli.app.LLMRegistry"),
            patch("tavern.cli.app.LLMService"),
            patch("tavern.cli.app.IntentParser"),
            patch("tavern.cli.app.DialogueManager"),
            patch("tavern.cli.app.Narrator"),
        ):
            from tavern.cli.app import GameApp
            import asyncio
            app = GameApp(config_path="")
            app._memory = mock_memory

            success_result = ActionResult(
                success=True, action=ActionType.MOVE,
                message="你走进了吧台区。", target=None,
            )
            diff = StateDiff(turn_increment=1)

            app._rules = MagicMock()
            app._rules.validate.return_value = (success_result, diff)
            app._parser = MagicMock()
            app._parser.parse = AsyncMock(
                return_value=MagicMock(
                    action=ActionType.MOVE, target=None,
                    model_dump_json=MagicMock(return_value="{}"),
                )
            )
            app._narrator = MagicMock()
            app._narrator.stream_narrative = MagicMock(return_value=iter([]))
            app._renderer = MagicMock()
            app._renderer.render_stream = AsyncMock()
            app._dialogue_manager = MagicMock()
            app._dialogue_manager.is_active = False

            asyncio.get_event_loop().run_until_complete(
                app._handle_free_input("向北走")
            )
            mock_memory.apply_diff.assert_called_once()

    def test_apply_diff_called_after_dialogue_end(self, minimal_state, mock_memory):
        """apply_diff is called after both commits in _apply_dialogue_end."""
        with (
            patch("tavern.cli.app.load_scenario", return_value=minimal_state),
            patch("tavern.cli.app.LLMRegistry"),
            patch("tavern.cli.app.LLMService"),
            patch("tavern.cli.app.IntentParser"),
            patch("tavern.cli.app.DialogueManager"),
            patch("tavern.cli.app.Narrator"),
        ):
            from tavern.cli.app import GameApp
            from tavern.dialogue.context import DialogueSummary
            app = GameApp(config_path="")
            app._memory = mock_memory
            app._renderer = MagicMock()

            summary = DialogueSummary(
                npc_id="traveler",
                summary_text="进行了友好交谈。",
                total_trust_delta=5,
                key_info=("北方有宝藏",),
                turns_count=3,
            )
            app._apply_dialogue_end(summary)
            # Two commits happen in _apply_dialogue_end: trust + event
            assert mock_memory.apply_diff.call_count == 2


class TestGameAppBuildContextCalled:
    def test_build_context_called_in_handle_free_input(self, minimal_state, mock_memory):
        with (
            patch("tavern.cli.app.load_scenario", return_value=minimal_state),
            patch("tavern.cli.app.LLMRegistry"),
            patch("tavern.cli.app.LLMService"),
            patch("tavern.cli.app.IntentParser"),
            patch("tavern.cli.app.DialogueManager"),
            patch("tavern.cli.app.Narrator"),
        ):
            from tavern.cli.app import GameApp
            import asyncio
            app = GameApp(config_path="")
            app._memory = mock_memory

            success_result = ActionResult(
                success=True, action=ActionType.MOVE,
                message="你走进了吧台区。", target=None,
            )
            diff = StateDiff(turn_increment=1)

            app._rules = MagicMock()
            app._rules.validate.return_value = (success_result, diff)
            app._parser = MagicMock()
            app._parser.parse = AsyncMock(
                return_value=MagicMock(
                    action=ActionType.MOVE, target=None,
                    model_dump_json=MagicMock(return_value="{}"),
                )
            )
            app._narrator = MagicMock()
            app._narrator.stream_narrative = MagicMock(return_value=iter([]))
            app._renderer = MagicMock()
            app._renderer.render_stream = AsyncMock()
            app._dialogue_manager = MagicMock()
            app._dialogue_manager.is_active = False

            asyncio.get_event_loop().run_until_complete(
                app._handle_free_input("向北走")
            )
            mock_memory.build_context.assert_called_once()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/cli/test_app_memory.py -v 2>&1 | head -30
```
Expected: Some tests fail because `_memory` attribute doesn't exist yet.

- [ ] **Step 3: Update `src/tavern/cli/app.py`**

Add import near the top (after existing imports):

```python
from tavern.world.memory import MemorySystem
```

In `GameApp.__init__`, after `self._narrator = Narrator(...)`, add:

```python
        skills_dir = scenario_path / "skills"
        self._memory = MemorySystem(
            state=initial_state,
            skills_dir=skills_dir if skills_dir.exists() else None,
        )
```

In `_handle_free_input`, after `if diff is not None: self._state_manager.commit(diff, result)`, add `apply_diff` call. The full updated section after the commit:

```python
        if diff is not None:
            self._state_manager.commit(diff, result)
            self._memory.apply_diff(diff, self.state)

        if result.success and request.action in (
            ActionType.TALK, ActionType.PERSUADE
        ) and result.target:
            try:
                memory_ctx = self._memory.build_context(
                    actor=result.target,
                    state=self.state,
                    current_topic=result.message,
                )
                ctx, opening_response = await self._dialogue_manager.start(
                    self.state, result.target,
                    is_persuade=(request.action == ActionType.PERSUADE),
                    memory_ctx=memory_ctx,
                )
                self._dialogue_ctx = ctx
                self._renderer.render_dialogue_start(ctx, opening_response)
                self._renderer.render_status_bar(self.state)
                return
            except ValueError as e:
                self._renderer.console.print(f"\n[red]{e}[/]\n")
                return

        if result.success and not self._dialogue_manager.is_active:
            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
                current_topic=result.message,
            )
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx)
            )
        else:
            self._renderer.render_result(result)
        self._renderer.render_status_bar(self.state)
```

In `_process_dialogue_input`, update the `respond` call to pass `memory_ctx`:

```python
        memory_ctx = self._memory.build_context(
            actor=ctx.npc_id,
            state=self.state,
            current_topic=user_input,
        )
        new_ctx, response = await self._dialogue_manager.respond(
            ctx, user_input, self.state, memory_ctx
        )
```

In `_apply_dialogue_end`, update the trust StateDiff to include `relationship_changes` and call `apply_diff` after each commit:

```python
    def _apply_dialogue_end(self, summary) -> None:
        state = self.state
        npc = state.characters.get(summary.npc_id)
        if npc is not None:
            old_trust = int(npc.stats.get("trust", 0))
            new_trust = max(-100, min(100, old_trust + summary.total_trust_delta))
            new_stats = {**dict(npc.stats), "trust": new_trust}
            trust_diff = StateDiff(
                updated_characters={summary.npc_id: {"stats": new_stats}},
                relationship_changes=(
                    {"src": summary.npc_id, "tgt": state.player_id, "delta": summary.total_trust_delta},
                ),
                turn_increment=0,
            )
            self._state_manager.commit(
                trust_diff,
                ActionResult(
                    success=True,
                    action=ActionType.TALK,
                    message=f"与{npc.name}的对话结束",
                    target=summary.npc_id,
                ),
            )
            self._memory.apply_diff(trust_diff, self.state)
        else:
            logger.warning(
                "_apply_dialogue_end: NPC %s not found in state, skipping trust update",
                summary.npc_id,
            )

        event = Event(
            id=f"dialogue_{summary.npc_id}_{uuid.uuid4().hex[:8]}",
            turn=self.state.turn,
            type="dialogue_summary",
            actor=summary.npc_id,
            description=summary.summary_text,
            consequences=summary.key_info,
        )
        event_diff = StateDiff(new_events=(event,), turn_increment=0)
        self._state_manager.commit(
            event_diff,
            ActionResult(
                success=True,
                action=ActionType.TALK,
                message="对话摘要已记录",
                target=summary.npc_id,
            ),
        )
        self._memory.apply_diff(event_diff, self.state)
```

- [ ] **Step 4: Run CLI memory tests**

```bash
python -m pytest tests/cli/test_app_memory.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest --tb=short -q
```
Expected: All tests PASS, no regressions.

- [ ] **Step 6: Check coverage**

```bash
python -m pytest --cov=src/tavern --cov-report=term-missing --cov-fail-under=80 -q
```
Expected: `world/memory.py` ≥ 85%, `world/skills.py` ≥ 85%, overall ≥ 80%.

- [ ] **Step 7: Commit**

```bash
git add src/tavern/cli/app.py tests/cli/test_app_memory.py
git commit -m "feat: wire MemorySystem into GameApp — build_context, apply_diff, memory_ctx passthrough"
```
