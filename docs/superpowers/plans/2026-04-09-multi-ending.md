# Multi-Ending System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 mutually-exclusive endings (good/bad/neutral) to the tavern scenario, driven by story nodes with new condition types, LLM-generated ending narrative, and game loop exit on trigger.

**Architecture:** Endings are ordinary `StoryNode` entries with a `trigger_ending` effect field. Two new condition evaluators (`quest_count`, `turn_count`) enable aggregate checks. When an ending fires, the narrator generates epilogue prose via a dedicated prompt template, the renderer displays it in a styled panel, and the game loop exits.

**Tech Stack:** Python 3.14, Pydantic, PyYAML, Rich, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-09-multi-ending-design.md`

---

### Task 1: New Condition Types — `quest_count` and `turn_count`

**Files:**
- Modify: `src/tavern/engine/story_conditions.py:23-59`
- Test: `tests/engine/test_story_conditions.py`

**Context:**
- `CONDITION_REGISTRY` (line 23) maps type strings to evaluator functions.
- Each evaluator has signature `(cond: ActivationCondition, state, timeline, relationships) -> bool`.
- `ActivationCondition` fields available: `type`, `check`, `operator`, `value`, `event_id`, `source`, `target`, `attribute`.
- Operator comparison pattern exists in `src/tavern/world/skills.py:71-83` (`_eval_relationship`).
- `state.quests` is a `dict[str, dict]` where each quest has a `"status"` key.
- `state.turn` is an `int`.

- [ ] **Step 1: Write failing tests for `quest_count`**

```python
# Append to tests/engine/test_story_conditions.py

def test_quest_count_gte_met():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="quest_count", check="completed", operator=">=", value=2)
    state = MagicMock()
    state.quests = {
        "q1": {"status": "completed"},
        "q2": {"status": "completed"},
        "q3": {"status": "active"},
    }
    assert CONDITION_REGISTRY["quest_count"](cond, state, None, None) is True


def test_quest_count_gte_not_met():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="quest_count", check="completed", operator=">=", value=3)
    state = MagicMock()
    state.quests = {
        "q1": {"status": "completed"},
        "q2": {"status": "active"},
    }
    assert CONDITION_REGISTRY["quest_count"](cond, state, None, None) is False


def test_quest_count_exact_match():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="quest_count", check="completed", operator="==", value=1)
    state = MagicMock()
    state.quests = {"q1": {"status": "completed"}}
    assert CONDITION_REGISTRY["quest_count"](cond, state, None, None) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_story_conditions.py::test_quest_count_gte_met tests/engine/test_story_conditions.py::test_quest_count_gte_not_met tests/engine/test_story_conditions.py::test_quest_count_exact_match -v`
Expected: FAIL with `KeyError: 'quest_count'`

- [ ] **Step 3: Write failing tests for `turn_count`**

```python
# Append to tests/engine/test_story_conditions.py

def test_turn_count_gte_met():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="turn_count", operator=">=", value=40)
    state = MagicMock()
    state.turn = 45
    assert CONDITION_REGISTRY["turn_count"](cond, state, None, None) is True


def test_turn_count_gte_not_met():
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    cond = ActivationCondition(type="turn_count", operator=">=", value=40)
    state = MagicMock()
    state.turn = 20
    assert CONDITION_REGISTRY["turn_count"](cond, state, None, None) is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/engine/test_story_conditions.py::test_turn_count_gte_met tests/engine/test_story_conditions.py::test_turn_count_gte_not_met -v`
Expected: FAIL with `KeyError: 'turn_count'`

- [ ] **Step 5: Implement both evaluators**

Add a `_compare` helper and two evaluators at the end of `src/tavern/engine/story_conditions.py`:

```python
def _compare(actual: int, operator: str, target: int) -> bool:
    if operator == "==":
        return actual == target
    if operator == "!=":
        return actual != target
    if operator == ">":
        return actual > target
    if operator == "<":
        return actual < target
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    return False


