# Phase 5A: 基础设施接线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 1-4 构建的 ContentLoader、KeybindingResolver、Markdown 渲染组件接入运行时，实现端到端生效。

**Architecture:** §0 修复 Renderer.get_input() 签名不一致（现存 bug），§1 创建 Markdown 内容文件并接入 ContentLoader + CachedPromptBuilder，§2 通过 KeybindingBridge 将 KeybindingResolver 接入 prompt_toolkit，§3 用 rich.Live + rich.Markdown 实现流式 Markdown 渲染。§0 是前置，§1/§2/§3 可并行。

**Tech Stack:** Python 3.14, rich (Live, Markdown), prompt_toolkit (KeyBindings), pytest, frozen dataclasses

---

## File Structure

### New Files
| File | Responsibility |
|------|----------------|
| `src/tavern/content/conditions.py` | 内容条件求值（variant when 表达式） |
| `src/tavern/engine/keybinding_bridge.py` | KeybindingResolver → prompt_toolkit 适配器 |
| `src/tavern/data/scenarios/tavern/content/locations/*.md` (6) | Location Markdown 描述 |
| `src/tavern/data/scenarios/tavern/content/items/*.md` (10) | Item Markdown 描述 |
| `src/tavern/data/scenarios/tavern/content/characters/*.md` (3) | Character Markdown 描述 |
| `tests/content/test_conditions.py` | conditions 测试 |
| `tests/engine/test_keybinding_bridge.py` | KeybindingBridge 测试 |
| `tests/cli/test_renderer_markdown.py` | Markdown 渲染测试 |
| `tests/narrator/test_cached_builder_resolve.py` | resolve_content + condition_evaluator 测试 |

### Modified Files
| File | Changes |
|------|---------|
| `src/tavern/cli/renderer.py:439-443` | get_input 加 config + extra_bindings 参数，render_stream 改 Live+Markdown |
| `src/tavern/narrator/cached_builder.py:24-62` | 加 resolve_content()，build_scene_context 接入 condition_evaluator |
| `src/tavern/cli/app.py:85-90` | 实例化 ContentLoader 并传入 bootstrap |
| `src/tavern/cli/bootstrap.py:17-67` | 注入 KeybindingBridge |
| `src/tavern/engine/fsm.py:62-75` | ModeContext 加 keybinding_bridge 字段 |
| `src/tavern/engine/modes/exploring.py:114-124` | get_keybindings 清空 |
| `src/tavern/engine/modes/dialogue.py:93-99` | get_keybindings 清空 |

---

### Task 1: §0 — Renderer.get_input() 签名对齐

**Files:**
- Modify: `src/tavern/cli/renderer.py:439-443`
- Test: `tests/cli/test_renderer_get_input.py`

- [ ] **Step 1: Write failing test**

```python
# tests/cli/test_renderer_get_input.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.cli.renderer import Renderer
from tavern.engine.fsm import PromptConfig


@pytest.fixture
def renderer():
    console = MagicMock()
    console.status = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
    with patch("tavern.cli.renderer.PromptSession") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.prompt_async = AsyncMock(return_value="test input")
        mock_session_cls.return_value = mock_session
        r = Renderer(console=console)
        r._session = mock_session
        yield r


@pytest.mark.asyncio
async def test_get_input_no_args(renderer):
    """get_input() with no args works (backwards compatible)."""
    result = await renderer.get_input()
    assert result == "test input"


@pytest.mark.asyncio
async def test_get_input_with_prompt_config(renderer):
    """get_input() accepts PromptConfig and uses its prompt_text."""
    config = PromptConfig(prompt_text="对话> ", show_status_bar=False)
    result = await renderer.get_input(config=config)
    assert result == "test input"
    call_args = renderer._session.prompt_async.call_args
    prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    # Verify prompt_text was used (not the default "▸ ")
    assert "对话" in str(prompt_arg)


@pytest.mark.asyncio
async def test_get_input_with_none_config(renderer):
    """get_input(config=None) uses default prompt."""
    result = await renderer.get_input(config=None)
    assert result == "test input"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_renderer_get_input.py -v`
Expected: `test_get_input_with_prompt_config` FAILS because get_input() doesn't accept `config`

- [ ] **Step 3: Implement — modify get_input()**

In `src/tavern/cli/renderer.py`, replace lines 439-443:

```python
    async def get_input(
        self,
        config: PromptConfig | None = None,
        extra_bindings: KeyBindings | None = None,
    ) -> str:
        prompt_text = config.prompt_text if config else "▸ "
        prompt_html = HTML(f"<ansigreen><b>{prompt_text} </b></ansigreen>")
        try:
            session_kwargs: dict = {}
            if extra_bindings is not None:
                from prompt_toolkit.key_binding import merge_key_bindings
                merged = merge_key_bindings([self._session.key_bindings or KeyBindings(), extra_bindings])
                session_kwargs["key_bindings"] = merged
            return (await self._session.prompt_async(prompt_html, **session_kwargs)).strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"
```

