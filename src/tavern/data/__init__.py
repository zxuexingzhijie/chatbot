from __future__ import annotations

from importlib import resources
from pathlib import Path


def get_bundled_scenarios_dir() -> Path:
    return Path(str(resources.files("tavern.data") / "scenarios"))


def get_bundled_scenario(name: str) -> Path:
    return get_bundled_scenarios_dir() / name
