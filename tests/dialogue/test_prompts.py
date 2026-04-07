from tavern.dialogue.prompts import TONE_TEMPLATES, build_dialogue_prompt, resolve_tone
from tavern.dialogue.context import DialogueContext


class TestResolveTone:
    def test_hostile_threshold(self):
        assert resolve_tone(-20) == "hostile"
        assert resolve_tone(-100) == "hostile"

    def test_neutral_range(self):
        assert resolve_tone(-19) == "neutral"
        assert resolve_tone(0) == "neutral"
        assert resolve_tone(19) == "neutral"

    def test_friendly_threshold(self):
        assert resolve_tone(20) == "friendly"
        assert resolve_tone(100) == "friendly"


class TestToneTemplates:
    def test_all_tones_defined(self):
        assert "hostile" in TONE_TEMPLATES
        assert "neutral" in TONE_TEMPLATES
        assert "friendly" in TONE_TEMPLATES

    def test_templates_are_non_empty_strings(self):
        for tone, template in TONE_TEMPLATES.items():
            assert isinstance(template, str)
            assert len(template) > 10, f"Tone template for '{tone}' is too short"


class TestBuildDialoguePrompt:
    def test_prompt_contains_npc_name(self):
        ctx = DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善", "健谈"),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "酒馆大厅", history_summaries=())
        assert "旅行者" in prompt

    def test_prompt_contains_tone_instruction(self):
        ctx = DialogueContext(
            npc_id="bartender",
            npc_name="格里姆",
            npc_traits=("沉默",),
            trust=-30,
            tone="hostile",
            messages=(),
            location_id="bar_area",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "吧台区", history_summaries=())
        assert TONE_TEMPLATES["hostile"] in prompt

    def test_prompt_contains_json_format(self):
        ctx = DialogueContext(
            npc_id="npc1",
            npc_name="NPC",
            npc_traits=(),
            trust=0,
            tone="neutral",
            messages=(),
            location_id="loc1",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "某地", history_summaries=())
        assert "trust_delta" in prompt
        assert "wants_to_end" in prompt

    def test_prompt_includes_history_summary(self):
        ctx = DialogueContext(
            npc_id="npc1",
            npc_name="NPC",
            npc_traits=(),
            trust=5,
            tone="neutral",
            messages=(),
            location_id="loc1",
            turn_entered=0,
        )
        prompt = build_dialogue_prompt(
            ctx, "某地", history_summaries=("上次聊到了宝藏",)
        )
        assert "上次聊到了宝藏" in prompt
