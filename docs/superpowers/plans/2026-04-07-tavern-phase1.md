# Tavern Phase 1 — Core Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core game skeleton — player can move between tavern locations, observe surroundings, and pick up items via natural language input classified by LLM.

**Architecture:** Three-layer pipeline (LLM Intent Parser → Rules Engine → Rich CLI Renderer) with immutable WorldState managed by StateManager. Phase 1 skips the full LLM narrative layer — rules engine produces descriptive ActionResult messages directly. LLM is used only for intent classification.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), Rich (CLI), OpenAI async SDK (intent parsing), PyYAML (scenario data), pytest + pytest-asyncio (testing)

**Spec:** `docs/superpowers/specs/2026-04-07-cli-interactive-novel-design.md`

---

## File Map

### New Files (Phase 1)

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package metadata, dependencies |
| `config.yaml` | LLM + game configuration |
| `src/tavern/__init__.py` | Package root |
| `src/tavern/__main__.py` | Entry point (`python -m tavern`) |
| `src/tavern/world/models.py` | Character, Location, Item, Event, Exit, enums, ActionRequest, ActionResult |
| `src/tavern/world/state.py` | WorldState (frozen), StateDiff, StateManager |
| `src/tavern/world/loader.py` | YAML scenario loader → initial WorldState |
| `src/tavern/llm/adapter.py` | LLMAdapter Protocol, LLMConfig, LLMRegistry |
| `src/tavern/llm/openai_llm.py` | OpenAIAdapter implementation |
| `src/tavern/llm/service.py` | LLMService (intent classification only in P1) |
| `src/tavern/parser/intent.py` | IntentParser — prompt template + LLM classification |
| `src/tavern/engine/actions.py` | ActionType enum (shared between parser & engine) |
| `src/tavern/engine/rules.py` | RulesEngine — validate actions, produce StateDiff |
| `src/tavern/cli/renderer.py` | Rich panels, status bar, narrative output |
| `src/tavern/cli/app.py` | GameApp — main loop, system command routing |
| `data/scenarios/tavern/world.yaml` | 5 locations + items |
| `data/scenarios/tavern/characters.yaml` | 3 NPCs + player template |
| `tests/conftest.py` | Shared fixtures |
| `tests/world/test_models.py` | Model creation, validation, immutability |
| `tests/world/test_state.py` | WorldState.apply(), StateManager commit/undo/redo |
| `tests/world/test_loader.py` | YAML loading, WorldState construction |
| `tests/llm/test_adapter.py` | LLM adapter with mock |
| `tests/parser/test_intent.py` | Intent classification with mock LLM |
| `tests/engine/test_rules.py` | MOVE, LOOK, TAKE validation |
| `tests/cli/test_renderer.py` | Renderer output verification |
| `tests/test_integration.py` | End-to-end pipeline smoke test |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `config.yaml`
- Create: `src/tavern/__init__.py`
- Create: `src/tavern/world/__init__.py`
- Create: `src/tavern/llm/__init__.py`
- Create: `src/tavern/parser/__init__.py`
- Create: `src/tavern/engine/__init__.py`
- Create: `src/tavern/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/world/__init__.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/parser/__init__.py`
- Create: `tests/engine/__init__.py`
- Create: `tests/cli/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "tavern"
version = "0.1.0"
description = "CLI interactive novel game — fantasy tavern exploration"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0,<3.0",
    "rich>=13.0",
    "networkx>=3.0",
    "openai>=1.0",
    "pyyaml>=6.0",
    "tenacity>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
]

[project.scripts]
tavern = "tavern.__main__:main"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create config.yaml**

```yaml
llm:
  intent:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1
    max_tokens: 200
    max_retries: 3
    timeout: 10.0
  narrative:
    provider: openai
    model: gpt-4o
    temperature: 0.8
    max_tokens: 500
    max_retries: 2
    timeout: 30.0
    stream: true

game:
  auto_save_interval: 5
  undo_history_size: 50
  save_dir: ./saves
  scenario: data/scenarios/tavern

debug:
  show_intent_json: false
  show_prompt: false
  log_level: INFO
```

- [ ] **Step 3: Create package directories with __init__.py**

Create all `__init__.py` files (empty) for packages:
- `src/tavern/__init__.py`
- `src/tavern/world/__init__.py`
- `src/tavern/llm/__init__.py`
- `src/tavern/parser/__init__.py`
- `src/tavern/engine/__init__.py`
- `src/tavern/cli/__init__.py`
- `tests/__init__.py`
- `tests/world/__init__.py`
- `tests/llm/__init__.py`
- `tests/parser/__init__.py`
- `tests/engine/__init__.py`
- `tests/cli/__init__.py`

- [ ] **Step 4: Install in dev mode and verify**

Run: `cd /Users/makoto/Downloads/work/chatbot && pip install -e ".[dev]"`
Expected: Successfully installed tavern + all dependencies

- [ ] **Step 5: Verify pytest discovers test directories**

Run: `pytest --collect-only`
Expected: "no tests ran" (no test files yet), no import errors

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml config.yaml src/ tests/
git commit -m "feat: scaffold project structure with dependencies"
```

---

## Task 2: Core Data Models

**Files:**
- Create: `src/tavern/engine/actions.py`
- Create: `src/tavern/world/models.py`
- Test: `tests/world/test_models.py`

- [ ] **Step 1: Write failing tests for action enums and models**

```python
# tests/world/test_models.py
import pytest
from tavern.engine.actions import ActionType
from tavern.world.models import (
    Character,
    CharacterRole,
    Exit,
    Item,
    Location,
    Event,
    ActionRequest,
    ActionResult,
)


class TestActionType:
    def test_move_action_exists(self):
        assert ActionType.MOVE == "move"

    def test_all_phase1_actions(self):
        expected = {"move", "look", "search", "talk", "persuade", "trade",
                    "take", "use", "give", "stealth", "combat", "custom"}
        actual = {a.value for a in ActionType}
        assert actual == expected


class TestCharacter:
    def test_create_player(self):
        player = Character(
            id="player",
            name="冒险者",
            role=CharacterRole.PLAYER,
            traits=("勇敢", "好奇"),
            stats={"hp": 100, "gold": 10},
            inventory=(),
            location_id="tavern_hall",
        )
        assert player.id == "player"
        assert player.role == CharacterRole.PLAYER
        assert player.stats["hp"] == 100

    def test_create_npc(self):
        npc = Character(
            id="bartender_grim",
            name="格里姆",
            role=CharacterRole.NPC,
            traits=("沉默寡言", "警觉"),
            stats={"trust": 0},
            inventory=("cellar_key",),
            location_id="bar_area",
        )
        assert npc.role == CharacterRole.NPC
        assert "cellar_key" in npc.inventory

    def test_character_is_frozen(self):
        player = Character(
            id="player", name="冒险者", role=CharacterRole.PLAYER,
            traits=(), stats={}, inventory=(), location_id="tavern_hall",
        )
        with pytest.raises(Exception):
            player.name = "新名字"


class TestLocation:
    def test_create_location_with_exits(self):
        loc = Location(
            id="tavern_hall",
            name="酒馆大厅",
            description="一间温暖的酒馆大厅，壁炉中火焰跳动。",
            exits={
                "north": Exit(target="bar_area", description="通往吧台区"),
                "east": Exit(target="corridor", description="通往客房走廊"),
            },
            items=("old_notice",),
            npcs=("traveler",),
        )
        assert loc.exits["north"].target == "bar_area"
        assert not loc.exits["north"].locked

    def test_locked_exit(self):
        exit_ = Exit(target="cellar", locked=True, key_item="cellar_key")
        assert exit_.locked
        assert exit_.key_item == "cellar_key"


class TestItem:
    def test_portable_item(self):
        item = Item(id="cellar_key", name="地下室钥匙",
                    description="一把生锈的铁钥匙", portable=True)
        assert item.portable

    def test_non_portable_item(self):
        item = Item(id="fireplace", name="壁炉",
                    description="熊熊燃烧的壁炉", portable=False)
        assert not item.portable

    def test_usable_with(self):
        item = Item(id="cellar_key", name="地下室钥匙",
                    description="钥匙", portable=True,
                    usable_with=("cellar_door",))
        assert "cellar_door" in item.usable_with


class TestEvent:
    def test_create_event(self):
        event = Event(
            id="evt_001", turn=1, type="action",
            actor="player", description="玩家进入酒馆",
            consequences=("npc_notice_player",),
        )
        assert event.turn == 1
        assert event.actor == "player"


class TestActionRequest:
    def test_create_request(self):
        req = ActionRequest(
            action=ActionType.MOVE, target="bar_area",
            detail="走向吧台", confidence=0.95,
        )
        assert req.action == ActionType.MOVE
        assert req.confidence == 0.95

    def test_default_confidence(self):
        req = ActionRequest(action=ActionType.LOOK)
        assert req.confidence == 1.0


class TestActionResult:
    def test_success_result(self):
        result = ActionResult(
            success=True, action=ActionType.MOVE,
            message="你走向吧台区。", target="bar_area",
        )
        assert result.success
        assert result.action == ActionType.MOVE

    def test_failure_result(self):
        result = ActionResult(
            success=False, action=ActionType.MOVE,
            message="门被锁住了。", target="cellar",
        )
        assert not result.success
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/world/test_models.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement ActionType enum**

```python
# src/tavern/engine/actions.py
from enum import Enum


