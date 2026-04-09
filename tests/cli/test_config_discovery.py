from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tavern.cli.app import GameApp


class TestConfigDiscovery:
    def test_explicit_path_used(self, tmp_path):
        config_file = tmp_path / "my.yaml"
        config_file.write_text(yaml.dump({"game": {"scenario": "custom"}}))
        result = GameApp._load_config(str(config_file))
        assert result["game"]["scenario"] == "custom"

    def test_explicit_path_missing_returns_empty(self, tmp_path):
        result = GameApp._load_config(str(tmp_path / "nonexistent.yaml"))
        assert result == {}

    def test_xdg_config_found(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "tavern"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"game": {"scenario": "xdg_test"}}))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        result = GameApp._load_config(None)
        assert result["game"]["scenario"] == "xdg_test"

    def test_local_config_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"game": {"scenario": "local_test"}}))
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        result = GameApp._load_config(None)
        assert result["game"]["scenario"] == "local_test"

    def test_no_config_triggers_init(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))

        xdg_dir = tmp_path / "fakehome" / ".config" / "tavern"

        def fake_init():
            xdg_dir.mkdir(parents=True, exist_ok=True)
            config_path = xdg_dir / "config.yaml"
            config_path.write_text(
                yaml.dump({"llm": {"intent": {"provider": "openai"}}, "game": {"scenario": "tavern"}}),
            )
            return config_path

        with patch("tavern.cli.init.run_init", fake_init):
            result = GameApp._load_config(None)

        assert result["game"]["scenario"] == "tavern"
        assert result["llm"]["intent"]["provider"] == "openai"

    def test_no_config_init_creates_file_that_is_loaded(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        xdg_base = tmp_path / "xdg"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_base))
        xdg_dir = xdg_base / "tavern"

        def fake_init():
            xdg_dir.mkdir(parents=True, exist_ok=True)
            config_path = xdg_dir / "config.yaml"
            config_path.write_text(
                yaml.dump({"llm": {"intent": {"provider": "anthropic"}}, "game": {"scenario": "tavern"}}),
            )
            return config_path

        with patch("tavern.cli.init.run_init", fake_init):
            result = GameApp._load_config(None)

        assert result["llm"]["intent"]["provider"] == "anthropic"
