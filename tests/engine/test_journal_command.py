from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tavern.engine.command_defs import cmd_journal
from tavern.engine.game_logger import GameLogEntry, GameLogger


@pytest.fixture
def mock_context_with_logger(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    game_logger = GameLogger(log_dir=log_dir, session_id="test", flush_interval=999)
    for i in range(5):
        game_logger.log(GameLogEntry(
            timestamp=f"2026-04-11T14:3{i}:00", turn=i,
            session_id="test", entry_type="player_input",
            data={"raw": f"动作{i}", "parsed_action": "LOOK"},
        ))
    game_logger.flush()

    renderer = MagicMock()
    renderer.console = MagicMock()
    renderer.console.print = MagicMock()

    ctx = MagicMock()
    ctx.renderer = renderer
    ctx.game_logger = game_logger
    return ctx


@pytest.mark.asyncio
async def test_cmd_journal_renders_entries(mock_context_with_logger):
    await cmd_journal("", mock_context_with_logger)
    calls = mock_context_with_logger.renderer.console.print.call_args_list
    assert len(calls) >= 2  # header + at least one entry + footer


@pytest.mark.asyncio
async def test_cmd_journal_no_logger():
    ctx = MagicMock()
    ctx.game_logger = None
    ctx.renderer = MagicMock()
    ctx.renderer.console = MagicMock()
    await cmd_journal("", ctx)
    ctx.renderer.console.print.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_journal_empty_log(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    game_logger = GameLogger(log_dir=log_dir, session_id="empty", flush_interval=999)

    ctx = MagicMock()
    ctx.game_logger = game_logger
    ctx.renderer = MagicMock()
    ctx.renderer.console = MagicMock()
    await cmd_journal("", ctx)
    ctx.renderer.console.print.assert_called_once()