class ActionType(str, Enum):
    MOVE = "move"
    LOOK = "look"
    SEARCH = "search"
    TALK = "talk"
    PERSUADE = "persuade"
    TRADE = "trade"
    TAKE = "take"
    USE = "use"
    GIVE = "give"
    STEALTH = "stealth"
    COMBAT = "combat"
    CUSTOM = "custom"
```

- [ ] **Step 4: Implement world models**

```python
# src/tavern/world/models.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from tavern.engine.actions import ActionType


class CharacterRole(str, Enum):
    NPC = "npc"
    PLAYER = "player"


class Character(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    role: CharacterRole
    traits: tuple[str, ...] = ()
    stats: dict[str, int] = {}
    inventory: tuple[str, ...] = ()
    location_id: str


class Exit(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    locked: bool = False
    key_item: str | None = None
    description: str = ""


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    exits: dict[str, Exit] = {}
    items: tuple[str, ...] = ()
    npcs: tuple[str, ...] = ()


class Item(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    portable: bool = True
    usable_with: tuple[str, ...] = ()


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    turn: int
    type: str
    actor: str
    description: str
    consequences: tuple[str, ...] = ()


class ActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: ActionType
    target: str | None = None
    detail: str | None = None
    confidence: float = 1.0


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    action: ActionType
    message: str
    target: str | None = None
    detail: str | None = None
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `pytest tests/world/test_models.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/actions.py src/tavern/world/models.py tests/world/test_models.py
git commit -m "feat: add core data models — Character, Location, Item, Event, ActionRequest, ActionResult"
```

---

## Task 3: WorldState, StateDiff & StateManager

**Files:**
- Create: `src/tavern/world/state.py`
- Test: `tests/world/test_state.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/conftest.py
import pytest
from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionResult,
    Character,
    CharacterRole,
    Event,
    Exit,
    Item,
    Location,
)
from tavern.world.state import StateManager, WorldState


@pytest.fixture
def sample_locations() -> dict[str, Location]:
    return {
        "tavern_hall": Location(
            id="tavern_hall",
            name="酒馆大厅",
            description="温暖的酒馆大厅。",
            exits={"north": Exit(target="bar_area", description="通往吧台")},
            items=("old_notice",),
            npcs=("traveler",),
        ),
        "bar_area": Location(
            id="bar_area",
            name="吧台区",
            description="木质吧台前摆着几张高脚凳。",
            exits={
                "south": Exit(target="tavern_hall", description="回到大厅"),
                "down": Exit(target="cellar", locked=True, key_item="cellar_key",
                             description="通往地下室（已锁）"),
            },
            items=(),
            npcs=("bartender_grim",),
        ),
    }


@pytest.fixture
def sample_items() -> dict[str, Item]:
    return {
        "old_notice": Item(id="old_notice", name="旧告示",
                           description="一张泛黄的告示", portable=True),
        "cellar_key": Item(id="cellar_key", name="地下室钥匙",
                           description="一把生锈的铁钥匙", portable=True),
    }


@pytest.fixture
def sample_characters() -> dict[str, Character]:
    return {
        "player": Character(
            id="player", name="冒险者", role=CharacterRole.PLAYER,
            traits=("勇敢",), stats={"hp": 100, "gold": 10},
            inventory=(), location_id="tavern_hall",
        ),
        "traveler": Character(
            id="traveler", name="旅行者", role=CharacterRole.NPC,
            traits=("友善", "健谈"), stats={"trust": 10},
            inventory=(), location_id="tavern_hall",
        ),
        "bartender_grim": Character(
            id="bartender_grim", name="格里姆", role=CharacterRole.NPC,
            traits=("沉默寡言", "警觉"), stats={"trust": 0},
            inventory=("cellar_key",), location_id="bar_area",
        ),
    }


@pytest.fixture
def sample_world_state(sample_locations, sample_items, sample_characters):
    return WorldState(
        turn=0,
        player_id="player",
        locations=sample_locations,
        characters=sample_characters,
        items=sample_items,
    )


@pytest.fixture
def sample_state_manager(sample_world_state):
    return StateManager(initial_state=sample_world_state)
```

```python
# tests/world/test_state.py
import pytest
from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult, Event
from tavern.world.state import StateDiff, StateManager, WorldState


class TestWorldState:
    def test_is_frozen(self, sample_world_state):
        with pytest.raises(Exception):
            sample_world_state.turn = 99

    def test_apply_diff_increments_turn(self, sample_world_state):
        diff = StateDiff(turn_increment=1)
        new_state = sample_world_state.apply(diff)
        assert new_state.turn == 1
        assert sample_world_state.turn == 0  # original unchanged

    def test_apply_diff_updates_character(self, sample_world_state):
        diff = StateDiff(
            updated_characters={
                "player": {"location_id": "bar_area"},
            },
        )
        new_state = sample_world_state.apply(diff)
        assert new_state.characters["player"].location_id == "bar_area"
        assert sample_world_state.characters["player"].location_id == "tavern_hall"

    def test_apply_diff_removes_item_from_location(self, sample_world_state):
        diff = StateDiff(
            updated_locations={
                "tavern_hall": {
                    "items": (),  # removed old_notice
                },
            },
        )
        new_state = sample_world_state.apply(diff)
        assert "old_notice" not in new_state.locations["tavern_hall"].items

    def test_apply_diff_adds_item_to_inventory(self, sample_world_state):
        diff = StateDiff(
            updated_characters={
                "player": {"inventory": ("old_notice",)},
            },
        )
        new_state = sample_world_state.apply(diff)
        assert "old_notice" in new_state.characters["player"].inventory

    def test_apply_diff_adds_event(self, sample_world_state):
        event = Event(id="evt_1", turn=1, type="move", actor="player",
                      description="玩家移动到吧台区")
        diff = StateDiff(new_events=(event,))
        new_state = sample_world_state.apply(diff)
        assert len(new_state.timeline) == 1
        assert new_state.timeline[0].id == "evt_1"


class TestStateManager:
    def test_current_returns_initial(self, sample_state_manager, sample_world_state):
        assert sample_state_manager.current.turn == sample_world_state.turn

    def test_commit_advances_state(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(success=True, action=ActionType.LOOK, message="你环顾四周。")
        new_state = sample_state_manager.commit(diff, action)
        assert new_state.turn == 1
        assert sample_state_manager.current.turn == 1

    def test_commit_stores_last_action(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(success=True, action=ActionType.LOOK, message="你环顾四周。")
        sample_state_manager.commit(diff, action)
        assert sample_state_manager.current.last_action == action

    def test_undo_restores_previous(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(success=True, action=ActionType.LOOK, message="看")
        sample_state_manager.commit(diff, action)
        assert sample_state_manager.current.turn == 1
        restored = sample_state_manager.undo()
        assert restored.turn == 0

    def test_undo_on_empty_history_raises(self, sample_state_manager):
        with pytest.raises(IndexError):
            sample_state_manager.undo()

    def test_redo_after_undo(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(success=True, action=ActionType.LOOK, message="看")
        sample_state_manager.commit(diff, action)
        sample_state_manager.undo()
        redone = sample_state_manager.redo()
        assert redone.turn == 1

    def test_redo_on_empty_raises(self, sample_state_manager):
        with pytest.raises(IndexError):
            sample_state_manager.redo()

    def test_commit_clears_redo_stack(self, sample_state_manager):
        diff1 = StateDiff(turn_increment=1)
        action1 = ActionResult(success=True, action=ActionType.LOOK, message="看")
        sample_state_manager.commit(diff1, action1)
        sample_state_manager.undo()

        diff2 = StateDiff(turn_increment=1)
        action2 = ActionResult(success=True, action=ActionType.MOVE, message="走")
        sample_state_manager.commit(diff2, action2)

        with pytest.raises(IndexError):
            sample_state_manager.redo()
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/world/test_state.py -v`
Expected: FAIL — cannot import WorldState, StateDiff, StateManager

- [ ] **Step 3: Implement WorldState, StateDiff, StateManager**

```python
# src/tavern/world/state.py
from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict

from tavern.world.models import (
    ActionResult,
    Character,
    Event,
    Item,
    Location,
)


class StateDiff(BaseModel):
    updated_characters: dict[str, dict] = {}
    updated_locations: dict[str, dict] = {}
    added_items: dict[str, Item] = {}
    removed_items: tuple[str, ...] = ()
    relationship_changes: tuple[dict, ...] = ()
    quest_updates: dict[str, dict] = {}
    new_events: tuple[Event, ...] = ()
    turn_increment: int = 1


class WorldState(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn: int = 0
    player_id: str = "player"
    locations: dict[str, Location] = {}
    characters: dict[str, Character] = {}
    items: dict[str, Item] = {}
    relationships_snapshot: dict = {}
    quests: dict[str, dict] = {}
    timeline: tuple[Event, ...] = ()
    last_action: ActionResult | None = None

    def apply(self, diff: StateDiff, action: ActionResult | None = None) -> WorldState:
        new_characters = dict(self.characters)
        for char_id, updates in diff.updated_characters.items():
            if char_id in new_characters:
                new_characters[char_id] = new_characters[char_id].model_copy(
                    update=updates
                )

        new_locations = dict(self.locations)
        for loc_id, updates in diff.updated_locations.items():
            if loc_id in new_locations:
                new_locations[loc_id] = new_locations[loc_id].model_copy(
                    update=updates
                )

        new_items = dict(self.items)
        new_items.update(diff.added_items)
        for item_id in diff.removed_items:
            new_items.pop(item_id, None)

        new_timeline = self.timeline + diff.new_events

        new_quests = dict(self.quests)
        for quest_id, updates in diff.quest_updates.items():
            existing = new_quests.get(quest_id, {})
            new_quests[quest_id] = {**existing, **updates}

        return WorldState(
            turn=self.turn + diff.turn_increment,
            player_id=self.player_id,
            locations=new_locations,
            characters=new_characters,
            items=new_items,
            relationships_snapshot=self.relationships_snapshot,
            quests=new_quests,
            timeline=new_timeline,
            last_action=action,
        )


class StateManager:
    def __init__(
        self,
        initial_state: WorldState,
        max_history: int = 50,
    ):
        self._current = initial_state
        self._history: deque[WorldState] = deque(maxlen=max_history)
        self._redo: deque[WorldState] = deque(maxlen=max_history)

    @property
    def current(self) -> WorldState:
        return self._current

    def commit(self, diff: StateDiff, action: ActionResult) -> WorldState:
        self._history.append(self._current)
        self._current = self._current.apply(diff, action=action)
        self._redo.clear()
        return self._current

    def undo(self) -> WorldState:
        previous = self._history.pop()  # raises IndexError if empty
        self._redo.append(self._current)
        self._current = previous
        return self._current

    def redo(self) -> WorldState:
        next_state = self._redo.pop()  # raises IndexError if empty
        self._history.append(self._current)
        self._current = next_state
        return self._current
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/world/test_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/state.py tests/conftest.py tests/world/test_state.py
git commit -m "feat: add WorldState, StateDiff, StateManager with undo/redo"
```

---

## Task 4: Scenario YAML Data & Loader

**Files:**
- Create: `data/scenarios/tavern/world.yaml`
- Create: `data/scenarios/tavern/characters.yaml`
- Create: `src/tavern/world/loader.py`
- Test: `tests/world/test_loader.py`

- [ ] **Step 1: Create world.yaml**

```yaml
# data/scenarios/tavern/world.yaml
locations:
  tavern_hall:
    name: 酒馆大厅
    description: >-
      推开沉重的橡木门，你走进了「醉龙酒馆」。大厅里弥漫着麦酒和烤肉的香气，
      壁炉中的火焰投射出温暖的光芒。几张粗糙的木桌散落各处，角落里坐着一位
      风尘仆仆的旅行者。墙上挂着一张泛黄的告示。
    exits:
      north:
        target: bar_area
        description: 通往吧台区的木质拱门
      east:
        target: corridor
        description: 通往客房走廊的昏暗过道
      west:
        target: backyard
        description: 通往后院的侧门
    items:
      - old_notice
    npcs:
      - traveler

  bar_area:
    name: 吧台区
    description: >-
      长长的橡木吧台后面，酒保格里姆正在擦拭杯子。吧台上摆着各式酒瓶，
      墙上挂着一面铜质奖牌和一幅褪色的城镇地图。吧台尽头有一扇沉重的
      铁门，上面挂着一把锁。
    exits:
      south:
        target: tavern_hall
        description: 回到大厅
      down:
        target: cellar
        locked: true
        key_item: cellar_key
        description: 通往地下室的铁门（已锁）
    items: []
    npcs:
      - bartender_grim

  cellar:
    name: 地下室
    description: >-
      阴暗潮湿的地下室，空气中弥漫着霉味。几个破旧的木桶堆在角落，
      蜘蛛网挂满了石质墙壁。地面上有一些奇怪的划痕，似乎有什么沉重的
      东西被拖过。
    exits:
      up:
        target: bar_area
        description: 返回吧台区的石阶
    items:
      - old_barrel
    npcs: []

  corridor:
    name: 客房走廊
    description: >-
      狭窄的走廊两侧排列着几扇紧闭的房门。走廊尽头的房间门半掩着，
      透出昏暗的烛光。一位戴着兜帽的神秘旅客靠在墙边，似乎在等待什么。
    exits:
      west:
        target: tavern_hall
        description: 回到大厅
    items: []
    npcs:
      - mysterious_guest

  backyard:
    name: 后院
    description: >-
      杂草丛生的后院，月光洒在一辆废弃的马车上。马车的篷布已经破烂不堪，
      但车厢下似乎藏着什么东西。院子角落有一口枯井，井沿上长满了青苔。
    exits:
      east:
        target: tavern_hall
        description: 回到酒馆大厅
    items:
      - abandoned_cart
      - dry_well
    npcs: []

items:
  old_notice:
    name: 旧告示
    description: >-
      一张泛黄的告示，上面写着：「警告：近日地下室频繁传出异响，
      闲人勿入。——酒馆老板 格里姆」
    portable: true

  cellar_key:
    name: 地下室钥匙
    description: 一把生锈的铁钥匙，上面刻着一个小小的龙形标记
    portable: true
    usable_with:
      - cellar_door

  old_barrel:
    name: 旧木桶
    description: 几个破旧的木桶，其中一个底部有奇怪的刮痕
    portable: false

  abandoned_cart:
    name: 废弃马车
    description: 一辆破旧的马车，篷布下隐约能看到一个小铁盒
    portable: false

  dry_well:
    name: 枯井
    description: 一口枯井，井沿长满青苔，井底黑漆漆的看不到尽头
    portable: false

  rusty_box:
    name: 生锈铁盒
    description: 从马车下找到的铁盒，里面有一把备用钥匙
    portable: true

  spare_key:
    name: 备用钥匙
    description: 一把形状和地下室钥匙相似的备用钥匙
    portable: true
    usable_with:
      - cellar_door
```

- [ ] **Step 2: Create characters.yaml**

```yaml
# data/scenarios/tavern/characters.yaml
player:
  id: player
  name: 冒险者
  role: player
  traits:
    - 勇敢
    - 好奇
  stats:
    hp: 100
    gold: 10
  inventory: []
  location_id: tavern_hall

npcs:
  traveler:
    name: 旅行者艾琳
    traits:
      - 友善
      - 健谈
      - 风尘仆仆
    stats:
      trust: 10
    inventory: []
    location_id: tavern_hall

  bartender_grim:
    name: 酒保格里姆
    traits:
      - 沉默寡言
      - 警觉
      - 粗犷
    stats:
      trust: 0
    inventory:
      - cellar_key
    location_id: bar_area

  mysterious_guest:
    name: 神秘旅客
    traits:
      - 神秘
      - 冷淡
      - 戴兜帽
    stats:
      trust: -10
    inventory: []
    location_id: corridor
```

- [ ] **Step 3: Write failing tests for loader**

```python
# tests/world/test_loader.py
from pathlib import Path

import pytest

from tavern.world.loader import load_scenario
from tavern.world.models import CharacterRole
from tavern.world.state import WorldState


SCENARIO_PATH = Path(__file__).parent.parent.parent / "data" / "scenarios" / "tavern"


class TestLoadScenario:
    def test_returns_world_state(self):
        state = load_scenario(SCENARIO_PATH)
        assert isinstance(state, WorldState)

    def test_loads_all_locations(self):
        state = load_scenario(SCENARIO_PATH)
        assert len(state.locations) == 5
        assert "tavern_hall" in state.locations
        assert "bar_area" in state.locations
        assert "cellar" in state.locations

    def test_loads_player(self):
        state = load_scenario(SCENARIO_PATH)
        player = state.characters["player"]
        assert player.role == CharacterRole.PLAYER
        assert player.location_id == "tavern_hall"

    def test_loads_npcs(self):
        state = load_scenario(SCENARIO_PATH)
        assert "bartender_grim" in state.characters
        assert "traveler" in state.characters
        assert "mysterious_guest" in state.characters

    def test_loads_items(self):
        state = load_scenario(SCENARIO_PATH)
        assert "cellar_key" in state.items
        assert "old_notice" in state.items

    def test_locked_exit_loaded(self):
        state = load_scenario(SCENARIO_PATH)
        cellar_exit = state.locations["bar_area"].exits["down"]
        assert cellar_exit.locked
        assert cellar_exit.key_item == "cellar_key"

    def test_player_id_set(self):
        state = load_scenario(SCENARIO_PATH)
        assert state.player_id == "player"

    def test_initial_turn_is_zero(self):
        state = load_scenario(SCENARIO_PATH)
        assert state.turn == 0
```

- [ ] **Step 4: Run tests — verify they fail**

Run: `pytest tests/world/test_loader.py -v`
Expected: FAIL — cannot import load_scenario

- [ ] **Step 5: Implement loader**

```python
# src/tavern/world/loader.py
from pathlib import Path

import yaml

from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def load_scenario(scenario_path: Path) -> WorldState:
    world_data = _load_yaml(scenario_path / "world.yaml")
    char_data = _load_yaml(scenario_path / "characters.yaml")

    locations = _build_locations(world_data["locations"])
    items = _build_items(world_data["items"])
    characters = _build_characters(char_data)

    return WorldState(
        turn=0,
        player_id="player",
        locations=locations,
        characters=characters,
        items=items,
    )


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_locations(raw: dict) -> dict[str, Location]:
    locations: dict[str, Location] = {}
    for loc_id, data in raw.items():
        exits = {}
        for direction, exit_data in data.get("exits", {}).items():
            exits[direction] = Exit(
                target=exit_data["target"],
                locked=exit_data.get("locked", False),
                key_item=exit_data.get("key_item"),
                description=exit_data.get("description", ""),
            )
        locations[loc_id] = Location(
            id=loc_id,
            name=data["name"],
            description=data["description"],
            exits=exits,
            items=tuple(data.get("items", [])),
            npcs=tuple(data.get("npcs", [])),
        )
    return locations


def _build_items(raw: dict) -> dict[str, Item]:
    items: dict[str, Item] = {}
    for item_id, data in raw.items():
        items[item_id] = Item(
            id=item_id,
            name=data["name"],
            description=data["description"],
            portable=data.get("portable", True),
            usable_with=tuple(data.get("usable_with", [])),
        )
    return items


def _build_characters(raw: dict) -> dict[str, Character]:
    characters: dict[str, Character] = {}

    player_data = raw["player"]
    characters["player"] = Character(
        id=player_data["id"],
        name=player_data["name"],
        role=CharacterRole.PLAYER,
        traits=tuple(player_data.get("traits", [])),
        stats=player_data.get("stats", {}),
        inventory=tuple(player_data.get("inventory", [])),
        location_id=player_data["location_id"],
    )

    for npc_id, data in raw.get("npcs", {}).items():
        characters[npc_id] = Character(
            id=npc_id,
            name=data["name"],
            role=CharacterRole.NPC,
            traits=tuple(data.get("traits", [])),
            stats=data.get("stats", {}),
            inventory=tuple(data.get("inventory", [])),
            location_id=data["location_id"],
        )

    return characters
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `pytest tests/world/test_loader.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add data/scenarios/tavern/ src/tavern/world/loader.py tests/world/test_loader.py
git commit -m "feat: add tavern scenario YAML data and loader"
```

---

## Task 5: LLM Adapter Protocol & OpenAI Implementation

**Files:**
- Create: `src/tavern/llm/adapter.py`
- Create: `src/tavern/llm/openai_llm.py`
- Create: `src/tavern/llm/service.py`
- Test: `tests/llm/test_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/llm/test_adapter.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tavern.engine.actions import ActionType
from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.openai_llm import OpenAIAdapter
from tavern.llm.service import LLMService
from tavern.world.models import ActionRequest


class TestLLMConfig:
    def test_create_config(self):
        config = LLMConfig(
            provider="openai", model="gpt-4o-mini",
            temperature=0.1, max_tokens=200,
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"

    def test_default_values(self):
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        assert config.timeout == 30.0
        assert config.max_retries == 3


class TestLLMRegistry:
    def test_create_openai_adapter(self):
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        adapter = LLMRegistry.create(config)
        assert isinstance(adapter, OpenAIAdapter)

    def test_unknown_provider_raises(self):
        config = LLMConfig(provider="unknown", model="x")
        with pytest.raises(ValueError, match="unknown"):
            LLMRegistry.create(config)


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_parsed_model(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"action": "move", "target": "bar_area", '
            '"detail": "走向吧台", "confidence": 0.9}'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        adapter = OpenAIAdapter(
            config=LLMConfig(provider="openai", model="gpt-4o-mini"),
        )
        adapter._client = mock_client

        messages = [{"role": "user", "content": "我想去吧台"}]
        result = await adapter.complete(messages, response_format=ActionRequest)
        assert isinstance(result, ActionRequest)
        assert result.action == ActionType.MOVE

    @pytest.mark.asyncio
    async def test_complete_returns_string_without_format(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你走向吧台。"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        adapter = OpenAIAdapter(
            config=LLMConfig(provider="openai", model="gpt-4o-mini"),
        )
        adapter._client = mock_client

        messages = [{"role": "user", "content": "test"}]
        result = await adapter.complete(messages)
        assert result == "你走向吧台。"


class TestLLMService:
    @pytest.mark.asyncio
    async def test_classify_intent(self):
        mock_adapter = AsyncMock()
        mock_adapter.complete = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE, target="bar_area",
                detail="走向吧台", confidence=0.95,
            )
        )

        service = LLMService(intent_adapter=mock_adapter, narrative_adapter=mock_adapter)
        scene_context = {
            "location": "tavern_hall",
            "npcs": ["traveler"],
            "items": ["old_notice"],
            "exits": ["north", "east", "west"],
        }
        result = await service.classify_intent("我想去吧台", scene_context)
        assert result.action == ActionType.MOVE
        assert result.target == "bar_area"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/llm/test_adapter.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement LLMConfig and LLMRegistry**

```python
# src/tavern/llm/adapter.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING, AsyncIterator, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


class LLMConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.5
    max_tokens: int = 500
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 30.0
    max_retries: int = 3


@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str: ...

    async def stream(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]: ...


class LLMRegistry:
    _providers: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type) -> None:
        cls._providers[name] = adapter_cls

    @classmethod
    def create(cls, config: LLMConfig) -> LLMAdapter:
        if config.provider not in cls._providers:
            raise ValueError(
                f"Unknown LLM provider: '{config.provider}'. "
                f"Available: {list(cls._providers.keys())}"
            )
        return cls._providers[config.provider](config=config)
```

- [ ] **Step 4: Implement OpenAIAdapter**

```python
# src/tavern/llm/openai_llm.py
from __future__ import annotations

import json
from typing import AsyncIterator, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from tavern.llm.adapter import LLMConfig, LLMRegistry

T = TypeVar("T", bound=BaseModel)


class OpenAIAdapter:
    def __init__(self, config: LLMConfig):
        self._config = config
        self._client = AsyncOpenAI(
            api_key=config.api_key or None,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        response_format: type[T] | None = None,
    ) -> T | str:
        kwargs: dict = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}
            # Append JSON instruction to system message
            if messages and messages[0]["role"] == "system":
                messages = list(messages)
                messages[0] = {
                    **messages[0],
                    "content": messages[0]["content"]
                    + "\n\nRespond with valid JSON only.",
                }
            kwargs["messages"] = messages

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if response_format is not None:
            return response_format.model_validate_json(content)
        return content

    async def stream(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


LLMRegistry.register("openai", OpenAIAdapter)
```

- [ ] **Step 5: Implement LLMService**

```python
# src/tavern/llm/service.py
from __future__ import annotations

from tavern.llm.adapter import LLMAdapter
from tavern.world.models import ActionRequest


INTENT_SYSTEM_PROMPT = """\
你是一个奇幻文字冒险游戏的意图分析器。根据玩家的输入，分析其意图并返回JSON。

当前场景信息：
- 位置: {location}
- 在场NPC: {npcs}
- 可见物品: {items}
- 可用出口: {exits}

动作类型:
- move: 移动到另一个位置
- look: 观察环境或某个对象
- search: 搜索隐藏物品
- talk: 与NPC对话
- persuade: 说服NPC
- trade: 与NPC交易
- take: 拾取物品
- use: 使用物品
- give: 给予物品
- stealth: 潜行
- combat: 战斗
- custom: 其他（无法归类时使用）

返回JSON格式: {{"action": "<动作类型>", "target": "<目标ID或null>", "detail": "<补充描述>", "confidence": <0.0-1.0>}}

示例:
- 输入: "走到吧台那边" -> {{"action": "move", "target": "bar_area", "detail": "走向吧台", "confidence": 0.95}}
- 输入: "看看四周有什么" -> {{"action": "look", "target": null, "detail": "观察周围环境", "confidence": 0.9}}
- 输入: "捡起那张告示" -> {{"action": "take", "target": "old_notice", "detail": "拾取旧告示", "confidence": 0.95}}
- 输入: "和旅行者聊聊" -> {{"action": "talk", "target": "traveler", "detail": "与旅行者对话", "confidence": 0.9}}
"""


class LLMService:
    def __init__(
        self,
        intent_adapter: LLMAdapter,
        narrative_adapter: LLMAdapter,
    ):
        self._intent = intent_adapter
        self._narrative = narrative_adapter

    async def classify_intent(
        self,
        player_input: str,
        scene_context: dict,
    ) -> ActionRequest:
        system_msg = INTENT_SYSTEM_PROMPT.format(
            location=scene_context.get("location", "unknown"),
            npcs=", ".join(scene_context.get("npcs", [])) or "无",
            items=", ".join(scene_context.get("items", [])) or "无",
            exits=", ".join(scene_context.get("exits", [])) or "无",
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": player_input},
        ]
        return await self._intent.complete(messages, response_format=ActionRequest)
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `pytest tests/llm/test_adapter.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/tavern/llm/ tests/llm/
git commit -m "feat: add LLM adapter protocol, OpenAI implementation, and LLMService"
```

---

## Task 6: Intent Parser

**Files:**
- Create: `src/tavern/parser/intent.py`
- Test: `tests/parser/test_intent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/parser/test_intent.py
from unittest.mock import AsyncMock

import pytest

from tavern.engine.actions import ActionType
from tavern.parser.intent import IntentParser
from tavern.world.models import ActionRequest


@pytest.fixture
def mock_llm_service():
    return AsyncMock()


@pytest.fixture
def parser(mock_llm_service):
    return IntentParser(llm_service=mock_llm_service)


class TestIntentParser:
    @pytest.mark.asyncio
    async def test_parse_move_intent(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE, target="bar_area",
                detail="走向吧台", confidence=0.95,
            )
        )
        result = await parser.parse(
            "我要去吧台",
            location_id="tavern_hall",
            npcs=["traveler"],
            items=["old_notice"],
            exits=["north", "east", "west"],
        )
        assert result.action == ActionType.MOVE
        assert result.target == "bar_area"

    @pytest.mark.asyncio
    async def test_parse_look_intent(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.LOOK, target=None,
                detail="环顾四周", confidence=0.9,
            )
        )
        result = await parser.parse(
            "看看周围",
            location_id="tavern_hall",
            npcs=["traveler"],
            items=["old_notice"],
            exits=["north", "east", "west"],
        )
        assert result.action == ActionType.LOOK

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back_to_custom(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE, target="bar_area",
                detail="模糊", confidence=0.3,
            )
        )
        result = await parser.parse(
            "嗯...",
            location_id="tavern_hall",
            npcs=[], items=[], exits=[],
        )
        assert result.action == ActionType.CUSTOM

    @pytest.mark.asyncio
    async def test_llm_error_returns_custom(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            side_effect=Exception("LLM error")
        )
        result = await parser.parse(
            "随便说说",
            location_id="tavern_hall",
            npcs=[], items=[], exits=[],
        )
        assert result.action == ActionType.CUSTOM
        assert not result.success if hasattr(result, "success") else True
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/parser/test_intent.py -v`
Expected: FAIL — cannot import IntentParser

- [ ] **Step 3: Implement IntentParser**

```python
# src/tavern/parser/intent.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest

