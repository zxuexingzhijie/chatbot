from __future__ import annotations

import json
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
