from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from io import StringIO

from rich.console import Console

from tavern.cli.renderer import Renderer, _LIVE_REFRESH_RATE


class TestLiveRefreshRateConstant:
    def test_exists_and_reasonable(self):
        assert isinstance(_LIVE_REFRESH_RATE, (int, float))
        assert 5 <= _LIVE_REFRESH_RATE <= 30


class TestRenderStreamMarkdown:
    @pytest.mark.asyncio
    async def test_render_stream_accumulates_and_renders_markdown(self):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=False)

        async def fake_stream():
            yield "Hello "
            yield "**world**"

        with patch("rich.live.Live") as mock_live_cls:
            mock_live = MagicMock()
            mock_live.__enter__ = MagicMock(return_value=mock_live)
            mock_live.__exit__ = MagicMock(return_value=False)
            mock_live_cls.return_value = mock_live

            await renderer.render_stream(fake_stream())

            assert mock_live.update.call_count == 2

    @pytest.mark.asyncio
    async def test_render_stream_typewriter_pauses(self):
        console = Console(file=StringIO(), force_terminal=True, width=80)
        renderer = Renderer(console=console, typewriter_effect=True)

        async def fake_stream():
            yield "句子结束。"
            yield "继续"

        with patch("rich.live.Live") as mock_live_cls:
            mock_live = MagicMock()
            mock_live.__enter__ = MagicMock(return_value=mock_live)
            mock_live.__exit__ = MagicMock(return_value=False)
            mock_live_cls.return_value = mock_live

            with patch("asyncio.sleep", new_callable=lambda: MagicMock(side_effect=lambda _: asyncio.sleep(0))) as mock_sleep:
                await renderer.render_stream(fake_stream())
                assert mock_sleep.call_count >= 1


class TestRenderMarkdownText:
    def test_renders_markdown_to_console(self):
        from tavern.cli.renderer import render_markdown_text
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=80)
        render_markdown_text(console, "**bold text**")
        rendered = output.getvalue()
        assert "bold text" in rendered
