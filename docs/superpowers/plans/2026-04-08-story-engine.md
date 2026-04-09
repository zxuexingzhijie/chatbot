# StoryEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为酒馆 CLI 游戏添加 YAML 驱动的剧情节点引擎，支持 DAG 前置依赖、passive/continue 双触发模式，以及超时 Fail Forward 提示机制。

**Architecture:** StoryEngine 是无状态服务，节点定义从 story.yaml 加载，运行时状态（story_active_since）存入 WorldState/StateDiff。条件评估通过 CONDITION_REGISTRY 注册制实现，支持 location/inventory/relationship/event/quest 五种类型。GameApp 在每次行动后执行 passive 检查，并通过 `continue` 命令支持玩家主动推进。

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML, pytest, dataclasses

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/tavern/engine/story_conditions.py` | CONDITION_REGISTRY + 五种内置条件 evaluator |
| 新建 | `src/tavern/engine/story.py` | 数据类 + StoryEngine 主逻辑 |
| 修改 | `src/tavern/world/state.py` | WorldState 加 story_active_since，StateDiff 加 story_active_since_updates，apply() 合并逻辑 |
| 新建 | `data/scenarios/tavern/story.yaml` | 两个示例节点（cellar_mystery_discovered / cellar_secret_revealed） |
| 修改 | `src/tavern/narrator/narrator.py` | stream_narrative 增加 story_hint: str \| None 参数并注入 prompt |
| 修改 | `src/tavern/narrator/prompts.py` | build_narrative_prompt 增加 story_hint: str \| None 参数 |
| 修改 | `src/tavern/cli/app.py` | 初始化 StoryEngine，wiring passive check / continue 命令 / _apply_story_results / _update_story_active_since |
| 新建 | `tests/engine/test_story_conditions.py` | ConditionRegistry 测试（6 个） |
| 新建 | `tests/engine/test_story.py` | StoryEngine 单元测试（15 个） |
| 新建 | `tests/cli/test_app_story.py` | GameApp 集成测试（5 个） |

---

### Task 1: story_conditions.py — CONDITION_REGISTRY

**Files:**
- Create: `src/tavern/engine/story_conditions.py`
- Create: `tests/engine/__init__.py`
- Create: `tests/engine/test_story_conditions.py`

- [ ] **Step 1: 创建 tests/engine/__init__.py**

```python
# empty
```

- [ ] **Step 2: 写 6 个失败测试**

创建 `tests/engine/test_story_conditions.py`：

```python
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from tavern.world.skills import ActivationCondition


def _make_state(player_location="tavern", inventory=()):
    state = MagicMock()
    state.player_id = "player"
    state.characters = {
        "player": MagicMock(location_id=player_location, inventory=inventory)
    }
    return state


def _make_timeline(event_ids=()):
    tl = MagicMock()
    tl.has = lambda eid: eid in event_ids
    return tl


def _make_relationships(value=0):
    rel = MagicMock()
    rel.value = value
    rg = MagicMock()
    rg.get = lambda src, tgt: rel
    return rg


def test_location_condition_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="location", value=30)  # value field is int in dataclass
    # We'll use a string-valued cond by creating it with custom fields
    # ActivationCondition doesn't have a 'location_value' field, so we use event_id for string storage
    # Actually location uses cond.event_id for the location string
    cond = ActivationCondition(type="location", event_id="cellar")
    state = _make_state(player_location="cellar")
    result = CONDITION_REGISTRY["location"](cond, state, None, None)
    assert result is True


def test_location_condition_no_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="location", event_id="cellar")
    state = _make_state(player_location="tavern")
    result = CONDITION_REGISTRY["location"](cond, state, None, None)
    assert result is False


def test_inventory_condition_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="inventory", event_id="rusty_key")
    state = _make_state(inventory=("rusty_key", "torch"))
    result = CONDITION_REGISTRY["inventory"](cond, state, None, None)
    assert result is True


def test_relationship_condition():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(
        type="relationship",
        source="player", target="bartender_grim",
        attribute="trust", operator=">=", value=30,
    )
    relationships = _make_relationships(value=35)
    result = CONDITION_REGISTRY["relationship"](cond, None, None, relationships)
    assert result is True


