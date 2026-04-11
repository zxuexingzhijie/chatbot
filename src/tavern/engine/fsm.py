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
    INIT_COMBAT = "init_combat"
    APPLY_REWARDS = "apply_rewards"
    FLEE_PENALTY = "flee_penalty"
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
    show_status_bar: bool = True


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

    def get_keybindings(self) -> list[Keybinding]: ...


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
                handler = self._handlers[self._current_mode]
                state = self._context.state_manager.state
                raw = await self._context.renderer.get_input(
                    handler.get_prompt_config(state)
                )
                result = await handler.handle_input(raw, state, self._context)
                for effect in result.side_effects:
                    await self._execute_effect(effect)
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

    def reset(self, new_state: WorldState) -> None:
        self._context.state_manager.replace(new_state)
        if hasattr(self._context.memory, "rebuild"):
            self._context.memory.rebuild(new_state)
        if hasattr(self._context.dialogue_manager, "reset"):
            self._context.dialogue_manager.reset()
        self._current_mode = GameMode.EXPLORING