Add import at top of file (after existing `from prompt_toolkit.key_binding import KeyBindings`):

```python
from tavern.engine.fsm import PromptConfig
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/cli/test_renderer_get_input.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer_get_input.py
git commit -m "fix(§0): align Renderer.get_input() with GameLoop's PromptConfig call"
```

---

### Task 2: §1a — Content condition evaluator

**Files:**
- Create: `src/tavern/content/conditions.py`
- Test: `tests/content/test_conditions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/content/test_conditions.py
from __future__ import annotations

import pytest

from tavern.content.conditions import evaluate_content_condition


class TestEvaluateContentCondition:
    def test_turn_greater_than_true(self):
        assert evaluate_content_condition("turn > 20", turn=25) is True

    def test_turn_greater_than_false(self):
        assert evaluate_content_condition("turn > 20", turn=15) is False

    def test_turn_greater_than_equal(self):
        assert evaluate_content_condition("turn > 20", turn=20) is False

    def test_turn_less_than(self):
        assert evaluate_content_condition("turn < 10", turn=5) is True

    def test_turn_greater_equal(self):
        assert evaluate_content_condition("turn >= 20", turn=20) is True

    def test_turn_less_equal(self):
        assert evaluate_content_condition("turn <= 5", turn=5) is True

    def test_invalid_expression_returns_false(self):
        assert evaluate_content_condition("invalid stuff", turn=10) is False

    def test_unknown_variable_returns_false(self):
        assert evaluate_content_condition("health > 50", turn=10) is False

    def test_empty_string_returns_false(self):
        assert evaluate_content_condition("", turn=0) is False

    def test_default_turn_zero(self):
        assert evaluate_content_condition("turn > 0", turn=0) is False
        assert evaluate_content_condition("turn >= 0") is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/content/test_conditions.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement conditions.py**

```python
# src/tavern/content/conditions.py
from __future__ import annotations

import re

_CONDITION_PATTERN = re.compile(
    r"^(turn)\s*(>|<|>=|<=|==|!=)\s*(\d+)$"
)

_OPERATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate_content_condition(when: str, *, turn: int = 0, **kwargs: object) -> bool:
    """Evaluate a simple content condition expression.

    Supports: 'turn > N', 'turn < N', 'turn >= N', 'turn <= N',
              'turn == N', 'turn != N'.

    Returns False for unparseable expressions or unknown variables.
    """
    when = when.strip()
    if not when:
        return False

    match = _CONDITION_PATTERN.match(when)
    if match is None:
        return False

    variable, operator, value_str = match.groups()
    variables = {"turn": turn}

    if variable not in variables:
        return False

    op_fn = _OPERATORS.get(operator)
    if op_fn is None:
        return False

    return op_fn(variables[variable], int(value_str))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/content/test_conditions.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/content/conditions.py tests/content/test_conditions.py
git commit -m "feat(§1): add evaluate_content_condition for variant when expressions"
```

---

### Task 3: §1b — CachedPromptBuilder.resolve_content + condition_evaluator 接入

**Files:**
- Modify: `src/tavern/narrator/cached_builder.py:1-62`
- Test: `tests/narrator/test_cached_builder_resolve.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/narrator/test_cached_builder_resolve.py
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tavern.narrator.cached_builder import CachedPromptBuilder
from tavern.narrator.scene_cache import SceneContextCache


def _make_builder(content_loader=None):
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1
    return CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )


class TestResolveContent:
    def test_returns_none_when_no_loader(self):
        builder = _make_builder(content_loader=None)
        assert builder.resolve_content("tavern_hall") is None

    def test_returns_resolved_text(self):
        loader = MagicMock()
        loader.resolve.return_value = "Markdown description"
        builder = _make_builder(content_loader=loader)
        result = builder.resolve_content("old_notice")
        assert result == "Markdown description"
        loader.resolve.assert_called_once_with("old_notice")

    def test_returns_none_when_id_not_found(self):
        loader = MagicMock()
        loader.resolve.return_value = None
        builder = _make_builder(content_loader=loader)
        assert builder.resolve_content("nonexistent") is None


