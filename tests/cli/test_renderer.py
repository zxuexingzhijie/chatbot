from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
            success=True,
            action=ActionType.LOOK,
            message="你环顾四周，看到一间温暖的酒馆。",
        )
        renderer.render_result(result)
        output = console.file.getvalue()
        assert "温暖的酒馆" in output

    def test_render_failure_result(self, renderer, console):
        result = ActionResult(
            success=False,
            action=ActionType.MOVE,
            message="门被锁住了。",
        )
        renderer.render_result(result)
        output = console.file.getvalue()
        assert "锁" in output

    def test_render_inventory(self, renderer, sample_world_state, console):
        renderer.render_inventory(sample_world_state)
        output = console.file.getvalue()
        assert "背包" in output or "空" in output

    def test_render_save_success(self, renderer, console):
        renderer.render_save_success("autosave", Path("saves/autosave.json"))
        output = console.file.getvalue()
        assert "autosave" in output

    def test_render_load_success(self, renderer, console):
        renderer.render_load_success("autosave", "2026-04-08T12:00:00+00:00")
        output = console.file.getvalue()
        assert "autosave" in output

    def test_render_saves_list_empty(self, renderer, console):
        renderer.render_saves_list([])
        output = console.file.getvalue()
        assert "暂无存档" in output

    def test_render_saves_list_nonempty(self, renderer, console):
        from tavern.world.persistence import SaveInfo
        saves = [
            SaveInfo(slot="autosave", timestamp="2026-04-08T12:00:00+00:00", path=Path("saves/autosave.json")),
            SaveInfo(slot="mygame", timestamp="2026-04-07T09:00:00+00:00", path=Path("saves/mygame.json")),
        ]
        renderer.render_saves_list(saves)
        output = console.file.getvalue()
        assert "autosave" in output
        assert "mygame" in output

    def test_render_help_includes_save_commands(self, renderer, console):
        renderer.render_help()
        output = console.file.getvalue()
        assert "save" in output
        assert "load" in output
        assert "saves" in output
        assert "/" in output

    def test_render_status_shows_stats_compact(self, renderer, sample_world_state, console):
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "hp" in output
        assert "100" in output
        assert "gold" in output

    def test_render_status_shows_relationships(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        rels = [
            Relationship(src="player", tgt="traveler", value=25),
            Relationship(src="player", tgt="bartender_grim", value=-25),
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
        assert "旅行者" in output

    def test_render_status_incoming_edge_shows_npc_name(self, renderer, sample_world_state, console):
        from tavern.world.memory import Relationship
        rels = [Relationship(src="traveler", tgt="player", value=30)]
        renderer.render_status(sample_world_state, rels)
        output = console.file.getvalue()
        assert "旅行者" in output
        assert "玩家" not in output or "旅行者" in output

    def test_render_status_empty_relationships(self, renderer, sample_world_state, console):
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "尚无人际关系记录" in output

    def test_render_status_shows_quests(self, renderer, sample_world_state, console):
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
        renderer.render_status(sample_world_state, [])
        output = console.file.getvalue()
        assert "暂无任务记录" in output


from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary


class TestDialogueRenderer:
    def test_render_dialogue_start_outputs_npc_name(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善",),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        response = DialogueResponse(text="你好！", trust_delta=1, mood="平静", wants_to_end=False)
        renderer.render_dialogue_start(ctx, response)
        output = console.file.getvalue()
        assert "旅行者" in output

    def test_render_dialogue_shows_trust_delta(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        response = DialogueResponse(text="很高兴认识你", trust_delta=2, mood="开心", wants_to_end=False)
        renderer.render_dialogue(response)
        output = console.file.getvalue()
        assert "2" in output

    def test_render_dialogue_end_shows_summary(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="旅行者分享了北方的传说。",
            total_trust_delta=5,
            key_info=("北方有宝藏",),
            turns_count=3,
        )
        renderer.render_dialogue_end(summary)
        output = console.file.getvalue()
        assert "旅行者分享了北方的传说" in output

    def test_get_dialogue_input_callable(self):
        from rich.console import Console
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        assert callable(renderer.get_dialogue_input)


async def _async_gen(*values):
    for v in values:
        yield v


async def _raise_mid_stream():
    yield "你走进了"
    raise RuntimeError("stream interrupted")


class TestRenderStream:
    @pytest.mark.asyncio
    async def test_render_stream_outputs_all_chunks(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("你走进了", "温暖的酒馆。"))
        output = console.file.getvalue()
        assert "你走进了" in output
        assert "温暖的酒馆。" in output

    @pytest.mark.asyncio
    async def test_render_stream_adds_trailing_newline(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("内容"))
        output = console.file.getvalue()
        assert output.endswith("\n")

    @pytest.mark.asyncio
    async def test_render_stream_handles_mid_stream_error(self):
        console = Console(file=StringIO(), width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_raise_mid_stream())
        output = console.file.getvalue()
        assert "你走进了" in output
        assert output.endswith("\n")


class TestRendererInit:
    def test_default_vi_mode_off(self):
        from prompt_toolkit.enums import EditingMode
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        assert renderer._session.editing_mode == EditingMode.EMACS

    def test_vi_mode_on(self):
        from prompt_toolkit.enums import EditingMode
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, vi_mode=True)
        assert renderer._session.editing_mode == EditingMode.VI


class TestSpinner:
    @pytest.mark.asyncio
    async def test_spinner_context_manager_runs_block(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        executed = False
        async with renderer.spinner("测试中..."):
            executed = True
        assert executed


class TestSlashCommandCompleter:
    def test_completes_slash_commands(self):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import SlashCommandCompleter

        completer = SlashCommandCompleter()
        doc = Document("/", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        labels = [c.text for c in completions]
        assert "look" in labels
        assert "quit" in labels
        assert "inventory" in labels
        assert len(completions) == 11

    def test_filters_by_prefix(self):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import SlashCommandCompleter

        completer = SlashCommandCompleter()
        doc = Document("/lo", cursor_position=3)
        completions = list(completer.get_completions(doc, None))
        labels = [c.text for c in completions]
        assert "look" in labels
        assert "load" in labels
        assert "quit" not in labels

    def test_no_completions_without_slash(self):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import SlashCommandCompleter

        completer = SlashCommandCompleter()
        doc = Document("hello", cursor_position=5)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_completions_have_display_meta(self):
        from prompt_toolkit.document import Document
        from tavern.cli.renderer import SlashCommandCompleter

        completer = SlashCommandCompleter()
        doc = Document("/qu", cursor_position=3)
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 1
        assert completions[0].display_meta_text == "退出游戏"


class TestAtmosphereStyles:
    def test_atmosphere_style_mapping_has_all_keys(self):
        from tavern.cli.renderer import _ATMOSPHERE_STYLES
        for key in ("warm", "cold", "dim", "natural", "danger", "neutral"):
            assert key in _ATMOSPHERE_STYLES

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
    async def test_render_stream_unknown_atmosphere_falls_back(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        await renderer.render_stream(_async_gen("未知氛围"), atmosphere="unknown_type")
        output = console.file.getvalue()
        assert "未知氛围" in output


class TestTypewriterEffect:
    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_period(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("你好。"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.3 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_exclamation(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("太好了！"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.25 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_ellipsis(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("等等…"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.4 in delays

    @pytest.mark.asyncio
    async def test_typewriter_pauses_on_double_newline(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("第一段\n\n"))
            mock_sleep.assert_called()
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            assert 0.5 in delays

    @pytest.mark.asyncio
    async def test_typewriter_no_pause_on_normal_text(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("普通文字"))
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_typewriter_disabled_no_pause(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=False)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("你好。太好了！"))
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_typewriter_default_is_disabled(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        with patch("tavern.cli.renderer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await renderer.render_stream(_async_gen("你好。"))
            mock_sleep.assert_not_called()


class TestContextualCompleter:
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
        assert any("旅" in t for t in texts)

    def test_npc_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        npc_completions = [
            c for c in completions if "NPC" in (c.display_meta_text or "")
        ]
        assert len(npc_completions) > 0

    def test_completes_item_names(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旧", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert any("旧" in t for t in texts)

    def test_completes_exit_directions(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("n", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "north" in texts

    def test_no_completions_for_empty_input(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("", cursor_position=0)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_no_state_returns_no_completions(self):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: None)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_exit_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("n", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        exit_completions = [
            c for c in completions if "出口" in (c.display_meta_text or "")
        ]
        assert len(exit_completions) > 0

    def test_item_completion_has_meta(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=lambda: sample_world_state)
        doc = Document("旧", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        item_completions = [
            c for c in completions if "物品" in (c.display_meta_text or "")
        ]
        assert len(item_completions) > 0

    def test_inventory_items_completed(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter
        from tavern.world.models import Character, CharacterRole
        from tavern.world.state import WorldState

        player_with_inv = Character(
            id="player",
            name="冒险者",
            role=CharacterRole.PLAYER,
            traits=("勇敢",),
            stats={"hp": 100, "gold": 10},
            inventory=("cellar_key",),
            location_id="tavern_hall",
        )
        state = WorldState(
            turn=sample_world_state.turn,
            player_id=sample_world_state.player_id,
            locations=dict(sample_world_state.locations),
            characters={
                **dict(sample_world_state.characters),
                "player": player_with_inv,
            },
            items=dict(sample_world_state.items),
        )
        completer = ContextualCompleter(state_provider=lambda: state)
        doc = Document("地", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "地下室钥匙" in texts

    def test_no_duplicate_items(self, sample_world_state):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter
        from tavern.world.models import Character, CharacterRole, Exit, Location
        from tavern.world.state import WorldState

        player_with_inv = Character(
            id="player",
            name="冒险者",
            role=CharacterRole.PLAYER,
            traits=("勇敢",),
            stats={"hp": 100, "gold": 10},
            inventory=("old_notice",),
            location_id="tavern_hall",
        )
        state = WorldState(
            turn=sample_world_state.turn,
            player_id=sample_world_state.player_id,
            locations=dict(sample_world_state.locations),
            characters={
                **dict(sample_world_state.characters),
                "player": player_with_inv,
            },
            items=dict(sample_world_state.items),
        )
        completer = ContextualCompleter(state_provider=lambda: state)
        doc = Document("旧", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert texts.count("旧告示") == 1

    def test_no_state_provider_returns_no_completions(self):
        from prompt_toolkit.document import Document

        from tavern.cli.renderer import ContextualCompleter

        completer = ContextualCompleter(state_provider=None)
        doc = Document("旅", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        assert completions == []


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


class TestEntityHighlighting:
    def test_highlight_npc_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)
        result = renderer._highlight_entities("旅行者正在喝酒。")
        assert "[bold cyan]旅行者[/]" in result

    def test_highlight_item_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)
        result = renderer._highlight_entities("你看到了旧告示。")
        assert "[cyan]旧告示[/]" in result

    def test_highlight_location_names(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)
        result = renderer._highlight_entities("你走进酒馆大厅。")
        assert "[green]酒馆大厅[/]" in result

    def test_highlight_longer_names_first(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)
        result = renderer._highlight_entities("地下室钥匙很重要。")
        assert "[cyan]地下室钥匙[/]" in result

    def test_no_state_returns_unchanged(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console)
        result = renderer._highlight_entities("旅行者正在喝酒。")
        assert result == "旅行者正在喝酒。"

    def test_no_state_provider_returns_none(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: None)
        result = renderer._highlight_entities("旅行者正在喝酒。")
        assert result == "旅行者正在喝酒。"

    def test_player_name_not_highlighted(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)
        result = renderer._highlight_entities("冒险者走进了大厅。")
        assert "[bold cyan]冒险者[/]" not in result

    @pytest.mark.asyncio
    async def test_render_stream_with_highlighting(self, sample_world_state):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, state_provider=lambda: sample_world_state)

        async def _stream():
            yield "旅行者走进了酒馆大厅。\n"

        await renderer.render_stream(_stream())
        output = console.file.getvalue()
        assert "旅行者" in output
        assert "酒馆大厅" in output
