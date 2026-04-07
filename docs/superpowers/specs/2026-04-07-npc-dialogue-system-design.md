# NPC 对话系统设计规格 — Phase 2a

**日期**: 2026-04-07
**状态**: 已批准
**范围**: NPC 多轮对话系统，含关系值影响、对话历史管理、退出摘要

---

## 1. 概述

为酒馆 CLI 互动小说添加 NPC 对话系统。玩家通过 `talk <npc>` 进入多轮对话模式，与 NPC 自由交流。关系值（trust）影响 NPC 的语气和愿意分享的信息深度。退出对话时 LLM 生成摘要，作为跨会话记忆存入游戏状态。

### 设计目标

- 沉浸式多轮对话体验
- 关系值动态影响 NPC 行为
- Token 消耗可控（会话内完整历史 + 退出后摘要压缩）
- 与现有不可变状态架构一致

---

## 2. 架构

### 2.1 方案选择

**方案 A（已选）：独立 DialogueManager 模块**

新建 `src/tavern/dialogue/` 模块，独立管理对话状态机。RulesEngine 负责触发进入对话，DialogueManager 负责对话生命周期。

选择理由：
- RulesEngine 已 292 行，不宜继续膨胀
- 对话逻辑与游戏规则解耦，便于独立测试
- 符合现有分层架构（parser → engine → narrator）

### 2.2 模块结构

```
src/tavern/dialogue/
├── __init__.py
├── manager.py       # DialogueManager — 对话生命周期管理
├── context.py       # DialogueContext, Message, DialogueResponse, DialogueSummary
└── prompts.py       # 语气模板 + prompt 组装
```

### 2.3 状态机

```
EXPLORING ──talk/persuade npc──> DIALOGUE ──bye/leave──> EXPLORING
                                     │
                              (每轮 respond)
                                     │
                            NPC wants_to_end ──> EXPLORING
                                     │
                            超过 20 轮 ──> 强制结束
```

---

## 3. 数据模型

所有模型遵循项目不可变约定（frozen dataclass 或 frozen Pydantic BaseModel）。

### 3.1 Message

```python
@dataclass(frozen=True)
class Message:
    role: str           # "player" | "npc"
    content: str
    trust_delta: int    # 该轮关系值变化（player 消息为 0）
    turn: int           # 游戏回合数
```

### 3.2 DialogueContext

```python
@dataclass(frozen=True)
class DialogueContext:
    npc_id: str
    npc_name: str
    npc_traits: tuple[str, ...]
    trust: int                          # 运行时关系值（初始值 + 累计 trust_delta）
    tone: str                           # "hostile" | "neutral" | "friendly"
    messages: tuple[Message, ...]       # 完整对话历史
    location_id: str                    # 对话发生地点
    turn_entered: int                   # 进入对话时的游戏回合
```

### 3.3 DialogueResponse

```python
@dataclass(frozen=True)
class DialogueResponse:
    text: str              # NPC 回复文本
    trust_delta: int       # 本轮关系值变化，clamp to [-5, +5]
    mood: str              # NPC 当前情绪（供渲染用）
    wants_to_end: bool     # NPC 是否想结束对话
```

### 3.4 DialogueSummary

```python
@dataclass(frozen=True)
class DialogueSummary:
    npc_id: str
    summary_text: str              # LLM 生成的摘要文本
    total_trust_delta: int         # 累计关系变化
    key_info: tuple[str, ...]      # 提取的关键信息点
    turns_count: int               # 对话轮次数
```

---

## 4. 核心组件

### 4.1 DialogueManager

```python
class DialogueManager:
    _active: DialogueContext | None     # None = 不在对话模式
    _llm_service: LLMService

    async def start(self, state: WorldState, npc_id: str) -> tuple[DialogueContext, DialogueResponse]
    async def respond(self, ctx: DialogueContext, player_input: str, state: WorldState) -> tuple[DialogueContext, DialogueResponse]
    async def end(self, ctx: DialogueContext) -> DialogueSummary

    @property
    def is_active(self) -> bool
```

**start(state, npc_id)**:
1. 验证 NPC 存在且与玩家在同一地点
2. 从 NPC stats 读取当前 trust 值
3. 通过 `resolve_tone(trust)` 确定语气档位
4. 查询 WorldState events 中该 NPC 的历史对话摘要，注入到 prompt
5. 调用 LLM 生成 NPC 开场白
6. 返回初始 DialogueContext + 开场白 DialogueResponse