@register_condition("quest_count")
def eval_quest_count(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    if cond.check is None or cond.operator is None or cond.value is None:
        return False
    count = sum(1 for q in state.quests.values() if q.get("status") == cond.check)
    return _compare(count, cond.operator, cond.value)


@register_condition("turn_count")
def eval_turn_count(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    if cond.operator is None or cond.value is None:
        return False
    return _compare(state.turn, cond.operator, cond.value)
```

- [ ] **Step 6: Run all condition tests**

Run: `pytest tests/engine/test_story_conditions.py -v`
Expected: all PASS (11 tests)

- [ ] **Step 7: Commit**

```bash
git add src/tavern/engine/story_conditions.py tests/engine/test_story_conditions.py
git commit -m "feat: add quest_count and turn_count condition evaluators"
```

---

### Task 2: State Model Extension — `endings_reached` and `new_endings`

**Files:**
- Modify: `src/tavern/world/state.py:12-112`
- Modify: `src/tavern/engine/rules.py:414-445`
- Test: `tests/world/test_state.py`
- Test: `tests/engine/test_rules_use.py`

**Context:**
- `StateDiff` (line 12) is a Pydantic `BaseModel` with fields like `new_events: tuple[Event, ...] = ()`.
- `WorldState.apply()` (line 58) creates a new `WorldState` by applying a diff. Tuples are concatenated: `self.timeline + diff.new_events`.
- `WorldState.freeze_mutable_fields` (line 39) converts `dict` fields to `MappingProxyType`. Tuples don't need freezing.
- `_merge_diffs` in `rules.py:414` merges two `StateDiff` instances. Tuple fields use concatenation.
- `tests/world/test_state.py` uses a `sample_world_state` fixture from conftest.
- `tests/engine/test_rules_use.py` tests `_merge_diffs` (imports `_merge_diffs` from `tavern.engine.rules`).

- [ ] **Step 1: Write failing tests for `endings_reached` apply**

```python
# Append to tests/world/test_state.py

class TestEndingsReached:
    def test_apply_new_endings_from_empty(self, sample_world_state):
        diff = StateDiff(new_endings=("good_ending",), turn_increment=0)
        new_state = sample_world_state.apply(diff)
        assert new_state.endings_reached == ("good_ending",)
        assert sample_world_state.endings_reached == ()

    def test_apply_new_endings_appends(self, sample_world_state):
        diff1 = StateDiff(new_endings=("neutral_ending",), turn_increment=0)
        state1 = sample_world_state.apply(diff1)
        diff2 = StateDiff(new_endings=("good_ending",), turn_increment=0)
        state2 = state1.apply(diff2)
        assert state2.endings_reached == ("neutral_ending", "good_ending")

    def test_apply_no_new_endings_unchanged(self, sample_world_state):
        diff = StateDiff(turn_increment=1)
        new_state = sample_world_state.apply(diff)
        assert new_state.endings_reached == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/world/test_state.py::TestEndingsReached -v`
Expected: FAIL with `AttributeError` or `ValidationError` (fields don't exist yet)

- [ ] **Step 3: Write failing test for `_merge_diffs` new_endings**

```python
# Append to tests/engine/test_rules_use.py

def test_merge_diffs_new_endings():
    from tavern.engine.rules import _merge_diffs
    from tavern.world.state import StateDiff

    a = StateDiff(new_endings=("good_ending",), turn_increment=0)
    b = StateDiff(new_endings=("bad_ending",), turn_increment=0)
    merged = _merge_diffs(a, b)
    assert merged.new_endings == ("good_ending", "bad_ending")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/engine/test_rules_use.py::test_merge_diffs_new_endings -v`
Expected: FAIL

- [ ] **Step 5: Add `new_endings` field to `StateDiff`**

In `src/tavern/world/state.py`, add after line 21 (`character_stat_deltas`):

```python
    new_endings: tuple[str, ...] = ()
```

- [ ] **Step 6: Add `endings_reached` field to `WorldState`**

In `src/tavern/world/state.py`, add after line 36 (`timeline`):

```python
    endings_reached: tuple[str, ...] = ()
```

- [ ] **Step 7: Update `WorldState.apply` to handle `new_endings`**

In `src/tavern/world/state.py`, in the `apply` method, add before the `return WorldState(...)` call (before line 101):

```python
        new_endings_reached = self.endings_reached + diff.new_endings
```

Then add `endings_reached=new_endings_reached,` to the `WorldState(...)` constructor call, after `timeline=new_timeline,`.

- [ ] **Step 8: Update `_merge_diffs` for `new_endings`**

In `src/tavern/engine/rules.py`, in the `_merge_diffs` function, add to the returned `StateDiff(...)` after `new_events` line:

```python
        new_endings=a.new_endings + b.new_endings,
```

- [ ] **Step 9: Run all state and rules tests**

Run: `pytest tests/world/test_state.py tests/engine/test_rules_use.py -v`
Expected: all PASS

- [ ] **Step 10: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS (no regressions — the new fields have empty defaults)

- [ ] **Step 11: Commit**

```bash
git add src/tavern/world/state.py src/tavern/engine/rules.py tests/world/test_state.py tests/engine/test_rules_use.py
git commit -m "feat: add endings_reached to WorldState and new_endings to StateDiff"
```

---

### Task 3: StoryEffects `trigger_ending` — Effect, Builder, and Loader

**Files:**
- Modify: `src/tavern/engine/story.py:57-62` (StoryEffects), `114-172` (_build_result), `250-307` (loader)
- Test: `tests/engine/test_story.py`

**Context:**
- `StoryEffects` (line 57) is a frozen dataclass with fields: `quest_updates`, `new_events`, `add_items`, `remove_items`, `character_stat_deltas`.
- `_build_result` (line 114) constructs a `StoryResult` with a `StateDiff`. It builds `events`, `quest_updates`, handles items and stat deltas.
- `load_story_nodes` (line 250) parses YAML. Effects are read from `effects_raw = entry.get("effects", {})`.
- `StateDiff` now has `new_endings: tuple[str, ...] = ()` (from Task 2).
- Test helper `_make_node` creates `StoryNode` with `StoryEffects`.

- [ ] **Step 1: Write failing test for `_build_result` with `trigger_ending`**

```python
# Append to tests/engine/test_story.py

def test_build_result_trigger_ending():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={"main_story": {"status": "good_ending"}},
        new_events=(),
        trigger_ending="good_ending",
    )
    node = StoryNode(
        id="ending_good", act="act1", requires=(), repeatable=False,
        trigger_mode="passive", conditions=(), effects=effects,
        narrator_hint="温暖收束", fail_forward=None,
    )
    engine = _make_engine([node])
    state = _make_state()
    results = engine.check(state, "passive", MagicMock(), MagicMock())
    diff = results[0].diff
    assert diff.new_endings == ("good_ending",)


def test_build_result_no_trigger_ending():
    from tavern.engine.story import StoryEffects, StoryNode
    effects = StoryEffects(
        quest_updates={"q1": {"status": "done"}},
        new_events=(),
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
    assert diff.new_endings == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_story.py::test_build_result_trigger_ending tests/engine/test_story.py::test_build_result_no_trigger_ending -v`
Expected: FAIL with `TypeError` (unexpected keyword `trigger_ending`)

- [ ] **Step 3: Write failing test for YAML loader parsing `trigger_ending`**

```python
# Append to tests/engine/test_story.py

def test_load_story_nodes_with_trigger_ending(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: ending_good
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates:
        main_story: { status: good_ending }
      new_events:
        - id: ending_good_reached
          type: ending
          description: "好结局达成"
      trigger_ending: good_ending
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert "ending_good" in nodes
    assert nodes["ending_good"].effects.trigger_ending == "good_ending"


def test_load_story_nodes_without_trigger_ending(tmp_path):
    from tavern.engine.story import load_story_nodes
    yaml_content = """
nodes:
  - id: normal_node
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions: []
    effects:
      quest_updates: {}
      new_events: []
"""
    path = tmp_path / "story.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    nodes = load_story_nodes(path)
    assert nodes["normal_node"].effects.trigger_ending is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/engine/test_story.py::test_load_story_nodes_with_trigger_ending tests/engine/test_story.py::test_load_story_nodes_without_trigger_ending -v`
Expected: FAIL

- [ ] **Step 5: Add `trigger_ending` field to `StoryEffects`**

In `src/tavern/engine/story.py`, add to `StoryEffects` after `character_stat_deltas` (line 62):

```python
    trigger_ending: str | None = None
```

- [ ] **Step 6: Update `_build_result` to set `new_endings`**

In `src/tavern/engine/story.py`, in the `_build_result` function, add after the `character_stat_deltas` line and before `diff = StateDiff(...)` (around line 164):

```python
    new_endings = (node.effects.trigger_ending,) if node.effects.trigger_ending else ()
```

Then add `new_endings=new_endings,` to the `StateDiff(...)` constructor call.

- [ ] **Step 7: Update loader to parse `trigger_ending`**

In `src/tavern/engine/story.py`, in `load_story_nodes`, update the `StoryEffects(...)` constructor (around line 271) to add:

```python
                trigger_ending=effects_raw.get("trigger_ending"),
```

- [ ] **Step 8: Run all story engine tests**

Run: `pytest tests/engine/test_story.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/tavern/engine/story.py tests/engine/test_story.py
git commit -m "feat: add trigger_ending to StoryEffects with builder and loader support"
```

---

### Task 4: Narrator Ending Prompt and Streaming

**Files:**
- Modify: `src/tavern/narrator/prompts.py:1-72`
- Modify: `src/tavern/narrator/narrator.py:1-56`
- Test: `tests/narrator/test_narrator.py`

**Context:**
- `prompts.py` has `NARRATIVE_TEMPLATES` dict and `build_narrative_prompt` function.
- `narrator.py` has `Narrator` class with `stream_narrative` async generator method.
- `Narrator._build_context` requires an `ActionResult` which ending flow doesn't have.
- The ending prompt needs: ending_id, narrator_hint, state context (quests, items, relationships).
- Tests use `mock_llm_service` fixture with `stream_narrative` mock.
- `MemoryContext` (from `tavern.world.memory`) has `recent_events` and `relationship_summary` strings.

- [ ] **Step 1: Write failing test for `build_ending_prompt`**

```python
# Append to tests/narrator/test_narrator.py

from tavern.narrator.prompts import build_ending_prompt


class TestEndingPrompt:
    def test_build_ending_prompt_structure(self, sample_world_state):
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "结局" in messages[0]["content"]
        assert "good_ending" in messages[1]["content"]
        assert "温暖收束" in messages[1]["content"]

    def test_build_ending_prompt_includes_quests(self, sample_world_state):
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="hint",
            state=sample_world_state,
        )
        system_content = messages[0]["content"]
        # System prompt should mention quest/task context
        assert "任务" in system_content or "quest" in system_content.lower()

    def test_build_ending_prompt_with_memory(self, sample_world_state):
        memory = MagicMock()
        memory.recent_events = "玩家揭开了密道的秘密"
        memory.relationship_summary = "酒保: 信任 30"
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="hint",
            state=sample_world_state,
            memory=memory,
        )
        system_content = messages[0]["content"]
        assert "密道" in system_content
        assert "酒保" in system_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/narrator/test_narrator.py::TestEndingPrompt -v`
Expected: FAIL with `ImportError` (function doesn't exist)

- [ ] **Step 3: Write failing test for `stream_ending_narrative`**

```python
# Append to tests/narrator/test_narrator.py

class TestEndingNarrative:
    @pytest.mark.asyncio
    async def test_stream_ending_yields_chunks(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_async_gen("夜色温柔，", "冒险者踏上新的旅途。")
        )
        chunks = []
        async for chunk in narrator.stream_ending_narrative(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        ):
            chunks.append(chunk)
        assert chunks == ["夜色温柔，", "冒险者踏上新的旅途。"]

    @pytest.mark.asyncio
    async def test_stream_ending_fallback_on_error(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_raise_on_iter()
        )
        chunks = []
        async for chunk in narrator.stream_ending_narrative(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        ):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "good_ending" in chunks[0]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/narrator/test_narrator.py::TestEndingNarrative -v`
Expected: FAIL with `AttributeError` (method doesn't exist)

- [ ] **Step 5: Implement `build_ending_prompt` in `prompts.py`**

Add at the end of `src/tavern/narrator/prompts.py`:

```python
ENDING_TEMPLATE = (
    "你是一位叙事大师，正在为这段冒险故事画上句号。\n"
    "用200-300字的篇幅，以第二人称（「你」）写一段结局叙事。\n"
    "风格：富有余韵的收束感，不要戛然而止，也不要拖沓。中文。"
)


def build_ending_prompt(
    ending_id: str,
    narrator_hint: str,
    state: WorldState,
    memory: MemoryContext | None = None,
) -> list[dict[str, str]]:
    quest_lines = []
    for qid, q in state.quests.items():
        status = q.get("status", "unknown")
        quest_lines.append(f"  {qid}: {status}")
    quest_text = "\n".join(quest_lines) if quest_lines else "  无"

    player = state.characters.get(state.player_id)
    inv_text = ", ".join(player.inventory) if player and player.inventory else "无"

    system_content = (
        f"{ENDING_TEMPLATE}\n\n"
        f"【任务状态】\n{quest_text}\n\n"
        f"【持有物品】\n  {inv_text}"
    )

    if memory is not None:
        system_content += f"\n\n【近期历史】\n{memory.recent_events}"
        system_content += f"\n\n【关系状态】\n{memory.relationship_summary}"

    user_content = f"结局ID: {ending_id}\n\n叙事方向: {narrator_hint}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
```

Also add the `WorldState` import. Update the `TYPE_CHECKING` block at the top of `prompts.py`:

```python
if TYPE_CHECKING:
    from tavern.world.memory import MemoryContext
    from tavern.world.state import WorldState
```

- [ ] **Step 6: Implement `stream_ending_narrative` in `narrator.py`**

Add at the end of the `Narrator` class in `src/tavern/narrator/narrator.py`:

```python
    async def stream_ending_narrative(
        self,
        ending_id: str,
        narrator_hint: str,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            from tavern.narrator.prompts import build_ending_prompt
            messages = build_ending_prompt(ending_id, narrator_hint, state, memory_ctx)
            system_prompt = messages[0]["content"]
            user_content = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, user_content):
                yield chunk
        except Exception:
            yield f"[结局: {ending_id}]"
```

- [ ] **Step 7: Run all narrator tests**

Run: `pytest tests/narrator/test_narrator.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/tavern/narrator/prompts.py src/tavern/narrator/narrator.py tests/narrator/test_narrator.py
git commit -m "feat: add ending narrative prompt template and stream_ending_narrative method"
```

---

### Task 5: CLI Ending Detection, Rendering, and Game Exit

**Files:**
- Modify: `src/tavern/cli/app.py:86-87` (init), `105-136` (run loop), `264-284` (_handle_free_input), `165-174` (_handle_system_command continue), `367-382` (_apply_story_results)
- Modify: `src/tavern/cli/renderer.py`
- Test: `tests/cli/test_app_story.py`

**Context:**
- `GameApp.__init__` (line 86) sets `self._pending_story_hints: list[str] = []`.
- Main loop (line 109-136): `while True:` checks for quit, dialogue, system commands, free input.
- `_handle_free_input` (line 264-284): after applying story results, streams narrator narrative.
- `_handle_system_command("continue")` (line 165-174): applies story results synchronously.
- `_apply_story_results` (line 367-382): commits each `StoryResult.diff` and collects narrator hints.
- `StoryResult.diff.new_endings` is `tuple[str, ...]` (from Task 2).
- `Renderer` uses `rich.panel.Panel` and `rich.console.Console`.
- Test helper `_make_app()` in `test_app_story.py` constructs a mock `GameApp`.

- [ ] **Step 1: Write failing tests for ending detection and game exit**

```python
# Append to tests/cli/test_app_story.py

def test_apply_story_results_detects_ending():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(
        new_endings=("good_ending",),
        quest_updates={"ending_good": {"_story_status": "completed"}},
        turn_increment=0,
    )
    results = [StoryResult(node_id="ending_good", diff=diff, narrator_hint="温暖收束")]
    asyncio.run(app._apply_story_results(results))
    assert app._ending_triggered is not None
    assert app._ending_triggered == ("good_ending", "温暖收束")


def test_apply_story_results_no_ending():
    app, state = _make_app()
    from tavern.engine.story import StoryResult
    from tavern.world.state import StateDiff

    diff = StateDiff(quest_updates={"n1": {"_story_status": "completed"}}, turn_increment=0)
    results = [StoryResult(node_id="n1", diff=diff, narrator_hint="some hint")]
    asyncio.run(app._apply_story_results(results))
    assert app._ending_triggered is None


def test_game_over_flag_set_after_ending():
    app, state = _make_app()
    from tavern.engine.actions import ActionType
    from tavern.engine.story import StoryResult
    from tavern.world.models import ActionResult
    from tavern.world.state import StateDiff

    result = ActionResult(success=True, action=ActionType.MOVE, message="移动成功", target="cellar")
    diff = StateDiff()
    app._rules.validate = MagicMock(return_value=(result, diff))
    app._parser.parse = AsyncMock(return_value=MagicMock(action=ActionType.MOVE))
    app._state_manager.commit = MagicMock(return_value=state)

    ending_diff = StateDiff(
        new_endings=("good_ending",),
        quest_updates={"ending_good": {"_story_status": "completed"}},
        turn_increment=0,
    )
    ending_result = StoryResult(node_id="ending_good", diff=ending_diff, narrator_hint="温暖收束")
    app._story_engine.check = MagicMock(return_value=[ending_result])

    asyncio.run(app._handle_free_input("go cellar"))
    assert app._game_over is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_app_story.py::test_apply_story_results_detects_ending tests/cli/test_app_story.py::test_apply_story_results_no_ending tests/cli/test_app_story.py::test_game_over_flag_set_after_ending -v`
Expected: FAIL with `AttributeError` (`_ending_triggered` / `_game_over` don't exist)

- [ ] **Step 3: Add `render_ending` to `Renderer`**

In `src/tavern/cli/renderer.py`, add a new method to the `Renderer` class:

```python
    def render_ending(self, ending_id: str) -> None:
        ending_titles = {
            "good_ending": "🌅 黎明之路",
            "bad_ending": "🌑 暗影独行",
            "neutral_ending": "🚶 过客",
        }
        title = ending_titles.get(ending_id, f"结局: {ending_id}")
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]{title}[/]\n\n"
                "[dim]感谢你的冒险。输入任意键退出。[/]",
                border_style="bright_yellow",
                padding=(1, 2),
            )
        )