def test_event_condition_exists():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="event", event_id="cellar_entered", check="exists")
    timeline = _make_timeline(event_ids=("cellar_entered",))
    result = CONDITION_REGISTRY["event"](cond, None, timeline, None)
    assert result is True


def test_quest_condition():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="quest", event_id="cellar_mystery", check="discovered")
    state = MagicMock()
    state.quests = {"cellar_mystery": {"status": "discovered"}}
    result = CONDITION_REGISTRY["quest"](cond, state, None, None)
    assert result is True
```

- [ ] **Step 3: 运行确认失败**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/engine/test_story_conditions.py -v 2>&1 | head -30
```

期望：`ModuleNotFoundError: No module named 'tavern.engine.story_conditions'`

- [ ] **Step 4: 创建 `src/tavern/engine/story_conditions.py`**

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from tavern.world.skills import ActivationCondition, ConditionEvaluator

if TYPE_CHECKING:
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

ConditionEvaluatorFn = Callable[
    [ActivationCondition, "WorldState", "EventTimeline", "RelationshipGraph"],
    bool,
]

CONDITION_REGISTRY: dict[str, ConditionEvaluatorFn] = {}


def register_condition(type_name: str):
    def decorator(fn: ConditionEvaluatorFn) -> ConditionEvaluatorFn:
        CONDITION_REGISTRY[type_name] = fn
        return fn
    return decorator


