# Phase 4: Content / Memory / Log / Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the remaining 4 architectural improvements from the master design: §3 Markdown-as-Code ContentLoader, §9 Classified Memory System, §8 JSONL Game Logger, §10 Scene Context Cache.

**Architecture:** ContentLoader parses Markdown+frontmatter into ContentEntry objects with variant support. ClassifiedMemorySystem replaces MemorySystem with type-based decay and budget-aware context building. GameLogger provides async JSONL append-only logging. SceneContextCache provides LRU caching for prompt building with auto-invalidation.

**Tech Stack:** Python 3.14, Pydantic, pytest, pytest-asyncio, PyYAML (frontmatter parsing)

---

### Task 1: ContentEntry data models + ContentError

**Files:**
- Create: `src/tavern/content/__init__.py`
- Create: `src/tavern/content/loader.py`
- Test: `tests/content/test_loader.py`

- [ ] **Step 1: Write failing tests for data models**

```python
# tests/content/test_loader.py
from __future__ import annotations

import pytest

from tavern.content.loader import ContentEntry, ContentError, VariantDef


def test_variant_def_frozen():
    v = VariantDef(name="night", when="time:night")
    assert v.name == "night"
    assert v.when == "time:night"
    with pytest.raises(AttributeError):
        v.name = "day"


def test_content_entry_defaults():
    entry = ContentEntry(
        id="tavern_hall",
        content_type="room",
        metadata={},
        body="默认描述",
        variants={},
        variant_defs=(),
    )
    assert entry.id == "tavern_hall"
    assert entry.content_type == "room"
    assert entry.body == "默认描述"
    assert entry.variants == {}


def test_content_entry_with_variants():
    entry = ContentEntry(
        id="tavern_hall",
        content_type="room",
        metadata={"atmosphere": "warm"},
        body="默认描述",
        variants={"night": "夜晚描述", "after_secret": "秘密后描述"},
        variant_defs=(
            VariantDef(name="after_secret", when="event:cellar_secret_revealed"),
            VariantDef(name="night", when="time:night"),
        ),
    )
    assert len(entry.variant_defs) == 2
    assert entry.variants["night"] == "夜晚描述"


def test_content_error():
    with pytest.raises(ContentError, match="invalid"):
        raise ContentError("invalid content id")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/content/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tavern.content'`

- [ ] **Step 3: Implement data models**

```python
# src/tavern/content/__init__.py
```

```python
# src/tavern/content/loader.py
from __future__ import annotations

import re
from dataclasses import dataclass


class ContentError(Exception):
    pass


_VALID_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class VariantDef:
    name: str
    when: str


@dataclass(frozen=True)
class ContentEntry:
    id: str
    content_type: str
    metadata: dict
    body: str
    variants: dict[str, str]
    variant_defs: tuple[VariantDef, ...]


def validate_content_id(content_id: str) -> None:
    if not _VALID_ID_PATTERN.match(content_id):
        raise ContentError(
            f"Invalid content ID '{content_id}': only [a-z0-9_] allowed"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/content/test_loader.py -v`
Expected: PASS — all 4 tests green

- [ ] **Step 5: Commit**

```bash
git add src/tavern/content/__init__.py src/tavern/content/loader.py tests/content/__init__.py tests/content/test_loader.py
git commit -m "feat(§3): add ContentEntry, VariantDef, ContentError data models"
```

---

### Task 2: evaluate_condition_str adapter in story_conditions.py

**Files:**
- Modify: `src/tavern/engine/story_conditions.py`
- Test: `tests/engine/test_story_conditions_str.py`

ContentLoader needs to evaluate condition strings like `"event:cellar_secret_revealed"` or `"relationship:bartender_grim >= 30"`. The existing `CONDITION_REGISTRY` expects `ActivationCondition` objects. We add a parser + adapter function.

- [ ] **Step 1: Write failing tests for condition string parsing**

```python
# tests/engine/test_story_conditions_str.py
from __future__ import annotations

import pytest

from tavern.engine.story_conditions import parse_condition_str, evaluate_condition_str
from tavern.world.memory import EventTimeline, RelationshipGraph
from tavern.world.models import Event


def _make_timeline(event_ids: list[str]) -> EventTimeline:
    events = tuple(
        Event(id=eid, type="test", description="", actor="player", turn=1)
        for eid in event_ids
    )
    return EventTimeline(events)


def test_parse_event_condition():
    cond = parse_condition_str("event:cellar_secret_revealed")
    assert cond.type == "event"
    assert cond.event_id == "cellar_secret_revealed"
    assert cond.check == "exists"


def test_parse_event_not_exists():
    cond = parse_condition_str("event_not_exists:cellar_entered")
    assert cond.type == "event"
    assert cond.event_id == "cellar_entered"
    assert cond.check == "not_exists"


def test_parse_relationship_condition():
    cond = parse_condition_str("relationship:bartender_grim >= 30")
    assert cond.type == "relationship"
    assert cond.source == "player"
    assert cond.target == "bartender_grim"
    assert cond.operator == ">="
    assert cond.value == 30


def test_parse_inventory_condition():
    cond = parse_condition_str("inventory:cellar_key")
    assert cond.type == "inventory"
    assert cond.event_id == "cellar_key"


def test_parse_quest_condition():
    cond = parse_condition_str("quest:main_quest:completed")
    assert cond.type == "quest"
    assert cond.event_id == "main_quest"
    assert cond.check == "completed"


def test_parse_location_condition():
    cond = parse_condition_str("location:tavern_hall")
    assert cond.type == "location"
    assert cond.event_id == "tavern_hall"


def test_parse_invalid_condition():
    with pytest.raises(ValueError, match="Cannot parse"):
        parse_condition_str("")


def test_evaluate_event_exists(make_state):
    state = make_state()
    timeline = _make_timeline(["cellar_secret_revealed"])
    graph = RelationshipGraph()
    result = evaluate_condition_str(
        "event:cellar_secret_revealed", state, timeline, graph,
    )
    assert result is True


def test_evaluate_event_not_exists(make_state):
    state = make_state()
    timeline = _make_timeline([])
    graph = RelationshipGraph()
    result = evaluate_condition_str(
        "event:cellar_secret_revealed", state, timeline, graph,
    )
    assert result is False


def test_evaluate_relationship_ge(make_state):
    state = make_state()
    graph = RelationshipGraph()
    graph.update(
        __import__("tavern.world.memory", fromlist=["RelationshipDelta"]).RelationshipDelta(
            src="player", tgt="bartender_grim", delta=35,
        )
    )
    timeline = _make_timeline([])
    result = evaluate_condition_str(
        "relationship:bartender_grim >= 30", state, timeline, graph,
    )
    assert result is True
```

Note: the `make_state` fixture should already exist in `conftest.py`. If not, create a minimal one in this test file that returns a WorldState with a player character.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_story_conditions_str.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_condition_str'`

- [ ] **Step 3: Implement parse_condition_str and evaluate_condition_str**

Add to the end of `src/tavern/engine/story_conditions.py`:

