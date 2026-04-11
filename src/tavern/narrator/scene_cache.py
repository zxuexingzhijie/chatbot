# src/tavern/narrator/scene_cache.py
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.engine.seeded_rng import AmbienceDetails


@dataclass(frozen=True)
class SceneContext:
    location_description: str
    npcs_present: tuple[str, ...]
    items_visible: tuple[str, ...]
    exits_available: tuple[str, ...]
    atmosphere: str
    ambience: AmbienceDetails


class SceneContextCache:
    MAX_ENTRIES = 100

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple[str, int], SceneContext] = OrderedDict()

    def get(self, location_id: str, state_version: int) -> SceneContext | None:
        key = (location_id, state_version)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(
        self, location_id: str, state_version: int, context: SceneContext,
    ) -> None:
        key = (location_id, state_version)
        stale_keys = [
            k for k in self._cache
            if k[0] == location_id and k[1] < state_version
        ]
        for k in stale_keys:
            del self._cache[k]
        self._cache[key] = context
        self._cache.move_to_end(key)
        while len(self._cache) > self.MAX_ENTRIES:
            self._cache.popitem(last=False)

    def invalidate(self, location_id: str | None = None) -> None:
        if location_id is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k[0] == location_id]
            for k in keys_to_remove:
                del self._cache[k]
