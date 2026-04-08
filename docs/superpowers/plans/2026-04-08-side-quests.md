# Side Quests System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 side quests (traveler, mysterious guest, backyard cart) with extended story effects (add/remove items, stat deltas).

**Architecture:** Two code changes feed the data layer: (1) `StateDiff` gets a new `character_stat_deltas` field with additive apply logic; (2) `StoryEffects` gets `add_items`, `remove_items`, `character_stat_deltas` with corresponding `_build_result` expansion. Then 8 story nodes, 3 items, and 4 skills YAML files define all quest content.

**Tech Stack:** Python 3.12, Pydantic v2, dataclasses, PyYAML, pytest

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/tavern/world/state.py` | Add `character_stat_deltas` to `StateDiff`; handle in `WorldState.apply` |
| Modify | `src/tavern/engine/rules.py` | Merge `character_stat_deltas` in `_merge_diffs` |
| Modify | `src/tavern/engine/story.py` | Extend `StoryEffects` with 3 fields + data classes; update `_build_result`; update loader |
| Modify | `data/scenarios/tavern/world.yaml` | Add 3 new items |
| Modify | `data/scenarios/tavern/story.yaml` | Add 8 side quest story nodes |
| Create | `data/scenarios/tavern/skills/traveler_quest_info.yaml` | Traveler quest active skill |
| Create | `data/scenarios/tavern/skills/traveler_gratitude.yaml` | Traveler quest complete skill |
| Create | `data/scenarios/tavern/skills/guest_quest_info.yaml` | Guest quest active skill |
| Create | `data/scenarios/tavern/skills/guest_secret_knowledge.yaml` | Guest quest complete skill |
| Modify | `tests/world/test_state.py` | Tests for `character_stat_deltas` apply |
| Modify | `tests/engine/test_rules_use.py` | Test `_merge_diffs` with `character_stat_deltas` |
| Modify | `tests/engine/test_story.py` | Tests for extended `StoryEffects` and `_build_result` |

---

## Task 1: StateDiff.character_stat_deltas + WorldState.apply

**Files:**
- Modify: `src/tavern/world/state.py`
- Modify: `tests/world/test_state.py`

### Background

`StateDiff` is a Pydantic `BaseModel` at `state.py:12`. `WorldState.apply` at `state.py:57` processes each diff field. `Character.stats` is a `dict[str, int]` frozen via `MappingProxyType`. The new field uses additive semantics: `current_val + delta`.

- [ ] **Step 1: Write failing tests**

Add to `tests/world/test_state.py` at the bottom of `TestWorldState`:

```python
def test_apply_character_stat_deltas(self, sample_world_state):
    diff = StateDiff(
        character_stat_deltas={"bartender_grim": {"trust": 20}},
        turn_increment=0,
    )
    new_state = sample_world_state.apply(diff)
    assert new_state.characters["bartender_grim"].stats["trust"] == 20

def test_apply_character_stat_deltas_additive(self, sample_world_state):
    diff1 = StateDiff(
        character_stat_deltas={"bartender_grim": {"trust": 15}},
        turn_increment=0,
    )
    state2 = sample_world_state.apply(diff1)
    diff2 = StateDiff(
        character_stat_deltas={"bartender_grim": {"trust": 10}},
        turn_increment=0,
    )
    state3 = state2.apply(diff2)
    assert state3.characters["bartender_grim"].stats["trust"] == 25

def test_apply_character_stat_deltas_new_stat(self, sample_world_state):
    diff = StateDiff(
        character_stat_deltas={"bartender_grim": {"fear": 5}},
        turn_increment=0,
    )
    new_state = sample_world_state.apply(diff)
    assert new_state.characters["bartender_grim"].stats["fear"] == 5

