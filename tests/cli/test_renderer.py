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
