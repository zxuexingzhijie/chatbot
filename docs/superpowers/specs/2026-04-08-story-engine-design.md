# 剧情节点引擎（StoryEngine）— Phase 3b 设计规格

**日期**: 2026-04-08
**状态**: 已批准
**范围**: StoryEngine + story.yaml + WorldState 扩展 + GameApp 集成（passive/continue 触发 + Fail Forward）

---

## 1. 概述

为酒馆 CLI 游戏添加剧情节点引擎，支持 YAML 定义的故事节点、DAG 前置依赖过滤、被动检查与主动推进两种触发方式，以及超时 Fail Forward 提示机制。

### 设计目标

- `StoryEngine`：无状态服务，节点定义从 YAML 加载，运行时状态全部存入 `WorldState`
- DAG 前置依赖：`requires` 字段，活跃集过滤（O(活跃节点) 而非 O(全量)）
- 触发模式：`passive`（每次行动后自动检查）、`continue`（玩家主动推进）、`both`
- 效果：`effects`（直接修改状态）+ `narrator_hint`（指导 LLM 叙事，可为 None）
- 节点状态：`repeatable: false`（默认一次性）或 `true`（可重复触发）
- Fail Forward：超时触发 hint 事件（NPC 主动搭话 / 环境异动），重置计时，不强制完成节点
- 条件类型注册制：`CONDITION_REGISTRY`，替代 if-else，支持扩展

---

## 2. 架构

### 2.1 数据流

```
每次行动后（_handle_free_input）:
  StoryEngine.check(state, "passive", timeline, relationships)
  + StoryEngine.check_fail_forward(state)
  → list[StoryResult]
  → _apply_story_results(results)
      → 每个 result: commit(diff), memory.apply_diff
      → 收集 narrator_hints 到 _pending_story_hints: list[str]
      → 循环后一次性 commit story_active_since_updates

continue 命令:
  StoryEngine.check(state, "continue", ...)
  → 同上
```

### 2.2 模块结构

```
src/tavern/
├── engine/
│   ├── story.py              # StoryNode, StoryEffects, StoryResult, StoryEngine
│   └── story_conditions.py  # CONDITION_REGISTRY + 内置条件 evaluator

data/scenarios/tavern/
└── story.yaml                # 节点定义

tests/engine/
├── test_story.py             # StoryEngine 单元测试（~15 个）
└── test_story_conditions.py  # ConditionRegistry 测试（~6 个）

tests/cli/
└── test_app_story.py         # GameApp 集成测试（~5 个）
```

---

## 3. 数据模型

### 3.1 Python 数据类

```python
from typing import Literal
from dataclasses import dataclass
from tavern.world.skills import ActivationCondition  # 复用

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
    actor: str | None = None  # None → 默认 player_id

@dataclass(frozen=True)
class StoryEffects:
    quest_updates: dict[str, dict]          # { quest_id: { key: value } }
    new_events: tuple[NewEventSpec, ...]

@dataclass(frozen=True)
class StoryNode:
    id: str
    act: str
    requires: tuple[str, ...]               # 前置节点 ID（DAG）
    repeatable: bool                        # 默认 False
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
```

### 3.2 YAML 节点格式

```yaml
# data/scenarios/tavern/story.yaml
nodes:
  - id: cellar_mystery_discovered
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive           # passive | continue | both
      conditions:
        - type: location
          value: cellar

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
    requires: [cellar_mystery_discovered]   # 必须先发现异常
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

---

## 4. 核心组件

### 4.1 条件注册制（`engine/story_conditions.py`）

```python
from typing import Callable
from tavern.world.skills import ActivationCondition

ConditionEvaluatorFn = Callable[
    [ActivationCondition, "WorldState", "EventTimeline", "RelationshipGraph"],
    bool
]

CONDITION_REGISTRY: dict[str, ConditionEvaluatorFn] = {}

def register_condition(type_name: str):
    def decorator(fn: ConditionEvaluatorFn) -> ConditionEvaluatorFn:
        CONDITION_REGISTRY[type_name] = fn
        return fn
    return decorator

@register_condition("location")
def eval_location(cond, state, timeline, relationships) -> bool:
    player = state.characters[state.player_id]
    return player.location_id == cond.value

@register_condition("inventory")
def eval_inventory(cond, state, timeline, relationships) -> bool:
    player = state.characters[state.player_id]
    return cond.item in player.inventory

# relationship / event / quest 复用 skills.py ConditionEvaluator 逻辑
@register_condition("relationship")
def eval_relationship(cond, state, timeline, relationships) -> bool: ...

@register_condition("event")
def eval_event(cond, state, timeline, relationships) -> bool: ...

