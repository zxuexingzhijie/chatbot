# Phase 4: 内容系统 + 分类记忆 + 游戏日志 + 场景缓存

> 前置: Phase 1 (FSM/CommandRegistry/ReactiveStore/SeededRNG) + Phase 2 (ActionDef/ActionRegistry/KeybindingResolver/Bootstrap) + Phase 3 (类型统一/Effect Executor/ExploringMode/DialogueMode/GameApp集成) 已完成。

## 目标

实现 master design 中剩余 4 个架构改进：

- §3 Markdown-as-Code 内容系统 — ContentLoader 基础设施（不迁移现有内容）
- §9 分类记忆体系 — 替换现有 MemorySystem，按类型 + 衰减裁剪 prompt 上下文
- §8 Append-Only JSONL 游戏日志 — 异步批量写入 + /journal 命令
- §10 Memoized 场景上下文缓存 — LRU 缓存 + 自动失效 + 集成 ContentLoader/SeededRNG

## 完成标准

- ContentLoader 能加载 Markdown + frontmatter，解析变体文件，按条件选择变体
- ClassifiedMemorySystem 替换 MemorySystem，build_context() 接口不变，内部按类型 + 衰减裁剪
- GameLogger 异步写入 JSONL，/journal 命令可查看最近操作
- SceneContextCache 命中时跳过 prompt 重建，状态变更自动失效
- 所有现有测试通过 + 新模块测试覆盖

---

## §3 Markdown-as-Code 内容系统

### 范围

只建 ContentLoader 基础设施。不迁移现有 YAML 描述，不接入 Narrator（§10 做集成）。`content/` 目录不存在时 ContentLoader 返回空，调用方 fallback 到 YAML description。

### 数据模型

```python
@dataclass(frozen=True)
class VariantDef:
    name: str       # "after_secret"
    when: str       # "event:cellar_secret_revealed" — 原始条件字符串

@dataclass(frozen=True)
class ContentEntry:
    id: str                           # "tavern_hall"
    content_type: str                 # "room", "npc", "item", "event"
    metadata: dict                    # frontmatter 中的其他字段
    body: str                         # 默认正文
    variants: dict[str, str]          # variant_name -> variant_body
    variant_defs: tuple[VariantDef, ...]  # frontmatter 中声明的变体条件
```

### Content ID 约束

ID 只允许 `[a-z0-9_]`。文件名按第一个 `.` 分割：`tavern_hall.night.md` → ID=`tavern_hall`，variant=`night`。加载时校验 ID 格式，不合规 raise `ContentError`。

### 变体文件

- 主文件（`tavern_hall.md`）：含 frontmatter + body
- 变体文件（`tavern_hall.night.md`）：纯 body，无 frontmatter，自动关联到主文件

### 条件求值

`ContentLoader._evaluate_condition(condition_str, state)` 需要将 `"type:params"` 字符串解析为 `ActivationCondition` 对象，然后调用 `CONDITION_REGISTRY[type]`。

现有 `story_conditions.py` 的签名是 `(ActivationCondition, WorldState, EventTimeline, RelationshipGraph) -> bool`。ContentLoader 需要：
1. 解析 `"event:cellar_secret_revealed"` → `ActivationCondition(type="event", event_id="cellar_secret_revealed")`
2. 解析 `"relationship:bartender_grim >= 30"` → `ActivationCondition(type="relationship", character="bartender_grim", operator=">=", value=30)`
3. 从 state 中获取 timeline 和 relationships_snapshot 构造参数

新增一个 `evaluate_condition_str(condition_str, state, timeline, relationships)` 公共函数在 `story_conditions.py` 中，ContentLoader 调用它。

### 文件

- 新建 `src/tavern/content/__init__.py`
- 新建 `src/tavern/content/loader.py` (~120 行)
- 更新 `src/tavern/engine/story_conditions.py` (新增 `evaluate_condition_str`)
- 新建 `tests/content/test_loader.py`