**respond(ctx, player_input, state)**:
1. 检查是否超过 20 轮上限，超过则返回 wants_to_end=True
2. 追加玩家消息到 messages
3. 组装 prompt（system prompt + 完整 messages 历史）
4. 调用 LLM，解析 JSON 响应
5. Clamp trust_delta 到 [-5, +5]
6. 构造新 DialogueContext（更新 messages 和 trust）
7. 返回新 context + DialogueResponse

**end(ctx)**:
1. 调用 LLM 生成对话摘要
2. 计算 total_trust_delta（累加所有轮次）
3. 提取 key_info
4. 返回 DialogueSummary

### 4.2 Prompt 混合方案

#### 语气模板（3 档）

| trust 范围 | tone | 描述 |
|-----------|------|------|
| ≤ -20 | hostile | 敌意、冷淡、不主动提供信息 |
| -19 ~ 19 | neutral | 中立、回答基本问题、不分享秘密 |
| ≥ 20 | friendly | 友好、热情、愿意分享秘密 |

#### System Prompt 组装

```python
def build_dialogue_prompt(ctx: DialogueContext, state: WorldState, history_summaries: tuple[str, ...]) -> str:
```

Prompt 包含以下部分：
1. **角色定义**：NPC 名字、性格特征
2. **场景信息**：当前位置名称
3. **语气指令**：根据 tone 选择的模板文本
4. **关系状态**：trust 数值 + 定性描述
5. **历史摘要**：之前对话的摘要（如有）
6. **回复格式**：JSON schema 约束（text, trust_delta, mood, wants_to_end）
7. **trust_delta 规则**：范围 [-5, +5]，正/负值触发条件
8. **行为约束**：保持角色一致性、回复长度 2-4 句、反复骚扰时 wants_to_end

#### 摘要 Prompt

```
请用1-2句话总结以下对话的关键信息，重点记录：
- 玩家获得的重要线索
- NPC透露的秘密
- 关系变化的关键转折点
不需要描述对话过程，只提炼对游戏进展有用的信息。
同时以 JSON 数组提取关键信息点。
```

---

## 5. GameApp 集成

### 5.1 输入路由改动

`GameApp._process_input()` 增加对话模式分支：

```
if dialogue_manager.is_active:
    if input in ("bye", "leave", "再见", "离开"):
        → end dialogue → apply trust delta → add summary event
    else:
        → dialogue_manager.respond()
        → render dialogue response
        → if wants_to_end: end dialogue
    return

# 正常模式
intent = parser.parse(input)
if intent.action in (TALK, PERSUADE):
    → dialogue_manager.start(state, intent.target)
    → render dialogue start
    return

# 其他动作走原有流程
```

### 5.2 关系值写入

退出对话时，通过 StateDiff 更新 NPC 的 trust：

```python
npc = state.characters[summary.npc_id]
new_trust = clamp(npc.stats["trust"] + summary.total_trust_delta, -100, 100)
new_stats = {**dict(npc.stats), "trust": new_trust}
updated_npc = Character(... stats=new_stats ...)
diff = StateDiff(updated_characters=(updated_npc,))
state_manager.commit(diff, "dialogue_end")
```

### 5.3 摘要事件写入

```python
event = Event(
    id=f"dialogue_{npc_id}_{turn}",
    turn=current_turn,
    type="dialogue_summary",
    actor=npc_id,
    description=summary.summary_text,
    consequences=tuple(summary.key_info),
)
diff = StateDiff(added_events=(event,))
state_manager.commit(diff, "dialogue_summary")
```

---

## 6. RulesEngine 扩展

为 TALK 和 PERSUADE 注册 handler：

```python
def _handle_talk(request, state) -> ActionResult:
    npc_id = request.target
    # 验证 NPC 存在于当前地点
    player = _find_player(state)
    location = state.locations[player.location_id]
    if npc_id not in location.npcs:
        return ActionResult(success=False, message=f"这里没有 {npc_id}")
    return ActionResult(success=True, action=ActionType.TALK, target=npc_id,
                        message=f"你走向{state.characters[npc_id].name}，准备交谈。")
```

handler 返回 success=True 后，GameApp 负责调用 DialogueManager.start()。

PERSUADE 复用 TALK handler，区别在 prompt 中注入"玩家正在尝试说服"的上下文。

---

## 7. Renderer 扩展

### 新增方法

| 方法 | 功能 |
|------|------|
| `render_dialogue_start(ctx, response)` | 显示进入对话面板：NPC 名字、语气指示、开场白、退出提示 |
| `render_dialogue(response)` | 显示 NPC 回复 + 情绪 + 关系变化指示（↑+3 / ↓-2） |
| `render_dialogue_end(summary)` | 显示退出对话摘要 + 累计关系变化 |

