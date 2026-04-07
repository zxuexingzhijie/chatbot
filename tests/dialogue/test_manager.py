import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary, Message
from tavern.dialogue.manager import DialogueManager
from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.generate_dialogue = AsyncMock(
        return_value=DialogueResponse(
            text="欢迎，冒险者！",
            trust_delta=1,
            mood="平静",
            wants_to_end=False,
        )
    )
    service.generate_summary = AsyncMock(
        return_value={"summary": "进行了友好交谈。", "key_info": ["旅行者来自北方"]}
    )
    return service


@pytest.fixture
def sample_state():
    return WorldState(
        turn=5,
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
                traits=("友善", "健谈"),
                stats={"trust": 10},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


@pytest.fixture
def state_with_npc_elsewhere():
    return WorldState(
        turn=0,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            ),
            "bar_area": Location(
                id="bar_area",
                name="吧台区",
                description="吧台",
                npcs=("bartender_grim",),
            ),
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
                stats={"trust": 10},
                location_id="tavern_hall",
            ),
            "bartender_grim": Character(
                id="bartender_grim", name="格里姆",
                role=CharacterRole.NPC,
                traits=("沉默",),
                stats={"trust": 0},
                location_id="bar_area",
            ),
        },
        items={},
    )


class TestDialogueManagerStart:
    @pytest.mark.asyncio
    async def test_start_returns_context_and_response(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, response = await manager.start(sample_state, "traveler")
        assert ctx.npc_id == "traveler"
        assert ctx.npc_name == "旅行者"
        assert ctx.trust == 10 + 1  # initial + opening trust_delta
        assert ctx.tone == "neutral"
        assert isinstance(response, DialogueResponse)

    @pytest.mark.asyncio
    async def test_start_sets_is_active(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        assert not manager.is_active
        await manager.start(sample_state, "traveler")
        assert manager.is_active

    @pytest.mark.asyncio
    async def test_start_npc_not_in_location_raises(self, mock_llm_service, state_with_npc_elsewhere):
        manager = DialogueManager(llm_service=mock_llm_service)
        with pytest.raises(ValueError, match="不在"):
            await manager.start(state_with_npc_elsewhere, "bartender_grim")

    @pytest.mark.asyncio
    async def test_start_unknown_npc_raises(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        with pytest.raises(ValueError):
            await manager.start(sample_state, "nonexistent_npc")


class TestDialogueManagerRespond:
    @pytest.mark.asyncio
    async def test_respond_appends_messages(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        new_ctx, response = await manager.respond(ctx, "你好", sample_state)
        # ctx already has 1 message (opening), respond adds 2 (player + npc)
        assert len(new_ctx.messages) == 3
        assert isinstance(response, DialogueResponse)

    @pytest.mark.asyncio
    async def test_respond_updates_trust(self, mock_llm_service, sample_state):
        mock_llm_service.generate_dialogue = AsyncMock(
            return_value=DialogueResponse(text="好的", trust_delta=3, mood="开心", wants_to_end=False)
        )
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        new_ctx, _ = await manager.respond(ctx, "我来帮助你", sample_state)
        assert new_ctx.trust == ctx.trust + 3

    @pytest.mark.asyncio
    async def test_respond_enforces_20_turn_limit(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        messages = tuple(
            Message(role="npc", content=f"reply{i}", trust_delta=0, turn=i)
            for i in range(20)
        )
        ctx_full = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust,
            tone=ctx.tone,
            messages=messages,
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )
        _, response = await manager.respond(ctx_full, "还有吗", sample_state)
        assert response.wants_to_end is True


class TestDialogueManagerEnd:
    @pytest.mark.asyncio
    async def test_end_returns_summary(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, opening = await manager.start(sample_state, "traveler")
        summary = await manager.end(ctx)
        assert isinstance(summary, DialogueSummary)
        assert summary.npc_id == "traveler"
        assert summary.summary_text == "进行了友好交谈。"

    @pytest.mark.asyncio
    async def test_end_clears_active(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        assert manager.is_active
        await manager.end(ctx)
        assert not manager.is_active

    @pytest.mark.asyncio
    async def test_end_calculates_total_trust_delta(self, mock_llm_service, sample_state):
        manager = DialogueManager(llm_service=mock_llm_service)
        ctx, _ = await manager.start(sample_state, "traveler")
        ctx_with_messages = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=ctx.trust,
            tone=ctx.tone,
            messages=(
                Message(role="npc", content="嗨", trust_delta=2, turn=5),
                Message(role="player", content="你好", trust_delta=0, turn=5),
                Message(role="npc", content="很好", trust_delta=3, turn=5),
            ),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )
        summary = await manager.end(ctx_with_messages)
        assert summary.total_trust_delta == 5  # 2 + 0 + 3
