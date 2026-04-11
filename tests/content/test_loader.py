from __future__ import annotations

import pytest

from tavern.content.loader import ContentEntry, ContentError, VariantDef, validate_content_id


def test_variant_def_frozen():
    v = VariantDef(name="night", when="time:night")
    assert v.name == "night"
    assert v.when == "time:night"
    with pytest.raises(AttributeError):
        v.name = "day"


def test_content_entry_defaults():
    entry = ContentEntry(
        id="tavern_hall",
        content_type="room",
        metadata={},
        body="默认描述",
        variants={},
        variant_defs=(),
    )
    assert entry.id == "tavern_hall"
    assert entry.content_type == "room"
    assert entry.body == "默认描述"
    assert entry.variants == {}


def test_content_entry_with_variants():
    entry = ContentEntry(
        id="tavern_hall",
        content_type="room",
        metadata={"atmosphere": "warm"},
        body="默认描述",
        variants={"night": "夜晚描述", "after_secret": "秘密后描述"},
        variant_defs=(
            VariantDef(name="after_secret", when="event:cellar_secret_revealed"),
            VariantDef(name="night", when="time:night"),
        ),
    )
    assert len(entry.variant_defs) == 2
    assert entry.variants["night"] == "夜晚描述"


def test_content_error():
    with pytest.raises(ContentError, match="invalid"):
        raise ContentError("invalid content id")


def test_validate_content_id_valid():
    validate_content_id("tavern_hall")
    validate_content_id("bar_area_01")


def test_validate_content_id_invalid():
    with pytest.raises(ContentError, match="Invalid content ID"):
        validate_content_id("Invalid-ID")

    with pytest.raises(ContentError, match="Invalid content ID"):
        validate_content_id("has.dot")

    with pytest.raises(ContentError, match="Invalid content ID"):
        validate_content_id("has space")
