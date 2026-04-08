from __future__ import annotations

import pytest
from tavern.world.models import Character, CharacterRole, Exit, Item, Location, UseEffect
from tavern.world.state import WorldState


@pytest.fixture()
def use_state() -> WorldState:
    """Shared state fixture for USE-related engine tests."""
    exits = {"down": Exit(target="cellar", locked=True, description="铁门")}
    return WorldState(
        turn=1,
        player_id="player",
        locations={
            "bar_area": Location(id="bar_area", name="吧台区", description=".", exits=exits),
            "cellar": Location(id="cellar", name="地下室", description="."),
        },
        characters={
            "player": Character(
                id="player",
                name="玩家",
                role=CharacterRole.PLAYER,
                location_id="bar_area",
                inventory=("cellar_key", "rusty_box", "inert_item"),
            )
        },
        items={
            "cellar_key": Item(
                id="cellar_key",
                name="地下室钥匙",
                description="一把钥匙",
                usable_with=("cellar_door",),
                use_effects=(
                    UseEffect(type="unlock", location="bar_area", exit_direction="down"),
                    UseEffect(type="consume"),
                ),
            ),
            "rusty_box": Item(
                id="rusty_box",
                name="铁盒",
                description="生锈的盒子",
                use_effects=(
                    UseEffect(type="spawn_item", item_id="spare_key", spawn_to_inventory=True),
                ),
            ),
            "spare_key": Item(id="spare_key", name="备用钥匙", description="备用"),
            "inert_item": Item(id="inert_item", name="无用物品", description="什么都不能做"),
        },
    )
