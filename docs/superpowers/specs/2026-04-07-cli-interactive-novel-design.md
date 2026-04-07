# CLI互动式小说游戏 — 设计规格文档

> 项目代号: **Tavern (酒馆)**
> 日期: 2026-04-07
> 状态: 设计完成，待实施

---

## 1. 产品概述

基于CLI的互动式小说游戏，玩家通过自然语言输入探索奇幻世界。采用混合管道架构（规则引擎 + LLM），在保障剧情可控的前提下提供开放式叙事体验。

**核心体验**: 玩家自主发言 → 世界实时演绎 → 叙事可存续 → 既定规则下的全自由探索

**技术栈**: Python + Rich (美化流式CLI) + NetworkX (角色关系图) + 多LLM后端 (OpenAI / Anthropic / Ollama)

**MVP场景**: 奇幻酒馆探索 — 多NPC对话驱动，地下室之谜主线

---

## 2. 系统架构

### 2.1 混合管道架构

三层引擎 + 横切模块：

```
玩家输入 (Rich CLI)
       ↓
┌─────────────────┐
│ ① 意图解析层     │  LLM意图分类 → ActionRequest
│   (parser/)     │  Structured Output (JSON)
└────────┬────────┘
         ↓
┌─────────────────┐
│ ② 规则引擎层     │  世界规则验证 → ActionResult + 状态diff
│   (engine/)     │  前置条件检查、状态变更计算
└────────┬────────┘
         ↓
┌─────────────────┐
│ ③ 叙事生成层     │  LLM生成场景描述、NPC对话
│   (narrator/)   │  流式输出（打字机效果）
└────────┬────────┘
         ↓
   Rich 渲染输出
```

**横切模块**:
- **状态管理器** (world/state.py): 世界状态、存档、加载
- **记忆系统** (world/memory.py): 事件时间线、关系图
- **技能管理器** (world/skills.py): YAML Skill加载、条件求值、Prompt注入
- **LLM适配器** (llm/adapter.py): 多后端统一接口

### 2.2 横切模块详细设计

#### 2.2.1 状态管理器 (world/state.py)

**核心类**:

- `WorldState` (frozen Pydantic BaseModel): 不可变世界状态快照，包含turn、player、locations、characters、items、relationships_snapshot(dict, 由`nx.node_link_data(G)`序列化而来)、quests、timeline、last_action(ActionResult | None, 供retry使用)。提供 `apply(diff) -> WorldState` 方法返回新实例。所有字段均为不可变类型——RelationshipGraph作为活对象由MemorySystem持有，WorldState仅存储其序列化快照。
- `StateDiff` (BaseModel): 规则引擎输出的状态变更描述，包含updated_characters、updated_locations、added_items、removed_items、relationship_changes、quest_updates、new_events、turn_increment。
- `StateManager`: 有状态管理器，持有 `_current: WorldState`、`_history: deque[WorldState]`(undo栈, maxlen=50)、`_redo: deque[WorldState]`(redo栈)。

**核心方法**:

- `commit(diff: StateDiff, action: ActionResult) -> WorldState`: 推旧状态入history → apply diff(含last_action=action) → 清空redo → 触发auto_save检查
- `undo() -> WorldState`: 推当前状态到redo → pop history
- `redo() -> WorldState`: 推当前状态到history → pop redo
- `save(name, path) -> Path`: snapshot → 附加meta(save_version, timestamp, SHA256 checksum) → atomic write(先写.tmp再rename)
- `load(name, path) -> WorldState`: 读JSON → 校验version兼容性 → 校验checksum → 反序列化 → 清空history/redo
- `list_saves(path) -> list[SaveInfo]`: 列出所有存档元信息

**设计决策**:

- 不可变状态: undo/redo只需保存引用无需深拷贝，避免竞态，天然可序列化。WorldState所有字段均为不可变类型——RelationshipGraph活对象由MemorySystem持有，WorldState仅存储`node_link_data`序列化快照
- StateDiff模式: 变更可审计（日志记录diff），叙事层可读取diff描述"发生了什么"，retry时丢弃diff即可
- 存档安全: atomic write防损坏，checksum校验完整性，version字段支持未来格式迁移
- Auto-save: 每N回合或关键剧情节点自动存档

#### 2.2.2 记忆系统 (world/memory.py)