if TYPE_CHECKING:
    from tavern.llm.service import LLMService

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.5


class IntentParser:
    def __init__(self, llm_service: LLMService):
        self._llm = llm_service

    async def parse(
        self,
        player_input: str,
        *,
        location_id: str,
        npcs: list[str],
        items: list[str],
        exits: list[str],
    ) -> ActionRequest:
        scene_context = {
            "location": location_id,
            "npcs": npcs,
            "items": items,
            "exits": exits,
        }
        try:
            result = await self._llm.classify_intent(player_input, scene_context)
        except Exception:
            logger.warning("LLM intent classification failed, falling back to CUSTOM")
            return ActionRequest(
                action=ActionType.CUSTOM,
                detail=player_input,
                confidence=0.0,
            )

        if result.confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "Low confidence %.2f for action %s, falling back to CUSTOM",
                result.confidence, result.action,
            )
            return ActionRequest(
                action=ActionType.CUSTOM,
                detail=player_input,
                confidence=result.confidence,
            )

        return result
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/parser/test_intent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/parser/intent.py tests/parser/test_intent.py
git commit -m "feat: add IntentParser with confidence threshold and error fallback"
```

---

## Task 7: Rules Engine

**Files:**
- Create: `src/tavern/engine/rules.py`
- Test: `tests/engine/test_rules.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_rules.py
import pytest

