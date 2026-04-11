import pytest
from tavern.engine.actions import ActionType
from tavern.world.models import (
    Character, CharacterRole, Exit, Item, Location, Event, ActionRequest, ActionResult,
)


class TestActionType:
    def test_move_action_exists(self):
        assert ActionType.MOVE == "move"

    def test_all_phase1_actions(self):
        expected = {"move", "look", "search", "talk", "persuade",
                    "take", "use", "custom"}
        actual = {a.value for a in ActionType}
        assert actual == expected


class TestCharacter:
    def test_create_player(self):
        player = Character(
            id="player", name="冒险者", role=CharacterRole.PLAYER,
            traits=("勇敢", "好奇"), stats={"hp": 100, "gold": 10},
            inventory=(), location_id="tavern_hall",
        )
        assert player.id == "player"
        assert player.role == CharacterRole.PLAYER
        assert player.stats["hp"] == 100

    def test_create_npc(self):
        npc = Character(
            id="bartender_grim", name="格里姆", role=CharacterRole.NPC,
            traits=("沉默寡言", "警觉"), stats={"trust": 0},
            inventory=("cellar_key",), location_id="bar_area",
        )
        assert npc.role == CharacterRole.NPC
        assert "cellar_key" in npc.inventory

    def test_character_is_frozen(self):
        player = Character(
            id="player", name="冒险者", role=CharacterRole.PLAYER,
            traits=(), stats={}, inventory=(), location_id="tavern_hall",
        )
        with pytest.raises(Exception):
            player.name = "新名字"


class TestLocation:
    def test_create_location_with_exits(self):
        loc = Location(
            id="tavern_hall", name="酒馆大厅",
            description="一间温暖的酒馆大厅，壁炉中火焰跳动。",
            exits={
                "north": Exit(target="bar_area", description="通往吧台区"),
                "east": Exit(target="corridor", description="通往客房走廊"),
            },
            items=("old_notice",), npcs=("traveler",),
        )
        assert loc.exits["north"].target == "bar_area"
        assert not loc.exits["north"].locked

    def test_locked_exit(self):
        exit_ = Exit(target="cellar", locked=True, key_item="cellar_key")
        assert exit_.locked
        assert exit_.key_item == "cellar_key"


class TestItem:
    def test_portable_item(self):
        item = Item(id="cellar_key", name="地下室钥匙",
                    description="一把生锈的铁钥匙", portable=True)
        assert item.portable

    def test_non_portable_item(self):
        item = Item(id="fireplace", name="壁炉",
                    description="熊熊燃烧的壁炉", portable=False)
        assert not item.portable

    def test_usable_with(self):
        item = Item(id="cellar_key", name="地下室钥匙",
                    description="钥匙", portable=True, usable_with=("cellar_door",))
        assert "cellar_door" in item.usable_with


class TestEvent:
    def test_create_event(self):
        event = Event(
            id="evt_001", turn=1, type="action",
            actor="player", description="玩家进入酒馆",
            consequences=("npc_notice_player",),
        )
        assert event.turn == 1
        assert event.actor == "player"


class TestActionRequest:
    def test_create_request(self):
        req = ActionRequest(
            action=ActionType.MOVE, target="bar_area",
            detail="走向吧台", confidence=0.95,
        )
        assert req.action == ActionType.MOVE
        assert req.confidence == 0.95

    def test_default_confidence(self):
        req = ActionRequest(action=ActionType.LOOK)
        assert req.confidence == 1.0


class TestActionResult:
    def test_success_result(self):
        result = ActionResult(
            success=True, action=ActionType.MOVE,
            message="你走向吧台区。", target="bar_area",
        )
        assert result.success
        assert result.action == ActionType.MOVE

    def test_failure_result(self):
        result = ActionResult(
            success=False, action=ActionType.MOVE,
            message="门被锁住了。", target="cellar",
        )
        assert not result.success