三个独立子系统 + 统一入口。采用 **Skills模块管理知识与行为** + **NetworkX管理动态关系** 的混合架构，借鉴Agent Skills范式替代传统RAG式的知识检索：

**EventTimeline** — 线性事件时间线:
- `append(event)`: 追加事件，按turn排序
- `recent(n=5) -> list[Event]`: 最近n条，供Prompt注入
- `query(**filters) -> list[Event]`: 按actor/type/after_turn/contains过滤
- `summarize(max_tokens=200) -> str`: 最近5条完整 + 更早的截断为「[已省略N条早期事件]」标记，控制Prompt长度。不引入LLM调用，保持纯数据结构
- `has(event_id) -> bool`: 供剧情引擎trigger条件检查

**RelationshipGraph** — 基于NetworkX DiGraph的角色关系图:
- 底层: `nx.DiGraph`，节点=角色ID，边属性=关系类型+数值
- `G.edges["bartender", "player"]["trust"] = -20` 语义清晰
- `get(src, tgt) -> Relationship | None`: 查询两角色关系
- `update(delta: RelationshipDelta) -> Relationship`: 原地修改DiGraph边属性，自动clamp [-100, 100]。不可变性由StateManager层保障（commit时snapshot当前图状态）
- `get_all_for(char_id) -> list[Relationship]`: 某角色所有关系（`G.edges(char_id)`）
- `multi_hop(char_id, depth=2) -> subgraph`: 多跳查询（"谁认识谁的敌人"），供复杂社交场景
- `describe_for_prompt(char_id) -> str`: 生成关系描述文本供Prompt注入
- 序列化: `nx.node_link_data(G)` → JSON，兼容存档系统

**SkillManager** — 基于YAML文件的知识与行为模块系统（替代KnowledgeGraph）:

Skills采用Agent Skills范式：每个Skill是一个YAML文件，将NPC的**知识（facts）+ 行为方式（behavior）+ 激活条件（activation）**内聚为一个可独立管理的模块。相比传统RAG式的知识图谱BFS检索，Skills通过条件匹配精准激活，只将相关模块注入Prompt。

Skill文件格式:
```yaml
id: bartender_cellar_secret
name: 格里姆的地下室秘密
character: bartender_grim
activation:
  conditions:                              # 全部满足才激活（结构化条件对象）
    - type: relationship                   # 条件类型: relationship | event | quest | inventory
      source: player
      target: bartender_grim
      attribute: trust
      operator: ">="                       # 支持: ==, !=, >, <, >=, <=
      value: 30
    - type: event
      event_id: asked_about_cellar
      check: exists                        # exists | not_exists
  priority: high                           # 同时激活多个Skill时的注入优先级 (high > normal > low)

facts:                                     # NPC知道的事实
  - "地下室有一条通往城外森林的密道"
  - "密道是二十年前战争时期挖的"
  - "最近有人在深夜使用过密道"

behavior:                                  # 指导LLM如何表达
  tone: "压低声音、犹豫、左顾右盼"
  reveal_strategy: "不会一次全说，先透露存在密道，第二次才说位置"
  forbidden: "绝不提及谁在使用密道（他不知道）"

related_skills:                            # 可链式激活的相关Skill
  - bartender_gossip
```

Skill文件存放位置:
```
data/scenarios/tavern/skills/
├── bartender_gossip.yaml            # 酒馆八卦（低门槛闲聊触发）
├── bartender_cellar_secret.yaml     # 地下室秘密（trust>30解锁）
├── bartender_town_history.yaml      # 城镇历史（任何时候可问）
├── traveler_quest_info.yaml         # 旅行者的委托信息
└── mysterious_guest_hint.yaml       # 神秘旅客的线索
```

SkillManager核心方法:
- `load_skills(scenario_path) -> dict[str, Skill]`: 启动时从YAML目录加载所有Skill定义
- `evaluate_activation(skill, state, memory) -> bool`: 遍历Skill的activation.conditions列表，按type字段分发到对应求值器（RelationshipConditionEvaluator / EventConditionEvaluator / QuestConditionEvaluator / InventoryConditionEvaluator），全部返回True才激活
- `get_active_skills(char_id, state, memory) -> list[Skill]`: 获取某角色当前所有已激活的Skills，按priority排序
- `inject_to_prompt(skills, max_tokens) -> str`: 将激活的Skills序列化为Prompt文本（facts + behavior指令），按priority裁剪到token预算
- `unlock(skill_id, state) -> StateDiff`: 当条件新满足时，产生"Skill解锁"事件（可触发叙事提示）
- `teach(char_id, fact, skill_id)`: 运行时向某Skill动态追加fact（内存中修改，存档时持久化）

