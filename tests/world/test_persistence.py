from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tavern.world.persistence import SaveInfo, SaveManager
from tavern.world.state import WorldState
from tavern.world.models import Character, CharacterRole, Location


@pytest.fixture
def minimal_state():
    return WorldState(
        turn=3,
        player_id="player",
        locations={
            "room": Location(id="room", name="房间", description="一个房间")
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="room",
            )
        },
        items={},
    )


def test_save_creates_file(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "autosave")
    assert (tmp_path / "saves" / "autosave.json").exists()


def test_save_envelope_format(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "autosave")
    data = json.loads((tmp_path / "saves" / "autosave.json").read_text())
    assert data["version"] == 1
    assert "timestamp" in data
    assert data["slot"] == "autosave"
    assert "state" in data


def test_save_named_slot(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "mygame")
    assert (tmp_path / "saves" / "mygame.json").exists()


def test_saves_dir_created_on_first_save(tmp_path, minimal_state):
    saves_dir = tmp_path / "nonexistent" / "saves"
    assert not saves_dir.exists()
    mgr = SaveManager(saves_dir)
    mgr.save(minimal_state, "autosave")
    assert saves_dir.exists()


def test_save_load_roundtrip(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "autosave")
    loaded = mgr.load("autosave")
    assert loaded.turn == minimal_state.turn
    assert loaded.player_id == minimal_state.player_id
    assert loaded.characters["player"].stats["hp"] == 100


def test_load_nonexistent_slot(tmp_path):
    mgr = SaveManager(tmp_path / "saves")
    with pytest.raises(FileNotFoundError, match="autosave"):
        mgr.load("autosave")


def test_load_corrupt_json(tmp_path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    (saves_dir / "bad.json").write_text("not valid json", encoding="utf-8")
    mgr = SaveManager(saves_dir)
    with pytest.raises(ValueError, match="bad"):
        mgr.load("bad")


def test_load_wrong_version(tmp_path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    import json as _json
    bad_envelope = {
        "version": 99,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "slot": "test",
        "state": {},
    }
    (saves_dir / "test.json").write_text(_json.dumps(bad_envelope), encoding="utf-8")
    mgr = SaveManager(saves_dir)
    with pytest.raises(ValueError, match="版本不兼容"):
        mgr.load("test")


def test_list_saves_empty(tmp_path):
    mgr = SaveManager(tmp_path / "saves")
    assert mgr.list_saves() == []


def test_list_saves_returns_saveinfo(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "slot1")
    saves = mgr.list_saves()
    assert len(saves) == 1
    assert saves[0].slot == "slot1"
    assert saves[0].path == tmp_path / "saves" / "slot1.json"
    assert "T" in saves[0].timestamp  # ISO 8601


def test_list_saves_sorted_by_timestamp_desc(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "old")
    time.sleep(0.01)
    mgr.save(minimal_state, "new")
    saves = mgr.list_saves()
    assert saves[0].slot == "new"
    assert saves[1].slot == "old"


def test_exists_true(tmp_path, minimal_state):
    mgr = SaveManager(tmp_path / "saves")
    mgr.save(minimal_state, "autosave")
    assert mgr.exists("autosave") is True


def test_exists_false(tmp_path):
    mgr = SaveManager(tmp_path / "saves")
    assert mgr.exists("autosave") is False
