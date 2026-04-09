from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.engine.actions import ActionType
from tavern.world.memory import Relationship
from tavern.world.models import ActionResult, CharacterRole
from tavern.world.persistence import SaveInfo
from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

_COMMAND_COMPLETIONS: list[tuple[str, str]] = [
    ("look", "查看当前环境"),
    ("inventory", "查看背包"),
    ("status", "查看角色状态"),
    ("hint", "获取游戏提示"),
    ("undo", "回退上一步"),
    ("save", "存档"),
    ("load", "读档"),
    ("saves", "列出所有存档"),
    ("continue", "推进剧情"),
    ("help", "显示帮助"),
    ("quit", "退出游戏"),
]

_ATMOSPHERE_STYLES: dict[str, str] = {
    "warm": "italic rgb(255,200,140)",
    "cold": "italic rgb(140,170,220)",
    "dim": "italic rgb(160,160,160)",
    "natural": "italic rgb(140,200,140)",
    "danger": "italic rgb(220,140,140)",
    "neutral": "italic dim",
}

_TYPEWRITER_PAUSES: dict[str, float] = {
    "。": 0.3,
    "！": 0.25,
    "？": 0.25,
    "…": 0.4,
    "\n\n": 0.5,
}


class SlashCommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        for cmd, desc in _COMMAND_COMPLETIONS:
            if cmd.startswith(prefix):
                yield Completion(
                    cmd,
                    start_position=-len(prefix),
                    display_meta=desc,
                )


class ContextualCompleter(Completer):
    def __init__(
        self, state_provider: Callable[[], WorldState | None] | None = None
    ):
        self._state_provider = state_provider

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/"):
            prefix = text[1:]
            for cmd, desc in _COMMAND_COMPLETIONS:
                if cmd.startswith(prefix):
                    yield Completion(
                        cmd, start_position=-len(prefix), display_meta=desc
                    )
            return

        if not text:
            return

        state = self._state_provider() if self._state_provider else None
        if state is None:
            return

        player = state.characters.get(state.player_id)
        if player is None:
            return
        location = state.locations.get(player.location_id)
        if location is None:
            return

        for npc_id in location.npcs:
            npc = state.characters.get(npc_id)
            if npc and npc.name.startswith(text):
                yield Completion(
                    npc.name, start_position=-len(text), display_meta="NPC"
                )

        seen_items: set[str] = set()
        for item_id in location.items:
            item = state.items.get(item_id)
            if item and item.name.startswith(text):
                seen_items.add(item.name)
                yield Completion(
                    item.name, start_position=-len(text), display_meta="物品"
                )
        for item_id in player.inventory:
            item = state.items.get(item_id)
            if item and item.name.startswith(text) and item.name not in seen_items:
                yield Completion(
                    item.name, start_position=-len(text), display_meta="物品"
                )

        for direction in location.exits:
            if direction.startswith(text):
                yield Completion(
                    direction, start_position=-len(text), display_meta="出口"
                )


class Renderer:
    def __init__(
        self,
        console: Console | None = None,
        vi_mode: bool = False,
        typewriter_effect: bool = False,
        state_provider: Callable[[], WorldState | None] | None = None,
    ):
        self.console = console or Console()
        self._typewriter_effect = typewriter_effect
        self._state_provider = state_provider
        self._session = PromptSession(
            vi_mode=vi_mode,
            completer=ContextualCompleter(state_provider=state_provider),
        )

    def _highlight_entities(self, text: str) -> str:
        if self._state_provider is None:
            return text

        state = self._state_provider()
        if state is None:
            return text

        replacements: list[tuple[str, str]] = []

        for char in state.characters.values():
            if char.role == CharacterRole.NPC:
                replacements.append((char.name, f"[bold cyan]{char.name}[/]"))

        for item in state.items.values():
            replacements.append((item.name, f"[cyan]{item.name}[/]"))

        for loc in state.locations.values():
            replacements.append((loc.name, f"[green]{loc.name}[/]"))

        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

        placeholders: list[tuple[str, str]] = []
        for i, (original, highlighted) in enumerate(replacements):
            placeholder = f"\x00ENTITY{i}\x00"
            text = text.replace(original, placeholder)
            placeholders.append((placeholder, highlighted))

        for placeholder, highlighted in placeholders:
            text = text.replace(placeholder, highlighted)

        return text

    @asynccontextmanager
    async def spinner(self, message: str = "思考中..."):
        with self.console.status(f"[dim]{message}[/]", spinner="dots"):
            yield

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

    async def render_stream(self, stream, *, atmosphere: str = "neutral") -> None:
        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        line_buffer = ""
        accumulated = ""
        try:
            async for chunk in stream:
                line_buffer += chunk
                accumulated += chunk

                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    highlighted = self._highlight_entities(line)
                    self.console.print(highlighted, end="\n", style=style, highlight=False)

                    if self._typewriter_effect:
                        stripped = line.rstrip()
                        last_char = stripped[-1:] if stripped else ""
                        if last_char in _TYPEWRITER_PAUSES:
                            await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])

                if self._typewriter_effect and not line_buffer:
                    if accumulated.endswith("\n\n"):
                        await asyncio.sleep(_TYPEWRITER_PAUSES["\n\n"])
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)

        if line_buffer:
            highlighted = self._highlight_entities(line_buffer)
            self.console.print(highlighted, end="", style=style, highlight=False)
            if self._typewriter_effect:
                stripped = line_buffer.rstrip()
                last_char = stripped[-1:] if stripped else ""
                if last_char in _TYPEWRITER_PAUSES:
                    await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
        self.console.print("\n")

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
                other_id = rel.tgt if rel.src == state.player_id else rel.src
                npc = state.characters.get(other_id)
                name = npc.name if npc else other_id
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
                "输入自然语言与世界互动，输入 [cyan]/help[/] 查看命令列表。",
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
            self.console.print(f"  [cyan]/{cmd}[/] — {desc}")
        self.console.print("\n[dim]输入任何其他内容与世界自由互动。输入框支持 Vim 键绑定。[/]\n")

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

    async def get_input(self) -> str:
        try:
            return (await self._session.prompt_async(HTML("<ansigreen><b>▸ </b></ansigreen>"))).strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"

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

    def render_action_hints(self, hints: list[str]) -> None:
        if not hints:
            return
        parts = [f"[dim][{i + 1}][/] [cyan]{h}[/]" for i, h in enumerate(hints)]
        self.console.print("  ".join(parts))

    async def get_dialogue_input(self) -> str:
        try:
            return (await self._session.prompt_async(HTML("<ansicyan><b>对话▸ </b></ansicyan>"))).strip()
        except (EOFError, KeyboardInterrupt):
            return "bye"
