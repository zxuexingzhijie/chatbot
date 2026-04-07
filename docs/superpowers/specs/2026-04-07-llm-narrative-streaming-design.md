# LLM叙事生成 + 流式输出 — Phase 2b 设计规格

**日期**: 2026-04-07
**状态**: 已批准
**范围**: 所有成功行动触发 LLM 叙事生成，流式打字机效果渲染；失败行动保持规则引擎消息

---

## 1. 概述

为酒馆 CLI 游戏添加叙事生成层。玩家每次成功行动后，不再显示规则引擎的硬编码文本，而是由 LLM 流式生成 2-3 句沉浸式场景描写。对话模式（DialogueManager 激活时）不触发叙事层，保持现有对话渲染。

### 设计目标

- 所有成功行动（MOVE / LOOK / TAKE / TALK 验证后 / 等）触发叙事生成
- 流式打字机效果（逐 chunk 输出，无等待感）
- LLM 失败时自动降级到规则引擎消息，不中断游戏
- Prompt 模板集中管理，按 ActionType 区分风格

---

## 2. 架构

### 2.1 数据流

```
玩家输入
  → IntentParser → ActionRequest
  → RulesEngine.validate() → ActionResult

  if success:
    → Narrator.stream_narrative(result, state)
        → build_narrative_prompt(ctx) → messages
        → LLMService.stream_narrative(system, action_msg) → AsyncIterator[str]
        → Renderer.render_stream(iterator)    ← 打字机效果
  else:
    → Renderer.render_result(result)          ← 规则引擎消息

对话模式（dialogue_manager.is_active）:
  → 现有 DialogueManager 流程，不经过 Narrator
```

### 2.2 模块结构

```
src/tavern/narrator/
├── __init__.py
├── prompts.py       # NarrativeContext + NARRATIVE_TEMPLATES + build_narrative_prompt()
└── narrator.py      # Narrator 类
```

---

## 3. 数据模型

### 3.1 NarrativeContext

```python
@dataclass(frozen=True)
class NarrativeContext:
    action_type: str       # ActionType 的 value，如 "move" | "look" | "take"
    action_message: str    # 规则引擎原始消息（「发生了什么」的事实依据）
    location_name: str     # 当前地点名称
    location_desc: str     # 地点描述
    player_name: str       # 玩家角色名
    target: str | None     # 行动目标（物品名 / NPC 名，无则 None）
```

---

## 4. 核心组件

### 4.1 `narrator/prompts.py`

#### NARRATIVE_TEMPLATES

按 ActionType 区分 system prompt 风格：

| ActionType | 风格指令 |
|-----------|---------|
| move | 强调进入新地点的氛围感，描写环境细节 |
| look | 侧重观察细节，描述性文字，感官体验 |
| take | 简短的拾取动作描写，带一点物品质感 |
| 其他（默认） | 通用模板，简短、第二人称、点题即止 |

所有模板共享约束：**2-3 句话，中文，第二人称（「你」），不重复行动事实**。

#### `build_narrative_prompt(ctx: NarrativeContext) -> list[dict]`

返回 `[{"role": "system", "content": ...}, {"role": "user", "content": ...}]`：

- system：角色定义（奇幻小说叙述者）+ 对应 ActionType 的风格指令 + 格式约束
- user：`ctx.action_message`（规则引擎消息，作为叙事的事实基础）+ 地点/目标上下文

### 4.2 `narrator/narrator.py` — `Narrator`

```python
class Narrator:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def stream_narrative(
        self, result: ActionResult, state: WorldState
    ) -> AsyncIterator[str]:
        """
        构建 NarrativeContext → 组装 Prompt → 调用 LLMService.stream_narrative()
        LLM 失败时 yield result.message 作为降级内容
        """
```

**`_build_context(result, state) -> NarrativeContext`**：
- 从 `state` 提取 player、location
- 若 `result.target` 是 NPC ID，转换为 NPC name；若是物品 ID，转换为物品 name
- 组装并返回 `NarrativeContext`

