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


class ExploringModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.EXPLORING

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()
        if not stripped:
            return TransitionResult()

        if stripped.startswith("/"):
            handled = await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            if not handled:
                await context.renderer.render_error(
                    f"未知命令: {stripped.split()[0]}"
                )
            return TransitionResult()

        return TransitionResult()

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="> ", show_status_bar=True)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
        ]
