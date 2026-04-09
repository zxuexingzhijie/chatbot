# 关系可视化（status 命令增强） — 设计规格文档

> 日期: 2026-04-09
> 状态: 设计完成，待实施
> 依赖: 无（纯 UI 改动）

---

## 1. 目标

将 `status` 命令从裸 stats 输出升级为信息丰富的状态面板，包含三个区域：属性概览、人际关系连线、任务进度。纯 renderer 层改动，不涉及引擎或状态模型。

---

## 2. 渲染效果

```
角色状态 — 冒险者
━━━━━━━━━━━━━━━━━━━━━━━━
属性: HP 100 | Gold 50

人际关系:
  ★ 你 ──[+25 友好]──▶ 酒保格里姆
  ★ 你 ──[+40 友好]──▶ 旅行者
  ★ 你 ──[-15 敌对]──▶ 神秘旅客

任务进度:
  ● 地下室之谜 ········ active
  ● 旅行者委托 ········ completed
```

---

## 3. 接口设计

### 3.1 `render_status` 新签名

```python
def render_status(
    self,
    state: WorldState,
    relationships: list[Relationship],
) -> None:
```

- `state`: 提供 player stats、quests
- `relationships`: 由 `app.py` 从 `RelationshipGraph.get_all_for(player_id)` 提取后传入

**Renderer 不依赖 MemorySystem**——只接收纯数据类型 `list[Relationship]`。

### 3.2 `app.py` 调用处修改

```python
elif command == "status":
    relationships = self._memory.get_player_relationships()
    self._renderer.render_status(self.state, relationships)
```

`MemorySystem.get_player_relationships()` 是一个便利方法，委托给 `RelationshipGraph.get_all_for(state.player_id)`。

---

## 4. 渲染细节

### 4.1 属性行

紧凑单行，替代现有逐行打印：

```python
stats_line = " | ".join(f"{k} [green]{v}[/]" for k, v in player.stats.items())
console.print(f"  属性: {stats_line}")
```

### 4.2 人际关系连线

遍历 `relationships: list[Relationship]`，每条关系渲染为带颜色的连线：

```
★ 你 ──[+25 友好]──▶ NPC名
```

颜色规则（复用 `RelationshipGraph.describe_for_prompt` 的值域）：

| 值域 | 标签 | 颜色 |
|------|------|------|
| >= 60 | 非常友好 | bright_green |
| >= 20 | 友好 | green |
| (-20, 20) | 中立 | yellow |
| <= -20 | 敌对 | red |
| <= -60 | 非常敌对 | bright_red |

需要从 `state.characters` 查找 NPC 的 `name` 来替换 ID 展示。无关系时显示 `[dim]（尚无人际关系记录）[/]`。

### 4.3 任务进度

遍历 `state.quests`：

- 有记录的任务用 `●`，根据 status 显示：
  - `completed` → `[green]completed[/]`
  - `active` → `[cyan]active[/]`
  - 其他 → `[yellow]{status}[/]`
- 无任务时显示 `[dim]（暂无任务记录）[/]`

不显示"未开始"的任务（我们无法得知全部可能的支线，只展示已触发的）。

### 4.4 整体布局

用 Rich `Panel` 包裹全部内容，`border_style="bright_blue"`，标题为 `"📊 角色状态"`。三个区域用空行分隔。

---

## 5. 代码改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/tavern/cli/renderer.py:72-77` | Modify | 重写 `render_status`，新增 `_relationship_label` 私有方法 |
| `src/tavern/cli/app.py:149-150` | Modify | `status` 命令处理时提取 relationships 传入 |
| `src/tavern/world/memory.py` | Modify | 新增 `MemorySystem.get_player_relationships()` 便利方法 |
| `tests/cli/test_renderer.py` | Modify | 覆盖新 `render_status` 三个区域的渲染 |
| `tests/world/test_memory.py` | Modify | 覆盖 `get_player_relationships` |

---

## 6. 不做的事情

- 不实现 `multi_hop` 图查询（spec 中提到但本次不需要）
- 不修改 `render_status_bar`（顶部状态栏保持不变）
- 不展示 NPC 之间的关系（只展示玩家与 NPC 的关系）
- 不展示未触发的任务
