import pytest

from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionResult,
    Character,
    CharacterRole,
    Event,
    Exit,
    Item,
    Location,
)
from tavern.world.state import StateManager, WorldState


@pytest.fixture
def sample_locations() -> dict[str, Location]:
    return {
        "tavern_hall": Location(
            id="tavern_hall",
            name="酒馆大厅",
            description="温暖的酒馆大厅。",
            exits={"north": Exit(target="bar_area", description="通往吧台")},
            items=("old_notice",),
            npcs=("traveler",),
        ),
        "bar_area": Location(
            id="bar_area",
            name="吧台区",
            description="木质吧台前摆着几张高脚凳。",
            exits={
                "south": Exit(target="tavern_hall", description="回到大厅"),
                "down": Exit(
                    target="cellar",
                    locked=True,
                    key_item="cellar_key",
                    description="通往地下室（已锁）",
                ),
            },
            items=(),
            npcs=("bartender_grim",),
        ),
        "cellar": Location(
            id="cellar",
            name="地下室",
            description="阴暗潮湿的地下室，空气中弥漫着霉味。",
            exits={
                "up": Exit(target="bar_area", description="回到吧台"),
            },
            items=(),
            npcs=(),
        ),
    }


@pytest.fixture
def sample_items() -> dict[str, Item]:
    return {
        "old_notice": Item(
            id="old_notice",
            name="旧告示",
            description="一张泛黄的告示",
            portable=True,
        ),
        "cellar_key": Item(
            id="cellar_key",
            name="地下室钥匙",
            description="一把生锈的铁钥匙",
            portable=True,
        ),
    }


@pytest.fixture
def sample_characters() -> dict[str, Character]:
    return {
        "player": Character(
            id="player",
            name="冒险者",
            role=CharacterRole.PLAYER,
            traits=("勇敢",),
            stats={"hp": 100, "gold": 10},
            inventory=(),
            location_id="tavern_hall",
        ),
        "traveler": Character(
            id="traveler",
            name="旅行者",
            role=CharacterRole.NPC,
            traits=("友善", "健谈"),
            stats={"trust": 10},
            inventory=(),
            location_id="tavern_hall",
        ),
        "bartender_grim": Character(
            id="bartender_grim",
            name="格里姆",
            role=CharacterRole.NPC,
            traits=("沉默寡言", "警觉"),
            stats={"trust": 0},
            inventory=("cellar_key",),
            location_id="bar_area",
        ),
    }


@pytest.fixture
def sample_world_state(sample_locations, sample_items, sample_characters):
    return WorldState(
        turn=0,
        player_id="player",
        locations=sample_locations,
        characters=sample_characters,
        items=sample_items,
    )


@pytest.fixture
def sample_state_manager(sample_world_state):
    return StateManager(initial_state=sample_world_state)
