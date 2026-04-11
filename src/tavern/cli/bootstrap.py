from __future__ import annotations

from typing import Any

from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.command_defs import register_all_commands
from tavern.engine.commands import CommandRegistry
from tavern.engine.effects import EFFECT_EXECUTORS
from tavern.engine.fsm import GameLoop, GameMode, ModeContext
from tavern.engine.keybinding_bridge import KeybindingBridge
from tavern.engine.keybindings import DEFAULT_BINDINGS, KeybindingResolver
from tavern.engine.modes.dialogue import DialogueModeHandler
from tavern.engine.modes.exploring import ExploringModeHandler
from tavern.narrator.cached_builder import CachedPromptBuilder
from tavern.narrator.scene_cache import SceneContextCache


def bootstrap(
    state_manager: Any,
    renderer: Any,
    dialogue_manager: Any,
    narrator: Any,
    memory: Any,
    persistence: Any,
    story_engine: Any,
    intent_parser: Any,
    logger: Any,
    game_logger: Any = None,
    content_loader: Any = None,
) -> GameLoop:
    command_registry = CommandRegistry()
    register_all_commands(command_registry)

    action_registry = ActionRegistry(build_all_actions())

    keybinding_resolver = KeybindingResolver(DEFAULT_BINDINGS)
    keybinding_bridge = KeybindingBridge(keybinding_resolver, blocks=DEFAULT_BINDINGS)

    scene_cache = SceneContextCache()
    cached_builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=scene_cache,
        state_manager=state_manager,
    )
    if not hasattr(narrator, '_cached_builder') or narrator._cached_builder is None:
        narrator._cached_builder = cached_builder

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
        intent_parser=intent_parser,
        logger=logger,
        game_logger=game_logger,
        keybinding_bridge=keybinding_bridge,
    )

    handlers = {
        GameMode.EXPLORING: ExploringModeHandler(),
        GameMode.DIALOGUE: DialogueModeHandler(dialogue_manager=dialogue_manager),
    }

    return GameLoop(
        handlers=handlers,
        context=context,
        effect_executors=dict(EFFECT_EXECUTORS),
    )
