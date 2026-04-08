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

    def list_saves(self) -> list[SaveInfo]:
        if not self._saves_dir.exists():
            return []
        saves: list[SaveInfo] = []
        for path in self._saves_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                saves.append(SaveInfo(
                    slot=data.get("slot", path.stem),
                    timestamp=data.get("timestamp", ""),
                    path=path,
                ))
            except Exception:
                logger.warning("list_saves: skipping unreadable file %s", path)
        saves.sort(key=lambda s: s.timestamp, reverse=True)
        return saves

    def exists(self, slot: str) -> bool:
        return (self._saves_dir / f"{slot}.json").exists()

    def load(self, slot: str = "autosave") -> WorldState:
        path = self._saves_dir / f"{slot}.json"
        if not path.exists():
            raise FileNotFoundError(f"存档不存在：{slot}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"存档文件损坏：{slot}") from exc
        if data.get("version") != SAVE_VERSION:
            raise ValueError("存档版本不兼容，请重新开始游戏")
        return WorldState.model_validate(data["state"])