### 不在范围

- 迁移 world.yaml 中现有描述到 Markdown 文件
- 接入 Narrator prompt 构建
- 模组支持（多来源加载）
- `activate_when` 懒加载模式

---

## §9 分类记忆体系

### 范围

替换现有 `MemorySystem`，保持 `build_context()` 返回 `MemoryContext(recent_events, relationship_summary, active_skills_text)` 接口不变。内部通过分类 + 衰减选择最相关的记忆填充 prompt。

### 数据模型

```python
class MemoryType(Enum):
    LORE = "lore"                # 世界设定、已发现的知识
    QUEST = "quest"              # 任务进度、目标
    RELATIONSHIP = "relationship"  # NPC 关系变化
    DISCOVERY = "discovery"       # 探索发现、环境细节

@dataclass(frozen=True)
class MemoryEntry:
    id: str
    memory_type: MemoryType
    content: str
    importance: int        # 1-10
    created_turn: int
    last_relevant_turn: int

@dataclass(frozen=True)
class MemoryBudget:
    lore: int = 200        # token 预算
    quest: int = 300
    relationship: int = 150
    discovery: int = 100
```

### 时间衰减

```python
_DECAY_RATE = {
    MemoryType.LORE: 0.01,           # 100 turns 后权重仍 0.5
    MemoryType.QUEST: 0.05,          # 20 turns 后权重 0.5
    MemoryType.RELATIONSHIP: 0.08,   # ~12 turns 后权重 0.5
    MemoryType.DISCOVERY: 0.2,       # 5 turns 后权重 0.5
}

def _recency_score(entry, current_turn):
    age = current_turn - entry.last_relevant_turn
    return 1.0 / (1.0 + age * _DECAY_RATE[entry.memory_type])
```

### build_context 映射

- LORE → `active_skills_text`（世界知识）
- QUEST + DISCOVERY → `recent_events`（事件性信息）
- RELATIONSHIP → `relationship_summary`

### MemoryExtractor

规则匹配，不用 LLM。事件类型 → 记忆分类的映射表：

| 事件类型模式 | 记忆类型 | importance |
|-------------|---------|------------|
| `dialogue_summary_*` | LORE (has_secret→8, 否则→4) | 4-8 |
| `quest_*` | QUEST | 7 |
| `relationship_changed` | RELATIONSHIP | abs(delta)>=10→6, 否则→3 |
| `search\|look_detail` | DISCOVERY | 2 |

### 与现有组件的关系

- **EventTimeline**: 保留。完整事件流仍存储在 WorldState.timeline 中。MemoryExtractor 从新事件中提取分类记忆
- **RelationshipGraph**: 保留。仍在 ClassifiedMemorySystem 内部使用，relationship_summary 的描述逻辑不变
- **SkillManager**: 保留。skill 知识注入归入 LORE 类型的 active_skills_text 构建

### 文件

- 重写 `src/tavern/world/memory.py` (~250 行)
- 新建 `src/tavern/world/memory_extractor.py` (~80 行)
- 更新 `tests/world/test_memory.py`
- 新建 `tests/world/test_memory_extractor.py`

---

## §8 Append-Only JSONL 游戏日志

### 数据模型

```python
@dataclass(frozen=True)
class GameLogEntry:
    timestamp: str       # ISO 8601
    turn: int
    session_id: str
    entry_type: str      # "player_input", "system_output", "state_change", "error"
    data: dict
```

### GameLogger

- 内存 buffer + `flush_interval` (默认 2s) 定时刷盘
- 文件路径: `{log_dir}/{session_id}.jsonl`
- 文件轮转: 超过 `MAX_FILE_SIZE` (5MB) 时重命名加时间戳后缀
- `read_recent(n)`: 从文件末尾反向读取 + buffer 未刷盘条目
- `close()`: 同步 flush，在 GameApp.run() 的 finally 块中调用

### /journal 命令

