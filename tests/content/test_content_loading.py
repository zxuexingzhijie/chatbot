from __future__ import annotations

import pytest
from pathlib import Path

from tavern.content.loader import ContentLoader


@pytest.fixture
def loaded_content():
    content_dir = Path(__file__).resolve().parents[2] / "src" / "tavern" / "data" / "scenarios" / "tavern" / "content"
    loader = ContentLoader()
    loader.load_directory(content_dir)
    return loader


class TestContentFilesLoaded:
    LOCATION_IDS = ["tavern_hall", "bar_area", "cellar", "corridor", "backyard"]
    ITEM_IDS = [
        "old_notice", "cellar_key", "old_barrel", "abandoned_cart",
        "dry_well", "rusty_box", "spare_key", "lost_amulet",
        "map_fragment", "guest_letter",
    ]
    CHARACTER_IDS = ["traveler", "bartender_grim", "mysterious_guest"]

    def test_all_locations_loaded(self, loaded_content):
        for loc_id in self.LOCATION_IDS:
            entry = loaded_content.entries.get(loc_id)
            assert entry is not None, f"Missing location: {loc_id}"
            assert entry.content_type == "location"
            assert len(entry.body) > 0

    def test_all_items_loaded(self, loaded_content):
        for item_id in self.ITEM_IDS:
            entry = loaded_content.entries.get(item_id)
            assert entry is not None, f"Missing item: {item_id}"
            assert entry.content_type == "item"
            assert len(entry.body) > 0

    def test_all_characters_loaded(self, loaded_content):
        for char_id in self.CHARACTER_IDS:
            entry = loaded_content.entries.get(char_id)
            assert entry is not None, f"Missing character: {char_id}"
            assert entry.content_type == "character"
            assert len(entry.body) > 0

    def test_tavern_hall_has_night_variant(self, loaded_content):
        entry = loaded_content.entries["tavern_hall"]
        assert len(entry.variant_defs) == 1
        assert entry.variant_defs[0].name == "night"
        assert entry.variant_defs[0].when == "turn > 20"
        assert "night" in entry.variants
        assert len(entry.variants["night"]) > 0

    def test_resolve_tavern_hall_default(self, loaded_content):
        body = loaded_content.resolve("tavern_hall")
        assert "醉龙酒馆" in body

    def test_resolve_tavern_hall_night_variant(self, loaded_content):
        from tavern.content.conditions import evaluate_content_condition
        body = loaded_content.resolve(
            "tavern_hall",
            condition_evaluator=lambda when, **kw: evaluate_content_condition(when, turn=25),
        )
        assert "夜深" in body or "暗淡" in body

    def test_total_entry_count(self, loaded_content):
        assert len(loaded_content.entries) == 18  # 5 loc + 10 item + 3 char
