# 支线任务系统 — 设计规格文档

> 日期: 2026-04-08
> 状态: 设计完成，待实施
> 依赖: Phase 3 全部完成（story engine、item-use-system、save/load）

---

## 1. 目标

为酒馆场景添加 3 条支线任务，丰富可玩内容，为多结局系统铺路。纯数据驱动——不新增动作类型（GIVE/TRADE），全部通过 story nodes + skills YAML + 扩展 effects 实现。

---

## 2. StoryEffects 扩展

当前 `StoryEffects` 只有 `quest_updates` 和 `new_events`。新增 3 个字段：

### 2.1 add_items — 物品生成

```yaml
add_items:
  - item_id: map_fragment
    to: inventory          # "inventory" 或 location_id
```

映射到 `StateDiff.updated_characters`（背包）或 `StateDiff.updated_locations`（场景 items）。

### 2.2 remove_items — 物品移除

```yaml
remove_items:
  - item_id: lost_amulet
    from: inventory        # "inventory" 或 location_id
```

映射到同样的 StateDiff 字段，从对应容器中过滤掉指定物品。

### 2.3 character_stat_deltas — 增量属性修改

```yaml
character_stat_deltas:
  bartender_grim:
    trust: 20              # 增量，非绝对值
  traveler:
    trust: 10
```

映射到新的 `StateDiff.character_stat_deltas` 字段。`WorldState.apply` 做 `current_val + delta`。

与现有 `updated_characters`（set 语义）互不干扰：
- `updated_characters`: 覆盖字段（如 location_id、inventory）
- `character_stat_deltas`: 增量修改 stats 子字段

---

## 3. StateDiff 扩展

```python
class StateDiff(BaseModel):
    # ... 现有字段 ...
    character_stat_deltas: dict[str, dict[str, int]] = {}
```

`WorldState.apply` 新增逻辑：

```python
for char_id, deltas in diff.character_stat_deltas.items():
    char = current.characters[char_id]
    new_stats = dict(char.stats)
    for stat_name, delta_val in deltas.items():
        new_stats[stat_name] = new_stats.get(stat_name, 0) + delta_val
    # 更新 character 的 stats
```

`_merge_diffs` 中 `character_stat_deltas` 合并策略：同 character 同 stat 时累加 delta 值。

---

## 4. StoryEngine 扩展

### 4.1 StoryEffects 数据类

```python
@dataclass(frozen=True)
class ItemPlacement:
    item_id: str
    to: str              # "inventory" 或 location_id

@dataclass(frozen=True)
class ItemRemoval:
    item_id: str
    from_: str           # "inventory" 或 location_id

@dataclass(frozen=True)
class StoryEffects:
    quest_updates: dict[str, dict]
    new_events: tuple[NewEventSpec, ...]
    add_items: tuple[ItemPlacement, ...] = ()
    remove_items: tuple[ItemRemoval, ...] = ()
    character_stat_deltas: dict[str, dict[str, int]] = field(default_factory=dict)
```

### 4.2 `_build_result` 扩展

在构建 `StateDiff` 时，额外处理 `add_items`、`remove_items`、`character_stat_deltas`：

- `add_items`: to="inventory" → 追加到 player inventory；to=location_id → 追加到 location.items
- `remove_items`: from_="inventory" → 从 player inventory 过滤；from_=location_id → 从 location.items 过滤
- `character_stat_deltas`: 直接透传到 `StateDiff.character_stat_deltas`

### 4.3 YAML Loader 扩展

`load_story_nodes` 解析新字段：

```yaml
effects:
  quest_updates: ...
  new_events: ...
  add_items:
    - item_id: map_fragment
      to: inventory
  remove_items:
    - item_id: lost_amulet
      from: inventory
  character_stat_deltas:
    traveler:
      trust: 20
```

---

## 5. 三条支线任务设计

### 5.1 支线 A — 旅行者艾琳的失物

**概要**: 艾琳在旅途中丢失了一个护身符，请玩家帮忙在后院找到。

**新物品**:
- `lost_amulet`: 艾琳的护身符（后院可搜索到，portable: true）
- `map_fragment`: 地图碎片（奖励，含密道额外线索，portable: true）

**Story Nodes (3 个)**:

| Node ID | 触发条件 | Effects | narrator_hint |
|---------|---------|---------|---------------|
| `traveler_quest_start` | 与 traveler 对话 (event: `talked_to_traveler` exists) | quest: traveler_quest=active; event: traveler_quest_accepted; add_items: lost_amulet→backyard | 艾琳恳请帮忙，语气诚恳焦急 |
| `amulet_found` | inventory 含 lost_amulet | quest: traveler_quest=amulet_found; event: amulet_picked_up | 护身符泛着微光，似乎有特殊意义 |
| `traveler_quest_complete` | event: amulet_picked_up exists + location: tavern_hall | quest: traveler_quest=completed; remove_items: lost_amulet→inventory; add_items: map_fragment→inventory; character_stat_deltas: traveler trust+20; event: traveler_quest_done | 艾琳感激地接过护身符，递给你一张泛黄的地图碎片 |

**Fail Forward**:
- `traveler_quest_start`: 8 回合后艾琳主动搭话提及丢失物品
- `amulet_found`: 15 回合后提示"后院马车附近似乎有什么东西在发光"

