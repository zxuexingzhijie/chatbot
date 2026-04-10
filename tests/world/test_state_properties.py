from tavern.world.models import Character, CharacterRole, Exit, Item, Location
from tavern.world.state import WorldState


def _make_state() -> WorldState:
    return WorldState(
        turn=3,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="一个温暖的大厅",
                exits={"north": Exit(target="cellar", description="通往地窖")},
                items=("old_notice",),
                npcs=("bartender",),
            ),
            "cellar": Location(
                id="cellar", name="地窖", description="阴暗的地窖",
            ),
        },
        characters={
            "player": Character(
                id="player", name="旅人", role=CharacterRole.PLAYER,
                location_id="tavern_hall", inventory=("rusty_key",),
            ),
            "bartender": Character(
                id="bartender", name="格里姆", role=CharacterRole.NPC,
                location_id="tavern_hall",
            ),
        },
        items={
            "old_notice": Item(id="old_notice", name="旧告示", description="一张旧告示"),
            "rusty_key": Item(id="rusty_key", name="生锈的钥匙", description="一把钥匙"),
        },
    )


class TestWorldStateProperties:
    def test_player_location_returns_player_location_id(self):
        state = _make_state()
        assert state.player_location == "tavern_hall"

    def test_current_location_returns_location_object(self):
        state = _make_state()
        loc = state.current_location
        assert loc.id == "tavern_hall"
        assert loc.name == "酒馆大厅"

    def test_npcs_at_returns_npcs_at_location(self):
        state = _make_state()
        npcs = state.npcs_at("tavern_hall")
        assert len(npcs) == 1
        assert npcs[0].id == "bartender"

    def test_npcs_at_excludes_player(self):
        state = _make_state()
        npcs = state.npcs_at("tavern_hall")
        ids = [n.id for n in npcs]
        assert "player" not in ids

    def test_npcs_in_location_is_shortcut(self):
        state = _make_state()
        assert state.npcs_in_location == state.npcs_at("tavern_hall")

    def test_npcs_at_empty_location(self):
        state = _make_state()
        assert state.npcs_at("cellar") == []

    def test_player_inventory_returns_item_objects(self):
        state = _make_state()
        inv = state.player_inventory
        assert len(inv) == 1
        assert inv[0].id == "rusty_key"

    def test_player_inventory_empty(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        assert state.player_inventory == []
