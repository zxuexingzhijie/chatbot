from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tavern.narrator.cached_builder import CachedPromptBuilder
from tavern.narrator.scene_cache import SceneContextCache


def _make_builder(content_loader=None):
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1
    return CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )


class TestResolveContent:
    def test_returns_none_when_no_loader(self):
        builder = _make_builder(content_loader=None)
        assert builder.resolve_content("tavern_hall") is None

    def test_returns_resolved_text(self):
        loader = MagicMock()
        loader.resolve.return_value = "Markdown description"
        builder = _make_builder(content_loader=loader)
        result = builder.resolve_content("old_notice")
        assert result == "Markdown description"
        loader.resolve.assert_called_once_with("old_notice")

    def test_returns_none_when_id_not_found(self):
        loader = MagicMock()
        loader.resolve.return_value = None
        builder = _make_builder(content_loader=loader)
        assert builder.resolve_content("nonexistent") is None


class TestBuildSceneContextWithConditionEvaluator:
    def test_passes_condition_evaluator_to_resolve(self):
        loader = MagicMock()
        loader.resolve.return_value = "Night version of hall"
        builder = _make_builder(content_loader=loader)

        state = MagicMock()
        state.player_location = "tavern_hall"
        state.locations = {
            "tavern_hall": MagicMock(
                description="YAML fallback",
                npcs=(),
                items=(),
                exits={},
                atmosphere="warm",
            )
        }
        state.characters = {}
        state.items = {}
        state.turn = 25

        ctx = builder.build_scene_context(state)
        assert ctx.location_description == "Night version of hall"

        call_args = loader.resolve.call_args
        assert call_args[0][0] == "tavern_hall"
        assert "condition_evaluator" in call_args[1]

    def test_fallback_to_yaml_when_loader_returns_none(self):
        loader = MagicMock()
        loader.resolve.return_value = None
        builder = _make_builder(content_loader=loader)

        state = MagicMock()
        state.player_location = "tavern_hall"
        state.locations = {
            "tavern_hall": MagicMock(
                description="YAML description",
                npcs=(),
                items=(),
                exits={},
                atmosphere="warm",
            )
        }
        state.characters = {}
        state.items = {}
        state.turn = 5

        ctx = builder.build_scene_context(state)
        assert ctx.location_description == "YAML description"