@register_condition("location")
def eval_location(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    player = state.characters.get(state.player_id)
    if player is None:
        return False
    return player.location_id == cond.event_id


@register_condition("inventory")
def eval_inventory(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    player = state.characters.get(state.player_id)
    if player is None:
        return False
    return cond.event_id in player.inventory


@register_condition("relationship")
def eval_relationship(cond: ActivationCondition, state, timeline, relationships: "RelationshipGraph") -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


@register_condition("event")
def eval_event(cond: ActivationCondition, state, timeline: "EventTimeline", relationships) -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


@register_condition("quest")
def eval_quest(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)
```

- [ ] **Step 5: 运行确认通过**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/engine/test_story_conditions.py -v
```

期望：6 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/engine/story_conditions.py tests/engine/__init__.py tests/engine/test_story_conditions.py && git commit -m "feat: add CONDITION_REGISTRY with location/inventory/relationship/event/quest evaluators"
```

---

### Task 2: WorldState / StateDiff — story_active_since 扩展

**Files:**
- Modify: `src/tavern/world/state.py`
- Modify: `tests/world/test_state.py` (如果存在则追加，否则新建)

- [ ] **Step 1: 找到现有 state 测试文件**

```bash
ls /Users/makoto/Downloads/work/chatbot/tests/world/
```

- [ ] **Step 2: 写 2 个失败测试**

在 `tests/world/test_state.py` 末尾追加（若文件不存在则新建）：

```python
# --- story_active_since tests ---

def test_state_diff_has_story_active_since_updates():
    from tavern.world.state import StateDiff
    diff = StateDiff(story_active_since_updates={"node1": 5})
    assert diff.story_active_since_updates == {"node1": 5}


def test_world_state_apply_merges_story_active_since():
    from tavern.world.state import StateDiff, WorldState
    from tavern.world.models import Character, CharacterRole, Location, ActionResult
    from tavern.engine.actions import ActionType
    state = WorldState(
        turn=3,
        player_id="player",
        locations={"room": Location(id="room", name="R", description="d")},
        characters={"player": Character(id="player", name="P", role=CharacterRole.PLAYER, location_id="room")},
        story_active_since={"node_a": 1},
    )
    diff = StateDiff(story_active_since_updates={"node_b": 3}, turn_increment=0)
    result = ActionResult(success=True, action=ActionType.LOOK, message="ok")
    new_state = state.apply(diff, action=result)
    assert new_state.story_active_since == {"node_a": 1, "node_b": 3}
```

- [ ] **Step 3: 运行确认失败**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/world/test_state.py -k "story_active" -v 2>&1 | tail -15
```

期望：2 failed（字段不存在）

- [ ] **Step 4: 修改 `src/tavern/world/state.py`**

在 `StateDiff` 中加新字段（在最后一个字段 `turn_increment` 之前）：

```python
    story_active_since_updates: dict[str, int] = {}
```

在 `WorldState` 中加新字段（在 `last_action` 之前）：

```python
    story_active_since: dict[str, int] = {}
```

同时在 `freeze_mutable_fields` validator 中，把 `story_active_since` 也加入 `frozen_fields`：

```python
        frozen_fields = {
            "locations": instance.locations,
            "characters": instance.characters,
            "items": instance.items,
            "relationships_snapshot": instance.relationships_snapshot,
            "quests": instance.quests,
            "story_active_since": instance.story_active_since,
        }
```

在 `WorldState.apply()` 中，在 `return WorldState(...)` 之前加：

```python
        new_story_active_since = {
            **dict(self.story_active_since),
            **diff.story_active_since_updates,
        }
```

并在 `return WorldState(...)` 调用中加参数：

```python
            story_active_since=new_story_active_since,
```

- [ ] **Step 5: 运行确认通过**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/world/test_state.py -v
```

期望：全部通过

- [ ] **Step 6: 运行全量测试确保没有回归**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest --tb=short -q 2>&1 | tail -10
```

期望：全部通过

- [ ] **Step 7: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/world/state.py tests/world/test_state.py && git commit -m "feat: add story_active_since to WorldState and StateDiff"
```

---

### Task 3: story.py — 数据类 + StoryEngine

**Files:**
- Create: `src/tavern/engine/story.py`
- Create: `tests/engine/test_story.py`

- [ ] **Step 1: 写 15 个失败测试**

创建 `tests/engine/test_story.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/engine/test_story.py -v 2>&1 | head -30
```

期望：`ModuleNotFoundError: No module named 'tavern.engine.story'`

- [ ] **Step 3: 创建 `src/tavern/engine/story.py`**

```python
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import yaml

from tavern.world.models import ActionResult, Event
from tavern.world.skills import ActivationCondition
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from pathlib import Path
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

TriggerMode = Literal["passive", "continue", "both"]


@dataclass(frozen=True)
class HintEvent:
    description: str
    actor: str


@dataclass(frozen=True)
class FailForward:
    after_turns: int
    hint_event: HintEvent


@dataclass(frozen=True)
class NewEventSpec:
    id: str
    type: str
    description: str
    actor: str | None = None  # None → defaults to player_id at build time


@dataclass(frozen=True)
class StoryEffects:
    quest_updates: dict[str, dict]
    new_events: tuple[NewEventSpec, ...]


@dataclass(frozen=True)
class StoryNode:
    id: str
    act: str
    requires: tuple[str, ...]
    repeatable: bool
    trigger_mode: TriggerMode
    conditions: tuple[ActivationCondition, ...]
    effects: StoryEffects
    narrator_hint: str | None
    fail_forward: FailForward | None


@dataclass(frozen=True)
class StoryResult:
    node_id: str
    diff: StateDiff
    narrator_hint: str | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mode_matches(node_mode: TriggerMode, trigger: TriggerMode) -> bool:
    return node_mode == "both" or node_mode == trigger


def _all_conditions_met(
    node: StoryNode,
    state: "WorldState",
    timeline: "EventTimeline",
    relationships: "RelationshipGraph",
) -> bool:
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    for cond in node.conditions:
        evaluator = CONDITION_REGISTRY.get(cond.type)
        if evaluator is None:
            logger.warning("StoryEngine: unknown condition type %r — node %s skipped", cond.type, node.id)
            return False
        if not evaluator(cond, state, timeline, relationships):
            return False
    return True


def _build_result(node: StoryNode, state: "WorldState") -> StoryResult:
    events = tuple(
        Event(
            id=e.id,
            turn=state.turn,
            type=e.type,
            actor=e.actor if e.actor is not None else state.player_id,
            description=e.description,
        )
        for e in node.effects.new_events
    )
    quest_updates = {
        **node.effects.quest_updates,
        node.id: {"_story_status": "completed"},
    }
    diff = StateDiff(new_events=events, quest_updates=quest_updates, turn_increment=0)
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=node.narrator_hint)


def _build_hint_result(node: StoryNode, state: "WorldState") -> StoryResult:
    ff = node.fail_forward
    assert ff is not None
    hint_event = Event(
        id=f"hint_{node.id}_{uuid.uuid4().hex[:6]}",
        turn=state.turn,
        type="hint",
        actor=ff.hint_event.actor,
        description=ff.hint_event.description,
    )
    diff = StateDiff(
        new_events=(hint_event,),
        story_active_since_updates={node.id: state.turn},
        turn_increment=0,
    )
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=None)


