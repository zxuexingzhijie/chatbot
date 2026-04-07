# 存档/读档系统 — Phase 3a 设计规格

**日期**: 2026-04-08
**状态**: 已批准
**范围**: SaveManager + GameApp 集成（save/load/saves 命令 + 自动存档）

---

## 1. 概述

为酒馆 CLI 游戏添加持久化层。目前每次启动游戏所有状态（WorldState、RelationshipGraph、EventTimeline）均从零开始。Phase 3a 实现手动存档、命名存档和自动存档，使记忆系统（Phase 2c）的数据能跨会话保留。

### 设计目标

- `SaveManager`：独立模块，负责序列化/反序列化 WorldState
- 存档格式：JSON envelope（version + timestamp + slot + state）
- 自动存档：对话结束后 + 成功非对话行动后，存入 `autosave` 槽
- 手动存档：`save` / `save <name>` 命令
- 读档：`load` / `load <name>` 命令
- 存档列表：`saves` 命令
- 存档目录：可配置（`config.yaml` 中 `game.saves_dir`，默认 `saves/`）

---

## 2. 架构

### 2.1 数据流

```
Save 流程:
  new_state = memory.sync_to_state(state)     ← RelationshipGraph 写回 WorldState.relationships_snapshot
  envelope = {
    "version": 1,
    "timestamp": "2026-04-08T12:00:00",
    "slot": "autosave",
    "state": new_state.model_dump(mode='json')
  }
  写入 saves_dir / "{slot}.json"

Load 流程:
  读取 saves_dir / "{slot}.json"
  校验 envelope["version"] == 1
  loaded_state = WorldState.model_validate(envelope["state"])
  重建 StateManager(initial_state=loaded_state)
  重建 MemorySystem(state=loaded_state, skills_dir=...)
  ← RelationshipGraph 从 loaded_state.relationships_snapshot 自动恢复
```

### 2.2 模块结构

```
src/tavern/world/
└── persistence.py     # SaveInfo + SaveManager

tests/world/
└── test_persistence.py    # SaveManager 单元测试（~13 个）

tests/cli/
└── test_app_save.py       # GameApp 集成测试（~5 个）

config.yaml
└── game.saves_dir: "saves"

data/
└── saves/                 # 默认存档目录（.gitignore）
```

---

## 3. 数据模型

### 3.1 SaveInfo

```python
@dataclass(frozen=True)
class SaveInfo:
    slot: str
    timestamp: str   # ISO 8601
    path: Path
```

### 3.2 存档文件格式

```json
{
  "version": 1,
  "timestamp": "2026-04-08T12:34:56.789012",
  "slot": "autosave",
  "state": { ...WorldState.model_dump(mode='json')... }
}
```

`model_dump(mode='json')` 确保 enum 序列化为 value（而非 name），tuple 序列化为 list；Pydantic `model_validate()` 在反序列化时自动还原 enum 和 list→tuple 强转。

---

## 4. 核心组件

### 4.1 `SaveManager`（`world/persistence.py`）

```python
class SaveManager:
    def __init__(self, saves_dir: Path) -> None
    # saves_dir 不存在时不立即创建，等首次 save() 时 mkdir(parents=True, exist_ok=True)

    def save(self, state: WorldState, slot: str = "autosave") -> Path
    # 序列化为 envelope JSON，写入 saves_dir/{slot}.json，返回文件路径

    def load(self, slot: str = "autosave") -> WorldState
    # FileNotFoundError — 槽不存在
    # ValueError — JSON 损坏或 version 不匹配

    def list_saves(self) -> list[SaveInfo]
    # 扫描 saves_dir/*.json，解析 envelope header，按 timestamp 倒序返回

    def exists(self, slot: str) -> bool
    # 检查 saves_dir/{slot}.json 是否存在
```

---

## 5. 集成变更

### 5.1 `config.yaml`

```yaml
game:
  saves_dir: "saves"   # 新增，默认值
```

### 5.2 `cli/app.py`

**`__init__`** 新增：
```python
saves_dir = Path(game_config.get("saves_dir", "saves"))
self._save_manager = SaveManager(saves_dir)
```

**`SYSTEM_COMMANDS`** 新增 `"save"`, `"load"`, `"saves"`（用于 `help` 显示），但命令解析改为前缀匹配：

```python
# 在 run() 主循环中，system command 判断改为：
first_word = command.split()[0] if command.split() else ""
slot_arg = command.split()[1] if len(command.split()) > 1 else "autosave"

if first_word in {"save", "load", "saves", "look", "inventory", "status", "hint", "undo", "help", "quit"}:
    self._handle_system_command(first_word, slot_arg)
```

**`_handle_system_command`** 新增三个分支：

