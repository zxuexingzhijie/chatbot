from tavern.engine.fsm import GameMode, Keybinding
from tavern.engine.keybindings import (
    DEFAULT_BINDINGS, InputMode, KeybindingBlock, KeybindingResolver,
)


class TestInputMode:
    def test_hotkey_value(self):
        assert InputMode.HOTKEY.value == "hotkey"

    def test_text_value(self):
        assert InputMode.TEXT.value == "text"


class TestKeybindingResolver:
    def _make_resolver(self) -> KeybindingResolver:
        return KeybindingResolver(DEFAULT_BINDINGS)

    def test_resolve_hotkey_mode_exploring(self):
        resolver = self._make_resolver()
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action == "move_north"

    def test_resolve_hotkey_mode_unknown_key(self):
        resolver = self._make_resolver()
        action = resolver.resolve("z", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action is None

    def test_resolve_text_mode_ignores_hotkeys(self):
        resolver = self._make_resolver()
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.TEXT)
        assert action is None

    def test_resolve_text_mode_with_allow_in_text_and_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "1", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=True,
        )
        assert action == "select_hint_1"

    def test_resolve_text_mode_allow_in_text_non_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "1", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=False,
        )
        assert action is None

    def test_resolve_escape_in_text_mode_empty_buffer(self):
        resolver = self._make_resolver()
        action = resolver.resolve(
            "escape", GameMode.DIALOGUE, InputMode.TEXT, buffer_empty=True,
        )
        assert action == "end_dialogue"

    def test_resolve_hotkey_mode_combat(self):
        resolver = self._make_resolver()
        action = resolver.resolve("a", GameMode.COMBAT, InputMode.HOTKEY)
        assert action == "attack"

    def test_resolve_no_bindings_for_mode(self):
        resolver = KeybindingResolver([])
        action = resolver.resolve("n", GameMode.EXPLORING, InputMode.HOTKEY)
        assert action is None


class TestDefaultBindings:
    def test_exploring_has_direction_keys(self):
        exploring = [b for b in DEFAULT_BINDINGS if b.context == GameMode.EXPLORING]
        assert len(exploring) == 1
        keys = {kb.key for kb in exploring[0].bindings}
        assert {"n", "s", "e", "w"}.issubset(keys)

    def test_dialogue_has_hint_keys(self):
        dialogue = [b for b in DEFAULT_BINDINGS if b.context == GameMode.DIALOGUE]
        assert len(dialogue) == 1
        keys = {kb.key for kb in dialogue[0].bindings}
        assert {"1", "2", "3", "escape"}.issubset(keys)

    def test_combat_has_action_keys(self):
        combat = [b for b in DEFAULT_BINDINGS if b.context == GameMode.COMBAT]
        assert len(combat) == 1
        keys = {kb.key for kb in combat[0].bindings}
        assert {"a", "d", "r"}.issubset(keys)