# ---------------------------------------------------------------------------
# StoryEngine
# ---------------------------------------------------------------------------

class StoryEngine:
    def __init__(self, nodes: dict[str, StoryNode]) -> None:
        self._nodes = nodes

    def get_active_nodes(self, state: "WorldState") -> set[str]:
        completed = {
            nid
            for nid, q in state.quests.items()
            if q.get("_story_status") == "completed"
        }
        return {
            nid
            for nid, node in self._nodes.items()
            if (nid not in completed or node.repeatable)
            and all(r in completed for r in node.requires)
        }

    def check(
        self,
        state: "WorldState",
        trigger_mode: TriggerMode,
        timeline: "EventTimeline",
        relationships: "RelationshipGraph",
    ) -> list[StoryResult]:
        active = self.get_active_nodes(state)
        results = []
        for nid in active:
            node = self._nodes[nid]
            if not _mode_matches(node.trigger_mode, trigger_mode):
                continue
            if _all_conditions_met(node, state, timeline, relationships):
                results.append(_build_result(node, state))
        return results

    def check_fail_forward(self, state: "WorldState") -> list[StoryResult]:
        active = self.get_active_nodes(state)
        results = []
        for nid in active:
            node = self._nodes[nid]
            if node.fail_forward is None:
                continue
            since = state.story_active_since.get(nid)
            if since is None:
                continue
            if state.turn - since >= node.fail_forward.after_turns:
                results.append(_build_hint_result(node, state))
        return results


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def load_story_nodes(path: "Path") -> dict[str, StoryNode]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    nodes: dict[str, StoryNode] = {}
    for entry in raw.get("nodes", []):
        try:
            trigger = entry.get("trigger", {})
            conditions = tuple(
                ActivationCondition(**c) for c in (trigger.get("conditions") or [])
            )
            effects_raw = entry.get("effects", {})
            new_events = tuple(
                NewEventSpec(**e) for e in (effects_raw.get("new_events") or [])
            )
            effects = StoryEffects(
                quest_updates=dict(effects_raw.get("quest_updates") or {}),
                new_events=new_events,
            )
            ff_raw = entry.get("fail_forward")
            fail_forward = None
            if ff_raw:
                hint_raw = ff_raw["hint_event"]
                fail_forward = FailForward(
                    after_turns=int(ff_raw["after_turns"]),
                    hint_event=HintEvent(
                        description=hint_raw["description"],
                        actor=hint_raw["actor"],
                    ),
                )
            node = StoryNode(
                id=entry["id"],
                act=entry.get("act", "act1"),
                requires=tuple(entry.get("requires") or []),
                repeatable=bool(entry.get("repeatable", False)),
                trigger_mode=trigger.get("mode", "passive"),
                conditions=conditions,
                effects=effects,
                narrator_hint=entry.get("narrator_hint"),
                fail_forward=fail_forward,
            )
            nodes[node.id] = node
        except Exception as exc:
            logger.warning("load_story_nodes: failed to parse node %r: %s", entry.get("id"), exc)
    return nodes
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/engine/test_story.py -v
```

期望：15 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/engine/story.py tests/engine/test_story.py && git commit -m "feat: add StoryEngine with DAG active-set, check/check_fail_forward, YAML loader"
```

---

### Task 4: story.yaml — 示例节点

**Files:**
- Create: `data/scenarios/tavern/story.yaml`

- [ ] **Step 1: 创建示例 story.yaml**

```yaml
# data/scenarios/tavern/story.yaml
nodes:
  - id: cellar_mystery_discovered
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: location
          event_id: cellar

    fail_forward:
      after_turns: 8
      hint_event:
        description: "格里姆擦拭杯子时无意间说道：地下室里的东西，不是一般人能碰的……"
        actor: bartender_grim

    effects:
      quest_updates:
        cellar_mystery: { status: discovered }
      new_events:
        - id: cellar_entered
          type: story
          description: "玩家首次进入地下室，发现异常划痕"

    narrator_hint: "氛围阴森，引导玩家注意地面划痕和旧木桶，暗示有秘密。"

  - id: cellar_secret_revealed
    act: act1
    requires: [cellar_mystery_discovered]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: relationship
          source: player
          target: bartender_grim
          attribute: trust
          operator: ">="
          value: 30
        - type: event
          event_id: cellar_entered
          check: exists

    fail_forward:
      after_turns: 15
      hint_event:
        description: "深夜，你隐约听到地下室传来拖拽重物的声音。"
        actor: bartender_grim

    effects:
      quest_updates:
        cellar_mystery: { status: revealed }
      new_events:
        - id: secret_learned
          type: story
          description: "玩家得知地下室密道的存在"

    narrator_hint: "格里姆终于开口，压低声音提及密道，措辞谨慎。"
```