```python
elif command == "save":
    try:
        new_state = self._memory.sync_to_state(self.state)
        path = self._save_manager.save(new_state, slot)
        self._renderer.render_save_success(slot, path)
    except Exception as e:
        self._renderer.console.print(f"\n[red]存档失败：{e}[/]\n")

elif command == "load":
    if self._dialogue_manager.is_active:
        self._renderer.console.print("\n[red]请先结束当前对话再加载存档。[/]\n")
        return
    try:
        loaded_state = self._save_manager.load(slot)
        self._state_manager = StateManager(
            initial_state=loaded_state,
            max_history=game_config.get("undo_history_size", 50),
        )
        skills_dir = scenario_path / "skills"
        self._memory = MemorySystem(
            state=loaded_state,
            skills_dir=skills_dir if skills_dir.exists() else None,
        )
        self._dialogue_ctx = None
        self._renderer.render_load_success(slot, ...)
        self._renderer.render_status_bar(self.state)
    except (FileNotFoundError, ValueError) as e:
        self._renderer.console.print(f"\n[red]{e}[/]\n")

elif command == "saves":
    saves = self._save_manager.list_saves()
    self._renderer.render_saves_list(saves)
```

注：`_handle_system_command` 需接收 `slot` 参数，签名改为 `_handle_system_command(self, command: str, slot: str = "autosave") -> None`。`__init__` 中需将 `scenario_path` 和 `game_config` 保存为实例变量（`self._scenario_path`、`self._game_config`），供 `load` 时重建 MemorySystem 使用。

**自动存档（两处）：**

`_handle_free_input` 成功非对话行动后（`diff is not None` 且非 TALK/PERSUADE）：
```python
self._memory.apply_diff(diff, self.state)
# 自动存档
new_state = self._memory.sync_to_state(self.state)
self._save_manager.save(new_state, "autosave")
```

`_apply_dialogue_end` 事件 commit 后（最后一个 commit）：
```python
self._memory.apply_diff(event_diff, self.state)
# 自动存档
new_state = self._memory.sync_to_state(self.state)
self._save_manager.save(new_state, "autosave")
```

### 5.3 `cli/renderer.py`

新增三个方法：

```python
def render_save_success(self, slot: str, path: Path) -> None:
    self.console.print(f"\n[green]已存档：{slot}（{path}）[/]\n")

def render_load_success(self, slot: str, timestamp: str) -> None:
    self.console.print(f"\n[green]已读取存档：{slot}（{timestamp}）[/]\n")

def render_saves_list(self, saves: list[SaveInfo]) -> None:
    # 若无存档：[dim]暂无存档。[/]
    # 否则：Rich Table，列：槽名 | 时间戳 | 文件路径
```

`render_help()` 新增三条命令说明：`save [名称]`、`load [名称]`、`saves`。

---

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| `saves_dir` 不存在 | 首次 `save()` 时 `mkdir(parents=True, exist_ok=True)` |
| `load` 槽文件不存在 | `FileNotFoundError("存档不存在：{slot}")` |
| JSON 损坏 | `ValueError("存档文件损坏：{slot}")` |
| version 不匹配 | `ValueError("存档版本不兼容，请重新开始游戏")` |
| 对话中执行 `load` | 提示"请先结束当前对话再加载存档"，不加载 |
| `save` 写盘失败 | 捕获 `OSError`，渲染错误信息，不崩溃 |

---

## 7. 测试计划

### `tests/world/test_persistence.py`（~13 个）

| 测试 | 内容 |
|------|------|
| `test_save_creates_file` | `save()` 后文件存在 |
| `test_save_envelope_format` | envelope 含 version/timestamp/slot/state |
| `test_save_load_roundtrip` | `loaded_state == original_state`（显式断言，验证 enum/tuple 还原） |
| `test_load_nonexistent_slot` | `FileNotFoundError` |
| `test_load_corrupt_json` | `ValueError` |
| `test_load_wrong_version` | `ValueError` |
| `test_saves_dir_created_on_first_save` | 目录不存在时自动创建 |
| `test_list_saves_empty` | 返回空列表 |
| `test_list_saves_sorted_by_timestamp_desc` | 多个存档按时间戳倒序 |
| `test_list_saves_returns_saveinfo` | 返回正确 slot/timestamp/path |
| `test_exists_true` | 存档存在时返回 True |
| `test_exists_false` | 存档不存在时返回 False |
| `test_save_named_slot` | 命名槽文件名正确（`mygame.json`） |

### `tests/cli/test_app_save.py`（~5 个）

| 测试 | 内容 |
|------|------|
| `test_save_command_calls_save_manager` | `save` 命令调用 `save_manager.save` |
| `test_load_command_rebuilds_state_manager_and_memory` | `load` 后 state/memory 重建 |
| `test_load_during_dialogue_rejected` | 对话中 `load` 不执行加载 |
| `test_autosave_after_successful_action` | `_handle_free_input` 成功后 `save_manager.save` 被调用 |
| `test_autosave_after_dialogue_end` | `_apply_dialogue_end` 后 `save_manager.save` 被调用 |

---

## 8. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/world/persistence.py` | ~80 |
| 修改 | `src/tavern/cli/app.py` | +~40 |
| 修改 | `src/tavern/cli/renderer.py` | +~20 |
| 修改 | `config.yaml` | +1 |
| 新建 | `tests/world/test_persistence.py` | ~160 |
| 新建 | `tests/cli/test_app_save.py` | ~80 |

**新增代码约 ~100 行，测试约 ~240 行**

---

## 9. 不在范围内

- 存档加密 / 压缩
- 云端同步
- 存档槽数量限制
- 存档缩略图 / 预览文本
- 存档版本迁移脚本（version > 1 时）
