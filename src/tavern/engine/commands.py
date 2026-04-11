from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext


@dataclass(frozen=True)
class GameCommand:
    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    available_in: tuple = ()
    is_available: Callable[[Any], bool] = lambda _: True
    execute: Callable[[str, ModeContext], Awaitable[None]] = field(default=None)


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: list[GameCommand] = []
        self._lookup: dict[str, GameCommand] = {}

    def register(self, cmd: GameCommand) -> None:
        self._commands.append(cmd)
        self._lookup[cmd.name] = cmd
        for alias in cmd.aliases:
            self._lookup[alias] = cmd

    def find(self, name: str) -> GameCommand | None:
        return self._lookup.get(name)

    def get_available(self, mode: Any, state: Any) -> list[GameCommand]:
        return [
            c for c in self._commands
            if mode in c.available_in
            and c.is_available(state)
        ]

    def get_completions(self, mode: Any, state: Any) -> list[str]:
        return [c.name for c in self.get_available(mode, state)]

    async def handle_command(
        self, raw: str, mode: Any, ctx: ModeContext
    ) -> bool:
        parts = raw.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        cmd = self.find(cmd_name)
        if cmd is None:
            return False
        if mode not in cmd.available_in:
            await ctx.renderer.render_error(f"当前模式下不可用: {cmd_name}")
            return True
        if not cmd.is_available(ctx.state_manager.state):
            await ctx.renderer.render_error(f"当前无法执行: {cmd_name}")
            return True
        await cmd.execute(args, ctx)
        return True