```

- [ ] **Step 4: Add `_ending_triggered` and `_game_over` to `GameApp.__init__`**

In `src/tavern/cli/app.py`, add after `self._pending_story_hints: list[str] = []` (line 86):

```python
        self._ending_triggered: tuple[str, str] | None = None  # (ending_id, narrator_hint)
        self._game_over = False
```

- [ ] **Step 5: Update `_apply_story_results` to detect endings**

In `src/tavern/cli/app.py`, update `_apply_story_results_sync` (line 370-382). Replace the method body:

```python
    def _apply_story_results_sync(self, results: list[StoryResult]) -> None:
        for r in results:
            self._state_manager.commit(
                r.diff,
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message=f"剧情节点触发：{r.node_id}",
                ),
            )
            self._memory.apply_diff(r.diff, self.state)
            if r.narrator_hint:
                self._pending_story_hints.append(r.narrator_hint)
            if r.diff.new_endings:
                self._ending_triggered = (r.diff.new_endings[0], r.narrator_hint or "")
```

- [ ] **Step 6: Update `_handle_free_input` to handle ending after story check**

In `src/tavern/cli/app.py`, in `_handle_free_input`, after `await self._apply_story_results(story_results)` and `self._update_story_active_since()` (around line 270-271), add ending handling BEFORE the regular narrator streaming. Replace lines 264-284 with:

```python
        if result.success and not self._dialogue_manager.is_active:
            story_results = self._story_engine.check(
                self.state, "passive",
                self._memory._timeline, self._memory._relationship_graph,
            )
            story_results += self._story_engine.check_fail_forward(self.state)
            await self._apply_story_results(story_results)
            self._update_story_active_since()

            if self._ending_triggered is not None:
                ending_id, ending_hint = self._ending_triggered
                memory_ctx = self._memory.build_context(
                    actor=self.state.player_id,
                    state=self.state,
                )
                await self._renderer.render_stream(
                    self._narrator.stream_ending_narrative(
                        ending_id, ending_hint, self.state, memory_ctx,
                    )
                )
                self._renderer.render_ending(ending_id)
                self._game_over = True
                return

            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
            )
            combined_hint = "\n".join(self._pending_story_hints) or None
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint)
            )
        else:
            self._renderer.render_result(result)
        self._pending_story_hints.clear()
        self._renderer.render_status_bar(self.state)