与传统RAG/KnowledgeGraph的对比:
| | KnowledgeGraph (旧方案) | Skills (新方案) |
|---|---|---|
| 知识存储 | 图节点+边 | YAML文件模块 |
| 检索方式 | BFS图遍历 + 相关度排序 | 条件激活 + priority排序 |
| 行为指导 | 无（散落在narrator prompts） | 内聚在Skill的behavior字段 |
| 内容创作 | 需要理解图结构 | 写YAML即可，非程序员友好 |
| 渐进解锁 | 需额外逻辑 | activation.conditions天然支持 |
| 可组合性 | 图的关联边 | related_skills链式激活 |

**MemorySystem** — 统一入口:
- 组合 timeline + relationships(NetworkX) + skills(SkillManager)
- `build_context(actor, current_topic, max_tokens) -> MemoryContext`: 为Prompt构建完整记忆上下文。渐进加载策略:
  1. 最近5条事件（最高优先级）
  2. 当前交互NPC的直接关系（从RelationshipGraph提取）
  3. 当前NPC的已激活Skills（从SkillManager.get_active_skills()获取，按priority + 与current_topic的相关度排序）
  4. 超出token预算则截断低优先级Skills
- `apply_diff(diff: StateDiff)`: 从StateDiff提取变更 → 更新timeline + relationships + 检查是否有新Skill被解锁

**设计决策**:

- Skills替代KnowledgeGraph: 知识不再是图中的零散节点，而是内聚了facts+behavior+conditions的模块。从"搜索+填空"升级为"条件激活+精准注入"，避免传统RAG的"检索失误即满盘皆输"问题
- NetworkX仅管关系: 角色间的动态数值关系（trust/fear/hostility）仍用NetworkX DiGraph追踪，因为关系是频繁变化的数值，不适合静态YAML
- 渐进式Skill加载: 只有满足activation.conditions的Skills才注入Prompt，随着玩家推进游戏，更多Skills解锁，NPC"知道"的东西越来越多
- MemorySystem不持久化: 它是WorldState的读视图。存档时序列化RelationshipGraph(node_link_data→JSON) + 已解锁的Skill状态 + 动态追加的facts。加载后重建
- Token预算控制: build_context按priority填充已激活Skills，自动截断低优先级部分

#### 2.2.3 LLM适配器 (llm/)

**核心类**:

- `LLMConfig` (BaseModel): provider、model、temperature、max_tokens、base_url、api_key(从环境变量读取)、timeout(默认30s)、max_retries(默认3)
- `LLMAdapter` (Protocol): 所有后端必须实现的接口
  - `complete(messages, response_format?) -> T | str`: 通用补全，传入Pydantic model类型时返回Structured Output实例，否则返回纯文本
  - `stream(messages) -> AsyncIterator[str]`: 流式输出，yield每个文本chunk
- `OpenAIAdapter`: P1实现，使用AsyncOpenAI客户端
- `AnthropicAdapter`: P4实现，system message → system参数，Structured Output → tool_use模拟
- `OllamaAdapter`: P4实现，httpx直连本地API，JSON mode + SSE流式

**业务层**:

- `LLMRegistry`: 适配器工厂，`create(config) -> LLMAdapter` 根据provider动态创建
- `LLMService`: 组合两个适配器实例
  - `_intent_llm`: 轻量模型（低温度、确定性分类）
  - `_narrative_llm`: 强模型（高温度、创意叙事）
  - `classify_intent(input, context) -> ActionRequest`: 构建few-shot messages → _intent_llm.complete(msgs, ActionRequest)
  - `generate_narrative(action, state, memory) -> str`: 构建叙事messages → _narrative_llm.complete(msgs)
  - `stream_narrative(action, state, memory) -> AsyncIterator[str]`: 同上但用stream()，Rich渲染层消费iterator实现打字机效果

**错误处理**:

