# Phase 5A: 基础设施接线设计

**目标**：将 Phase 1-4 构建的基础设施组件（ContentLoader、KeybindingResolver、Markdown 渲染）接入实际运行时，使其端到端生效。

**范围**：3 个独立方向，无相互依赖。

**不在范围**：COMBAT / INVENTORY / SHOP mode handler（Phase 5B 单独设计）。

---

## §1 YAML→Markdown 内容迁移

### 1.1 目标

将 `world.yaml` / `characters.yaml` 中的文本描述迁移到 Markdown 文件，启用 ContentLoader 的 frontmatter + variant 机制。

### 1.2 Markdown 文件结构

```
data/scenarios/tavern/content/
├── locations/
│   ├── tavern_hall.md
│   ├── tavern_hall.night.md   # variant 示范
│   ├── bar_area.md
│   ├── cellar.md
│   ├── corridor.md
│   └── backyard.md
├── items/
│   ├── old_notice.md
│   ├── cellar_key.md
│   ├── old_barrel.md
│   ├── abandoned_cart.md
│   ├── dry_well.md
│   ├── rusty_box.md
│   ├── spare_key.md
│   ├── lost_amulet.md
│   ├── map_fragment.md
│   └── guest_letter.md
└── characters/
    ├── traveler.md
    ├── bartender_grim.md
    └── mysterious_guest.md
```

### 1.3 Markdown 文件格式

**Location 示例**（`tavern_hall.md`）：

```markdown
---
id: tavern_hall
type: location
variants:
  - name: night
    when: "turn > 20"
---

你走进醉龙酒馆的大厅。壁炉中跳动着温暖的火焰，照亮了斑驳的石墙...
```

**Item 示例**（`old_notice.md`）：

```markdown
---
id: old_notice
type: item
---

一张泛黄的旧告示，边角已经卷曲。上面用潦草的字迹写着...
```

**Character 示例**（`traveler.md`）：

```markdown
---
id: traveler
type: character
---

一位风尘仆仆的旅行者，名叫艾琳。她穿着一件已经磨损的旅行斗篷...
```

### 1.4 Variant 文件

`tavern_hall.night.md`（无 frontmatter，纯 body）：

```markdown
夜色笼罩了酒馆大厅。壁炉的火焰已经暗淡下来，只剩几点余烬...
```

ContentLoader 的 variant 匹配规则（已实现）：文件名 `{base_id}.{variant_name}.md`，在 `resolve()` 时通过 `condition_evaluator` 决定是否使用。

### 1.5 代码改动

**`GameApp.__init__`（app.py）**：

```python
from tavern.content.loader import ContentLoader

content_loader = ContentLoader()
content_dir = scenario_path / "content"
if content_dir.exists():
    content_loader.load_directory(content_dir)

self._game_loop = bootstrap(
    ...,
    content_loader=content_loader,  # 目前传 None
)
```

**`CachedPromptBuilder`（cached_builder.py）**：

新增两个方法：

```python
def resolve_item(self, item_id: str) -> str | None:
    """查询 item 的 Markdown 描述，fallback 返回 None。"""
    if self._content is None:
        return None
    return self._content.resolve(item_id)

def resolve_character(self, char_id: str) -> str | None:
    """查询 character 的 Markdown 描述，fallback 返回 None。"""
    if self._content is None:
        return None
    return self._content.resolve(char_id)
```

**`build_scene_context` 已有的 location 查询逻辑不变**（先 ContentLoader，fallback 到 YAML description）。

**Condition evaluator**：

为 variant 提供 `condition_evaluator` 回调，在 `build_scene_context` 中：

```python
def _eval_condition(self, when: str, state: WorldState) -> bool:
    """简单表达式求值：支持 'turn > N' 格式。"""
    # 仅支持 turn 比较，后续可扩展
```

### 1.6 YAML 字段保留

YAML 中的 `description` 字段继续保留作为 fallback。ContentLoader 无对应 Markdown 文件时自动降级到 YAML 描述，实现渐进迁移。

---

## §2 KeybindingResolver 接入 prompt_toolkit

### 2.1 目标

将 KeybindingResolver 的 game-level 快捷键（n/s/e/w 移动、l 查看等）接入 prompt_toolkit 键盘事件系统，使快捷键在运行时生效。

### 2.2 架构

```
KeybindingResolver (已有，纯逻辑层)
       ↓ resolve(key, mode, input_mode, buffer_empty) → action | None
KeybindingBridge (新建，适配层)
       ↓ build_ptk_bindings(mode, on_action) → KeyBindings
prompt_toolkit PromptSession / Application
       ↓
Renderer.get_input() → raw input string
       ↓
GameLoop.run() → handler.handle_input(raw, ...)
```

### 2.3 新文件：`src/tavern/engine/keybinding_bridge.py`

```python
from prompt_toolkit.key_binding import KeyBindings

class KeybindingBridge:
    """将 KeybindingResolver 映射转为 prompt_toolkit KeyBindings。"""

    ACTION_TO_TEXT: dict[str, str] = {
        "move_north": "前往北方",
        "move_south": "前往南方",
        "move_east": "前往东方",
        "move_west": "前往西方",
        "look_around": "/look",
        "open_inventory": "/inventory",
        "talk_nearest": "和最近的人交谈",
        "show_help": "/help",
        "save_game": "/save",
        "end_dialogue": "bye",
        "select_hint_1": "1",  # 对话模式数字选择
        "select_hint_2": "2",
        "select_hint_3": "3",
    }

    def __init__(self, resolver: KeybindingResolver) -> None:
        self._resolver = resolver

    def build_ptk_bindings(
        self,
        mode: GameMode,
        on_action: Callable[[str], None],
    ) -> KeyBindings:
        """为指定 mode 构建 prompt_toolkit 按键绑定。

        on_action: 回调函数，接收转换后的文本指令。
        """
        bindings = KeyBindings()
        # 遍历 resolver 中该 mode 的所有绑定，注册 ptk handler
        # handler 内部调用 resolver.resolve() 并通过 ACTION_TO_TEXT 转换
        return bindings
```

