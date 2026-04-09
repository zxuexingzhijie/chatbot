from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.engine.actions import ActionType
from tavern.world.memory import Relationship
from tavern.world.models import ActionResult
from tavern.world.persistence import SaveInfo
from tavern.world.state import WorldState

logger = logging.getLogger(__name__)


class Renderer:
    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def render_status_bar(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]
        hp = player.stats.get("hp", "?")
        gold = player.stats.get("gold", "?")
        inv_count = len(player.inventory)

        status = Table.grid(padding=(0, 2))
        status.add_row(
            f"[bold cyan]{location.name}[/]",
            f"HP: [green]{hp}[/]",
            f"Gold: [yellow]{gold}[/]",
            f"背包: [white]{inv_count}件[/]",
            f"回合: [dim]{state.turn}[/]",
        )
        self.console.print(Panel(status, style="dim", height=3))

    def render_result(self, result: ActionResult) -> None:
        if result.success:
            style = "white"
            prefix = ""
        else:
            style = "red"
            prefix = "[bold red]✗[/] "

        self.console.print(f"\n{prefix}{result.message}\n", style=style)

    async def render_stream(self, stream) -> None:
        try:
            async for chunk in stream:
                self.console.print(chunk, end="", highlight=False)
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)
        self.console.print()

    def render_inventory(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        if not player.inventory:
            self.console.print("\n[dim]背包是空的。[/]\n")
            return

        self.console.print("\n[bold]背包物品:[/]")
        for item_id in player.inventory:
            item = state.items.get(item_id)
            name = item.name if item else item_id
            desc = item.description if item else ""
            self.console.print(f"  [cyan]•[/] {name} — [dim]{desc}[/]")
        self.console.print()

    @staticmethod
    def _relationship_label(value: int) -> tuple[str, str]:
        if value >= 60:
            return "非常友好", "bright_green"
        if value >= 20:
            return "友好", "green"
        if value <= -60:
            return "非常敌对", "bright_red"
        if value <= -20:
            return "敌对", "red"
        return "中立", "yellow"

    def render_status(self, state: WorldState, relationships: list[Relationship]) -> None:
        player = state.characters[state.player_id]
        lines: list[str] = []

        stats_line = " | ".join(
            f"{k} [{('green' if k == 'hp' else 'yellow')}]{v}[/]"
            for k, v in player.stats.items()
        )
        lines.append(f"  属性: {stats_line}")

        lines.append("")
        lines.append("  [bold]人际关系:[/]")
        if relationships:
            for rel in relationships:
                npc = state.characters.get(rel.tgt)
                name = npc.name if npc else rel.tgt
                label, color = self._relationship_label(rel.value)
                sign = f"+{rel.value}" if rel.value >= 0 else str(rel.value)
                lines.append(f"    ★ 你 ──[[{color}]{sign} {label}[/]]──▶ {name}")
        else:
            lines.append("    [dim]（尚无人际关系记录）[/]")

        lines.append("")
        lines.append("  [bold]任务进度:[/]")
        if state.quests:
            for quest_id, quest_data in state.quests.items():
                status = quest_data.get("status", "unknown")
                if status == "completed":
                    style = "[green]completed[/]"
                elif status == "active":
                    style = "[cyan]active[/]"
                else:
                    style = f"[yellow]{status}[/]"
                lines.append(f"    ● {quest_id} ········ {style}")
        else:
            lines.append("    [dim]（暂无任务记录）[/]")

        body = "\n".join(lines)
        self.console.print(
            Panel(
                f"[bold]{player.name}[/]\n\n{body}",
                title="📊 角色状态",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )

    def render_welcome(self, state: WorldState, scenario_name: str = "醉龙酒馆") -> None:
        self.console.print(
            Panel(
                f"[bold]{scenario_name}[/]\n\n"
                "欢迎来到奇幻世界的互动小说体验。\n"
                "输入自然语言与世界互动，输入 [cyan]help[/] 查看命令列表。",
                title="🐉 Tavern",
                border_style="bright_blue",
            )
        )
        location = state.locations[state.characters[state.player_id].location_id]
        self.console.print(f"\n{location.description}\n")

    def render_help(self) -> None:
        self.console.print("\n[bold]系统命令:[/]")
        commands = {
            "look": "查看当前环境",
            "inventory": "查看背包",
            "status": "查看角色状态",
            "hint": "获取游戏提示",
            "undo": "回退上一步",
            "save [名称]": "存档（默认槽: autosave）",
            "load [名称]": "读档（默认槽: autosave）",
            "saves": "列出所有存档",
            "help": "显示此帮助",
            "quit": "退出游戏",
        }
        for cmd, desc in commands.items():
            self.console.print(f"  [cyan]{cmd}[/] — {desc}")
        self.console.print("\n[dim]输入任何其他内容与世界自由互动。[/]\n")

    def render_save_success(self, slot: str, path: Path) -> None:
        self.console.print(f"\n[green]已存档：{slot}（{path}）[/]\n")

    def render_load_success(self, slot: str, timestamp: str) -> None:
        self.console.print(f"\n[green]已读取存档：{slot}（{timestamp}）[/]\n")

    def render_saves_list(self, saves: list[SaveInfo]) -> None:
        if not saves:
            self.console.print("\n[dim]暂无存档。[/]\n")
            return
        table = Table(title="存档列表")
        table.add_column("槽名", style="cyan")
        table.add_column("时间戳")
        table.add_column("路径", style="dim")
        for s in saves:
            table.add_row(s.slot, s.timestamp, str(s.path))
        self.console.print(table)

    def get_input(self) -> str:
        try:
            return self.console.input("[bold green]▸[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def render_dialogue_start(
        self, ctx: DialogueContext, response: DialogueResponse
    ) -> None:
        tone_label = {"hostile": "敌意", "neutral": "中立", "friendly": "友好"}.get(
            ctx.tone, ctx.tone
        )
        self.console.print(
            Panel(
                f"[bold]{ctx.npc_name}[/] — 关系：{ctx.trust} ({tone_label})\n\n"
                f"{response.text}\n\n"
                "[dim]输入 bye / 再见 退出对话[/]",
                title=f"💬 {ctx.npc_name}",
                border_style="cyan",
            )
        )

    def render_dialogue(self, response: DialogueResponse) -> None:
        delta = response.trust_delta
        if delta > 0:
            delta_str = f"[green]+{delta}[/]"
        elif delta < 0:
            delta_str = f"[red]{delta}[/]"
        else:
            delta_str = "[dim]±0[/]"

        self.console.print(
            Panel(
                f"{response.text}\n\n"
                f"[dim]情绪: {response.mood}  关系变化: {delta_str}[/]",
                border_style="cyan",
            )
        )

    def render_dialogue_end(self, summary: DialogueSummary) -> None:
        delta = summary.total_trust_delta
        delta_str = f"+{delta}" if delta >= 0 else str(delta)
        key_info_text = (
            "\n".join(f"  • {info}" for info in summary.key_info)
            if summary.key_info
            else "  （无特别收获）"
        )
        self.console.print(
            Panel(
                f"[bold]对话结束[/]\n\n"
                f"{summary.summary_text}\n\n"
                f"关键信息:\n{key_info_text}\n\n"
                f"[dim]共 {summary.turns_count} 轮  |  关系变化: {delta_str}[/]",
                border_style="dim",
            )
        )

    def render_ending(self, ending_id: str) -> None:
        ending_titles = {
            "good_ending": "🌅 黎明之路",
            "bad_ending": "🌑 暗影独行",
            "neutral_ending": "🚶 过客",
        }
        title = ending_titles.get(ending_id, f"结局: {ending_id}")
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]{title}[/]\n\n"
                "[dim]感谢你的冒险。游戏已结束。[/]",
                border_style="bright_yellow",
                padding=(1, 2),
            )
        )

    def get_dialogue_input(self) -> str:
        try:
            return self.console.input("[bold cyan]对话▸[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            return "bye"
