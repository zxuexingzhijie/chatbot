import pytest
from tavern.dialogue.context import (
    DialogueContext,
    DialogueResponse,
    DialogueSummary,
    Message,
)


class TestMessage:
    def test_creation(self):
        msg = Message(role="player", content="你好", trust_delta=0, turn=1)
        assert msg.role == "player"
        assert msg.content == "你好"
        assert msg.trust_delta == 0
        assert msg.turn == 1

    def test_immutable(self):
        msg = Message(role="npc", content="...", trust_delta=2, turn=1)
        with pytest.raises(Exception):
            msg.content = "changed"  # type: ignore[misc]


class TestDialogueContext:
    def test_creation(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善",),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        assert ctx.npc_id == "traveler"
        assert ctx.tone == "neutral"
        assert ctx.messages == ()

    def test_immutable(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=(),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        with pytest.raises(Exception):
            ctx.trust = 99  # type: ignore[misc]


class TestDialogueResponse:
    def test_creation(self):
        resp = DialogueResponse(
            text="欢迎！", trust_delta=1, mood="friendly", wants_to_end=False
        )
        assert resp.text == "欢迎！"
        assert resp.trust_delta == 1
        assert not resp.wants_to_end

    def test_immutable(self):
        resp = DialogueResponse(text="...", trust_delta=0, mood="neutral", wants_to_end=False)
        with pytest.raises(Exception):
            resp.text = "changed"  # type: ignore[misc]


class TestDialogueSummary:
    def test_creation(self):
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="玩家与旅行者聊了旅行。",
            total_trust_delta=3,
            key_info=("旅行者来自北方",),
            turns_count=2,
        )
        assert summary.npc_id == "traveler"
        assert summary.total_trust_delta == 3
        assert len(summary.key_info) == 1

    def test_immutable(self):
        summary = DialogueSummary(
            npc_id="x", summary_text="x", total_trust_delta=0,
            key_info=(), turns_count=1,
        )
        with pytest.raises(Exception):
            summary.npc_id = "y"  # type: ignore[misc]
