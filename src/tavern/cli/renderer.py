from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style as PTKStyle
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl as PTKFormattedTextControl
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.engine.actions import ActionType
from tavern.engine.fsm import PromptConfig
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
    ("journal", "查看冒险日志"),
    ("help", "显示帮助"),
    ("quit", "退出游戏"),
]

_ATMOSPHERE_STYLES: dict[str, str] = {
    "warm": "italic rgb(255,210,160)",
    "cold": "italic rgb(160,190,235)",
    "dim": "italic rgb(185,185,185)",
    "natural": "italic rgb(160,215,160)",
    "danger": "italic rgb(235,160,160)",
    "neutral": "italic rgb(200,200,200)",
}

_TYPEWRITER_PAUSES: dict[str, float] = {
    "。": 0.3,
    "！": 0.25,
    "？": 0.25,
    "…": 0.4,
    "\n\n": 0.5,
}

_TYPEWRITER_CHAR_DELAY: float = 0.03

_CARD_MIN_WIDTH: int = 20
_CARD_MAX_WIDTH: int = 40

_LIVE_REFRESH_RATE: int = 15


def _display_width(text: str) -> int:
    import unicodedata
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def _pad_to_width(text: str, target: int) -> str:
    current = _display_width(text)
    return text + " " * max(0, target - current)


def _build_card_display(
    hints: list[str],
    selected: int,
    input_text: str,
) -> list[tuple[str, str]]:
    input_display = f"▸ {input_text}_" if selected == len(hints) else f"▸ {input_text or '_'}"

    all_labels = list(hints) + [input_display]
    max_dw = max(_display_width(label) for label in all_labels)
    width = max(_CARD_MIN_WIDTH, min(_CARD_MAX_WIDTH, max_dw + 2))

    top = f"  ╭{'─' * (width + 2)}╮\n"
    bot = f"  ╰{'─' * (width + 2)}╯\n"

    fragments: list[tuple[str, str]] = []

    for i, label in enumerate(all_labels):
        padded = _pad_to_width(label, width)
        if i == selected:
            fragments.append(("class:card.border", top))
            fragments.append(("class:card.border", "  │ "))
            fragments.append(("class:card.selected", padded))
            fragments.append(("class:card.border", " │\n"))
            fragments.append(("class:card.border", bot))
        else:
            fragments.append(("", f"    {label}\n"))

    fragments.append(("", "\n"))
    fragments.append(("class:card.nav", "  ↑↓ 切换  ↵ 确认\n"))

    return fragments