from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.world.models import ActionRequest


@pytest.fixture
def rules_engine():
    return RulesEngine()


class TestMoveAction:
    def test_move_to_valid_exit(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is not None
        assert diff.updated_characters["player"]["location_id"] == "bar_area"

    def test_move_to_invalid_direction(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.MOVE, target="up")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_move_to_locked_exit(self, rules_engine, sample_world_state):
        # Move player to bar_area first
        state = sample_world_state.apply(
            __import__("tavern.world.state", fromlist=["StateDiff"]).StateDiff(
                updated_characters={"player": {"location_id": "bar_area"}},
            )
        )
        request = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules_engine.validate(request, state)
        assert not result.success
        assert "锁" in result.message or "locked" in result.message.lower()

    def test_move_to_locked_exit_with_key(self, rules_engine, sample_world_state):
        from tavern.world.state import StateDiff

        state = sample_world_state.apply(
            StateDiff(
                updated_characters={
                    "player": {"location_id": "bar_area", "inventory": ("cellar_key",)},
                },
            )
        )
        request = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules_engine.validate(request, state)
        assert result.success


class TestLookAction:
    def test_look_at_current_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK)
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert "酒馆大厅" in result.message
        assert diff is None  # LOOK doesn't change state

    def test_look_at_specific_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK, target="old_notice")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert "告示" in result.message

    def test_look_at_nonexistent_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK, target="magic_sword")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success


