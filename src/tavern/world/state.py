from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Awaitable, Callable
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, model_validator

from tavern.world.models import ActionResult, Character, Event, Item, Location


class StateDiff(BaseModel):
    updated_characters: dict[str, dict] = {}
    updated_locations: dict[str, dict] = {}
    added_items: dict[str, Item] = {}
    removed_items: tuple[str, ...] = ()
    relationship_changes: tuple[dict, ...] = ()
    quest_updates: dict[str, dict] = {}
    new_events: tuple[Event, ...] = ()
    story_active_since_updates: dict[str, int] = {}
    character_stat_deltas: dict[str, dict[str, int]] = {}
    new_endings: tuple[str, ...] = ()
    turn_increment: int = 1


class WorldState(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    turn: int = 0
    player_id: str = "player"
    locations: dict[str, Location] = {}
    characters: dict[str, Character] = {}
    items: dict[str, Item] = {}
    relationships_snapshot: dict = {}
    quests: dict[str, dict] = {}
    story_active_since: dict[str, int] = {}
    timeline: tuple[Event, ...] = ()
    endings_reached: tuple[str, ...] = ()
    last_action: ActionResult | None = None

    @model_validator(mode="wrap")
    @classmethod
    def freeze_mutable_fields(cls, values: Any, handler: Any) -> WorldState:
        instance = handler(values)
        frozen_fields = {
            "locations": instance.locations,
            "characters": instance.characters,
            "items": instance.items,
            "relationships_snapshot": instance.relationships_snapshot,
            "quests": instance.quests,
            "story_active_since": instance.story_active_since,
        }
        for field_name, field_val in frozen_fields.items():
            if isinstance(field_val, dict) and not isinstance(field_val, MappingProxyType):
                object.__setattr__(
                    instance, field_name, MappingProxyType(field_val)
                )
        return instance

    def apply(
        self, diff: StateDiff, action: ActionResult | None = None
    ) -> WorldState:
        new_characters = dict(self.characters)
        for char_id, updates in diff.updated_characters.items():
            if char_id in new_characters:
                new_characters[char_id] = new_characters[char_id].model_copy(
                    update=updates
                )

        for char_id, deltas in diff.character_stat_deltas.items():
            if char_id not in new_characters:
                continue
            char = new_characters[char_id]
            new_stats = dict(char.stats)
            for stat_name, delta_val in deltas.items():
                new_stats[stat_name] = new_stats.get(stat_name, 0) + delta_val
            new_characters[char_id] = char.model_copy(update={"stats": new_stats})

        new_locations = dict(self.locations)
        for loc_id, updates in diff.updated_locations.items():
            if loc_id in new_locations:
                new_locations[loc_id] = new_locations[loc_id].model_copy(
                    update=updates
                )

        new_items = dict(self.items)
        new_items.update(diff.added_items)
        for item_id in diff.removed_items:
            new_items.pop(item_id, None)

        new_timeline = self.timeline + diff.new_events

        new_quests = dict(self.quests)
        for quest_id, updates in diff.quest_updates.items():
            existing = new_quests.get(quest_id, {})
            new_quests[quest_id] = {**existing, **updates}

        new_story_active_since = {
            **dict(self.story_active_since),
            **diff.story_active_since_updates,
        }

        new_endings_reached = self.endings_reached + diff.new_endings

        return WorldState(
            turn=self.turn + diff.turn_increment,
            player_id=self.player_id,
            locations=new_locations,
            characters=new_characters,
            items=new_items,
            relationships_snapshot=self.relationships_snapshot,
            quests=new_quests,
            story_active_since=new_story_active_since,
            timeline=new_timeline,
            endings_reached=new_endings_reached,
            last_action=action,
        )


Listener = Callable[[], None]
OnChange = Callable[["WorldState", "WorldState"], Awaitable[None]]


class ReactiveStateManager:
    def __init__(
        self,
        initial_state: WorldState,
        max_history: int = 50,
        on_change: OnChange | None = None,
    ):
        self._state = initial_state
        self._version = 0
        self._history: deque[tuple[WorldState, int]] = deque(maxlen=max_history)
        self._future: list[tuple[WorldState, int]] = []
        self._listeners: list[Listener] = []
        self._on_change = on_change

    @property
    def current(self) -> WorldState:
        return self._state

    @property
    def state(self) -> WorldState:
        return self._state

    @property
    def version(self) -> int:
        return self._version

    def _notify(self, old: WorldState) -> None:
        if self._on_change:
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._on_change(old, self._state))
            except RuntimeError:
                pass
        for listener in list(self._listeners):
            listener()

    def commit(self, diff: StateDiff, action: ActionResult | None = None) -> WorldState:
        old = self._state
        self._history.append((old, self._version))
        self._future.clear()
        self._state = old.apply(diff, action=action)
        self._version += 1
        self._notify(old)
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def undo(self) -> WorldState | None:
        if not self._history:
            return None
        self._future.append((self._state, self._version))
        old = self._state
        self._state, self._version = self._history.pop()
        self._notify(old)
        return self._state

    def redo(self) -> WorldState | None:
        if not self._future:
            return None
        self._history.append((self._state, self._version))
        old = self._state
        self._state, self._version = self._future.pop()
        self._notify(old)
        return self._state

    def replace(self, new_state: WorldState) -> None:
        old = self._state
        self._state = new_state
        self._history.clear()
        self._future.clear()
        self._version += 1
        self._notify(old)


StateManager = ReactiveStateManager
