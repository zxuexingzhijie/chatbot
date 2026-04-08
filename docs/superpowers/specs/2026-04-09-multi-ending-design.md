# 多结局系统 — 设计规格文档

> 日期: 2026-04-09
> 状态: 设计完成，待实施
> 依赖: Phase 4 支线任务系统全部完成

---

## 1. 目标

为酒馆场景添加 3 个结局（好/坏/中），采用混合触发机制（综合评分 + 关键决策点）。结局触发后由 LLM 生成纯叙事，玩家可继续探索。纯数据驱动——结局是普通 story nodes，不新增引擎概念。

---

## 2. 新增条件类型

### 2.1 quest_count — 任务完成数统计

```yaml
- type: quest_count
  check: completed    # 匹配 quests 中 status == 此值的数量
  operator: ">="
  value: 2            # 阈值
```

实现：遍历 `state.quests`，统计 `q.get("status") == cond.check` 的数量，与 `value` 做数值比较（复用 relationship 条件的运算符逻辑）。

注册到 `CONDITION_REGISTRY`（`story_conditions.py`）。

### 2.2 turn_count — 回合数检查

```yaml
- type: turn_count
  operator: ">="
  value: 40
```

实现：`state.turn` 与 `value` 做数值比较。一行评估器。

注册到 `CONDITION_REGISTRY`。

---

## 3. 状态模型扩展

### 3.1 WorldState 新增字段

```python
endings_reached: tuple[str, ...] = ()  # 已触发的结局 ID
```

`WorldState.apply` 处理：`self.endings_reached + diff.new_endings`。

`freeze_mutable_fields` 不需要处理此字段（tuple 本身不可变）。

### 3.2 StateDiff 新增字段

```python
new_endings: tuple[str, ...] = ()  # 本次触发的结局 ID
```

`_merge_diffs` 合并策略：元组拼接 `a.new_endings + b.new_endings`。

### 3.3 StoryEffects 新增字段

```python
trigger_ending: str | None = None  # 结局 ID，None 表示非结局节点
```

`_build_result` 中如果 `trigger_ending` 非 None，写入 `StateDiff.new_endings = (trigger_ending,)`。

YAML loader 解析：`effects.trigger_ending` 字段（字符串或缺省为 None）。

---

## 4. 结局叙事生成

### 4.1 Narrator 扩展

在 `narrator.py` 中新增方法：

```python
def build_ending_prompt(
    ending_id: str,
    narrator_hint: str,
    state: WorldState,
    memory: MemoryContext | None = None,
) -> list[dict]:
```

系统 prompt 引导 LLM 生成结局叙事：
- 角色定位：你是一位叙事大师，为这段冒险故事画上句号
- 注入上下文：已完成的任务列表、持有物品、NPC 关系状态
- `narrator_hint` 提供具体叙事方向
- 输出风格：200-300 字，结局感，余韵收束

### 4.2 CLI 呈现

`DialogueManager` 处理 story results 时检测 `diff.new_endings`：
- 调用 narrator 的 ending 方法生成叙事
- 用 Rich Panel 特殊样式渲染（标题 + 边框，区别于普通叙事）
- 渲染后不退出游戏循环，玩家可继续 free roam

---

## 5. 三个结局设计

### 5.1 好结局 — 「黎明之路」

**Story Node**: `ending_good`

**触发条件**（全部满足）：
- `cellar_secret_revealed` 已完成（event: `secret_learned` exists）
- `quest_count >= 2`（至少 2 条支线 status == completed）
- relationship: traveler trust >= 20

**Effects**:
- `trigger_ending: good_ending`
- `quest_updates: { main_story: { status: good_ending } }`
- `new_events: [{ id: ending_good_reached, type: ending, description: "玩家达成好结局「黎明之路」" }]`

**narrator_hint**: "玩家赢得了酒馆众人的信任，揭开了密道的秘密。艾琳愿意与你同行，格里姆终于露出了难得的笑容。新的冒险在密道的尽头等待着你。用温暖、希望的笔触收束这段故事。"

### 5.2 坏结局 — 「暗影独行」

需要先新增一个决策节点：

**Story Node**: `betray_guest`（决策节点）

**触发条件**：
- inventory: guest_letter（持有神秘信件）
- location: bar_area（在吧台区）
- event: `talked_to_bartender_about_letter` exists（与酒保对话提及信件 — 此事件由对话系统产生，需在 skills 中引导）

