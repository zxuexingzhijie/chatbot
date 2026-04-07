# 记忆系统 — Phase 2c 设计规格

**日期**: 2026-04-07
**状态**: 已批准
**范围**: EventTimeline + RelationshipGraph + SkillManager（基础设施）+ MemorySystem 统一入口 + 注入 Narrator/DialogueManager

---

## 1. 概述

为酒馆 CLI 游戏添加记忆层。当前 Narrator 和 DialogueManager 是"失忆"的——每次叙事和对话都没有历史上下文。Phase 2c 构建三个子系统，通过 `MemoryContext` 数据包注入 Prompt，让 NPC 对话随关系值变化而深化，叙事随剧情历史而连贯。

### 设计目标

- EventTimeline：WorldState.timeline 的查询视图，提供最近事件摘要文本
- RelationshipGraph：NetworkX DiGraph 追踪角色关系，并行于 `stats["trust"]`（不替换）
- SkillManager：YAML Skill 加载 + 条件激活，基础设施只，不含具体 Skill 文件（Phase 3）
- MemorySystem：统一入口，`build_context()` 输出 `MemoryContext` 数据包
- Narrator/DialogueManager：接收可选 `MemoryContext`，`None` 时行为与现在完全一致

---

## 2. 架构

### 2.1 数据流

```
每次行动后（GameApp）:
  memory.apply_diff(diff, new_state)         ← 更新 timeline 视图 + RelationshipGraph

成功行动叙事:
  memory_ctx = memory.build_context(actor, state, current_topic, max_tokens)
  narrator.stream_narrative(result, state, memory_ctx)

NPC 对话 start:
  memory_ctx = memory.build_context(npc_id, state, current_topic)
  dialogue_manager.start(state, npc_id, is_persuade, memory_ctx)

NPC 对话每轮 respond:
  memory_ctx = memory.build_context(npc_id, state, current_topic=user_input)
  dialogue_manager.respond(ctx, user_input, state, memory_ctx)
```

### 2.2 模块结构

```
src/tavern/world/
├── memory.py     # EventTimeline + RelationshipGraph + MemoryContext + MemorySystem
└── skills.py     # Skill dataclass + ActivationCondition + SkillManager + ConditionEvaluator

data/scenarios/tavern/
└── skills/       # 目录预建，Skill YAML 文件留 Phase 3 填充
```

---

## 3. 数据模型

### 3.1 MemoryContext

```python
@dataclass(frozen=True)
class MemoryContext:
    recent_events: str          # EventTimeline.summarize() 输出文本
    relationship_summary: str   # RelationshipGraph.describe_for_prompt(char_id) 输出文本
    active_skills_text: str     # SkillManager.inject_to_prompt(active_skills) 输出文本
```

### 3.2 RelationshipDelta / Relationship

```python
@dataclass(frozen=True)
class RelationshipDelta:
    src: str
    tgt: str
    delta: int

@dataclass(frozen=True)
class Relationship:
    src: str
    tgt: str
    value: int   # clamp [-100, 100]
```

### 3.3 Skill / ActivationCondition

```python
@dataclass(frozen=True)
class ActivationCondition:
    type: str        # "relationship" | "event" | "quest" | "inventory"
    # relationship 条件字段
    source: str | None = None
    target: str | None = None
    attribute: str | None = None
    operator: str | None = None  # "==" | "!=" | ">" | "<" | ">=" | "<="
    value: int | None = None
    # event 条件字段
    event_id: str | None = None
    check: str | None = None     # "exists" | "not_exists"

@dataclass(frozen=True)
class Skill:
    id: str
    character: str
    priority: str                      # "high" | "normal" | "low"
    activation: tuple[ActivationCondition, ...]
    facts: tuple[str, ...]
    behavior: dict[str, str]           # tone, reveal_strategy, forbidden 等
```

---

## 4. 核心组件

### 4.1 `EventTimeline`（`world/memory.py`）

WorldState.timeline 的只读视图，不持久化，每次从最新 WorldState 重建。

```python
class EventTimeline:
    def __init__(self, events: tuple[Event, ...]) -> None

    def recent(self, n: int = 5) -> list[Event]
    def query(
        self, actor: str | None = None,
        type: str | None = None,
        after_turn: int | None = None
    ) -> list[Event]
    def summarize(self, max_tokens: int = 200) -> str
    # 最近5条完整描述 + 更早的「[已省略N条早期事件]」
    # 纯字符串拼接，不调用 LLM
    def has(self, event_id: str) -> bool
```

### 4.2 `RelationshipGraph`（`world/memory.py`）

并行于 `stats["trust"]`，不替换。`apply_diff` 时从 StateDiff.relationship_changes 同步，存档前快照写回 WorldState.relationships_snapshot。

