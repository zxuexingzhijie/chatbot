# Card-Style Hint Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bottom-toolbar horizontal hint selector with a vertical card-style selection UI using `prompt_toolkit.Application`.

**Architecture:** A new `get_input_with_card_hints()` method on `Renderer` creates a `prompt_toolkit.Application` with a `FormattedTextControl` rendering 3 hints + 1 free-input line as a vertical list. The selected item gets a box-drawing border. Key bindings handle navigation, text input, and selection.

**Tech Stack:** prompt_toolkit (Application, Layout, Window, FormattedTextControl, KeyBindings)

---

### Task 1: Write card hint selector tests

**Files:**
- Modify: `tests/cli/test_renderer.py:214-227` (replace existing hint tests)
- Modify: `tests/cli/test_renderer.py:621-646` (remove render_action_hints tests)

- [ ] **Step 1: Replace `test_get_input_with_hints_callable` and `test_get_input_with_hints_empty_falls_back` with new card hint tests**

In `tests/cli/test_renderer.py`, replace lines 214-227:

```python
    def test_get_input_with_card_hints_callable(self):
        from rich.console import Console
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        assert callable(renderer.get_input_with_card_hints)

    @pytest.mark.asyncio
    async def test_get_input_with_card_hints_empty_falls_back(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        with patch.object(renderer, "get_input", new_callable=AsyncMock, return_value="test") as mock_get:
            result = await renderer.get_input_with_card_hints([])
            mock_get.assert_called_once()
            assert result == "test"
```

- [ ] **Step 2: Add tests for card hint selection logic**

Add after the tests above, still in `TestInputMethods`:

```python
    def test_card_hint_build_display_selected_has_border(self):
        from tavern.cli.renderer import _build_card_display
        lines = _build_card_display(["查看告示", "询问旅行者", "前往吧台"], selected=0, input_text="")
        text = "".join(frag[1] for frag in lines)
        assert "╭" in text
        assert "查看告示" in text

    def test_card_hint_build_display_unselected_no_border(self):
        from tavern.cli.renderer import _build_card_display
        lines = _build_card_display(["查看告示", "询问旅行者", "前往吧台"], selected=0, input_text="")
        text = "".join(frag[1] for frag in lines)
        # Count border characters - only selected item should have them
        border_sections = text.split("╭")
        assert len(border_sections) == 2  # one split = one border

    def test_card_hint_build_display_input_row_present(self):
        from tavern.cli.renderer import _build_card_display
        lines = _build_card_display(["查看告示"], selected=0, input_text="")
        text = "".join(frag[1] for frag in lines)
        assert "▸" in text

    def test_card_hint_build_display_input_selected_has_border(self):
        from tavern.cli.renderer import _build_card_display
        lines = _build_card_display(["查看告示"], selected=1, input_text="你好")
        text = "".join(frag[1] for frag in lines)
        border_sections = text.split("╭")
        assert len(border_sections) == 2
        assert "你好" in text

    def test_card_hint_build_display_nav_help(self):
        from tavern.cli.renderer import _build_card_display
        lines = _build_card_display(["查看告示"], selected=0, input_text="")
        text = "".join(frag[1] for frag in lines)
        assert "↑↓" in text
        assert "确认" in text
```

- [ ] **Step 3: Remove `TestActionHints` class (render_action_hints tests)**

Delete the entire `TestActionHints` class (lines 621-646) from `tests/cli/test_renderer.py`:

```python
# DELETE this entire class:
# class TestActionHints:
#     def test_render_action_hints_outputs_numbered_hints ...
#     def test_render_action_hints_empty_list ...
#     def test_render_action_hints_single_hint ...
```

- [ ] **Step 4: Run tests to verify new tests fail**

Run: `python3 -m pytest tests/cli/test_renderer.py::TestInputMethods -v`
Expected: FAIL — `_build_card_display` not found, `get_input_with_card_hints` not found

