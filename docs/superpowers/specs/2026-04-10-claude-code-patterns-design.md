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

@dataclass
class ModeContext:
    """Handler 可使用的服务引用集合。非游戏状态，而是基础设施。"""
    state_manager: ReactiveStateManager
    renderer: Renderer
    dialogue_manager: DialogueManager
    narrator: Narrator
    memory: MemorySystem
    persistence: SaveManager
    story_engine: StoryEngine
    command_registry: CommandRegistry
    action_registry: ActionRegistry
    logger: GameLogger

class ModeHandler(Protocol):
    """每个游戏模式的处理器协议"""

    @property
    def mode(self) -> GameMode: ...

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext
    ) -> TransitionResult: ...

    def get_prompt_config(self, state: WorldState) -> PromptConfig: ...

    def get_keybindings(self) -> list[Keybinding]: ...

    # 注意：没有 get_available_commands()。
    # 命令归 §6 CommandRegistry 统一管理，通过 available_in + is_available 控制。
    # ModeHandler 需要命令列表时，通过 context.command_registry.get_available(self.mode, state) 获取。
```

模式转换表（示例，非穷举）：

```
# 基本转换
EXPLORING + "/talk npc"     -> DIALOGUE  (side_effect: start_dialogue)
EXPLORING + "/attack npc"   -> COMBAT    (side_effect: init_combat)
EXPLORING + "/inventory"    -> INVENTORY (side_effect: render_inventory)
DIALOGUE  + "再见"          -> EXPLORING (side_effect: end_dialogue, apply_trust)
DIALOGUE  + 对话超限         -> EXPLORING (side_effect: force_end, summary)
COMBAT    + 战斗结束         -> EXPLORING (side_effect: apply_rewards)
COMBAT    + 逃跑成功         -> EXPLORING (side_effect: flee_penalty)
INVENTORY + "/back"         -> EXPLORING (side_effect: none)
SHOP      + "/leave"        -> EXPLORING (side_effect: none)

# 跨模式转换
EXPLORING + 与商人对话选择交易 -> SHOP      (side_effect: open_shop)
DIALOGUE  + NPC 敌意爆发       -> COMBAT    (side_effect: init_combat, end_dialogue)
INVENTORY + 选择卖出物品        -> SHOP      (side_effect: open_sell_menu)
```

转换表是**开放的**：新增游戏模式只需注册 `ModeHandler` + 在相关 handler 的 `handle_input` 中返回新的 `TransitionResult`。无需修改 `GameLoop` 或集中式转换表。

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
class EffectKind(Enum):
    """FSM 副作用：只负责模式转换相关的命令式操作。
    不包含 SAVE、RENDER 等状态驱动的反应——那些由 §5 on_change 负责。"""
    START_DIALOGUE = "start_dialogue"
    END_DIALOGUE = "end_dialogue"
    APPLY_DIFF = "apply_diff"
    EMIT_EVENT = "emit_event"
    APPLY_TRUST = "apply_trust"
    INIT_COMBAT = "init_combat"
    APPLY_REWARDS = "apply_rewards"
    FLEE_PENALTY = "flee_penalty"
    OPEN_SHOP = "open_shop"

@dataclass(frozen=True)
class SideEffect:
    kind: EffectKind
    payload: dict

# 示例
SideEffect(kind=EffectKind.START_DIALOGUE, payload={"npc_id": "bartender_grim"})
SideEffect(kind=EffectKind.APPLY_DIFF, payload={"diff": state_diff})
SideEffect(kind=EffectKind.EMIT_EVENT, payload={"event": Event(...)})
```

#### FSM SideEffect 与 §5 on_change 的职责边界

两套机制分工明确，**不重叠**：

| 机制 | 职责 | 触发时机 | 示例 |
|------|------|---------|------|
| FSM SideEffect | 模式转换相关的命令式操作 | handler 返回后，由 GameLoop 执行 | start_dialogue, init_combat, apply_diff |
| §5 on_change | 状态变更自动触发的反应式副作用 | state_manager.commit() 后 | auto_save, cache invalidation, story trigger check, room description |

规则：
- **handler 不做 save、render、trigger check**——这些是状态变更的自然后果，由 on_change 统一处理
- **on_change 不做模式切换**——它不知道 FSM 的存在，只关心 WorldState 变化
- 唯一的桥梁是 `APPLY_DIFF`：handler 返回 diff → GameLoop 执行 SideEffect(APPLY_DIFF) → commit() → 触发 on_change

副作用执行器是一个注册表，值为 async 函数引用（非 lambda，支持错误处理和复杂逻辑）：

