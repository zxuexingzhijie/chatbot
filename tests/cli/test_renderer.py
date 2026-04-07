from io import StringIO

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


from io import StringIO
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
