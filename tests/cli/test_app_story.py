from __future__ import annotations


def test_app_import_registers_anthropic_provider():
    """Importing tavern.cli.app registers both openai and anthropic providers."""
    from tavern.llm.adapter import LLMRegistry
    import tavern.cli.app  # noqa: F401 — triggers registration side-effects
    assert "openai" in LLMRegistry._providers
    assert "anthropic" in LLMRegistry._providers