class TestBuildSceneContextWithConditionEvaluator:
    def test_passes_condition_evaluator_to_resolve(self):
        loader = MagicMock()
        loader.resolve.return_value = "Night version of hall"
        builder = _make_builder(content_loader=loader)

        state = MagicMock()
        state.player_location = "tavern_hall"
        state.locations = {
            "tavern_hall": MagicMock(
                description="YAML fallback",
                npcs=(),
                items=(),
                exits={},
                atmosphere="warm",
            )
        }
        state.characters = {}
        state.items = {}
        state.turn = 25

        ctx = builder.build_scene_context(state)
        assert ctx.location_description == "Night version of hall"

        call_args = loader.resolve.call_args
        assert call_args[0][0] == "tavern_hall"
        assert "condition_evaluator" in call_args[1]

    def test_fallback_to_yaml_when_loader_returns_none(self):
        loader = MagicMock()
        loader.resolve.return_value = None
        builder = _make_builder(content_loader=loader)

        state = MagicMock()
        state.player_location = "tavern_hall"
        state.locations = {
            "tavern_hall": MagicMock(
                description="YAML description",
                npcs=(),
                items=(),
                exits={},
                atmosphere="warm",
            )
        }
        state.characters = {}
        state.items = {}
        state.turn = 5

        ctx = builder.build_scene_context(state)
        assert ctx.location_description == "YAML description"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/narrator/test_cached_builder_resolve.py -v`
Expected: FAIL — `resolve_content` not found, `condition_evaluator` not passed

- [ ] **Step 3: Implement changes to cached_builder.py**

Replace `src/tavern/narrator/cached_builder.py` with:

```python
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tavern.content.conditions import evaluate_content_condition
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

    def resolve_content(self, content_id: str) -> str | None:
        if self._content is None:
            return None
        return self._content.resolve(content_id)

    def build_scene_context(self, state: WorldState) -> SceneContext:
        loc_id = state.player_location
        version = self._state_manager.version

        cached = self._cache.get(loc_id, version)
        if cached is not None:
            return cached

        location = state.locations[loc_id]

        description = None
        if self._content is not None:
            description = self._content.resolve(
                loc_id,
                condition_evaluator=lambda when, **kw: evaluate_content_condition(
                    when, turn=state.turn,
                ),
            )
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

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/narrator/test_cached_builder_resolve.py tests/narrator/test_cached_builder.py -v`
Expected: ALL PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/tavern/narrator/cached_builder.py tests/narrator/test_cached_builder_resolve.py
git commit -m "feat(§1): add resolve_content() and wire condition_evaluator in build_scene_context"
```

---

### Task 4: §1c — Markdown 内容文件创建

**Files:**
- Create: `src/tavern/data/scenarios/tavern/content/locations/tavern_hall.md`
- Create: `src/tavern/data/scenarios/tavern/content/locations/tavern_hall.night.md`
- Create: `src/tavern/data/scenarios/tavern/content/locations/bar_area.md`
- Create: `src/tavern/data/scenarios/tavern/content/locations/cellar.md`
- Create: `src/tavern/data/scenarios/tavern/content/locations/corridor.md`
- Create: `src/tavern/data/scenarios/tavern/content/locations/backyard.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/old_notice.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/cellar_key.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/old_barrel.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/abandoned_cart.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/dry_well.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/rusty_box.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/spare_key.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/lost_amulet.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/map_fragment.md`
- Create: `src/tavern/data/scenarios/tavern/content/items/guest_letter.md`
- Create: `src/tavern/data/scenarios/tavern/content/characters/traveler.md`
- Create: `src/tavern/data/scenarios/tavern/content/characters/bartender_grim.md`
- Create: `src/tavern/data/scenarios/tavern/content/characters/mysterious_guest.md`
- Test: `tests/content/test_content_loading.py`

- [ ] **Step 1: Create location Markdown files**

`src/tavern/data/scenarios/tavern/content/locations/tavern_hall.md`:
```markdown
---
id: tavern_hall
type: location
variants:
  - name: night
    when: "turn > 20"
---

推开沉重的橡木门，你走进了「醉龙酒馆」。大厅里弥漫着麦酒和烤肉的香气，壁炉中的火焰投射出温暖的光芒。几张粗糙的木桌散落各处，角落里坐着一位风尘仆仆的旅行者。墙上挂着一张泛黄的告示。
```

`src/tavern/data/scenarios/tavern/content/locations/tavern_hall.night.md`:
```markdown
夜深了，醉龙酒馆的大厅变得安静。壁炉中的火焰已经暗淡下来，只剩几点余烬在灰烬中闪烁。空气中残留着麦酒的气味，大多数客人已经离去。昏暗的烛光在墙上投下摇曳的影子。
```

`src/tavern/data/scenarios/tavern/content/locations/bar_area.md`:
```markdown
---
id: bar_area
type: location
---

长长的橡木吧台后面，酒保格里姆正在擦拭杯子。吧台上摆着各式酒瓶，墙上挂着一面铜质奖牌和一幅褪色的城镇地图。吧台尽头有一扇沉重的铁门，上面挂着一把锁。
```