- 网络错误: tenacity指数退避重试(max_retries次)
- Rate limit: 自动等待retry-after
- JSON解析失败: 重试1次，仍失败返回CUSTOM动作兜底
- 超时: 配置化timeout
- 所有错误包装为LLMError自定义异常

**配置热加载**: config.yaml变更时LLMRegistry重新创建适配器实例，无需重启游戏。

### 2.3 模块划分

| 模块 | 职责 | 核心文件 |
|------|------|----------|
| `cli/` | Rich终端UI、输入输出、命令路由 | app.py, renderer.py |
| `parser/` | LLM意图分类 | intent.py |
| `engine/` | 规则验证、状态变更、剧情节点管理 | rules.py, story.py, actions.py |
| `narrator/` | LLM叙事生成、Prompt模板管理 | narrator.py, prompts.py |
| `world/` | 世界模型、角色、地点、物品、关系、技能 | models.py, state.py, memory.py, skills.py |
| `llm/` | 多后端LLM适配器 | adapter.py, openai_llm.py, claude_llm.py, ollama_llm.py |
| `data/` | 世界配置、剧本YAML | scenarios/, saves/ |

---

## 3. 世界模型与数据结构

### 3.1 核心模型 (Pydantic dataclass)

**Character (角色)**:
- `id`, `name`, `role` (NPC | PLAYER)
- `traits`: list[str] — 性格特征，影响LLM对话风格
- `stats`: dict[str, int] — HP、trust等数值属性
- `inventory`: list[str] — 持有物品
- `location_id`: str — 当前位置

**Location (地点)**:
- `id`, `name`, `description`
- `exits`: dict[str, Exit] — 相邻地点及锁定状态
- `items`: list[str] — 场景中的物品
- `npcs`: list[str] — 场景中的NPC

**Item (物品)**:
- `id`, `name`, `description`
- `portable`: bool — 可否拾取
- `usable_with`: list[str] — 可交互目标（如钥匙→门）

**Relationship (关系边)**:
- `source`, `target` — 角色ID
- `type`: TRUST | FEAR | HOSTILITY | ALLIANCE
- `value`: int (-100 ~ 100)

**Event (事件记录)**:
- `id`, `timestamp` (游戏回合数), `type`, `actor`
- `description`: 事件描述
- `consequences`: list[str] — 副作用

### 3.2 奇幻酒馆地图

5个区域:
- **酒馆大厅**: 主入口，旅行者NPC
- **吧台区**: 核心交互区，酒保格里姆NPC
- **地下室**: 需要钥匙，隐藏密道入口
- **客房走廊**: 支线探索，神秘旅客NPC
- **后院**: 可选区域，废弃马车（备用钥匙）

### 3.3 存档格式

JSON结构，包含:
- `save_version`: 版本号
- `turn`: 当前回合数
- `player`: 位置、背包、属性
- `world`: 场景状态（门锁、NPC状态）
- `relationships_snapshot`: 关系图快照（NetworkX node_link_data序列化）
- `quests`: 任务进度
- `timeline`: 事件时间线
- `skills_state`: Skill系统状态
  - `unlocked`: list[str] — 已解锁的Skill ID列表
  - `dynamic_facts`: dict[str, list[str]] — 运行时通过teach()追加的facts，key=skill_id

---

## 4. 交互机制

### 4.1 CLI界面布局 (Rich)

三区布局:
- **顶部状态栏**: 当前位置 | HP/Gold/背包 | 回合数
- **中间叙事区**: 场景描述 + NPC对话 + 环境线索
- **底部输入区**: 提示符 `▸` + 玩家输入

### 4.2 命令体系

**系统命令** (硬编码处理，不经过LLM):
- `continue` — 剧情自动推进（系统回合），跳过意图解析层，直接由剧情引擎(StoryEngine)查询当前最高优先级的待触发节点，生成系统ActionResult后交给叙事层
- `undo` — 回退上一步（StateManager.undo()恢复上一轮WorldState快照）
- `retry` — 重新生成本轮叙事：先从当前WorldState.last_action暂存本轮ActionResult，再执行undo()回退状态，最后用暂存的ActionResult重新调用叙事生成层（LLM重新生成，因temperature > 0会产生不同文本）
- `save [名称]` / `load [名称]` — 存档/读档
- `look` — 查看环境
- `inventory` — 查看背包
- `status` — 角色状态
- `hint` — 获取提示
- `help` — 命令帮助

