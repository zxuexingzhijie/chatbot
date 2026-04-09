"""Tests for the 7-bug fix batch — relationship direction, dialogue events,
SEARCH events, story stat→relationship sync, Anthropic base_url, default config,
and story_active_since apply_diff."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from tavern.dialogue.context import DialogueSummary
from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.llm.adapter import LLMConfig
from tavern.world.memory import RelationshipGraph
from tavern.world.models import (
    ActionRequest,
    ActionResult,
    Character,
    CharacterRole,
    Location,
)
from tavern.world.state import StateManager, StateDiff, WorldState
from tavern.cli.app import GameApp


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_app(state: WorldState) -> GameApp:
    app = GameApp.__new__(GameApp)
    app._state_manager = StateManager(initial_state=state)
    app._renderer = MagicMock()
    app._memory = MagicMock()
    app._save_manager = MagicMock()
    return app


def _base_state() -> WorldState:
    return WorldState(
        turn=5,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall", name="酒馆大厅", description="大厅",
                npcs=("traveler",),
            ),
            "backyard": Location(
                id="backyard", name="后院", description="后院",
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
        },
        items={},
    )


# ── Bug #1: relationship direction ──────────────────────────────────────────

class TestBug1RelationshipDirection:
    def test_dialogue_end_relationship_direction_player_to_npc(self):
        state = _base_state()
        app = _make_app(state)
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="友好交谈",
            total_trust_delta=5,
            key_info=(),
            turns_count=2,
        )
        app._apply_dialogue_end(summary)

        calls = app._memory.apply_diff.call_args_list
        trust_call = calls[0]
        diff = trust_call[0][0]
        assert len(diff.relationship_changes) == 1
        rc = diff.relationship_changes[0]
        assert rc["src"] == "player"
        assert rc["tgt"] == "traveler"
        assert rc["delta"] == 5


# ── Bug #2: talked_to events ────────────────────────────────────────────────

class TestBug2TalkedToEvents:
    def test_dialogue_end_produces_talked_to_event(self):
        state = _base_state()
        app = _make_app(state)
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="友好交谈",
            total_trust_delta=0,
            key_info=(),
            turns_count=1,
        )
        app._apply_dialogue_end(summary)

        new_state = app._state_manager.current
        talked_events = [e for e in new_state.timeline if e.id == "talked_to_traveler"]
        assert len(talked_events) == 1
        assert talked_events[0].type == "dialogue_trigger"


# ── Bug #3: SEARCH produces events ──────────────────────────────────────────

class TestBug3SearchEvents:
    def test_search_produces_searched_event(self):
        state = WorldState(
            turn=3,
            player_id="player",
            locations={
                "backyard": Location(
                    id="backyard", name="后院", description="后院",
                ),
            },
            characters={
                "player": Character(
                    id="player", name="冒险者",
                    role=CharacterRole.PLAYER,
                    location_id="backyard",
                ),
            },
            items={},
        )
        engine = RulesEngine()
        request = ActionRequest(action=ActionType.SEARCH)
        result, diff = engine.validate(request, state)
        assert result.success
        assert diff is not None
        assert len(diff.new_events) == 1
        assert diff.new_events[0].id == "searched_backyard"
        assert diff.new_events[0].type == "search"

    def test_search_with_target_no_event(self):
        state = WorldState(
            turn=3,
            player_id="player",
            locations={
                "backyard": Location(
                    id="backyard", name="后院", description="后院",
                    npcs=("traveler",),
                ),
            },
            characters={
                "player": Character(
                    id="player", name="冒险者",
                    role=CharacterRole.PLAYER,
                    location_id="backyard",
                ),
                "traveler": Character(
                    id="traveler", name="旅行者",
                    role=CharacterRole.NPC,
                    location_id="backyard",
                ),
            },
            items={},
        )
        engine = RulesEngine()
        request = ActionRequest(action=ActionType.SEARCH, target="traveler")
        result, diff = engine.validate(request, state)
        assert result.success
        assert diff is None


# ── Bug #4: story character_stat_deltas → relationship_changes ──────────────

class TestBug4StoryStatDeltasRelationship:
    def test_build_result_trust_delta_generates_relationship_changes(self):
        from tavern.engine.story import StoryEffects, StoryNode, StoryEngine

        effects = StoryEffects(
            quest_updates={},
            new_events=(),
            character_stat_deltas={"traveler": {"trust": 20}},
        )
        node = StoryNode(
            id="n1", act="act1", requires=(), repeatable=False,
            trigger_mode="passive", conditions=(), effects=effects,
            narrator_hint=None, fail_forward=None,
        )
        engine = StoryEngine({"n1": node})
        state = MagicMock()
        state.turn = 1
        state.player_id = "player"
        state.characters = {"player": MagicMock(location_id="tavern", inventory=())}
        state.quests = {}
        state.story_active_since = {}

        results = engine.check(state, "passive", MagicMock(), MagicMock())
        diff = results[0].diff
        assert len(diff.relationship_changes) == 1
        assert diff.relationship_changes[0]["src"] == "player"
        assert diff.relationship_changes[0]["tgt"] == "traveler"
        assert diff.relationship_changes[0]["delta"] == 20

    def test_build_result_no_trust_no_relationship_changes(self):
        from tavern.engine.story import StoryEffects, StoryNode, StoryEngine

        effects = StoryEffects(
            quest_updates={},
            new_events=(),
            character_stat_deltas={"traveler": {"hp": 10}},
        )
        node = StoryNode(
            id="n1", act="act1", requires=(), repeatable=False,
            trigger_mode="passive", conditions=(), effects=effects,
            narrator_hint=None, fail_forward=None,
        )
        engine = StoryEngine({"n1": node})
        state = MagicMock()
        state.turn = 1
        state.player_id = "player"
        state.characters = {"player": MagicMock(location_id="tavern", inventory=())}
        state.quests = {}
        state.story_active_since = {}

        results = engine.check(state, "passive", MagicMock(), MagicMock())
        diff = results[0].diff
        assert len(diff.relationship_changes) == 0


# ── Bug #5: Anthropic base_url strip /v1 ────────────────────────────────────

class TestBug5AnthropicBaseUrl:
    def test_strips_trailing_v1(self):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.anthropic_llm import AnthropicAdapter
            config = LLMConfig(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                api_key="test",
                base_url="https://example.com/v1",
            )
            AnthropicAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["base_url"] == "https://example.com"

    def test_strips_trailing_v1_with_slash(self):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.anthropic_llm import AnthropicAdapter
            config = LLMConfig(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                api_key="test",
                base_url="https://example.com/v1/",
            )
            AnthropicAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["base_url"] == "https://example.com"

    def test_no_base_url_passes_none(self):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.anthropic_llm import AnthropicAdapter
            config = LLMConfig(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                api_key="test",
            )
            AnthropicAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["base_url"] is None

    def test_base_url_without_v1_unchanged(self):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.anthropic_llm import AnthropicAdapter
            config = LLMConfig(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                api_key="test",
                base_url="https://example.com/api",
            )
            AnthropicAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["base_url"] == "https://example.com/api"


# ── Bug #6: default_config.yaml + no LLM guard ─────────────────────────────

class TestBug6DefaultConfig:
    def test_missing_llm_config_raises_exit(self):
        with pytest.raises(SystemExit, match="tavern init"):
            with patch.object(GameApp, "_load_config", return_value={"game": {"scenario": "tavern"}}):
                GameApp(config_path="dummy")

    def test_default_config_yaml_has_no_llm_section(self):
        from tavern.data import get_bundled_scenarios_dir
        import yaml
        default_path = get_bundled_scenarios_dir().parent / "default_config.yaml"
        if not default_path.exists():
            pytest.skip("default_config.yaml not found")
        with open(default_path) as f:
            config = yaml.safe_load(f)
        assert "llm" not in config


# ── Bug #6 (key_info events) ────────────────────────────────────────────────

class TestBug6KeyInfoEvents:
    def test_key_info_with_letter_produces_about_letter_event(self):
        state = _base_state()
        app = _make_app(state)
        summary = DialogueSummary(
            npc_id="bartender_grim",
            summary_text="酒保谈了信件",
            total_trust_delta=0,
            key_info=("酒保提到了一封重要的letter",),
            turns_count=1,
        )
        state_with_bartender = state.model_copy(update={
            "characters": {
                **dict(state.characters),
                "bartender_grim": Character(
                    id="bartender_grim", name="格里姆",
                    role=CharacterRole.NPC,
                    stats={"trust": 0},
                    location_id="tavern_hall",
                ),
            },
        })
        app._state_manager = StateManager(initial_state=state_with_bartender)
        app._apply_dialogue_end(summary)

        new_state = app._state_manager.current
        letter_events = [
            e for e in new_state.timeline
            if e.id == "talked_to_bartender_grim_about_letter"
        ]
        assert len(letter_events) == 1
        assert letter_events[0].type == "dialogue_topic"

    def test_key_info_without_keyword_no_extra_events(self):
        state = _base_state()
        app = _make_app(state)
        summary = DialogueSummary(
            npc_id="traveler",
            summary_text="闲聊",
            total_trust_delta=0,
            key_info=("旅行者来自北方",),
            turns_count=1,
        )
        app._apply_dialogue_end(summary)

        new_state = app._state_manager.current
        topic_events = [e for e in new_state.timeline if e.type == "dialogue_topic"]
        assert len(topic_events) == 0


# ── API key strip (trailing whitespace) ─────────────────────────────────────

class TestApiKeyStrip:
    def test_llm_config_strips_api_key(self):
        config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-abc123 ")
        assert config.api_key == "sk-abc123"

    def test_llm_config_strips_base_url(self):
        config = LLMConfig(provider="openai", model="gpt-4o", base_url=" https://api.example.com ")
        assert config.base_url == "https://api.example.com"

    def test_llm_config_empty_string_becomes_none(self):
        config = LLMConfig(provider="openai", model="gpt-4o", api_key="  ")
        assert config.api_key is None

    def test_llm_config_strips_provider_and_model(self):
        config = LLMConfig(provider=" openai ", model=" gpt-4o ")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"

    def test_openai_env_key_stripped(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123 ")
        with patch("tavern.llm.openai_llm.AsyncOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.openai_llm import OpenAIAdapter
            config = LLMConfig(provider="openai", model="gpt-4o")
            OpenAIAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test123"

    def test_anthropic_env_key_stripped(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test ")
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from tavern.llm.anthropic_llm import AnthropicAdapter
            config = LLMConfig(provider="anthropic", model="claude-3-haiku-20240307")
            AnthropicAdapter(config=config)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-ant-test"

class TestBug7StoryActiveSince:
    def test_update_story_active_since_calls_apply_diff(self):
        state = _base_state()
        app = _make_app(state)
        mock_story_engine = MagicMock()
        mock_story_engine.get_active_nodes.return_value = {"node_1"}
        app._story_engine = mock_story_engine

        app._update_story_active_since()

        app._memory.apply_diff.assert_called_once()
        diff_arg = app._memory.apply_diff.call_args[0][0]
        assert "node_1" in diff_arg.story_active_since_updates

    def test_update_story_active_since_no_new_nodes_no_call(self):
        state = _base_state()
        app = _make_app(state)
        mock_story_engine = MagicMock()
        mock_story_engine.get_active_nodes.return_value = set()
        app._story_engine = mock_story_engine

        app._update_story_active_since()

        app._memory.apply_diff.assert_not_called()
