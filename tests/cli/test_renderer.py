from io import StringIO
from pathlib import Path

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
