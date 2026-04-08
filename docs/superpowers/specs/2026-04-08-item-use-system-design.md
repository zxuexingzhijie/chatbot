# 物品使用系统（Item Use System）— 设计规格

**日期**: 2026-04-08
**状态**: 已批准
**范围**: USE 动作实现 + 效果注册制 + world.yaml 扩展 + 解析器 prompt 补充

---

## 1. 概述

为酒馆 CLI 游戏实现 `USE` 动作的完整处理链：玩家输入 → `IntentParser` → `RulesEngine._handle_use` → 效果注册制依次执行 → `StateDiff` 提交。效果类型通过 `USE_EFFECT_REGISTRY` 注册，与 `CONDITION_REGISTRY` 模式完全一致。

### 设计目标

- 支持四种效果类型：`unlock`、`consume`、`spawn_item`、`story_event`
- 效果组合：一个物品可有多条 `use_effects`，依次全部执行
- 目标校验：`usable_with` 非空时作为目标守卫，匹配 `request.detail`
- 无新抽象层：`USE` 走与 `MOVE`/`TAKE` 相同的 `rules.validate()` 路径

---

## 2. 数据模型

### 2.1 新增：`EventSpec` 与 `UseEffect`（`world/models.py`）

```python
class EventSpec(BaseModel):
    """物品使用时产生的事件规格（与 story.py 的 NewEventSpec 结构相同，独立 BaseModel）。"""
    model_config = ConfigDict(frozen=True)
    id: str
    type: str
    description: str
    actor: str | None = None   # None → 默认 player_id

class UseEffect(BaseModel):
    """单条物品使用效果。"""
    model_config = ConfigDict(frozen=True)
    type: str                          # unlock | consume | spawn_item | story_event
    location: str | None = None        # unlock: 出口所在地点ID；spawn_item(spawn_to_inventory=False): 物品放置地点ID
    exit_direction: str | None = None  # unlock 专用：哪个方向的出口
    item_id: str | None = None         # spawn_item 专用：生成哪个物品
    spawn_to_inventory: bool = True    # spawn_item: True→进背包，False→放到 location 指定地点
    event: EventSpec | None = None     # story_event 专用
```

### 2.2 修改：`Item`（`world/models.py`）

```python
class Item(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    description: str
    portable: bool = True
    usable_with: tuple[str, ...] = ()      # 目标守卫：非空时 detail 必须匹配其中一个
    use_effects: tuple[UseEffect, ...] = ()
```

### 2.3 `world.yaml` 扩展示例

```yaml
cellar_key:
  name: 地下室钥匙
  description: 一把生锈的铁钥匙，上面刻着一个小小的龙形标记
  portable: true
  usable_with:
    - cellar_door
  use_effects:
    - type: unlock
      location: bar_area
      exit_direction: down
    - type: consume

rusty_box:
  name: 生锈铁盒
  description: 从马车下找到的铁盒，里面有一把备用钥匙
  portable: false
  use_effects:
    - type: spawn_item
      item_id: spare_key
      spawn_to_inventory: true
    - type: story_event
      event:
        id: box_opened
        type: story
        description: "玩家打开了铁盒，找到了备用钥匙"
```

---

## 3. 效果注册制（`engine/use_effects.py`）

```python
from typing import Callable
from tavern.world.models import UseEffect
from tavern.world.state import WorldState, StateDiff

UseEffectFn = Callable[[UseEffect, str, WorldState], tuple[StateDiff, str | None]]
# 参数: (effect, item_id, state)
# 返回: (diff, 反馈消息 | None)

USE_EFFECT_REGISTRY: dict[str, UseEffectFn] = {}

def register_effect(type_name: str):
    def decorator(fn: UseEffectFn) -> UseEffectFn:
        USE_EFFECT_REGISTRY[type_name] = fn
        return fn
    return decorator
```

### 3.1 内置效果实现

**`unlock`**
- 找到 `state.locations[eff.location].exits[eff.exit_direction]`
- 生成新 `Exit(locked=False)`，写入 `StateDiff(updated_locations=...)`
- 消息：`f"门被打开了。"`

**`consume`**
- 从玩家背包移除 `item_id`
- 写入 `StateDiff(updated_characters={player_id: {"inventory": new_inventory}})`
- 消息：`None`（不额外提示）

**`spawn_item`**
- `spawn_to_inventory=True`：把 `eff.item_id` 加入玩家背包
- `spawn_to_inventory=False`：把 `eff.item_id` 加入 `state.locations[eff.location].items`
- 消息：`f"你获得了{item.name}。"`

**`story_event`**
- 用 `eff.event` 生成 `Event`（`actor` 默认 `state.player_id`）
- 写入 `StateDiff(new_events=(event,))`
- 消息：`None`

---

## 4. RulesEngine 扩展（`engine/rules.py`）