`src/tavern/data/scenarios/tavern/content/locations/cellar.md`:
```markdown
---
id: cellar
type: location
---

阴暗潮湿的地下室，空气中弥漫着霉味。几个破旧的木桶堆在角落，蜘蛛网挂满了石质墙壁。地面上有一些奇怪的划痕，似乎有什么沉重的东西被拖过。
```

`src/tavern/data/scenarios/tavern/content/locations/corridor.md`:
```markdown
---
id: corridor
type: location
---

狭窄的走廊两侧排列着几扇紧闭的房门。走廊尽头的房间门半掩着，透出昏暗的烛光。一位戴着兜帽的神秘旅客靠在墙边，似乎在等待什么。
```

`src/tavern/data/scenarios/tavern/content/locations/backyard.md`:
```markdown
---
id: backyard
type: location
---

杂草丛生的后院，月光洒在一辆废弃的马车上。马车的篷布已经破烂不堪，但车厢下似乎藏着什么东西。院子角落有一口枯井，井沿上长满了青苔。
```

- [ ] **Step 2: Create item Markdown files**

`src/tavern/data/scenarios/tavern/content/items/old_notice.md`:
```markdown
---
id: old_notice
type: item
---

一张泛黄的告示，上面写着：「警告：近日地下室频繁传出异响，闲人勿入。——酒馆老板 格里姆」
```

`src/tavern/data/scenarios/tavern/content/items/cellar_key.md`:
```markdown
---
id: cellar_key
type: item
---

一把生锈的铁钥匙，上面刻着一个小小的龙形标记。
```

`src/tavern/data/scenarios/tavern/content/items/old_barrel.md`:
```markdown
---
id: old_barrel
type: item
---

几个破旧的木桶，其中一个底部有奇怪的刮痕。
```

`src/tavern/data/scenarios/tavern/content/items/abandoned_cart.md`:
```markdown
---
id: abandoned_cart
type: item
---

一辆破旧的马车，篷布下隐约能看到一个小铁盒。
```

`src/tavern/data/scenarios/tavern/content/items/dry_well.md`:
```markdown
---
id: dry_well
type: item
---

一口枯井，井沿长满青苔，井底黑漆漆的看不到尽头。
```

`src/tavern/data/scenarios/tavern/content/items/rusty_box.md`:
```markdown
---
id: rusty_box
type: item
---

从马车下找到的铁盒，里面有一把备用钥匙。
```

`src/tavern/data/scenarios/tavern/content/items/spare_key.md`:
```markdown
---
id: spare_key
type: item
---

一把形状和地下室钥匙相似的备用钥匙。
```

`src/tavern/data/scenarios/tavern/content/items/lost_amulet.md`:
```markdown
---
id: lost_amulet
type: item
---

一个精致的银质护身符，表面刻着古老的符文，散发着微弱的光芒。
```

`src/tavern/data/scenarios/tavern/content/items/map_fragment.md`:
```markdown
---
id: map_fragment
type: item
---

一张泛黄的羊皮纸碎片，上面标注着城镇地下的密道走向。
```

`src/tavern/data/scenarios/tavern/content/items/guest_letter.md`:
```markdown
---
id: guest_letter
type: item
---

一封密封的信件，火漆上印着一个陌生的徽章。信纸透出淡淡的墨香。
```

- [ ] **Step 3: Create character Markdown files**

Note: YAML 中 characters 没有 description 字段，只有 traits。基于 traits 创建描述。

`src/tavern/data/scenarios/tavern/content/characters/traveler.md`:
```markdown
---
id: traveler
type: character
---

一位风尘仆仆的旅行者，名叫艾琳。她性格友善、健谈，穿着一件已经磨损的旅行斗篷，目光中透着对远方的向往。
```

`src/tavern/data/scenarios/tavern/content/characters/bartender_grim.md`:
```markdown
---
id: bartender_grim
type: character
---

酒保格里姆，一个沉默寡言但警觉的中年人。他身材粗犷，双手布满老茧，擦拭杯子的动作机械而熟练。
```

`src/tavern/data/scenarios/tavern/content/characters/mysterious_guest.md`:
```markdown
---
id: mysterious_guest
type: character
---

一位戴着兜帽的神秘旅客，面容隐在阴影中。他举止冷淡，似乎刻意与周围保持距离，但偶尔会用锐利的目光扫视周围。
```

- [ ] **Step 4: Write integration test — ContentLoader loads all files**

