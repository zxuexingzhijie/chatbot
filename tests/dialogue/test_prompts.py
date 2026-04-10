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

    def test_prompt_contains_location_name(self):
        ctx = DialogueContext(
            npc_id="npc1", npc_name="NPC", npc_traits=(), trust=0,
            tone="neutral", messages=(), location_id="loc1", turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "神秘地点", history_summaries=())
        assert "神秘地点" in prompt

    def test_prompt_contains_trust_value(self):
        ctx = DialogueContext(
            npc_id="npc1", npc_name="NPC", npc_traits=(), trust=15,
            tone="neutral", messages=(), location_id="loc1", turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "某地", history_summaries=())
        assert "15" in prompt

    def test_persuade_context_in_prompt(self):
        ctx = DialogueContext(
            npc_id="npc1", npc_name="NPC", npc_traits=(), trust=0,
            tone="neutral", messages=(), location_id="loc1", turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "某地", history_summaries=(), is_persuade=True)
        assert "说服" in prompt

    def test_no_persuade_context_by_default(self):
        ctx = DialogueContext(
            npc_id="npc1", npc_name="NPC", npc_traits=(), trust=0,
            tone="neutral", messages=(), location_id="loc1", turn_entered=0,
        )
        prompt = build_dialogue_prompt(ctx, "某地", history_summaries=())
        assert "玩家正在尝试说服" not in prompt


class TestBuildSummaryPrompt:
    def test_contains_npc_name(self):
        from tavern.dialogue.prompts import build_summary_prompt
        prompt = build_summary_prompt("旅行者", [{"role": "user", "content": "你好"}])
        assert "旅行者" in prompt

    def test_contains_json_instruction(self):
        from tavern.dialogue.prompts import build_summary_prompt
        prompt = build_summary_prompt("NPC", [])
        assert "summary" in prompt
        assert "key_info" in prompt

    def test_includes_dialogue_content(self):
        from tavern.dialogue.prompts import build_summary_prompt
        messages = [
            {"role": "user", "content": "北方有什么？"},
            {"role": "assistant", "content": "北方有宝藏。"},
        ]
        prompt = build_summary_prompt("旅行者", messages)
        assert "北方有什么" in prompt
        assert "北方有宝藏" in prompt


class TestBuildDialoguePromptWithSkills:
    def _make_ctx(self):
        return DialogueContext(
            npc_id="bartender",
            npc_name="格里姆",
            npc_traits=("沉默",),
            trust=0,
            tone="neutral",
            messages=(),
            location_id="bar_area",
            turn_entered=0,
        )

    def test_active_skills_text_empty_string_no_change(self):
        ctx = self._make_ctx()
        prompt = build_dialogue_prompt(ctx, "吧台区", history_summaries=(), active_skills_text="")
        assert "【NPC知识与行为】" not in prompt

    def test_active_skills_text_appended_to_prompt(self):
        ctx = self._make_ctx()
        skills_text = "格里姆知道地下室藏有秘密\ntone: 神秘"
        prompt = build_dialogue_prompt(
            ctx, "吧台区", history_summaries=(), active_skills_text=skills_text
        )
        assert "格里姆知道地下室藏有秘密" in prompt
        assert "【NPC知识与行为】" in prompt


class TestBuildDialoguePromptWithSceneContext:
    def _make_ctx(self):
        return DialogueContext(
            npc_id="traveler",
            npc_name="旅行者",
            npc_traits=("友善",),
            trust=10,
            tone="neutral",
            messages=(),
            location_id="tavern_hall",
            turn_entered=0,
        )

    def test_scene_context_empty_not_in_prompt(self):
        ctx = self._make_ctx()
        prompt = build_dialogue_prompt(ctx, "酒馆大厅", history_summaries=(), scene_context="")
        assert "【当前情境】" not in prompt

    def test_scene_context_included_in_prompt(self):
        ctx = self._make_ctx()
        prompt = build_dialogue_prompt(
            ctx, "酒馆大厅", history_summaries=(),
            scene_context="玩家刚刚搜索了吧台，发现了一张藏宝图。",
        )
        assert "【当前情境】" in prompt
        assert "藏宝图" in prompt
