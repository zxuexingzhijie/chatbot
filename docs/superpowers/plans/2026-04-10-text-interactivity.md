# 文字交互性创新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add 5 interactive text features: atmosphere color, typewriter rhythm, entity highlighting, contextual auto-complete, action hint tags

**Architecture:** Extend Renderer with atmosphere styles, typewriter delays, entity highlighting, and a state-aware ContextualCompleter. Add action hint generation to GameApp.

**Tech Stack:** Rich (Console, markup), prompt_toolkit (Completer, Completion), asyncio

---

## File Structure

```
src/tavern/
├── cli/
│   ├── renderer.py             # Modify: atmosphere styles, typewriter, highlights,
│   │                           #         ContextualCompleter, action hints
│   └── app.py                  # Modify: state_provider, hint generation, number-input mapping
├── world/
│   └── models.py               # Modify: Location.atmosphere field
├── data/scenarios/tavern/
│   └── world.yaml              # Modify: atmosphere per location

config.yaml                     # Modify: typewriter_effect

tests/
└── cli/
    └── test_renderer.py        # Modify: all new feature tests
```

---

### Task 1: 氛围色调系统

**Files:**
- Modify: `src/tavern/world/models.py:53-69`
- Modify: `src/tavern/data/scenarios/tavern/world.yaml` (all 5 locations)
- Modify: `src/tavern/cli/renderer.py:53-97` (Renderer class, render_stream)
- Modify: `src/tavern/cli/app.py:351,365` (render_stream calls)
- Test: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests for atmosphere style mapping and render_stream atmosphere param**

In `tests/cli/test_renderer.py`, add a new test class at the end of the file:

```python
class TestAtmosphereStyles:
    def test_atmosphere_style_mapping_has_all_keys(self):
        from tavern.cli.renderer import _ATMOSPHERE_STYLES

        assert "warm" in _ATMOSPHERE_STYLES
        assert "cold" in _ATMOSPHERE_STYLES
        assert "dim" in _ATMOSPHERE_STYLES
        assert "natural" in _ATMOSPHERE_STYLES
        assert "danger" in _ATMOSPHERE_STYLES
        assert "neutral" in _ATMOSPHERE_STYLES

    def test_atmosphere_style_values_are_strings(self):
        from tavern.cli.renderer import _ATMOSPHERE_STYLES

        for key, value in _ATMOSPHERE_STYLES.items():
            assert isinstance(value, str), f"Style for '{key}' is not a string"

    def test_neutral_is_default_fallback(self):
        from tavern.cli.renderer import _ATMOSPHERE_STYLES

        assert "italic" in _ATMOSPHERE_STYLES["neutral"]
        assert "dim" in _ATMOSPHERE_STYLES["neutral"]

    @pytest.mark.asyncio
    async def test_render_stream_uses_atmosphere_style(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("温暖的酒馆大厅"), atmosphere="warm")
        output = console.file.getvalue()
        assert "温暖的酒馆大厅" in output

    @pytest.mark.asyncio
    async def test_render_stream_defaults_to_neutral(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("普通文字"))
        output = console.file.getvalue()
        assert "普通文字" in output

    @pytest.mark.asyncio
    async def test_render_stream_unknown_atmosphere_falls_back_to_neutral(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("未知氛围"), atmosphere="unknown_type")
        output = console.file.getvalue()
        assert "未知氛围" in output
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestAtmosphereStyles -x -v 2>&1 | tail -20
```

