# src/tavern/engine/keybinding_bridge.py
from __future__ import annotations

from collections.abc import Callable, Sequence

from prompt_toolkit.key_binding import KeyBindings

from tavern.engine.fsm import GameMode
from tavern.engine.keybindings import KeybindingBlock, KeybindingResolver


_ACTION_TO_TEXT: dict[str, str] = {
    "move_north": "前往北方",
    "move_south": "前往南方",
    "move_east": "前往东方",
    "move_west": "前往西方",
    "look_around": "/look",
    "open_inventory": "/inventory",
    "talk_nearest": "和最近的人交谈",
    "show_help": "/help",
    "save_game": "/save",
    "end_dialogue": "bye",
    "select_hint_1": "1",
    "select_hint_2": "2",
    "select_hint_3": "3",
}


class KeybindingBridge:
    """Adapts KeybindingResolver mappings into prompt_toolkit KeyBindings."""

    ACTION_TO_TEXT: dict[str, str] = _ACTION_TO_TEXT

    def __init__(
        self,
        resolver: KeybindingResolver,
        blocks: Sequence[KeybindingBlock] = (),
    ) -> None:
        self._resolver = resolver
        self._blocks = tuple(blocks)

    def build_ptk_bindings(
        self,
        mode: GameMode,
    ) -> KeyBindings:
        bindings = KeyBindings()
        context_map = self._resolver.get_context_map(mode)

        allow_in_text_keys: set[str] = set()
        for block in self._blocks:
            if block.context == mode:
                for kb in block.bindings:
                    if kb.allow_in_text:
                        allow_in_text_keys.add(kb.key)

        for key, action in context_map.items():
            text = self.ACTION_TO_TEXT.get(action)
            if text is None:
                continue
            self._register_key(
                bindings, key, text,
                hotkey_only=key not in allow_in_text_keys,
            )

        return bindings

    @staticmethod
    def _register_key(
        bindings: KeyBindings,
        key: str,
        text: str,
        *,
        hotkey_only: bool = True,
    ) -> None:
        ptk_key = key.replace("ctrl+", "c-")

        @bindings.add(ptk_key, eager=True)
        def handler(event, _text: str = text, _hotkey_only: bool = hotkey_only) -> None:
            if _hotkey_only and event.app.current_buffer.text.strip():
                event.app.current_buffer.insert_text(event.data)
                return
            event.app.exit(result=_text)

    def get_bindings_for_help(self, mode: GameMode) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for block in self._blocks:
            if block.context == mode:
                result.extend((kb.key, kb.description) for kb in block.bindings)
        return result