def _card_style():
    from prompt_toolkit.styles import Style
    return Style.from_dict({
        "card.border": "ansicyan",
        "card.selected": "bold",
        "card.nav": "ansigray",
    })


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
                        cmd,
                        start_position=-len(prefix),
                        display=f"/{cmd}",
                        display_meta=desc,
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
            complete_style=CompleteStyle.COLUMN,
            complete_while_typing=True,
            style=PTKStyle.from_dict({
                "completion-menu": "bg:#1a1a2e",
                "completion-menu.completion": "fg:#e0e0e0 bg:#1a1a2e",
                "completion-menu.completion.current": "fg:#ffffff bg:#16213e bold",
                "completion-menu.meta.completion": "fg:#888888 bg:#1a1a2e",
                "completion-menu.meta.completion.current": "fg:#aaaaff bg:#16213e",
                "scrollbar.background": "bg:#1a1a2e",
                "scrollbar.button": "bg:#333355",
            }),
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
        from tavern.content.quotes import random_quote
        quote = random_quote()
        with self.console.status(
            f"[dim]{message}[/]\n  [dim italic]{quote}[/]",
            spinner="dots",
        ):
            yield

    def render_status_bar(self, state: WorldState) -> None:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]
        hp = player.stats.get("hp", "?")
        gold = player.stats.get("gold", "?")
        inv_count = len(player.inventory)

        self.console.print(
            f"[bold cyan]{location.name}[/]  "
            f"HP: [green]{hp}[/]  "
            f"Gold: [yellow]{gold}[/]  "
            f"背包: [white]{inv_count}件[/]  "
            f"回合: [dim]{state.turn}[/]"
        )

    def render_result(self, result: ActionResult) -> None:
        if result.success:
            style = "white"
            prefix = ""
        else:
            style = "red"
            prefix = "[bold red]✗[/] "

        msg = self._highlight_entities(result.message)
        self.console.print(f"\n{prefix}{msg}\n", style=style)

    async def render_error(self, message: str) -> None:
        self.console.print(f"\n[bold red]✗[/] {message}\n", style="red")

    def start_thinking_status(self) -> Any:
        from tavern.content.quotes import random_quote
        quote = random_quote()
        status = self.console.status(
            f"[dim]思考中...[/]\n  [dim italic]{quote}[/]", spinner="dots",
        )
        status.start()
        return status

    async def render_stream(self, stream, *, atmosphere: str = "neutral", pending_status=None) -> None:
        from rich.live import Live
        from rich.markdown import Markdown
        from rich.styled import Styled

        style = _ATMOSPHERE_STYLES.get(atmosphere, _ATMOSPHERE_STYLES["neutral"])
        self.console.print()
        if pending_status is not None:
            status = pending_status
        else:
            from tavern.content.quotes import random_quote
            quote = random_quote()
            status = self.console.status(
                f"[dim]思考中...[/]\n  [dim italic]{quote}[/]", spinner="dots",
            )
            status.start()
        buffer = ""
        live = None
        try:
            async for chunk in stream:
                if live is None:
                    status.stop()
                    live = Live(
                        Styled(Markdown(""), style=style),
                        console=self.console,
                        refresh_per_second=_LIVE_REFRESH_RATE,
                    )
                    live.start()
                buffer += chunk
                live.update(Styled(Markdown(buffer), style=style))

                if self._typewriter_effect:
                    stripped = chunk.rstrip()
                    if stripped:
                        last_char = stripped[-1]
                        if last_char in _TYPEWRITER_PAUSES:
                            await asyncio.sleep(_TYPEWRITER_PAUSES[last_char])
                    if buffer.endswith("\n\n"):
                        await asyncio.sleep(_TYPEWRITER_PAUSES["\n\n"])
        except Exception as exc:
            logger.warning("render_stream interrupted: %s", exc)
        finally:
            if live is not None:
                live.stop()
            else:
                status.stop()

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
        from rich.markdown import Markdown
        self.console.print()
        self.console.print(Markdown(location.description))
        self.console.print()
        self.render_onboarding_hint(
            "输入你想做的任何事，比如'看看四周'或'和酒保说话'"
        )

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

    async def get_input(
        self,
        config: PromptConfig | None = None,
        extra_bindings: KeyBindings | None = None,
    ) -> str:
        prompt_text = config.prompt_text if config else "▸ "
        prompt_html = HTML(f"<ansigreen><b>{prompt_text} </b></ansigreen>")
        try:
            session_kwargs: dict = {}
            if extra_bindings is not None:
                from prompt_toolkit.key_binding import merge_key_bindings
                merged = merge_key_bindings([self._session.key_bindings or KeyBindings(), extra_bindings])
                session_kwargs["key_bindings"] = merged
            return (await self._session.prompt_async(prompt_html, **session_kwargs)).strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"

    async def get_input_with_card_hints(self, hints: list[str], extra_bindings: KeyBindings | None = None) -> str:
        if not hints:
            return await self.get_input()

        selected_index = [0]
        input_text = [""]
        total = len(hints) + 1

        def _get_display():
            return _build_card_display(hints, selected_index[0], input_text[0])

        bindings = KeyBindings()

        @bindings.add("up")
        def _up(event):
            selected_index[0] = (selected_index[0] - 1) % total

        @bindings.add("down")
        def _down(event):
            selected_index[0] = (selected_index[0] + 1) % total

        @bindings.add("enter")
        def _enter(event):
            idx = selected_index[0]
            if idx < len(hints):
                event.app.exit(result=hints[idx])
            elif input_text[0].strip():
                event.app.exit(result=input_text[0].strip())

        @bindings.add("c-c")
        def _ctrl_c(event):
            event.app.exit(result="/quit")

        @bindings.add("c-d")
        def _ctrl_d(event):
            event.app.exit(result="/quit")

        @bindings.add("backspace")
        def _backspace(event):
            if selected_index[0] == len(hints) and input_text[0]:
                input_text[0] = input_text[0][:-1]

        @bindings.add("<any>")
        def _any_key(event):
            char = event.data
            if not char.isprintable() or len(char) != 1:
                return
            is_input_row = selected_index[0] == len(hints)
            is_shortcut = (
                not input_text[0]
                and char in "123"
                and int(char) <= len(hints)
            )
            if is_shortcut:
                event.app.exit(result=hints[int(char) - 1])
                return
            if not is_input_row:
                selected_index[0] = len(hints)
            input_text[0] += char

        control = PTKFormattedTextControl(_get_display)
        layout = Layout(Window(content=control, dont_extend_height=True))
        style = _card_style()

        final_bindings = bindings
        if extra_bindings is not None:
            from prompt_toolkit.key_binding import merge_key_bindings
            final_bindings = merge_key_bindings([bindings, extra_bindings])

        app: Application[str] = Application(
            layout=layout,
            key_bindings=final_bindings,
            style=style,
            full_screen=False,
        )

        result = await app.run_async()
        return result or "/quit"

    def render_dialogue_start(
        self, ctx: DialogueContext, response: DialogueResponse
    ) -> None:
        tone_label = {"hostile": "敌意", "neutral": "中立", "friendly": "友好"}.get(
            ctx.tone, ctx.tone
        )
        self.console.print(
            Panel(
                f"[bold]{ctx.npc_name}[/] — 关系：{ctx.trust} ({tone_label})\n\n"
                "[dim]输入 bye / 再见 退出对话[/]",
                title=f"💬 {ctx.npc_name}",
                border_style="cyan",
            )
        )
        self.console.print(f"  [cyan]{ctx.npc_name}:[/] ", end="")
        self.console.file.flush()

    async def render_dialogue_streaming(self, text: str) -> None:
        for ch in text:
            self.console.print(ch, end="", highlight=False)
            self.console.file.flush()
            if self._typewriter_effect and ch in _TYPEWRITER_PAUSES:
                await asyncio.sleep(_TYPEWRITER_PAUSES[ch])
            elif self._typewriter_effect:
                await asyncio.sleep(_TYPEWRITER_CHAR_DELAY)
        self.console.print()

    async def render_dialogue_with_typewriter(
        self, npc_name: str, response: DialogueResponse
    ) -> None:
        delta = response.trust_delta
        if delta > 0:
            delta_str = f"[green]+{delta}[/]"
        elif delta < 0:
            delta_str = f"[red]{delta}[/]"
        else:
            delta_str = "[dim]±0[/]"

        self.console.print(f"  [cyan]{npc_name}:[/] ", end="")
        self.console.file.flush()
        for ch in response.text:
            self.console.print(ch, end="", highlight=False)
            self.console.file.flush()
            if self._typewriter_effect and ch in _TYPEWRITER_PAUSES:
                await asyncio.sleep(_TYPEWRITER_PAUSES[ch])
            elif self._typewriter_effect:
                await asyncio.sleep(_TYPEWRITER_CHAR_DELAY)
        self.console.print()
        self.console.print(
            f"  [dim]情绪: {response.mood}  关系变化: {delta_str}[/]"
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

    def render_quest_notification(
        self, quest_id: str, status: str, description: str = "",
    ) -> None:
        _QUEST_ICONS: dict[str, tuple[str, str]] = {
            "active": ("📜 新任务", "bright_cyan"),
            "discovered": ("🔍 线索", "cyan"),
            "completed": ("✅ 任务完成", "green"),
            "abandoned": ("❌ 任务失败", "red"),
            "reported": ("📨 任务更新", "yellow"),
            "amulet_found": ("📨 任务更新", "yellow"),
            "found_box": ("📨 任务更新", "yellow"),
        }
        icon, color = _QUEST_ICONS.get(status, ("📨 任务更新", "yellow"))
        body = f"[bold]{quest_id}[/]"
        if description:
            body += f"\n{description}"
        self.console.print(
            Panel(body, title=icon, border_style=color, padding=(0, 2))
        )

    def render_quest_expiry_warning(
        self, quest_id: str, turns_left: int, description: str = "",
    ) -> None:
        body = f"[bold]{quest_id}[/] — 还剩 {turns_left} 回合"
        if description:
            body += f"\n{description}"
        self.console.print(
            Panel(body, title="⚠ 任务即将过期", border_style="bright_yellow", padding=(0, 2))
        )

    def render_onboarding_hint(self, hint: str) -> None:
        self.console.print(f"\n  [dim italic]💡 {hint}[/]\n")

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

    async def get_dialogue_input(self) -> str:
        try:
            return (await self._session.prompt_async(HTML("<ansicyan><b>对话▸ </b></ansicyan>"))).strip()
        except (EOFError, KeyboardInterrupt):
            return "bye"


def render_markdown_text(console: Console, text: str) -> None:
    from rich.markdown import Markdown
    console.print(Markdown(text))
