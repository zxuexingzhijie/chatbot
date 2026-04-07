from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.dialogue.context import DialogueResponse, DialogueSummary
from tavern.dialogue.manager import DialogueManager
from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
from tavern.world.models import ActionRequest, ActionResult, Character, CharacterRole, Location
from tavern.world.state import StateManager, StateDiff, WorldState
from pathlib import Path

SCENARIO_PATH = Path(__file__).parent.parent / "data" / "scenarios" / "tavern"


class TestFullPipeline:
    @pytest.fixture
    def game_state(self):
        initial = load_scenario(SCENARIO_PATH)
        return StateManager(initial_state=initial)

    @pytest.fixture
    def rules(self):
        return RulesEngine()

    def test_look_at_starting_location(self, game_state, rules):
        request = ActionRequest(action=ActionType.LOOK)
        result, diff = rules.validate(request, game_state.current)
        assert result.success
        assert "酒馆大厅" in result.message

    def test_move_north_to_bar(self, game_state, rules):
        request = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(request, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

    def test_move_and_undo(self, game_state, rules):
        # Move north
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(req, game_state.current)
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

        # Undo
        game_state.undo()
        assert game_state.current.characters["player"].location_id == "tavern_hall"

    def test_take_item_then_undo(self, game_state, rules):
        # Take old_notice
        req = ActionRequest(action=ActionType.TAKE, target="old_notice")
        result, diff = rules.validate(req, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert "old_notice" in game_state.current.characters["player"].inventory

        # Undo
        game_state.undo()
        assert "old_notice" not in game_state.current.characters["player"].inventory
        assert "old_notice" in game_state.current.locations["tavern_hall"].items

    def test_cannot_enter_locked_cellar(self, game_state, rules):
        # Move to bar
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules.validate(req, game_state.current)
        game_state.commit(diff, result)

        # Try cellar
        req = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules.validate(req, game_state.current)
        assert not result.success
        assert diff is None

    def test_full_scenario_move_look_take(self, game_state, rules):
        # 1. Look around
        result, _ = rules.validate(
            ActionRequest(action=ActionType.LOOK), game_state.current
        )
        assert result.success
        assert "旅行者" in result.message or "告示" in result.message

        # 2. Take the notice
        result, diff = rules.validate(
            ActionRequest(action=ActionType.TAKE, target="old_notice"),
            game_state.current,
        )
        assert result.success
        game_state.commit(diff, result)

        # 3. Look at it in inventory
        result, _ = rules.validate(
            ActionRequest(action=ActionType.LOOK, target="old_notice"),
            game_state.current,
        )
        assert result.success
        assert "地下室" in result.message

        # 4. Move to bar
        result, diff = rules.validate(
            ActionRequest(action=ActionType.MOVE, target="north"),
            game_state.current,
        )
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"

    @pytest.mark.asyncio
    async def test_intent_parser_pipeline(self, game_state, rules):
        mock_llm = AsyncMock()
        mock_llm.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE, target="north",
                detail="去吧台", confidence=0.95,
            )
        )
        parser = IntentParser(llm_service=mock_llm)

        location = game_state.current.locations["tavern_hall"]
        request = await parser.parse(
            "我要去吧台看看",
            location_id="tavern_hall",
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
        )

        result, diff = rules.validate(request, game_state.current)
        assert result.success
        game_state.commit(diff, result)
        assert game_state.current.characters["player"].location_id == "bar_area"


@pytest.fixture
def dialogue_world_state():
    return WorldState(
        turn=1,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            )
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="tavern_hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者",
                role=CharacterRole.NPC,
                traits=("友善",),
                stats={"trust": 5},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


class TestDialogueE2E:
    @pytest.mark.asyncio
    async def test_full_dialogue_lifecycle(self, dialogue_world_state):
        mock_service = MagicMock()
        mock_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(
                text="你好，旅行者！",
                trust_delta=2,
                mood="开心",
                wants_to_end=False,
            )
        )
        mock_service.generate_summary = AsyncMock(
            return_value={
                "summary": "玩家与旅行者进行了友好交谈。",
                "key_info": ["旅行者来自北方"],
            }
        )

        manager = DialogueManager(llm_service=mock_service)
        state = dialogue_world_state

        ctx, opening = await manager.start(state, "traveler")
        assert opening.text == "你好，旅行者！"
        assert manager.is_active

        ctx, resp1 = await manager.respond(ctx, "你从哪里来？", state)
        assert resp1.trust_delta == 2

        ctx, resp2 = await manager.respond(ctx, "有什么有趣的故事吗？", state)
        assert resp2.trust_delta == 2

        summary = await manager.end(ctx)
        assert not manager.is_active
        assert summary.npc_id == "traveler"
        assert summary.summary_text == "玩家与旅行者进行了友好交谈。"
        # total_trust_delta = opening(2) + resp1(2) + resp2(2) = 6
        assert summary.total_trust_delta == 6

    @pytest.mark.asyncio
    async def test_dialogue_state_persistence(self, dialogue_world_state):
        mock_service = MagicMock()
        mock_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(text="!", trust_delta=5, mood="x", wants_to_end=False)
        )
        mock_service.generate_summary = AsyncMock(
            return_value={"summary": "对话完成", "key_info": []}
        )

        manager = DialogueManager(llm_service=mock_service)
        state = dialogue_world_state

        ctx, _ = await manager.start(state, "traveler")
        summary = await manager.end(ctx)

        old_trust = state.characters["traveler"].stats["trust"]  # 5
        npc = state.characters["traveler"]
        new_stats = {**dict(npc.stats), "trust": old_trust + summary.total_trust_delta}
        diff = StateDiff(
            updated_characters={"traveler": {"stats": new_stats}},
            turn_increment=0,
        )
        state_manager = StateManager(initial_state=state)
        state_manager.commit(
            diff,
            ActionResult(success=True, action=ActionType.TALK, message="对话结束", target="traveler"),
        )
        new_trust = state_manager.current.characters["traveler"].stats["trust"]
        assert new_trust == old_trust + summary.total_trust_delta