class TestTakeAction:
    def test_take_portable_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TAKE, target="old_notice")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is not None
        assert "old_notice" in diff.updated_characters["player"]["inventory"]
        # item removed from location
        assert "old_notice" not in diff.updated_locations["tavern_hall"]["items"]

    def test_take_nonexistent_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TAKE, target="ghost_gem")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_take_non_portable_item(self, rules_engine, sample_world_state):
        # old_barrel is in cellar and non-portable, but test concept with a fixture
        from tavern.world.models import Item, Location, Exit
        from tavern.world.state import StateDiff

        state = sample_world_state.apply(
            StateDiff(
                updated_characters={"player": {"location_id": "test_room"}},
                updated_locations={},
                turn_increment=0,
            )
        )
        # Build state with non-portable item directly
        heavy_item = Item(id="heavy_rock", name="巨石",
                          description="太重了搬不动", portable=False)
        test_loc = Location(
            id="test_room", name="测试房间", description="测试",
            exits={}, items=("heavy_rock",), npcs=(),
        )
        from tavern.world.state import WorldState

        state = WorldState(
            turn=0, player_id="player",
            locations={**sample_world_state.locations, "test_room": test_loc},
            characters={
                **sample_world_state.characters,
                "player": sample_world_state.characters["player"].model_copy(
                    update={"location_id": "test_room"}
                ),
            },
            items={**sample_world_state.items, "heavy_rock": heavy_item},
        )
        request = ActionRequest(action=ActionType.TAKE, target="heavy_rock")
        result, diff = rules_engine.validate(request, state)
        assert not result.success
        assert diff is None


