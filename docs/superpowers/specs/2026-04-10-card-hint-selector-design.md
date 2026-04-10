# Card-Style Hint Selector Design

## Context

当前 hint 选择使用 prompt_toolkit 的 `bottom_toolbar` 横排显示，体验不够直观。需要改为垂直卡片式选择 UI，选中项用边框包裹，上下键切换，Enter 确认执行。同时集成自由输入行作为第 4 个选项。

## Architecture

### 核心组件

`Renderer.get_input_with_card_hints(hints: list[str]) -> str`

替换现有 `get_input_with_hints()`，使用 `prompt_toolkit.Application` + 自定义 `Layout` 实现。

### 技术选型

使用 `FormattedTextControl` 渲染整个 UI（3 个 hint + 1 个输入行 + 导航提示），手动管理输入文本（不用 `Buffer`/`BufferControl`）。原因：`BufferControl` 的光标定位与卡片边框难以对齐，手动管理输入文本 + `_` 模拟光标更简单。

### 调用链

```
app.py: run() 主循环
  → renderer.get_input_with_card_hints(hints)
    → 构建 Application(layout, key_bindings, full_screen=False)
    → app.run_async() → 返回选中的文本
```

无 hints 时退化为 `get_input()`。

## UI Rendering

### 视觉效果

```
selected_index=0:

  ╭──────────────────────────╮
  │ 仔细阅读告示             │
  ╰──────────────────────────╯
    向艾琳展示告示
    检查纸张材质
    ▸ _

  ↑↓ 切换  ↵ 确认

selected_index=3 (输入行):

    仔细阅读告示
    向艾琳展示告示
    检查纸张材质
  ╭──────────────────────────╮
  │ ▸ 和酒保聊天_            │
  ╰──────────────────────────╯

  ↑↓ 切换  ↵ 确认
```

### 卡片宽度

取所有 hint 和输入文本中最长项 + 固定 padding。最小宽度 20 字符，最大 40 字符。每次按键重新计算，对齐到最长项。

### 样式

| 元素 | 样式 |
|------|------|
| 选中项边框 | ansicyan |
| 选中项文字 | bold |
| 未选中项文字 | ansiwhite |
| 导航提示 | ansigray |
| ▸ 符号 | ansigreen |

## Key Bindings

| 按键 | 行为 |
|------|------|
| ↑ / ↓ | 在 4 个选项间循环（0→1→2→3→0） |
| Enter | 选中 0-2 → 返回该 hint 文本；选中 3 → 返回输入框文本（空则不响应） |
| 可打印字符 | 若当前在 0-2，自动跳到第 3 项并追加字符；已在第 3 项直接追加 |
| Backspace | 仅在第 3 项时删除末尾字符 |
| Ctrl+C / Ctrl+D | 返回 "/quit" |
| 1 / 2 / 3 | 输入框为空时作为快捷键直接返回对应 hint；输入框非空时当普通字符 |

### 边界情况

- hints 为空 → 退化为普通 `get_input()`
- hints 只有 1-2 个 → 选项数 = len(hints) + 1，正常循环
- 输入框 `/` 开头 → 正常返回，app.py 命令路由处理

## Integration

### 改动文件

**renderer.py**:
- 删除 `get_input_with_hints()` → 新增 `get_input_with_card_hints()`
- 删除 `render_action_hints()`（不再需要）
- 新增导入：`Application`, `Layout`, `HSplit`, `Window`, `FormattedTextControl`

**app.py**:
- 主循环调用 `get_input_with_card_hints(hints)` 替换 `get_input_with_hints(hints)`

### 不改动

- `_generate_smart_hints()` 不变
- LLM service 层不变
- 对话系统不变

## Testing

- 更新 `test_renderer.py` 中 hint 相关测试
- 测试点：无 hints 退化、返回值类型、数字快捷键逻辑
