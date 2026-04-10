from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.fsm import (
    GameMode,
    Keybinding,
    ModeContext,
    PromptConfig,
    TransitionResult,
)

if TYPE_CHECKING:
    from tavern.world.state import WorldState


class DialogueModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.DIALOGUE

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()

        if stripped.startswith("/"):
            await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            return TransitionResult()

        if not stripped:
            return TransitionResult()

        return TransitionResult()

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="对话> ", show_status_bar=False)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
        ]
