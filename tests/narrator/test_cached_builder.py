from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tavern.engine.seeded_rng import AmbienceDetails
from tavern.narrator.cached_builder import CachedPromptBuilder
from tavern.narrator.scene_cache import SceneContext, SceneContextCache
from tavern.world.models import Character, CharacterRole, Item, Location
from tavern.world.state import WorldState


def _make_state(location_id="tavern_hall", turn=1, version=1):
    state = WorldState(
        turn=turn,
        player_id="player",
        locations={
            location_id: Location(
                id=location_id, name="酒馆大厅",
                description="YAML描述", atmosphere="warm",
                exits={}, items=("old_notice",), npcs=("bartender_grim",),
            ),
        },
        characters={
            "player": Character(
                id="player", name="冒险者", role=CharacterRole.PLAYER,
                location_id=location_id, traits=(), stats={}, inventory=(),
            ),
            "bartender_grim": Character(
                id="bartender_grim", name="格林", role=CharacterRole.NPC,
                location_id=location_id, traits=(), stats={}, inventory=(),
            ),
        },
        items={
            "old_notice": Item(id="old_notice", name="旧告示", description="一张旧告示"),
        },
    )
    return state


@pytest.fixture
def builder():
    content_loader = MagicMock()
    content_loader.resolve.return_value = None

    cache = SceneContextCache()

    state_manager = MagicMock()
    state_manager.version = 1

    return CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )


def test_build_scene_context_returns_scene_context(builder):
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert isinstance(ctx, SceneContext)
    assert ctx.atmosphere == "warm"
    assert "格林" in ctx.npcs_present


def test_build_scene_context_cache_hit(builder):
    state = _make_state()
    ctx1 = builder.build_scene_context(state)
    ctx2 = builder.build_scene_context(state)
    assert ctx1 is ctx2


def test_build_scene_context_uses_content_loader():
    content_loader = MagicMock()
    content_loader.resolve.return_value = "Markdown描述内容"
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1

    builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert ctx.location_description == "Markdown描述内容"


def test_build_scene_context_fallback_to_yaml():
    content_loader = MagicMock()
    content_loader.resolve.return_value = None
    cache = SceneContextCache()
    state_manager = MagicMock()
    state_manager.version = 1

    builder = CachedPromptBuilder(
        content_loader=content_loader,
        cache=cache,
        state_manager=state_manager,
    )
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert ctx.location_description == "YAML描述"


def test_build_scene_context_includes_ambience(builder):
    state = _make_state()
    ctx = builder.build_scene_context(state)
    assert isinstance(ctx.ambience, AmbienceDetails)
    assert ctx.ambience.weather