```python
class RelationshipGraph:
    def __init__(self, snapshot: dict | None = None) -> None
    # snapshot 为 nx.node_link_data(G) 格式，None 时初始化空图

    def get(self, src: str, tgt: str) -> Relationship
    # 不存在的边返回 Relationship(src, tgt, value=0)

    def update(self, delta: RelationshipDelta) -> Relationship
    # 更新边属性，clamp [-100, 100]，返回更新后的 Relationship

    def get_all_for(self, char_id: str) -> list[Relationship]
    # 返回 char_id 所有出边关系

    def describe_for_prompt(self, char_id: str) -> str
    # 生成关系描述文本，如「旅行者对你的信任: 20（中立）」

    def to_snapshot(self) -> dict
    # 返回 nx.node_link_data(G)，供 WorldState.relationships_snapshot 存储

    # multi_hop(char_id, depth) → Phase 4
```

### 4.3 `SkillManager`（`world/skills.py`）

YAML Skill 加载 + 条件激活。具体 Skill 文件（bartender_gossip.yaml 等）留 Phase 3。

```python
class SkillManager:
    def load_skills(self, scenario_path: Path) -> None
    # 扫描 scenario_path/skills/*.yaml，解析为 Skill 对象存入内部 dict

    def get_active_skills(
        self,
        char_id: str,
        state: WorldState,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
    ) -> list[Skill]
    # 过滤 character==char_id 的 Skills，对每个 Skill 求值 activation.conditions
    # 全部满足才纳入结果，按 priority（high > normal > low）排序

    def inject_to_prompt(self, skills: list[Skill], max_chars: int = 800) -> str
    # 将 skills 的 facts + behavior 序列化为文本，超出 max_chars 截断低优先级

    # unlock(skill_id, state) → Phase 3
    # teach(char_id, fact, skill_id) → Phase 3
```

**ConditionEvaluator**（`world/skills.py`）

按 `type` 分发的内部求值函数，Phase 3 剧情节点引擎将复用同一套：

- `_eval_relationship(cond, relationships)` — 读 RelationshipGraph.get() 值，按 operator 比较
- `_eval_event(cond, timeline)` — 调用 timeline.has(event_id)，按 check 判断存在/不存在
- `_eval_quest(cond, state)` — 读 state.quests
- `_eval_inventory(cond, state)` — 读 player.inventory

### 4.4 `MemorySystem`（`world/memory.py`）

统一入口，GameApp 持有一个实例。

```python
class MemorySystem:
    def __init__(self, state: WorldState, skills_dir: Path | None = None) -> None
    # 从 state.timeline 构建 EventTimeline
    # 从 state.relationships_snapshot 恢复 RelationshipGraph
    # 若 skills_dir 存在则调用 skill_manager.load_skills()

    def apply_diff(self, diff: StateDiff, new_state: WorldState) -> None
    # 从 diff.relationship_changes 调用 relationship_graph.update()
    # 重建 EventTimeline（从 new_state.timeline）

    def build_context(
        self,
        actor: str,
        state: WorldState,
        current_topic: str = "",
        max_tokens: int = 2000,
    ) -> MemoryContext
    # 渐进加载策略：
    # 1. recent_events = timeline.summarize()
    # 2. relationship_summary = relationships.describe_for_prompt(actor)
    # 3. active_skills = skill_manager.get_active_skills(actor, state, timeline, relationships)
    # 4. active_skills_text = skill_manager.inject_to_prompt(active_skills, max_chars 由 max_tokens 估算)
    # current_topic 用于未来按相关度排序 Skills（Phase 3），当前传入但暂不使用

    def sync_to_state(self, state: WorldState) -> WorldState
    # 将 RelationshipGraph.to_snapshot() 写入 WorldState.relationships_snapshot
    # 返回新的不可变 WorldState，存档前调用
```

---

## 5. 集成变更

### 5.1 `narrator/prompts.py`

`build_narrative_prompt` 增加可选参数，NarrativeContext 结构不变：

```python
def build_narrative_prompt(
    ctx: NarrativeContext,
    memory_ctx: MemoryContext | None = None,
) -> list[dict[str, str]]:
```

memory_ctx 存在时，将 `recent_events` 和 `relationship_summary` 追加到 system_content 末尾。

### 5.2 `narrator/narrator.py`

```python
async def stream_narrative(
    self,
    result: ActionResult,
    state: WorldState,
    memory_ctx: MemoryContext | None = None,
) -> AsyncGenerator[str, None]:
```

传递给 `build_narrative_prompt(ctx, memory_ctx)`。

### 5.3 `dialogue/prompts.py`

`build_dialogue_prompt` 增加 `active_skills_text` 参数：