**Skills YAML**:
- `traveler_quest_info.yaml`: 激活条件 quest traveler_quest=active。facts: 护身符是家传宝物、可能掉在后院马车附近。behavior: 焦急但友善。
- `traveler_gratitude.yaml`: 激活条件 quest traveler_quest=completed。facts: 地图碎片来源、密道的额外信息。behavior: 感激、愿意分享更多旅途见闻。

### 5.2 支线 B — 神秘旅客的委托

**概要**: 神秘旅客想知道酒保在地下室藏了什么，请玩家调查后回来汇报。

**新物品**:
- `guest_letter`: 神秘信件（奖励，为多结局铺路，portable: true）

**Story Nodes (3 个)**:

| Node ID | 触发条件 | Effects | narrator_hint |
|---------|---------|---------|---------------|
| `guest_quest_start` | relationship: mysterious_guest trust >= 5 + location: corridor | quest: guest_quest=active; event: guest_quest_accepted | 神秘旅客压低声音，语气紧迫而谨慎 |
| `cellar_reported` | quest: guest_quest=active + event: cellar_entered exists + location: corridor | quest: guest_quest=reported; event: cellar_info_shared | 你把地下室的发现告诉了神秘旅客 |
| `guest_quest_complete` | event: cellar_info_shared exists | quest: guest_quest=completed; add_items: guest_letter→inventory; character_stat_deltas: mysterious_guest trust+15; event: guest_quest_done | 神秘旅客递给你一封密封的信件，眼中闪过复杂的神色 |

**触发说明**: mysterious_guest 初始 trust=-10，需要 PERSUADE 提升 trust 到 >= 5（至少一次成功说服）。`cellar_entered` 事件由主线节点 `cellar_mystery_discovered` 产生，支线复用主线事件。

**Fail Forward**:
- `guest_quest_start`: 10 回合后神秘旅客在走廊低语"如果你愿意帮忙..."
- `cellar_reported`: 无（玩家必须主动回来）

**Skills YAML**:
- `guest_quest_info.yaml`: 激活条件 quest guest_quest=active。facts: 怀疑酒保藏了重要东西、地下室有异常。behavior: 冷静、点到为止、不透露自己身份。
- `guest_secret_knowledge.yaml`: 激活条件 quest guest_quest=completed。facts: 信件内容暗示、密道与城外势力有关。behavior: 稍微放下戒备、暗示后续故事。

### 5.3 支线 C — 后院铁盒

**概要**: 搜索后院废弃马车发现铁盒，打开获得备用钥匙（主线捷径）。

**新物品**: 无（rusty_box、spare_key 已在 world.yaml 中定义）

**Story Nodes (2 个)**:

| Node ID | 触发条件 | Effects | narrator_hint |
|---------|---------|---------|---------------|
| `cart_searched` | location: backyard + event: searched_backyard exists | quest: backyard_search=found_box; event: cart_search_complete; add_items: rusty_box→backyard（如果不在） | 马车篷布下露出一个生锈的铁盒 |
| `box_opened` | event: box_opened exists | quest: backyard_search=completed; event: spare_key_obtained | 铁盒里的备用钥匙，或许能打开什么 |

**触发说明**:
- `searched_backyard` 事件由玩家在后院执行 SEARCH 动作产生（现有 SEARCH handler 已生成 look 事件，需确认 event ID 格式）
- `box_opened` 事件由 rusty_box 的 `use_effects.story_event` 写入 timeline（event ID: `box_opened`，无后缀）

**Fail Forward**:
- `cart_searched`: 5 回合后"月光照在马车上，篷布下似乎有东西反光"

**Skills YAML**: 无（纯环境交互，不涉及 NPC 对话）

---

## 6. 物品汇总

world.yaml 新增：

```yaml
lost_amulet:
  name: 银质护身符
  description: 一个精致的银质护身符，表面刻着古老的符文，散发着微弱的光芒
  portable: true

map_fragment:
  name: 地图碎片
  description: 一张泛黄的羊皮纸碎片，上面标注着城镇地下的密道走向
  portable: true

guest_letter:
  name: 神秘信件
  description: 一封密封的信件，火漆上印着一个陌生的徽章。信纸透出淡淡的墨香
  portable: true
```

---

## 7. 代码改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `world/state.py` | Modify | StateDiff 新增 character_stat_deltas；WorldState.apply 处理增量 |
| `engine/rules.py` | Modify | _merge_diffs 合并 character_stat_deltas |
| `engine/story.py` | Modify | StoryEffects 新增 3 字段 + 数据类；_build_result 扩展；loader 解析新字段 |
| `data/scenarios/tavern/world.yaml` | Modify | 新增 3 个物品 |
| `data/scenarios/tavern/story.yaml` | Modify | 新增 8 个支线 story nodes |
| `data/scenarios/tavern/skills/` | Create | 4 个 NPC skill YAML 文件 |
| `tests/engine/test_story.py` | Modify | 覆盖新 effects 类型 |
| `tests/world/test_state.py` | Modify | 覆盖 character_stat_deltas apply/merge |

---

## 8. 不做的事情

- 不新增 GIVE / TRADE 动作类型
- 不新增 NPC（复用现有 traveler、mysterious_guest、bartender_grim）
- 不新增地图区域
- 不实现多结局（在下一个子任务中处理）
- 支线之间无硬性依赖（可独立完成）