class TestCustomAction:
    def test_custom_action_always_succeeds(self, rules_engine, sample_world_state):
        request = ActionRequest(
            action=ActionType.CUSTOM, detail="跳一段舞", confidence=0.3,
        )
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is None  # CUSTOM doesn't change state in P1
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/engine/test_rules.py -v`
Expected: FAIL — cannot import RulesEngine

- [ ] **Step 3: Implement RulesEngine**

```python
# src/tavern/engine/rules.py
from __future__ import annotations

import uuid

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult, Event
from tavern.world.state import StateDiff, WorldState


class RulesEngine:
    def validate(
        self,
        request: ActionRequest,
        state: WorldState,
    ) -> tuple[ActionResult, StateDiff | None]:
        handler = _ACTION_HANDLERS.get(request.action, _handle_custom)
        return handler(request, state)


def _get_player(state: WorldState):
    return state.characters[state.player_id]


def _get_player_location(state: WorldState):
    player = _get_player(state)
    return state.locations[player.location_id]


def _handle_move(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)
    player = _get_player(state)
    direction = request.target

    if direction not in location.exits:
        return (
            ActionResult(
                success=False, action=ActionType.MOVE,
                message=f"这里没有通往「{direction}」的出口。可用方向: {', '.join(location.exits.keys())}",
                target=direction,
            ),
            None,
        )

    exit_ = location.exits[direction]

    if exit_.locked:
        if exit_.key_item and exit_.key_item in player.inventory:
            # Unlock and move
            new_exits = dict(location.exits)
            new_exits[direction] = exit_.model_copy(update={"locked": False})
            target_loc = state.locations[exit_.target]
            event = Event(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                turn=state.turn,
                type="unlock",
                actor=state.player_id,
                description=f"用{state.items.get(exit_.key_item, exit_.key_item)}打开了通往{target_loc.name}的门",
            )
            diff = StateDiff(
                updated_characters={state.player_id: {"location_id": exit_.target}},
                updated_locations={location.id: {"exits": new_exits}},
                new_events=(event,),
            )
            return (
                ActionResult(
                    success=True, action=ActionType.MOVE,
                    message=f"你用钥匙打开了门，走进了{target_loc.name}。\n\n{target_loc.description}",
                    target=exit_.target,
                ),
                diff,
            )
        return (
            ActionResult(
                success=False, action=ActionType.MOVE,
                message=f"通往{state.locations[exit_.target].name}的门被锁住了。{exit_.description}",
                target=direction,
            ),
            None,
        )

    target_loc = state.locations[exit_.target]
    diff = StateDiff(
        updated_characters={state.player_id: {"location_id": exit_.target}},
    )
    return (
        ActionResult(
            success=True, action=ActionType.MOVE,
            message=f"你走向{target_loc.name}。\n\n{target_loc.description}",
            target=exit_.target,
        ),
        diff,
    )


def _handle_look(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)

    if request.target is None:
        # Look at current location
        parts = [f"【{location.name}】", location.description]
        if location.npcs:
            npc_names = [state.characters[npc_id].name for npc_id in location.npcs
                         if npc_id in state.characters]
            if npc_names:
                parts.append(f"在场人物: {', '.join(npc_names)}")
        if location.items:
            item_names = [state.items[item_id].name for item_id in location.items
                          if item_id in state.items]
            if item_names:
                parts.append(f"可见物品: {', '.join(item_names)}")
        if location.exits:
            exit_descs = [f"  {d}: {e.description}" for d, e in location.exits.items()]
            parts.append("出口:\n" + "\n".join(exit_descs))
        return (
            ActionResult(
                success=True, action=ActionType.LOOK,
                message="\n".join(parts),
            ),
            None,
        )

    # Look at specific target
    target_id = request.target

    # Check items in location
    if target_id in location.items and target_id in state.items:
        item = state.items[target_id]
        return (
            ActionResult(
                success=True, action=ActionType.LOOK,
                message=f"【{item.name}】\n{item.description}",
                target=target_id,
            ),
            None,
        )

    # Check items in player inventory
    player = _get_player(state)
    if target_id in player.inventory and target_id in state.items:
        item = state.items[target_id]
        return (
            ActionResult(
                success=True, action=ActionType.LOOK,
                message=f"【{item.name}】（背包中）\n{item.description}",
                target=target_id,
            ),
            None,
        )

    # Check NPCs in location
    if target_id in location.npcs and target_id in state.characters:
        npc = state.characters[target_id]
        traits_desc = "、".join(npc.traits) if npc.traits else "难以捉摸"
        return (
            ActionResult(
                success=True, action=ActionType.LOOK,
                message=f"【{npc.name}】\n{traits_desc}",
                target=target_id,
            ),
            None,
        )

    return (
        ActionResult(
            success=False, action=ActionType.LOOK,
            message=f"你没有看到「{target_id}」。",
            target=target_id,
        ),
        None,
    )


