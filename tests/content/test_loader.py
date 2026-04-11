from __future__ import annotations

import pytest

from pathlib import Path

from tavern.content.loader import ContentEntry, ContentError, ContentLoader, VariantDef, validate_content_id


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


@pytest.fixture
def content_dir(tmp_path):
    rooms = tmp_path / "rooms"
    rooms.mkdir()

    (rooms / "tavern_hall.md").write_text(
        "---\n"
        "id: tavern_hall\n"
        "type: room\n"
        "variants:\n"
        "  - name: after_secret\n"
        '    when: "event:cellar_secret_revealed"\n'
        "  - name: night\n"
        '    when: "time:night"\n'
        "tags: [main_area]\n"
        "---\n"
        "\n"
        "你站在酒馆大厅中。\n",
        encoding="utf-8",
    )

    (rooms / "tavern_hall.night.md").write_text(
        "酒馆已近打烊时分。\n",
        encoding="utf-8",
    )
    (rooms / "tavern_hall.after_secret.md").write_text(
        "大厅里的气氛变了。\n",
        encoding="utf-8",
    )

    (rooms / "bar_area.md").write_text(
        "---\n"
        "id: bar_area\n"
        "type: room\n"
        "---\n"
        "\n"
        "吧台区域。\n",
        encoding="utf-8",
    )

    npcs = tmp_path / "npcs"
    npcs.mkdir()
    (npcs / "bartender_grim.md").write_text(
        "---\n"
        "id: bartender_grim\n"
        "type: npc\n"
        "personality_tags: [guarded]\n"
        "---\n"
        "\n"
        "壮实的中年男人。\n",
        encoding="utf-8",
    )

    return tmp_path


def test_load_directory_finds_all_entries(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    assert "tavern_hall" in loader.entries
    assert "bar_area" in loader.entries
    assert "bartender_grim" in loader.entries
    assert len(loader.entries) == 3


def test_load_directory_parses_frontmatter(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert entry.content_type == "room"
    assert "main_area" in entry.metadata.get("tags", [])
    assert len(entry.variant_defs) == 2


def test_load_directory_loads_variant_bodies(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert "night" in entry.variants
    assert "after_secret" in entry.variants
    assert "打烊" in entry.variants["night"]
    assert "气氛变了" in entry.variants["after_secret"]


def test_load_directory_default_body(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    entry = loader.entries["tavern_hall"]
    assert "酒馆大厅" in entry.body


def test_resolve_returns_default_body(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)
    body = loader.resolve("tavern_hall")
    assert "酒馆大厅" in body


def test_resolve_returns_none_for_unknown_id():
    loader = ContentLoader()
    result = loader.resolve("nonexistent")
    assert result is None


def test_resolve_with_condition_evaluator(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)

    def eval_fn(cond_str, **kwargs):
        return "cellar_secret_revealed" in cond_str

    body = loader.resolve("tavern_hall", condition_evaluator=eval_fn)
    assert "气氛变了" in body


def test_resolve_condition_no_match(content_dir):
    loader = ContentLoader()
    loader.load_directory(content_dir)

    def eval_fn(cond_str, **kwargs):
        return False

    body = loader.resolve("tavern_hall", condition_evaluator=eval_fn)
    assert "酒馆大厅" in body


def test_load_invalid_id(tmp_path):
    rooms = tmp_path / "rooms"
    rooms.mkdir()
    (rooms / "Invalid-ID.md").write_text(
        "---\nid: Invalid-ID\ntype: room\n---\n\nbody\n",
        encoding="utf-8",
    )
    loader = ContentLoader()
    with pytest.raises(ContentError, match="Invalid content ID"):
        loader.load_directory(tmp_path)


def test_load_empty_directory(tmp_path):
    loader = ContentLoader()
    loader.load_directory(tmp_path)
    assert len(loader.entries) == 0


def test_load_nonexistent_directory():
    loader = ContentLoader()
    loader.load_directory(Path("/nonexistent/path"))
    assert len(loader.entries) == 0


def test_parse_frontmatter_no_frontmatter():
    from tavern.content.loader import _parse_frontmatter
    meta, body = _parse_frontmatter("Just plain text")
    assert meta == {}
    assert body == "Just plain text"
