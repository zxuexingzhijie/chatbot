from __future__ import annotations

from typing import Any

from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.command_defs import register_all_commands
from tavern.engine.commands import CommandRegistry
from tavern.engine.effects import EFFECT_EXECUTORS
from tavern.engine.fsm import GameLoop, GameMode, ModeContext
from tavern.engine.modes.dialogue import DialogueModeHandler
from tavern.engine.modes.exploring import ExploringModeHandler


def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    logger: Any,
) -> GameLoop:
    command_registry = CommandRegistry()
    register_all_commands(command_registry)

    action_registry = ActionRegistry(build_all_actions())

    context = ModeContext(
        state_manager=state_manager,
        renderer=renderer,
        dialogue_manager=dialogue_manager,
        narrator=narrator,
        memory=memory,
        persistence=persistence,
        story_engine=story_engine,
        command_registry=command_registry,
        action_registry=action_registry,
        logger=logger,
    )

    handlers = {
        GameMode.EXPLORING: ExploringModeHandler(),
        GameMode.DIALOGUE: DialogueModeHandler(),
    }

    return GameLoop(
        handlers=handlers,
        context=context,
        effect_executors=dict(EFFECT_EXECUTORS),
    )