@register_condition("quest")
def eval_quest(cond, state, timeline, relationships) -> bool: ...
```

### 4.2 `StoryEngine`（`engine/story.py`）

```python
class StoryEngine:
    def __init__(self, nodes: dict[str, StoryNode]) -> None:
        self._nodes = nodes

    def get_active_nodes(self, state: WorldState) -> set[str]:
        completed = {
            nid for nid, q in state.quests.items()
            if q.get("_story_status") == "completed"
        }
        return {
            nid for nid, node in self._nodes.items()
            if (nid not in completed or node.repeatable)
            and all(r in completed for r in node.requires)
        }

    def check(
        self,
        state: WorldState,
        trigger_mode: TriggerMode,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
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

    def check_fail_forward(self, state: WorldState) -> list[StoryResult]:
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
```

**辅助函数**：

```python
def _mode_matches(node_mode: TriggerMode, trigger: TriggerMode) -> bool:
    return node_mode == "both" or node_mode == trigger

def _all_conditions_met(node, state, timeline, relationships) -> bool:
    for cond in node.conditions:
        evaluator = CONDITION_REGISTRY.get(cond.type)
        if evaluator is None:
            logger.warning("未知条件类型: %s", cond.type)
            return False
        if not evaluator(cond, state, timeline, relationships):
            return False
    return True

def _build_result(node: StoryNode, state: WorldState) -> StoryResult:
    events = tuple(
        Event(
            id=e.id, turn=state.turn, type=e.type,
            actor=e.actor or state.player_id,
            description=e.description,
        )
        for e in node.effects.new_events
    )
    quest_updates = {
        **node.effects.quest_updates,
        node.id: {"_story_status": "completed"},
    }
    diff = StateDiff(new_events=events, quest_updates=quest_updates)
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=node.narrator_hint)

def _build_hint_result(node: StoryNode, state: WorldState) -> StoryResult:
    ff = node.fail_forward
    hint_event = Event(
        id=f"hint_{node.id}_{uuid.uuid4().hex[:6]}",
        turn=state.turn,
        type="hint",
        actor=ff.hint_event.actor,
        description=ff.hint_event.description,
    )
    diff = StateDiff(
        new_events=(hint_event,),
        story_active_since_updates={node.id: state.turn},  # 重置计时
    )
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=None)
```

---

## 5. WorldState 与 StateDiff 扩展

### 5.1 `WorldState` 新增字段

```python
class WorldState(BaseModel):
    ...
    story_active_since: dict[str, int] = {}  # node_id → 进入活跃集时的 turn
```

参与序列化/存档（Pydantic 自动处理）。

### 5.2 `StateDiff` 新增字段

```python
class StateDiff(BaseModel):
    ...
    story_active_since_updates: dict[str, int] = {}  # node_id → turn
```

`WorldState.apply()` 中合并：

```python
new_story_active_since = {
    **dict(self.story_active_since),
    **diff.story_active_since_updates,
}
```

---

## 6. GameApp 集成

### 6.1 初始化

```python
# __init__ 中
from tavern.engine.story import StoryEngine, load_story_nodes
story_path = scenario_path / "story.yaml"
self._story_engine = StoryEngine(
    load_story_nodes(story_path) if story_path.exists() else {}
)
self._pending_story_hints: list[str] = []
```

### 6.2 被动检查（每次行动后）

`_handle_free_input` 成功行动 commit 后追加：

```python
story_results = self._story_engine.check(
    self.state, "passive",
    self._memory._timeline, self._memory._relationship_graph,
)
story_results += self._story_engine.check_fail_forward(self.state)
await self._apply_story_results(story_results)
```

### 6.3 `continue` 命令

`_handle_system_command` 新增分支：

```python
elif command == "continue":
    story_results = self._story_engine.check(
        self.state, "continue",
        self._memory._timeline, self._memory._relationship_graph,
    )
    if not story_results:
        self._renderer.console.print("\n[dim]目前没有新的剧情推进。[/]\n")
    else:
        await self._apply_story_results(story_results)
```

### 6.4 `_apply_story_results`

```python
async def _apply_story_results(self, results: list[StoryResult]) -> None:
    if not results:
        return
    for r in results:
        self._state_manager.commit(
            r.diff,
            ActionResult(success=True, action=ActionType.CUSTOM,
                         message=f"剧情节点触发：{r.node_id}"),
        )
        self._memory.apply_diff(r.diff, self.state)
        if r.narrator_hint:
            self._pending_story_hints.append(r.narrator_hint)

    # 循环结束后一次性更新 active_since
    new_active = self._story_engine.get_active_nodes(self.state)
    since_updates = {
        nid: self.state.turn
        for nid in new_active
        if nid not in self.state.story_active_since
    }
    if since_updates:
        self._state_manager.commit(
            StateDiff(story_active_since_updates=since_updates),
            ActionResult(success=True, action=ActionType.CUSTOM,
                         message="故事进度更新"),
        )
