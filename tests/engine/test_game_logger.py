from __future__ import annotations

import json
from pathlib import Path

import pytest

from tavern.engine.game_logger import GameLogEntry, GameLogger


@pytest.fixture
def log_dir(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    return d


def test_game_log_entry_frozen():
    entry = GameLogEntry(
        timestamp="2026-04-11T14:30:00", turn=1,
        session_id="test123", entry_type="player_input",
        data={"raw": "查看四周"},
    )
    assert entry.turn == 1
    with pytest.raises(AttributeError):
        entry.turn = 2


def test_logger_log_and_flush(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s1", flush_interval=999)
    entry = GameLogEntry(
        timestamp="2026-04-11T14:30:00", turn=1,
        session_id="s1", entry_type="player_input",
        data={"raw": "查看四周"},
    )
    gl.log(entry)
    assert len(gl._buffer) == 1
    gl.flush()
    assert len(gl._buffer) == 0
    assert (log_dir / "s1.jsonl").exists()
    lines = (log_dir / "s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["turn"] == 1
    assert parsed["data"]["raw"] == "查看四周"


def test_logger_multiple_entries(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s2", flush_interval=999)
    for i in range(5):
        gl.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s2",
            entry_type="player_input", data={"raw": f"action_{i}"},
        ))
    gl.flush()
    lines = (log_dir / "s2.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5


def test_logger_read_recent(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s3", flush_interval=999)
    for i in range(10):
        gl.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s3",
            entry_type="player_input", data={"raw": f"action_{i}"},
        ))
    gl.flush()
    recent = gl.read_recent(n=3)
    assert len(recent) == 3
    assert recent[-1].data["raw"] == "action_9"
    assert recent[0].data["raw"] == "action_7"


def test_logger_read_recent_includes_buffer(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s4", flush_interval=999)
    for i in range(3):
        gl.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s4",
            entry_type="player_input", data={"raw": f"disk_{i}"},
        ))
    gl.flush()
    gl.log(GameLogEntry(
        timestamp="t3", turn=3, session_id="s4",
        entry_type="player_input", data={"raw": "buffer_3"},
    ))
    recent = gl.read_recent(n=2)
    assert len(recent) == 2
    assert recent[-1].data["raw"] == "buffer_3"


def test_logger_close_flushes(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s5", flush_interval=999)
    gl.log(GameLogEntry(
        timestamp="t0", turn=0, session_id="s5",
        entry_type="test", data={},
    ))
    gl.close()
    assert (log_dir / "s5.jsonl").exists()
    assert len(gl._buffer) == 0


def test_logger_read_recent_empty(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s6", flush_interval=999)
    recent = gl.read_recent(n=5)
    assert recent == []


def test_logger_file_rotation(log_dir):
    gl = GameLogger(log_dir=log_dir, session_id="s7", flush_interval=999)
    gl.MAX_FILE_SIZE = 100  # tiny for testing
    for i in range(20):
        gl.log(GameLogEntry(
            timestamp=f"t{i}", turn=i, session_id="s7",
            entry_type="player_input", data={"raw": "x" * 50},
        ))
        gl.flush()
    files = list(log_dir.glob("s7*.jsonl"))
    assert len(files) >= 2
