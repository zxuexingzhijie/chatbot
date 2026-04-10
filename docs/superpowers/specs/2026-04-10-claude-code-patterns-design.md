# 从 Claude Code 借鉴的架构设计方案

> 日期: 2026-04-10
> 状态: 草案
> 范围: 10 项设计改进，按优先级分为高/中/低三组

---

## 目录

1. [FSM 游戏模式状态机](#1-fsm-游戏模式状态机)
2. [上下文作用域快捷键系统](#2-上下文作用域快捷键系统)
3. [Markdown-as-Code 内容系统](#3-markdown-as-code-内容系统)
4. [Action 工厂模式与统一接口](#4-action-工厂模式与统一接口)
5. [极简响应式 Store](#5-极简响应式-store)
6. [命令注册表系统](#6-命令注册表系统)
7. [确定性种子生成器](#7-确定性种子生成器)
8. [Append-Only JSONL 游戏日志](#8-append-only-jsonl-游戏日志)
9. [分类记忆体系](#9-分类记忆体系)
10. [Memoized 场景上下文缓存](#10-memoized-场景上下文缓存)

---

## 1. FSM 游戏模式状态机

### 来源

Claude Code `vim/` 模块。Vim 模式用不可变状态机管理 `INSERT` / `NORMAL` 模式及 11 种子命令状态（`idle`, `count`, `operator`, `find` 等），转换函数 `transition(state, input, ctx)` 是纯函数，返回 `{ next, execute }`。

### 当前问题

`GameApp.run()` 的主循环用 if-else 区分三种模式：

```python
# app.py 当前结构
async def run(self):
    while True:
        if self.dialogue_manager.is_active:
            await self._process_dialogue_input(raw)
        elif raw.startswith("/"):
            await self._handle_system_command(raw)
        else:
            await self._handle_free_input(raw)
```

问题：
- 模式判断散落在主循环中，新增模式（战斗、商店、背包管理）需要不断加 elif
- 模式间的转换逻辑隐藏在各个处理函数内部（如对话结束后隐式回到探索模式）
- 无法对模式转换做单独的单元测试
- 同一模式下的输入解析、渲染、可用命令没有内聚

### 目标设计

引入正式的 FSM，将游戏模式作为一等公民：

```python
from enum import Enum
from dataclasses import dataclass
from typing import Protocol

class GameMode(Enum):
    EXPLORING = "exploring"
    DIALOGUE = "dialogue"
    COMBAT = "combat"
    INVENTORY = "inventory"
    SHOP = "shop"

@dataclass(frozen=True)
class TransitionResult:
    next_mode: GameMode | None       # None = 保持当前模式
    side_effects: tuple[SideEffect, ...]  # 要执行的副作用列表

class ModeHandler(Protocol):
    """每个游戏模式的处理器协议"""

    @property
    def mode(self) -> GameMode: ...

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext
    ) -> TransitionResult: ...

    def get_available_commands(self, state: WorldState) -> list[CommandInfo]: ...

    def get_prompt_config(self, state: WorldState) -> PromptConfig: ...

    def get_keybindings(self) -> list[Keybinding]: ...
```

模式转换表：

```
EXPLORING + "/talk npc"     -> DIALOGUE  (side_effect: start_dialogue)
EXPLORING + "/attack npc"   -> COMBAT    (side_effect: init_combat)
EXPLORING + "/inventory"    -> INVENTORY (side_effect: render_inventory)
DIALOGUE  + "再见"          -> EXPLORING (side_effect: end_dialogue, apply_trust)
DIALOGUE  + 对话超限         -> EXPLORING (side_effect: force_end, summary)
COMBAT    + 战斗结束         -> EXPLORING (side_effect: apply_rewards)
COMBAT    + 逃跑成功         -> EXPLORING (side_effect: flee_penalty)
INVENTORY + "/back"         -> EXPLORING (side_effect: none)
SHOP      + "/leave"        -> EXPLORING (side_effect: none)
```

主循环简化为：

```python
class GameLoop:
    def __init__(self, handlers: dict[GameMode, ModeHandler]):
        self._handlers = handlers
        self._current_mode = GameMode.EXPLORING

    async def run(self):
        while True:
            handler = self._handlers[self._current_mode]
            raw = await self.renderer.get_input(handler.get_prompt_config(state))
            result = await handler.handle_input(raw, state, context)
            for effect in result.side_effects:
                await self._execute_effect(effect)
            if result.next_mode is not None:
                self._current_mode = result.next_mode
```

### 副作用系统

副作用是命令式操作的声明式描述，使转换函数保持纯净：

```python
@dataclass(frozen=True)
class SideEffect:
    kind: str  # "start_dialogue", "apply_diff", "render", "save", ...
    payload: dict

# 示例
SideEffect(kind="start_dialogue", payload={"npc_id": "bartender_grim"})
SideEffect(kind="apply_diff", payload={"diff": state_diff})
SideEffect(kind="emit_event", payload={"event": Event(...)})
```

副作用执行器是一个注册表：

```python
EFFECT_EXECUTORS: dict[str, Callable] = {
    "start_dialogue": lambda p, ctx: ctx.dialogue_manager.start(p["npc_id"]),
    "apply_diff": lambda p, ctx: ctx.state_manager.commit(p["diff"]),
    "emit_event": lambda p, ctx: ctx.memory.timeline.append(p["event"]),
    "render": lambda p, ctx: ctx.renderer.render(p["content"]),
    "save": lambda p, ctx: ctx.persistence.auto_save(ctx.state),
}
```

### 与现有代码的集成

- `_process_dialogue_input()` 提取为 `DialogueModeHandler`
- `_handle_free_input()` 提取为 `ExploringModeHandler`
- `_handle_system_command()` 的命令分发逻辑移入各个 handler 的 `get_available_commands()` 返回值中
- `GameApp` 瘦身为 `GameLoop`，只做模式分发和副作用执行

### 测试策略

```python
def test_dialogue_to_exploring_on_farewell():
    handler = DialogueModeHandler(...)
    result = await handler.handle_input("再见", state, context)
    assert result.next_mode == GameMode.EXPLORING
    assert any(e.kind == "end_dialogue" for e in result.side_effects)
```

---

## 2. 上下文作用域快捷键系统

### 来源

Claude Code `keybindings/` 模块。按键绑定按 context 分组（`Global`, `Chat`, `Settings`, `Confirmation` 等），同一按键在不同上下文有不同行为。`resolveKeyWithChordState()` 支持 chord 连续按键（如 `ctrl+x ctrl+k`）。

### 当前问题

当前只有两种输入模式：
- prompt_toolkit 的 vi_mode（可选）
- slash 命令（`/` 前缀触发补全）

没有快捷键系统。玩家在对话模式下想快速选择语气需要打字，探索时移动需要完整输入"向北走"。

### 目标设计

```python
@dataclass(frozen=True)
class Keybinding:
    key: str             # "n", "ctrl+s", "f1"
    action: str          # "move_north", "save_game", "show_help"
    description: str     # 显示在帮助中

@dataclass(frozen=True)
class KeybindingBlock:
    context: GameMode
    bindings: tuple[Keybinding, ...]

# 默认绑定
DEFAULT_BINDINGS: list[KeybindingBlock] = [
    KeybindingBlock(
        context=GameMode.EXPLORING,
        bindings=(
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
            Keybinding("ctrl+s", "save_game", "保存游戏"),
        ),
    ),
    KeybindingBlock(
        context=GameMode.DIALOGUE,
        bindings=(
            Keybinding("1", "tone_friendly", "友好语气"),
            Keybinding("2", "tone_neutral", "中立语气"),
            Keybinding("3", "tone_aggressive", "强硬语气"),
            Keybinding("escape", "end_dialogue", "结束对话"),
        ),
    ),
    KeybindingBlock(
        context=GameMode.COMBAT,
        bindings=(
            Keybinding("a", "attack", "攻击"),
            Keybinding("d", "defend", "防御"),
            Keybinding("r", "run_away", "逃跑"),
            Keybinding("1", "use_skill_1", "使用技能1"),
            Keybinding("2", "use_skill_2", "使用技能2"),
        ),
    ),
]
```

快捷键解析器：

```python
class KeybindingResolver:
    def __init__(self, bindings: list[KeybindingBlock]):
        self._by_context: dict[GameMode, dict[str, str]] = {}
        for block in bindings:
            self._by_context[block.context] = {
                kb.key: kb.action for kb in block.bindings
            }

    def resolve(self, key: str, current_mode: GameMode) -> str | None:
        """返回 action 名称，或 None 表示无匹配"""
        context_bindings = self._by_context.get(current_mode, {})
        return context_bindings.get(key)
```

### Chord 支持（二期）

chord 允许多按键组合指令，如探索时按 `g n` 表示 "go north"：

```python
@dataclass(frozen=True)
class ChordState:
    pending: tuple[str, ...]  # 已按下但未匹配的按键序列
    timeout_ms: int = 500

def resolve_with_chord(
    key: str, mode: GameMode, chord_state: ChordState | None
) -> tuple[str | None, ChordState | None]:
    """返回 (action_or_none, new_chord_state)"""
    ...
```

### 用户自定义

用户可在 config.yaml 中覆盖默认绑定：

```yaml
keybindings:
  exploring:
    h: move_west    # 用 hjkl 替代 nesw
    j: move_south
    k: move_north
    l: move_east
```

加载顺序：默认绑定 -> 用户配置覆盖（后者优先）。

### 与现有代码的集成

- 在 `Renderer.get_input()` 中接入 `KeybindingResolver`
- prompt_toolkit 的 `KeyBindings` 可以直接绑定自定义按键处理
- 快捷键帮助信息在状态栏或 `/help` 中显示当前模式可用的快捷键
- 与 FSM 配合：`ModeHandler.get_keybindings()` 返回当前模式的绑定列表

---

## 3. Markdown-as-Code 内容系统

### 来源

Claude Code `skills/` 模块。Skills 是 Markdown 文件 + YAML frontmatter，声明 `name`, `description`, `when_to_use`, `paths`（条件激活）等元数据。系统从多个目录加载（managed > user > project），支持懒激活。

### 当前问题

当前所有游戏内容都在 YAML 文件中：

```yaml
# world.yaml - 房间描述嵌在 YAML 值里
tavern_hall:
  name: "酒馆大厅"
  description: "你站在一间宽敞的酒馆大厅中。空气中弥漫着麦酒..."
```

问题：
- YAML 中写大段文本很别扭（需要用 `|` 块标量，缩进容易出错）
- 内容创作者需要理解 YAML 语法
- 描述无法包含富格式（粗体、列表、分隔线）
- 内容和配置耦合在一起，改描述要碰配置文件
- 不支持"条件内容"（同一房间在不同条件下显示不同描述）

### 目标设计

将内容从配置中分离，用 Markdown 文件 + frontmatter 定义游戏内容：

```
scenarios/tavern/
├── scenario.yaml          # 场景元数据（不变）
├── world.yaml             # 结构定义：房间连接、出口、物品位置（不变）
├── characters.yaml        # 角色属性、初始关系（不变）
├── story.yaml             # 故事节点定义（不变）
├── content/               # 新增：Markdown 内容目录
│   ├── rooms/
│   │   ├── tavern_hall.md
│   │   ├── bar_area.md
│   │   ├── cellar.md
│   │   └── ...
│   ├── npcs/
│   │   ├── bartender_grim.md
│   │   ├── traveler.md
│   │   └── mysterious_guest.md
│   ├── items/
│   │   ├── cellar_key.md
│   │   ├── old_notice.md
│   │   └── ...
│   ├── events/
│   │   ├── cellar_secret_revealed.md
│   │   └── ...
│   └── dialogue_templates/
│       ├── bartender_greeting.md
│       └── ...
```

单个内容文件示例：

```markdown
---
id: tavern_hall
type: room
conditions:
  - when: "event_exists:cellar_secret_revealed"
    use: tavern_hall_after_secret
  - when: "time:night"
    use: tavern_hall_night
tags: [main_area, social]
atmosphere: warm
---

你站在一间宽敞的酒馆大厅中。粗糙的木质横梁撑起高高的天花板，
壁炉中的火焰将橙色的光投射在每一张桌子上。空气中弥漫着**麦酒**
和**烤肉**的香气。

大厅里零星坐着几个客人，低声交谈。吧台方向传来杯碟碰撞的声响。

---

## tavern_hall_after_secret

大厅里的气氛微妙地变了。*格林*擦杯子的动作比平时慢了些，
目光不时扫向地窖方向的走廊。你注意到之前锁着的那扇门现在
微微开着一条缝。

---

## tavern_hall_night

酒馆已近打烊时分。火焰低了下去，只剩余烬闪烁着暗红色的光。
大部分客人已经离开，只有角落里**神秘客人**还坐在那里，
低头看着什么东西。
```

NPC 内容文件示例：

```markdown
---
id: bartender_grim
type: npc
personality_tags: [guarded, loyal, observant]
voice_style: 简短有力，不说废话，偶尔流露关心
---

# 外观

壮实的中年男人，满脸胡茬，双手粗糙。系着一条洗得发白的围裙。
眼神锐利，像是什么都看在眼里，但嘴上不说。

# 背景

格林经营这家酒馆已经十五年。他见过太多人来人去，
学会了不多问、不多说。但对于信任的人，他愿意透露一些
别人不知道的事。

# 对话风格指导

- 回答简短，很少超过两句
- 用动作代替语言（擦杯子、点头、皱眉）
- 对陌生人警惕，对熟客偶尔开玩笑
- 绝不主动提起地窖的事，除非被直接追问且信任足够
```

### 内容加载器

```python
@dataclass(frozen=True)
class ContentEntry:
    id: str
    type: str              # "room", "npc", "item", "event"
    metadata: dict          # frontmatter 中的其他字段
    body: str              # 默认正文
    variants: dict[str, str]  # condition_name -> variant_body

class ContentLoader:
    """从 Markdown 文件加载游戏内容"""

    def load_directory(self, path: Path) -> dict[str, ContentEntry]:
        """递归加载目录下所有 .md 文件"""
        ...

    def resolve(
        self, entry_id: str, state: WorldState
    ) -> str:
        """根据当前状态选择正确的内容变体"""
        entry = self._entries[entry_id]
        for condition in entry.metadata.get("conditions", []):
            if self._evaluate_condition(condition["when"], state):
                variant_key = condition["use"]
                return entry.variants.get(variant_key, entry.body)
        return entry.body
```

### 条件激活（懒加载模式）

借鉴 Claude Code Skills 的 `paths:` 激活模式。某些内容只在特定条件首次满足时才加载到内存：

```yaml
# events/cellar_secret_revealed.md frontmatter
---
id: cellar_secret_revealed
type: event
activate_when:
  - "event_exists:cellar_entered"
  - "relationship:bartender_grim >= 30"
---
```

这避免了在游戏启动时加载所有内容，也为大型场景的按需加载做好准备。

### 与现有代码的集成

- `world.yaml` 中的 `description` 字段改为可选。如果存在对应 `.md` 文件，优先使用 Markdown 内容
- `Narrator` 在组装 prompt 时，调用 `ContentLoader.resolve()` 获取当前条件下的房间/NPC 描述
- `Renderer` 可以解析 Markdown 的部分语法（粗体 -> Rich 加粗，`---` -> 分隔线）
- 向后兼容：没有 `content/` 目录时退回到 YAML 内联描述

### 模组支持（远期）

内容目录可以有多个来源，按优先级合并：

```
加载顺序（后者覆盖前者）：
1. 核心场景内容  (scenarios/tavern/content/)
2. 社区模组      (mods/dark_tavern/content/)
3. 玩家自定义    (user/content/)
```

---

## 4. Action 工厂模式与统一接口

### 来源

Claude Code `Tool.ts` + `tools.ts`。每个 Tool 实现统一接口（`inputSchema`, `call()`, `isEnabled()`, `checkPermissions()`, `description()` 等），通过 `buildTool(partial)` 工厂函数合并默认值，只需声明差异部分。

### 当前问题

当前 `RulesEngine` 的 action handler 是裸函数，注册在 `_ACTION_HANDLERS` 字典中：

```python
_ACTION_HANDLERS: dict[ActionType, _Handler] = {
    ActionType.MOVE: _handle_move,
    ActionType.LOOK: _handle_look,
    ...
}
```

缺少：
- 没有标准化的"这个 action 在当前状态下是否可用"检查
- 没有"这个 action 需要什么参数"的声明
- `TRADE`, `GIVE`, `STEALTH`, `COMBAT` 在 enum 中定义了但没有 handler
- hint 系统无法自动发现"当前可用的 actions"

### 目标设计

```python
@dataclass(frozen=True)
class ActionDef:
    action_type: ActionType
    description: str                                   # 显示名称
    description_fn: Callable[[WorldState], str] | None  # 动态描述（可选）
    valid_targets: Callable[[WorldState], list[str]]    # 当前合法目标列表
    is_available: Callable[[WorldState], bool]          # 当前是否可执行
    handler: Callable[[ActionRequest, WorldState], tuple[ActionResult, StateDiff | None]]
    requires_target: bool = True
    cooldown_turns: int = 0

# 默认值
ACTION_DEFAULTS = ActionDef(
    action_type=ActionType.CUSTOM,
    description="自定义动作",
    description_fn=None,
    valid_targets=lambda s: [],
    is_available=lambda s: True,
    handler=lambda req, s: (ActionResult(success=True, message=""), None),
    requires_target=False,
    cooldown_turns=0,
)

def build_action(**overrides) -> ActionDef:
    """工厂函数：只需声明与默认值不同的部分"""
    defaults = asdict(ACTION_DEFAULTS)
    defaults.update(overrides)
    return ActionDef(**defaults)
```

使用示例：

```python
move_action = build_action(
    action_type=ActionType.MOVE,
    description="移动",
    valid_targets=lambda s: [
        exit.target_location_id
        for exit in s.current_location.exits
        if not exit.is_locked
    ],
    is_available=lambda s: len(s.current_location.exits) > 0,
    handler=_handle_move,
)

trade_action = build_action(
    action_type=ActionType.TRADE,
    description="交易",
    description_fn=lambda s: f"与{s.current_npc.name}交易" if s.current_npc else "交易",
    valid_targets=lambda s: [
        npc.id for npc in s.npcs_in_location
        if npc.has_shop
    ],
    is_available=lambda s: any(npc.has_shop for npc in s.npcs_in_location),
    handler=_handle_trade,
)
```

### 自动化优势

有了统一接口，以下功能自动获得：

```python
class ActionRegistry:
    def __init__(self, actions: list[ActionDef]):
        self._actions = {a.action_type: a for a in actions}

    def get_available_actions(self, state: WorldState) -> list[ActionDef]:
        """hint 系统和自动补全使用"""
        return [a for a in self._actions.values() if a.is_available(state)]

    def get_valid_targets(
        self, action_type: ActionType, state: WorldState
    ) -> list[str]:
        """Intent 解析时限定合法目标"""
        action = self._actions.get(action_type)
        return action.valid_targets(state) if action else []

    def validate_and_execute(
        self, request: ActionRequest, state: WorldState
    ) -> tuple[ActionResult, StateDiff | None]:
        action = self._actions.get(request.action)
        if not action:
            return ActionResult(success=False, message="未知动作"), None
        if not action.is_available(state):
            return ActionResult(success=False, message="当前无法执行此动作"), None
        if action.requires_target and request.target not in action.valid_targets(state):
            return ActionResult(success=False, message=f"无效目标: {request.target}"), None
        return action.handler(request, state)
```

### 与现有代码的集成

- `RulesEngine._ACTION_HANDLERS` 替换为 `ActionRegistry`
- `_handle_move`, `_handle_look` 等函数保持不变，只是包装进 `build_action()`
- `IntentParser` 在构建 prompt 时可调用 `registry.get_available_actions(state)` 列出合法动作，提高 LLM 分类准确率
- `Renderer.ContextualCompleter` 可用 `get_valid_targets()` 动态提供补全候选

---

## 5. 极简响应式 Store

### 来源

Claude Code `state/store.ts`。35 行代码实现 `createStore(initial, onChange)`，核心是 `setState(prev => next)` 更新器 + `subscribe()` 监听器。

### 当前问题

`StateManager` 已经实现了不可变状态 + undo/redo，但缺少响应式能力：

```python
# 当前：手动触发副作用
self.state_manager.commit(diff, action)
# 然后在 GameApp 里手动调用：
await self.renderer.render_status(...)
await self.persistence.auto_save(...)
await self.story_engine.check_triggers(...)
```

每个状态变更后的副作用都需要在 `GameApp` 中手动编排，容易遗漏。

### 目标设计

在 `StateManager` 上增加订阅机制：

```python
from typing import Callable

Listener = Callable[[], None]
OnChange = Callable[[WorldState, WorldState], None]  # (old, new)

class ReactiveStateManager:
    def __init__(
        self,
        initial: WorldState,
        max_history: int = 50,
        on_change: OnChange | None = None,
    ):
        self._state = initial
        self._history: deque[WorldState] = deque(maxlen=max_history)
        self._future: list[WorldState] = []
        self._listeners: list[Listener] = []
        self._on_change = on_change

    @property
    def state(self) -> WorldState:
        return self._state

    def commit(self, diff: StateDiff, action: str = "") -> WorldState:
        old = self._state
        self._history.append(old)
        self._future.clear()
        self._state = old.apply(diff)
        if self._on_change:
            self._on_change(old, self._state)
        for listener in self._listeners:
            listener()
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """返回取消订阅函数"""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def undo(self) -> WorldState | None:
        if not self._history:
            return None
        self._future.append(self._state)
        old = self._state
        self._state = self._history.pop()
        if self._on_change:
            self._on_change(old, self._state)
        for listener in self._listeners:
            listener()
        return self._state
```

注册副作用：

```python
def setup_state_reactions(
    store: ReactiveStateManager,
    renderer: Renderer,
    persistence: SaveManager,
    story_engine: StoryEngine,
):
    def on_state_change(old: WorldState, new: WorldState):
        # 自动保存
        if new.turn % 5 == 0:
            persistence.auto_save(new)

        # 位置变更时自动 look
        if old.player_location != new.player_location:
            renderer.queue_room_description(new)

        # 检查故事触发
        story_engine.queue_trigger_check(new)

        # 成就检测
        check_achievements(old, new)

    store = ReactiveStateManager(initial_state, on_change=on_state_change)
```

### 与现有代码的集成

- `StateManager` 重命名为 `ReactiveStateManager`，新增 `subscribe()` 和 `on_change` 参数
- 现有的 `commit()` 和 `undo()` 接口保持不变，只是在内部增加通知
- `GameApp` 中散落的手动副作用调用逐步迁移到 `on_change` 回调中
- undo/redo 也会触发 `on_change`，确保副作用一致

---

## 6. 命令注册表系统

### 来源

Claude Code `commands.ts` + `types/command.ts`。命令是 discriminated union（`prompt` / `local` / `local-jsx` 三种类型），每个命令声明 `name`, `aliases`, `description`, `isEnabled()`, `isHidden` 等。通过 `getCommands(cwd)` 统一获取，`findCommand()` 线性查找。

### 当前问题

`_handle_system_command()` 是一个巨大的 if-elif 链：

```python
async def _handle_system_command(self, raw: str):
    cmd = raw.split()[0].lower()
    if cmd == "/look": ...
    elif cmd == "/inventory": ...
    elif cmd == "/status": ...
    elif cmd == "/hint": ...
    elif cmd == "/undo": ...
    # ... 12 个分支
```

新增命令需要：修改这个函数 + 修改 `ContextualCompleter` 的补全列表 + 修改 `/help` 输出。三处改动，容易遗漏。

### 目标设计

```python
@dataclass(frozen=True)
class GameCommand:
    name: str                    # "/look"
    aliases: tuple[str, ...] = ()  # ("/l", "/观察")
    description: str = ""
    is_hidden: bool = False
    available_in: tuple[GameMode, ...] = (GameMode.EXPLORING,)
    execute: Callable  # async (args: str, ctx: CommandContext) -> None

class CommandRegistry:
    def __init__(self):
        self._commands: list[GameCommand] = []
        self._lookup: dict[str, GameCommand] = {}

    def register(self, cmd: GameCommand) -> None:
        self._commands.append(cmd)
        self._lookup[cmd.name] = cmd
        for alias in cmd.aliases:
            self._lookup[alias] = cmd

    def find(self, name: str) -> GameCommand | None:
        return self._lookup.get(name)

    def get_available(self, mode: GameMode) -> list[GameCommand]:
        return [
            c for c in self._commands
            if mode in c.available_in and not c.is_hidden
        ]

    def get_completions(self, mode: GameMode) -> list[str]:
        """供 ContextualCompleter 使用"""
        return [
            c.name for c in self.get_available(mode)
        ]
```

注册命令（声明式）：

```python
registry = CommandRegistry()

registry.register(GameCommand(
    name="/look",
    aliases=("/l", "/观察"),
    description="查看当前环境",
    available_in=(GameMode.EXPLORING, GameMode.COMBAT),
    execute=cmd_look,
))

registry.register(GameCommand(
    name="/inventory",
    aliases=("/i", "/背包"),
    description="查看背包物品",
    available_in=(GameMode.EXPLORING, GameMode.INVENTORY),
    execute=cmd_inventory,
))

registry.register(GameCommand(
    name="/save",
    aliases=("/s",),
    description="保存游戏",
    available_in=(GameMode.EXPLORING,),
    execute=cmd_save,
))

# 隐藏调试命令
registry.register(GameCommand(
    name="/debug",
    description="显示调试信息",
    is_hidden=True,
    available_in=tuple(GameMode),
    execute=cmd_debug,
))
```

分发简化为一行：

```python
async def handle_command(self, raw: str, mode: GameMode, ctx: CommandContext):
    parts = raw.split(maxsplit=1)
    cmd_name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    cmd = self.registry.find(cmd_name)
    if cmd is None:
        await ctx.renderer.render_error(f"未知命令: {cmd_name}")
        return
    if mode not in cmd.available_in:
        await ctx.renderer.render_error(f"当前模式下不可用: {cmd_name}")
        return
    await cmd.execute(args, ctx)
```

### 自动化收益

- `/help` 自动从 `registry.get_available(mode)` 生成
- `ContextualCompleter` 从 `registry.get_completions(mode)` 获取补全列表
- 新增命令 = 一个 `register()` 调用，不改任何调度代码
- 别名和中文命令自动支持

### 与现有代码的集成

- 将 `_handle_system_command()` 中的每个分支提取为独立函数
- 用 `CommandRegistry` 替代 if-elif 分发
- `ContextualCompleter` 中硬编码的命令列表改为查询 registry

---

## 7. 确定性种子生成器

### 来源

Claude Code `buddy/companion.ts`。从 `hash(userId + salt)` 出发，用 Mulberry32 PRNG 确定性生成物种、稀有度、属性。关键设计：**不存储生成结果**，每次从 seed 重算，只存储不可重算的数据（名字、性格等 LLM 生成的内容）。

### 当前问题

当前游戏的环境描述完全依赖 LLM 实时生成或 YAML 静态定义。没有中间层——一些环境细节（天气、路人活动、摊贩叫卖）可以用确定性随机生成，不需要 LLM 参与。

### 目标设计

```python
import hashlib
import struct

class SeededRNG:
    """Mulberry32 确定性伪随机数生成器"""

    def __init__(self, seed: int):
        self._state = seed & 0xFFFFFFFF

    def next(self) -> float:
        """返回 [0, 1) 的浮点数"""
        self._state += 0x6D2B79F5
        self._state &= 0xFFFFFFFF
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 0x100000000

    def choice(self, options: list) -> any:
        return options[int(self.next() * len(options))]

    def weighted_choice(self, options: list[tuple[any, float]]) -> any:
        total = sum(w for _, w in options)
        r = self.next() * total
        cumulative = 0
        for item, weight in options:
            cumulative += weight
            if r < cumulative:
                return item
        return options[-1][0]

def make_seed(location_id: str, turn: int, salt: str = "") -> int:
    raw = f"{location_id}:{turn}:{salt}"
    digest = hashlib.md5(raw.encode()).digest()
    return struct.unpack("<I", digest[:4])[0]
```

使用场景：

```python
# 环境氛围细节（每次进入房间时确定性生成）
def generate_ambience(location_id: str, turn: int) -> AmbienceDetails:
    rng = SeededRNG(make_seed(location_id, turn, "ambience"))
    return AmbienceDetails(
        weather=rng.choice(["晴朗", "阴沉", "微雨", "大雾"]),
        crowd_level=rng.choice(["冷清", "稍有人气", "热闹", "拥挤"]),
        background_sound=rng.choice([
            "远处传来马蹄声",
            "炉火噼啪作响",
            "窗外有鸟鸣",
            "隔壁桌传来笑声",
        ]),
        smell=rng.choice([
            "烤面包的香气",
            "潮湿木头的味道",
            "麦酒的醇厚气息",
            "草药的淡淡清香",
        ]),
    )

# NPC 外观细节（从 NPC ID 确定性生成，不需要存储）
def generate_npc_appearance(npc_id: str) -> dict:
    rng = SeededRNG(make_seed(npc_id, 0, "appearance"))
    return {
        "scar": rng.choice([None, "左颊", "额头", "下巴"]),
        "hair_detail": rng.choice(["凌乱", "整齐梳理", "扎成马尾", "半遮面"]),
        "clothing_condition": rng.choice(["整洁", "略显陈旧", "满是尘土", "有修补痕迹"]),
    }

# 随机事件触发（每 N 回合检查一次）
def should_trigger_random_event(location_id: str, turn: int) -> bool:
    rng = SeededRNG(make_seed(location_id, turn, "event"))
    return rng.next() < 0.15  # 15% 触发率
```

### 设计原则

- **Bones vs Soul**：确定性生成的属性（外观、天气）= Bones，不需要存储；LLM 生成的内容（名字、对话）= Soul，需要存储
- **同一 seed → 同一结果**：玩家在同一回合重新查看同一房间，看到一致的描述
- **seed 中包含 turn**：不同回合看同一房间有不同的环境细节（天气变化、人来人往）

### 与现有代码的集成

- 在 `Narrator.build_narrative_prompt()` 中注入 `generate_ambience()` 的结果作为额外上下文
- NPC 的 Markdown 内容文件中可以引用 `{appearance.scar}` 等模板变量
- `StoryEngine` 的随机事件触发可以用确定性种子替代 `random.random()`，使重放存档时事件一致

---

## 8. Append-Only JSONL 游戏日志

### 来源

Claude Code `history.ts`。历史记录追加写入 JSONL 文件，异步批量刷盘。支持反向读取（最近优先），大内容走 content-addressable 外部存储。`removeLastFromHistory()` 通过 skip-set 实现软删除。

### 当前问题

当前游戏有 `EventTimeline`（内存中的 tuple），但没有持久化的玩家操作日志。问题：
- 无法回看"冒险日志"（玩家做过什么、看过什么）
- 调试时无法重放玩家操作序列
- 没有跨存档的操作统计

### 目标设计

```python
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class GameLogEntry:
    timestamp: str       # ISO 8601
    turn: int
    session_id: str
    entry_type: str      # "player_input", "system_output", "state_change", "error"
    data: dict

class GameLogger:
    """异步批量写入的 JSONL 游戏日志"""

    def __init__(self, log_path: Path, flush_interval: float = 2.0):
        self._path = log_path
        self._buffer: list[GameLogEntry] = []
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None

    def log(self, entry: GameLogEntry) -> None:
        """非阻塞追加。累积在内存 buffer 中。"""
        self._buffer.append(entry)
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self):
        await asyncio.sleep(self._flush_interval)
        await self.flush()

    async def flush(self):
        if not self._buffer:
            return
        entries = self._buffer.copy()
        self._buffer.clear()
        lines = [json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in entries]
        async with aiofiles.open(self._path, "a") as f:
            await f.writelines(lines)

    def read_recent(self, n: int = 50) -> list[GameLogEntry]:
        """读取最近 N 条记录（反向读取优化，大文件时从末尾读）"""
        ...

    async def close(self):
        """关闭前刷盘"""
        await self.flush()
```

日志内容示例：

```jsonl
{"timestamp":"2026-04-10T14:30:01","turn":1,"session_id":"abc123","entry_type":"player_input","data":{"raw":"查看四周","parsed_action":"LOOK","target":null}}
{"timestamp":"2026-04-10T14:30:03","turn":1,"session_id":"abc123","entry_type":"system_output","data":{"type":"narrative","length":245,"atmosphere":"warm"}}
{"timestamp":"2026-04-10T14:30:10","turn":2,"session_id":"abc123","entry_type":"player_input","data":{"raw":"和酒保说话","parsed_action":"TALK","target":"bartender_grim"}}
{"timestamp":"2026-04-10T14:30:11","turn":2,"session_id":"abc123","entry_type":"state_change","data":{"type":"enter_dialogue","npc":"bartender_grim"}}
```

### 冒险日志命令

```python
# /journal 命令 - 查看冒险回顾
async def cmd_journal(args: str, ctx: CommandContext):
    entries = ctx.logger.read_recent(n=20)
    player_actions = [
        e for e in entries if e.entry_type == "player_input"
    ]
    # 渲染为可读的冒险日志
    for entry in player_actions:
        ctx.renderer.render_journal_entry(entry)
```

### 与现有代码的集成

- `GameLogger` 在 `GameApp` 启动时创建
- 在 `_handle_free_input()` 入口记录 `player_input`
- 在 `Narrator.stream_narrative()` 完成后记录 `system_output`
- 在 `StateManager.commit()` 后记录 `state_change`
- `/journal` 注册为新命令

---

## 9. 分类记忆体系

### 来源

Claude Code `memdir/` 模块。记忆按 `user` / `feedback` / `project` / `reference` 四类分类存储，每类有明确的 `when_to_save` 和 `how_to_use` 规则。索引文件（`MEMORY.md`）与详情文件分离。

### 当前问题

当前 `MemorySystem` 有三个组件：`EventTimeline`（事件流）、`RelationshipGraph`（关系值）、`SkillManager`（知识注入）。但在给 LLM 构建 prompt 时，所有记忆是平等的——没有优先级区分。

问题：
- 长对话后 context window 压力大，需要选择性截断
- 重要的世界设定事实和临时环境细节混在一起
- LLM 无法区分"必须记住的"和"可以遗忘的"

### 目标设计

将记忆分为四类，每类有不同的保留策略和 prompt 注入权重：

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
    importance: int        # 1-10，影响保留优先级
    created_turn: int
    last_relevant_turn: int  # 最后一次相关使用

@dataclass(frozen=True)
class MemoryBudget:
    """每类记忆在 prompt 中的 token 预算"""
    lore: int = 200
    quest: int = 300
    relationship: int = 150
    discovery: int = 100
```

分类记忆管理器：

```python
class ClassifiedMemorySystem:
    def __init__(self, budget: MemoryBudget):
        self._memories: dict[MemoryType, list[MemoryEntry]] = {
            t: [] for t in MemoryType
        }
        self._budget = budget

    def add(self, entry: MemoryEntry) -> None:
        self._memories[entry.memory_type].append(entry)

    def build_context(self, state: WorldState) -> str:
        """按预算裁剪，组装 prompt 上下文"""
        sections = []
        for mem_type in MemoryType:
            entries = self._memories[mem_type]
            # 按重要性 * 新鲜度排序
            scored = sorted(
                entries,
                key=lambda e: e.importance * self._recency_score(e, state.turn),
                reverse=True,
            )
            budget = getattr(self._budget, mem_type.value)
            section = self._truncate_to_budget(scored, budget)  # 按 token 数截断，保留高分条目
            if section:
                sections.append(f"【{mem_type.value.upper()}】\n{section}")
        return "\n\n".join(sections)

    def _recency_score(self, entry: MemoryEntry, current_turn: int) -> float:
        age = current_turn - entry.last_relevant_turn
        return 1.0 / (1.0 + age * 0.1)  # 越久远越低
```

各类记忆的保留规则：

| 类型 | 何时写入 | 保留策略 | prompt 权重 |
|------|---------|---------|------------|
| LORE | 发现世界设定、NPC 透露秘密 | 永久保留，importance >= 7 | 最高 |
| QUEST | 任务状态变更、目标更新 | 任务完成后降级为 LORE | 高 |
| RELATIONSHIP | 信任变化、重要对话 | 保留最近 + importance >= 5 | 中 |
| DISCOVERY | 搜索结果、环境细节 | 只保留最近 10 条 | 低 |

### 与现有代码的集成

- `MemorySystem.build_context()` 替换为 `ClassifiedMemorySystem.build_context()`
- `EventTimeline` 仍然保留（完整事件流），但 `ClassifiedMemorySystem` 从中提取分类摘要
- `RelationshipGraph` 的变更事件自动写入 RELATIONSHIP 类型
- `StoryEngine` 触发节点时自动写入 QUEST 类型
- `SkillManager` 的知识注入归入 LORE 类型

---

## 10. Memoized 场景上下文缓存

### 来源

Claude Code `context.ts`。`getSystemContext()` 和 `getUserContext()` 使用 `memoize()` 缓存结果，5 个 git 命令并行执行。状态变更时手动 `cache.clear()` 失效。

### 当前问题

每次 action 都需要为 LLM 组装完整的场景上下文：

```python
# narrator/prompts/builder.py 每次都重新构建
def build_narrative_prompt(action_result, state, memory_ctx, story_hints):
    # 拼装房间描述 + NPC 列表 + 物品列表 + 出口 + 记忆 + 关系 + 故事提示
    ...
```

如果玩家连续在同一房间做 `look` 然后 `search`，房间描述、NPC 列表、出口信息完全一样，但每次都重新拼装。

### 目标设计

```python
from functools import lru_cache

@dataclass(frozen=True)
class SceneContext:
    """场景上下文快照——可缓存因为 WorldState 是 frozen 的"""
    location_description: str
    npcs_present: tuple[str, ...]
    items_visible: tuple[str, ...]
    exits_available: tuple[str, ...]
    atmosphere: str
    ambience: AmbienceDetails  # 来自 #7 种子生成器的 generate_ambience()

class SceneContextCache:
    def __init__(self):
        self._cache: dict[tuple[str, int], SceneContext] = {}

    def get(self, location_id: str, state_version: int) -> SceneContext | None:
        return self._cache.get((location_id, state_version))

    def put(
        self, location_id: str, state_version: int, context: SceneContext
    ) -> None:
        self._cache[(location_id, state_version)] = context

    def invalidate(self, location_id: str | None = None) -> None:
        if location_id is None:
            self._cache.clear()
        else:
            self._cache = {
                k: v for k, v in self._cache.items() if k[0] != location_id
            }
```

在 prompt builder 中使用：

```python
class CachedPromptBuilder:
    def __init__(self, content_loader: ContentLoader, cache: SceneContextCache):
        self._content = content_loader
        self._cache = cache

    def build_scene_context(self, state: WorldState) -> SceneContext:
        loc_id = state.player_location
        version = state.turn  # 用 turn 作为版本号

        cached = self._cache.get(loc_id, version)
        if cached is not None:
            return cached

        # 并行构建各部分（Python 中用普通函数，不需要 await）
        context = SceneContext(
            location_description=self._content.resolve(loc_id, state),
            npcs_present=tuple(
                npc.name for npc in state.npcs_at(loc_id)
            ),
            items_visible=tuple(
                item.name for item in state.items_at(loc_id)
            ),
            exits_available=tuple(
                exit.display_name for exit in state.exits_at(loc_id)
            ),
            atmosphere=state.location(loc_id).atmosphere,
            ambience=generate_ambience(loc_id, state.turn),
        )
        self._cache.put(loc_id, version, context)
        return context
```

### 失效时机

通过 `ReactiveStateManager.on_change` 自动失效：

```python
def on_state_change(old: WorldState, new: WorldState):
    # 位置变更：失效旧位置缓存
    if old.player_location != new.player_location:
        scene_cache.invalidate(old.player_location)

    # 物品变更：失效相关位置缓存
    if old.items != new.items:
        scene_cache.invalidate(new.player_location)

    # NPC 移动：全部失效
    if old.characters != new.characters:
        scene_cache.invalidate()
```

### 与现有代码的集成

- `SceneContextCache` 作为 `GameApp` 的属性，传给 `Narrator`
- `build_narrative_prompt()` 内部先查缓存，命中则跳过重建
- 与设计 #5（响应式 Store）配合：`on_change` 回调中自动失效缓存

---

## 实施路线图

### Phase 1：核心架构（1-2 周）
- **#1 FSM 状态机** — 重构 GameApp 为模式分发
- **#5 响应式 Store** — 在 StateManager 上加 subscribe/onChange
- **#6 命令注册表** — 替换 if-elif 分发

### Phase 2：游戏机制（1-2 周）
- **#4 Action 工厂** — 统一 action 接口，补全 TRADE/COMBAT handler
- **#2 快捷键系统** — 分模式快捷键，基础方向键移动
- **#7 种子生成器** — 环境氛围细节确定性生成

### Phase 3：内容系统（1-2 周）
- **#3 Markdown-as-Code** — 内容文件分离，ContentLoader
- **#9 分类记忆** — 记忆分类 + 预算裁剪

### Phase 4：优化与体验（1 周）
- **#10 场景缓存** — prompt 构建缓存 + 自动失效
- **#8 游戏日志** — JSONL 追加日志 + /journal 命令

---

## 依赖关系

```
#1 FSM ──────────┐
                  ├──> #2 快捷键（依赖模式上下文）
#6 命令注册表 ───┘
                  ├──> #4 Action 工厂（依赖 FSM 中的模式）

#5 响应式 Store ──┬──> #10 场景缓存（依赖 onChange 失效）
                  └──> #8 游戏日志（依赖 onChange 触发记录）

#3 Markdown 内容 ─┬──> #10 场景缓存（ContentLoader 是缓存数据源）
                  └──> #9 分类记忆（内容文件中的 LORE 归入记忆）

#7 种子生成器 ────────> 独立，无依赖
```
