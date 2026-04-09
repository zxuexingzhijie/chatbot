from __future__ import annotations

from pathlib import Path

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

    def test_bundled_default_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        result = GameApp._load_config(None)
        assert result.get("game", {}).get("scenario") == "tavern"