def test_apply_character_stat_deltas_unknown_character_ignored(self, sample_world_state):
    diff = StateDiff(
        character_stat_deltas={"nonexistent": {"trust": 10}},
        turn_increment=0,
    )
    new_state = sample_world_state.apply(diff)
    assert "nonexistent" not in new_state.characters
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/makoto/Downloads/work/chatbot
python3 -m pytest tests/world/test_state.py::TestWorldState::test_apply_character_stat_deltas -v 2>&1 | tail -10
```

Expected: `TypeError` or `AttributeError` — `character_stat_deltas` not recognized by `StateDiff`.

- [ ] **Step 3: Add character_stat_deltas to StateDiff**

In `src/tavern/world/state.py`, add the new field to `StateDiff` (line 20, before `turn_increment`):

```python
class StateDiff(BaseModel):
    updated_characters: dict[str, dict] = {}
    updated_locations: dict[str, dict] = {}
    added_items: dict[str, Item] = {}
    removed_items: tuple[str, ...] = ()
    relationship_changes: tuple[dict, ...] = ()
    quest_updates: dict[str, dict] = {}
    new_events: tuple[Event, ...] = ()
    story_active_since_updates: dict[str, int] = {}
    character_stat_deltas: dict[str, dict[str, int]] = {}
    turn_increment: int = 1
```

- [ ] **Step 4: Handle character_stat_deltas in WorldState.apply**

In `src/tavern/world/state.py`, inside `apply()`, add after the `updated_characters` loop (after line 65) and before `new_locations`:

```python
for char_id, deltas in diff.character_stat_deltas.items():
    if char_id not in new_characters:
        continue
    char = new_characters[char_id]
    new_stats = dict(char.stats)
    for stat_name, delta_val in deltas.items():
        new_stats[stat_name] = new_stats.get(stat_name, 0) + delta_val
    new_characters[char_id] = char.model_copy(update={"stats": new_stats})
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/world/test_state.py -v -k "stat_delta" 2>&1 | tail -10
```

Expected: 4 tests PASSED

- [ ] **Step 6: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/tavern/world/state.py tests/world/test_state.py
git commit -m "feat: add character_stat_deltas to StateDiff with additive apply logic"
```

---

## Task 2: _merge_diffs handles character_stat_deltas

**Files:**
- Modify: `src/tavern/engine/rules.py`
- Modify: `tests/engine/test_rules_use.py`

### Background

`_merge_diffs` at `rules.py:414` merges two `StateDiff` instances. `character_stat_deltas` merge strategy: for same character + same stat, sum the delta values.

- [ ] **Step 1: Write failing tests**

Add to `tests/engine/test_rules_use.py` at the bottom:

```python
def test_merge_diffs_character_stat_deltas_sum():
    from tavern.engine.rules import _merge_diffs
    a = StateDiff(character_stat_deltas={"npc1": {"trust": 10}})
    b = StateDiff(character_stat_deltas={"npc1": {"trust": 5, "fear": 3}})
    merged = _merge_diffs(a, b)
    assert merged.character_stat_deltas["npc1"]["trust"] == 15
    assert merged.character_stat_deltas["npc1"]["fear"] == 3


def test_merge_diffs_character_stat_deltas_different_chars():
    from tavern.engine.rules import _merge_diffs
    a = StateDiff(character_stat_deltas={"npc1": {"trust": 10}})
    b = StateDiff(character_stat_deltas={"npc2": {"trust": 5}})
    merged = _merge_diffs(a, b)
    assert merged.character_stat_deltas["npc1"]["trust"] == 10
    assert merged.character_stat_deltas["npc2"]["trust"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/engine/test_rules_use.py::test_merge_diffs_character_stat_deltas_sum -v 2>&1 | tail -10
```

Expected: FAIL — `character_stat_deltas` not in `_merge_diffs` output (defaults to `{}`).

- [ ] **Step 3: Add character_stat_deltas merge to _merge_diffs**

In `src/tavern/engine/rules.py`, update the `_merge_diffs` function. Add a helper inside it and include the new field in the returned `StateDiff`:

```python
def _merge_diffs(a: StateDiff, b: StateDiff) -> StateDiff:
    def _deep_merge(x: dict, y: dict) -> dict:
        result = dict(x)
        for k, v in y.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _merge_stat_deltas(x: dict, y: dict) -> dict:
        result = {char_id: dict(stats) for char_id, stats in x.items()}
        for char_id, stats in y.items():
            if char_id not in result:
                result[char_id] = dict(stats)
            else:
                for stat, val in stats.items():
                    result[char_id][stat] = result[char_id].get(stat, 0) + val
        return result

    return StateDiff(
        updated_characters=_deep_merge(a.updated_characters, b.updated_characters),
        updated_locations=_deep_merge(a.updated_locations, b.updated_locations),
        added_items={**a.added_items, **b.added_items},
        removed_items=a.removed_items + b.removed_items,
        relationship_changes=a.relationship_changes + b.relationship_changes,
        quest_updates={**a.quest_updates, **b.quest_updates},
        new_events=a.new_events + b.new_events,
        story_active_since_updates={**a.story_active_since_updates, **b.story_active_since_updates},
        character_stat_deltas=_merge_stat_deltas(a.character_stat_deltas, b.character_stat_deltas),
        turn_increment=a.turn_increment + b.turn_increment,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/engine/test_rules_use.py -v -k "stat_delta" 2>&1 | tail -10
```

