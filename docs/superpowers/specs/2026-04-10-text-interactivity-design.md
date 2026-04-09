# 文字交互性创新设计方案

> 日期：2026-04-10
> 状态：待实施

## 概述

为 Tavern 奇幻酒馆游戏新增 5 项文字交互创新功能，提升沉浸感和可用性。

---

## 1. 语境感知自动补全

### 问题
当前 `SlashCommandCompleter` 仅补全 `/command`，用户输入自然语言时没有任何辅助。

### 方案

**文件：`src/tavern/cli/renderer.py`**

创建 `ContextualCompleter`，合并斜杠命令补全与游戏状态补全：

- 当输入以 `/` 开头：保持现有斜杠命令补全
- 当输入非 `/` 开头：根据当前场景提供补全
  - NPC 名（当前地点的 `location.npcs` → `character.name`）
  - 物品名（当前地点的 `location.items` + 玩家 `inventory` → `item.name`）
  - 出口方向（`location.exits.keys()`）

`ContextualCompleter` 持有一个 `state_provider: Callable[[], WorldState | None]` 回调，每次补全时调用获取最新状态。

**文件：`src/tavern/cli/app.py`**

初始化 Renderer 时传入 state provider：
```python
self._renderer = Renderer(vi_mode=vi_mode, state_provider=lambda: self.state)
```

补全触发规则：
- 输入长度 >= 1 个字符时开始匹配
- 匹配 NPC 名、物品名时用 `startswith` 或 `in` 匹配
- `display_meta` 显示类型标签（如 "NPC"、"物品"、"出口"）

---

## 2. 叙事内嵌高亮

### 问题
LLM 叙事输出中的 NPC 名、物品名、地点名与普通文字无区分，关键信息淹没在长文中。

### 方案

**文件：`src/tavern/cli/renderer.py`**

新增 `_highlight_entities(text, state)` 方法：

1. 从 WorldState 收集当前已知实体名：
   - NPC 名 → `[bold cyan]{name}[/]`
   - 物品名 → `[cyan]{name}[/]`
   - 地点名 → `[green]{name}[/]`

2. 对文本做字符串替换（按实体名长度降序，避免短名误匹配）

3. 在 `render_stream` 中：
   - 流式输出时仍用 `italic dim`（保持实时反馈）
   - 流式结束后，将累积的完整文本用高亮版本重新渲染（清行 + 重输出）

   实现：累积所有 chunk 到 buffer，流式结束后用 `console.control` 清除已输出的行，然后用高亮版本重新 print。

**简化方案（推荐）**：不做清除重输出（复杂且闪烁），而是直接在流式输出时对每个 chunk 做实体替换。因为 Rich 的 `console.print` 支持 markup，chunk 中如果恰好包含完整实体名就高亮，不完整的不处理。可接受少量遗漏。

更实用的方案：在 `render_stream` 中按行缓冲（遇到 `\n` 时 flush），对完整行做实体替换后输出。这样既保持近实时，又能准确高亮。

---

## 3. 氛围色调系统

### 问题
所有场景的叙事文字都用同一种 `italic dim` 样式，缺乏氛围差异。

### 方案

**文件：`src/tavern/data/scenarios/tavern/world.yaml`**

为每个 location 新增 `atmosphere` 字段：
```yaml
tavern_hall:
  atmosphere: warm     # 暖色调
bar_area:
  atmosphere: warm
cellar:
  atmosphere: cold     # 冷色调
corridor:
  atmosphere: dim      # 昏暗
backyard:
  atmosphere: natural  # 自然
```

**文件：`src/tavern/world/models.py`**

`Location` model 新增：
```python
atmosphere: str = "neutral"
```

**文件：`src/tavern/cli/renderer.py`**

氛围到 Rich style 的映射：
```python
_ATMOSPHERE_STYLES: dict[str, str] = {
    "warm": "italic rgb(255,200,140)",      # 暖黄
    "cold": "italic rgb(140,170,220)",      # 蓝灰
    "dim": "italic rgb(160,160,160)",       # 暗灰
    "natural": "italic rgb(140,200,140)",   # 淡绿
    "danger": "italic rgb(220,140,140)",    # 暗红
    "neutral": "italic dim",               # 默认
}
```

`render_stream` 接收 `atmosphere` 参数，用对应 style 渲染。

---

## 4. 打字机节奏

### 问题
流式输出匀速到达，缺乏戏剧节奏感。

### 方案

**文件：`src/tavern/cli/renderer.py`**

在 `render_stream` 中，根据 chunk 内容在输出后插入微延迟：

```python
import asyncio

PAUSE_CHARS = {"。": 0.3, "！": 0.25, "？": 0.25, "…": 0.4, "——": 0.3, "\n\n": 0.5}
```

逻辑：
- 输出每个 chunk 后，检查末尾字符
- 匹配到标点则 `await asyncio.sleep(delay)`
- 段落分隔（`\n\n`）暂停最长
- 普通文字不暂停（LLM streaming 本身已有自然节奏）

可配置开关，在 `config.yaml` 的 `game` 段：
```yaml
game:
  typewriter_effect: true
```

---

## 5. 交互式快捷标签

### 问题
每次叙事后用户需要从零开始思考下一步行动，认知负担大。

### 方案

**文件：`src/tavern/cli/renderer.py`**

新增 `render_action_hints(hints: list[str])` 方法：
```python
def render_action_hints(self, hints: list[str]) -> None:
    parts = [f"[dim][{i+1}][/] [cyan]{h}[/]" for i, h in enumerate(hints)]
    self.console.print("  ".join(parts))
```

**文件：`src/tavern/cli/app.py`**

新增 `_generate_action_hints(self) -> list[str]` 方法，根据当前场景状态生成 2-3 个建议：

生成规则（按优先级）：
1. 如果场景有 NPC → "和{npc_name}交谈"
2. 如果场景有物品 → "查看{item_name}" 或 "拿起{item_name}"
3. 如果有可用出口 → "前往{exit_desc/direction}"
4. 通用 → "环顾四周"

限制最多 3 个建议，确保多样性（不全是同类型）。

在 `_handle_free_input` 叙事输出后、`render_status_bar` 之前调用。

**输入处理**：在 `run()` 主循环中，如果用户输入是纯数字 "1"/"2"/"3"，映射到对应的 hint 文本，作为正常输入处理。

---

## 涉及文件总览

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `src/tavern/cli/renderer.py` | 修改 | ContextualCompleter、实体高亮、氛围样式、打字机节奏、快捷标签渲染 |
| `src/tavern/cli/app.py` | 修改 | state_provider 传递、快捷标签生成与数字输入映射 |
| `src/tavern/world/models.py` | 修改 | Location 新增 atmosphere 字段 |
| `src/tavern/data/scenarios/tavern/world.yaml` | 修改 | 各 location 新增 atmosphere |
| `config.yaml` | 修改 | 新增 typewriter_effect 配置 |

## 实施顺序

1. **氛围色调系统**（第 3 节）— models + yaml + renderer，改动最小
2. **打字机节奏**（第 4 节）— 仅 renderer，独立
3. **叙事内嵌高亮**（第 2 节）— renderer，需要 state 访问
4. **语境感知自动补全**（第 1 节）— renderer + app，需要 state provider 机制
5. **交互式快捷标签**（第 5 节）— app + renderer，依赖 state 访问机制