```

- [ ] **Step 7: Update `_handle_system_command("continue")` for endings**

In `src/tavern/cli/app.py`, update the `continue` branch (around line 165-174). After `self._apply_story_results_sync(story_results)`, add:

```python
            if self._ending_triggered is not None:
                ending_id, ending_hint = self._ending_triggered
                memory_ctx = self._memory.build_context(
                    actor=self.state.player_id,
                    state=self.state,
                )
                import asyncio as _aio
                _aio.get_event_loop().run_until_complete(
                    self._renderer.render_stream(
                        self._narrator.stream_ending_narrative(
                            ending_id, ending_hint, self.state, memory_ctx,
                        )
                    )
                )
                self._renderer.render_ending(ending_id)
                self._game_over = True
```

- [ ] **Step 8: Update main `run` loop to check `_game_over`**

In `src/tavern/cli/app.py`, in the `run` method (line 109), change the loop to check game_over:

```python
        while not self._game_over:
```

- [ ] **Step 9: Update `_make_app` helper in tests**

In `tests/cli/test_app_story.py`, add to `_make_app` after `app._pending_story_hints = []` (line 41):

```python
    app._ending_triggered = None
    app._game_over = False
```

- [ ] **Step 10: Run all app story tests**

Run: `pytest tests/cli/test_app_story.py -v`
Expected: all PASS

- [ ] **Step 11: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS

- [ ] **Step 12: Commit**

```bash
git add src/tavern/cli/app.py src/tavern/cli/renderer.py tests/cli/test_app_story.py
git commit -m "feat: detect ending in story results, render ending panel, exit game loop"
```

---

### Task 6: Story YAML Data — Ending Nodes and Bartender Skill

**Files:**
- Modify: `data/scenarios/tavern/story.yaml` (append 4 nodes)
- Create: `data/scenarios/tavern/skills/bartender_letter_hint.yaml`
- Test: validate with loader test

**Context:**
- Existing `story.yaml` has 10 nodes (2 main + 3 side quest chains). New nodes append after `box_opened_node`.
- Condition types available: `location`, `inventory`, `relationship`, `event`, `quest`, `quest_count` (Task 1), `turn_count` (Task 1).
- `trigger_ending` field parsed by loader (Task 3).
- Skill files use flat `activation: [...]` list format (matching `SkillManager.load_skills` parser).
- All three endings are mutually exclusive via `event` not_exists conditions.
- The `betray_guest` node is a decision point (not an ending itself).

- [ ] **Step 1: Add `betray_guest` story node to `story.yaml`**

Append to `data/scenarios/tavern/story.yaml` after the `box_opened_node` entry:

```yaml

  # ── Multi-Ending: Decision Node ─────────────────────────────────────────

  - id: betray_guest
    act: act1
    requires: [guest_quest_complete]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: inventory
          event_id: guest_letter
        - type: location
          event_id: bar_area
        - type: event
          event_id: talked_to_bartender_about_letter
          check: exists

    effects:
      quest_updates:
        guest_betrayal: { status: completed }
      new_events:
        - id: guest_betrayed
          type: story
          description: "玩家将神秘旅客的信件交给了酒保"
      remove_items:
        - item_id: guest_letter
          from: inventory
      character_stat_deltas:
        bartender_grim:
          trust: 30
        mysterious_guest:
          trust: -50

    narrator_hint: "玩家做出了背叛的选择。酒保接过信件时眼中闪过贪婪的光芒。"
