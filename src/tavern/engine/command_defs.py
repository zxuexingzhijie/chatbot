from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.engine.commands import CommandRegistry, GameCommand
from tavern.engine.fsm import GameMode
from tavern.world.models import ActionRequest

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext


async def cmd_look(args: str, ctx: ModeContext) -> None:
    if args:
        request = ActionRequest(action=ActionType.LOOK, target=args)
    else:
        request = ActionRequest(action=ActionType.LOOK)
    if ctx.action_registry is not None:
        result, _ = ctx.action_registry.validate_and_execute(
            request, ctx.state_manager.state,
        )
    else:
        from tavern.engine.rules import RulesEngine
        rules = RulesEngine()
        result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(result)


async def cmd_inventory(args: str, ctx: ModeContext) -> None:
    ctx.renderer.render_inventory(ctx.state_manager.state)


async def cmd_status(args: str, ctx: ModeContext) -> None:
    relationships = ctx.memory.get_player_relationships(
        ctx.state_manager.state.player_id
    )
    ctx.renderer.render_status(ctx.state_manager.state, relationships)


async def cmd_hint(args: str, ctx: ModeContext) -> None:
    ctx.renderer.console.print(
        "\n[dim italic]尝试和酒馆里的人聊聊天，也许能发现什么线索...[/]\n"
    )


async def cmd_undo(args: str, ctx: ModeContext) -> None:
    result = ctx.state_manager.undo()
    if result is None:
        ctx.renderer.console.print("\n[red]没有可以回退的步骤。[/]\n")
        return
    ctx.renderer.console.print("\n[dim]已回退上一步。[/]\n")
    request = ActionRequest(action=ActionType.LOOK)
    if ctx.action_registry is not None:
        look_result, _ = ctx.action_registry.validate_and_execute(
            request, ctx.state_manager.state,
        )
    else:
        from tavern.engine.rules import RulesEngine
        rules = RulesEngine()
        look_result, _ = rules.validate(request, ctx.state_manager.state)
    ctx.renderer.render_result(look_result)


async def cmd_help(args: str, ctx: ModeContext) -> None:
    ctx.renderer.render_help()


async def cmd_save(args: str, ctx: ModeContext) -> None:
    slot = args.strip() if args.strip() else "auto"
    try:
        new_state = ctx.memory.sync_to_state(ctx.state_manager.state)
        path = ctx.persistence.save(new_state, slot)
        ctx.renderer.render_save_success(slot, path)
    except OSError as e:
        ctx.renderer.console.print(f"\n[red]存档失败：{e}[/]\n")


async def cmd_saves(args: str, ctx: ModeContext) -> None:
    saves = ctx.persistence.list_saves()
    ctx.renderer.render_saves_list(saves)


async def cmd_load(args: str, ctx: ModeContext) -> None:
    if ctx.dialogue_manager and ctx.dialogue_manager.is_active:
        ctx.renderer.console.print("\n[red]请先结束当前对话再加载存档。[/]\n")
        return
    slot = args.strip() if args.strip() else "auto"
    try:
        loaded_state, timestamp = ctx.persistence.load(slot)
        ctx.state_manager.replace(loaded_state)
        ctx.memory.rebuild(loaded_state)
        ctx.renderer.render_load_success(slot, timestamp)
    except (FileNotFoundError, ValueError) as e:
        ctx.renderer.console.print(f"\n[red]{e}[/]\n")


async def cmd_journal(args: str, ctx: ModeContext) -> None:
    if ctx.game_logger is None:
        ctx.renderer.console.print("\n[dim]冒险日志尚未启用。[/]\n")
        return
    entries = ctx.game_logger.read_recent(n=20)
    player_entries = [e for e in entries if e.entry_type == "player_input"]
    if not player_entries:
        ctx.renderer.console.print("\n[dim]冒险日志为空。[/]\n")
        return
    ctx.renderer.console.print("\n[bold]冒险日志[/]")
    for entry in player_entries:
        raw = entry.data.get("raw", "?")
        ctx.renderer.console.print(f"  [dim]回合{entry.turn}[/] {raw}")
    ctx.renderer.console.print()


async def cmd_quit(args: str, ctx: ModeContext) -> None:
    raise SystemExit(0)


_ALL_MODES = tuple(GameMode)
_EXPLORING = (GameMode.EXPLORING,)


def register_all_commands(registry: CommandRegistry) -> None:
    registry.register(GameCommand(
        name="/look", aliases=("/l", "/观察"), description="查看当前环境",
        available_in=_ALL_MODES, execute=cmd_look,
    ))
    registry.register(GameCommand(
        name="/inventory", aliases=("/i", "/背包"), description="查看背包物品",
        available_in=_ALL_MODES, execute=cmd_inventory,
    ))
    registry.register(GameCommand(
        name="/status", aliases=("/st",), description="查看状态",
        available_in=_ALL_MODES, execute=cmd_status,
    ))
    registry.register(GameCommand(
        name="/hint", description="查看提示",
        available_in=_EXPLORING, execute=cmd_hint,
    ))
    registry.register(GameCommand(
        name="/undo", description="回退上一步",
        available_in=_EXPLORING, execute=cmd_undo,
    ))
    registry.register(GameCommand(
        name="/help", aliases=("/h", "/帮助"), description="显示帮助",
        available_in=_ALL_MODES, execute=cmd_help,
    ))
    registry.register(GameCommand(
        name="/save", aliases=("/s",), description="保存游戏",
        available_in=_EXPLORING, execute=cmd_save,
    ))
    registry.register(GameCommand(
        name="/saves", description="查看存档列表",
        available_in=_EXPLORING, execute=cmd_saves,
    ))
    registry.register(GameCommand(
        name="/load", description="加载存档",
        available_in=_EXPLORING, execute=cmd_load,
    ))
    registry.register(GameCommand(
        name="/journal", aliases=("/j", "/日志"), description="查看冒险日志",
        available_in=_ALL_MODES, execute=cmd_journal,
    ))
    registry.register(GameCommand(
        name="/quit", aliases=("/q", "/退出"), description="退出游戏",
        available_in=_ALL_MODES, execute=cmd_quit,
    ))