def _handle_take(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)
    player = _get_player(state)
    target_id = request.target

    if target_id is None:
        return (
            ActionResult(
                success=False, action=ActionType.TAKE,
                message="你想拾取什么？",
            ),
            None,
        )

    if target_id not in location.items:
        return (
            ActionResult(
                success=False, action=ActionType.TAKE,
                message=f"这里没有「{target_id}」可以拾取。",
                target=target_id,
            ),
            None,
        )

    if target_id not in state.items:
        return (
            ActionResult(
                success=False, action=ActionType.TAKE,
                message=f"未知物品: {target_id}",
                target=target_id,
            ),
            None,
        )

    item = state.items[target_id]

    if not item.portable:
        return (
            ActionResult(
                success=False, action=ActionType.TAKE,
                message=f"「{item.name}」太重了，无法拾取。",
                target=target_id,
            ),
            None,
        )

    new_inventory = player.inventory + (target_id,)
    new_location_items = tuple(i for i in location.items if i != target_id)

    event = Event(
        id=f"evt_{uuid.uuid4().hex[:8]}",
        turn=state.turn,
        type="take",
        actor=state.player_id,
        description=f"拾取了{item.name}",
    )
    diff = StateDiff(
        updated_characters={state.player_id: {"inventory": new_inventory}},
        updated_locations={location.id: {"items": new_location_items}},
        new_events=(event,),
        turn_increment=0,
    )
    return (
        ActionResult(
            success=True, action=ActionType.TAKE,
            message=f"你拾取了「{item.name}」。",
            target=target_id,
        ),
        diff,
    )


def _handle_custom(request: ActionRequest, state: WorldState):
    return (
        ActionResult(
            success=True, action=ActionType.CUSTOM,
            message=f"你尝试了: {request.detail or '某些事情'}",
            detail=request.detail,
        ),
        None,
    )


_ACTION_HANDLERS = {
    ActionType.MOVE: _handle_move,
    ActionType.LOOK: _handle_look,
    ActionType.SEARCH: _handle_look,  # SEARCH reuses LOOK for P1
    ActionType.TAKE: _handle_take,
    ActionType.CUSTOM: _handle_custom,
}
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/engine/test_rules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/rules.py tests/engine/test_rules.py
git commit -m "feat: add RulesEngine with MOVE, LOOK, TAKE validation"
```

---

## Task 8: Rich CLI Renderer

**Files:**
- Create: `src/tavern/cli/renderer.py`
- Test: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cli/test_renderer.py
from io import StringIO
from unittest.mock import patch

import pytest

from rich.console import Console

from tavern.cli.renderer import Renderer
from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=True, width=80)


@pytest.fixture
def renderer(console):
    return Renderer(console=console)


class TestRenderer:
    def test_render_status_bar(self, renderer, sample_world_state, console):
        renderer.render_status_bar(sample_world_state)
        output = console.file.getvalue()
        assert "酒馆大厅" in output

    def test_render_action_result(self, renderer, console):
        result = ActionResult(
            success=True, action=ActionType.LOOK,
            message="你环顾四周，看到一间温暖的酒馆。",
        )
        renderer.render_result(result)
        output = console.file.getvalue()
        assert "温暖的酒馆" in output

    def test_render_failure_result(self, renderer, console):
        result = ActionResult(
            success=False, action=ActionType.MOVE,
            message="门被锁住了。",
        )
        renderer.render_result(result)
        output = console.file.getvalue()
        assert "锁" in output

    def test_render_inventory(self, renderer, sample_world_state, console):
        renderer.render_inventory(sample_world_state)
        output = console.file.getvalue()
        assert "背包" in output or "空" in output
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/cli/test_renderer.py -v`
Expected: FAIL — cannot import Renderer

- [ ] **Step 3: Implement Renderer**

```python
# src/tavern/cli/renderer.py
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult
from tavern.world.state import WorldState


class Renderer:
    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def render_status_bar(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]
        hp = player.stats.get("hp", "?")
        gold = player.stats.get("gold", "?")
        inv_count = len(player.inventory)

        status = Table.grid(padding=(0, 2))
        status.add_row(
            f"[bold cyan]{location.name}[/]",
            f"HP: [green]{hp}[/]",
            f"Gold: [yellow]{gold}[/]",
            f"背包: [white]{inv_count}件[/]",
            f"回合: [dim]{state.turn}[/]",
        )
        self.console.print(Panel(status, style="dim", height=3))

    def render_result(self, result: ActionResult) -> None:
        if result.success:
            style = "white"
            prefix = ""
        else:
            style = "red"
            prefix = "[bold red]✗[/] "

        self.console.print(f"\n{prefix}{result.message}\n", style=style)

    def render_inventory(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        if not player.inventory:
            self.console.print("\n[dim]背包是空的。[/]\n")
            return

        self.console.print("\n[bold]背包物品:[/]")
        for item_id in player.inventory:
            item = state.items.get(item_id)
            name = item.name if item else item_id
            desc = item.description if item else ""
            self.console.print(f"  [cyan]•[/] {name} — [dim]{desc}[/]")
        self.console.print()

    def render_status(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        self.console.print(f"\n[bold]角色状态 — {player.name}[/]")
        for stat, value in player.stats.items():
            self.console.print(f"  {stat}: {value}")
        self.console.print()

    def render_welcome(self, state: WorldState) -> None:
        self.console.print(
            Panel(
                "[bold]醉龙酒馆[/]\n\n"
                "欢迎来到奇幻世界的互动小说体验。\n"
                "输入自然语言与世界互动，输入 [cyan]help[/] 查看命令列表。",
                title="🐉 Tavern",
                border_style="bright_blue",
            )
        )
        location = state.locations[state.characters[state.player_id].location_id]
        self.console.print(f"\n{location.description}\n")

    def render_help(self) -> None:
        self.console.print("\n[bold]系统命令:[/]")
        commands = {
            "look": "查看当前环境",
            "inventory": "查看背包",
            "status": "查看角色状态",
            "hint": "获取游戏提示",
            "undo": "回退上一步",
            "help": "显示此帮助",
            "quit": "退出游戏",
        }
        for cmd, desc in commands.items():
            self.console.print(f"  [cyan]{cmd}[/] — {desc}")
        self.console.print("\n[dim]输入任何其他内容与世界自由互动。[/]\n")

    def get_input(self) -> str:
        try:
            return self.console.input("[bold green]▸[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/cli/test_renderer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer.py
git commit -m "feat: add Rich CLI renderer with status bar, result display, and inventory"
```

---

## Task 9: Game Loop & System Commands

**Files:**
- Create: `src/tavern/cli/app.py`
- Create: `src/tavern/__main__.py`

- [ ] **Step 1: Implement GameApp**

