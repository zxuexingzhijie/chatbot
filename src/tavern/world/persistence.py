from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

SAVE_VERSION = 1


def _mapping_proxy_fallback(obj: Any) -> Any:
    if isinstance(obj, MappingProxyType):
        return dict(obj)
    raise ValueError(f"Cannot serialize {type(obj)}")


@dataclass(frozen=True)
class SaveInfo:
    slot: str
    timestamp: str  # ISO 8601
    path: Path


class SaveManager:
    def __init__(self, saves_dir: Path) -> None:
        self._saves_dir = saves_dir

    def save(self, state: WorldState, slot: str = "autosave") -> Path:
        self._saves_dir.mkdir(parents=True, exist_ok=True)
        path = self._saves_dir / f"{slot}.json"
        timestamp = datetime.now(timezone.utc).isoformat()
        envelope = {
            "version": SAVE_VERSION,
            "timestamp": timestamp,
            "slot": slot,
            "state": json.loads(state.model_dump_json(fallback=_mapping_proxy_fallback)),
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