注册为 GameCommand，读取最近 20 条 player_input 类型条目，渲染为可读的冒险日志。

### 接入点

- ExploringModeHandler: 记录 player_input (raw + parsed_action + target)
- effects executor (APPLY_DIFF): 记录 state_change
- GameLoop 异常捕获: 记录 error

### 文件

- 新建 `src/tavern/engine/game_logger.py` (~130 行)
- 更新 `src/tavern/engine/command_defs.py` (添加 cmd_journal)
- 更新 `src/tavern/cli/bootstrap.py` (注入 logger)
- 更新 `src/tavern/engine/fsm.py` (ModeContext 新增 logger 字段)
- 新建 `tests/engine/test_game_logger.py`

---

## §10 Memoized 场景上下文缓存

### SceneContext

```python
@dataclass(frozen=True)
class SceneContext:
    location_description: str    # 来自 ContentLoader (优先) 或 YAML description
    npcs_present: tuple[str, ...]
    items_visible: tuple[str, ...]
    exits_available: tuple[str, ...]
    atmosphere: str
    ambience: AmbienceDetails    # 来自 SeededRNG.generate_ambience()
```

### SceneContextCache

LRU 缓存，key = `(location_id, state_version)`，MAX_ENTRIES = 100。

- `get(location_id, state_version)` → `SceneContext | None`
- `put(location_id, state_version, context)` — 自动清理同一 location 的旧 version
- `invalidate(location_id=None)` — None 时清空全部

### CachedPromptBuilder

封装缓存 + 内容解析 + 氛围生成：

```python
class CachedPromptBuilder:
    def __init__(self, content_loader, cache, state_manager):
        ...

    def build_scene_context(self, state) -> SceneContext:
        # 1. 查缓存 (location_id, state_manager.version)
        # 2. miss → 构建:
        #    a. ContentLoader.resolve() 优先，fallback YAML description
        #    b. generate_ambience() 生成氛围
        #    c. 收集 NPC/物品/出口
        # 3. 存缓存
```

### 失效机制

通过 ReactiveStateManager.on_change：
- 位置变更 → 失效旧位置缓存
- 当前位置物品/NPC 变更 → 失效当前位置缓存

### 接入 Narrator

`build_narrative_prompt()` 内部：如果有 CachedPromptBuilder，用 SceneContext 的 location_description 替代 NarrativeContext 的 location_desc。

### 文件

- 新建 `src/tavern/narrator/scene_cache.py` (~100 行，SceneContext + SceneContextCache)
- 新建 `src/tavern/narrator/cached_builder.py` (~80 行，CachedPromptBuilder)
- 更新 `src/tavern/narrator/prompts/builder.py` (接入 SceneContext)
- 更新 `src/tavern/cli/bootstrap.py` (注入 cache + builder)
- 新建 `tests/narrator/test_scene_cache.py`
- 新建 `tests/narrator/test_cached_builder.py`

---

## 依赖顺序

```
§3 ContentLoader ─────────┐
                          ├─→ §10 SceneContextCache + CachedPromptBuilder
§9 ClassifiedMemorySystem │
                          │
§8 GameLogger ────────────┘
```

§3 和 §8 互相独立可并行。§9 不严格依赖 §3（MemoryExtractor 从事件提取记忆，不从 Markdown 文件读取），但建议 §3 先完成以确保 LORE 类型可从 ContentLoader 获取内容元数据。§10 依赖 §3（ContentLoader 作为数据源）。

推荐实施顺序: §3 → §9 → §8 → §10

---

## 不在范围

- 迁移 world.yaml 中现有描述到 Markdown 文件
- `activate_when` 懒加载模式和模组支持
- COMBAT/INVENTORY/SHOP mode handler 实现
- KeybindingResolver 接入 prompt_toolkit
- renderer Markdown 渲染（粗体→Rich 加粗等）
- narrator.py 中 `memory_ctx.relationships` bug 修复（独立 issue）