**失败降级**：
- `try: async for chunk in stream: yield chunk`
- `except Exception: yield result.message`（完整消息一次性输出）

### 4.3 `LLMService` 扩展

新增方法：
```python
async def stream_narrative(
    self, system_prompt: str, action_message: str
) -> AsyncIterator[str]:
    """使用 narrative adapter 的 stream() 接口"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": action_message},
    ]
    async for chunk in self._narrative.stream(messages):
        yield chunk
```

### 4.4 `Renderer` 扩展

新增方法：
```python
async def render_stream(self, stream: AsyncIterator[str]) -> None:
    """
    打字机效果：逐 chunk 输出到 console
    流结束后补一个空行
    流中断时补换行，静默继续
    """
```

实现：使用 Rich `Console` 的 `print(chunk, end="", highlight=False)` 逐块输出，完成后 `print()` 补空行。

### 4.5 `GameApp` 集成

**`__init__`** 新增：
```python
self._narrator = Narrator(llm_service=llm_service)
```

**`_handle_free_input`** 修改叙事触发逻辑：
```python
if result.success and not self._dialogue_manager.is_active:
    await self._renderer.render_stream(
        self._narrator.stream_narrative(result, self.state)
    )
else:
    self._renderer.render_result(result)
```

对话模式下（`is_active=True`）：TALK/PERSUADE 成功后进入 DialogueManager，不触发叙事层。

---

## 5. 错误处理

| 场景 | 处理方式 |
|------|---------|
| LLM 调用超时 / 网络错误 | Narrator 捕获异常，yield `result.message` 降级 |
| 流式输出中断（半途异常） | 已输出文字保留，`Renderer.render_stream` 补换行，静默继续 |
| LLM 返回空流 | render_stream 只输出空行，游戏正常继续 |
| 对话模式中不触发叙事 | `_handle_free_input` 通过 `dialogue_manager.is_active` 判断跳过 |

---

## 6. 测试计划

### 6.1 单元测试

| 文件 | 测试内容 | 预计数量 |
|------|---------|---------|
| `tests/narrator/test_prompts.py` | `build_narrative_prompt` 包含地点名、action_message；不同 ActionType 使用不同模板；NarrativeContext 创建与不可变性 | 6 |
| `tests/narrator/test_narrator.py` | `stream_narrative` 正确构建 context、传递给 LLM；降级路径（LLM 异常 → yield message）；target ID 转换为名称 | 5 |
| `tests/cli/test_renderer.py` | `render_stream` 消费所有 chunk；流中断时补换行 | 3 |

### 6.2 LLMService 测试

| 文件 | 测试内容 | 预计数量 |
|------|---------|---------|
| `tests/llm/test_service_narrative.py` | `stream_narrative` 使用 narrative adapter；正确传递 system_prompt 和 action_message | 2 |

**预计新增测试：16 个**

### 6.3 覆盖率目标

新模块 `narrator/` ≥ 85%，整体项目保持 ≥ 80%。

---

## 7. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/narrator/__init__.py` | 0 |
| 新建 | `src/tavern/narrator/prompts.py` | ~70 |
| 新建 | `src/tavern/narrator/narrator.py` | ~70 |
| 修改 | `src/tavern/llm/service.py` | +~15 |
| 修改 | `src/tavern/cli/renderer.py` | +~15 |
| 修改 | `src/tavern/cli/app.py` | +~10 |
| 新建 | `tests/narrator/__init__.py` | 0 |
| 新建 | `tests/narrator/test_prompts.py` | ~80 |
| 新建 | `tests/narrator/test_narrator.py` | ~90 |
| 新建 | `tests/llm/test_service_narrative.py` | ~40 |
| 修改 | `tests/cli/test_renderer.py` | +~30 |

**新增代码约 ~180 行，测试约 ~240 行**

---

## 8. 不在范围内

- MemorySystem 集成（记忆上下文注入 Prompt）— Phase 2c
- 对话模式内的叙事增强 — Phase 2c
- Anthropic / Ollama 后端适配器 — Phase 4
- 存档/读档 — Phase 3
