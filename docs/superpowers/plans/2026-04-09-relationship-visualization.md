# Relationship Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the `status` command from bare stats output to a rich panel with attributes, relationship arrows, and quest progress.

**Architecture:** Add `get_player_relationships()` convenience method to `MemorySystem`, pass `list[Relationship]` into a rewritten `render_status` on `Renderer`. Renderer stays decoupled from MemorySystem — it only receives plain data types.

**Tech Stack:** Python 3.14, Rich (Panel, markup), pytest

**Spec:** `docs/superpowers/specs/2026-04-09-relationship-visualization-design.md`

---

### Task 1: `MemorySystem.get_player_relationships()` Convenience Method

**Files:**
- Modify: `src/tavern/world/memory.py:129-178`
- Test: `tests/world/test_memory.py`

**Context:**
- `MemorySystem` (line 129) holds `self._relationship_graph: RelationshipGraph`.
- `RelationshipGraph.get_all_for(char_id) -> list[Relationship]` (memory.py:100-104) returns outgoing edges.
- `MemorySystem` doesn't currently expose `_relationship_graph` — we need a thin wrapper.
- Test file uses fixtures from `conftest.py` (`sample_world_state`).

- [ ] **Step 1: Write failing test**

```python
# Append to tests/world/test_memory.py

from tavern.world.memory import MemorySystem, Relationship


class TestGetPlayerRelationships:
    def test_returns_relationships_for_player(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="traveler", delta=25))
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="bartender_grim", delta=-10))

        rels = memory.get_player_relationships()

        assert len(rels) == 2
        ids = {r.tgt for r in rels}
        assert ids == {"traveler", "bartender_grim"}

    def test_returns_empty_list_when_no_relationships(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)

        rels = memory.get_player_relationships()

        assert rels == []

    def test_returns_relationship_type(self, sample_world_state):
        memory = MemorySystem(state=sample_world_state)
        memory._relationship_graph.update(RelationshipDelta(src="player", tgt="traveler", delta=40))

        rels = memory.get_player_relationships()

        assert len(rels) == 1
        assert isinstance(rels[0], Relationship)
        assert rels[0].src == "player"
        assert rels[0].tgt == "traveler"
        assert rels[0].value == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_memory.py::TestGetPlayerRelationships -v`
Expected: FAIL with `AttributeError: 'MemorySystem' object has no attribute 'get_player_relationships'`

- [ ] **Step 3: Implement `get_player_relationships`**

In `src/tavern/world/memory.py`, add at the end of the `MemorySystem` class (after `sync_to_state`, line 177):

