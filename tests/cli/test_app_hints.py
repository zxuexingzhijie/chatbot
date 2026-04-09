import pytest
from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def _make_state(
    npcs=(),
    items=(),
    exits=None,
    all_characters=None,
    all_items=None,
):
    exit_map = exits or {}
    chars = all_characters or {}
    chars["player"] = Character(
        id="player",
        name="冒险者",
        role=CharacterRole.PLAYER,
        stats={"hp": 100, "gold": 10},
        location_id="tavern_hall",
    )
    items_dict = all_items or {}
    return WorldState(
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                exits=exit_map,
                items=items,
                npcs=npcs,
            ),
        },
        characters=chars,
        items=items_dict,
    )


class TestGenerateActionHints:
    def test_npc_present_generates_talk_hint(self):
        from tavern.cli.app import GameApp
        state = _make_state(
            npcs=("traveler",),
            all_characters={
                "traveler": Character(
                    id="traveler", name="旅行者",
                    role=CharacterRole.NPC, location_id="tavern_hall",
                ),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("旅行者" in h and "交谈" in h for h in hints)

    def test_item_present_generates_inspect_hint(self):
        from tavern.cli.app import GameApp
        state = _make_state(
            items=("old_notice",),
            all_items={
                "old_notice": Item(id="old_notice", name="旧告示", description="告示"),
            },
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("旧告示" in h and "查看" in h for h in hints)

    def test_exit_generates_move_hint(self):
        from tavern.cli.app import GameApp
        state = _make_state(
            exits={"north": Exit(target="bar_area", description="通往吧台")},
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("north" in h and "前往" in h for h in hints)

    def test_empty_scene_generates_fallback(self):
        from tavern.cli.app import GameApp
        state = _make_state()
        hints = GameApp._generate_action_hints_from_state(state)
        assert any("环顾四周" in h for h in hints)

    def test_max_three_hints(self):
        from tavern.cli.app import GameApp
        state = _make_state(
            npcs=("traveler", "bartender"),
            items=("old_notice",),
            exits={"north": Exit(target="bar_area"), "east": Exit(target="corridor")},
            all_characters={
                "traveler": Character(id="traveler", name="旅行者", role=CharacterRole.NPC, location_id="tavern_hall"),
                "bartender": Character(id="bartender", name="格里姆", role=CharacterRole.NPC, location_id="tavern_hall"),
            },
            all_items={"old_notice": Item(id="old_notice", name="旧告示", description="告示")},
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert len(hints) <= 3

    def test_diverse_hint_types(self):
        from tavern.cli.app import GameApp
        state = _make_state(
            npcs=("traveler",),
            items=("old_notice",),
            exits={"north": Exit(target="bar_area")},
            all_characters={
                "traveler": Character(id="traveler", name="旅行者", role=CharacterRole.NPC, location_id="tavern_hall"),
            },
            all_items={"old_notice": Item(id="old_notice", name="旧告示", description="告示")},
        )
        hints = GameApp._generate_action_hints_from_state(state)
        assert len(hints) == 3
        hint_text = " ".join(hints)
        assert "交谈" in hint_text
        assert "查看" in hint_text
        assert "前往" in hint_text