```

- [ ] **Step 2: Add `ending_good` story node**

Append to `data/scenarios/tavern/story.yaml`:

```yaml

  # ── Multi-Ending: Good Ending ───────────────────────────────────────────

  - id: ending_good
    act: act1
    requires: [cellar_secret_revealed]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: secret_learned
          check: exists
        - type: quest_count
          check: completed
          operator: ">="
          value: 2
        - type: relationship
          source: player
          target: traveler
          attribute: trust
          operator: ">="
          value: 20
        - type: event
          event_id: ending_bad_reached
          check: not_exists
        - type: event
          event_id: ending_neutral_reached
          check: not_exists

    effects:
      quest_updates:
        main_story: { status: good_ending }
      new_events:
        - id: ending_good_reached
          type: ending
          description: "玩家达成好结局「黎明之路」"
      trigger_ending: good_ending

    narrator_hint: "玩家赢得了酒馆众人的信任，揭开了密道的秘密。艾琳愿意与你同行，格里姆终于露出了难得的笑容。新的冒险在密道的尽头等待着你。用温暖、希望的笔触收束这段故事。"
```

- [ ] **Step 3: Add `ending_bad` story node**

Append to `data/scenarios/tavern/story.yaml`:

```yaml

  # ── Multi-Ending: Bad Ending ────────────────────────────────────────────

  - id: ending_bad
    act: act1
    requires: [betray_guest]
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: event
          event_id: guest_betrayed
          check: exists
        - type: event
          event_id: ending_good_reached
          check: not_exists
        - type: event
          event_id: ending_neutral_reached
          check: not_exists

    effects:
      quest_updates:
        main_story: { status: bad_ending }
      new_events:
        - id: ending_bad_reached
          type: ending
          description: "玩家达成坏结局「暗影独行」"
      trigger_ending: bad_ending

    narrator_hint: "你出卖了神秘旅客的信任。格里姆收下信件，脸上浮现出意味深长的笑容。走廊里传来沉重而急促的脚步声——神秘旅客已经消失在夜色中。你得到了酒保的信任，却失去了更重要的东西。用阴暗、孤独的笔触收束。"