```python
    def get_player_relationships(self) -> list[Relationship]:
        return self._relationship_graph.get_all_for("player")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/world/test_memory.py::TestGetPlayerRelationships -v`
Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/world/memory.py tests/world/test_memory.py
git commit -m "feat: add MemorySystem.get_player_relationships convenience method"
```

---

### Task 2: Rewrite `render_status` with Relationships and Quests

**Files:**
- Modify: `src/tavern/cli/renderer.py:1-14` (imports), `72-77` (render_status)
- Test: `tests/cli/test_renderer.py`

**Context:**
- Current `render_status` (line 72) takes only `WorldState` and prints bare stats.
- New signature: `render_status(self, state: WorldState, relationships: list[Relationship]) -> None`.
- `Relationship` (from `tavern.world.memory`) has `src: str`, `tgt: str`, `value: int`.
- `state.characters` is `dict[str, Character]` where `Character.name` is the display name.
- `state.quests` is `dict[str, dict]` where each quest dict has a `"status"` key.
- `state.characters[state.player_id]` gives the player `Character`.
- Test fixture `sample_world_state` has player with stats `{"hp": 100, "gold": 10}` and empty quests.

- [ ] **Step 1: Write failing tests for render_status**

```python
# Append to tests/cli/test_renderer.py, inside class TestRenderer

    def test_render_status_shows_stats_compact(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "hp" in output
        assert "100" in output
        assert "gold" in output

    def test_render_status_shows_relationships(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        rels = [
            Relationship(src="player", tgt="traveler", value=25),
            Relationship(src="player", tgt="bartender_grim", value=-15),
        ]
        renderer.render_status(sample_world_state, rels)
        output = console.file.getvalue()
        assert "友好" in output
        assert "敌对" in output

    def test_render_status_shows_npc_names(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        rels = [Relationship(src="player", tgt="traveler", value=10)]
        renderer.render_status(sample_world_state, rels)
        output = console.file.getvalue()
        # sample_world_state has Character(id="traveler", name="旅行者")
        assert "旅行者" in output

    def test_render_status_empty_relationships(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "尚无人际关系记录" in output

    def test_render_status_shows_quests(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        from tavern.world.state import StateDiff
        diff = StateDiff(
            quest_updates={"cellar_mystery": {"status": "active"}, "traveler_quest": {"status": "completed"}},
            turn_increment=0,
        )
        state_with_quests = sample_world_state.apply(diff)
        renderer.render_status(state_with_quests, [])
        output = console.file.getvalue()
        assert "cellar_mystery" in output
        assert "active" in output
        assert "completed" in output

    def test_render_status_empty_quests(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "暂无任务记录" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_renderer.py::TestRenderer::test_render_status_shows_stats_compact tests/cli/test_renderer.py::TestRenderer::test_render_status_shows_relationships tests/cli/test_renderer.py::TestRenderer::test_render_status_shows_npc_names tests/cli/test_renderer.py::TestRenderer::test_render_status_empty_relationships tests/cli/test_renderer.py::TestRenderer::test_render_status_shows_quests tests/cli/test_renderer.py::TestRenderer::test_render_status_empty_quests -v`
Expected: FAIL with `TypeError` (unexpected argument `relationships`)

- [ ] **Step 3: Implement `render_status` and `_relationship_label`**

In `src/tavern/cli/renderer.py`, add the import at line 2 area (after existing imports):

```python
from tavern.world.memory import Relationship
```

Then replace lines 72-77 (`render_status`) with:

```python
    @staticmethod
    def _relationship_label(value: int) -> tuple[str, str]:
        if value >= 60:
            return "非常友好", "bright_green"
        if value >= 20:
            return "友好", "green"
        if value <= -60:
            return "非常敌对", "bright_red"
        if value <= -20:
            return "敌对", "red"
        return "中立", "yellow"

    def render_status(self, state: WorldState, relationships: list[Relationship]) -> None:
        player = state.characters[state.player_id]
        lines: list[str] = []

        # ── Attributes ──
        stats_line = " | ".join(f"{k} [{('green' if k == 'hp' else 'yellow')}]{v}[/]" for k, v in player.stats.items())
        lines.append(f"  属性: {stats_line}")

        # ── Relationships ──
        lines.append("")
        lines.append("  [bold]人际关系:[/]")
        if relationships:
            for rel in relationships:
                npc = state.characters.get(rel.tgt)
                name = npc.name if npc else rel.tgt
                label, color = self._relationship_label(rel.value)
                sign = f"+{rel.value}" if rel.value >= 0 else str(rel.value)
                lines.append(f"    ★ 你 ──[[{color}]{sign} {label}[/]]──▶ {name}")
        else:
            lines.append("    [dim]（尚无人际关系记录）[/]")

        # ── Quests ──
        lines.append("")
        lines.append("  [bold]任务进度:[/]")
        if state.quests:
            for quest_id, quest_data in state.quests.items():
                status = quest_data.get("status", "unknown")
                if status == "completed":
                    style = "[green]completed[/]"
                elif status == "active":
                    style = "[cyan]active[/]"
                else:
                    style = f"[yellow]{status}[/]"
                lines.append(f"    ● {quest_id} ········ {style}")
        else:
            lines.append("    [dim]（暂无任务记录）[/]")

        body = "\n".join(lines)
        self.console.print(
            Panel(
                f"[bold]{player.name}[/]\n\n{body}",
                title="📊 角色状态",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_renderer.py::TestRenderer -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer.py
git commit -m "feat: rewrite render_status with relationships, quests, and Panel layout"
```

---

### Task 3: Wire `app.py` Status Command to New Interface

**Files:**
- Modify: `src/tavern/cli/app.py:149-150`

**Context:**
- Current code: `self._renderer.render_status(self.state)` — needs to pass relationships.
- `self._memory` is a `MemorySystem` instance with new `get_player_relationships()`.
- No new test needed — this is a wiring change covered by integration in existing tests.

- [ ] **Step 1: Update status command handler**

In `src/tavern/cli/app.py`, replace line 149-150:

Old:
```python
        elif command == "status":
            self._renderer.render_status(self.state)
```

New:
```python
        elif command == "status":
            relationships = self._memory.get_player_relationships()
            self._renderer.render_status(self.state, relationships)
```

- [ ] **Step 2: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS (no regressions)

- [ ] **Step 3: Commit**

```bash
git add src/tavern/cli/app.py
git commit -m "feat: wire status command to pass relationships into render_status"
```