Expected: 2 tests PASSED

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/rules.py tests/engine/test_rules_use.py
git commit -m "feat: merge character_stat_deltas additively in _merge_diffs"
```

---

## Task 3: StoryEffects extension + _build_result

**Files:**
- Modify: `src/tavern/engine/story.py`
- Modify: `tests/engine/test_story.py`

### Background

`StoryEffects` at `story.py:45` is a frozen dataclass with `quest_updates` and `new_events`. `_build_result` at `story.py:99` converts a `StoryNode` + `WorldState` into a `StoryResult` containing a `StateDiff`. We add 3 new fields: `add_items`, `remove_items`, `character_stat_deltas`. The `_build_result` function maps them into `StateDiff` fields.

- [ ] **Step 1: Write failing tests**

Add to `tests/engine/test_story.py`:

```python
# ---------------------------------------------------------------------------
# Extended effects: add_items, remove_items, character_stat_deltas
# ---------------------------------------------------------------------------

def test_build_result_add_items_to_inventory():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement
    effects = StoryEffects(
        quest_updates={"q1": {"status": "done"}},
        new_events=(),
        add_items=(ItemPlacement(item_id="map_fragment", to="inventory"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert "player" in diff.updated_characters
    inv = diff.updated_characters["player"]["inventory"]
    assert "map_fragment" in inv


def test_build_result_add_items_to_location():
    from tavern.engine.story import StoryEffects, StoryNode, ItemPlacement
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        add_items=(ItemPlacement(item_id="lost_amulet", to="backyard"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert "backyard" in diff.updated_locations
    assert "lost_amulet" in diff.updated_locations["backyard"]["items"]


def test_build_result_remove_items_from_inventory():
    from tavern.engine.story import StoryEffects, StoryNode, ItemRemoval
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        remove_items=(ItemRemoval(item_id="lost_amulet", from_="inventory"),),
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    state.characters["player"].inventory = ("lost_amulet", "old_notice")
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    inv = diff.updated_characters["player"]["inventory"]
    assert "lost_amulet" not in inv
    assert "old_notice" in inv


def test_build_result_character_stat_deltas():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={},
        new_events=(),
        character_stat_deltas={"traveler": {"trust": 20}},
    )
    node = StoryNode(
        id="n1", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint=None, fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.character_stat_deltas == {"traveler": {"trust": 20}}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/engine/test_story.py::test_build_result_add_items_to_inventory -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'ItemPlacement' from 'tavern.engine.story'`

- [ ] **Step 3: Add data classes and extend StoryEffects**

In `src/tavern/engine/story.py`, add after `NewEventSpec` (after line 41) and before `StoryEffects`:

```python
@dataclass(frozen=True)
class ItemPlacement:
    item_id: str
    to: str  # "inventory" or location_id


@dataclass(frozen=True)
class ItemRemoval:
    item_id: str
    from_: str  # "inventory" or location_id
```

Update `StoryEffects` to:

```python
@dataclass(frozen=True)
class StoryEffects:
    quest_updates: dict[str, dict]
    new_events: tuple[NewEventSpec, ...]
    add_items: tuple[ItemPlacement, ...] = ()
    remove_items: tuple[ItemRemoval, ...] = ()
    character_stat_deltas: dict[str, dict[str, int]] = field(default_factory=dict)
```

Add `from dataclasses import dataclass, field` to the imports at the top (replace `from dataclasses import dataclass`).

- [ ] **Step 4: Update _build_result to handle new fields**

Replace `_build_result` at `story.py:99`:

```python
def _build_result(node: StoryNode, state: "WorldState") -> StoryResult:
    events = tuple(
        Event(
            id=e.id,
            turn=state.turn,
            type=e.type,
            actor=e.actor if e.actor is not None else state.player_id,
            description=e.description,
        )
        for e in node.effects.new_events
    )
    quest_updates = {
        **node.effects.quest_updates,
        node.id: {"_story_status": "completed"},
    }

    updated_characters: dict[str, dict] = {}
    updated_locations: dict[str, dict] = {}

    player = state.characters.get(state.player_id)
    player_inv = list(player.inventory) if player else []

    for placement in node.effects.add_items:
        if placement.to == "inventory":
            player_inv.append(placement.item_id)
        else:
            loc = state.locations.get(placement.to)
            loc_items = list(loc.items) if loc else []
            loc_items.append(placement.item_id)
            updated_locations[placement.to] = {"items": tuple(loc_items)}

    for removal in node.effects.remove_items:
        if removal.from_ == "inventory":
            player_inv = [i for i in player_inv if i != removal.item_id]
        else:
            loc = state.locations.get(removal.from_)
            loc_items = list(loc.items) if loc else []
            loc_items = [i for i in loc_items if i != removal.item_id]
            updated_locations[removal.from_] = {"items": tuple(loc_items)}

    if node.effects.add_items or node.effects.remove_items:
        updated_characters[state.player_id] = {"inventory": tuple(player_inv)}

    diff = StateDiff(
        new_events=events,
        quest_updates=quest_updates,
        updated_characters=updated_characters,
        updated_locations=updated_locations,
        character_stat_deltas=dict(node.effects.character_stat_deltas),
        turn_increment=0,
    )
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=node.narrator_hint)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/engine/test_story.py -v -k "add_items or remove_items or stat_deltas" 2>&1 | tail -15
```

Expected: 4 tests PASSED

- [ ] **Step 6: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/tavern/engine/story.py tests/engine/test_story.py
git commit -m "feat: extend StoryEffects with add_items, remove_items, character_stat_deltas"
```

---

## Task 4: Story YAML loader parses new effects fields

**Files:**
- Modify: `src/tavern/engine/story.py` (the `load_story_nodes` function)
- Modify: `tests/engine/test_story.py`

### Background

`load_story_nodes` at `story.py:193` parses YAML entries. It constructs `StoryEffects` from the `effects` block. We extend it to parse `add_items`, `remove_items`, and `character_stat_deltas`.

- [ ] **Step 1: Write failing test**

Add to `tests/engine/test_story.py`:

```python
def test_load_story_nodes_with_extended_effects(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: test_extended
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates:
        q1: { status: done }
      new_events:
        - id: ev1
          type: story
          description: "something happened"
      add_items:
        - item_id: map_fragment
          to: inventory
        - item_id: lost_amulet
          to: backyard
      remove_items:
        - item_id: old_key
          from: inventory
      character_stat_deltas:
        traveler:
          trust: 20
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "test_extended" in nodes
    effects = nodes["test_extended"].effects
    assert len(effects.add_items) == 2
    assert effects.add_items[0].item_id == "map_fragment"
    assert effects.add_items[0].to == "inventory"
    assert effects.add_items[1].to == "backyard"
    assert len(effects.remove_items) == 1
    assert effects.remove_items[0].item_id == "old_key"
    assert effects.remove_items[0].from_ == "inventory"
    assert effects.character_stat_deltas == {"traveler": {"trust": 20}}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/engine/test_story.py::test_load_story_nodes_with_extended_effects -v 2>&1 | tail -10
```

Expected: FAIL — loader doesn't parse the new fields yet.

- [ ] **Step 3: Update load_story_nodes**

In `src/tavern/engine/story.py`, replace the `effects` construction block inside `load_story_nodes` (around lines 202-209):

```python
            effects_raw = entry.get("effects", {})
            new_events = tuple(
                NewEventSpec(**e) for e in (effects_raw.get("new_events") or [])
            )
            add_items = tuple(
                ItemPlacement(item_id=p["item_id"], to=p["to"])
                for p in (effects_raw.get("add_items") or [])
            )
            remove_items = tuple(
                ItemRemoval(item_id=r["item_id"], from_=r["from"])
                for r in (effects_raw.get("remove_items") or [])
            )
            effects = StoryEffects(
                quest_updates=dict(effects_raw.get("quest_updates") or {}),
                new_events=new_events,
                add_items=add_items,
                remove_items=remove_items,
                character_stat_deltas=dict(effects_raw.get("character_stat_deltas") or {}),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/engine/test_story.py -v 2>&1 | tail -10
```

Expected: all tests PASSED

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/story.py tests/engine/test_story.py
git commit -m "feat: parse add_items, remove_items, character_stat_deltas in story YAML loader"
```

---

## Task 5: New items in world.yaml

**Files:**
- Modify: `data/scenarios/tavern/world.yaml`

### Background

Three new items needed for side quests. No code changes — YAML only. Existing loader handles them automatically.

- [ ] **Step 1: Add items to world.yaml**

In `data/scenarios/tavern/world.yaml`, add after the `spare_key` entry in the `items` section:

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

- [ ] **Step 2: Run full suite to verify no regressions**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add data/scenarios/tavern/world.yaml
git commit -m "feat: add lost_amulet, map_fragment, guest_letter items for side quests"
```

---

## Task 6: Side quest story nodes in story.yaml

**Files:**
- Modify: `data/scenarios/tavern/story.yaml`

### Background

Add 8 story nodes for 3 side quests. All use the existing condition types: `event`, `relationship`, `location`, `inventory`, `quest`. Effects use the new `add_items`, `remove_items`, `character_stat_deltas` fields from Task 3-4.

- [ ] **Step 1: Add side quest nodes to story.yaml**

Append to `data/scenarios/tavern/story.yaml` after the existing `cellar_secret_revealed` node:

```yaml
  # ── Side Quest A: Traveler's Lost Amulet ──────────────────────────────────

  - id: traveler_quest_start
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: talked_to_traveler
          check: exists

    fail_forward:
      after_turns: 8
      hint_event:
        description: "旅行者艾琳叹了口气，喃喃道：'要是能找到我的护身符就好了……'"
        actor: traveler

    effects:
      quest_updates:
        traveler_quest: { status: active }
      new_events:
        - id: traveler_quest_accepted
          type: side_quest
          description: "艾琳请求你帮她找回丢失的银质护身符"
      add_items:
        - item_id: lost_amulet
          to: backyard

    narrator_hint: "艾琳恳请帮忙，语气诚恳焦急。她提到护身符可能掉在了后院马车附近。"

  - id: amulet_found
    act: act1
    requires: [traveler_quest_start]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: inventory
          event_id: lost_amulet

    fail_forward:
      after_turns: 15
      hint_event:
        description: "后院马车附近似乎有什么东西在微微发光。"
        actor: traveler

    effects:
      quest_updates:
        traveler_quest: { status: amulet_found }
      new_events:
        - id: amulet_picked_up
          type: side_quest
          description: "玩家找到了艾琳的银质护身符"

    narrator_hint: "护身符泛着微光，表面的符文似乎在呼应什么。这对艾琳一定很重要。"

  - id: traveler_quest_complete
    act: act1
    requires: [amulet_found]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: amulet_picked_up
          check: exists
        - type: location
          event_id: tavern_hall

    effects:
      quest_updates:
        traveler_quest: { status: completed }
      new_events:
        - id: traveler_quest_done
          type: side_quest
          description: "艾琳感激地接过护身符，送出地图碎片作为答谢"
      remove_items:
        - item_id: lost_amulet
          from: inventory
      add_items:
        - item_id: map_fragment
          to: inventory
      character_stat_deltas:
        traveler:
          trust: 20

    narrator_hint: "艾琳感激地接过护身符，眼中闪着泪光。她从包裹里取出一张泛黄的碎片递给你。"

  # ── Side Quest B: Mysterious Guest's Commission ───────────────────────────

  - id: guest_quest_start
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: relationship
          source: player
          target: mysterious_guest
          attribute: trust
          operator: ">="
          value: 5
        - type: location
          event_id: corridor

    fail_forward:
      after_turns: 10
      hint_event:
        description: "神秘旅客在走廊低语：'如果你愿意帮忙，我有个……请求。'"
        actor: mysterious_guest

    effects:
      quest_updates:
        guest_quest: { status: active }
      new_events:
        - id: guest_quest_accepted
          type: side_quest
          description: "神秘旅客请求你调查地下室的秘密"

    narrator_hint: "神秘旅客压低声音，语气紧迫而谨慎。他想知道酒保在地下室藏了什么。"

  - id: cellar_reported
    act: act1
    requires: [guest_quest_start]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: quest
          event_id: guest_quest
          check: exists
        - type: event
          event_id: cellar_entered
          check: exists
        - type: location
          event_id: corridor

    effects:
      quest_updates:
        guest_quest: { status: reported }
      new_events:
        - id: cellar_info_shared
          type: side_quest
          description: "你把地下室的发现告诉了神秘旅客"

    narrator_hint: "你把地下室的发现告诉了神秘旅客，他听得很认真，不时微微点头。"

  - id: guest_quest_complete
    act: act1
    requires: [cellar_reported]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: cellar_info_shared
          check: exists

    effects:
      quest_updates:
        guest_quest: { status: completed }
      new_events:
        - id: guest_quest_done
          type: side_quest
          description: "神秘旅客递给你一封密封的信件"
      add_items:
        - item_id: guest_letter
          to: inventory
      character_stat_deltas:
        mysterious_guest:
          trust: 15

    narrator_hint: "神秘旅客递给你一封密封的信件，眼中闪过复杂的神色。'这个……也许将来你会用到。'"

  # ── Side Quest C: Backyard Cart ───────────────────────────────────────────

  - id: cart_searched
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: location
          event_id: backyard
        - type: event
          event_id: searched_backyard
          check: exists

    fail_forward:
      after_turns: 5
      hint_event:
        description: "月光照在马车上，篷布下似乎有东西反光。"
        actor: player

    effects:
      quest_updates:
        backyard_search: { status: found_box }
      new_events:
        - id: cart_search_complete
          type: side_quest
          description: "在废弃马车下发现了一个生锈铁盒"

    narrator_hint: "马车篷布下露出一个生锈的铁盒，看起来已经在这里很久了。"

  - id: box_opened_node
    act: act1
    requires: [cart_searched]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: box_opened
          check: exists

    effects:
      quest_updates:
        backyard_search: { status: completed }
      new_events:
        - id: spare_key_obtained
          type: side_quest
          description: "从铁盒中获得了一把备用钥匙"

    narrator_hint: "铁盒里的备用钥匙，形状和地下室钥匙相似。也许能打开地下室的门。"
```

- [ ] **Step 2: Verify YAML parses correctly**

```bash
python3 -c "
from pathlib import Path
from tavern.engine.story import load_story_nodes
nodes = load_story_nodes(Path('data/scenarios/tavern/story.yaml'))
print(f'{len(nodes)} nodes loaded: {sorted(nodes.keys())}')
for nid, node in sorted(nodes.items()):
    ai = len(node.effects.add_items)
    ri = len(node.effects.remove_items)
    sd = bool(node.effects.character_stat_deltas)
    if ai or ri or sd:
        print(f'  {nid}: add_items={ai}, remove_items={ri}, stat_deltas={sd}')
"
```

Expected: 10 nodes loaded (2 main + 8 side), extended effects printed for relevant nodes.

- [ ] **Step 3: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add data/scenarios/tavern/story.yaml
git commit -m "feat: add 8 side quest story nodes for traveler, guest, and cart quests"
```

---

## Task 7: Skills YAML files

**Files:**
- Create: `data/scenarios/tavern/skills/traveler_quest_info.yaml`
- Create: `data/scenarios/tavern/skills/traveler_gratitude.yaml`
- Create: `data/scenarios/tavern/skills/guest_quest_info.yaml`
- Create: `data/scenarios/tavern/skills/guest_secret_knowledge.yaml`

### Background

Skills are YAML files loaded by `SkillManager`. Format: `id`, `character`, `activation.conditions`, `priority`, `facts`, `behavior`. Conditions reuse `ActivationCondition` structure. No code changes needed.

- [ ] **Step 1: Create skills directory**

```bash
ls data/scenarios/tavern/skills/ 2>/dev/null || mkdir -p data/scenarios/tavern/skills
```

- [ ] **Step 2: Create traveler_quest_info.yaml**

```yaml
id: traveler_quest_info
name: 旅行者的委托
character: traveler
activation:
  conditions:
    - type: quest
      event_id: traveler_quest
      check: exists
  priority: high

facts:
  - "护身符是家传宝物，从祖母那里继承的"
  - "护身符可能掉在了后院废弃马车附近"
  - "护身符表面有古老的符文，会微微发光"

behavior:
  tone: "焦急但友善，偶尔叹气"
  reveal_strategy: "先说护身符很重要，再说可能掉在后院"
  forbidden: "不会提及护身符有任何魔法效果"

related_skills:
  - traveler_gratitude
```

- [ ] **Step 3: Create traveler_gratitude.yaml**

```yaml
id: traveler_gratitude
name: 旅行者的感谢
character: traveler
activation:
  conditions:
    - type: quest
      event_id: traveler_quest
      check: exists
    - type: event
      event_id: traveler_quest_done
      check: exists
  priority: high

facts:
  - "地图碎片标注了城镇地下密道的一段走向"
  - "这张地图碎片是在旅途中一个废弃图书馆里找到的"
  - "密道似乎通往城外的森林"

behavior:
  tone: "感激、放松、愿意分享更多"
  reveal_strategy: "主动分享地图碎片的来历和密道信息"
  forbidden: "不知道密道的确切位置和目前是否有人使用"

related_skills: []
```

- [ ] **Step 4: Create guest_quest_info.yaml**

```yaml
id: guest_quest_info
name: 神秘旅客的委托
character: mysterious_guest
activation:
  conditions:
    - type: quest
      event_id: guest_quest
      check: exists
  priority: high

facts:
  - "怀疑酒保在地下室藏了什么东西"
  - "地下室最近有异常动静"
  - "自己来酒馆是有特殊目的的"

behavior:
  tone: "冷静、点到为止、警觉"
  reveal_strategy: "只说怀疑地下室有秘密，不透露自己的真实身份和目的"
  forbidden: "绝不透露自己的身份、来历或真正目的"

related_skills:
  - guest_secret_knowledge
```

- [ ] **Step 5: Create guest_secret_knowledge.yaml**

```yaml
id: guest_secret_knowledge
name: 神秘旅客的秘密
character: mysterious_guest
activation:
  conditions:
    - type: event
      event_id: guest_quest_done
      check: exists
  priority: high

facts:
  - "信件内容暗示城外有一个组织在关注这条密道"
  - "密道可能与二十年前的战争有关"
  - "信件上的徽章属于一个古老的骑士团"

behavior:
  tone: "稍微放下戒备、语气深沉"
  reveal_strategy: "暗示信件的重要性，但不直接说明内容"
  forbidden: "不会说出骑士团的名字或自己与骑士团的关系"

related_skills: []
```

- [ ] **Step 6: Verify skills load correctly**

```bash
python3 -c "
from pathlib import Path
from tavern.world.skills import SkillManager
sm = SkillManager()
sm.load_skills(Path('data/scenarios/tavern'))
print(f'{len(sm._skills)} skills loaded: {sorted(sm._skills.keys())}')
"
```

Expected: 4 skills loaded.

- [ ] **Step 7: Run full suite**

```bash
python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add data/scenarios/tavern/skills/
git commit -m "feat: add 4 NPC skill files for traveler and guest side quests"
```

---

## Verification

After all tasks:

```bash
python3 -m pytest tests/ -q
```

Expected: all tests pass. Check coverage on modified files:

```bash
python3 -m pytest tests/world/test_state.py tests/engine/test_story.py tests/engine/test_rules_use.py \
  --cov=tavern.world.state --cov=tavern.engine.story --cov=tavern.engine.rules \
  --cov-report=term-missing 2>&1 | tail -20
```

Validate all 10 story nodes load and 4 skills load:

```bash
python3 -c "
from pathlib import Path
from tavern.engine.story import load_story_nodes
from tavern.world.skills import SkillManager
nodes = load_story_nodes(Path('data/scenarios/tavern/story.yaml'))
sm = SkillManager()
sm.load_skills(Path('data/scenarios/tavern'))
print(f'Story nodes: {len(nodes)} (expected 10)')
print(f'Skills: {len(sm._skills)} (expected 4)')
assert len(nodes) == 10
assert len(sm._skills) == 4
print('All good!')
"
```