```python
def _handle_use(request: ActionRequest, state: WorldState):
    item_id = request.target

    # 1. 验证物品存在
    player = _get_player(state)
    location = _get_player_location(state)
    if item_id not in player.inventory and item_id not in location.items:
        return ActionResult(success=False, action=ActionType.USE,
                            message="你没有那个物品。", target=item_id), None

    if item_id not in state.items:
        return ActionResult(success=False, action=ActionType.USE,
                            message=f"未知物品: {item_id}", target=item_id), None

    item = state.items[item_id]

    # 2. 目标守卫
    if item.usable_with:
        if request.detail is None:
            return ActionResult(success=False, action=ActionType.USE,
                                message="你想把它用在什么上？", target=item_id), None
        if request.detail not in item.usable_with:
            return ActionResult(success=False, action=ActionType.USE,
                                message="该物品不能用在这里。", target=item_id), None

    # 3. 无效果
    if not item.use_effects:
        return ActionResult(success=False, action=ActionType.USE,
                            message=f"「{item.name}」无法使用。", target=item_id), None

    # 4. 依次执行效果，合并 diff
    combined_diff = StateDiff(turn_increment=0)
    messages = []
    current_state = state
    for eff in item.use_effects:
        fn = USE_EFFECT_REGISTRY.get(eff.type)
        if fn is None:
            logger.warning("未知 use_effect 类型: %s（物品: %s）", eff.type, item_id)
            continue
        diff, msg = fn(eff, item_id, current_state)
        combined_diff = _merge_diffs(combined_diff, diff)
        current_state = current_state.apply(diff)   # 让后续效果看到更新后的状态
        if msg:
            messages.append(msg)

    final_message = "\n".join(messages) if messages else f"你使用了「{item.name}」。"
    return ActionResult(success=True, action=ActionType.USE,
                        message=final_message, target=item_id), combined_diff
```

> `_merge_diffs` 为新增私有辅助函数，将两个 `StateDiff` 字段逐一合并（dict 合并、tuple 拼接、turn_increment 相加）。

---

## 5. IntentParser prompt 补充（`llm/service.py`）

在 `INTENT_SYSTEM_PROMPT` 的示例列表中添加 USE 条目：

```
- 输入: "用钥匙开地下室的门" -> {"action": "use", "target": "cellar_key", "detail": "cellar_door", "confidence": 0.95}
- 输入: "使用铁盒" -> {"action": "use", "target": "rusty_box", "detail": null, "confidence": 0.9}
```

明确语义：`target` = 使用的物品 ID，`detail` = 使用对象 ID（无目标时为 null）。

---

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| 物品不在背包也不在当前地点 | 失败：「你没有那个物品」 |
| `use_effects` 为空 | 失败：「该物品无法使用」 |
| `usable_with` 非空但 `detail` 为 None | 失败：「你想把它用在什么上？」 |
| `usable_with` 非空但 `detail` 不匹配 | 失败：「该物品不能用在这里」 |
| 未知 effect type | `logger.warning`，跳过该条效果，继续执行其余效果 |
| `unlock` 目标 exit 不存在 | `logger.warning`，跳过 |
| `spawn_item` 的 `item_id` 不在 `state.items` | `logger.warning`，跳过 |
| `spawn_item(spawn_to_inventory=False)` 的 `location` 为 None | `logger.warning`，跳过 |

---

## 7. 测试计划

### `tests/engine/test_use_effects.py`（~10 个）

| 测试 | 内容 |
|------|------|
| `test_unlock_effect` | `effect_unlock` 正确修改 exit.locked |
| `test_consume_effect` | `effect_consume` 从背包移除物品 |
| `test_spawn_item_to_inventory` | `effect_spawn_item` 进背包 |
| `test_spawn_item_to_location` | `effect_spawn_item` 放到地点 |
| `test_story_event_effect` | `effect_story_event` 写入 new_events |
| `test_unknown_effect_type_skipped` | 未知 type 跳过，不报错 |
| `test_multiple_effects_merged` | unlock + consume 组合，diff 正确合并 |
| `test_consume_updates_state_for_next_effect` | 后续效果能看到 consume 后的状态 |

### `tests/engine/test_rules_use.py`（~7 个）

| 测试 | 内容 |
|------|------|
| `test_use_item_not_in_inventory_or_location` | 物品不存在 → 失败 |
| `test_use_item_no_effects` | 无 use_effects → 失败 |
| `test_use_item_usable_with_no_detail` | usable_with 非空但无 detail → 失败 |
| `test_use_item_usable_with_wrong_target` | detail 不匹配 → 失败 |
| `test_use_item_usable_with_correct_target` | detail 匹配 → 成功 |
| `test_use_item_no_usable_with_succeeds` | usable_with 空 → 直接执行 |
| `test_use_item_combine_message` | 多条效果消息正确拼接 |

### `tests/world/test_models_use_effect.py`（~3 个）

| 测试 | 内容 |
|------|------|
| `test_use_effect_serialization` | `UseEffect` Pydantic roundtrip |
| `test_event_spec_serialization` | `EventSpec` Pydantic roundtrip |
| `test_item_with_use_effects_serialization` | `Item` 含嵌套 `UseEffect` roundtrip |

---

## 8. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 修改 | `src/tavern/world/models.py` | +~30（EventSpec, UseEffect, Item.use_effects） |
| 新建 | `src/tavern/engine/use_effects.py` | ~100 |
| 修改 | `src/tavern/engine/rules.py` | +~50（_handle_use, _merge_diffs） |
| 修改 | `src/tavern/llm/service.py` | +2（USE prompt 示例） |
| 修改 | `src/tavern/world/loader.py` | +~10（解析 use_effects） |
| 修改 | `data/scenarios/tavern/world.yaml` | +~20（cellar_key, rusty_box 补充效果） |
| 新建 | `tests/engine/test_use_effects.py` | ~150 |
| 新建 | `tests/engine/test_rules_use.py` | ~120 |
| 新建 | `tests/world/test_models_use_effect.py` | ~50 |

---

## 9. 不在范围内

- `GIVE` / `TRADE` 动作（独立阶段）
- USE 动作触发对话（由 StoryEngine 的 `story_event` 节点负责）
- 物品耐久度 / 使用次数限制
- 条件性效果（"如果 trust >= 30 才能解锁"）