- [ ] **Step 2: 验证 YAML 可被 load_story_nodes 解析**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -c "
from pathlib import Path
from tavern.engine.story import load_story_nodes
nodes = load_story_nodes(Path('data/scenarios/tavern/story.yaml'))
print('Loaded nodes:', list(nodes.keys()))
assert 'cellar_mystery_discovered' in nodes
assert 'cellar_secret_revealed' in nodes
print('OK')
"
```

期望：`Loaded nodes: ['cellar_mystery_discovered', 'cellar_secret_revealed']` + `OK`

- [ ] **Step 3: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add data/scenarios/tavern/story.yaml && git commit -m "feat: add story.yaml with cellar mystery arc nodes"
```

---

### Task 5: Narrator — story_hint 参数

**Files:**
- Modify: `src/tavern/narrator/prompts.py`
- Modify: `src/tavern/narrator/narrator.py`

- [ ] **Step 1: 写 2 个失败测试**

在 `tests/` 中找到叙事测试文件：

```bash
ls /Users/makoto/Downloads/work/chatbot/tests/llm/
```

在 `tests/llm/test_service_narrative.py` 末尾追加（或新建）：

```python
# --- story_hint tests ---

def test_build_narrative_prompt_with_story_hint():
    from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt
    ctx = NarrativeContext(
        action_type="move",
        action_message="你走进了地下室",
        location_name="地下室",
        location_desc="昏暗潮湿",
        player_name="冒险者",
        target=None,
    )
    messages = build_narrative_prompt(ctx, memory_ctx=None, story_hint="氛围阴森，注意地面划痕。")
    system_content = messages[0]["content"]
    assert "氛围阴森" in system_content
    assert "story_hint" not in system_content  # 不要暴露参数名本身


def test_build_narrative_prompt_no_hint_no_section():
    from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt
    ctx = NarrativeContext(
        action_type="look",
        action_message="你环顾四周",
        location_name="酒馆",
        location_desc="嘈杂",
        player_name="冒险者",
        target=None,
    )
    messages = build_narrative_prompt(ctx, memory_ctx=None, story_hint=None)
    system_content = messages[0]["content"]
    assert "【剧情提示】" not in system_content
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/llm/test_service_narrative.py -k "story_hint" -v 2>&1 | tail -15
```

期望：2 failed（`build_narrative_prompt` 不接受 `story_hint` 参数）

- [ ] **Step 3: 修改 `src/tavern/narrator/prompts.py`**

修改 `build_narrative_prompt` 签名，加 `story_hint: str | None = None` 参数，并在 `system_content` 末尾追加：

```python
def build_narrative_prompt(
    ctx: NarrativeContext,
    memory_ctx: MemoryContext | None = None,
    story_hint: str | None = None,
) -> list[dict[str, str]]:
    system_style = NARRATIVE_TEMPLATES.get(ctx.action_type, NARRATIVE_TEMPLATES["_default"])

    system_content = (
        f"{system_style}\n\n"
        f"当前地点：{ctx.location_name}——{ctx.location_desc}\n"
        f"玩家角色名：{ctx.player_name}"
    )

    if memory_ctx is not None:
        system_content += f"\n\n【近期历史】\n{memory_ctx.recent_events}"
        system_content += f"\n\n【关系状态】\n{memory_ctx.relationship_summary}"

    if story_hint is not None:
        system_content += f"\n\n【剧情提示】\n{story_hint}"

    user_parts = [ctx.action_message]
    if ctx.target:
        user_parts.append(f"（涉及对象：{ctx.target}）")
    user_content = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
```

- [ ] **Step 4: 修改 `src/tavern/narrator/narrator.py`**

修改 `stream_narrative` 签名，加 `story_hint: str | None = None`，并传给 `build_narrative_prompt`：