```python
# src/tavern/cli/app.py
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from tavern.cli.renderer import Renderer
from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.openai_llm import OpenAIAdapter  # noqa: F401 — triggers registration
from tavern.llm.service import LLMService
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
from tavern.world.models import ActionRequest
from tavern.world.state import StateManager, StateDiff

logger = logging.getLogger(__name__)

SYSTEM_COMMANDS = {"look", "inventory", "status", "hint", "undo", "help", "quit"}


class GameApp:
    def __init__(self, config_path: str = "config.yaml"):
        config = self._load_config(config_path)
        llm_config = config.get("llm", {})
        game_config = config.get("game", {})

        scenario_path = Path(game_config.get("scenario", "data/scenarios/tavern"))
        initial_state = load_scenario(scenario_path)

        self._state_manager = StateManager(
            initial_state=initial_state,
            max_history=game_config.get("undo_history_size", 50),
        )
        self._rules = RulesEngine()
        self._renderer = Renderer()

        intent_config = LLMConfig(**llm_config.get("intent", {
            "provider": "openai", "model": "gpt-4o-mini",
        }))
        narrative_config = LLMConfig(**llm_config.get("narrative", {
            "provider": "openai", "model": "gpt-4o",
        }))
        intent_adapter = LLMRegistry.create(intent_config)
        narrative_adapter = LLMRegistry.create(narrative_config)
        llm_service = LLMService(
            intent_adapter=intent_adapter,
            narrative_adapter=narrative_adapter,
        )
        self._parser = IntentParser(llm_service=llm_service)

        debug_config = config.get("debug", {})
        self._show_intent = debug_config.get("show_intent_json", False)
        log_level = debug_config.get("log_level", "INFO")
        logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

    @staticmethod
    def _load_config(path: str) -> dict:
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @property
    def state(self):
        return self._state_manager.current

    async def run(self) -> None:
        self._renderer.render_welcome(self.state)
        self._renderer.render_status_bar(self.state)

        while True:
            user_input = self._renderer.get_input()
            if not user_input:
                continue

            command = user_input.lower().strip()

            if command == "quit":
                self._renderer.console.print("\n[dim]再见，冒险者。[/]\n")
                break

            if command in SYSTEM_COMMANDS:
                self._handle_system_command(command)
                continue

            await self._handle_free_input(user_input)

    def _handle_system_command(self, command: str) -> None:
        if command == "look":
            request = ActionRequest(action=ActionType.LOOK)
            result, _ = self._rules.validate(request, self.state)
            self._renderer.render_result(result)

        elif command == "inventory":
            self._renderer.render_inventory(self.state)

        elif command == "status":
            self._renderer.render_status(self.state)

        elif command == "hint":
            self._renderer.console.print(
                "\n[dim italic]尝试和酒馆里的人聊聊天，也许能发现什么线索...[/]\n"
            )

        elif command == "undo":
            try:
                self._state_manager.undo()
                self._renderer.console.print("\n[dim]已回退上一步。[/]\n")
                request = ActionRequest(action=ActionType.LOOK)
                result, _ = self._rules.validate(request, self.state)
                self._renderer.render_result(result)
            except IndexError:
                self._renderer.console.print("\n[red]没有可以回退的步骤。[/]\n")

        elif command == "help":
            self._renderer.render_help()

        self._renderer.render_status_bar(self.state)

    async def _handle_free_input(self, user_input: str) -> None:
        player = self.state.characters[self.state.player_id]
        location = self.state.locations[player.location_id]

        request = await self._parser.parse(
            user_input,
            location_id=player.location_id,
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
        )

        if self._show_intent:
            self._renderer.console.print(
                f"[dim]Intent: {request.model_dump_json()}[/]"
            )

        result, diff = self._rules.validate(request, self.state)

        if diff is not None:
            self._state_manager.commit(diff, result)

        self._renderer.render_result(result)
        self._renderer.render_status_bar(self.state)
```

- [ ] **Step 2: Implement __main__.py**

```python
# src/tavern/__main__.py
import asyncio

from tavern.cli.app import GameApp


def main():
    app = GameApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manual smoke test**

Run: `cd /Users/makoto/Downloads/work/chatbot && python -m tavern`
Expected: Welcome banner displays, prompt appears, `look`/`inventory`/`help`/`quit` commands work

- [ ] **Step 4: Commit**

```bash
git add src/tavern/cli/app.py src/tavern/__main__.py
git commit -m "feat: add game loop with system commands and LLM intent parsing"
```

---

## Task 10: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
from unittest.mock import AsyncMock

import pytest

from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
from tavern.world.models import ActionRequest
from tavern.world.state import StateManager
from pathlib import Path

SCENARIO_PATH = Path(__file__).parent.parent / "data" / "scenarios" / "tavern"


class TestFullPipeline:
    @pytest.fixture
    def game_state(self):
        initial = load_scenario(SCENARIO_PATH)
        return StateManager(initial_state=initial)

    @pytest.fixture
    def rules(self):
        return RulesEngine()

    def test_look_at_starting_location(self, game_state, rules):
        request = ActionRequest(action=ActionType.LOOK)
        result, diff = rules.validate(request, game_state.current)
        assert result.success
        assert "酒馆大厅" in result.message

    def test_move_north_to_bar(self, game_state, rules):
        request = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(request, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

    def test_move_and_undo(self, game_state, rules):
        # Move north
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(req, game_state.current)
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

        # Undo
        game_state.undo()
        assert game_state.current.characters["player"].location_id == "tavern_hall"

    def test_take_item_then_undo(self, game_state, rules):
        # Take old_notice
        req = ActionRequest(action=ActionType.TAKE, target="old_notice")
        result, diff = rules.validate(req, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert "old_notice" in game_state.current.characters["player"].inventory

        # Undo
        game_state.undo()
        assert "old_notice" not in game_state.current.characters["player"].inventory
        assert "old_notice" in game_state.current.locations["tavern_hall"].items

    def test_cannot_enter_locked_cellar(self, game_state, rules):
        # Move to bar
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(req, game_state.current)
        game_state.commit(diff, result)

        # Try cellar
        req = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules.validate(req, game_state.current)
        assert not result.success
        assert diff is None

    def test_full_scenario_move_look_take(self, game_state, rules):
        # 1. Look around
        result, _ = rules.validate(
            ActionRequest(action=ActionType.LOOK), game_state.current
        )
        assert result.success
        assert "旅行者" in result.message or "告示" in result.message

        # 2. Take the notice
        result, diff = rules.validate(
            ActionRequest(action=ActionType.TAKE, target="old_notice"),
            game_state.current,
        )
        assert result.success
        game_state.commit(diff, result)

        # 3. Look at it in inventory
        result, _ = rules.validate(
            ActionRequest(action=ActionType.LOOK, target="old_notice"),
            game_state.current,
        )
        assert result.success
        assert "地下室" in result.message

        # 4. Move to bar
        result, diff = rules.validate(
            ActionRequest(action=ActionType.MOVE, target="north"),
            game_state.current,
        )
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

    @pytest.mark.asyncio
    async def test_intent_parser_pipeline(self, game_state, rules):
        mock_llm = AsyncMock()
        mock_llm.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE, target="north",
                detail="去吧台", confidence=0.95,
            )
        )
        parser = IntentParser(llm_service=mock_llm)

        location = game_state.current.locations["tavern_hall"]
        request = await parser.parse(
            "我要去吧台看看",
            location_id="tavern_hall",
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
        )

        result, diff = rules.validate(request, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Run coverage check**

Run: `pytest tests/ --cov=tavern --cov-report=term-missing`
Expected: Coverage ≥ 80% on core modules (models, state, rules, parser)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration smoke tests for full game pipeline"
```

---

## Phase 1 Completion Checklist

- [ ] `python -m tavern` launches and displays welcome screen
- [ ] `look` shows current location with NPCs, items, exits
- [ ] `inventory` shows empty/full inventory
- [ ] `status` shows player stats
- [ ] `help` lists commands
- [ ] Free text input is classified by LLM and validated by rules engine
- [ ] Player can move between tavern_hall ↔ bar_area ↔ corridor ↔ backyard
- [ ] Locked cellar door blocks entry without key
- [ ] Player can pick up portable items (old_notice)
- [ ] Non-portable items cannot be picked up
- [ ] `undo` reverses last action
- [ ] `quit` exits cleanly
- [ ] Test coverage ≥ 80%
