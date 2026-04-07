from __future__ import annotations

from collections import deque
from types import MappingProxyType
from typing import Any

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
    timeline: tuple[Event, ...] = ()
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

        return WorldState(
            turn=self.turn + diff.turn_increment,
            player_id=self.player_id,
            locations=new_locations,
            characters=new_characters,
            items=new_items,
            relationships_snapshot=self.relationships_snapshot,
            quests=new_quests,
            timeline=new_timeline,
            last_action=action,
        )


class StateManager:
    def __init__(self, initial_state: WorldState, max_history: int = 50):
        self._current = initial_state
        self._history: deque[WorldState] = deque(maxlen=max_history)
        self._redo: deque[WorldState] = deque(maxlen=max_history)

    @property
    def current(self) -> WorldState:
        return self._current

    def commit(self, diff: StateDiff, action: ActionResult) -> WorldState:
        self._history.append(self._current)
        self._current = self._current.apply(diff, action=action)
        self._redo.clear()
        return self._current

    def undo(self) -> WorldState:
        previous = self._history.pop()
        self._redo.append(self._current)
        self._current = previous
        return self._current

    def redo(self) -> WorldState:
        next_state = self._redo.pop()
        self._history.append(self._current)
        self._current = next_state
        return self._current