```python
import re as _re

_REL_PATTERN = _re.compile(
    r"^relationship:(\w+)\s*(==|!=|>=|<=|>|<)\s*(-?\d+)$"
)


def parse_condition_str(condition_str: str) -> ActivationCondition:
    """Parse a 'type:params' condition string into an ActivationCondition.

    Supported formats:
      event:event_id              → event exists check
      event_not_exists:event_id   → event not-exists check
      event_exists:event_id       → event exists check (explicit)
      relationship:target OP val  → relationship comparison (player as source)
      inventory:item_id           → item in player inventory
      quest:quest_id:status       → quest status check
      location:location_id        → player at location
    """
    if not condition_str or ":" not in condition_str:
        raise ValueError(f"Cannot parse condition string: {condition_str!r}")

    # event_exists / event_not_exists shorthand
    if condition_str.startswith("event_exists:"):
        event_id = condition_str.split(":", 1)[1].strip()
        return ActivationCondition(type="event", event_id=event_id, check="exists")

    if condition_str.startswith("event_not_exists:"):
        event_id = condition_str.split(":", 1)[1].strip()
        return ActivationCondition(type="event", event_id=event_id, check="not_exists")

    cond_type, _, rest = condition_str.partition(":")
    rest = rest.strip()

    if cond_type == "event":
        return ActivationCondition(type="event", event_id=rest, check="exists")

    if cond_type == "relationship":
        m = _REL_PATTERN.match(condition_str)
        if not m:
            raise ValueError(f"Cannot parse relationship condition: {condition_str!r}")
        target, op, val = m.group(1), m.group(2), int(m.group(3))
        return ActivationCondition(
            type="relationship", source="player", target=target,
            operator=op, value=val,
        )

    if cond_type == "inventory":
        return ActivationCondition(type="inventory", event_id=rest)

    if cond_type == "quest":
        parts = rest.split(":", 1)
        if len(parts) == 2:
            return ActivationCondition(type="quest", event_id=parts[0], check=parts[1])
        return ActivationCondition(type="quest", event_id=rest)

    if cond_type == "location":
        return ActivationCondition(type="location", event_id=rest)

    raise ValueError(f"Cannot parse condition string: {condition_str!r}")


def evaluate_condition_str(
    condition_str: str,
    state: WorldState,
    timeline: EventTimeline,
    relationships: RelationshipGraph,
) -> bool:
    """Parse condition string and evaluate against current state."""
    cond = parse_condition_str(condition_str)
    evaluator = CONDITION_REGISTRY.get(cond.type)
    if evaluator is None:
        logger.warning("No evaluator for condition type: %s", cond.type)
        return False
    return evaluator(cond, state, timeline, relationships)
```

Also add the required imports at the top of the file (after existing imports):

```python
from tavern.world.memory import EventTimeline, RelationshipGraph
```

Note: `EventTimeline` and `RelationshipGraph` are already in the TYPE_CHECKING block. Move them out since `evaluate_condition_str` needs them at runtime.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_story_conditions_str.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/story_conditions.py tests/engine/test_story_conditions_str.py
git commit -m "feat(§3): add parse_condition_str and evaluate_condition_str"
```

---

### Task 3: ContentLoader — load_directory + resolve

**Files:**
- Modify: `src/tavern/content/loader.py`
- Test: `tests/content/test_loader.py` (append tests)

- [ ] **Step 1: Write failing tests for ContentLoader**

Append to `tests/content/test_loader.py`:

```python
from pathlib import Path
from tavern.content.loader import ContentLoader


@pytest.fixture
def content_dir(tmp_path):
    """Create a temporary content directory with test Markdown files."""
    rooms = tmp_path / "rooms"
    rooms.mkdir()

    # Main file with frontmatter
    (rooms / "tavern_hall.md").write_text(
        "---\n"
        "id: tavern_hall\n"
        "type: room\n"
        "variants:\n"
        "  - name: after_secret\n"
        '    when: "event:cellar_secret_revealed"\n'
        "  - name: night\n"
        '    when: "time:night"\n'
        "tags: [main_area]\n"
        "---\n"
        "\n"
        "你站在酒馆大厅中。\n",
        encoding="utf-8",
    )

    # Variant files (pure body, no frontmatter)
    (rooms / "tavern_hall.night.md").write_text(
        "酒馆已近打烊时分。\n",
        encoding="utf-8",
    )
    (rooms / "tavern_hall.after_secret.md").write_text(
        "大厅里的气氛变了。\n",
        encoding="utf-8",
    )

    # Second room, no variants
    (rooms / "bar_area.md").write_text(
        "---\n"
        "id: bar_area\n"
        "type: room\n"
        "---\n"
        "\n"
        "吧台区域。\n",
        encoding="utf-8",
    )

    # NPC directory
    npcs = tmp_path / "npcs"
    npcs.mkdir()
    (npcs / "bartender_grim.md").write_text(
        "---\n"
        "id: bartender_grim\n"
        "type: npc\n"
        "personality_tags: [guarded]\n"
        "---\n"
        "\n"
        "壮实的中年男人。\n",
        encoding="utf-8",
    )

    return tmp_path


