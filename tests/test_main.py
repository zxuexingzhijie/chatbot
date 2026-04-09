from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reload_main():
    """Reload __main__ before each test so patches take effect."""
    import tavern.__main__ as mod
    importlib.reload(mod)
    yield


def test_no_args_runs_game():
    with patch("sys.argv", ["tavern"]):
        import tavern.__main__ as mod
        importlib.reload(mod)
        with patch.object(mod, "_run_game") as mock_run:
            mod.main()
            mock_run.assert_called_once()


def test_run_subcommand_runs_game():
    with patch("sys.argv", ["tavern", "run"]):
        import tavern.__main__ as mod
        importlib.reload(mod)
        with patch.object(mod, "_run_game") as mock_run:
            mod.main()
            mock_run.assert_called_once()


def test_run_subcommand_with_custom_config():
    with patch("sys.argv", ["tavern", "run", "--config", "custom.yaml"]):
        import tavern.__main__ as mod
        importlib.reload(mod)
        with patch.object(mod, "_run_game") as mock_run:
            mod.main()
            mock_run.assert_called_once_with("custom.yaml")


def test_create_scenario_calls_scaffold(tmp_path):
    with patch("sys.argv", ["tavern", "create-scenario", "my_test", "--dir", str(tmp_path)]):
        import tavern.__main__ as mod
        importlib.reload(mod)
        with patch("tavern.world.scenario.scaffold_scenario") as mock_scaffold:
            mock_scaffold.return_value = tmp_path / "my_test"
            mod.main()
            mock_scaffold.assert_called_once_with("my_test", Path(str(tmp_path)))