**自由输入**: 所有非系统命令的输入统一交给LLM意图分类处理。

### 4.3 意图解析 (LLM统一解析)

所有玩家自由输入统一走LLM意图分类:

1. 玩家输入 → LLM意图分类（Structured Output JSON）
2. 返回 `ActionRequest {action, target, detail, confidence}`
3. 交给规则引擎验证
4. 验证通过 → LLM叙事生成

**意图分类Prompt**:
- System: 游戏意图解析器角色
- 注入当前场景实体列表（NPC、物品、出口）
- few-shot示例引导
- 输出JSON: `{action, target, detail, confidence}`

**成本优化**: 意图分类用轻量模型 (gpt-4o-mini / haiku)，叙事生成用强模型 (gpt-4o / sonnet)。

### 4.4 动作类型

| 类别 | 动作 | 说明 |
|------|------|------|
| 移动 | MOVE, LOOK, SEARCH | 移动、观察、搜索隐藏物品 |
| 交互 | TALK, PERSUADE, TRADE | 对话、说服、交易 |
| 物品 | TAKE, USE, GIVE | 拾取、使用、给予 |
| 特殊 | STEALTH, COMBAT, CUSTOM | 潜行、战斗(后期)、LLM兜底 |

---

## 5. 剧情控制与叙事策略

### 5.1 三层叙事结构

**主线剧情** (设计者预设): 不可跳过的关键节点，因果链驱动
- 进入酒馆 → 获取地下室线索 → 找到钥匙 → 发现密道秘密

**支线故事** (条件触发): 丰富世界，可选但有奖励
- 帮助旅行者（奖励: 地图碎片）
- 神秘旅客的委托（奖励: 隐藏结局）
- 后院废弃马车（奖励: 备用钥匙/主线捷径）

**动态生成** (LLM实时创作): NPC对话、环境描写、随机事件、失败叙事

### 5.2 剧情节点定义 (YAML)

每个节点包含:
- `id`, `type` (main/side), `description`
- `trigger`: 触发条件（复用Skill的`ActivationCondition`结构化条件模型，支持 `any_of` 多路径触发。StoryEngine和SkillManager共用同一套`ConditionEvaluator`）
- `effects`: 副作用（添加事件、修改NPC状态、给予物品等）
- `narrator_hint`: 指导LLM生成风格
- `fail_forward`: 超时回合数 + 降级事件，避免死胡同

### 5.3 叙事控制机制

**硬性约束**:
- 世界物理规则不可违反
- 主线节点按因果链推进
- 锁定条件未满足时拒绝操作
- NPC知识边界（由SkillManager激活机制保障——未激活Skill的facts不进入Prompt，behavior.forbidden显式约束禁止透露内容）

**软性引导**:
- NPC对话暗示方向
- 环境描写突出线索
- hint命令提供非强制建议
- 长时间无进展触发过渡事件
- Fail Forward机制

**连贯性保障**:
- 事件时间线供LLM参考
- NPC记住交互历史
- 伏笔回收
- 变量填充（角色名/物品名）
- Prompt注入世界状态摘要

### 5.4 叙事生成Prompt结构

```
[System] 叙事风格指令（第二人称、沉浸式）
[World State Summary] 地点、时间、氛围、NPC状态、玩家背包
[Recent Timeline] 最近3-5个事件
[Active Skills] 当前NPC已激活的Skill内容（facts + behavior指令）
[Story Node Hint] 当前主线节点的narrator_hint
[Action] 本轮动作和规则验证结果
[Output Requirements] 字数限制、内容要求
```

---

## 6. LLM多后端适配器

