from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from tavern.engine.actions import ActionType


def _freeze_dicts(obj: Any) -> Any:
    """Recursively convert dicts to MappingProxyType for true immutability."""
    if isinstance(obj, dict) and not isinstance(obj, MappingProxyType):
        return MappingProxyType({k: _freeze_dicts(v) for k, v in obj.items()})
    return obj


class CharacterRole(str, Enum):
    NPC = "npc"
    PLAYER = "player"


class Character(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    name: str
    role: CharacterRole
    traits: tuple[str, ...] = ()
    stats: dict[str, int] = {}
    inventory: tuple[str, ...] = ()
    location_id: str

    @model_validator(mode="wrap")
    @classmethod
    def freeze_mutable_fields(cls, values: Any, handler: Any) -> Character:
        instance = handler(values)
        if isinstance(instance.stats, dict) and not isinstance(instance.stats, MappingProxyType):
            object.__setattr__(instance, "stats", MappingProxyType(instance.stats))
        return instance


class Exit(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    locked: bool = False
    key_item: str | None = None
    description: str = ""


class Location(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    name: str
    description: str
    exits: dict[str, Exit] = {}
    items: tuple[str, ...] = ()
    npcs: tuple[str, ...] = ()

    @model_validator(mode="wrap")
    @classmethod
    def freeze_mutable_fields(cls, values: Any, handler: Any) -> Location:
        instance = handler(values)
        if isinstance(instance.exits, dict) and not isinstance(instance.exits, MappingProxyType):
            object.__setattr__(instance, "exits", MappingProxyType(instance.exits))
        return instance


class EventSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    description: str
    actor: str | None = None


class UseEffect(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    location: str | None = None
    exit_direction: str | None = None
    item_id: str | None = None
    spawn_to_inventory: bool = True
    event: EventSpec | None = None


class Item(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    portable: bool = True
    usable_with: tuple[str, ...] = ()
    use_effects: tuple[UseEffect, ...] = ()


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    turn: int
    type: str
    actor: str
    description: str
    consequences: tuple[str, ...] = ()


class ActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: ActionType
    target: str | None = None
    detail: str | None = None
    confidence: float = 1.0


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    action: ActionType
    message: str
    target: str | None = None
    detail: str | None = None
