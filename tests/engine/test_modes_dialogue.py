from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    Keybinding,
    ModeContext,
    PromptConfig,
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


class TestDialogueModeHandler:
    def test_mode_is_dialogue(self):
        handler = DialogueModeHandler()
        assert handler.mode == GameMode.DIALOGUE

    def test_keybindings_include_hint_selection(self):
        handler = DialogueModeHandler()
        bindings = handler.get_keybindings()
        hint_keys = [b for b in bindings if b.action.startswith("select_hint")]
        assert len(hint_keys) == 3
        for b in hint_keys:
            assert b.allow_in_text is True

    def test_keybindings_include_escape(self):
        handler = DialogueModeHandler()
        bindings = handler.get_keybindings()
        esc = [b for b in bindings if b.key == "escape"]
        assert len(esc) == 1
        assert esc[0].allow_in_text is True

    def test_keybindings_have_required_fields(self):
        handler = DialogueModeHandler()
        for binding in handler.get_keybindings():
            assert binding.key
            assert binding.action
            assert binding.description

    def test_get_prompt_config(self):
        handler = DialogueModeHandler()
        config = handler.get_prompt_config(_make_state())
        assert isinstance(config, PromptConfig)
        assert config.prompt_text == "对话> "
        assert config.show_status_bar is False

    @pytest.mark.asyncio
    async def test_slash_command_delegates_to_registry(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=True)
        ctx = _make_context(command_registry=registry)
        handler = DialogueModeHandler()
        state = _make_state()
        result = await handler.handle_input("/help", state, ctx)
        registry.handle_command.assert_awaited_once()
        assert result.next_mode is None

    @pytest.mark.asyncio
    async def test_empty_input_returns_no_transition(self):
        ctx = _make_context()
        handler = DialogueModeHandler()
        state = _make_state()
        result = await handler.handle_input("", state, ctx)
        assert result.next_mode is None
        assert result.side_effects == ()

    @pytest.mark.asyncio
    async def test_whitespace_input_returns_no_transition(self):
        ctx = _make_context()
        handler = DialogueModeHandler()
        state = _make_state()
        result = await handler.handle_input("   ", state, ctx)
        assert result.next_mode is None
        assert result.side_effects == ()

    @pytest.mark.asyncio
    async def test_free_text_returns_no_transition(self):
        ctx = _make_context()
        handler = DialogueModeHandler()
        state = _make_state()
        result = await handler.handle_input("你好啊老板", state, ctx)
        assert result.next_mode is None
