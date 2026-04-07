from __future__ import annotations

from pathlib import Path

import yaml

from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def load_scenario(scenario_path: Path) -> WorldState:
    world_data = _load_yaml(scenario_path / "world.yaml")
    char_data = _load_yaml(scenario_path / "characters.yaml")

    locations = _build_locations(world_data["locations"])
    items = _build_items(world_data["items"])
    characters = _build_characters(char_data)

    return WorldState(
        turn=0,
        player_id="player",
        locations=locations,
        characters=characters,
        items=items,
    )


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_locations(raw: dict) -> dict[str, Location]:
    locations: dict[str, Location] = {}
    for loc_id, data in raw.items():
        exits: dict[str, Exit] = {}
        for direction, exit_data in data.get("exits", {}).items():
            exits[direction] = Exit(
                target=exit_data["target"],
                locked=exit_data.get("locked", False),
                key_item=exit_data.get("key_item"),
                description=exit_data.get("description", ""),
            )
        locations[loc_id] = Location(
            id=loc_id,
            name=data["name"],
            description=data["description"],
            exits=exits,
            items=tuple(data.get("items", [])),
            npcs=tuple(data.get("npcs", [])),
        )
    return locations


def _build_items(raw: dict) -> dict[str, Item]:
    items: dict[str, Item] = {}
    for item_id, data in raw.items():
        items[item_id] = Item(
            id=item_id,
            name=data["name"],
            description=data["description"],
            portable=data.get("portable", True),
            usable_with=tuple(data.get("usable_with", [])),
        )
    return items


def _build_characters(raw: dict) -> dict[str, Character]:
    characters: dict[str, Character] = {}

    player_data = raw["player"]
    characters["player"] = Character(
        id=player_data["id"],
        name=player_data["name"],
        role=CharacterRole.PLAYER,
        traits=tuple(player_data.get("traits", [])),
        stats=player_data.get("stats", {}),
        inventory=tuple(player_data.get("inventory", [])),
        location_id=player_data["location_id"],
    )

    for npc_id, data in raw.get("npcs", {}).items():
        characters[npc_id] = Character(
            id=npc_id,
            name=data["name"],
            role=CharacterRole.NPC,
            traits=tuple(data.get("traits", [])),
            stats=data.get("stats", {}),
            inventory=tuple(data.get("inventory", [])),
            location_id=data["location_id"],
        )

    return characters