```python
EffectExecutor = Callable[[dict, GameContext], Awaitable[None]]

async def _exec_start_dialogue(payload: dict, ctx: GameContext) -> None:
    npc_id = payload["npc_id"]
    npc = ctx.state_manager.state.characters.get(npc_id)
    if npc is None:
        raise GameError(f"NPC not found: {npc_id}")
    await ctx.dialogue_manager.start(npc_id)

async def _exec_apply_diff(payload: dict, ctx: GameContext) -> None:
    ctx.state_manager.commit(payload["diff"])

async def _exec_save(payload: dict, ctx: GameContext) -> None:
    await ctx.persistence.auto_save(ctx.state_manager.state)

EFFECT_EXECUTORS: dict[EffectKind, EffectExecutor] = {
    EffectKind.START_DIALOGUE: _exec_start_dialogue,
    EffectKind.APPLY_DIFF: _exec_apply_diff,
    EffectKind.EMIT_EVENT: lambda p, ctx: ctx.memory.timeline.append(p["event"]),
    # 注意：SAVE 和 RENDER 不在这里——由 §5 on_change 负责
}
```

### 与现有代码的集成

- `_process_dialogue_input()` 提取为 `DialogueModeHandler`
- `_handle_free_input()` 提取为 `ExploringModeHandler`
- `_handle_system_command()` 的命令分发交给 §6 `CommandRegistry`，handler 通过 `context.command_registry` 查询
- `GameApp` 拆分为 `Bootstrapper` + `GameLoop`：
  - **`Bootstrapper`**：负责当前 `GameApp.__init__()` 中 ~220 行的初始化逻辑（加载配置、创建 LLM、加载场景、构建 ModeHandler 实例、组装 ModeContext），返回一个就绪的 `GameLoop` 实例
  - **`GameLoop`**：只做模式分发和副作用执行，不负责初始化

#### GameLoop.reset() — 支持 /load 命令

当前 `/load` 命令（app.py:390-404）重建 `StateManager` 和 `MemorySystem`。新架构下 `GameLoop` 和 `ModeContext` 都持有旧引用，必须有 reset 机制：

```python
class GameLoop:
    def reset(self, new_state: WorldState) -> None:
        """/load 时重置所有持有旧 state 引用的组件"""
        self._context.state_manager.replace(new_state)
        self._context.memory.rebuild(new_state)
        self._context.dialogue_manager.reset()
        self._current_mode = GameMode.EXPLORING
        # 场景缓存全部失效
        self._scene_cache.invalidate()
```

`ReactiveStateManager.replace(new_state)` 清空 history/future，设置新 state，触发 on_change。这让 /load 不需要重建整个对象图。

### 测试策略

```python
def test_dialogue_to_exploring_on_farewell():
    handler = DialogueModeHandler(...)
    result = await handler.handle_input("再见", state, context)
    assert result.next_mode == GameMode.EXPLORING
    assert any(e.kind == EffectKind.END_DIALOGUE for e in result.side_effects)
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

### 核心约束：单键绑定与文本输入冲突

这是 CLI 文本游戏快捷键系统的根本矛盾：玩家在对话模式下要输入中文，按 `n` 是"向北走"还是"你好"的一部分？必须引入 **输入模式（InputMode）** 概念来解决。

### 目标设计

#### 输入模式

```python
class InputMode(Enum):
    HOTKEY = "hotkey"  # 单键直接触发 action（不进入文本编辑）
    TEXT = "text"      # 正常文本输入（键盘输入进 buffer）

# 每个 GameMode 的默认输入模式
DEFAULT_INPUT_MODE: dict[GameMode, InputMode] = {
    GameMode.EXPLORING: InputMode.HOTKEY,   # 探索时单键移动
    GameMode.DIALOGUE: InputMode.TEXT,       # 对话时打字
    GameMode.COMBAT: InputMode.HOTKEY,       # 战斗时快捷选择
    GameMode.INVENTORY: InputMode.HOTKEY,    # 背包浏览
    GameMode.SHOP: InputMode.HOTKEY,         # 商店浏览
}
```

模式切换规则：
- **HOTKEY → TEXT**：按 `/`（进入命令输入）或按 `Enter`（进入自由文本输入）
- **TEXT → HOTKEY**：按 `Escape`（取消输入）或发送文本后自动回到 HOTKEY
- HOTKEY 模式下显示底部提示栏：`[n/s/e/w] 移动  [l] 查看  [t] 交谈  [i] 背包  [Enter] 输入文字`
- TEXT 模式下显示正常的文本输入框（prompt_toolkit input）

快捷键只在 HOTKEY 模式下生效，但 TEXT 模式有一个例外——**空缓冲区快捷键**：

```python
class KeybindingResolver:
    def resolve(
        self, key: str, game_mode: GameMode, input_mode: InputMode,
        buffer_empty: bool = False,
    ) -> str | None:
        if input_mode == InputMode.TEXT:
            # TEXT 模式下，只有输入缓冲区为空时才检查快捷键
            # 这让对话模式在空输入时可以用数字键选择 hint
            if not buffer_empty:
                return None
            # 只匹配标记为 allow_in_text 的绑定
            context_bindings = self._text_shortcuts.get(game_mode, {})
            return context_bindings.get(key)
        context_bindings = self._by_context.get(game_mode, {})
        return context_bindings.get(key)