```python
def build_dialogue_prompt(
    ctx: DialogueContext,
    location_name: str,
    history_summaries: list[str],
    is_persuade: bool = False,
    active_skills_text: str = "",
) -> str:
```

`active_skills_text` 非空时追加到 system prompt 末尾的【NPC知识与行为】区块。

### 5.4 `dialogue/manager.py`

```python
async def start(
    self,
    state: WorldState,
    npc_id: str,
    is_persuade: bool = False,
    memory_ctx: MemoryContext | None = None,
) -> tuple[DialogueContext, DialogueResponse]

async def respond(
    self,
    ctx: DialogueContext,
    player_input: str,
    state: WorldState,
    memory_ctx: MemoryContext | None = None,
) -> tuple[DialogueContext, DialogueResponse]
```

### 5.5 `cli/app.py`

**`__init__`** 新增：
```python
skills_dir = scenario_path / "skills"
self._memory = MemorySystem(
    state=initial_state,
    skills_dir=skills_dir if skills_dir.exists() else None,
)
```

**`_handle_free_input`** 成功行动后：
```python
memory_ctx = self._memory.build_context(
    actor=result.target or state.player_id,
    state=self.state,
    current_topic=result.message,
)
# 传给 narrator 或 dialogue_manager.start()
```

**`_process_dialogue_input`** 每轮：
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

**每次 `state_manager.commit()` 后**：
```python
self._memory.apply_diff(diff, self.state)
```

---

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| networkx 未安装 | `ImportError` 在启动时抛出，明确提示 `pip install networkx` |
| skills/ 目录不存在 | SkillManager 初始化为空，`get_active_skills` 返回空列表 |
| Skill YAML 解析失败 | 跳过该文件，记录 `logger.warning`，其余 Skills 正常加载 |
| MemoryContext 为 None | Narrator/DialogueManager 行为与 Phase 2b 完全一致 |
| RelationshipGraph 快照损坏 | 初始化空图，记录 `logger.warning` |

---

## 7. 测试计划

| 文件 | 测试内容 | 预计数量 |
|------|---------|---------|
| `tests/world/test_memory.py` | EventTimeline query/summarize/has；RelationshipGraph get/update/clamp/describe；MemorySystem build_context；apply_diff 同步 | 14 |
| `tests/world/test_skills.py` | Skill YAML 加载；ConditionEvaluator relationship/event 条件；get_active_skills 过滤+排序；inject_to_prompt 截断 | 10 |
| `tests/narrator/test_prompts.py` | build_narrative_prompt 携带 memory_ctx 时包含事件摘要；memory_ctx=None 时与现有一致 | 3 |
| `tests/dialogue/test_prompts.py` | build_dialogue_prompt 携带 active_skills_text 时包含 skills；空字符串时不变 | 2 |
| `tests/dialogue/test_manager.py` | start/respond 接收 memory_ctx 并传递；None 时行为不变 | 3 |
| `tests/cli/test_app_memory.py` | GameApp._handle_free_input 调用 memory.build_context；_process_dialogue_input 每轮调用；apply_diff 在 commit 后调用 | 4 |

**预计新增测试：36 个**

### 覆盖率目标

新模块 `world/memory.py`、`world/skills.py` ≥ 85%，整体项目保持 ≥ 80%。

---

## 8. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/world/memory.py` | ~150 |
| 新建 | `src/tavern/world/skills.py` | ~130 |
| 新建 | `data/scenarios/tavern/skills/` | 目录 |
| 修改 | `src/tavern/narrator/prompts.py` | +~15 |
| 修改 | `src/tavern/narrator/narrator.py` | +~5 |
| 修改 | `src/tavern/dialogue/prompts.py` | +~10 |
| 修改 | `src/tavern/dialogue/manager.py` | +~10 |
| 修改 | `src/tavern/cli/app.py` | +~20 |
| 新建 | `tests/world/test_memory.py` | ~180 |
| 新建 | `tests/world/test_skills.py` | ~130 |
| 修改 | `tests/narrator/test_prompts.py` | +~30 |
| 修改 | `tests/dialogue/test_prompts.py` | +~20 |
| 修改 | `tests/dialogue/test_manager.py` | +~30 |
| 新建 | `tests/cli/test_app_memory.py` | ~60 |

**新增代码约 ~350 行，测试约 ~450 行**

---

## 9. 不在范围内

- SkillManager.unlock / teach — Phase 3
- RelationshipGraph.multi_hop — Phase 4
- 具体 Skill YAML 文件（bartender_gossip 等）— Phase 3
- current_topic 相关度排序 — Phase 3
- Anthropic / Ollama 后端 — Phase 4
- 存档/读档（save/load 命令）— Phase 3
