from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)
from tavern.engine.modes.exploring import ExploringModeHandler
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


class TestExploringModeHandler:
    def test_mode_is_exploring(self):
        handler = ExploringModeHandler()
        assert handler.mode == GameMode.EXPLORING

    @pytest.mark.asyncio
    async def test_slash_command_delegates_to_registry(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=True)
        ctx = _make_context(command_registry=registry)
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("/look", state, ctx)
        registry.handle_command.assert_awaited_once()
        assert result.next_mode is None

    @pytest.mark.asyncio
    async def test_unknown_slash_command(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=False)
        renderer = MagicMock()
        renderer.render_error = AsyncMock()
        ctx = _make_context(command_registry=registry, renderer=renderer)
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("/nonexistent", state, ctx)
        assert result.next_mode is None

    @pytest.mark.asyncio
    async def test_unknown_slash_command_renders_error(self):
        registry = MagicMock()
        registry.handle_command = AsyncMock(return_value=False)
        renderer = MagicMock()
        renderer.render_error = AsyncMock()
        ctx = _make_context(command_registry=registry, renderer=renderer)
        handler = ExploringModeHandler()
        state = _make_state()
        await handler.handle_input("/nonexistent", state, ctx)
        renderer.render_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_input_returns_no_transition(self):
        ctx = _make_context()
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("", state, ctx)
        assert result.next_mode is None
        assert result.side_effects == ()

    @pytest.mark.asyncio
    async def test_free_text_returns_no_transition(self):
        ctx = _make_context()
        handler = ExploringModeHandler()
        state = _make_state()
        result = await handler.handle_input("hello world", state, ctx)
        assert result.next_mode is None

    def test_get_prompt_config(self):
        handler = ExploringModeHandler()
        config = handler.get_prompt_config(_make_state())
        assert isinstance(config, PromptConfig)

    def test_get_prompt_config_values(self):
        handler = ExploringModeHandler()
        config = handler.get_prompt_config(_make_state())
        assert config.prompt_text == "> "
        assert config.show_status_bar is True

    def test_get_keybindings_returns_list(self):
        handler = ExploringModeHandler()
        bindings = handler.get_keybindings()
        assert isinstance(bindings, list)
        assert len(bindings) > 0

    def test_keybindings_have_required_fields(self):
        handler = ExploringModeHandler()
        for binding in handler.get_keybindings():
            assert binding.key
            assert binding.action
            assert binding.description