**Effects**:
- `remove_items: [{ item_id: guest_letter, from: inventory }]`
- `character_stat_deltas: { bartender_grim: { trust: 30 }, mysterious_guest: { trust: -50 } }`
- `quest_updates: { guest_betrayal: { status: completed } }`
- `new_events: [{ id: guest_betrayed, type: story, description: "玩家将神秘旅客的信件交给了酒保" }]`

**narrator_hint**: "玩家做出了背叛的选择。酒保接过信件时眼中闪过贪婪的光芒。"

---

**Story Node**: `ending_bad`

**触发条件**：
- event: `guest_betrayed` exists

**Effects**:
- `trigger_ending: bad_ending`
- `quest_updates: { main_story: { status: bad_ending } }`
- `new_events: [{ id: ending_bad_reached, type: ending, description: "玩家达成坏结局「暗影独行」" }]`

**narrator_hint**: "你出卖了神秘旅客的信任。格里姆收下信件，脸上浮现出意味深长的笑容。走廊里传来沉重而急促的脚步声——神秘旅客已经消失在夜色中。你得到了酒保的信任，却失去了更重要的东西。用阴暗、孤独的笔触收束。"

### 5.3 中结局 — 「过客」

**Story Node**: `ending_neutral`

**触发条件**（全部满足）：
- turn_count >= 40
- event: `ending_good_reached` check: not_exists
- event: `ending_bad_reached` check: not_exists

**Effects**:
- `trigger_ending: neutral_ending`
- `quest_updates: { main_story: { status: neutral_ending } }`
- `new_events: [{ id: ending_neutral_reached, type: ending, description: "玩家达成中结局「过客」" }]`

**narrator_hint**: "夜深了，你终究只是酒馆里的一个过客。一些谜团仍未解开，一些故事仍在继续。你推开酒馆的门，走进晨雾弥漫的街道。身后传来隐约的笑声和杯盏碰撞声。用淡然、若有所思的笔触收束。"

### 5.4 新增 Skills

**`bartender_letter_hint.yaml`** — 引导酒保在特定条件下提及信件话题：
- character: bartender_grim
- 激活条件：玩家持有 guest_letter + 在 bar_area
- facts：注意到玩家手中的信件、对信件上的徽章感兴趣
- behavior：旁敲侧击，暗示可以"帮忙处理"

---

## 6. 代码改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/tavern/engine/story_conditions.py` | Modify | 新增 `quest_count`、`turn_count` 条件评估器 |
| `src/tavern/world/state.py` | Modify | WorldState 新增 `endings_reached`；StateDiff 新增 `new_endings` |
| `src/tavern/engine/rules.py` | Modify | `_merge_diffs` 处理 `new_endings` |
| `src/tavern/engine/story.py` | Modify | StoryEffects 新增 `trigger_ending`；`_build_result` 扩展；loader 解析 |
| `src/tavern/narrator/narrator.py` | Modify | 新增 `build_ending_prompt` 方法 |
| `src/tavern/narrator/prompts.py` | Modify | 新增结局叙事系统 prompt 模板 |
| `src/tavern/dialogue/manager.py` | Modify | 检测 `new_endings` 并调用结局叙事 |
| `data/scenarios/tavern/story.yaml` | Modify | 新增 4 个 story nodes |
| `data/scenarios/tavern/skills/bartender_letter_hint.yaml` | Create | 酒保信件提示 skill |
| `tests/engine/test_story_conditions.py` | Modify | 覆盖 `quest_count`、`turn_count` |
| `tests/world/test_state.py` | Modify | 覆盖 `endings_reached` apply |
| `tests/engine/test_story.py` | Modify | 覆盖 `trigger_ending` 效果和 loader |
| `tests/narrator/test_narrator.py` | Modify | 覆盖 `build_ending_prompt` |

---

## 7. 不做的事情

- 不新增动作类型（GIVE/TRADE/BETRAY）— betray_guest 通过 story node 被动触发
- 不修改游戏循环结构 — 结局只是 story result 的特殊处理
- 不做结局回放/收藏/成就系统
- 不做结局统计面板（用户选择了纯叙事）
- 不新增 NPC 或地图区域
- 中结局不会阻断游戏 — 触发后标记但玩家可继续，可能后续触发好/坏结局