- [ ] **Step 5: Commit test changes**

```bash
git add tests/cli/test_renderer.py
git commit -m "test: add card hint selector tests, remove render_action_hints tests"
```

---

### Task 2: Implement `_build_card_display` helper

**Files:**
- Modify: `src/tavern/cli/renderer.py` (add module-level function before `Renderer` class)

- [ ] **Step 1: Add `_build_card_display` function**

Add after line 57 (`_TYPEWRITER_CHAR_DELAY`), before the `SlashCommandCompleter` class:

```python
_CARD_MIN_WIDTH: int = 20
_CARD_MAX_WIDTH: int = 40


def _build_card_display(
    hints: list[str],
    selected: int,
    input_text: str,
) -> list[tuple[str, str]]:
    total = len(hints) + 1  # hints + input row
    input_display = f"▸ {input_text}_" if selected == len(hints) else f"▸ {input_text or '_'}"

    all_labels = list(hints) + [input_display]
    max_len = max(len(label) for label in all_labels)
    width = max(_CARD_MIN_WIDTH, min(_CARD_MAX_WIDTH, max_len + 2))

    top = f"  ╭{'─' * (width + 2)}╮\n"
    bot = f"  ╰{'─' * (width + 2)}╯\n"

    fragments: list[tuple[str, str]] = []

    for i, label in enumerate(all_labels):
        padded = label + " " * (width - len(label))
        if i == selected:
            fragments.append(("class:card.border", top))
            fragments.append(("class:card.border", "  │ "))
            fragments.append(("class:card.selected", padded))
            fragments.append(("class:card.border", " │\n"))
            fragments.append(("class:card.border", bot))
        else:
            fragments.append(("", f"    {label}\n"))

    fragments.append(("", "\n"))
    fragments.append(("class:card.nav", "  ↑↓ 切换  ↵ 确认\n"))

    return fragments
```

- [ ] **Step 2: Run tests to verify `_build_card_display` tests pass**

Run: `python3 -m pytest tests/cli/test_renderer.py::TestInputMethods::test_card_hint_build_display_selected_has_border tests/cli/test_renderer.py::TestInputMethods::test_card_hint_build_display_unselected_no_border tests/cli/test_renderer.py::TestInputMethods::test_card_hint_build_display_input_row_present tests/cli/test_renderer.py::TestInputMethods::test_card_hint_build_display_input_selected_has_border tests/cli/test_renderer.py::TestInputMethods::test_card_hint_build_display_nav_help -v`

Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add src/tavern/cli/renderer.py
git commit -m "feat: add _build_card_display helper for card-style hint rendering"
```

---

### Task 3: Implement `get_input_with_card_hints`

**Files:**
- Modify: `src/tavern/cli/renderer.py` (replace `get_input_with_hints`, remove `render_action_hints`, add imports)

- [ ] **Step 1: Add new imports at top of renderer.py**

Add to the imports section (after `from prompt_toolkit.key_binding import KeyBindings`):

```python
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl as PTKFormattedTextControl
```

Note: We alias to `PTKFormattedTextControl` to avoid confusion since `FormattedTextControl` could conflict with other prompt_toolkit imports. Alternatively, just import as-is if there's no conflict.

- [ ] **Step 2: Replace `get_input_with_hints` with `get_input_with_card_hints` on the `Renderer` class**

Replace lines 367-429 (`get_input_with_hints` method) with:

```python
    async def get_input_with_card_hints(self, hints: list[str]) -> str:
        if not hints:
            return await self.get_input()

        selected_index = [0]
        input_text = [""]
        total = len(hints) + 1

        def _get_display():
            return _build_card_display(hints, selected_index[0], input_text[0])

        bindings = KeyBindings()

        @bindings.add("up")
        def _up(event):
            selected_index[0] = (selected_index[0] - 1) % total

        @bindings.add("down")
        def _down(event):
            selected_index[0] = (selected_index[0] + 1) % total

        @bindings.add("enter")
        def _enter(event):
            idx = selected_index[0]
            if idx < len(hints):
                event.app.exit(result=hints[idx])
            elif input_text[0].strip():
                event.app.exit(result=input_text[0].strip())

        @bindings.add("c-c")
        def _ctrl_c(event):
            event.app.exit(result="/quit")

        @bindings.add("c-d")
        def _ctrl_d(event):
            event.app.exit(result="/quit")

        @bindings.add("backspace")
        def _backspace(event):
            if selected_index[0] == len(hints) and input_text[0]:
                input_text[0] = input_text[0][:-1]

        @bindings.add("<any>")
        def _any_key(event):
            char = event.data
            if not char.isprintable() or len(char) != 1:
                return
            is_input_row = selected_index[0] == len(hints)
            is_shortcut = (
                not input_text[0]
                and char in "123"
                and int(char) <= len(hints)
            )
            if is_shortcut and not is_input_row:
                event.app.exit(result=hints[int(char) - 1])
                return
            if not is_input_row:
                selected_index[0] = len(hints)
            input_text[0] += char

        control = PTKFormattedTextControl(_get_display)
        layout = Layout(Window(content=control, dont_extend_height=True))
        style = _card_style()

        app: Application[str] = Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
            full_screen=False,
        )

        result = await app.run_async()
        return result or "/quit"