```python
# tests/content/test_content_loading.py
from __future__ import annotations

import pytest
from pathlib import Path

from tavern.content.loader import ContentLoader


@pytest.fixture
def loaded_content():
    content_dir = Path(__file__).resolve().parents[2] / "src" / "tavern" / "data" / "scenarios" / "tavern" / "content"
    loader = ContentLoader()
    loader.load_directory(content_dir)
    return loader


class TestContentFilesLoaded:
    LOCATION_IDS = ["tavern_hall", "bar_area", "cellar", "corridor", "backyard"]
    ITEM_IDS = [
        "old_notice", "cellar_key", "old_barrel", "abandoned_cart",
        "dry_well", "rusty_box", "spare_key", "lost_amulet",
        "map_fragment", "guest_letter",
    ]
    CHARACTER_IDS = ["traveler", "bartender_grim", "mysterious_guest"]

    def test_all_locations_loaded(self, loaded_content):
        for loc_id in self.LOCATION_IDS:
            entry = loaded_content.entries.get(loc_id)
            assert entry is not None, f"Missing location: {loc_id}"
            assert entry.content_type == "location"
            assert len(entry.body) > 0

    def test_all_items_loaded(self, loaded_content):
        for item_id in self.ITEM_IDS:
            entry = loaded_content.entries.get(item_id)
            assert entry is not None, f"Missing item: {item_id}"
            assert entry.content_type == "item"
            assert len(entry.body) > 0

    def test_all_characters_loaded(self, loaded_content):
        for char_id in self.CHARACTER_IDS:
            entry = loaded_content.entries.get(char_id)
            assert entry is not None, f"Missing character: {char_id}"
            assert entry.content_type == "character"
            assert len(entry.body) > 0

    def test_tavern_hall_has_night_variant(self, loaded_content):
        entry = loaded_content.entries["tavern_hall"]
        assert len(entry.variant_defs) == 1
        assert entry.variant_defs[0].name == "night"
        assert entry.variant_defs[0].when == "turn > 20"
        assert "night" in entry.variants
        assert len(entry.variants["night"]) > 0

    def test_resolve_tavern_hall_default(self, loaded_content):
        body = loaded_content.resolve("tavern_hall")
        assert "醉龙酒馆" in body

    def test_resolve_tavern_hall_night_variant(self, loaded_content):
        from tavern.content.conditions import evaluate_content_condition
        body = loaded_content.resolve(
            "tavern_hall",
            condition_evaluator=lambda when, **kw: evaluate_content_condition(when, turn=25),
        )
        assert "夜深" in body or "暗淡" in body

    def test_total_entry_count(self, loaded_content):
        assert len(loaded_content.entries) == 18  # 5 loc + 10 item + 3 char
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/content/test_content_loading.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/data/scenarios/tavern/content/ tests/content/test_content_loading.py
git commit -m "feat(§1): create Markdown content files for all locations, items, characters"
```

---

### Task 5: §1d — GameApp 接入 ContentLoader

**Files:**
- Modify: `src/tavern/cli/app.py:85-90`

- [ ] **Step 1: Modify app.py to instantiate ContentLoader**

In `src/tavern/cli/app.py`, after line 89 (`self._scenario_path = scenario_path`), add ContentLoader setup. Replace lines 85-90:

```python
        self._scenario_path = scenario_path

        from tavern.content.loader import ContentLoader
        content_loader = ContentLoader()
        content_dir = scenario_path / "content"
        if content_dir.exists():
            content_loader.load_directory(content_dir)
        else:
            content_loader = None
```

Then modify the `bootstrap()` call (lines 115-126) to pass `content_loader`:

```python
        self._game_loop = bootstrap(
            state_manager=self._state_manager,
            renderer=self._renderer,
            dialogue_manager=self._dialogue_manager,
            narrator=self._narrator,
            memory=self._memory,
            persistence=self._save_manager,
            story_engine=self._story_engine,
            intent_parser=self._parser,
            logger=logger,
            game_logger=self._game_logger,
            content_loader=content_loader,
        )
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/tavern/cli/app.py
git commit -m "feat(§1): wire ContentLoader into GameApp → bootstrap pipeline"
```

---

### Task 6: §2a — KeybindingBridge

