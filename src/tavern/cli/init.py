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


def _build_llm_config(
    provider: str,
    intent_model: str,
    narrative_model: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    intent: dict = {
        "provider": provider,
        "model": intent_model,
        "temperature": 0.1,
        "max_tokens": 200,
    }
    narrative: dict = {
        "provider": provider,
        "model": narrative_model,
        "temperature": 0.8,
        "max_tokens": 500,
    }
    if api_key:
        intent["api_key"] = api_key
        narrative["api_key"] = api_key
    if base_url:
        intent["base_url"] = base_url
        narrative["base_url"] = base_url
    return {"intent": intent, "narrative": narrative}


def _require_input(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("此项为必填，请输入。")


def _collect_provider_config(provider: str) -> dict:
    if provider == "openai":
        base_url = input(
            "API Base URL (直接回车使用 OpenAI 官方地址，或输入兼容地址): "
        ).strip() or None
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = getpass("API Key (输入后不显示): ").strip()
        intent_model = _require_input("意图解析模型名称 (如 gpt-4o-mini): ")
        narrative_model = _require_input("叙事生成模型名称 (如 gpt-4o): ")
        return _build_llm_config(
            "openai", intent_model, narrative_model,
            api_key=api_key, base_url=base_url,
        )

    if provider == "anthropic":
        base_url = input(
            "API Base URL (直接回车使用 Anthropic 官方地址，或输入兼容地址；注意：无需包含 /v1 后缀): "
        ).strip() or None
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            api_key = getpass("API Key (输入后不显示): ").strip()
        intent_model = _require_input("意图解析模型名称 (如 claude-haiku-4-5-20251001): ")
        narrative_model = _require_input("叙事生成模型名称 (如 claude-sonnet-4-6): ")
        return _build_llm_config(
            "anthropic", intent_model, narrative_model,
            api_key=api_key, base_url=base_url,
        )

    base_url = input("Ollama 地址 (默认 http://localhost:11434): ").strip()
    base_url = base_url or "http://localhost:11434"
    intent_model = _require_input("意图解析模型名称 (如 qwen2:7b): ")
    narrative_model = _require_input("叙事生成模型名称 (如 llama3:8b): ")
    return _build_llm_config(
        "ollama", intent_model, narrative_model,
        base_url=base_url,
    )


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