```

#### 快捷键定义

```python
@dataclass(frozen=True)
class Keybinding:
    key: str             # "n", "ctrl+s", "f1"
    action: str          # "move_north", "save_game", "show_help"
    description: str     # 显示在帮助中
    allow_in_text: bool = False  # True = 在 TEXT 模式且缓冲区为空时也生效

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
            # allow_in_text=True: 输入为空时数字键可快速选择 hint 选项
            # 与现有 app.py 的 card hint 数字选择行为一致
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
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

快捷键解析器（见上方 `KeybindingResolver`，已包含 `InputMode` 参数）。

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
│   │   ├── tavern_hall.md              # 默认描述
│   │   ├── tavern_hall.night.md        # 变体：夜晚
│   │   ├── tavern_hall.after_secret.md # 变体：发现秘密后
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

**变体文件命名规则**：`{id}.{variant_name}.md`。每个变体是独立文件，Markdown 内容完全自由，不受分隔符限制。

**Content ID 约束**：ID 不得包含 `.` 字符（只允许 `[a-z0-9_]`）。这样解析器可以安全地按第一个 `.` 分割文件名：`tavern_hall.night.md` → ID=`tavern_hall`，variant=`night`。加载时对 ID 做校验，不合规则 raise `ContentError`。

默认内容文件示例（`rooms/tavern_hall.md`）：

```markdown
---
id: tavern_hall
type: room
variants:
  - name: after_secret
    when: "event_exists:cellar_secret_revealed"
  - name: night
    when: "time:night"
tags: [main_area, social]
atmosphere: warm
---

你站在一间宽敞的酒馆大厅中。粗糙的木质横梁撑起高高的天花板，
壁炉中的火焰将橙色的光投射在每一张桌子上。空气中弥漫着**麦酒**
和**烤肉**的香气。

大厅里零星坐着几个客人，低声交谈。吧台方向传来杯碟碰撞的声响。
```

变体内容文件（`rooms/tavern_hall.after_secret.md`）——纯内容，无 frontmatter：

```markdown
大厅里的气氛微妙地变了。*格林*擦杯子的动作比平时慢了些，
目光不时扫向地窖方向的走廊。你注意到之前锁着的那扇门现在
微微开着一条缝。
```

变体文件（`rooms/tavern_hall.night.md`）：

```markdown
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
class VariantDef:
    name: str       # "after_secret"
    when: str       # "event_exists:cellar_secret_revealed"

@dataclass(frozen=True)
class ContentEntry:
    id: str
    type: str              # "room", "npc", "item", "event"
    metadata: dict          # frontmatter 中的其他字段
    body: str              # 默认正文（主文件内容）
    variants: dict[str, str]  # variant_name -> variant_body（从独立文件加载）
    variant_defs: tuple[VariantDef, ...]  # frontmatter 中声明的变体条件

class ContentLoader:
    """从 Markdown 文件加载游戏内容"""

    def load_directory(self, path: Path) -> dict[str, ContentEntry]:
        """递归加载目录下所有 .md 文件。
        主文件（如 tavern_hall.md）提供 frontmatter + 默认正文。
        变体文件（如 tavern_hall.night.md）按命名规则自动关联。
        """
        ...

    def resolve(
        self, entry_id: str, state: WorldState
    ) -> str:
        """根据当前状态选择正确的内容变体"""
        entry = self._entries[entry_id]
        for variant_def in entry.variant_defs:
            if self._evaluate_condition(variant_def.when, state):
                variant_body = entry.variants.get(variant_def.name)
                if variant_body is not None:
                    return variant_body
        return entry.body
```

### 条件激活（懒加载模式）

借鉴 Claude Code Skills 的 `paths:` 激活模式。某些内容只在特定条件首次满足时才加载到内存：

```yaml
# events/cellar_secret_revealed.md frontmatter
---
id: cellar_secret_revealed
type: event
activate_when:   # AND 语义：所有条件都满足才激活
  - "event_exists:cellar_entered"
  - "relationship:bartender_grim >= 30"
---
```

`activate_when` 列表中多个条件为 **AND** 关系（全部满足才激活）。单条件直接写一项即可。

### 条件求值器复用

`ContentLoader._evaluate_condition()` **必须复用** `engine/story_conditions.py` 中已有的 `CONDITION_REGISTRY`，而不是另起一套。已有的条件类型（`location`、`inventory`、`relationship`、`event`、`quest` 等）覆盖了内容系统的所有需求。

```python
# ContentLoader 中
from tavern.engine.story_conditions import evaluate_condition

def _evaluate_condition(self, condition_str: str, state: WorldState) -> bool:
    """解析 'type:params' 格式并委托给 CONDITION_REGISTRY"""
    return evaluate_condition(condition_str, state)
```

如需新增条件类型（如 `time:night`），在 `story_conditions.py` 中用 `@register_condition()` 注册，ContentLoader 自动获得。

这避免了在游戏启动时加载所有内容，也为大型场景的按需加载做好准备。

### 与现有代码的集成