### 视觉区分

- 对话模式输入提示符：`对话▸`（替代正常模式的 `▸`）
- NPC 回复使用 Rich Panel，标题为 NPC 名字
- 关系变化使用颜色：正值绿色、负值红色

---

## 8. LLMService 扩展

`LLMService` 新增两个方法：

```python
async def generate_dialogue(self, system_prompt: str, messages: list[dict]) -> DialogueResponse:
    """调用 narrative adapter 生成对话回复，解析 JSON 响应"""

async def generate_summary(self, dialogue_messages: list[dict]) -> dict:
    """调用 intent adapter（轻量模型）生成对话摘要"""
```

- 对话生成使用 narrative adapter（gpt-4o, temperature 0.8）
- 摘要生成使用 intent adapter（gpt-4o-mini, temperature 0.1）

---

## 9. 错误处理

| 场景 | 处理方式 |
|------|---------|
| NPC 不在当前地点 | RulesEngine 返回 ActionResult(success=False) |
| target 不是 NPC（是物品或不存在） | RulesEngine 验证失败 |
| LLM 返回非 JSON | 使用默认回复（"...沉默不语"）+ trust_delta=0 |
| LLM JSON 缺少字段 | 填充默认值（text="...", trust_delta=0, mood="neutral", wants_to_end=False） |
| trust_delta 超出 [-5, +5] | clamp 强制限制 |
| 对话超过 20 轮 | 强制 wants_to_end=True |
| LLM 调用超时/失败 | 返回默认回复，不中断对话 |
| 摘要生成失败 | 使用固定格式摘要（"与 NPC 进行了 N 轮对话"） |

---

## 10. 测试计划

### 10.1 单元测试

| 文件 | 测试内容 | 预计测试数 |
|------|---------|-----------|
| `tests/dialogue/test_context.py` | DialogueContext/Message/DialogueResponse/DialogueSummary 创建、不可变性 | 6 |
| `tests/dialogue/test_prompts.py` | resolve_tone 阈值、build_dialogue_prompt 输出、TONE_TEMPLATES 完整性 | 5 |
| `tests/dialogue/test_manager.py` | start 验证、respond 多轮、trust clamp、20 轮上限、end 摘要、LLM 错误回退 | 10 |

### 10.2 集成测试

| 文件 | 测试内容 | 预计测试数 |
|------|---------|-----------|
| `tests/engine/test_rules.py` | TALK/PERSUADE handler（NPC 在场/不在场） | 3 |
| `tests/cli/test_app_dialogue.py` | 完整对话流程：进入→多轮→退出、trust 写入 state、summary event 写入 | 4 |
| `tests/test_integration.py` | E2E 对话场景 | 2 |

**预计新增测试：30 个**

### 10.3 覆盖率目标

新模块 ≥ 85%，整体项目保持 ≥ 80%。

---

## 11. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/dialogue/__init__.py` | 0 |
| 新建 | `src/tavern/dialogue/context.py` | ~40 |
| 新建 | `src/tavern/dialogue/prompts.py` | ~80 |
| 新建 | `src/tavern/dialogue/manager.py` | ~120 |
| 修改 | `src/tavern/cli/app.py` | +~40 |
| 修改 | `src/tavern/cli/renderer.py` | +~30 |
| 修改 | `src/tavern/engine/rules.py` | +~20 |
| 修改 | `src/tavern/llm/service.py` | +~30 |
| 新建 | `tests/dialogue/test_context.py` | ~60 |
| 新建 | `tests/dialogue/test_prompts.py` | ~50 |
| 新建 | `tests/dialogue/test_manager.py` | ~120 |
| 修改 | `tests/engine/test_rules.py` | +~30 |
| 新建 | `tests/cli/test_app_dialogue.py` | ~80 |
| 修改 | `tests/test_integration.py` | +~40 |

**新增代码约 ~270 行，测试约 ~380 行**

---

## 12. 不在范围内

以下功能不在本 spec 范围，将在后续子系统中处理：

- LLM 流式输出 / 打字机效果（Phase 2 - LLM叙事+流式子系统）
- Prompt 模板管理系统（Phase 2 - Prompt模板子系统）
- EventTimeline / RelationshipGraph（Phase 2 - 记忆系统子系统）
- 系统命令完善 look/inventory/status/hint/help（Phase 2 - 系统命令子系统）
- TRADE/GIVE/USE/COMBAT action handlers（后续功能迭代）
- 存档/读档（Phase 3）