> 详细类设计、方法签名、错误处理策略见 [2.2.3 LLM适配器](#223-llm适配器-llm)

### 6.1 统一接口 (Protocol)

```python
class LLMAdapter(Protocol):
    """底层适配器 — 每个provider实现一次"""
    async def complete(self, messages: list[Message], response_format: type[T] | None = None) -> T | str
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]

class LLMService:
    """业务层 — 组合intent + narrative两个适配器实例"""
    async def classify_intent(self, input: str, context: SceneContext) -> ActionRequest
    async def generate_narrative(self, action: ActionResult, state: WorldState, memory: MemoryContext) -> str
    async def stream_narrative(self, action: ActionResult, state: WorldState, memory: MemoryContext) -> AsyncIterator[str]
```

### 6.2 后端实现

| 后端 | 适用模型 | 实现阶段 |
|------|----------|----------|
| OpenAI | gpt-4o, gpt-4o-mini | P1 |
| Anthropic | claude-sonnet-4-6, claude-haiku-4-5 | P4 |
| Ollama | llama3, qwen2 等 | P4 |

### 6.3 配置

YAML配置文件，意图分类和叙事生成可指定不同provider/model/参数。支持流式输出和配置热加载。完整配置示例:

```yaml
llm:
  intent:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1
    max_tokens: 200
    max_retries: 3
    timeout: 10.0
  narrative:
    provider: anthropic
    model: claude-sonnet-4-6
    temperature: 0.8
    max_tokens: 500
    max_retries: 2
    timeout: 30.0
    stream: true

game:
  auto_save_interval: 5
  undo_history_size: 50
  save_dir: ./saves

debug:
  show_intent_json: false
  show_prompt: false
  log_level: INFO
```

---

## 7. MVP分阶段交付

### Phase 1 — 核心骨架
- 项目结构搭建（Python包、依赖管理）
- Rich CLI界面（三区布局、输入/输出循环）
- 世界模型（Character, Location, Item 数据类）
- LLM适配器接口 + OpenAI实现
- 意图解析层（LLM分类 → ActionRequest）
- 基础规则引擎（位置移动、物品交互验证）
- **交付物**: 可以在酒馆里移动、观察、拾取物品

### Phase 2 — 对话与叙事
- NPC对话系统（关系值影响对话风格）
- LLM叙事生成 + 流式输出（打字机效果）
- Prompt模板管理（场景描写、对话、引导）
- 记忆系统（事件时间线 + SkillManager知识模块加载）
- 系统命令实现（look/inventory/status/hint/help）
- **交付物**: 可以和NPC自由对话，感受AI叙事

### Phase 3 — 剧情与存档
- 剧情节点引擎（YAML定义、条件触发）
- 主线任务：酒馆地下室之谜（完整可通关）
- 存档/读档功能（JSON序列化）
- continue/undo/retry 游戏控制命令
- Fail Forward机制（超时推进）
- **交付物**: 完整可通关的酒馆故事体验

### Phase 4 — 扩展与打磨
- 支线任务（帮助旅行者、神秘旅客委托）
- Anthropic / Ollama 后端适配器
- 关系图可视化（status命令增强）
- 多结局系统
- 世界配置模块化（支持加载不同故事）
- **交付物**: 多后端、多结局、可扩展的完整游戏

---

## 8. 项目目录结构

```
chatbot/
├── pyproject.toml
├── config.yaml
├── src/
│   └── tavern/
│       ├── __main__.py
│       ├── cli/
│       │   ├── app.py
│       │   └── renderer.py
│       ├── parser/
│       │   └── intent.py
│       ├── engine/
│       │   ├── rules.py
│       │   ├── story.py
│       │   └── actions.py
│       ├── narrator/
│       │   ├── narrator.py
│       │   └── prompts.py
│       ├── world/
│       │   ├── models.py
│       │   ├── state.py
│       │   ├── memory.py
│       │   └── skills.py              # SkillManager — YAML Skill加载、条件求值、Prompt注入
│       └── llm/
│           ├── adapter.py
│           ├── openai_llm.py
│           ├── claude_llm.py
│           └── ollama_llm.py
├── data/
│   └── scenarios/
│       └── tavern/
│           ├── world.yaml
│           ├── story.yaml
│           ├── characters.yaml
│           └── skills/              # NPC知识与行为Skill模块
│               ├── bartender_gossip.yaml
│               ├── bartender_cellar_secret.yaml
│               ├── bartender_town_history.yaml
│               ├── traveler_quest_info.yaml
│               └── mysterious_guest_hint.yaml
├── saves/
├── tests/
└── docs/
```

---

## 9. 测试策略

- **单元测试**: 世界模型、规则引擎、意图解析（mock LLM）
- **集成测试**: 管道端到端（输入→解析→规则→叙事）
- **E2E测试**: 完整游戏流程（自动化脚本模拟玩家）
- **目标覆盖率**: 80%+
