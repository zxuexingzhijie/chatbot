from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.action_registry import ActionRegistry
    from tavern.engine.commands import CommandRegistry
    from tavern.world.state import ReactiveStateManager, WorldState

logger = logging.getLogger(__name__)


class GameMode(Enum):
    EXPLORING = "exploring"
    DIALOGUE = "dialogue"
    COMBAT = "combat"
    INVENTORY = "inventory"
    SHOP = "shop"


class EffectKind(Enum):
    START_DIALOGUE = "start_dialogue"
    END_DIALOGUE = "end_dialogue"
    APPLY_DIFF = "apply_diff"
    EMIT_EVENT = "emit_event"
    APPLY_TRUST = "apply_trust"
    OPEN_SHOP = "open_shop"


@dataclass(frozen=True)
class SideEffect:
    kind: EffectKind
    payload: dict


@dataclass(frozen=True)
class TransitionResult:
    next_mode: GameMode | None = None
    side_effects: tuple[SideEffect, ...] = ()


@dataclass(frozen=True)
class PromptConfig:
    prompt_text: str = "> "



@dataclass(frozen=True)
class Keybinding:
    key: str
    action: str
    description: str
    allow_in_text: bool = False


@dataclass
class ModeContext:
    state_manager: ReactiveStateManager
    renderer: Any
    dialogue_manager: Any
    narrator: Any
    memory: Any
    persistence: Any
    story_engine: Any
    command_registry: CommandRegistry
    action_registry: ActionRegistry | None
    intent_parser: Any
    logger: Any
    game_logger: Any = None
    keybinding_bridge: Any = None


class ModeHandler(Protocol):
    @property
    def mode(self) -> GameMode: ...

    async def handle_input(
        self, raw: str, state: WorldState, context: ModeContext
    ) -> TransitionResult: ...

    def get_prompt_config(self, state: WorldState) -> PromptConfig: ...



EffectExecutor = Callable[[dict, ModeContext], Awaitable[None]]


class GameLoop:
    def __init__(
        self,
        handlers: dict[GameMode, ModeHandler],
        context: ModeContext,
        effect_executors: dict[EffectKind, EffectExecutor],
    ):
        self._handlers = handlers
        self._context = context
        self._effect_executors = effect_executors
        self._current_mode = GameMode.EXPLORING
        self._running = False

    @property
    def current_mode(self) -> GameMode:
        return self._current_mode

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                handler = self._handlers.get(self._current_mode)
                if handler is None:
                    logger.error("No handler for mode %s, falling back to EXPLORING", self._current_mode)
                    self._current_mode = GameMode.EXPLORING
                    handler = self._handlers[GameMode.EXPLORING]
                state = self._context.state_manager.state
                bridge = self._context.keybinding_bridge
                extra_bindings = None
                if bridge is not None:
                    extra_bindings = bridge.build_ptk_bindings(self._current_mode)
                hints = self._collect_hints(state)
                if hints and hasattr(self._context.renderer, "get_input_with_card_hints"):
                    raw = await self._context.renderer.get_input_with_card_hints(hints, extra_bindings=extra_bindings)
                else:
                    raw = await self._context.renderer.get_input(
                    config=handler.get_prompt_config(state),
                    extra_bindings=extra_bindings,
                )
                result = await handler.handle_input(raw, state, self._context)
                for effect in result.side_effects:
                    await self._execute_effect(effect)

                new_state = self._context.state_manager.state
                new_endings = set(new_state.endings_reached) - set(state.endings_reached)
                if new_endings:
                    await self._play_ending(sorted(new_endings)[0])
                    break

                if result.next_mode is not None:
                    self._current_mode = result.next_mode
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                logger.exception("GameLoop error")
                await self._context.renderer.render_error(f"内部错误: {e}")

    async def _execute_effect(self, effect: SideEffect) -> None:
        executor = self._effect_executors.get(effect.kind)
        if executor is None:
            logger.warning("No executor for effect kind: %s", effect.kind)
            return
        await executor(effect.payload, self._context)

    def stop(self) -> None:
        self._running = False

    def _collect_hints(self, state: "WorldState") -> list[str]:
        se = self._context.story_engine
        if se is None or not hasattr(se, "get_pending_hints"):
            return []
        memory = self._context.memory
        timeline = memory.timeline if hasattr(memory, "timeline") else ()
        relationships = memory.relationship_graph if hasattr(memory, "relationship_graph") else {}
        return se.get_pending_hints(state, timeline, relationships)

    async def _play_ending(self, ending_id: str) -> None:
        state = self._context.state_manager.state
        narrator = getattr(self._context, "narrator", None)
        renderer = self._context.renderer
        if narrator is not None:
            memory_ctx = None
            if hasattr(self._context.memory, "build_context"):
                memory_ctx = self._context.memory.build_context(
                    actor=state.player_id, state=state,
                )
            hint = ""
            if hasattr(self._context, "story_engine") and self._context.story_engine:
                for nid, node in self._context.story_engine._nodes.items():
                    if getattr(node.effects, "trigger_ending", None) == ending_id:
                        hint = node.narrator_hint or ""
                        break
            stream = narrator.stream_ending_narrative(ending_id, hint, state, memory_ctx)
            await renderer.render_stream(stream)
        renderer.render_ending(ending_id)
        self._running = False

    def reset(self, new_state: WorldState) -> None:
        self._context.state_manager.replace(new_state)
        if hasattr(self._context.memory, "rebuild"):
            self._context.memory.rebuild(new_state)
        if hasattr(self._context.dialogue_manager, "reset"):
            self._context.dialogue_manager.reset()
        self._current_mode = GameMode.EXPLORING
