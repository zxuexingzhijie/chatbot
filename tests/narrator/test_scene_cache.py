# tests/narrator/test_scene_cache.py
from __future__ import annotations

import pytest

from tavern.engine.seeded_rng import AmbienceDetails
from tavern.narrator.scene_cache import SceneContext, SceneContextCache


@pytest.fixture
def sample_context():
    return SceneContext(
        location_description="酒馆大厅",
        npcs_present=("格林",),
        items_visible=("旧告示",),
        exits_available=("吧台", "走廊"),
        atmosphere="warm",
        ambience=AmbienceDetails(
            weather="晴朗", crowd_level="热闹",
            background_sound="炉火噼啪作响", smell="麦酒的醇厚气息",
        ),
    )


def test_scene_context_frozen(sample_context):
    with pytest.raises(AttributeError):
        sample_context.atmosphere = "cold"


def test_cache_put_and_get(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    result = cache.get("tavern_hall", 1)
    assert result is sample_context


def test_cache_miss_returns_none():
    cache = SceneContextCache()
    assert cache.get("tavern_hall", 1) is None


def test_cache_version_mismatch(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    assert cache.get("tavern_hall", 2) is None


def test_cache_put_clears_old_versions(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("tavern_hall", 3, sample_context)
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("tavern_hall", 3) is sample_context


def test_cache_invalidate_specific(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("bar_area", 1, sample_context)
    cache.invalidate("tavern_hall")
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("bar_area", 1) is sample_context


def test_cache_invalidate_all(sample_context):
    cache = SceneContextCache()
    cache.put("tavern_hall", 1, sample_context)
    cache.put("bar_area", 1, sample_context)
    cache.invalidate()
    assert cache.get("tavern_hall", 1) is None
    assert cache.get("bar_area", 1) is None


def test_cache_lru_eviction(sample_context):
    cache = SceneContextCache()
    cache.MAX_ENTRIES = 3
    cache.put("loc_a", 1, sample_context)
    cache.put("loc_b", 1, sample_context)
    cache.put("loc_c", 1, sample_context)
    cache.get("loc_a", 1)
    cache.put("loc_d", 1, sample_context)
    assert cache.get("loc_a", 1) is sample_context
    assert cache.get("loc_b", 1) is None
    assert cache.get("loc_c", 1) is sample_context
    assert cache.get("loc_d", 1) is sample_context