### 2.4 桥接机制

1. **按键事件** → prompt_toolkit 触发 handler
2. **handler 内部**：调用 `resolver.resolve(key, current_mode, input_mode, buffer_empty)`
3. **resolve 返回 action 字符串**（如 `"move_north"`）
4. **`ACTION_TO_TEXT[action]`** 映射为中文指令或斜杠命令
5. **调用 `on_action(text)`**，在 Renderer 中实现为 `app.exit(result=text)`

### 2.5 Renderer 改动

**`get_input()` 方法**：

```python
async def get_input(self, extra_bindings: KeyBindings | None = None) -> str:
    merged = merge_key_bindings([self._session.key_bindings, extra_bindings])
    # 或者在 PromptSession 初始化时设置
```

**`get_input_with_card_hints()`**：card UI 的硬编码绑定保持不变，KeybindingBridge 的绑定在 card 模式下不生效（DIALOGUE mode 只有 1/2/3/escape）。

### 2.6 GameLoop 集成

GameLoop.run() 中每次输入前：

```python
ptk_bindings = bridge.build_ptk_bindings(
    self._current_mode,
    on_action=lambda text: ...,
)
raw = await renderer.get_input(extra_bindings=ptk_bindings)
```

### 2.7 ModeContext 扩展

`ModeContext` 新增可选字段：

```python
keybinding_bridge: Any = None  # KeybindingBridge 实例
```

`bootstrap()` 中实例化 `KeybindingResolver(DEFAULT_BINDINGS)` + `KeybindingBridge(resolver)` 并注入。

### 2.8 不在范围

- COMBAT mode 的快捷键执行逻辑（Phase 5B）
- 用户自定义键绑定配置文件

---

## §3 Renderer Markdown 渲染

### 3.1 目标

叙事输出支持 Markdown 格式渲染（粗体、斜体、列表等），同时保留打字机效果。

### 3.2 核心方案：`rich.Live` + `rich.Markdown` 渐进渲染

```python
from rich.live import Live
from rich.markdown import Markdown

async def render_stream(self, stream, *, atmosphere="neutral"):
    style = _ATMOSPHERE_STYLES.get(atmosphere, ...)
    buffer = ""
    with Live(
        Markdown(""),
        console=self.console,
        refresh_per_second=15,
        vertical_overflow="visible",
    ) as live:
        async for chunk in stream:
            buffer += chunk
            live.update(Markdown(buffer))
            if self._typewriter_effect:
                stripped = chunk.rstrip()
                if stripped:
                    last_char = stripped[-1]
                    if last_char in _TYPEWRITER_PAUSES:
                        await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
```

### 3.3 atmosphere 样式

当前 `_ATMOSPHERE_STYLES` 用 Rich markup 包裹文本（如 `[italic rgb(255,210,160)]`）。Markdown 渲染后无法直接套用这种方式。

**方案**：用 `rich.Live` 的 console style 或 `Panel` 包裹 Markdown 输出：

```python
from rich.panel import Panel

styled_md = Panel(Markdown(buffer), style=atmosphere_style, box=box.SIMPLE)
live.update(styled_md)
```

或者直接在 `Live` 的 `renderable` 外层套一个 `Styled` 对象。

### 3.4 Entity 高亮

Markdown 渲染后 Rich markup 标签（`[bold cyan]...[/]`）会被转义为纯文本。

**方案**：不再对叙事文本做 `_highlight_entities` 后处理。改为在 LLM prompt 中指示用 Markdown 加粗标记实体名称（`**名字**`），这样 `rich.Markdown` 会自动渲染为粗体。

`_highlight_entities` 仍保留给非 Markdown 渲染路径（`render_result` 等非叙事输出）。

### 3.5 其他渲染点适配

| 方法 | 改动 |
|------|------|
| `render_stream` | Live + Markdown 渐进渲染 |
| `render_welcome` | `location.description` 如果来自 ContentLoader，用 `Markdown()` 渲染 |
| `render_result` | 不改，保持简单文本 + Rich markup |
| `render_dialogue_*` | 不改，对话保持现有逻辑 |
| `render_inventory` | 不改 |

### 3.6 Markdown 渲染辅助

新增工具函数（在 renderer.py 内部或新文件 `src/tavern/cli/markdown_renderer.py`）：

```python
def render_markdown_text(console: Console, text: str) -> None:
    """渲染 Markdown 文本到终端。非流式场景使用。"""
    from rich.markdown import Markdown
    console.print(Markdown(text))
```

### 3.7 不做的事

- 不改 Panel / Table / 状态栏等 UI 组件
- 不改对话系统渲染
- 不给 Markdown 渲染添加自定义主题（使用 Rich 默认 Markdown 样式）

---

## 依赖关系

3 个方向彼此独立，可以并行实施：

```
§1 内容迁移 ─────┐
§2 Keybinding ───┼─→ 集成验证
§3 Markdown 渲染 ─┘
```

集成验证：§1 的 Markdown 内容通过 §3 的渲染管道显示，形成端到端闭环。

## 测试策略

| 方向 | 测试类型 |
|------|----------|
| §1 | ContentLoader 加载 Markdown 文件、CachedPromptBuilder 新方法、condition evaluator |
| §2 | KeybindingBridge 构建 ptk bindings、action→text 映射、Renderer 接受 extra_bindings |
| §3 | render_stream Live+Markdown 输出、render_welcome Markdown 适配 |
