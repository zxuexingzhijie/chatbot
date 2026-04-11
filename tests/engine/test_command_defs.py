from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tavern.engine.command_defs import (
    cmd_help,
    cmd_hint,
    cmd_inventory,
    cmd_load,
    cmd_look,
    cmd_quit,
    cmd_save,
    cmd_saves,
    cmd_status,
    cmd_undo,
    register_all_commands,
)
from tavern.engine.commands import CommandRegistry
from tavern.engine.fsm import ModeContext
from tavern.world.models import ActionResult
from tavern.engine.actions import ActionType


def _make_context(**overrides) -> ModeContext:
    defaults = dict(
        state_manager=MagicMock(),
        renderer=MagicMock(),
        dialogue_manager=MagicMock(),
        narrator=MagicMock(),
        memory=MagicMock(),
        persistence=MagicMock(),
        story_engine=MagicMock(),
        command_registry=MagicMock(),
        action_registry=MagicMock(),
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return ModeContext(**defaults)


class TestCmdLook:
    @pytest.mark.asyncio
    async def test_look_without_args_uses_action_registry(self):
        action_reg = MagicMock()
        result = ActionResult(success=True, action=ActionType.LOOK, message="你看到了酒馆")
        action_reg.validate_and_execute.return_value = (result, None)
        ctx = _make_context(action_registry=action_reg)
        await cmd_look("", ctx)
        action_reg.validate_and_execute.assert_called_once()
        ctx.renderer.render_result.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_look_with_args_passes_target(self):
        action_reg = MagicMock()
        result = ActionResult(success=True, action=ActionType.LOOK, message="你看到了桌子")
        action_reg.validate_and_execute.return_value = (result, None)
        ctx = _make_context(action_registry=action_reg)
        await cmd_look("桌子", ctx)
        call_args = action_reg.validate_and_execute.call_args
        request = call_args[0][0]
        assert request.target == "桌子"

    @pytest.mark.asyncio
    async def test_look_without_action_registry_falls_back_to_rules(self):
        rules_mock = MagicMock()
        result = ActionResult(success=True, action=ActionType.LOOK, message="酒馆大厅")
        rules_mock.validate.return_value = (result, None)
        ctx = _make_context(action_registry=None)
        with patch("tavern.engine.rules.RulesEngine", return_value=rules_mock):
            await cmd_look("", ctx)
        ctx.renderer.render_result.assert_called_once_with(result)


class TestCmdInventory:
    @pytest.mark.asyncio
    async def test_renders_inventory(self):
        ctx = _make_context()
        await cmd_inventory("", ctx)
        ctx.renderer.render_inventory.assert_called_once_with(
            ctx.state_manager.state
        )


class TestCmdStatus:
    @pytest.mark.asyncio
    async def test_renders_status_with_relationships(self):
        ctx = _make_context()
        await cmd_status("", ctx)
        ctx.memory.get_player_relationships.assert_called_once_with(
            ctx.state_manager.state.player_id
        )
        ctx.renderer.render_status.assert_called_once()


class TestCmdUndo:
    @pytest.mark.asyncio
    async def test_no_history_renders_error(self):
        ctx = _make_context()
        ctx.state_manager.undo.return_value = None
        await cmd_undo("", ctx)
        ctx.renderer.console.print.assert_called_once()
        call_str = ctx.renderer.console.print.call_args[0][0]
        assert "没有可以回退" in call_str

    @pytest.mark.asyncio
    async def test_undo_success_with_action_registry(self):
        action_reg = MagicMock()
        result = ActionResult(success=True, action=ActionType.LOOK, message="ok")
        action_reg.validate_and_execute.return_value = (result, None)
        ctx = _make_context(action_registry=action_reg)
        ctx.state_manager.undo.return_value = MagicMock()
        await cmd_undo("", ctx)
        action_reg.validate_and_execute.assert_called_once()
        ctx.renderer.render_result.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_undo_success_without_action_registry(self):
        rules_mock = MagicMock()
        result = ActionResult(success=True, action=ActionType.LOOK, message="ok")
        rules_mock.validate.return_value = (result, None)
        ctx = _make_context(action_registry=None)
        ctx.state_manager.undo.return_value = MagicMock()
        with patch("tavern.engine.rules.RulesEngine", return_value=rules_mock):
            await cmd_undo("", ctx)
        ctx.renderer.render_result.assert_called_once_with(result)


class TestCmdSave:
    @pytest.mark.asyncio
    async def test_default_slot(self):
        ctx = _make_context()
        await cmd_save("", ctx)
        call_args = ctx.persistence.save.call_args
        assert call_args[0][1] == "auto"

    @pytest.mark.asyncio
    async def test_named_slot(self):
        ctx = _make_context()
        await cmd_save("slot1", ctx)
        call_args = ctx.persistence.save.call_args
        assert call_args[0][1] == "slot1"

    @pytest.mark.asyncio
    async def test_save_failure_renders_error(self):
        ctx = _make_context()
        ctx.persistence.save.side_effect = OSError("disk full")
        await cmd_save("", ctx)
        call_str = ctx.renderer.console.print.call_args[0][0]
        assert "存档失败" in call_str


class TestCmdLoad:
    @pytest.mark.asyncio
    async def test_load_during_dialogue_blocked(self):
        dm = MagicMock()
        dm.is_active = True
        ctx = _make_context(dialogue_manager=dm)
        await cmd_load("", ctx)
        ctx.renderer.console.print.assert_called_once()
        call_str = ctx.renderer.console.print.call_args[0][0]
        assert "结束当前对话" in call_str

    @pytest.mark.asyncio
    async def test_load_success(self):
        dm = MagicMock()
        dm.is_active = False
        ctx = _make_context(dialogue_manager=dm)
        ctx.persistence.load.return_value = (MagicMock(), "2026-04-11")
        await cmd_load("", ctx)
        ctx.state_manager.replace.assert_called_once()
        ctx.memory.rebuild.assert_called_once()
        ctx.renderer.render_load_success.assert_called_once()


class TestCmdQuit:
    @pytest.mark.asyncio
    async def test_raises_system_exit(self):
        ctx = _make_context()
        with pytest.raises(SystemExit):
            await cmd_quit("", ctx)


class TestRegisterAllCommands:
    def test_registers_all_expected_commands(self):
        registry = CommandRegistry()
        register_all_commands(registry)
        expected = [
            "/look", "/inventory", "/status", "/hint",
            "/undo", "/help", "/save", "/saves", "/load", "/quit",
        ]
        for name in expected:
            assert registry.find(name) is not None, f"{name} not registered"

    def test_aliases_are_registered(self):
        registry = CommandRegistry()
        register_all_commands(registry)
        assert registry.find("/l") is not None
        assert registry.find("/i") is not None
        assert registry.find("/q") is not None
        assert registry.find("/h") is not None
