"""Tests for the 7-bug fix batch — SEARCH events, story stat->relationship sync,
Anthropic base_url, default config, and API key strip."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.llm.adapter import LLMConfig
from tavern.world.models import (
    ActionRequest,
    Character,
    CharacterRole,
    Location,
)
from tavern.world.state import WorldState
from tavern.cli.app import GameApp


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