def test_load_directory_finds_all_entries(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    assert "tavern_hall" in loader.entries
    assert "bar_area" in loader.entries
    assert "bartender_grim" in loader.entries
    assert len(loader.entries) == 3


def test_load_directory_parses_frontmatter(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert entry.content_type == "room"
    assert "main_area" in entry.metadata.get("tags", [])
    assert len(entry.variant_defs) == 2


def test_load_directory_loads_variant_bodies(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert "night" in entry.variants
    assert "after_secret" in entry.variants
    assert "打烊" in entry.variants["night"]
    assert "气氛变了" in entry.variants["after_secret"]


def test_load_directory_default_body(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert "酒馆大厅" in entry.body


def test_resolve_returns_default_body_when_no_conditions_match(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    # No evaluator provided → all conditions fail → default body
    body = loader.resolve("tavern_hall")
    assert "酒馆大厅" in body


def test_resolve_returns_none_for_unknown_id():
    loader = ContentLoader()
    result = loader.resolve("nonexistent")
    assert result is None


def test_resolve_with_condition_evaluator(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)

    def always_true(cond_str, state, tl, rg):
        return "after_secret" in cond_str

    body = loader.resolve("tavern_hall", condition_evaluator=always_true)
    assert "气氛变了" in body


def test_load_invalid_id(tmp_path):
    rooms = tmp_path / "rooms"
    rooms.mkdir()
    (rooms / "Invalid-ID.md").write_text(
        "---\nid: Invalid-ID\ntype: room\n---\n\nbody\n",
        encoding="utf-8",
    )
    loader = ContentLoader()
    with pytest.raises(ContentError, match="Invalid content ID"):
        loader.load_directory(tmp_path)


def test_load_empty_directory(tmp_path):
    loader = ContentLoader()
    loader.load_directory(tmp_path)
    assert len(loader.entries) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/content/test_loader.py::test_load_directory_finds_all_entries -v`
Expected: FAIL — `ImportError: cannot import name 'ContentLoader'`

- [ ] **Step 3: Implement ContentLoader**

Add to `src/tavern/content/loader.py`:

```python
import logging
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger(__name__)

ConditionEvaluatorFn = Callable[..., bool]


class ContentLoader:
    def __init__(self) -> None:
        self._entries: dict[str, ContentEntry] = {}

    @property
    def entries(self) -> dict[str, ContentEntry]:
        return self._entries

    def load_directory(self, path: Path) -> None:
        if not path.exists():
            return
        md_files = sorted(path.rglob("*.md"))

        # First pass: separate main files and variant files
        main_files: dict[str, tuple[Path, dict, str]] = {}  # id -> (path, meta, body)
        variant_files: dict[str, dict[str, str]] = {}  # id -> {variant_name: body}

        for md_path in md_files:
            stem = md_path.stem  # e.g. "tavern_hall" or "tavern_hall.night"
            parts = stem.split(".", 1)
            base_id = parts[0]

            validate_content_id(base_id)

            raw = md_path.read_text(encoding="utf-8")

            if len(parts) == 1:
                # Main file — parse frontmatter
                meta, body = _parse_frontmatter(raw)
                content_id = meta.get("id", base_id)
                validate_content_id(content_id)
                main_files[content_id] = (md_path, meta, body)
            else:
                # Variant file — pure body
                variant_name = parts[1]
                variant_files.setdefault(base_id, {})[variant_name] = raw.strip()

        # Second pass: assemble ContentEntry objects
        for content_id, (_, meta, body) in main_files.items():
            raw_variants = meta.pop("variants", []) or []
            variant_defs = tuple(
                VariantDef(name=v["name"], when=v["when"])
                for v in raw_variants
                if isinstance(v, dict) and "name" in v and "when" in v
            )
            content_type = meta.pop("type", "unknown")
            meta.pop("id", None)

            variants = variant_files.get(content_id, {})

            self._entries[content_id] = ContentEntry(
                id=content_id,
                content_type=content_type,
                metadata=meta,
                body=body,
                variants=variants,
                variant_defs=variant_defs,
            )

    def resolve(
        self,
        entry_id: str,
        condition_evaluator: ConditionEvaluatorFn | None = None,
        **eval_kwargs,
    ) -> str | None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        if condition_evaluator is not None:
            for variant_def in entry.variant_defs:
                if condition_evaluator(variant_def.when, **eval_kwargs):
                    variant_body = entry.variants.get(variant_def.name)
                    if variant_body is not None:
                        return variant_body

        return entry.body


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from Markdown content.

    Returns (metadata_dict, body_text).
    """
    if not raw.startswith("---"):
        return {}, raw.strip()

    end_idx = raw.find("---", 3)
    if end_idx == -1:
        return {}, raw.strip()

    frontmatter_str = raw[3:end_idx].strip()
    body = raw[end_idx + 3:].strip()

    try:
        meta = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError:
        logger.warning("Failed to parse frontmatter, treating as plain body")
        meta = {}

    return meta, body
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/content/test_loader.py -v`
Expected: PASS — all tests green

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed

- [ ] **Step 6: Commit**

```bash
git add src/tavern/content/loader.py tests/content/test_loader.py
git commit -m "feat(§3): implement ContentLoader with frontmatter parsing and variant resolution"
```

---

### Task 4: MemoryType + MemoryEntry + MemoryBudget data models

**Files:**
- Modify: `src/tavern/world/memory.py` (add new types, keep existing MemoryContext/EventTimeline/RelationshipGraph)
- Test: `tests/world/test_classified_memory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/world/test_classified_memory.py
from __future__ import annotations

import pytest

from tavern.world.memory import MemoryBudget, MemoryEntry, MemoryType


def test_memory_type_values():
    assert MemoryType.LORE.value == "lore"
    assert MemoryType.QUEST.value == "quest"
    assert MemoryType.RELATIONSHIP.value == "relationship"
    assert MemoryType.DISCOVERY.value == "discovery"


def test_memory_entry_frozen():
    entry = MemoryEntry(
        id="m1",
        memory_type=MemoryType.LORE,
        content="格林透露了地窖秘密",
        importance=8,
        created_turn=5,
        last_relevant_turn=5,
    )
    assert entry.importance == 8
    with pytest.raises(AttributeError):
        entry.importance = 10


def test_memory_budget_defaults():
    budget = MemoryBudget()
    assert budget.lore == 200
    assert budget.quest == 300
    assert budget.relationship == 150
    assert budget.discovery == 100


def test_memory_budget_custom():
    budget = MemoryBudget(lore=500, quest=200, relationship=100, discovery=50)
    assert budget.lore == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_classified_memory.py -v`
Expected: FAIL — `ImportError: cannot import name 'MemoryBudget'`

- [ ] **Step 3: Add data models to memory.py**

Add after the existing `RelationshipDelta`/`Relationship` dataclasses (around line 35) in `src/tavern/world/memory.py`:

```python
from enum import Enum


class MemoryType(Enum):
    LORE = "lore"
    QUEST = "quest"
    RELATIONSHIP = "relationship"
    DISCOVERY = "discovery"


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    memory_type: MemoryType
    content: str
    importance: int
    created_turn: int
    last_relevant_turn: int


@dataclass(frozen=True)
class MemoryBudget:
    lore: int = 200
    quest: int = 300
    relationship: int = 150
    discovery: int = 100
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/world/test_classified_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/memory.py tests/world/test_classified_memory.py
git commit -m "feat(§9): add MemoryType, MemoryEntry, MemoryBudget data models"
```

---

### Task 5: ClassifiedMemorySystem — replaces MemorySystem

**Files:**
- Modify: `src/tavern/world/memory.py` (rename MemorySystem → ClassifiedMemorySystem, rewrite internals)
- Modify: `tests/world/test_classified_memory.py` (append)
- Modify: `src/tavern/cli/app.py` (update import if class name changes)
- Modify: `src/tavern/engine/modes/exploring.py` (if accessing private attrs like `_timeline`)

The class name stays `MemorySystem` to avoid mass-rename across the codebase. Internal implementation changes.

**Important:** The existing `MemorySystem` is used by:
- `app.py:86-89` — constructor `MemorySystem(state, skills_dir)`
- `app.py:227-230` — `self._memory.build_context(actor, state)`
- `exploring.py:83-86` — `context.memory.build_context(actor, state)`
- `exploring.py:97-98` — `context.memory._timeline`, `context.memory._relationship_graph` (private access!)
- `command_defs.py:35-37` — `ctx.memory.get_player_relationships()`
- `command_defs.py:72,92` — `ctx.memory.sync_to_state()`, `ctx.memory.rebuild()`

We must preserve all these public interfaces. For the private attribute access in `exploring.py`, expose public properties.

- [ ] **Step 1: Write failing tests for ClassifiedMemorySystem**

Append to `tests/world/test_classified_memory.py`:

```python
from tavern.world.memory import (
    ClassifiedMemorySystem,
    EventTimeline,
    MemoryContext,
    RelationshipGraph,
    RelationshipDelta,
)
from tavern.world.models import Event


def _make_state(**overrides):
    """Minimal WorldState for testing."""
    from tavern.world.state import WorldState
    from tavern.world.models import Character, Location

    defaults = {
        "player_id": "player",
        "characters": {
            "player": Character(
                id="player", name="冒险者", location_id="tavern_hall",
                traits=[], stats={"hp": 100}, inventory=(),
            ),
        },
        "locations": {
            "tavern_hall": Location(
                id="tavern_hall", name="酒馆大厅", description="大厅",
                atmosphere="warm", exits={}, items=(), npcs=(),
            ),
        },
        "timeline": (),
    }
    defaults.update(overrides)
    return WorldState(**defaults)


def test_classified_memory_build_context_returns_memory_context():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    ctx = mem.build_context(actor="player", state=state)
    assert isinstance(ctx, MemoryContext)
    assert isinstance(ctx.recent_events, str)
    assert isinstance(ctx.relationship_summary, str)
    assert isinstance(ctx.active_skills_text, str)


def test_classified_memory_add_and_retrieve():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    entry = MemoryEntry(
        id="m1", memory_type=MemoryType.LORE,
        content="格林透露了秘密", importance=8,
        created_turn=1, last_relevant_turn=1,
    )
    mem.add_memory(entry)
    ctx = mem.build_context(actor="player", state=state)
    assert "格林透露了秘密" in ctx.active_skills_text


def test_classified_memory_discovery_in_recent_events():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    entry = MemoryEntry(
        id="m2", memory_type=MemoryType.DISCOVERY,
        content="桌下什么也没有", importance=2,
        created_turn=1, last_relevant_turn=1,
    )
    mem.add_memory(entry)
    ctx = mem.build_context(actor="player", state=state)
    assert "桌下什么也没有" in ctx.recent_events


def test_classified_memory_quest_in_recent_events():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    entry = MemoryEntry(
        id="m3", memory_type=MemoryType.QUEST,
        content="地窖任务已开始", importance=7,
        created_turn=1, last_relevant_turn=1,
    )
    mem.add_memory(entry)
    ctx = mem.build_context(actor="player", state=state)
    assert "地窖任务" in ctx.recent_events


def test_classified_memory_relationship_in_summary():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    entry = MemoryEntry(
        id="m4", memory_type=MemoryType.RELATIONSHIP,
        content="格林信任度+15", importance=6,
        created_turn=1, last_relevant_turn=1,
    )
    mem.add_memory(entry)
    ctx = mem.build_context(actor="player", state=state)
    assert "格林信任度" in ctx.relationship_summary


def test_decay_lore_slower_than_discovery():
    state = _make_state(turn=100)
    mem = ClassifiedMemorySystem(state=state)

    lore = MemoryEntry(
        id="m_lore", memory_type=MemoryType.LORE,
        content="永久知识", importance=5,
        created_turn=1, last_relevant_turn=1,
    )
    disc = MemoryEntry(
        id="m_disc", memory_type=MemoryType.DISCOVERY,
        content="临时发现", importance=5,
        created_turn=1, last_relevant_turn=1,
    )
    lore_score = mem._recency_score(lore, 100)
    disc_score = mem._recency_score(disc, 100)
    assert lore_score > disc_score


def test_budget_truncation():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state, budget=MemoryBudget(discovery=20))
    # Add many discovery entries that exceed budget
    for i in range(20):
        mem.add_memory(MemoryEntry(
            id=f"d{i}", memory_type=MemoryType.DISCOVERY,
            content=f"发现{i}：" + "x" * 50, importance=2,
            created_turn=i, last_relevant_turn=i,
        ))
    ctx = mem.build_context(actor="player", state=state)
    # Should be truncated to fit within budget
    assert len(ctx.recent_events) < 2000


def test_get_player_relationships():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    rels = mem.get_player_relationships("player")
    assert isinstance(rels, list)


def test_apply_diff_updates_relationships():
    from tavern.world.state import StateDiff
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    diff = StateDiff(
        relationship_changes=(
            {"src": "player", "tgt": "bartender_grim", "delta": 10},
        ),
    )
    mem.apply_diff(diff, state)
    rels = mem.get_player_relationships("player")
    values = [r.value for r in rels if r.tgt == "bartender_grim"]
    assert values == [10]


def test_sync_to_state():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    new_state = mem.sync_to_state(state)
    assert isinstance(new_state.relationships_snapshot, dict)


def test_timeline_property():
    events = (
        Event(id="e1", type="test", description="事件1", actor="player", turn=1),
    )
    state = _make_state(timeline=events)
    mem = ClassifiedMemorySystem(state=state)
    assert mem.timeline.has("e1")


def test_relationship_graph_property():
    state = _make_state()
    mem = ClassifiedMemorySystem(state=state)
    assert mem.relationship_graph is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_classified_memory.py::test_classified_memory_build_context_returns_memory_context -v`
Expected: FAIL — `ImportError: cannot import name 'ClassifiedMemorySystem'`

- [ ] **Step 3: Implement ClassifiedMemorySystem**

In `src/tavern/world/memory.py`, keep the existing `MemorySystem` class (rename it to `_LegacyMemorySystem` or keep it) and add `ClassifiedMemorySystem`. Then alias `MemorySystem = ClassifiedMemorySystem` at the end for backward compatibility.

The key changes:
- `ClassifiedMemorySystem.__init__` takes same params as old `MemorySystem`
- Adds `_classified: dict[MemoryType, list[MemoryEntry]]` storage
- `add_memory(entry)` method for external callers
- `build_context()` builds MemoryContext using classified entries with decay scoring
- Preserves `apply_diff()`, `get_player_relationships()`, `sync_to_state()`, `rebuild()`
- Exposes `timeline` and `relationship_graph` as public properties (instead of `_timeline`/`_relationship_graph`)

```python
_DECAY_RATE: dict[MemoryType, float] = {
    MemoryType.LORE: 0.01,
    MemoryType.QUEST: 0.05,
    MemoryType.RELATIONSHIP: 0.08,
    MemoryType.DISCOVERY: 0.2,
}


class ClassifiedMemorySystem:
    def __init__(
        self,
        state: WorldState,
        skills_dir: Path | None = None,
        budget: MemoryBudget | None = None,
    ) -> None:
        from tavern.world.skills import SkillManager

        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            logger.warning("ClassifiedMemorySystem: failed to restore RelationshipGraph")
            self._relationship_graph = RelationshipGraph()
        self._skill_manager = SkillManager()
        if skills_dir is not None:
            self._skill_manager.load_skills(skills_dir)
        self._budget = budget or MemoryBudget()
        self._classified: dict[MemoryType, list[MemoryEntry]] = {
            t: [] for t in MemoryType
        }

    @property
    def timeline(self) -> EventTimeline:
        return self._timeline

    @property
    def relationship_graph(self) -> RelationshipGraph:
        return self._relationship_graph

    def add_memory(self, entry: MemoryEntry) -> None:
        self._classified[entry.memory_type].append(entry)

    def apply_diff(self, diff: StateDiff, new_state: WorldState) -> None:
        for change in diff.relationship_changes:
            if isinstance(change, dict):
                delta = RelationshipDelta(
                    src=change["src"], tgt=change["tgt"], delta=change["delta"],
                )
            else:
                delta = change
            self._relationship_graph.update(delta)
        self._timeline = EventTimeline(new_state.timeline)

    def build_context(
        self,
        actor: str,
        state: WorldState,
        max_tokens: int = 2000,
    ) -> MemoryContext:
        current_turn = state.turn

        # Collect classified memory sections
        sections: dict[MemoryType, str] = {}
        for mem_type in MemoryType:
            entries = self._classified[mem_type]
            scored = sorted(
                entries,
                key=lambda e: e.importance * self._recency_score(e, current_turn),
                reverse=True,
            )
            budget = getattr(self._budget, mem_type.value)
            sections[mem_type] = self._truncate_to_budget(scored, budget)

        # Relationship summary from graph (always include)
        rel_from_graph = self._relationship_graph.describe_for_prompt(actor)
        rel_from_classified = sections.get(MemoryType.RELATIONSHIP, "")
        relationship_summary = rel_from_graph
        if rel_from_classified:
            relationship_summary += "\n" + rel_from_classified

        # Recent events from timeline + classified QUEST/DISCOVERY
        timeline_summary = self._timeline.summarize()
        quest_text = sections.get(MemoryType.QUEST, "")
        discovery_text = sections.get(MemoryType.DISCOVERY, "")
        recent_parts = [p for p in (timeline_summary, quest_text, discovery_text) if p]
        recent_events = "\n".join(recent_parts)

        # Active skills text from SkillManager + classified LORE
        max_chars = max(100, max_tokens * 3 // 4)
        active_skills = self._skill_manager.get_active_skills(
            actor, state, self._timeline, self._relationship_graph,
        )
        skills_text = self._skill_manager.inject_to_prompt(
            active_skills, max_chars=max_chars,
        )
        lore_text = sections.get(MemoryType.LORE, "")
        active_skills_text = skills_text
        if lore_text:
            active_skills_text += "\n" + lore_text if active_skills_text else lore_text

        return MemoryContext(
            recent_events=recent_events,
            relationship_summary=relationship_summary,
            active_skills_text=active_skills_text,
        )

    def get_player_relationships(self, player_id: str = "player") -> list[Relationship]:
        return self._relationship_graph.get_all_for(player_id)

    def sync_to_state(self, state: WorldState) -> WorldState:
        snapshot = self._relationship_graph.to_snapshot()
        return state.model_copy(update={"relationships_snapshot": snapshot})

    def rebuild(self, state: WorldState) -> None:
        self._timeline = EventTimeline(state.timeline)
        try:
            snapshot = dict(state.relationships_snapshot) if state.relationships_snapshot else None
            self._relationship_graph = RelationshipGraph(snapshot=snapshot)
        except Exception:
            self._relationship_graph = RelationshipGraph()
        self._classified = {t: [] for t in MemoryType}

    def _recency_score(self, entry: MemoryEntry, current_turn: int) -> float:
        age = current_turn - entry.last_relevant_turn
        decay = _DECAY_RATE[entry.memory_type]
        return 1.0 / (1.0 + age * decay)

    @staticmethod
    def _truncate_to_budget(entries: list[MemoryEntry], budget_chars: int) -> str:
        parts: list[str] = []
        total = 0
        for entry in entries:
            if total + len(entry.content) > budget_chars:
                break
            parts.append(entry.content)
            total += len(entry.content)
        return "\n".join(parts)


# Backward compatibility alias
MemorySystem = ClassifiedMemorySystem
```

Delete the old `MemorySystem` class (lines 150-201).

- [ ] **Step 4: Update exploring.py private attribute access**

In `src/tavern/engine/modes/exploring.py`, lines 97-98 access `context.memory._timeline` and `context.memory._relationship_graph`. Change to:

```python
            story_results = context.story_engine.check(
                state,
                "passive",
                context.memory.timeline if hasattr(context.memory, "timeline") else (),
                context.memory.relationship_graph if hasattr(context.memory, "relationship_graph") else {},
            ) or []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/world/test_classified_memory.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed (existing tests should work because `MemorySystem = ClassifiedMemorySystem` alias)

- [ ] **Step 7: Commit**

```bash
git add src/tavern/world/memory.py src/tavern/engine/modes/exploring.py tests/world/test_classified_memory.py
git commit -m "feat(§9): implement ClassifiedMemorySystem with type-based decay and budget truncation"
```

---

### Task 6: MemoryExtractor — rule-based event → memory conversion

**Files:**
- Create: `src/tavern/world/memory_extractor.py`
- Test: `tests/world/test_memory_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/world/test_memory_extractor.py
from __future__ import annotations

import pytest

from tavern.world.memory import MemoryEntry, MemoryType
from tavern.world.memory_extractor import (
    EXTRACTION_RULES,
    MemoryExtractionRule,
    MemoryExtractor,
)
from tavern.world.models import Event


def test_dialogue_with_secret_produces_lore():
    event = Event(
        id="e1", type="dialogue_summary_bartender",
        description="格林透露了地窖的秘密",
        actor="bartender_grim", turn=5,
        data={"summary_text": "格林透露了地窖的秘密", "has_secret": True},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=5)
    assert memory is not None
    assert memory.memory_type == MemoryType.LORE
    assert memory.importance == 8
    assert "秘密" in memory.content


def test_dialogue_without_secret_produces_lower_lore():
    event = Event(
        id="e2", type="dialogue_summary_traveler",
        description="旅行者聊了些闲话",
        actor="traveler", turn=5,
        data={"summary_text": "旅行者聊了些闲话", "has_secret": False},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=5)
    assert memory is not None
    assert memory.memory_type == MemoryType.LORE
    assert memory.importance == 4


def test_quest_event_produces_quest_memory():
    event = Event(
        id="e3", type="quest_started",
        description="开始了地窖任务",
        actor="player", turn=3,
        data={"quest_id": "cellar_mystery", "status": "started"},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=3)
    assert memory is not None
    assert memory.memory_type == MemoryType.QUEST
    assert memory.importance == 7


def test_relationship_big_change_produces_high_importance():
    event = Event(
        id="e4", type="relationship_changed",
        description="信任度大幅变化",
        actor="player", turn=4,
        data={"npc_name": "格林", "delta": 15},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=4)
    assert memory is not None
    assert memory.memory_type == MemoryType.RELATIONSHIP
    assert memory.importance == 6


def test_relationship_small_change_low_importance():
    event = Event(
        id="e5", type="relationship_changed",
        description="信任度小幅变化",
        actor="player", turn=4,
        data={"npc_name": "格林", "delta": 3},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=4)
    assert memory is not None
    assert memory.importance == 3


def test_search_produces_discovery():
    event = Event(
        id="e6", type="search",
        description="桌子下面什么也没有",
        actor="player", turn=6,
        data={"description": "桌子下面什么也没有"},
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=6)
    assert memory is not None
    assert memory.memory_type == MemoryType.DISCOVERY
    assert memory.importance == 2


def test_unknown_event_returns_none():
    event = Event(
        id="e7", type="system_init",
        description="系统初始化",
        actor="system", turn=0,
    )
    extractor = MemoryExtractor(EXTRACTION_RULES)
    memory = extractor.extract(event, turn=0)
    assert memory is None


def test_extractor_empty_rules():
    event = Event(
        id="e8", type="search",
        description="test", actor="player", turn=1,
    )
    extractor = MemoryExtractor([])
    assert extractor.extract(event, turn=1) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_memory_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tavern.world.memory_extractor'`

- [ ] **Step 3: Implement MemoryExtractor**

```python
# src/tavern/world/memory_extractor.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from tavern.world.memory import MemoryEntry, MemoryType

if TYPE_CHECKING:
    from tavern.world.models import Event


@dataclass(frozen=True)
class MemoryExtractionRule:
    event_type_pattern: str
    memory_type: MemoryType
    importance_fn: Callable[[Event], int]
    content_fn: Callable[[Event], str]


class MemoryExtractor:
    def __init__(self, rules: list[MemoryExtractionRule]) -> None:
        self._rules: list[tuple[re.Pattern, MemoryExtractionRule]] = [
            (re.compile(r.event_type_pattern), r) for r in rules
        ]

    def extract(self, event: Event, turn: int) -> MemoryEntry | None:
        for pattern, rule in self._rules:
            if pattern.match(event.type):
                return MemoryEntry(
                    id=f"mem_{event.id}",
                    memory_type=rule.memory_type,
                    content=rule.content_fn(event),
                    importance=rule.importance_fn(event),
                    created_turn=turn,
                    last_relevant_turn=turn,
                )
        return None


def _dialogue_importance(e: Event) -> int:
    data = e.data if e.data else {}
    return 8 if data.get("has_secret") else 4


def _dialogue_content(e: Event) -> str:
    data = e.data if e.data else {}
    return data.get("summary_text", e.description)


def _quest_content(e: Event) -> str:
    data = e.data if e.data else {}
    quest_id = data.get("quest_id", "unknown")
    status = data.get("status", "unknown")
    return f"任务 {quest_id}: {status}"


def _relationship_importance(e: Event) -> int:
    data = e.data if e.data else {}
    return 6 if abs(data.get("delta", 0)) >= 10 else 3


def _relationship_content(e: Event) -> str:
    data = e.data if e.data else {}
    npc = data.get("npc_name", "unknown")
    delta = data.get("delta", 0)
    return f"{npc} 信任度 {delta:+d}"


def _discovery_content(e: Event) -> str:
    data = e.data if e.data else {}
    return data.get("description", e.description)


EXTRACTION_RULES: list[MemoryExtractionRule] = [
    MemoryExtractionRule(
        event_type_pattern=r"dialogue_summary_.*",
        memory_type=MemoryType.LORE,
        importance_fn=_dialogue_importance,
        content_fn=_dialogue_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"quest_.*",
        memory_type=MemoryType.QUEST,
        importance_fn=lambda e: 7,
        content_fn=_quest_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"relationship_changed",
        memory_type=MemoryType.RELATIONSHIP,
        importance_fn=_relationship_importance,
        content_fn=_relationship_content,
    ),
    MemoryExtractionRule(
        event_type_pattern=r"search|look_detail",
        memory_type=MemoryType.DISCOVERY,
        importance_fn=lambda e: 2,
        content_fn=_discovery_content,
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/world/test_memory_extractor.py -v`
Expected: PASS — all 8 tests green

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed

- [ ] **Step 6: Commit**

```bash
git add src/tavern/world/memory_extractor.py tests/world/test_memory_extractor.py
git commit -m "feat(§9): implement MemoryExtractor with rule-based event classification"
```

---

### Task 7: GameLogEntry + GameLogger

**Files:**
- Create: `src/tavern/engine/game_logger.py`
- Test: `tests/engine/test_game_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_game_logger.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tavern.engine.game_logger import GameLogEntry, GameLogger


@pytest.fixture
def log_dir(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    return d


def test_game_log_entry_frozen():
    entry = GameLogEntry(
        timestamp="2026-04-11T14:30:00",
        turn=1,
        session_id="test123",
        entry_type="player_input",
        data={"raw": "查看四周"},
    )
    assert entry.turn == 1
    with pytest.raises(AttributeError):
        entry.turn = 2


def test_logger_log_and_flush(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s1", flush_interval=999)
    entry = GameLogEntry(
        timestamp="2026-04-11T14:30:00", turn=1,
        session_id="s1", entry_type="player_input",
        data={"raw": "查看四周"},
    )
    logger.log(entry)
    assert len(logger._buffer) == 1

    logger.flush()
    assert len(logger._buffer) == 0
    assert (log_dir / "s1.jsonl").exists()

    lines = (log_dir / "s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["turn"] == 1
    assert parsed["data"]["raw"] == "查看四周"


def test_logger_multiple_entries(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s2", flush_interval=999)
    for i in range(5):
        logger.log(GameLogEntry(
            timestamp=f"2026-04-11T14:30:0{i}",
            turn=i, session_id="s2", entry_type="player_input",
            data={"raw": f"action_{i}"},
        ))
    logger.flush()
    lines = (log_dir / "s2.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5


def test_logger_read_recent(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s3", flush_interval=999)
    for i in range(10):
        logger.log(GameLogEntry(
            timestamp=f"2026-04-11T14:3{i}:00",
            turn=i, session_id="s3", entry_type="player_input",
            data={"raw": f"action_{i}"},
        ))
    logger.flush()
    recent = logger.read_recent(n=3)
    assert len(recent) == 3
    assert recent[-1].data["raw"] == "action_9"
    assert recent[0].data["raw"] == "action_7"


def test_logger_read_recent_includes_buffer(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s4", flush_interval=999)
    # Flush some entries to disk
    for i in range(3):
        logger.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s4",
            entry_type="player_input", data={"raw": f"disk_{i}"},
        ))
    logger.flush()
    # Add unflushed entry to buffer
    logger.log(GameLogEntry(
        timestamp="t3", turn=3, session_id="s4",
        entry_type="player_input", data={"raw": "buffer_3"},
    ))
    recent = logger.read_recent(n=2)
    assert len(recent) == 2
    assert recent[-1].data["raw"] == "buffer_3"


def test_logger_close_flushes(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s5", flush_interval=999)
    logger.log(GameLogEntry(
        timestamp="t0", turn=0, session_id="s5",
        entry_type="test", data={},
    ))
    logger.close()
    assert (log_dir / "s5.jsonl").exists()
    assert len(logger._buffer) == 0


def test_logger_read_recent_empty(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s6", flush_interval=999)
    recent = logger.read_recent(n=5)
    assert recent == []


def test_logger_file_rotation(log_dir):
    logger = GameLogger(log_dir=log_dir, session_id="s7", flush_interval=999)
    logger.MAX_FILE_SIZE = 100  # tiny limit for testing
    # Write enough to trigger rotation
    for i in range(20):
        logger.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s7",
            entry_type="player_input", data={"raw": "x" * 50},
        ))
        logger.flush()
    # Should have rotated files
    files = list(log_dir.glob("s7*.jsonl"))
    assert len(files) >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_game_logger.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GameLogger**

```python
# src/tavern/engine/game_logger.py
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameLogEntry:
    timestamp: str
    turn: int
    session_id: str
    entry_type: str
    data: dict


class GameLogger:
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    def __init__(
        self,
        log_dir: Path,
        session_id: str,
        flush_interval: float = 2.0,
    ) -> None:
        self._log_dir = log_dir
        self._session_id = session_id
        self._path = log_dir / f"{session_id}.jsonl"
        self._buffer: list[GameLogEntry] = []
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None

    def log(self, entry: GameLogEntry) -> None:
        self._buffer.append(entry)
        try:
            loop = asyncio.get_running_loop()
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = loop.create_task(self._flush_loop())
        except RuntimeError:
            pass  # No running event loop — flush manually via close()

    async def _flush_loop(self) -> None:
        await asyncio.sleep(self._flush_interval)
        self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and self._path.stat().st_size > self.MAX_FILE_SIZE:
            rotated = self._path.with_suffix(f".{int(time.time())}.jsonl")
            self._path.rename(rotated)
        entries = self._buffer.copy()
        self._buffer.clear()
        lines = [
            json.dumps(asdict(e), ensure_ascii=False) + "\n"
            for e in entries
        ]
        with open(self._path, "a", encoding="utf-8") as f:
            f.writelines(lines)

    def read_recent(self, n: int = 50) -> list[GameLogEntry]:
        result = list(self._buffer[-n:])
        remaining = n - len(result)
        if remaining <= 0:
            return result[-n:]
        if not self._path.exists():
            return result
        chunk_size = 8192
        with open(self._path, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            tail_lines: list[str] = []
            while pos > 0 and len(tail_lines) < remaining + 1:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size).decode("utf-8")
                tail_lines = chunk.splitlines() + tail_lines
        disk_entries: list[GameLogEntry] = []
        for line in tail_lines:
            line = line.strip()
            if line:
                try:
                    disk_entries.append(GameLogEntry(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue
        disk_recent = disk_entries[-remaining:]
        return disk_recent + result

    def close(self) -> None:
        self.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_game_logger.py -v`
Expected: PASS — all tests green

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/game_logger.py tests/engine/test_game_logger.py
git commit -m "feat(§8): implement GameLogEntry and GameLogger with async JSONL append"
```

---

### Task 8: /journal command + bootstrap integration

**Files:**
- Modify: `src/tavern/engine/fsm.py` (add `logger` field to ModeContext)
- Modify: `src/tavern/engine/command_defs.py` (add cmd_journal)
- Modify: `src/tavern/cli/bootstrap.py` (accept and wire logger)
- Modify: `src/tavern/cli/app.py` (create GameLogger, pass to bootstrap, close in finally)
- Test: `tests/engine/test_command_defs.py` (add test for cmd_journal)

- [ ] **Step 1: Write failing test for cmd_journal**

Append to an existing or new test file:

```python
# tests/engine/test_journal_command.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.command_defs import cmd_journal
from tavern.engine.game_logger import GameLogEntry, GameLogger


@pytest.fixture
def mock_context(tmp_path):
    from tavern.engine.fsm import ModeContext

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    game_logger = GameLogger(log_dir=log_dir, session_id="test", flush_interval=999)
    for i in range(5):
        game_logger.log(GameLogEntry(
            timestamp=f"2026-04-11T14:3{i}:00", turn=i,
            session_id="test", entry_type="player_input",
            data={"raw": f"动作{i}", "parsed_action": "LOOK"},
        ))
    game_logger.flush()

    renderer = MagicMock()
    renderer.console = MagicMock()
    renderer.console.print = MagicMock()

    ctx = MagicMock(spec=ModeContext)
    ctx.renderer = renderer
    ctx.logger = game_logger
    return ctx


@pytest.mark.asyncio
async def test_cmd_journal_renders_entries(mock_context):
    await cmd_journal("", mock_context)
    mock_context.renderer.console.print.assert_called()


@pytest.mark.asyncio
async def test_cmd_journal_no_logger():
    ctx = MagicMock()
    ctx.logger = None
    ctx.renderer = MagicMock()
    ctx.renderer.console = MagicMock()
    await cmd_journal("", ctx)
    ctx.renderer.console.print.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_journal_command.py -v`
Expected: FAIL — `ImportError: cannot import name 'cmd_journal'`

- [ ] **Step 3: Add logger field to ModeContext**

In `src/tavern/engine/fsm.py`, add `logger` field to `ModeContext` dataclass (line 74):

```python
@dataclass
class ModeContext:
    state_manager: ReactiveStateManager
    renderer: Any
    dialogue_manager: Any
    narrator: Any
    memory: Any
    persistence: Any
    story_engine: Any
    command_registry: CommandRegistry
    action_registry: ActionRegistry | None
    intent_parser: Any
    logger: Any
    game_logger: Any = None  # GameLogger instance
```

- [ ] **Step 4: Implement cmd_journal**

Add to `src/tavern/engine/command_defs.py`:

```python
async def cmd_journal(args: str, ctx: ModeContext) -> None:
    if ctx.game_logger is None:
        ctx.renderer.console.print("\n[dim]冒险日志尚未启用。[/]\n")
        return
    entries = ctx.game_logger.read_recent(n=20)
    player_entries = [e for e in entries if e.entry_type == "player_input"]
    if not player_entries:
        ctx.renderer.console.print("\n[dim]冒险日志为空。[/]\n")
        return
    ctx.renderer.console.print("\n[bold]📜 冒险日志[/]")
    for entry in player_entries:
        raw = entry.data.get("raw", "?")
        ctx.renderer.console.print(f"  [dim]回合{entry.turn}[/] {raw}")
    ctx.renderer.console.print()
```

Register in `register_all_commands()`:

```python
    registry.register(GameCommand(
        name="/journal", aliases=("/j", "/日志"), description="查看冒险日志",
        available_in=_ALL_MODES, execute=cmd_journal,
    ))
```

- [ ] **Step 5: Update bootstrap to accept game_logger**

In `src/tavern/cli/bootstrap.py`, add `game_logger` param:

```python
def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    intent_parser: Any,
    logger: Any,
    game_logger: Any = None,
) -> GameLoop:
```

Pass it to ModeContext:

```python
    context = ModeContext(
        ...
        logger=logger,
        game_logger=game_logger,
    )
```

- [ ] **Step 6: Update app.py to create GameLogger**

In `src/tavern/cli/app.py`:
1. Import `GameLogger` and `uuid`
2. In `__init__`, after saves_dir setup, create logger:

```python
        import uuid
        from tavern.engine.game_logger import GameLogger
        log_dir = Path(game_config.get("log_dir", "logs"))
        self._game_logger = GameLogger(
            log_dir=log_dir,
            session_id=str(uuid.uuid4())[:8],
        )
```

3. Pass to bootstrap:

```python
        self._game_loop = bootstrap(
            ...
            game_logger=self._game_logger,
        )
```

4. Update `run()` to close logger:

```python
    async def run(self) -> None:
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
        self._renderer.render_status_bar(self.state)
        try:
            await self._game_loop.run()
        finally:
            self._game_logger.close()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/engine/test_journal_command.py -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed

- [ ] **Step 9: Commit**

```bash
git add src/tavern/engine/fsm.py src/tavern/engine/command_defs.py src/tavern/cli/bootstrap.py src/tavern/cli/app.py tests/engine/test_journal_command.py
git commit -m "feat(§8): add /journal command, wire GameLogger into bootstrap and GameApp"
```

---

### Task 9: SceneContext + SceneContextCache

**Files:**
- Create: `src/tavern/narrator/scene_cache.py`
- Test: `tests/narrator/test_scene_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/narrator/test_scene_cache.py
from __future__ import annotations

import pytest

from tavern.engine.seeded_rng import AmbienceDetails
from tavern.narrator.scene_cache import SceneContext, SceneContextCache


@pytest.fixture
def sample_context():
    return SceneContext(
        location_description="酒馆大厅",
        npcs_present=("格林",),
        items_visible=("旧告示",),
        exits_available=("吧台", "走廊"),
        atmosphere="warm",
        ambience=AmbienceDetails(
            weather="晴朗", crowd_level="热闹",
            background_sound="炉火噼啪作响", smell="麦酒的醇厚气息",
        ),
    )


def test_scene_context_frozen(sample_context):
    with pytest.raises(AttributeError):
        sample_context.atmosphere = "cold"


def test_cache_put_and_get(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    result = cache.get("tavern_hall", 1)
    assert result is sample_context


def test_cache_miss_returns_none():
    cache = SceneContextCache()
    assert cache.get("tavern_hall", 1) is None


def test_cache_version_mismatch(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    assert cache.get("tavern_hall", 2) is None


def test_cache_put_clears_old_versions(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("tavern_hall", 3, sample_context)
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("tavern_hall", 3) is sample_context


def test_cache_invalidate_specific(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("bar_area", 1, sample_context)
    cache.invalidate("tavern_hall")
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("bar_area", 1) is sample_context


def test_cache_invalidate_all(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("bar_area", 1, sample_context)
    cache.invalidate()
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("bar_area", 1) is None


def test_cache_lru_eviction(sample_context):
    cache = SceneContextCache()
    cache.MAX_ENTRIES = 3
    cache.put("loc_a", 1, sample_context)
    cache.put("loc_b", 1, sample_context)
    cache.put("loc_c", 1, sample_context)
    # Access loc_a to make it recent
    cache.get("loc_a", 1)
    # Add loc_d — should evict loc_b (least recently used)
    cache.put("loc_d", 1, sample_context)
    assert cache.get("loc_a", 1) is sample_context
    assert cache.get("loc_b", 1) is None
    assert cache.get("loc_c", 1) is sample_context
    assert cache.get("loc_d", 1) is sample_context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/narrator/test_scene_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SceneContext + SceneContextCache**

```python
# src/tavern/narrator/scene_cache.py
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.seeded_rng import AmbienceDetails


@dataclass(frozen=True)
class SceneContext:
    location_description: str
    npcs_present: tuple[str, ...]
    items_visible: tuple[str, ...]
    exits_available: tuple[str, ...]
    atmosphere: str
    ambience: AmbienceDetails


class SceneContextCache:
    MAX_ENTRIES = 100

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple[str, int], SceneContext] = OrderedDict()

    def get(self, location_id: str, state_version: int) -> SceneContext | None:
        key = (location_id, state_version)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(
        self, location_id: str, state_version: int, context: SceneContext,
    ) -> None:
        key = (location_id, state_version)
        stale_keys = [
            k for k in self._cache
            if k[0] == location_id and k[1] < state_version
        ]
        for k in stale_keys:
            del self._cache[k]
        self._cache[key] = context
        self._cache.move_to_end(key)
        while len(self._cache) > self.MAX_ENTRIES:
            self._cache.popitem(last=False)

    def invalidate(self, location_id: str | None = None) -> None:
        if location_id is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k[0] == location_id]
            for k in keys_to_remove:
                del self._cache[k]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/narrator/test_scene_cache.py -v`
Expected: PASS — all tests green

- [ ] **Step 5: Commit**

```bash
git add src/tavern/narrator/scene_cache.py tests/narrator/__init__.py tests/narrator/test_scene_cache.py
git commit -m "feat(§10): implement SceneContext and SceneContextCache with LRU eviction"
```

---

### Task 10: CachedPromptBuilder + Narrator integration

**Files:**
- Create: `src/tavern/narrator/cached_builder.py`
- Modify: `src/tavern/narrator/narrator.py` (use CachedPromptBuilder in _build_context)
- Modify: `src/tavern/cli/bootstrap.py` (create and wire cache + builder)
- Test: `tests/narrator/test_cached_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/narrator/test_cached_builder.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tavern.engine.seeded_rng import AmbienceDetails
from tavern.narrator.cached_builder import CachedPromptBuilder
from tavern.narrator.scene_cache import SceneContext, SceneContextCache


def _make_state(location_id="tavern_hall", turn=1, version=1):
    from tavern.world.models import Character, Location
    from tavern.world.state import WorldState

    state = WorldState(
        turn=turn,
        player_id="player",
        locations={
            location_id: Location(
                id=location_id, name="酒馆大厅",
                description="YAML描述", atmosphere="warm",
                exits={}, items=("old_notice",), npcs=("bartender_grim",),
            ),
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                location_id=location_id, traits=[], stats={}, inventory=(),
            ),
            "bartender_grim": Character(
                id="bartender_grim", name="格林",
                location_id=location_id, traits=[], stats={}, inventory=(),
            ),
        },
        items={
            "old_notice": MagicMock(name="旧告示"),
        },
    )
    return state


@pytest.fixture
def builder():
    content_loader = MagicMock()
    content_loader.resolve.return_value = None  # fallback to YAML

    cache = SceneContextCache()

    state_manager = MagicMock()
    state_manager.version = 1

    return CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )


def test_build_scene_context_returns_scene_context(builder):
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert isinstance(ctx, SceneContext)
    assert ctx.atmosphere == "warm"
    assert "格林" in ctx.npcs_present


def test_build_scene_context_cache_hit(builder):
    state = _make_state()
    ctx1 = builder.build_scene_context(state)
    ctx2 = builder.build_scene_context(state)
    assert ctx1 is ctx2  # Same object from cache


def test_build_scene_context_uses_content_loader():
    content_loader = MagicMock()
    content_loader.resolve.return_value = "Markdown描述内容"
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1

    builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert ctx.location_description == "Markdown描述内容"


def test_build_scene_context_fallback_to_yaml():
    content_loader = MagicMock()
    content_loader.resolve.return_value = None
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1

    builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert ctx.location_description == "YAML描述"


def test_build_scene_context_includes_ambience(builder):
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert isinstance(ctx.ambience, AmbienceDetails)
    assert ctx.ambience.weather  # non-empty string
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/narrator/test_cached_builder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CachedPromptBuilder**

```python
# src/tavern/narrator/cached_builder.py
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tavern.engine.seeded_rng import generate_ambience
from tavern.narrator.scene_cache import SceneContext, SceneContextCache

if TYPE_CHECKING:
    from tavern.content.loader import ContentLoader
    from tavern.world.state import WorldState


class CachedPromptBuilder:
    def __init__(
        self,
        content_loader: ContentLoader | None,
        cache: SceneContextCache,
        state_manager: Any,
    ) -> None:
        self._content = content_loader
        self._cache = cache
        self._state_manager = state_manager

    def build_scene_context(self, state: WorldState) -> SceneContext:
        loc_id = state.player_location
        version = self._state_manager.version

        cached = self._cache.get(loc_id, version)
        if cached is not None:
            return cached

        location = state.locations[loc_id]

        # Try ContentLoader first, fallback to YAML description
        description = None
        if self._content is not None:
            description = self._content.resolve(loc_id)
        if description is None:
            description = location.description

        npcs_present = tuple(
            state.characters[npc_id].name
            for npc_id in location.npcs
            if npc_id in state.characters
        )
        items_visible = tuple(
            state.items[item_id].name
            for item_id in location.items
            if item_id in state.items
        )
        exits_available = tuple(location.exits.keys())
        ambience = generate_ambience(loc_id, state.turn)

        context = SceneContext(
            location_description=description,
            npcs_present=npcs_present,
            items_visible=items_visible,
            exits_available=exits_available,
            atmosphere=location.atmosphere,
            ambience=ambience,
        )
        self._cache.put(loc_id, version, context)
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/narrator/test_cached_builder.py -v`
Expected: PASS

- [ ] **Step 5: Update Narrator to optionally use CachedPromptBuilder**

In `src/tavern/narrator/narrator.py`, modify the constructor and `_build_context`:

```python
class Narrator:
    def __init__(
        self,
        llm_service: LLMService,
        cached_builder: Any = None,
    ) -> None:
        self._llm = llm_service
        self._cached_builder = cached_builder

    def _build_context(self, result: ActionResult, state: WorldState) -> NarrativeContext:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        # Use cached scene context if available
        if self._cached_builder is not None:
            scene = self._cached_builder.build_scene_context(state)
            loc_desc = scene.location_description
        else:
            loc_desc = location.description

        target_name: str | None = None
        if result.target:
            if result.target in state.characters:
                target_name = state.characters[result.target].name
            elif result.target in state.items:
                target_name = state.items[result.target].name
            else:
                target_name = result.target

        return NarrativeContext(
            action_type=result.action.value,
            action_message=result.message,
            location_name=location.name,
            location_desc=loc_desc,
            player_name=player.name,
            target=target_name,
        )
```

Also fix the bug on line 102: `memory_ctx.relationships` → `memory_ctx.relationship_summary`.

- [ ] **Step 6: Update bootstrap to create and wire cache + builder**

In `src/tavern/cli/bootstrap.py`:

```python
from tavern.narrator.scene_cache import SceneContextCache
from tavern.narrator.cached_builder import CachedPromptBuilder


def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    intent_parser: Any,
    logger: Any,
    game_logger: Any = None,
    content_loader: Any = None,
) -> GameLoop:
    ...

    # Create scene cache and cached builder
    scene_cache = SceneContextCache()
    cached_builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=scene_cache,
        state_manager=state_manager,
    )
    narrator._cached_builder = cached_builder

    ...
```

Note: Setting `narrator._cached_builder` directly is not ideal. Better: if Narrator already has the param in its constructor, pass `cached_builder` when creating Narrator in `app.py`. But since `app.py` creates Narrator before bootstrap, and bootstrap creates the cache, we set it post-construction. The Narrator constructor already accepts `cached_builder=None` from step 5.

Alternative: Pass `cached_builder` in app.py after bootstrap returns. The simplest approach for now is to set it in bootstrap since that's the assembly point.

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 625+ passed

- [ ] **Step 8: Commit**

```bash
git add src/tavern/narrator/cached_builder.py src/tavern/narrator/narrator.py src/tavern/narrator/scene_cache.py src/tavern/cli/bootstrap.py tests/narrator/test_cached_builder.py
git commit -m "feat(§10): implement CachedPromptBuilder, integrate with Narrator and bootstrap"
```

---

### Task 11: Integration verification — full test run + manual smoke test

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (625+ original + ~50 new)

- [ ] **Step 2: Run coverage check on new modules**

Run: `pytest tests/content/ tests/world/test_classified_memory.py tests/world/test_memory_extractor.py tests/engine/test_game_logger.py tests/engine/test_journal_command.py tests/narrator/test_scene_cache.py tests/narrator/test_cached_builder.py tests/engine/test_story_conditions_str.py --cov=tavern.content --cov=tavern.world.memory --cov=tavern.world.memory_extractor --cov=tavern.engine.game_logger --cov=tavern.narrator.scene_cache --cov=tavern.narrator.cached_builder --cov-report=term-missing -v`

Expected: 90%+ coverage on new modules

- [ ] **Step 3: Verify no import errors**

Run: `python -c "from tavern.content.loader import ContentLoader; from tavern.world.memory import ClassifiedMemorySystem, MemorySystem; from tavern.engine.game_logger import GameLogger; from tavern.narrator.scene_cache import SceneContextCache; from tavern.narrator.cached_builder import CachedPromptBuilder; print('All imports OK')"`

Expected: "All imports OK"

- [ ] **Step 4: Commit any fixes**

If any tests failed, fix and commit.
