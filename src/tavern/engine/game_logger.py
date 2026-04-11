from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameLogEntry:
    timestamp: str
    turn: int
    session_id: str
    entry_type: str
    data: dict


class GameLogger:
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    def __init__(
        self,
        log_dir: Path,
        session_id: str,
        flush_interval: float = 2.0,
    ) -> None:
        self._log_dir = log_dir
        self._session_id = session_id
        self._path = log_dir / f"{session_id}.jsonl"
        self._buffer: list[GameLogEntry] = []
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None

    def log(self, entry: GameLogEntry) -> None:
        self._buffer.append(entry)
        try:
            loop = asyncio.get_running_loop()
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = loop.create_task(self._flush_loop())
        except RuntimeError:
            pass

    async def _flush_loop(self) -> None:
        await asyncio.sleep(self._flush_interval)
        self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and self._path.stat().st_size > self.MAX_FILE_SIZE:
            rotated = self._path.with_suffix(f".{int(time.time())}.jsonl")
            self._path.rename(rotated)
        entries = self._buffer.copy()
        self._buffer.clear()
        lines = [
            json.dumps(asdict(e), ensure_ascii=False) + "\n"
            for e in entries
        ]
        with open(self._path, "a", encoding="utf-8") as f:
            f.writelines(lines)

    def read_recent(self, n: int = 50) -> list[GameLogEntry]:
        result = list(self._buffer[-n:])
        remaining = n - len(result)
        if remaining <= 0:
            return result[-n:]
        if not self._path.exists():
            return result
        chunk_size = 8192
        with open(self._path, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            tail_lines: list[str] = []
            while pos > 0 and len(tail_lines) < remaining + 1:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size).decode("utf-8")
                tail_lines = chunk.splitlines() + tail_lines
        disk_entries: list[GameLogEntry] = []
        for line in tail_lines:
            line = line.strip()
            if line:
                try:
                    disk_entries.append(GameLogEntry(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue
        disk_recent = disk_entries[-remaining:]
        return disk_recent + result

    def close(self) -> None:
        self.flush()
