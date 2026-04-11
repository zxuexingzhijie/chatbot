from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.actions import ActionType
from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)
from tavern.engine.modes.exploring import ExploringModeHandler
from tavern.world.models import ActionRequest, ActionResult, Character, CharacterRole, Location
from tavern.world.state import WorldState


async def _async_gen(items):
    for item in items:
        yield item


def _make_state(**kwargs) -> WorldState:
    return WorldState(turn=0, player_id="player", **kwargs)


def _make_exploring_state() -> WorldState:
    player = Character(
        id="player", name="Hero", role=CharacterRole.PLAYER, location_id="tavern",
    )
    npc = Character(
        id="grim", name="Grim", role=CharacterRole.NPC, location_id="tavern",
    )
    location = Location(
        id="tavern", name="Tavern", description="A cozy tavern.",
        npcs=("grim",), items=("mug",), exits={"north": {"target": "market"}},
        atmosphere="warm",
    )
    return WorldState(
        turn=1,
        player_id="player",
        characters={"player": player, "grim": npc},
        locations={"tavern": location},
    )


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
        state = _make_exploring_state()
        request = ActionRequest(action=ActionType.LOOK, target=None)
        action_result = ActionResult(
            success=True, action=ActionType.LOOK, message="You look around.",
        )

        parser = MagicMock()
        parser.parse = AsyncMock(return_value=request)
        registry = MagicMock()
        registry.validate_and_execute = MagicMock(return_value=(action_result, None))
        narrator = MagicMock()
        narrator.stream_narrative = MagicMock(return_value=_async_gen(["text"]))
        renderer = MagicMock()
        renderer.render_stream = AsyncMock()
        renderer.render_status_bar = MagicMock()
        memory = MagicMock()
        memory.build_context = MagicMock(return_value={})
        story_engine = MagicMock(spec=[])

        ctx = _make_context(
            intent_parser=parser,
            action_registry=registry,
            narrator=narrator,
            renderer=renderer,
            memory=memory,
            story_engine=story_engine,
        )
        handler = ExploringModeHandler()
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
        assert len(bindings) == 0

    def test_keybindings_have_required_fields(self):
        handler = ExploringModeHandler()
        assert handler.get_keybindings() == []


class TestExploringFreeText:
    @pytest.mark.asyncio
    async def test_parse_and_execute_action(self):
        state = _make_exploring_state()
        request = ActionRequest(action=ActionType.MOVE, target="north")
        result = ActionResult(
            success=True, action=ActionType.MOVE, message="You head north.", target="north",
        )
        diff = MagicMock()

        parser = MagicMock()
        parser.parse = AsyncMock(return_value=request)
        registry = MagicMock()
        registry.validate_and_execute = MagicMock(return_value=(result, diff))
        narrator = MagicMock()
        narrator.stream_narrative = MagicMock(return_value=_async_gen(["You walk north."]))
        renderer = MagicMock()
        renderer.render_stream = AsyncMock()
        renderer.render_status_bar = MagicMock()
        memory = MagicMock()
        memory.build_context = MagicMock(return_value={})
        story_engine = MagicMock(spec=[])

        ctx = _make_context(
            intent_parser=parser,
            action_registry=registry,
            narrator=narrator,
            renderer=renderer,
            memory=memory,
            story_engine=story_engine,
        )

        handler = ExploringModeHandler()
        tr = await handler.handle_input("go north", state, ctx)

        parser.parse.assert_awaited_once()
        registry.validate_and_execute.assert_called_once_with(request, state)
        assert any(e.kind == EffectKind.APPLY_DIFF for e in tr.side_effects)
        assert tr.next_mode is None

    @pytest.mark.asyncio
    async def test_talk_action_triggers_dialogue_transition(self):
        state = _make_exploring_state()
        request = ActionRequest(action=ActionType.TALK, target="grim")
        result = ActionResult(
            success=True, action=ActionType.TALK, message="Grim nods.", target="grim",
        )

        parser = MagicMock()
        parser.parse = AsyncMock(return_value=request)
        registry = MagicMock()
        registry.validate_and_execute = MagicMock(return_value=(result, None))
        narrator = MagicMock()
        narrator.stream_narrative = MagicMock(return_value=_async_gen(["Grim nods."]))
        renderer = MagicMock()
        renderer.render_stream = AsyncMock()
        renderer.render_status_bar = MagicMock()
        memory = MagicMock()
        memory.build_context = MagicMock(return_value={})
        story_engine = MagicMock(spec=[])

        ctx = _make_context(
            intent_parser=parser,
            action_registry=registry,
            narrator=narrator,
            renderer=renderer,
            memory=memory,
            story_engine=story_engine,
        )

        handler = ExploringModeHandler()
        tr = await handler.handle_input("talk to grim", state, ctx)

        assert tr.next_mode == GameMode.DIALOGUE
        dialogue_effects = [e for e in tr.side_effects if e.kind == EffectKind.START_DIALOGUE]
        assert len(dialogue_effects) == 1
        assert dialogue_effects[0].payload["npc_id"] == "grim"

    @pytest.mark.asyncio
    async def test_failed_action_renders_result_no_effects(self):
        state = _make_exploring_state()
        request = ActionRequest(action=ActionType.MOVE, target="south")
        result = ActionResult(
            success=False, action=ActionType.MOVE, message="No exit south.",
        )

        parser = MagicMock()
        parser.parse = AsyncMock(return_value=request)
        registry = MagicMock()
        registry.validate_and_execute = MagicMock(return_value=(result, None))
        renderer = MagicMock()
        renderer.render_result = MagicMock()

        ctx = _make_context(
            intent_parser=parser,
            action_registry=registry,
            renderer=renderer,
        )

        handler = ExploringModeHandler()
        tr = await handler.handle_input("go south", state, ctx)

        renderer.render_result.assert_called_once_with(result)
        assert tr.side_effects == ()
        assert tr.next_mode is None

    @pytest.mark.asyncio
    async def test_unknown_intent_renders_error(self):
        state = _make_exploring_state()
        request = ActionRequest(action=ActionType.CUSTOM, is_fallback=True, detail="dunno")
        result = ActionResult(
            success=False, action=ActionType.CUSTOM, message="I don't understand.",
        )

        parser = MagicMock()
        parser.parse = AsyncMock(return_value=request)
        registry = MagicMock()
        registry.validate_and_execute = MagicMock(return_value=(result, None))
        renderer = MagicMock()
        renderer.render_result = MagicMock()

        ctx = _make_context(
            intent_parser=parser,
            action_registry=registry,
            renderer=renderer,
        )

        handler = ExploringModeHandler()
        tr = await handler.handle_input("xyzzy", state, ctx)

        registry.validate_and_execute.assert_called_once_with(request, state)
        renderer.render_result.assert_called_once_with(result)
        assert tr.side_effects == ()
        assert tr.next_mode is None