```

- [ ] **Step 4: Add `ending_neutral` story node**

Append to `data/scenarios/tavern/story.yaml`:

```yaml

  # ── Multi-Ending: Neutral Ending ────────────────────────────────────────

  - id: ending_neutral
    act: act1
    requires: []
    repeatable: false
    trigger:
      mode: passive
      conditions:
        - type: turn_count
          operator: ">="
          value: 40
        - type: event
          event_id: ending_good_reached
          check: not_exists
        - type: event
          event_id: ending_bad_reached
          check: not_exists

    effects:
      quest_updates:
        main_story: { status: neutral_ending }
      new_events:
        - id: ending_neutral_reached
          type: ending
          description: "玩家达成中结局「过客」"
      trigger_ending: neutral_ending

    narrator_hint: "夜深了，你终究只是酒馆里的一个过客。一些谜团仍未解开，一些故事仍在继续。你推开酒馆的门，走进晨雾弥漫的街道。身后传来隐约的笑声和杯盏碰撞声。用淡然、若有所思的笔触收束。"
```

- [ ] **Step 5: Create `bartender_letter_hint.yaml` skill**

Create `data/scenarios/tavern/skills/bartender_letter_hint.yaml`:

```yaml
id: bartender_letter_hint
name: 酒保对信件的兴趣
character: bartender_grim
priority: high
activation:
  - type: inventory
    event_id: guest_letter
  - type: location
    event_id: bar_area