**Files:**
- Create: `src/tavern/engine/keybinding_bridge.py`
- Test: `tests/engine/test_keybinding_bridge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/engine/test_keybinding_bridge.py
from __future__ import annotations

import pytest

from tavern.engine.fsm import GameMode, Keybinding
from tavern.engine.keybindings import (
    DEFAULT_BINDINGS,
    InputMode,
    KeybindingBlock,
    KeybindingResolver,
)
from tavern.engine.keybinding_bridge import KeybindingBridge


@pytest.fixture
def bridge():
    resolver = KeybindingResolver(DEFAULT_BINDINGS)
    return KeybindingBridge(resolver)


class TestActionToText:
    def test_move_north_maps_to_chinese(self, bridge):
        assert bridge.ACTION_TO_TEXT["move_north"] == "前往北方"

    def test_look_around_maps_to_slash_command(self, bridge):
        assert bridge.ACTION_TO_TEXT["look_around"] == "/look"

    def test_all_exploring_actions_have_mapping(self, bridge):
        exploring_block = next(
            b for b in DEFAULT_BINDINGS if b.context == GameMode.EXPLORING
        )
        for kb in exploring_block.bindings:
            assert kb.action in bridge.ACTION_TO_TEXT, (
                f"Missing ACTION_TO_TEXT mapping for {kb.action}"
            )


class TestBuildPtkBindings:
    def test_returns_key_bindings_object(self, bridge):
        from prompt_toolkit.key_binding import KeyBindings
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.EXPLORING, on_action=actions.append,
        )
        assert isinstance(bindings, KeyBindings)

    def test_exploring_bindings_count(self, bridge):
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.EXPLORING, on_action=actions.append,
        )
        assert len(bindings.bindings) > 0

    def test_unknown_mode_returns_empty_bindings(self, bridge):
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.INVENTORY, on_action=actions.append,
        )
        assert len(bindings.bindings) == 0


class TestGetBindingsForHelp:
    def test_exploring_help_returns_tuples(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.EXPLORING)
        assert len(result) > 0
        for key, desc in result:
            assert isinstance(key, str)
            assert isinstance(desc, str)

    def test_exploring_help_contains_nsew(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.EXPLORING)
        keys = [k for k, _ in result]
        assert "n" in keys
        assert "s" in keys

    def test_empty_mode_returns_empty(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.INVENTORY)
        assert result == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/engine/test_keybinding_bridge.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement keybinding_bridge.py**

```python
# src/tavern/engine/keybinding_bridge.py
from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit.key_binding import KeyBindings

from tavern.engine.fsm import GameMode
from tavern.engine.keybindings import KeybindingResolver


# Temporary hardcoded Chinese mapping.
# When i18n support is needed, migrate to a config file.
_ACTION_TO_TEXT: dict[str, str] = {
    "move_north": "前往北方",
    "move_south": "前往南方",
    "move_east": "前往东方",
    "move_west": "前往西方",
    "look_around": "/look",
    "open_inventory": "/inventory",
    "talk_nearest": "和最近的人交谈",
    "show_help": "/help",
    "save_game": "/save",
    "end_dialogue": "bye",
    "select_hint_1": "1",
    "select_hint_2": "2",
    "select_hint_3": "3",
}


class KeybindingBridge:
    """Adapts KeybindingResolver mappings into prompt_toolkit KeyBindings."""

    ACTION_TO_TEXT: dict[str, str] = _ACTION_TO_TEXT

    def __init__(self, resolver: KeybindingResolver) -> None:
        self._resolver = resolver

    def build_ptk_bindings(
        self,
        mode: GameMode,
        on_action: Callable[[str], None],
    ) -> KeyBindings:
        bindings = KeyBindings()
        context_map = self._resolver._by_context.get(mode, {})

        for key, action in context_map.items():
            text = self.ACTION_TO_TEXT.get(action)
            if text is None:
                continue
            # Capture key/text in closure via default args
            self._register_key(bindings, key, text, on_action)

        return bindings

    @staticmethod
    def _register_key(
        bindings: KeyBindings,
        key: str,
        text: str,
        on_action: Callable[[str], None],
    ) -> None:
        ptk_key = key.replace("ctrl+", "c-")

        @bindings.add(ptk_key)
        def handler(event, _text: str = text, _on_action: Callable = on_action) -> None:
            _on_action(_text)
            event.app.exit(result=_text)

    def get_bindings_for_help(self, mode: GameMode) -> list[tuple[str, str]]:
        context_map = self._resolver._by_context.get(mode, {})
        result: list[tuple[str, str]] = []
        for key, action in context_map.items():
            # Find the description from the original bindings
            for block in self._resolver._blocks if hasattr(self._resolver, "_blocks") else ():
                if block.context == mode:
                    for kb in block.bindings:
                        if kb.key == key:
                            result.append((key, kb.description))
                            break
            else:
                text = self.ACTION_TO_TEXT.get(action, action)
                result.append((key, text))
        return result
```

Wait — `KeybindingResolver` doesn't expose `_blocks`. Let me fix `get_bindings_for_help` to work with what's available:

```python
# src/tavern/engine/keybinding_bridge.py
from __future__ import annotations

from collections.abc import Callable, Sequence

from prompt_toolkit.key_binding import KeyBindings

from tavern.engine.fsm import GameMode
from tavern.engine.keybindings import KeybindingBlock, KeybindingResolver


