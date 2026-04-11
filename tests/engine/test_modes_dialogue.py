from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)
from tavern.engine.modes.dialogue import DialogueModeHandler
from tavern.world.state import WorldState


def _make_state(**kwargs) -> WorldState:
    return WorldState(turn=0, player_id="player", **kwargs)


def _make_context(**overrides) -> ModeContext:
    defaults = dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=MagicMock(),
        intent_parser=MagicMock(),
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


def _make_dm(*, active: DialogueContext | None = None) -> AsyncMock:
    dm = AsyncMock()
    dm.active_context = active
    return dm


def _default_active_ctx() -> DialogueContext:
    return DialogueContext(
        npc_id="grim",
        npc_name="Grim",
        npc_traits=(),
        trust=10,
        tone="neutral",
        messages=(),
        location_id="tavern",
        turn_entered=0,
    )


class TestDialogueModeHandler:
    def test_mode_is_dialogue(self):
        handler = DialogueModeHandler(dialogue_manager=MagicMock())
        assert handler.mode == GameMode.DIALOGUE

    def test_get_prompt_config(self):
        handler = DialogueModeHandler(dialogue_manager=MagicMock())
        config = handler.get_prompt_config(_make_state())
        assert isinstance(config, PromptConfig)
        assert config.prompt_text == "对话> "

    @pytest.mark.asyncio
    async def test_slash_command_delegates_to_registry(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=True)
        ctx = _make_context(command_registry=registry)
        handler = DialogueModeHandler(dialogue_manager=MagicMock())
        state = _make_state()
        result = await handler.handle_input("/help", state, ctx)
        registry.handle_command.assert_awaited_once()
        assert result.next_mode is None

    @pytest.mark.asyncio
    async def test_empty_input_returns_no_transition(self):
        ctx = _make_context()
        handler = DialogueModeHandler(dialogue_manager=MagicMock())
        state = _make_state()
        result = await handler.handle_input("", state, ctx)
        assert result.next_mode is None
        assert result.side_effects == ()

    @pytest.mark.asyncio
    async def test_whitespace_input_returns_no_transition(self):
        ctx = _make_context()
        handler = DialogueModeHandler(dialogue_manager=MagicMock())
        state = _make_state()
        result = await handler.handle_input("   ", state, ctx)
        assert result.next_mode is None
        assert result.side_effects == ()


def _make_renderer() -> MagicMock:
    renderer = MagicMock()
    renderer.render_dialogue_with_typewriter = AsyncMock()
    renderer.render_error = AsyncMock()
    return renderer


class TestDialogueFlow:
    @pytest.mark.asyncio
    async def test_sends_message_and_renders(self):
        active_ctx = _default_active_ctx()
        dm = _make_dm(active=active_ctx)
        response = DialogueResponse(text="你好！", trust_delta=2, mood="friendly", wants_to_end=False)
        new_ctx = MagicMock()
        new_ctx.npc_name = "Grim"
        new_ctx.npc_id = "grim"
        dm.respond.return_value = (new_ctx, response)

        renderer = _make_renderer()
        memory = MagicMock()
        memory.build_context.return_value = {}
        ctx = _make_context(renderer=renderer, memory=memory)

        handler = DialogueModeHandler(dialogue_manager=dm)
        state = _make_state()
        result = await handler.handle_input("你好啊老板", state, ctx)

        dm.respond.assert_awaited_once()
        renderer.render_dialogue_with_typewriter.assert_awaited_once_with("Grim", response)
        assert result.next_mode is None
        assert len(result.side_effects) == 1
        effect = result.side_effects[0]
        assert effect.kind == EffectKind.APPLY_TRUST
        assert effect.payload == {"npc_id": "grim", "delta": 2}

    @pytest.mark.asyncio
    async def test_wants_to_end_transitions_to_exploring(self):
        active_ctx = _default_active_ctx()
        dm = _make_dm(active=active_ctx)
        response = DialogueResponse(text="再见", trust_delta=0, mood="neutral", wants_to_end=True)
        summary = DialogueSummary(
            npc_id="grim", summary_text="一段对话", total_trust_delta=0,
            key_info=(), turns_count=1,
        )
        dm.respond.return_value = (MagicMock(npc_name="Grim", npc_id="grim"), response)
        dm.end.return_value = summary

        renderer = _make_renderer()
        memory = MagicMock()
        memory.build_context.return_value = {}
        ctx = _make_context(renderer=renderer, memory=memory)

        handler = DialogueModeHandler(dialogue_manager=dm)
        state = _make_state()
        result = await handler.handle_input("再见了朋友", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
        kinds = [e.kind for e in result.side_effects]
        assert EffectKind.END_DIALOGUE in kinds
        renderer.render_dialogue_end.assert_called_once_with(summary)

    @pytest.mark.asyncio
    async def test_escape_input_ends_dialogue(self):
        active_ctx = _default_active_ctx()
        dm = _make_dm(active=active_ctx)
        summary = DialogueSummary(
            npc_id="grim", summary_text="对话结束", total_trust_delta=0,
            key_info=(), turns_count=1,
        )
        dm.end.return_value = summary

        renderer = _make_renderer()
        ctx = _make_context(renderer=renderer)

        handler = DialogueModeHandler(dialogue_manager=dm)
        state = _make_state()
        result = await handler.handle_input("\x1b", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
        kinds = [e.kind for e in result.side_effects]
        assert EffectKind.END_DIALOGUE in kinds
        dm.end.assert_awaited_once_with(active_ctx)
        renderer.render_dialogue_end.assert_called_once_with(summary)

    @pytest.mark.asyncio
    async def test_no_active_dialogue_renders_error(self):
        dm = _make_dm(active=None)
        renderer = _make_renderer()
        ctx = _make_context(renderer=renderer)

        handler = DialogueModeHandler(dialogue_manager=dm)
        state = _make_state()
        result = await handler.handle_input("你好", state, ctx)

        renderer.render_error.assert_awaited_once_with("没有进行中的对话")
        assert result.next_mode == GameMode.EXPLORING

    @pytest.mark.asyncio
    async def test_bye_phrase_ends_dialogue(self):
        active_ctx = _default_active_ctx()
        dm = _make_dm(active=active_ctx)
        summary = DialogueSummary(
            npc_id="grim", summary_text="对话结束", total_trust_delta=0,
            key_info=(), turns_count=1,
        )
        dm.end.return_value = summary

        renderer = _make_renderer()
        ctx = _make_context(renderer=renderer)

        handler = DialogueModeHandler(dialogue_manager=dm)
        state = _make_state()
        result = await handler.handle_input("再见", state, ctx)

        assert result.next_mode == GameMode.EXPLORING
        kinds = [e.kind for e in result.side_effects]
        assert EffectKind.END_DIALOGUE in kinds
        dm.end.assert_awaited_once_with(active_ctx)
        renderer.render_dialogue_end.assert_called_once_with(summary)