- `world.yaml` 中的 `description` 字段改为可选。如果存在对应 `.md` 文件，优先使用 Markdown 内容
- `Narrator` 在组装 prompt 时，调用 `ContentLoader.resolve()` 获取当前条件下的房间/NPC 描述
- `Renderer` 可以解析 Markdown 的部分语法（粗体 -> Rich 加粗，`---` -> 分隔线）
- 向后兼容：没有 `content/` 目录时退回到 YAML 内联描述

### 测试策略

```python
def test_content_loader_resolves_default_variant():
    loader = ContentLoader()
    loader.load_directory(Path("test_content/"))
    # 无条件匹配时返回默认正文
    state = make_state(events=[])
    assert "宽敞的酒馆大厅" in loader.resolve("tavern_hall", state)

def test_content_loader_resolves_conditional_variant():
    loader = ContentLoader()
    loader.load_directory(Path("test_content/"))
    state = make_state(events=["cellar_secret_revealed"])
    assert "格林擦杯子" in loader.resolve("tavern_hall", state)

def test_variant_file_naming_convention():
    # tavern_hall.night.md 自动关联到 tavern_hall 的 night 变体
    loader = ContentLoader()
    loader.load_directory(Path("test_content/"))
    entry = loader._entries["tavern_hall"]
    assert "night" in entry.variants
```

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

**关键契约：handler 是纯函数，不 commit 状态。** handler 接收 `(ActionRequest, WorldState)` 返回 `(ActionResult, StateDiff | None)`，由调用方（GameLoop 通过 FSM SideEffect `APPLY_DIFF`）负责 commit。这保证 handler 可测试、可组合，且与 §5 响应式 Store 的 `on_change` 不冲突。

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
    return dataclasses.replace(ACTION_DEFAULTS, **overrides)