```

### 6.5 Narrator hint 注入

`Narrator.stream_narrative` 接收 `story_hint: str | None`：

```python
# _handle_free_input 中调用叙事生成时
combined_hint = "\n".join(self._pending_story_hints) or None
self._pending_story_hints.clear()
await self._renderer.render_stream(
    self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint)
)
```

---

## 7. 错误处理

| 场景 | 处理方式 |
|------|---------|
| 未知条件类型 | `logger.warning`，该条件视为 False（节点不触发） |
| story.yaml 不存在 | `StoryEngine({})` 空引擎，游戏正常运行 |
| 节点 requires 引用不存在的 ID | `get_active_nodes` 永远无法满足，节点永不激活（YAML 作者责任） |
| 多节点 `quest_updates` key 冲突 | 顺序 apply，后者覆盖前者（YAML 设计责任，文档说明） |
| `_apply_story_results` 中 commit 失败 | 异常向上传播，与普通 commit 失败处理一致 |

---

## 8. 测试计划

### `tests/engine/test_story.py`（~15 个）

| 测试 | 内容 |
|------|------|
| `test_get_active_nodes_no_requires` | 无前置节点直接进入活跃集 |
| `test_get_active_nodes_requires_not_met` | 前置未完成，节点不进活跃集 |
| `test_get_active_nodes_requires_met` | 前置完成后节点进入活跃集 |
| `test_get_active_nodes_repeatable_stays` | repeatable 节点完成后仍在活跃集 |
| `test_check_passive_triggers` | passive 节点在 passive 模式触发 |
| `test_check_continue_not_triggered_by_passive` | continue 节点不在 passive 模式触发 |
| `test_check_both_triggers_in_either_mode` | both 节点在两种模式均触发 |
| `test_build_result_marks_completed` | `_story_status` 写入 quests |
| `test_build_result_effects_applied` | quest_updates + new_events 正确生成 |
| `test_fail_forward_triggers_after_timeout` | 超时后触发 hint |
| `test_fail_forward_resets_since` | hint 触发后 story_active_since 重置为当前 turn |
| `test_fail_forward_no_infinite_repeat` | 重置后不会立即再次触发 |
| `test_fail_forward_no_trigger_before_timeout` | 未超时不触发 |
| `test_empty_nodes_returns_empty` | 空引擎不崩溃 |
| `test_unknown_condition_type_skips_node` | 未知条件类型节点不触发，只 warning |

### `tests/engine/test_story_conditions.py`（~6 个）

| 测试 | 内容 |
|------|------|
| `test_location_condition_match` | 玩家在目标地点时为 True |
| `test_location_condition_no_match` | 玩家不在目标地点时为 False |
| `test_inventory_condition_match` | 背包含目标物品时为 True |
| `test_relationship_condition` | trust >= 30 正确判断 |
| `test_event_condition_exists` | event 存在时为 True |
| `test_quest_condition` | quest status 匹配时为 True |

### `tests/cli/test_app_story.py`（~5 个）

| 测试 | 内容 |
|------|------|
| `test_passive_check_after_action` | 行动后 story_engine.check 被调用 |
| `test_continue_command_triggers_story` | continue 命令触发 continue 模式节点 |
| `test_continue_no_results_prints_message` | 无节点时打印提示 |
| `test_apply_story_results_commits_diff` | diff 正确 commit |
| `test_active_since_updated_after_apply` | story_active_since 在触发后正确更新 |

---

## 9. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/engine/story.py` | ~140 |
| 新建 | `src/tavern/engine/story_conditions.py` | ~60 |
| 修改 | `src/tavern/world/state.py` | +~10 |
| 修改 | `src/tavern/cli/app.py` | +~50 |
| 修改 | `src/tavern/narrator/narrator.py` | +~5（story_hint 参数） |
| 新建 | `data/scenarios/tavern/story.yaml` | ~60 |
| 新建 | `tests/engine/test_story.py` | ~200 |
| 新建 | `tests/engine/test_story_conditions.py` | ~80 |
| 新建 | `tests/cli/test_app_story.py` | ~100 |

---

## 10. 不在范围内

- 剧情编辑器 / 可视化工具
- 节点热重载（运行时修改 story.yaml）
- 跨 act 章节动态加载（当前全量加载）
- 分支结局系统（Phase 4）
- 节点 requires 的循环检测（YAML 作者责任）