facts:
  - "注意到玩家手中那封带着古老徽章的信件"
  - "对信件上的徽章标志非常感兴趣"
  - "暗示自己认识信件上的徽章"
behavior:
  tone: "看似随意但暗含试探"
  reveal_strategy: "旁敲侧击，暗示可以帮忙处理这封信件"
  forbidden: "不会直接说出想要信件或承认认识徽章的主人"
related_skills:
  - guest_secret_knowledge
```

- [ ] **Step 6: Write loader validation test**

```python
# Append to tests/engine/test_story.py

def test_load_tavern_story_yaml_includes_endings():
    from pathlib import Path
    from tavern.engine.story import load_story_nodes
    path = Path("data/scenarios/tavern/story.yaml")
    if not path.exists():
        pytest.skip("tavern story.yaml not found")
    nodes = load_story_nodes(path)
    assert "ending_good" in nodes
    assert "ending_bad" in nodes
    assert "ending_neutral" in nodes
    assert "betray_guest" in nodes
    assert nodes["ending_good"].effects.trigger_ending == "good_ending"
    assert nodes["ending_bad"].effects.trigger_ending == "bad_ending"
    assert nodes["ending_neutral"].effects.trigger_ending == "neutral_ending"
    assert nodes["betray_guest"].effects.trigger_ending is None
```

- [ ] **Step 7: Run the loader validation test**

Run: `pytest tests/engine/test_story.py::test_load_tavern_story_yaml_includes_endings -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `pytest --tb=short -q`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add data/scenarios/tavern/story.yaml data/scenarios/tavern/skills/bartender_letter_hint.yaml tests/engine/test_story.py
git commit -m "feat: add 4 ending story nodes and bartender letter hint skill"
```
