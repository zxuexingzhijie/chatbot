from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path

import yaml


def _get_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "tavern"


def _prompt_choice(prompt: str, choices: list[str], default: int = 0) -> str:
    print(f"\n{prompt}")
    for i, c in enumerate(choices):
        marker = " *" if i == default else ""
        print(f"  [{i + 1}] {c}{marker}")
    while True:
        raw = input(f"请选择 (1-{len(choices)}, 默认 {default + 1}): ").strip()
        if not raw:
            return choices[default]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print("输入无效，请重试。")


def _build_openai_config(api_key: str) -> dict:
    return {
        "intent": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "max_tokens": 200,
            "api_key": api_key,
        },
        "narrative": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.8,
            "max_tokens": 500,
            "api_key": api_key,
        },
    }


def _build_anthropic_config(api_key: str) -> dict:
    return {
        "intent": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "temperature": 0.1,
            "max_tokens": 200,
            "api_key": api_key,
        },
        "narrative": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.8,
            "max_tokens": 500,
            "api_key": api_key,
        },
    }


def _build_ollama_config(base_url: str, intent_model: str, narrative_model: str) -> dict:
    return {
        "intent": {
            "provider": "ollama",
            "model": intent_model,
            "temperature": 0.1,
            "max_tokens": 200,
            "base_url": base_url,
        },
        "narrative": {
            "provider": "ollama",
            "model": narrative_model,
            "temperature": 0.8,
            "max_tokens": 500,
            "base_url": base_url,
        },
    }


def _collect_provider_config(provider: str) -> dict:
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            api_key = getpass("OpenAI API Key (输入后不显示): ")
        return _build_openai_config(api_key)

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            api_key = getpass("Anthropic API Key (输入后不显示): ")
        return _build_anthropic_config(api_key)

    base_url = input("Ollama 地址 (默认 http://localhost:11434): ").strip()
    base_url = base_url or "http://localhost:11434"
    intent_model = input("意图解析模型 (默认 qwen2:7b): ").strip() or "qwen2:7b"
    narrative_model = input("叙事生成模型 (默认 llama3:8b): ").strip() or "llama3:8b"
    return _build_ollama_config(base_url, intent_model, narrative_model)


def run_init() -> Path:
    print("欢迎使用 Tavern! 让我们配置 LLM 后端。\n")

    provider = _prompt_choice(
        "选择 LLM 提供商:",
        ["openai", "anthropic", "ollama"],
        default=0,
    )

    llm_config = _collect_provider_config(provider)
    config: dict = {
        "llm": llm_config,
        "game": {"scenario": "tavern"},
    }

    config_dir = _get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    print(f"\n配置已保存到: {config_path}")
    return config_path
