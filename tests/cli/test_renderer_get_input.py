from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.cli.renderer import Renderer
from tavern.engine.fsm import PromptConfig


@pytest.fixture
def renderer():
    console = MagicMock()
    console.status = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
    with patch("tavern.cli.renderer.PromptSession") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.prompt_async = AsyncMock(return_value="test input")
        mock_session_cls.return_value = mock_session
        r = Renderer(console=console)
        r._session = mock_session
        yield r


@pytest.mark.asyncio
async def test_get_input_no_args(renderer):
    """get_input() with no args works (backwards compatible)."""
    result = await renderer.get_input()
    assert result == "test input"


@pytest.mark.asyncio
async def test_get_input_with_prompt_config(renderer):
    """get_input() accepts PromptConfig and uses its prompt_text."""
    config = PromptConfig(prompt_text="对话> ", show_status_bar=False)
    result = await renderer.get_input(config=config)
    assert result == "test input"
    call_args = renderer._session.prompt_async.call_args
    prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "对话" in str(prompt_arg)


@pytest.mark.asyncio
async def test_get_input_with_none_config(renderer):
    """get_input(config=None) uses default prompt."""
    result = await renderer.get_input(config=None)
    assert result == "test input"