Expect: FAIL (no `_ATMOSPHERE_STYLES`, `render_stream` doesn't accept `atmosphere`).

- [ ] **Step 2: Add `atmosphere` field to Location model**

In `src/tavern/world/models.py`, add the `atmosphere` field to the `Location` class at line 61 (after the `npcs` field):

```python
class Location(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    name: str
    description: str
    exits: dict[str, Exit] = {}
    items: tuple[str, ...] = ()
    npcs: tuple[str, ...] = ()
    atmosphere: str = "neutral"

    @model_validator(mode="wrap")
    @classmethod
    def freeze_mutable_fields(cls, values: Any, handler: Any) -> Location:
        instance = handler(values)
        if isinstance(instance.exits, dict) and not isinstance(instance.exits, MappingProxyType):
            object.__setattr__(instance, "exits", MappingProxyType(instance.exits))
        return instance
```

The only change is inserting `atmosphere: str = "neutral"` after line 61 (`npcs: tuple[str, ...] = ()`).

- [ ] **Step 3: Add atmosphere values to each location in world.yaml**

In `src/tavern/data/scenarios/tavern/world.yaml`, add an `atmosphere` field to each location block:

For `tavern_hall` (after line 7, before `exits`):
```yaml
  tavern_hall:
    name: 酒馆大厅
    description: >-
      推开沉重的橡木门，你走进了「醉龙酒馆」。大厅里弥漫着麦酒和烤肉的香气，
      壁炉中的火焰投射出温暖的光芒。几张粗糙的木桌散落各处，角落里坐着一位
      风尘仆仆的旅行者。墙上挂着一张泛黄的告示。
    atmosphere: warm
    exits:
```

For `bar_area` (after line 26, before `exits`):
```yaml
  bar_area:
    name: 吧台区
    description: >-
      长长的橡木吧台后面，酒保格里姆正在擦拭杯子。吧台上摆着各式酒瓶，
      墙上挂着一面铜质奖牌和一幅褪色的城镇地图。吧台尽头有一扇沉重的
      铁门，上面挂着一把锁。
    atmosphere: warm
    exits:
```

For `cellar` (after line 46, before `exits`):
```yaml
  cellar:
    name: 地下室
    description: >-
      阴暗潮湿的地下室，空气中弥漫着霉味。几个破旧的木桶堆在角落，
      蜘蛛网挂满了石质墙壁。地面上有一些奇怪的划痕，似乎有什么沉重的
      东西被拖过。
    atmosphere: cold
    exits:
```

For `corridor` (after line 60, before `exits`):
```yaml
  corridor:
    name: 客房走廊
    description: >-
      狭窄的走廊两侧排列着几扇紧闭的房门。走廊尽头的房间门半掩着，
      透出昏暗的烛光。一位戴着兜帽的神秘旅客靠在墙边，似乎在等待什么。
    atmosphere: dim
    exits:
```

For `backyard` (after line 72, before `exits`):
```yaml
  backyard:
    name: 后院
    description: >-
      杂草丛生的后院，月光洒在一辆废弃的马车上。马车的篷布已经破烂不堪，
      但车厢下似乎藏着什么东西。院子角落有一口枯井，井沿上长满了青苔。
    atmosphere: natural
    exits:
```

- [ ] **Step 4: Add `_ATMOSPHERE_STYLES` dict and update `render_stream` in renderer.py**

In `src/tavern/cli/renderer.py`, add the styles dict at module level (after `_COMMAND_COMPLETIONS` at line 35, before the `SlashCommandCompleter` class):

```python
_ATMOSPHERE_STYLES: dict[str, str] = {
    "warm": "italic rgb(255,200,140)",
    "cold": "italic rgb(140,170,220)",
    "dim": "italic rgb(160,160,160)",
    "natural": "italic rgb(140,200,140)",
    "danger": "italic rgb(220,140,140)",
    "neutral": "italic dim",
}
```

Update `render_stream` (currently at line 90) to accept and use the atmosphere param:

```python
    async def render_stream(self, stream, *, atmosphere: str = "neutral") -> None:
        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        try:
            async for chunk in stream:
                self.console.print(chunk, end="", style=style, highlight=False)
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)
        self.console.print("\n")
```

- [ ] **Step 5: Pass atmosphere from app.py when calling render_stream**

In `src/tavern/cli/app.py`, update the `render_stream` calls in `_handle_free_input` to pass the current location's atmosphere.

At line 283, a local `location` is already computed. Use it in the two `render_stream` calls.

At line 351 (ending narrative stream):
```python
                await self._renderer.render_stream(
                    self._narrator.stream_ending_narrative(
                        ending_id, ending_hint, self.state, memory_ctx,
                    ),
                    atmosphere=location.atmosphere,
                )
```

At line 365 (normal narrative stream):
```python
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint),
                atmosphere=location.atmosphere,
            )
```

- [ ] **Step 6: Run tests — confirm GREEN**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestAtmosphereStyles -x -v 2>&1 | tail -20
```

Also run existing tests to confirm no regressions:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py -x -v 2>&1 | tail -30
```

- [ ] **Step 7: Commit**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/world/models.py src/tavern/data/scenarios/tavern/world.yaml src/tavern/cli/renderer.py src/tavern/cli/app.py tests/cli/test_renderer.py && git commit -m "feat: 添加氛围色调系统，根据场景渲染不同文字风格"
```

---

### Task 2: 打字机节奏

**Files:**
- Modify: `config.yaml:36-41`
- Modify: `src/tavern/cli/renderer.py` (Renderer.__init__, render_stream)
- Modify: `src/tavern/cli/app.py:70` (pass typewriter config to Renderer)
- Test: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests for typewriter delay behavior**

In `tests/cli/test_renderer.py`, add at the end:

```python
from unittest.mock import AsyncMock, patch


async def _async_gen_punctuation(*values):
    for v in values:
        yield v


class TestTypewriterEffect:
    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_period(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("你好。"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.3 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_exclamation(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("太好了！"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.25 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_question(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("真的吗？"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.25 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_ellipsis(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("等等…"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.4 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_double_newline(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("第一段\n\n第二段"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.5 in delays

    @pytest.mark.asyncio
    async def test_typewriter_no_pause_on_normal_text(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("普通文字"))
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_typewriter_disabled_no_pause(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=False)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("你好。太好了！"))
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_typewriter_default_is_disabled(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen_punctuation("你好。"))
            mock_sleep.assert_not_called()
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestTypewriterEffect -x -v 2>&1 | tail -20
```

Expect: FAIL (`Renderer` doesn't accept `typewriter_effect`).

- [ ] **Step 2: Add `typewriter_effect: true` to config.yaml**

In `config.yaml`, add inside the `game:` section (after line 40, before the `debug:` section):

```yaml
game:
  vi_mode: false
  auto_save_interval: 5
  undo_history_size: 50
  saves_dir: "saves"
  scenario: tavern
  typewriter_effect: true
```

- [ ] **Step 3: Add typewriter support to Renderer**

In `src/tavern/cli/renderer.py`, add the import at the top (after `import logging`, line 3):

```python
import asyncio
```

Add the pause chars dict at module level (after `_ATMOSPHERE_STYLES`):

```python
_TYPEWRITER_PAUSES: dict[str, float] = {
    "。": 0.3,
    "！": 0.25,
    "？": 0.25,
    "…": 0.4,
    "\n\n": 0.5,
}
```

Update `Renderer.__init__` to accept the typewriter param:

```python
class Renderer:
    def __init__(
        self,
        console: Console | None = None,
        vi_mode: bool = False,
        typewriter_effect: bool = False,
    ):
        self.console = console or Console()
        self._typewriter_effect = typewriter_effect
        self._session = PromptSession(vi_mode=vi_mode, completer=SlashCommandCompleter())
```

Update `render_stream` to apply typewriter delays. Replace the method entirely:

```python
    async def render_stream(self, stream, *, atmosphere: str = "neutral") -> None:
        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        accumulated = ""
        try:
            async for chunk in stream:
                self.console.print(chunk, end="", style=style, highlight=False)
                if self._typewriter_effect:
                    accumulated += chunk
                    if accumulated.endswith("\n\n"):
                        await asyncio.sleep(_TYPEWRITER_PAUSES["\n\n"])
                    else:
                        last_char = chunk.rstrip()[-1:] if chunk.rstrip() else ""
                        if last_char in _TYPEWRITER_PAUSES:
                            await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)
        self.console.print("\n")
```

- [ ] **Step 4: Pass typewriter_effect from app.py to Renderer**

In `src/tavern/cli/app.py`, update line 70 where Renderer is instantiated:

```python
        vi_mode = game_config.get("vi_mode", False)
        typewriter_effect = game_config.get("typewriter_effect", False)
        self._renderer = Renderer(vi_mode=vi_mode, typewriter_effect=typewriter_effect)
```

- [ ] **Step 5: Run tests — confirm GREEN**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestTypewriterEffect -x -v 2>&1 | tail -20
```

Run all renderer tests for regressions:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py -x -v 2>&1 | tail -30
```

- [ ] **Step 6: Commit**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add config.yaml src/tavern/cli/renderer.py src/tavern/cli/app.py tests/cli/test_renderer.py && git commit -m "feat: 添加打字机节奏效果，标点处自动停顿增强叙事感"
```

---

### Task 3: 叙事内嵌高亮

**Files:**
- Modify: `src/tavern/cli/renderer.py` (Renderer.__init__, _highlight_entities, render_stream)
- Modify: `src/tavern/cli/app.py:70` (pass state_provider to Renderer)
- Test: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests for entity highlighting**

In `tests/cli/test_renderer.py`, add at the end:

```python
class TestEntityHighlighting:
    def _make_state_provider(self, sample_world_state):
        return lambda: sample_world_state

    def test_highlight_npc_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )
        result = renderer._highlight_entities("旅行者正在喝酒。")
        assert "[bold cyan]旅行者[/]" in result

    def test_highlight_item_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )
        result = renderer._highlight_entities("你看到了旧告示。")
        assert "[cyan]旧告示[/]" in result

    def test_highlight_location_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )
        result = renderer._highlight_entities("你走进酒馆大厅。")
        assert "[green]酒馆大厅[/]" in result

    def test_highlight_longer_names_first(self, sample_world_state):
        """Longer names should be matched before shorter substrings."""
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )
        result = renderer._highlight_entities("地下室钥匙很重要。")
        assert "[cyan]地下室钥匙[/]" in result

    def test_highlight_no_state_returns_unchanged(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        result = renderer._highlight_entities("旅行者正在喝酒。")
        assert result == "旅行者正在喝酒。"

    @pytest.mark.asyncio
    async def test_render_stream_applies_highlighting(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )

        async def _line_stream():
            yield "旅行者走进了酒馆大厅。\n"

        await renderer.render_stream(_line_stream())
        output = console.file.getvalue()
        assert "旅行者" in output

    @pytest.mark.asyncio
    async def test_render_stream_buffers_by_line(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(
            console=console,
            state_provider=lambda: sample_world_state,
        )

        async def _multi_chunk_stream():
            yield "旅行者"
            yield "走进了\n"
            yield "酒馆大厅。\n"

        await renderer.render_stream(_multi_chunk_stream())
        output = console.file.getvalue()
        assert "旅行者" in output
        assert "酒馆大厅" in output
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestEntityHighlighting -x -v 2>&1 | tail -20
```

Expect: FAIL (`Renderer` doesn't accept `state_provider`, no `_highlight_entities` method).

- [ ] **Step 2: Add state_provider to Renderer.__init__**

In `src/tavern/cli/renderer.py`, update `Renderer.__init__`:

Add the import at the top of the file (update the existing `from __future__` block area):

```python
from typing import Callable
```

Update the `__init__` signature and body:

```python
class Renderer:
    def __init__(
        self,
        console: Console | None = None,
        vi_mode: bool = False,
        typewriter_effect: bool = False,
        state_provider: Callable[[], WorldState | None] | None = None,
    ):
        self.console = console or Console()
        self._typewriter_effect = typewriter_effect
        self._state_provider = state_provider
        self._session = PromptSession(vi_mode=vi_mode, completer=SlashCommandCompleter())
```

- [ ] **Step 3: Implement `_highlight_entities` method**

Add this method to the `Renderer` class (after `__init__`, before `spinner`):

```python
    def _highlight_entities(self, text: str) -> str:
        if self._state_provider is None:
            return text

        state = self._state_provider()
        if state is None:
            return text

        replacements: list[tuple[str, str]] = []

        for char in state.characters.values():
            if char.role.value == "npc":
                replacements.append((char.name, f"[bold cyan]{char.name}[/]"))

        for item in state.items.values():
            replacements.append((item.name, f"[cyan]{item.name}[/]"))

        for loc in state.locations.values():
            replacements.append((loc.name, f"[green]{loc.name}[/]"))

        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

        for original, highlighted in replacements:
            text = text.replace(original, highlighted)

        return text
```

- [ ] **Step 4: Update render_stream to buffer by line and apply highlighting**

Replace `render_stream` with a version that buffers text until newlines, then highlights and outputs complete lines. Partial text without newlines is flushed at the end:

```python
    async def render_stream(self, stream, *, atmosphere: str = "neutral") -> None:
        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        line_buffer = ""
        accumulated = ""
        try:
            async for chunk in stream:
                line_buffer += chunk
                accumulated += chunk

                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    highlighted = self._highlight_entities(line)
                    self.console.print(highlighted, end="\n", style=style, highlight=False)

                    if self._typewriter_effect:
                        stripped = line.rstrip()
                        last_char = stripped[-1:] if stripped else ""
                        if last_char in _TYPEWRITER_PAUSES:
                            await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])

                if self._typewriter_effect and not line_buffer:
                    if accumulated.endswith("\n\n"):
                        await asyncio.sleep(_TYPEWRITER_PAUSES["\n\n"])
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)

        if line_buffer:
            highlighted = self._highlight_entities(line_buffer)
            self.console.print(highlighted, end="", style=style, highlight=False)
            if self._typewriter_effect:
                stripped = line_buffer.rstrip()
                last_char = stripped[-1:] if stripped else ""
                if last_char in _TYPEWRITER_PAUSES:
                    await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
        self.console.print("\n")
```

- [ ] **Step 5: Pass state_provider from app.py to Renderer**

In `src/tavern/cli/app.py`, update the Renderer instantiation at line 70:

```python
        vi_mode = game_config.get("vi_mode", False)
        typewriter_effect = game_config.get("typewriter_effect", False)
        self._renderer = Renderer(
            vi_mode=vi_mode,
            typewriter_effect=typewriter_effect,
            state_provider=lambda: self.state,
        )
```

- [ ] **Step 6: Run tests — confirm GREEN**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestEntityHighlighting -x -v 2>&1 | tail -20
```

Run full suite:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py -x -v 2>&1 | tail -30
```

- [ ] **Step 7: Commit**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/cli/renderer.py src/tavern/cli/app.py tests/cli/test_renderer.py && git commit -m "feat: 添加叙事内嵌高亮，NPC/物品/地点名称自动标记"
```

---

### Task 4: 语境感知自动补全

**Files:**
- Modify: `src/tavern/cli/renderer.py` (ContextualCompleter, Renderer.__init__)
- Test: `tests/cli/test_renderer.py`

- [ ] **Step 1: Write failing tests for ContextualCompleter**

In `tests/cli/test_renderer.py`, add at the end:

```python
class TestContextualCompleter:
    def _make_completer(self, sample_world_state):
        from tavern.cli.renderer import ContextualCompleter

        return ContextualCompleter(state_provider=lambda: sample_world_state)

    def test_slash_commands_still_work(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("/lo", cursor_position=3)
        completions = list(completer.get_completions(doc, None))
        labels = [c.text for c in completions]
        assert "look" in labels
        assert "load" in labels

    def test_completes_npc_names(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "旅行者" in texts

    def test_npc_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        npc_completion = [c for c in completions if c.text == "旅行者"][0]
        assert "NPC" in npc_completion.display_meta_text

    def test_completes_item_names(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旧", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "旧告示" in texts

    def test_item_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旧", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        item_completion = [c for c in completions if c.text == "旧告示"][0]
        assert "物品" in item_completion.display_meta_text

    def test_completes_exit_directions(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("n", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "north" in texts

    def test_exit_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("n", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        exit_completion = [c for c in completions if c.text == "north"][0]
        assert "出口" in exit_completion.display_meta_text

    def test_no_completions_for_empty_input(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("", cursor_position=0)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_no_state_provider_only_slash_commands(self):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: None)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_slash_prefix_still_works_with_state(self, sample_world_state):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("/qu", cursor_position=3)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "quit" in texts
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestContextualCompleter -x -v 2>&1 | tail -20
```

Expect: FAIL (no `ContextualCompleter` class).

- [ ] **Step 2: Implement ContextualCompleter**

In `src/tavern/cli/renderer.py`, add the `ContextualCompleter` class after `SlashCommandCompleter` (after line 51):

```python
class ContextualCompleter(Completer):
    def __init__(self, state_provider: Callable[[], WorldState | None] | None = None):
        self._state_provider = state_provider

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/"):
            prefix = text[1:]
            for cmd, desc in _COMMAND_COMPLETIONS:
                if cmd.startswith(prefix):
                    yield Completion(
                        cmd,
                        start_position=-len(prefix),
                        display_meta=desc,
                    )
            return

        if not text:
            return

        state = self._state_provider() if self._state_provider else None
        if state is None:
            return

        player = state.characters.get(state.player_id)
        if player is None:
            return

        location = state.locations.get(player.location_id)
        if location is None:
            return

        for npc_id in location.npcs:
            npc = state.characters.get(npc_id)
            if npc and npc.name.startswith(text):
                yield Completion(
                    npc.name,
                    start_position=-len(text),
                    display_meta="NPC",
                )

        seen_items: set[str] = set()
        for item_id in location.items:
            item = state.items.get(item_id)
            if item and item.name.startswith(text):
                seen_items.add(item.name)
                yield Completion(
                    item.name,
                    start_position=-len(text),
                    display_meta="物品",
                )
        for item_id in player.inventory:
            item = state.items.get(item_id)
            if item and item.name.startswith(text) and item.name not in seen_items:
                yield Completion(
                    item.name,
                    start_position=-len(text),
                    display_meta="物品",
                )

        for direction in location.exits:
            if direction.startswith(text):
                yield Completion(
                    direction,
                    start_position=-len(text),
                    display_meta="出口",
                )
```

- [ ] **Step 3: Wire ContextualCompleter into Renderer**

In `Renderer.__init__`, replace `SlashCommandCompleter()` with `ContextualCompleter`:

```python
    def __init__(
        self,
        console: Console | None = None,
        vi_mode: bool = False,
        typewriter_effect: bool = False,
        state_provider: Callable[[], WorldState | None] | None = None,
    ):
        self.console = console or Console()
        self._typewriter_effect = typewriter_effect
        self._state_provider = state_provider
        self._session = PromptSession(
            vi_mode=vi_mode,
            completer=ContextualCompleter(state_provider=state_provider),
        )
```

- [ ] **Step 4: Run tests — confirm GREEN**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestContextualCompleter -x -v 2>&1 | tail -20
```

Also ensure the old `SlashCommandCompleter` tests still pass (the class remains in the module):
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py -x -v 2>&1 | tail -30
```

- [ ] **Step 5: Commit**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/cli/renderer.py tests/cli/test_renderer.py && git commit -m "feat: 添加语境感知自动补全，支持NPC/物品/出口智能提示"
```

---

### Task 5: 交互式快捷标签

**Files:**
- Modify: `src/tavern/cli/renderer.py` (render_action_hints)
- Modify: `src/tavern/cli/app.py` (_generate_action_hints, run loop, _handle_free_input)
- Test: `tests/cli/test_renderer.py`
- New test: `tests/cli/test_app_hints.py`

- [ ] **Step 1: Write failing tests for render_action_hints**

In `tests/cli/test_renderer.py`, add at the end:

```python
class TestActionHints:
    def test_render_action_hints_outputs_numbered_hints(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        renderer.render_action_hints(["和旅行者交谈", "查看旧告示", "前往north"])
        output = console.file.getvalue()
        assert "1" in output
        assert "2" in output
        assert "3" in output
        assert "旅行者" in output
        assert "旧告示" in output

    def test_render_action_hints_empty_list(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        renderer.render_action_hints([])
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_render_action_hints_single_hint(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        renderer.render_action_hints(["环顾四周"])
        output = console.file.getvalue()
        assert "1" in output
        assert "环顾四周" in output
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestActionHints -x -v 2>&1 | tail -20
```

Expect: FAIL (no `render_action_hints` method).

- [ ] **Step 2: Write failing tests for _generate_action_hints and number input mapping**

Create `tests/cli/test_app_hints.py`:

```python
import pytest

from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def _make_state(
    npcs: tuple[str, ...] = (),
    items: tuple[str, ...] = (),
    exits: dict | None = None,
    all_characters: dict | None = None,
    all_items: dict | None = None,
) -> WorldState:
    exit_map = exits or {}
    chars = all_characters or {}
    chars["player"] = Character(
        id="player",
        name="冒险者",
        role=CharacterRole.PLAYER,
        stats={"hp": 100, "gold": 10},
        location_id="tavern_hall",
    )
    items_dict = all_items or {}
    return WorldState(
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                exits=exit_map,
                items=items,
                npcs=npcs,
            ),
        },
        characters=chars,
        items=items_dict,
    )


class TestGenerateActionHints:
    def test_npc_present_generates_talk_hint(self):
        from tavern.cli.app import GameApp

        state = _make_state(
            npcs=("traveler",),
            all_characters={
                "traveler": Character(
                    id="traveler",
                    name="旅行者",
                    role=CharacterRole.NPC,
                    location_id="tavern_hall",
                ),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("旅行者" in h and "交谈" in h for h in hints)

    def test_item_present_generates_inspect_hint(self):
        from tavern.cli.app import GameApp

        state = _make_state(
            items=("old_notice",),
            all_items={
                "old_notice": Item(
                    id="old_notice",
                    name="旧告示",
                    description="一张告示",
                ),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("旧告示" in h and "查看" in h for h in hints)

    def test_exit_generates_move_hint(self):
        from tavern.cli.app import GameApp

        state = _make_state(
            exits={"north": Exit(target="bar_area", description="通往吧台")},
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("north" in h and "前往" in h for h in hints)

    def test_empty_scene_generates_fallback(self):
        from tavern.cli.app import GameApp

        state = _make_state()
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("环顾四周" in h for h in hints)

    def test_max_three_hints(self):
        from tavern.cli.app import GameApp

        state = _make_state(
            npcs=("traveler", "bartender_grim"),
            items=("old_notice",),
            exits={
                "north": Exit(target="bar_area"),
                "east": Exit(target="corridor"),
            },
            all_characters={
                "traveler": Character(
                    id="traveler",
                    name="旅行者",
                    role=CharacterRole.NPC,
                    location_id="tavern_hall",
                ),
                "bartender_grim": Character(
                    id="bartender_grim",
                    name="格里姆",
                    role=CharacterRole.NPC,
                    location_id="tavern_hall",
                ),
            },
            all_items={
                "old_notice": Item(
                    id="old_notice",
                    name="旧告示",
                    description="告示",
                ),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert len(hints) <= 3

    def test_diverse_hint_types(self):
        from tavern.cli.app import GameApp

        state = _make_state(
            npcs=("traveler",),
            items=("old_notice",),
            exits={"north": Exit(target="bar_area")},
            all_characters={
                "traveler": Character(
                    id="traveler",
                    name="旅行者",
                    role=CharacterRole.NPC,
                    location_id="tavern_hall",
                ),
            },
            all_items={
                "old_notice": Item(
                    id="old_notice",
                    name="旧告示",
                    description="告示",
                ),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert len(hints) == 3
        hint_text = " ".join(hints)
        assert "交谈" in hint_text
        assert "查看" in hint_text
        assert "前往" in hint_text
```

Run:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_app_hints.py -x -v 2>&1 | tail -20
```

Expect: FAIL (no `_generate_action_hints_from_state` static method).

- [ ] **Step 3: Implement render_action_hints in Renderer**

In `src/tavern/cli/renderer.py`, add this method to the `Renderer` class (after `render_ending`, before `get_dialogue_input`):

```python
    def render_action_hints(self, hints: list[str]) -> None:
        if not hints:
            return
        parts = [f"[dim][{i + 1}][/] [cyan]{h}[/]" for i, h in enumerate(hints)]
        self.console.print("  ".join(parts))
```

- [ ] **Step 4: Implement _generate_action_hints_from_state and instance method in GameApp**

In `src/tavern/cli/app.py`, add these methods to the `GameApp` class (before the `run` method, after `_load_config`):

```python
    @staticmethod
    def _generate_action_hints_from_state(state: WorldState) -> list[str]:
        player = state.characters.get(state.player_id)
        if player is None:
            return ["环顾四周"]

        location = state.locations.get(player.location_id)
        if location is None:
            return ["环顾四周"]

        hints: list[str] = []
        hint_types_used: set[str] = set()

        for npc_id in location.npcs:
            if len(hints) >= 3:
                break
            npc = state.characters.get(npc_id)
            if npc and "talk" not in hint_types_used:
                hints.append(f"和{npc.name}交谈")
                hint_types_used.add("talk")

        for item_id in location.items:
            if len(hints) >= 3:
                break
            item = state.items.get(item_id)
            if item and "inspect" not in hint_types_used:
                hints.append(f"查看{item.name}")
                hint_types_used.add("inspect")

        for direction in location.exits:
            if len(hints) >= 3:
                break
            if "move" not in hint_types_used:
                hints.append(f"前往{direction}")
                hint_types_used.add("move")

        if not hints:
            hints.append("环顾四周")

        return hints[:3]

    def _generate_action_hints(self) -> list[str]:
        return self._generate_action_hints_from_state(self.state)
```

- [ ] **Step 5: Add _last_hints tracking and number-input mapping in the run loop**

In `src/tavern/cli/app.py`, add `_last_hints` to `__init__` (after `self._game_over = False`, around line 105):

```python
        self._last_hints: list[str] = []
```

In the `run()` method, add number-input mapping after `if not user_input: continue` and before `command = user_input.lower().strip()` (around line 164-167):

```python
    async def run(self) -> None:
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
        self._renderer.render_status_bar(self.state)

        while not self._game_over:
            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                user_input = await self._renderer.get_dialogue_input()
            else:
                user_input = await self._renderer.get_input()

            if not user_input:
                continue

            if (
                user_input in ("1", "2", "3")
                and self._last_hints
                and not (self._dialogue_manager.is_active and self._dialogue_ctx is not None)
            ):
                idx = int(user_input) - 1
                if 0 <= idx < len(self._last_hints):
                    user_input = self._last_hints[idx]

            command = user_input.lower().strip()
```

- [ ] **Step 6: Call render_action_hints after narrative in _handle_free_input**

In `src/tavern/cli/app.py`, in `_handle_free_input`, right before the final `self._renderer.render_status_bar(self.state)` at line 371, add:

```python
        self._pending_story_hints.clear()
        self._last_hints = self._generate_action_hints()
        self._renderer.render_action_hints(self._last_hints)
        self._renderer.render_status_bar(self.state)
```

This replaces the existing lines 370-371:
```python
        self._pending_story_hints.clear()
        self._renderer.render_status_bar(self.state)
```

- [ ] **Step 7: Run tests — confirm GREEN**

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/test_renderer.py::TestActionHints tests/cli/test_app_hints.py -x -v 2>&1 | tail -30
```

Run full suite:
```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/cli/ -x -v 2>&1 | tail -30
```

- [ ] **Step 8: Commit**

```bash
cd /Users/makoto/Downloads/work/chatbot && git add src/tavern/cli/renderer.py src/tavern/cli/app.py tests/cli/test_renderer.py tests/cli/test_app_hints.py && git commit -m "feat: 添加交互式快捷标签，支持数字快捷键选择下一步行动"
```

---

## Final Verification

After all 5 tasks are complete, run the full test suite:

```bash
cd /Users/makoto/Downloads/work/chatbot && python -m pytest tests/ -x -v 2>&1 | tail -40
```

Confirm no regressions and all new tests pass.
