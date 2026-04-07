import pytest
from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt

class TestNarrativeContext:
    def test_creation(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走进了酒馆大厅。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        assert ctx.action_type == "move"
        assert ctx.target is None

    def test_immutable(self):
        ctx = NarrativeContext(
            action_type="look",
            action_message="你仔细观察四周。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.action_type = "move"  # type: ignore

    def test_with_target(self):
        ctx = NarrativeContext(
            action_type="take",
            action_message="你拾起了旧告示。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target="旧告示",
        )
        assert ctx.target == "旧告示"


class TestBuildNarrativePrompt:
    def test_returns_two_messages(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走进了吧台区。",
            location_name="吧台区",
            location_desc="木质吧台前摆着几张高脚凳。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_contains_location_name(self):
        ctx = NarrativeContext(
            action_type="look",
            action_message="你环顾四周。",
            location_name="地下室",
            location_desc="阴暗潮湿的地下室。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert "地下室" in messages[0]["content"] or "地下室" in messages[1]["content"]

    def test_user_message_contains_action_message(self):
        ctx = NarrativeContext(
            action_type="take",
            action_message="你拾起了地下室钥匙。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target="地下室钥匙",
        )
        messages = build_narrative_prompt(ctx)
        assert "地下室钥匙" in messages[1]["content"]

    def test_move_uses_different_system_than_look(self):
        ctx_move = NarrativeContext(
            action_type="move",
            action_message="你走进了吧台区。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target=None,
        )
        ctx_look = NarrativeContext(
            action_type="look",
            action_message="你环顾四周。",
            location_name="吧台区",
            location_desc="木质吧台。",
            player_name="冒险者",
            target=None,
        )
        msg_move = build_narrative_prompt(ctx_move)
        msg_look = build_narrative_prompt(ctx_look)
        assert msg_move[0]["content"] != msg_look[0]["content"]

    def test_unknown_action_type_uses_default_template(self):
        ctx = NarrativeContext(
            action_type="custom",
            action_message="你做了些奇怪的事情。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="冒险者",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert messages[0]["role"] == "system"

    def test_system_contains_player_name(self):
        ctx = NarrativeContext(
            action_type="move",
            action_message="你走向北方。",
            location_name="酒馆大厅",
            location_desc="温暖的酒馆大厅。",
            player_name="勇敢的艾拉",
            target=None,
        )
        messages = build_narrative_prompt(ctx)
        assert "勇敢的艾拉" in messages[0]["content"]
