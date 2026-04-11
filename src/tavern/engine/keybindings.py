from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from tavern.engine.fsm import GameMode, Keybinding


class InputMode(Enum):
    HOTKEY = "hotkey"
    TEXT = "text"


@dataclass(frozen=True)
class KeybindingBlock:
    context: GameMode
    bindings: tuple[Keybinding, ...]


DEFAULT_BINDINGS: tuple[KeybindingBlock, ...] = (
    KeybindingBlock(
        context=GameMode.EXPLORING,
        bindings=(
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
            Keybinding("ctrl+s", "save_game", "保存游戏"),
        ),
    ),
    KeybindingBlock(
        context=GameMode.DIALOGUE,
        bindings=(
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
        ),
    ),
    KeybindingBlock(
        context=GameMode.COMBAT,
        bindings=(
            Keybinding("a", "attack", "攻击"),
            Keybinding("d", "defend", "防御"),
            Keybinding("r", "run_away", "逃跑"),
            Keybinding("1", "use_skill_1", "使用技能1"),
            Keybinding("2", "use_skill_2", "使用技能2"),
        ),
    ),
)


class KeybindingResolver:
    def __init__(self, blocks: Sequence[KeybindingBlock]) -> None:
        self._by_context: dict[GameMode, dict[str, str]] = {}
        self._text_shortcuts: dict[GameMode, dict[str, str]] = {}
        for block in blocks:
            hotkey_map: dict[str, str] = {}
            text_map: dict[str, str] = {}
            for kb in block.bindings:
                hotkey_map[kb.key] = kb.action
                if kb.allow_in_text:
                    text_map[kb.key] = kb.action
            self._by_context[block.context] = hotkey_map
            self._text_shortcuts[block.context] = text_map

    def get_context_map(self, game_mode: GameMode) -> dict[str, str]:
        return self._by_context.get(game_mode, {})

    def resolve(
        self,
        key: str,
        game_mode: GameMode,
        input_mode: InputMode,
        buffer_empty: bool = False,
    ) -> str | None:
        if input_mode == InputMode.TEXT:
            if not buffer_empty:
                return None
            context_bindings = self._text_shortcuts.get(game_mode, {})
            return context_bindings.get(key)
        context_bindings = self._by_context.get(game_mode, {})
        return context_bindings.get(key)