```python
    async def stream_narrative(
        self,
        result: ActionResult,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
        story_hint: str | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            ctx = self._build_context(result, state)
            messages = build_narrative_prompt(ctx, memory_ctx, story_hint=story_hint)
            system_prompt = messages[0]["content"]
            action_message = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, action_message):
                yield chunk
        except Exception:
            yield result.message
```

- [ ] **Step 5: 运行确认通过**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/llm/test_service_narrative.py -v
```

期望：全部通过

- [ ] **Step 6: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/narrator/prompts.py src/tavern/narrator/narrator.py tests/llm/test_service_narrative.py && git commit -m "feat: add story_hint param to Narrator.stream_narrative and build_narrative_prompt"
```

---

### Task 6: GameApp 集成 — StoryEngine wiring

**Files:**
- Modify: `src/tavern/cli/app.py`
- Create: `tests/cli/test_app_story.py`

- [ ] **Step 1: 写 5 个失败测试**

创建 `tests/cli/test_app_story.py`：

```python
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

    asyncio.get_event_loop().run_until_complete(app._handle_free_input("go cellar"))

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

    app._handle_system_command("continue")

    app._story_engine.check.assert_called_once()
    call_args = app._story_engine.check.call_args
    assert call_args[0][1] == "continue"


def test_continue_no_results_prints_message():
    app, state = _make_app()
    app._story_engine.check = MagicMock(return_value=[])
    app._handle_system_command("continue")
    app._renderer.console.print.assert_called()
    printed = app._renderer.console.print.call_args[0][0]
    assert "没有新的剧情" in printed


def test_apply_story_results_commits_diff():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint=None)]
    asyncio.get_event_loop().run_until_complete(app._apply_story_results(results))
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
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_app_story.py -v 2>&1 | tail -20
```

期望：全部失败（`GameApp` 没有 `_story_engine` / `_pending_story_hints` / `_apply_story_results` / `_update_story_active_since`）

- [ ] **Step 3: 修改 `src/tavern/cli/app.py`**

**3a. 顶部 imports 区：**

在 `from tavern.world.state import ...` 这行之后加：

```python
from tavern.engine.story import StoryEngine, StoryResult, load_story_nodes
```

**3b. `__init__` 末尾（在 `self._show_intent` 之前）加：**

```python
        story_path = scenario_path / "story.yaml"
        self._story_engine = StoryEngine(
            load_story_nodes(story_path) if story_path.exists() else {}
        )
        self._pending_story_hints: list[str] = []
```

**3c. `SYSTEM_COMMANDS` 集合中加 `"continue"`：**

```python
SYSTEM_COMMANDS = {"look", "inventory", "status", "hint", "undo", "help", "quit", "save", "load", "saves", "continue"}
```

**3d. `_handle_system_command` 中在 `elif command == "help":` 之前加新分支：**

```python
        elif command == "continue":
            story_results = self._story_engine.check(
                self.state, "continue",
                self._memory._timeline, self._memory._relationship_graph,
            )
            if not story_results:
                self._renderer.console.print("\n[dim]目前没有新的剧情推进。[/]\n")
            else:
                asyncio.get_event_loop().run_until_complete(self._apply_story_results(story_results))
            self._update_story_active_since()
```

**3e. `_handle_free_input` 中，在 `if result.success and not self._dialogue_manager.is_active:` 块的 `await self._renderer.render_stream(...)` 调用前，加 story 检查逻辑：**

找到这段代码：
```python
        if result.success and not self._dialogue_manager.is_active:
            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
            )
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx)
            )
```

替换为：
```python
        if result.success and not self._dialogue_manager.is_active:
            story_results = self._story_engine.check(
                self.state, "passive",
                self._memory._timeline, self._memory._relationship_graph,
            )
            story_results += self._story_engine.check_fail_forward(self.state)
            await self._apply_story_results(story_results)
            self._update_story_active_since()

            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
            )
            combined_hint = "\n".join(self._pending_story_hints) or None
            self._pending_story_hints.clear()
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint)
            )
```

**3f. 在 `_apply_dialogue_end` 之后加两个新方法：**

