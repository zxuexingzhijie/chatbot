from __future__ import annotations

from unittest.mock import MagicMock

from tavern.cli.bootstrap import bootstrap
from tavern.engine.fsm import GameLoop, GameMode


class TestBootstrap:
    def test_returns_game_loop(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert isinstance(loop, GameLoop)

    def test_loop_starts_in_exploring(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert loop.current_mode == GameMode.EXPLORING

    def test_loop_has_exploring_handler(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert GameMode.EXPLORING in loop._handlers

    def test_loop_has_dialogue_handler(self):
        deps = _make_deps()
        loop = bootstrap(**deps)
        assert GameMode.DIALOGUE in loop._handlers

    def test_loop_has_all_effect_executors(self):
        from tavern.engine.fsm import EffectKind
        deps = _make_deps()
        loop = bootstrap(**deps)
        for kind in EffectKind:
            assert kind in loop._effect_executors


def _make_deps() -> dict:
    return dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        intent_parser=MagicMock(),
        logger=MagicMock(),
    )