```

- [ ] **Step 3: Add `_card_style` helper function**

Add near the top of the file, after the `_build_card_display` function:

```python
def _card_style():
    from prompt_toolkit.styles import Style
    return Style.from_dict({
        "card.border": "ansicyan",
        "card.selected": "bold",
        "card.nav": "ansigray",
    })
```

- [ ] **Step 4: Delete `render_action_hints` method**

Remove lines 535-539 from the `Renderer` class:

```python
# DELETE:
#     def render_action_hints(self, hints: list[str]) -> None:
#         if not hints:
#             return
#         parts = [f"[dim][{i + 1}][/] [cyan]{h}[/]" for i, h in enumerate(hints)]
#         self.console.print("  ".join(parts))
```

- [ ] **Step 5: Run card hint tests**

Run: `python3 -m pytest tests/cli/test_renderer.py::TestInputMethods -v`
Expected: All PASS (including `test_get_input_with_card_hints_callable` and `test_get_input_with_card_hints_empty_falls_back`)

- [ ] **Step 6: Commit**

```bash
git add src/tavern/cli/renderer.py
git commit -m "feat: implement card-style hint selector with prompt_toolkit Application"
```

---

### Task 4: Update app.py integration

**Files:**
- Modify: `src/tavern/cli/app.py:271` (one line change)

- [ ] **Step 1: Replace `get_input_with_hints` call with `get_input_with_card_hints`**

In `src/tavern/cli/app.py`, change line 271 from:

```python
                user_input = await self._renderer.get_input_with_hints(self._last_hints)
```

to:

```python
                user_input = await self._renderer.get_input_with_card_hints(self._last_hints)
```

- [ ] **Step 2: Run all tests**

Run: `python3 -m pytest tests/ -x -q`
Expected: 492 passed (or close — the removed `TestActionHints` tests reduce the count by 3, but new tests add ~7)

- [ ] **Step 3: Commit**

```bash
git add src/tavern/cli/app.py
git commit -m "feat: integrate card hint selector into main game loop"
```

---

### Task 5: Clean up and full verification

**Files:**
- Verify: all test files that reference old method names

- [ ] **Step 1: Search for any remaining references to old methods**

```bash
grep -rn "get_input_with_hints\|render_action_hints" src/ tests/
```

Expected: No results (all references should be removed or renamed)

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass, no warnings about missing methods

- [ ] **Step 3: Commit any straggler fixes if needed**

```bash
git add -A && git commit -m "chore: clean up old hint method references"
```

Only commit if there were changes. If grep found nothing, skip this step.