```

使用示例：

```python
move_action = build_action(
    action_type=ActionType.MOVE,
    description="移动",
    valid_targets=lambda s: [
        exit.target                          # models.Exit.target (非 target_location_id)
        for exit in s.current_location.exits.values()
        if not exit.locked                   # models.Exit.locked (非 is_locked)
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

### WorldState 需要新增的便利属性

示例代码中的 `s.current_location`、`s.npcs_in_location` 等属性在当前 `WorldState` 上不存在。需要新增以下便利方法/属性：

```python
class WorldState:
    # 现有字段不变...

    @property
    def current_location(self) -> Location:
        """当前玩家所在位置"""
        return self.locations[self.player_location]

    def npcs_at(self, location_id: str) -> list[Character]:
        """指定位置的 NPC 列表"""
        return [c for c in self.characters.values()
                if c.location_id == location_id and c.id != self.player_id]

    @property
    def npcs_in_location(self) -> list[Character]:
        """当前位置的 NPC（语法糖）"""
        return self.npcs_at(self.player_location)

    def items_at(self, location_id: str) -> list[Item]:
        """指定位置的物品列表"""
        loc = self.locations.get(location_id)
        return [self.items[iid] for iid in (loc.item_ids if loc else [])]

    def exits_at(self, location_id: str) -> list[Exit]:
        """指定位置的出口列表"""
        loc = self.locations.get(location_id)
        return list(loc.exits) if loc else []

    @property
    def player_inventory(self) -> list[Item]:
        """玩家背包物品"""
        player = self.characters[self.player_id]
        return [self.items[iid] for iid in player.inventory_ids]
```

这些属性是只读的、从现有数据派生的，不影响 frozen 不可变性。

### 测试策略

handler 是纯函数，天然可测试——构造 WorldState，传入 ActionRequest，断言返回的 (ActionResult, StateDiff)：

```python
def test_move_action_available_only_when_exits_exist():
    state_with_exits = make_state(exits=["north_room"])
    state_no_exits = make_state(exits=[])
    assert move_action.is_available(state_with_exits) is True
    assert move_action.is_available(state_no_exits) is False

def test_take_returns_diff_without_committing():
    state = make_state(location_items=["sword"])
    request = ActionRequest(action=ActionType.TAKE, target="sword")
    result, diff = take_action.handler(request, state)
    assert result.success is True
    assert "sword" in diff.removed_items
    # 原始 state 未变（handler 不 commit）
    assert "sword" in state.items_at(state.player_location)
```

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
from typing import Callable, Awaitable
import asyncio

Listener = Callable[[], None]
OnChange = Callable[[WorldState, WorldState], Awaitable[None]]  # async callback

class ReactiveStateManager:
    def __init__(
        self,
        initial: WorldState,
        max_history: int = 50,
        on_change: OnChange | None = None,
    ):
        self._state = initial
        self._version = 0  # 每次 commit +1，供 §10 缓存使用
        self._history: deque[tuple[WorldState, int]] = deque(maxlen=max_history)  # (state, version)
        self._future: list[tuple[WorldState, int]] = []
        self._listeners: list[Listener] = []
        self._on_change = on_change

    @property
    def state(self) -> WorldState:
        return self._state

    @property
    def version(self) -> int:
        return self._version

    def commit(self, diff: StateDiff, action: ActionResult | None = None) -> WorldState:
        """同步 commit。on_change 通过 fire-and-forget 异步执行，
        避免整个调用链被迫改成 async。trade-off：副作用执行顺序不保证。
        action 参数保持 ActionResult 类型，与现有 StateManager.commit() 签名一致。"""
        old = self._state
        self._history.append((old, self._version))
        self._future.clear()
        self._state = old.apply(diff, action=action)
        self._version += 1
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        # snapshot 迭代，防止回调中 unsubscribe 导致跳过元素
        for listener in list(self._listeners):
            listener()
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """返回取消订阅函数"""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def undo(self) -> WorldState | None:
        if not self._history:
            return None
        self._future.append((self._state, self._version))
        old = self._state
        self._state, self._version = self._history.pop()
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()
        return self._state

    def replace(self, new_state: WorldState) -> None:
        """/load 时整体替换状态，清空 history/future，触发 on_change"""
        old = self._state
        self._state = new_state
        self._history.clear()
        self._future.clear()
        self._version += 1
        if self._on_change:
            asyncio.create_task(self._on_change(old, self._state))
        for listener in list(self._listeners):
            listener()
```

注册副作用：

```python
def setup_state_reactions(
    store: ReactiveStateManager,
    renderer: Renderer,
    persistence: SaveManager,
    story_engine: StoryEngine,
):
    async def on_state_change(old: WorldState, new: WorldState):
        # 自动保存
        if new.turn % 5 == 0:
            await persistence.auto_save(new)

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

- `StateManager` 重命名为 `ReactiveStateManager`，新增 `subscribe()`、`on_change` 和 `replace()` 方法
- **`commit()` 和 `undo()` 保持同步**。`on_change` 通过 `asyncio.create_task()` fire-and-forget 执行，避免对 `rules.py` 等同步调用方的破坏性改动。trade-off：副作用执行顺序不保证，但副作用应当是独立的
- **`commit()` 第二参数保持 `ActionResult | None`**，与现有 `StateManager.commit(diff, action: ActionResult)` 签名一致
- **`undo()` 返回 `WorldState | None`**（而非 raise IndexError）。现有 app.py:331 的 `try/except IndexError` 调用侧需改为 `if result is None` 判断
- `replace(new_state)` 用于 `/load` 命令，整体替换状态并清空 history/future（见 §1 `GameLoop.reset()`）
- `WorldState` 新增 `version: int` 字段（每次 `apply(diff)` 时 +1），供 §10 场景缓存使用
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
    is_available: Callable[[WorldState], bool] = lambda _: True  # 动态启用/禁用
    execute: Callable[[str, CommandContext], Awaitable[None]] = ...  # async (args, ctx)

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

    def get_available(self, mode: GameMode, state: WorldState) -> list[GameCommand]:
        return [
            c for c in self._commands
            if mode in c.available_in
            and not c.is_hidden
            and c.is_available(state)
        ]

    def get_completions(self, mode: GameMode, state: WorldState) -> list[str]:
        """供 ContextualCompleter 使用"""
        return [
            c.name for c in self.get_available(mode, state)
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
    is_available=lambda s: not s.is_in_combat,  # 战斗中不可保存
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
    if not cmd.is_available(ctx.state_manager.state):
        await ctx.renderer.render_error(f"当前无法执行: {cmd_name}")
        return
    await cmd.execute(args, ctx)
```

### 自动化收益

- `/help` 自动从 `registry.get_available(mode, state)` 生成
- `ContextualCompleter` 从 `registry.get_completions(mode, state)` 获取补全列表
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
    # 用 \x00 分隔，避免 "bar:10:" vs "bar:1:0" 碰撞
    raw = f"{location_id}\x00{turn}\x00{salt}"
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

- **氛围注入路径**：`generate_ambience()` 的结果不直接传给 `build_narrative_prompt()`（其签名不变）。而是在 §10 `CachedPromptBuilder.build_scene_context()` 中调用 `generate_ambience()`，拼接到 `SceneContext.location_description` 末尾（如追加"空气中弥漫着烤面包的香气，远处传来马蹄声"）。`NarrativeContext.location_desc` 从 `SceneContext.location_description` 取值，自然包含氛围细节
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
    """异步批量写入的 JSONL 游戏日志，按 session 分文件"""

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB 单文件上限

    def __init__(self, log_dir: Path, session_id: str, flush_interval: float = 2.0):
        self._log_dir = log_dir
        self._session_id = session_id
        self._path = log_dir / f"{session_id}.jsonl"
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
        self.flush()

    def flush(self):
        if not self._buffer:
            return
        # 文件大小检查：超过上限时轮转
        if self._path.exists() and self._path.stat().st_size > self.MAX_FILE_SIZE:
            rotated = self._path.with_suffix(f".{int(time.time())}.jsonl")
            self._path.rename(rotated)
        entries = self._buffer.copy()
        self._buffer.clear()
        lines = [json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in entries]
        with open(self._path, "a", encoding="utf-8") as f:
            f.writelines(lines)  # 同步写入，JSONL append 量小，不需要 aiofiles

    def read_recent(self, n: int = 50) -> list[GameLogEntry]:
        """读取最近 N 条记录。
        策略：从文件末尾 seek，逐块反向读取（每块 8KB），
        解析 JSONL 行直到凑够 N 条。避免读取整个文件。
        优先读取内存 buffer 中未刷盘的条目。"""
        # 1. 先从 buffer 取未刷盘的
        result = list(self._buffer[-n:])
        remaining = n - len(result)
        if remaining <= 0:
            return result
        # 2. 从文件末尾逐块反向读取
        if not self._path.exists():
            return result
        chunk_size = 8192
        with open(self._path, "rb") as f:
            f.seek(0, 2)  # seek to end
            pos = f.tell()
            tail_lines: list[str] = []
            while pos > 0 and len(tail_lines) < remaining:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size).decode("utf-8")
                tail_lines = chunk.splitlines() + tail_lines
            for line in tail_lines[-remaining:]:
                if line.strip():
                    result.insert(0, GameLogEntry(**json.loads(line)))
        return result[-n:]

    def close(self):
        """关闭前刷盘"""
        self.flush()
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
- **`GameLogger.close()` 必须在 `GameApp.run()` 的 `finally` 块中调用**，否则崩溃时 buffer 中的数据丢失。`close()` 是同步方法（无需 await），可安全在 finally 中调用
- 在 `_handle_free_input()` 入口记录 `player_input`
- 在 `Narrator.stream_narrative()` 完成后记录 `system_output`
- 在 `StateManager.commit()` 后记录 `state_change`
- `/journal` 注册为新命令

---

## 9. 分类记忆体系

### 来源

Claude Code `memdir/` 模块的分类索引 + 详情分离模式。

### 设计动机

游戏中 LLM 需要的上下文信息本质上有不同的**生命周期和重要性**：

- **世界设定**（NPC 的秘密、已发现的传说）需要**永久保留**，它们是叙事一致性的基石
- **任务进度**（当前目标、待完成步骤）在任务活跃期间很重要，完成后重要性骤降
- **关系变化**（信任波动、关键对话）需要**中等保留**，影响 NPC 行为但不是每次都需要
- **探索细节**（搜索结果、环境描述）是**短期记忆**，很快就会被更新的信息取代

如果不分类，所有记忆平等竞争 prompt 空间。结果是：重要的世界设定被大量临时探索细节淹没，LLM 忘记关键信息，叙事出现矛盾。

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

    def build_context(self, state: WorldState) -> MemoryContext:
        """按预算裁剪，组装 prompt 上下文。
        返回 MemoryContext dataclass，保持与现有 build_narrative_prompt 接口兼容。"""
        sections: dict[str, str] = {}
        for mem_type in MemoryType:
            entries = self._memories[mem_type]
            # 按重要性 * 新鲜度排序
            scored = sorted(
                entries,
                key=lambda e: e.importance * self._recency_score(e, state.turn),
                reverse=True,
            )
            budget = getattr(self._budget, mem_type.value)
            sections[mem_type] = self._truncate_to_budget(scored, budget)

        # 映射到 MemoryContext 三字段：
        # recent_events ← QUEST + DISCOVERY（事件性信息）
        # relationship_summary ← RELATIONSHIP
        # active_skills_text ← LORE（世界知识）
        recent_parts = [s for k in (MemoryType.QUEST, MemoryType.DISCOVERY) if (s := sections.get(k))]
        return MemoryContext(
            recent_events="\n".join(recent_parts),
            relationship_summary=sections.get(MemoryType.RELATIONSHIP, ""),
            active_skills_text=sections.get(MemoryType.LORE, ""),
        )

    def _recency_score(self, entry: MemoryEntry, current_turn: int) -> float:
        age = current_turn - entry.last_relevant_turn
        decay_rate = _DECAY_RATE[entry.memory_type]
        return 1.0 / (1.0 + age * decay_rate)

# 每类记忆的时间衰减系数——LORE 几乎不衰减，DISCOVERY 快速衰减
_DECAY_RATE: dict[MemoryType, float] = {
    MemoryType.LORE: 0.01,           # 100 turns 前权重仍有 0.5
    MemoryType.QUEST: 0.05,          # 20 turns 前权重 0.5
    MemoryType.RELATIONSHIP: 0.08,   # ~12 turns 前权重 0.5
    MemoryType.DISCOVERY: 0.2,       # 5 turns 前权重 0.5
}
```

各类记忆的保留规则：

| 类型 | 何时写入 | 保留策略 | prompt 权重 |
|------|---------|---------|------------|
| LORE | 发现世界设定、NPC 透露秘密 | 永久保留，importance >= 7 | 最高 |
| QUEST | 任务状态变更、目标更新 | 任务完成后降级为 LORE | 高 |
| RELATIONSHIP | 信任变化、重要对话 | 保留最近 + importance >= 5 | 中 |
| DISCOVERY | 搜索结果、环境细节 | 只保留最近 10 条 | 低 |

### 记忆写入的触发机制

EventTimeline 产生事件 → **MemoryExtractor** 从事件中提取分类记忆 → 写入 ClassifiedMemorySystem。

MemoryExtractor 使用**规则匹配**（不用 LLM），通过事件类型到记忆类型的映射表决定分类和重要性：

```python
@dataclass(frozen=True)
class MemoryExtractionRule:
    event_type_pattern: str     # 正则匹配事件类型，如 "dialogue_summary_.*"
    memory_type: MemoryType
    importance_fn: Callable[[Event], int]  # 从事件内容计算重要性
    content_fn: Callable[[Event], str]     # 从事件提取记忆文本

# 规则表：事件类型 → 记忆分类
EXTRACTION_RULES: list[MemoryExtractionRule] = [
    # 对话摘要中提到的世界设定 → LORE
    MemoryExtractionRule(
        event_type_pattern=r"dialogue_summary_.*",
        memory_type=MemoryType.LORE,
        importance_fn=lambda e: 8 if e.data.get("has_secret") else 4,
        content_fn=lambda e: e.data["summary_text"],
    ),
    # 任务状态变更 → QUEST
    MemoryExtractionRule(
        event_type_pattern=r"quest_.*",
        memory_type=MemoryType.QUEST,
        importance_fn=lambda e: 7,
        content_fn=lambda e: f"任务 {e.data['quest_id']}: {e.data['status']}",
    ),
    # 关系变化 → RELATIONSHIP
    MemoryExtractionRule(
        event_type_pattern=r"relationship_changed",
        memory_type=MemoryType.RELATIONSHIP,
        importance_fn=lambda e: 6 if abs(e.data["delta"]) >= 10 else 3,
        content_fn=lambda e: f"{e.data['npc_name']} 信任度 {e.data['delta']:+d}",
    ),
    # 搜索、查看结果 → DISCOVERY
    MemoryExtractionRule(
        event_type_pattern=r"search|look_detail",
        memory_type=MemoryType.DISCOVERY,
        importance_fn=lambda e: 2,
        content_fn=lambda e: e.data.get("description", ""),
    ),
]

class MemoryExtractor:
    def __init__(self, rules: list[MemoryExtractionRule]):
        self._rules = [(re.compile(r.event_type_pattern), r) for r in rules]

    def extract(self, event: Event, turn: int) -> MemoryEntry | None:
        for pattern, rule in self._rules:
            if pattern.match(event.event_type):
                return MemoryEntry(
                    id=f"mem_{event.id}",
                    memory_type=rule.memory_type,
                    content=rule.content_fn(event),
                    importance=rule.importance_fn(event),
                    created_turn=turn,
                    last_relevant_turn=turn,
                )
        return None  # 不是所有事件都产生记忆
```

关键设计决策：
- **不用 LLM 分类**——事件类型是引擎已知的结构化数据，用规则匹配足够可靠且零延迟
- **importance 由事件内容决定**——对话中含秘密（`has_secret`）比闲聊重要，大幅关系变化比小波动重要
- **not 所有事件都产生记忆**——无匹配规则的事件只留在 EventTimeline 中，不进入分类记忆

MemoryExtractor 在 `on_change` 中被调用：新事件产生时遍历 diff 中的 events，提取记忆并 add 到 ClassifiedMemorySystem。

### 与现有代码的集成

- `MemorySystem.build_context()` 替换为 `ClassifiedMemorySystem.build_context()`，返回类型保持 `MemoryContext` dataclass（三字段：`recent_events`、`relationship_summary`、`active_skills_text`），与 `build_narrative_prompt` 接口兼容
- `EventTimeline` 仍然保留（完整事件流），`MemoryExtractor` 从新事件中提取分类记忆
- `RelationshipGraph` 的变更事件自动写入 RELATIONSHIP 类型
- `StoryEngine` 触发节点时自动写入 QUEST 类型
- `SkillManager` 的知识注入归入 LORE 类型

### 测试策略

```python
def test_dialogue_with_secret_produces_lore_memory():
    event = Event(id="e1", event_type="dialogue_summary_bartender",
                  data={"summary_text": "格林透露了地窖的秘密", "has_secret": True})
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=5)
    assert memory.memory_type == MemoryType.LORE
    assert memory.importance == 8

def test_search_produces_low_importance_discovery():
    event = Event(id="e2", event_type="search",
                  data={"description": "桌子下面什么也没有"})
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=5)
    assert memory.memory_type == MemoryType.DISCOVERY
    assert memory.importance == 2

def test_lore_decays_slowly():
    system = ClassifiedMemorySystem(MemoryBudget())
    entry = MemoryEntry("m1", MemoryType.LORE, "秘密", 8, 1, 1)
    score = system._recency_score(entry, current_turn=100)
    assert score > 0.4  # 99 turns 后 LORE 权重仍较高
```

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
    MAX_ENTRIES = 100  # LRU 上限，防止无限增长

    def __init__(self):
        self._cache: OrderedDict[tuple[str, int], SceneContext] = OrderedDict()

    def get(self, location_id: str, state_version: int) -> SceneContext | None:
        key = (location_id, state_version)
        if key in self._cache:
            self._cache.move_to_end(key)  # LRU: 标记为最近使用
            return self._cache[key]
        return None

    def put(
        self, location_id: str, state_version: int, context: SceneContext
    ) -> None:
        key = (location_id, state_version)
        # 同一 location 的旧 version 条目已过期，清理掉
        stale_keys = [
            k for k in self._cache if k[0] == location_id and k[1] < state_version
        ]
        for k in stale_keys:
            del self._cache[k]
        self._cache[key] = context
        self._cache.move_to_end(key)
        # LRU 淘汰
        while len(self._cache) > self.MAX_ENTRIES:
            self._cache.popitem(last=False)

    def invalidate(self, location_id: str | None = None) -> None:
        if location_id is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k[0] == location_id]
            for k in keys_to_remove:
                del self._cache[k]
```

在 prompt builder 中使用：

```python
class CachedPromptBuilder:
    def __init__(self, content_loader: ContentLoader, cache: SceneContextCache):
        self._content = content_loader
        self._cache = cache

    def build_scene_context(self, state: WorldState) -> SceneContext:
        loc_id = state.player_location
        # 用 state_version（每次 commit +1 的递增计数器）而非 turn
        # 一个 turn 内可能有多次 commit（如 TAKE 后立刻 USE），turn 粒度不够
        version = state.version

        cached = self._cache.get(loc_id, version)
        if cached is not None:
            return cached

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

    # 当前位置的物品变更：只失效当前位置缓存
    old_local_items = old.items_at(new.player_location)
    new_local_items = new.items_at(new.player_location)
    if old_local_items != new_local_items:
        scene_cache.invalidate(new.player_location)

    # 当前位置的 NPC 变更：只失效当前位置缓存
    old_local_npcs = old.npcs_at(new.player_location)
    new_local_npcs = new.npcs_at(new.player_location)
    if old_local_npcs != new_local_npcs:
        scene_cache.invalidate(new.player_location)
```

### 与现有代码的集成

- `SceneContextCache` 作为 `GameApp` 的属性，传给 `Narrator`
- `build_narrative_prompt()` 内部先查缓存，命中则跳过重建
- 与设计 #5（响应式 Store）配合：`on_change` 回调中自动失效缓存

---

## 实施路线图

### Phase 1：核心架构（1-2 周）
- **#6 命令注册表** — 最小改动、最高收益，替换 if-elif 分发，建立测试基础
- **#5 响应式 Store** — 在 StateManager 上加 subscribe/onChange
- **#1 FSM 状态机** — 重构 GameApp 为模式分发（依赖 #6 的命令注册表）

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
#6 命令注册表 ───> #1 FSM（FSM 的命令分发依赖 registry）
#1 FSM ──────────> #2 快捷键（依赖 GameMode 枚举）
#1 FSM ──────────> #4 Action 工厂（handler 返回 diff，FSM 负责 commit）

#5 响应式 Store ──┬──> #10 场景缓存（依赖 onChange 失效）
                  ├──> #8 游戏日志（依赖 onChange 触发记录）
                  └──> #9 分类记忆（MemoryExtractor 在 onChange 中提取记忆）

#3 Markdown 内容 ─┬──> #10 场景缓存（ContentLoader 是缓存数据源）
                  └──> story_conditions.py（条件求值器复用）

#7 种子生成器 ────────> 独立，无依赖
```

---

## 跨模块错误处理原则

所有 10 个模块遵循统一的错误处理约定：

**核心规则：handler/callback 抛异常时不崩溃主循环。**

```python
# GameLoop.run() 中
async def run(self):
    while True:
        try:
            handler = self._handlers[self._current_mode]
            raw = await self.renderer.get_input(handler.get_prompt_config(state))
            result = await handler.handle_input(raw, state, context)
            for effect in result.side_effects:
                await self._execute_effect(effect)
            if result.next_mode is not None:
                self._current_mode = result.next_mode
        except KeyboardInterrupt:
            break
        except Exception as e:
            self.logger.log(GameLogEntry(..., entry_type="error", data={"error": str(e)}))
            await self.renderer.render_error(f"内部错误: {e}")
            # 不回滚状态——append-only 语义，已提交的变更保留
```

各模块的具体行为：

| 场景 | 处理方式 |
|------|---------|
| §1 handler 抛异常 | GameLoop 捕获，render_error，保持当前模式 |
| §4 action handler 抛异常 | ActionRegistry.validate_and_execute 捕获，返回 ActionResult(success=False) |
| §5 on_change 回调抛异常 | fire-and-forget task 的异常被 asyncio 捕获并记录到 GameLogger，状态变更已提交不回滚 |
| §6 command execute 抛异常 | handle_command 捕获，render_error |
| §8 GameLogger.flush 失败 | 静默重试一次，仍失败则丢弃该批次（日志丢失可接受，不影响游戏） |