# Temporary hardcoded Chinese mapping.
# When i18n support is needed, migrate to a config file.
_ACTION_TO_TEXT: dict[str, str] = {
    "move_north": "前往北方",
    "move_south": "前往南方",
    "move_east": "前往东方",
    "move_west": "前往西方",
    "look_around": "/look",
    "open_inventory": "/inventory",
    "talk_nearest": "和最近的人交谈",
    "show_help": "/help",
    "save_game": "/save",
    "end_dialogue": "bye",
    "select_hint_1": "1",
    "select_hint_2": "2",
    "select_hint_3": "3",
}


class KeybindingBridge:
    """Adapts KeybindingResolver mappings into prompt_toolkit KeyBindings."""

    ACTION_TO_TEXT: dict[str, str] = _ACTION_TO_TEXT

    def __init__(
        self,
        resolver: KeybindingResolver,
        blocks: Sequence[KeybindingBlock] = (),
    ) -> None:
        self._resolver = resolver
        self._blocks = tuple(blocks)

    def build_ptk_bindings(
        self,
        mode: GameMode,
        on_action: Callable[[str], None],
    ) -> KeyBindings:
        bindings = KeyBindings()
        context_map = self._resolver._by_context.get(mode, {})

        for key, action in context_map.items():
            text = self.ACTION_TO_TEXT.get(action)
            if text is None:
                continue
            self._register_key(bindings, key, text, on_action)

        return bindings

    @staticmethod
    def _register_key(
        bindings: KeyBindings,
        key: str,
        text: str,
        on_action: Callable[[str], None],
    ) -> None:
        ptk_key = key.replace("ctrl+", "c-")

        @bindings.add(ptk_key)
        def handler(event, _text: str = text, _on_action: Callable = on_action) -> None:
            _on_action(_text)
            event.app.exit(result=_text)

    def get_bindings_for_help(self, mode: GameMode) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for block in self._blocks:
            if block.context == mode:
                for kb in block.bindings:
                    result.append((kb.key, kb.description))
        return result
```

Update the fixture in the test to pass blocks:

```python
@pytest.fixture
def bridge():
    resolver = KeybindingResolver(DEFAULT_BINDINGS)
    return KeybindingBridge(resolver, blocks=DEFAULT_BINDINGS)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/engine/test_keybinding_bridge.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tavern/engine/keybinding_bridge.py tests/engine/test_keybinding_bridge.py
git commit -m "feat(§2): implement KeybindingBridge adapter for prompt_toolkit"
```

---

### Task 7: §2b — ModeHandler.get_keybindings 清空 + bootstrap 注入

**Files:**
- Modify: `src/tavern/engine/modes/exploring.py:114-124`
- Modify: `src/tavern/engine/modes/dialogue.py:93-99`
- Modify: `src/tavern/engine/fsm.py:62-75`
- Modify: `src/tavern/cli/bootstrap.py:1-67`

- [ ] **Step 1: Clear ExploringModeHandler.get_keybindings()**

In `src/tavern/engine/modes/exploring.py`, replace lines 114-124:

```python
    def get_keybindings(self) -> list[Keybinding]:
        return []
```

- [ ] **Step 2: Clear DialogueModeHandler.get_keybindings()**

In `src/tavern/engine/modes/dialogue.py`, replace lines 93-99:

```python
    def get_keybindings(self) -> list[Keybinding]:
        return []
```

- [ ] **Step 3: Add keybinding_bridge to ModeContext**

In `src/tavern/engine/fsm.py`, after line 75 (`game_logger: Any = None`), add:

```python
    keybinding_bridge: Any = None
```

- [ ] **Step 4: Wire KeybindingBridge in bootstrap.py**

In `src/tavern/cli/bootstrap.py`, add imports:

```python
from tavern.engine.keybinding_bridge import KeybindingBridge
from tavern.engine.keybindings import DEFAULT_BINDINGS, KeybindingResolver
```

After `action_registry = ActionRegistry(build_all_actions())` (line 33), add:

```python
    keybinding_resolver = KeybindingResolver(DEFAULT_BINDINGS)
    keybinding_bridge = KeybindingBridge(keybinding_resolver, blocks=DEFAULT_BINDINGS)
```

Add `keybinding_bridge=keybinding_bridge` to `ModeContext(...)` constructor (after `game_logger=game_logger`).

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tavern/engine/modes/exploring.py src/tavern/engine/modes/dialogue.py src/tavern/engine/fsm.py src/tavern/cli/bootstrap.py
git commit -m "feat(§2): clear hardcoded keybindings, inject KeybindingBridge via bootstrap"
```

---

### Task 8: §3 — Markdown 渲染