```python
    async def _apply_story_results(self, results: list[StoryResult]) -> None:
        from tavern.engine.actions import ActionType
        for r in results:
            self._state_manager.commit(
                r.diff,
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message=f"剧情节点触发：{r.node_id}",
                ),
            )
            self._memory.apply_diff(r.diff, self.state)
            if r.narrator_hint:
                self._pending_story_hints.append(r.narrator_hint)

    def _update_story_active_since(self) -> None:
        from tavern.engine.actions import ActionType
        new_active = self._story_engine.get_active_nodes(self.state)
        since_updates = {
            nid: self.state.turn
            for nid in new_active
            if nid not in self.state.story_active_since
        }
        if since_updates:
            self._state_manager.commit(
                StateDiff(story_active_since_updates=since_updates, turn_increment=0),
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message="故事进度更新",
                ),
            )
```

- [ ] **Step 4: 检查 ActionType.CUSTOM 是否存在**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -c "from tavern.engine.actions import ActionType; print(ActionType.CUSTOM)"
```

如果不存在，找到 `src/tavern/engine/actions.py` 并追加 `CUSTOM = "custom"`。

- [ ] **Step 5: 运行确认测试通过**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_app_story.py -v
```

期望：5 passed

- [ ] **Step 6: 运行全量测试**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest --tb=short -q 2>&1 | tail -15
```

期望：全部通过

- [ ] **Step 7: 提交**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/cli/app.py tests/cli/test_app_story.py && git commit -m "feat: wire StoryEngine into GameApp — passive check, continue command, _apply_story_results, _update_story_active_since"
```

---

### Task 7: 全量验证与收尾

**Files:**
- 无新文件

- [ ] **Step 1: 运行全量测试**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest -v 2>&1 | tail -30
```

期望：全部通过（≥ 228 + 新增约 28 = ~256 个测试）

- [ ] **Step 2: 检查测试覆盖率（可选）**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest --cov=src/tavern/engine/story --cov=src/tavern/engine/story_conditions --cov-report=term-missing -q 2>&1 | tail -20
```

期望：story.py 和 story_conditions.py 覆盖率 ≥ 80%

- [ ] **Step 3: 验证 story.yaml 完整加载**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -c "
from pathlib import Path
from tavern.engine.story import load_story_nodes
nodes = load_story_nodes(Path('data/scenarios/tavern/story.yaml'))
for nid, n in nodes.items():
    print(f'{nid}: requires={n.requires}, mode={n.trigger_mode}, ff={n.fail_forward is not None}')
"
```

- [ ] **Step 4: 提交（如有遗漏文件）**

```bash
cd /Users/makoto/Downloads/work/chatbot && git status
```

如有未提交，逐一 `git add` + `git commit`。

---

## 自检：Spec Coverage

| Spec 要求 | 对应 Task |
|-----------|-----------|
| `CONDITION_REGISTRY` 注册制，5 种条件 | Task 1 |
| `story_active_since` 加入 WorldState | Task 2 |
| `story_active_since_updates` 加入 StateDiff | Task 2 |
| `WorldState.apply()` 合并 | Task 2 |
| `StoryNode`, `StoryEffects`, `StoryResult`, `HintEvent`, `FailForward`, `NewEventSpec` 数据类 | Task 3 |
| `StoryEngine.get_active_nodes()` DAG + repeatable | Task 3 |
| `StoryEngine.check()` 触发模式过滤 + 条件评估 | Task 3 |
| `StoryEngine.check_fail_forward()` 超时 + 重置 | Task 3 |
| `load_story_nodes()` YAML 加载 | Task 3 |
| `data/scenarios/tavern/story.yaml` 示例 | Task 4 |
| `Narrator.stream_narrative(story_hint=...)` | Task 5 |
| `build_narrative_prompt(story_hint=...)` | Task 5 |
| `GameApp.__init__` 初始化 StoryEngine | Task 6 |
| `GameApp._handle_free_input` passive 检查 | Task 6 |
| `GameApp._handle_system_command("continue")` | Task 6 |
| `GameApp._apply_story_results()` | Task 6 |
| `GameApp._update_story_active_since()` 无条件调用 | Task 6 |
| `_pending_story_hints: list[str]` 合并注入 | Task 6 |
| tests/engine/test_story_conditions.py (6) | Task 1 |
| tests/engine/test_story.py (15) | Task 3 |
| tests/cli/test_app_story.py (5) | Task 6 |
