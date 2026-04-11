# tests/engine/test_keybinding_bridge.py
from __future__ import annotations

import pytest

from tavern.engine.fsm import GameMode, Keybinding
from tavern.engine.keybindings import (
    DEFAULT_BINDINGS,
    InputMode,
    KeybindingBlock,
    KeybindingResolver,
)
from tavern.engine.keybinding_bridge import KeybindingBridge


@pytest.fixture
def bridge():
    resolver = KeybindingResolver(DEFAULT_BINDINGS)
    return KeybindingBridge(resolver, blocks=DEFAULT_BINDINGS)


class TestActionToText:
    def test_move_north_maps_to_chinese(self, bridge):
        assert bridge.ACTION_TO_TEXT["move_north"] == "前往北方"

    def test_look_around_maps_to_slash_command(self, bridge):
        assert bridge.ACTION_TO_TEXT["look_around"] == "/look"

    def test_all_exploring_actions_have_mapping(self, bridge):
        exploring_block = next(
            b for b in DEFAULT_BINDINGS if b.context == GameMode.EXPLORING
        )
        for kb in exploring_block.bindings:
            assert kb.action in bridge.ACTION_TO_TEXT, (
                f"Missing ACTION_TO_TEXT mapping for {kb.action}"
            )


class TestBuildPtkBindings:
    def test_returns_key_bindings_object(self, bridge):
        from prompt_toolkit.key_binding import KeyBindings
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.EXPLORING, on_action=actions.append,
        )
        assert isinstance(bindings, KeyBindings)

    def test_exploring_bindings_count(self, bridge):
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.EXPLORING, on_action=actions.append,
        )
        assert len(bindings.bindings) > 0

    def test_unknown_mode_returns_empty_bindings(self, bridge):
        actions: list[str] = []
        bindings = bridge.build_ptk_bindings(
            GameMode.INVENTORY, on_action=actions.append,
        )
        assert len(bindings.bindings) == 0


class TestGetBindingsForHelp:
    def test_exploring_help_returns_tuples(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.EXPLORING)
        assert len(result) > 0
        for key, desc in result:
            assert isinstance(key, str)
            assert isinstance(desc, str)

    def test_exploring_help_contains_nsew(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.EXPLORING)
        keys = [k for k, _ in result]
        assert "n" in keys
        assert "s" in keys

    def test_empty_mode_returns_empty(self, bridge):
        result = bridge.get_bindings_for_help(GameMode.INVENTORY)
        assert result == []