**Files:**
- Modify: `src/tavern/cli/renderer.py:45-52, 293-314, 390-401`
- Test: `tests/cli/test_renderer_markdown.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cli/test_renderer_markdown.py
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from io import StringIO

from rich.console import Console

from tavern.cli.renderer import Renderer, _LIVE_REFRESH_RATE


class TestLiveRefreshRateConstant:
    def test_exists_and_reasonable(self):
        assert isinstance(_LIVE_REFRESH_RATE, (int, float))
        assert 5 <= _LIVE_REFRESH_RATE <= 30


class TestRenderStreamMarkdown:
    @pytest.mark.asyncio
    async def test_render_stream_accumulates_and_renders_markdown(self):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=False)

        async def fake_stream():
            yield "Hello "
            yield "**world**"

        with patch("tavern.cli.renderer.Live") as mock_live_cls:
            mock_live = MagicMock()
            mock_live.__enter__ = MagicMock(return_value=mock_live)
            mock_live.__exit__ = MagicMock(return_value=False)
            mock_live_cls.return_value = mock_live

            await renderer.render_stream(fake_stream())

            assert mock_live.update.call_count == 2

    @pytest.mark.asyncio
    async def test_render_stream_typewriter_pauses(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)

        chunks = []

        async def fake_stream():
            yield "句子结束。"
            yield "继续"

        with patch("tavern.cli.renderer.Live") as mock_live_cls:
            mock_live = MagicMock()
            mock_live.__enter__ = MagicMock(return_value=mock_live)
            mock_live.__exit__ = MagicMock(return_value=False)
            mock_live_cls.return_value = mock_live

            with patch("asyncio.sleep", new_callable=lambda: MagicMock(side_effect=lambda _: asyncio.sleep(0))) as mock_sleep:
                await renderer.render_stream(fake_stream())
                assert mock_sleep.call_count >= 1


class TestRenderMarkdownText:
    def test_renders_markdown_to_console(self):
        from tavern.cli.renderer import render_markdown_text
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        render_markdown_text(console, "**bold text**")
        rendered = output.getvalue()
        assert "bold text" in rendered
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/cli/test_renderer_markdown.py -v`
Expected: FAIL — `_LIVE_REFRESH_RATE` not found, `render_markdown_text` not found

- [ ] **Step 3: Implement — add constant and render_markdown_text**

In `src/tavern/cli/renderer.py`, after `_CARD_MAX_WIDTH: int = 40` (line 65), add:

```python
_LIVE_REFRESH_RATE: int = 15
```

At the end of the file (after `get_dialogue_input`), add:

```python
def render_markdown_text(console: Console, text: str) -> None:
    from rich.markdown import Markdown
    console.print(Markdown(text))
```

- [ ] **Step 4: Implement — replace render_stream with Live+Markdown**

Replace `render_stream` method (lines 293-314) with:

```python
    async def render_stream(self, stream, *, atmosphere: str = "neutral") -> None:
        from rich.live import Live
        from rich.markdown import Markdown
        from rich.styled import Styled

        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        buffer = ""
        try:
            with Live(
                Styled(Markdown(""), style=style),
                console=self.console,
                refresh_per_second=_LIVE_REFRESH_RATE,
                vertical_overflow="visible",
            ) as live:
                async for chunk in stream:
                    buffer += chunk
                    live.update(Styled(Markdown(buffer), style=style))

                    if self._typewriter_effect:
                        stripped = chunk.rstrip()
                        if stripped:
                            last_char = stripped[-1]
                            if last_char in _TYPEWRITER_PAUSES:
                                await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
                        if buffer.endswith("\n\n"):
                            await asyncio.sleep(_TYPEWRITER_PAUSES["\n\n"])
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)

        self.console.print()
```

- [ ] **Step 5: Implement — update render_welcome to use Markdown for description**

Replace line 401 (`self.console.print(f"\n{location.description}\n")`) with:

```python
        from rich.markdown import Markdown
        self.console.print()
        self.console.print(Markdown(location.description))
        self.console.print()
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/cli/test_renderer_markdown.py tests/cli/test_renderer_get_input.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/tavern/cli/renderer.py tests/cli/test_renderer_markdown.py
git commit -m "feat(§3): implement Live+Markdown streaming render with typewriter effect"
```

---

### Task 9: 集成验证

**Files:**
- Test: (run existing test suite)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest --tb=short -q`
Expected: ALL PASS, no regressions

- [ ] **Step 2: Verify ContentLoader → CachedPromptBuilder → Renderer pipeline**

Run: `python -m pytest tests/content/ tests/narrator/ tests/cli/ -v`
Expected: ALL PASS

- [ ] **Step 3: Count total tests**

Run: `python -m pytest --co -q | tail -1`
Expected: More than 710 tests (previous count) + new tests from this phase

- [ ] **Step 4: Commit (if any final adjustments needed)**

```bash
git add -A
git commit -m "test(§5A): integration verification — all tests pass"
```
