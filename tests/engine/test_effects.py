from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

from tavern.engine.effects import (
    EFFECT_EXECUTORS,
    exec_apply_diff,
    exec_apply_trust,
    exec_emit_event,
    exec_end_dialogue,
    exec_start_dialogue,
)
from tavern.engine.fsm import EffectKind, ModeContext
from tavern.world.models import Character, CharacterRole
from tavern.world.state import StateDiff


def _make_ctx(
    characters: dict | None = None,
    player_id: str = "player",
    dialogue_manager: MagicMock | None = None,
    story_engine: MagicMock | None = None,
) -> ModeContext:
    state = MagicMock()
    state.player_id = player_id
    state.characters = characters or {}
    state.timeline = ()

    state_manager = MagicMock()
    state_manager.state = state

    dm = dialogue_manager if dialogue_manager is not None else MagicMock()
    memory = MagicMock()
    memory.graph = MagicMock()

    return ModeContext(
        state_manager=state_manager,
        renderer=MagicMock(),
        dialogue_manager=dm,
        narrator=MagicMock(),
        memory=memory,
        persistence=MagicMock(),
        story_engine=story_engine,
        command_registry=MagicMock(),
        action_registry=None,
        logger=MagicMock(),
    )


class TestEffectExecutors:
    def test_all_effect_kinds_have_executors(self):
        for kind in EffectKind:
            assert kind in EFFECT_EXECUTORS, f"Missing executor for {kind}"

    def test_all_executors_are_callable(self):
        for kind, executor in EFFECT_EXECUTORS.items():
            assert callable(executor), f"Executor for {kind} is not callable"


class TestExecApplyDiff:
    async def test_commits_diff(self):
        ctx = _make_ctx()
        diff = StateDiff(turn_increment=1)
        await exec_apply_diff({"diff": diff, "action": None}, ctx)
        ctx.state_manager.commit.assert_called_once_with(diff, None)


class TestExecStartDialogue:
    async def test_raises_on_unknown_npc(self):
        ctx = _make_ctx(characters={})
        with pytest.raises(ValueError, match="NPC not found"):
            await exec_start_dialogue({"npc_id": "grim"}, ctx)

    async def test_calls_set_active_npc(self):
        npc = Character(
            id="grim",
            name="Grim",
            role=CharacterRole.NPC,
            location_id="tavern",
            stats={"trust": 10},
        )
        dm = MagicMock()
        dm.set_active_npc = MagicMock()
        ctx = _make_ctx(characters={"grim": npc}, dialogue_manager=dm)
        await exec_start_dialogue({"npc_id": "grim"}, ctx)
        dm.set_active_npc.assert_called_once_with("grim")


class TestExecEndDialogue:
    async def test_calls_dialogue_manager_reset(self):
        dm = MagicMock()
        dm.reset = MagicMock()
        ctx = _make_ctx(dialogue_manager=dm)
        await exec_end_dialogue({}, ctx)
        dm.reset.assert_called_once()


class TestExecApplyTrust:
    async def test_commits_trust_diff(self):
        npc = Character(
            id="grim",
            name="Grim",
            role=CharacterRole.NPC,
            location_id="tavern",
            stats={"trust": 10},
        )
        ctx = _make_ctx(characters={"grim": npc})
        await exec_apply_trust({"npc_id": "grim", "delta": 5}, ctx)
        ctx.state_manager.commit.assert_called_once()
        call_args = ctx.state_manager.commit.call_args
        diff = call_args[0][0]
        assert "grim" in diff.updated_characters
        new_stats = diff.updated_characters["grim"]["stats"]
        assert new_stats["trust"] == 15
        assert len(diff.relationship_changes) == 1
        assert diff.relationship_changes[0]["delta"] == 5
        assert diff.turn_increment == 0

    async def test_clamps_trust_to_range(self):
        npc = Character(
            id="grim",
            name="Grim",
            role=CharacterRole.NPC,
            location_id="tavern",
            stats={"trust": 95},
        )
        ctx = _make_ctx(characters={"grim": npc})
        await exec_apply_trust({"npc_id": "grim", "delta": 20}, ctx)
        call_args = ctx.state_manager.commit.call_args
        diff = call_args[0][0]
        new_stats = diff.updated_characters["grim"]["stats"]
        assert new_stats["trust"] == 100


class TestExecEmitEvent:
    async def test_calls_story_engine_check(self):
        se = MagicMock()
        se.check = MagicMock(return_value=[])
        ctx = _make_ctx(story_engine=se)
        await exec_emit_event({"event": "test_event"}, ctx)
        se.check.assert_called_once()

    async def test_skips_when_no_story_engine(self):
        ctx = _make_ctx(story_engine=None)
        await exec_emit_event({"event": "test_event"}, ctx)
