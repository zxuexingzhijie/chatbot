# Phase 3: FSM 集成设计

> 前置: [Phase 1](./2026-04-10-claude-code-patterns-design.md) (FSM/CommandRegistry/ReactiveStore/SeededRNG) + Phase 2 (ActionDef/ActionRegistry/KeybindingResolver/Bootstrap) 已完成。

## 目标

将 Phase 1-2 构建的新架构接入 `app.py`，使游戏实际通过 `GameLoop` + `ModeHandler` 运行。完成后 `GameApp` 从 666 行瘦身到 ~150 行，探索和对话两个核心循环走新架构。

## 完成标准

- `GameApp.run()` 内部调用 `GameLoop.run()`，旧的 if/elif 模式分发删除
- 玩家可以正常进行 探索（自由文本输入 → 意图解析 → 行动 → 叙事）和 对话（LLM 对话 → trust → 退出）循环
- 所有现有测试通过

---

## §1 类型统一 — 删除 CommandContext

### 改动

1. 删除 `commands.py` 中的 `CommandContext` dataclass
2. `CommandRegistry.handle_command()` 的 `ctx` 参数类型改为 `ModeContext`（从 `fsm.py` 导入）
3. `command_defs.py` 中所有命令函数的 `ctx` 参数类型改为 `ModeContext`
4. `ModeContext.action_registry` 类型从 `Any` 收紧为 `ActionRegistry | None`
5. 所有引用 `CommandContext` 的测试改为构造 `ModeContext`

### 不改

- 不给 renderer、narrator 等定义 Protocol（只有一个实现，YAGNI）
- 不改 `ModeHandler.handle_input` 签名（已经用 `ModeContext`）

---

## §2 Effect Executor 补齐

只补 Exploring + Dialogue 实际触发的 5 个，其余保持 log stub。

| Effect | 实现内容 |
|--------|----------|
| `APPLY_DIFF` | 已实现，不动 |
| `START_DIALOGUE` | 初始化 dialogue_manager 会话上下文（设当前 NPC、清对话历史） |
| `END_DIALOGUE` | 调 dialogue_manager.reset()，清理对话状态 |
| `APPLY_TRUST` | 构造 StateDiff 更新 NPC trust 值，调 state_manager.commit() |
| `EMIT_EVENT` | 调 story_engine 检查事件触发条件（story_engine 存在时） |

每个 executor < 20 行，纯副作用执行，不含业务判断。

INIT_COMBAT / APPLY_REWARDS / FLEE_PENALTY / OPEN_SHOP 保持 log stub。

---

## §3 ExploringModeHandler 迁移

将 `app.py._handle_free_input()` 逻辑迁移到 `ExploringModeHandler.handle_input()` 的自由文本分支。

### 流程

```
用户输入（非 / 命令）
    │
    ▼
1. intent_parser.parse(input, state) → ParsedIntent
    │
    ▼
2. action_registry.validate_and_execute(intent, state)
   → (ActionResult, StateDiff | None)
    │
    ▼
3. 构造 side_effects:
   - 有 StateDiff → SideEffect(APPLY_DIFF, {diff, action})
   - 触发对话 → SideEffect(START_DIALOGUE, {npc_id})
   - story 事件 → SideEffect(EMIT_EVENT, {event})
    │
    ▼
4. narrator.narrate(action_result, state) → 叙事文本
   renderer.render_narrative(text)
    │
    ▼
5. 返回 TransitionResult(
       next_mode=DIALOGUE if 开始对话 else None,
       side_effects=(...)
   )
```

### 原则

- Handler 不直接改状态，所有变更通过 APPLY_DIFF effect
- intent parser 返回 UNKNOWN → renderer 显示"我不明白你想做什么"，返回空 TransitionResult
- Handler 职责：解析意图 → 验证执行 → 生成叙事 → 声明副作用

---

## §4 DialogueModeHandler 迁移

将 `app.py._process_dialogue_input()` 逻辑迁移。

### 架构：共享 Context + Handler 自持专属依赖

```python
class DialogueModeHandler:
    def __init__(self, dialogue_manager: DialogueManager):
        self._dm = dialogue_manager
```

ModeContext 放通用服务，模式专属依赖通过 handler 构造函数注入。这个模式适用于未来所有 mode handler（CombatModeHandler 注入 CombatEngine 等）。

### handle_input 流程

```
用户输入（非 / 命令）
    │
    ▼
1. dialogue_manager.send_message(input, state)
   → DialogueResponse(text, hints, trust_delta, wants_end)
    │
    ▼
2. renderer.render_dialogue(npc_name, response.text, response.hints)
    │
    ▼
3. 构造 side_effects:
   - trust_delta != 0 → SideEffect(APPLY_TRUST, {npc_id, delta})
   - wants_end → SideEffect(END_DIALOGUE, {npc_id})
    │
    ▼
4. 返回 TransitionResult(
       next_mode=EXPLORING if wants_end else None,
       side_effects=(...)
   )
```

### Escape 退出

keybinding 解析到 escape → 直接返回 `TransitionResult(next_mode=EXPLORING, side_effects=(SideEffect(END_DIALOGUE, ...),))`

---

## §5 GameApp 渐进集成

### 改动

1. `__init__` 末尾调用 `bootstrap()` 构造 `GameLoop`，保存为 `self._game_loop`
2. `run()` 替换为调用 `self._game_loop.run()`，删除原 while 循环和 if/elif 分发
3. 保留 `__init__` 的初始化逻辑（加载场景、创建服务实例）— 这些是 `bootstrap()` 的输入
4. 删除 `_handle_system_command()`、`_handle_free_input()`、`_process_dialogue_input()` 等已迁移方法
5. `_apply_story_results()` 的 story 事件检查逻辑迁移到 ExploringModeHandler（步骤 3 的 EMIT_EVENT 生成），叙事渲染部分由 EMIT_EVENT executor 调用 story_engine 处理。GameApp 中该方法删除

### GameApp 最终形态

```python
class GameApp:
    def __init__(self, scenario_path, ...):
        # 初始化所有服务（~120行，基本不变）
        ...
        # 构造 GameLoop
        self._game_loop = bootstrap(
            state_manager=self.state_manager,
            renderer=self.renderer,
            narrator=self.narrator,
            dialogue_manager=self.dialogue_manager,
            ...
        )

    async def run(self):
        self.renderer.render_welcome(...)
        await self._game_loop.run()
```

从 666 行瘦到 ~150 行。

---

## 依赖顺序

```
§1 类型统一
    │
    ▼
§2 Effect Executor 补齐
    │
    ▼
§3 ExploringModeHandler ──┐
                          ├─→ §5 GameApp 集成
§4 DialogueModeHandler ───┘
```

§3 和 §4 互相独立，可以并行。§5 依赖 §3 + §4 完成。

---

## 不在范围

- COMBAT / INVENTORY / SHOP mode handler 实现
- KeybindingResolver 接入 prompt_toolkit
- §3/8/9/10（Markdown 内容、JSONL 日志、记忆系统、场景缓存）
- renderer / narrator 的 Protocol 定义
- 对 COMBAT/SHOP 相关 effect executor 的实现
