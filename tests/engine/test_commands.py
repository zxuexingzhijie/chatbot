from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from unittest.mock import AsyncMock

import pytest

from tavern.engine.commands import CommandRegistry, GameCommand


class _GameMode(str, Enum):
    EXPLORING = "exploring"
    DIALOGUE = "dialogue"
    COMBAT = "combat"


@dataclass(frozen=True)
class _FakeState:
    turn: int = 0
    is_in_combat: bool = False


class TestCommandRegistry:
    def _make_registry(self) -> CommandRegistry:
        r = CommandRegistry()
        r.register(GameCommand(
            name="/look",
            aliases=("/l",),
            description="查看环境",
            available_in=(_GameMode.EXPLORING, _GameMode.COMBAT),
            execute=AsyncMock(),
        ))
        r.register(GameCommand(
            name="/save",
            aliases=("/s",),
            description="保存",
            available_in=(_GameMode.EXPLORING,),
            is_available=lambda s: not s.is_in_combat,
            execute=AsyncMock(),
        ))
        r.register(GameCommand(
            name="/debug",
            description="调试",
            available_in=(_GameMode.EXPLORING,),
            execute=AsyncMock(),
        ))
        return r

    def test_find_by_name(self):
        r = self._make_registry()
        assert r.find("/look") is not None
        assert r.find("/look").name == "/look"

    def test_find_by_alias(self):
        r = self._make_registry()
        cmd = r.find("/l")
        assert cmd is not None
        assert cmd.name == "/look"

    def test_find_unknown_returns_none(self):
        r = self._make_registry()
        assert r.find("/unknown") is None

    def test_get_available_filters_by_mode(self):
        r = self._make_registry()
        state = _FakeState()
        available = r.get_available(_GameMode.COMBAT, state)
        names = [c.name for c in available]
        assert "/look" in names
        assert "/save" not in names

    def test_get_available_checks_is_available(self):
        r = self._make_registry()
        state = _FakeState(is_in_combat=True)
        available = r.get_available(_GameMode.EXPLORING, state)
        names = [c.name for c in available]
        assert "/save" not in names

    def test_get_completions(self):
        r = self._make_registry()
        state = _FakeState()
        completions = r.get_completions(_GameMode.EXPLORING, state)
        assert "/look" in completions
        assert "/save" in completions
        assert "/debug" in completions
