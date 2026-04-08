# 多后端 LLM 适配器（Phase 4b）— 设计规格

**日期**: 2026-04-08
**状态**: 已批准
**范围**: AnthropicAdapter 实现 + Ollama 纯配置支持

---

## 1. 概述

为游戏 LLM 层新增 Anthropic Claude 后端支持，同时通过配置复用 `OpenAIAdapter` 支持 Ollama（OpenAI 兼容接口）。不引入新抽象层，保持与现有 `LLMAdapter` Protocol 一致。

### 设计目标

- `AnthropicAdapter`：实现 `LLMAdapter` Protocol，注册为 `"anthropic"`
- Ollama：零新代码，通过 `provider: openai` + `base_url` 配置复用 `OpenAIAdapter`
- 与 `OpenAIAdapter` 保持一致的行为：retry 策略、API key 环境变量回退、JSON mode 处理方式

---

## 2. 架构

### 2.1 数据流（不变）

```
config.yaml
  └─ LLMConfig(provider="anthropic", model=..., api_key=...)
       └─ LLMRegistry.create(config)
            └─ AnthropicAdapter(config)
                 ├─ complete(messages, response_format) → str
                 └─ stream(messages) → AsyncIterator[str]
```

### 2.2 模块结构

```
src/tavern/llm/
├── adapter.py              # 已有：LLMConfig, LLMAdapter Protocol, LLMRegistry
├── openai_llm.py           # 已有：OpenAIAdapter（注册为 "openai"）
├── anthropic_llm.py        # 新建：AnthropicAdapter（注册为 "anthropic"）
└── service.py              # 不变

src/tavern/cli/app.py       # 修改：添加 anthropic_llm import 触发注册
config.yaml                 # 修改：添加 Ollama 配置注释说明

tests/llm/
└── test_anthropic_llm.py   # 新建：AnthropicAdapter 单元测试
```

---

## 3. AnthropicAdapter 实现规格

### 3.1 文件：`src/tavern/llm/anthropic_llm.py`

```python
from __future__ import annotations

import os
from typing import AsyncIterator, Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from tavern.llm.adapter import LLMAdapter, LLMConfig, LLMRegistry


_RETRY_POLICY = dict(
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)


class AnthropicAdapter:
    def __init__(self, config: LLMConfig) -> None:
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=0,  # tenacity handles retry
        )
        self._config = config

    @retry(**_RETRY_POLICY)
    async def complete(
        self, messages: list[dict], response_format: Any = None
    ) -> str:
        system, user_messages = _split_system(messages)
        if response_format is not None:
            system = (system + "\n" if system else "") + "Respond with valid JSON only."
        kwargs = dict(
            model=self._config.model,
            max_tokens=self._config.max_tokens,
            messages=user_messages,
        )
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        system, user_messages = _split_system(messages)
        kwargs = dict(
            model=self._config.model,
            max_tokens=self._config.max_tokens,
            messages=user_messages,
        )
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as s:
            async for chunk in s.text_stream:
                yield chunk


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """提取所有 system 消息拼接为单一 system 参数，其余原样返回。"""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    user_messages = [m for m in messages if m.get("role") != "system"]
    return "\n".join(system_parts), user_messages


LLMRegistry.register("anthropic", AnthropicAdapter)
```

### 3.2 关键设计决策

| 问题 | 决策 |
|------|------|
| 多条 system 消息 | 全部提取，`"\n".join` 拼接后传入 `system` 参数 |
| API key | `config.api_key or os.environ.get("ANTHROPIC_API_KEY")` |
| JSON mode | 向 system 追加 `"Respond with valid JSON only."`（与 OpenAIAdapter 一致） |
| Retry | tenacity，retry `RateLimitError` / `APIConnectionError`，3 次，指数退避 |
| `max_retries=0` | 关闭 SDK 内置 retry，由 tenacity 统一管理 |
| `stream()` | 使用 `client.messages.stream()` context manager，yield `text_stream` 块 |

---

## 4. Ollama 支持

无新代码。在 `config.yaml` 添加注释说明用法：

```yaml
# Ollama 示例（本地运行）：
# llm:
#   intent:
#     provider: openai
#     model: llama3.2
#     base_url: http://localhost:11434/v1
#     api_key: ollama        # Ollama 要求非空字符串
#   narrative:
#     provider: openai
#     model: llama3.2
#     base_url: http://localhost:11434/v1
#     api_key: ollama
```

---

## 5. GameApp 集成

`src/tavern/cli/app.py` 添加一行 import 触发注册（与现有 openai 注册方式一致）：

```python
from tavern.llm.anthropic_llm import AnthropicAdapter  # noqa: F401 — triggers registration
```

---

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| `api_key` 未配置且环境变量未设置 | `anthropic.AuthenticationError` 自然抛出 |
| `RateLimitError` / `APIConnectionError` | tenacity 重试 3 次后 reraise |
| 其他 Anthropic API 错误 | 不捕获，向上传播（与 OpenAIAdapter 一致） |
| `response.content` 为空 | `IndexError`，不特殊处理（模型行为异常，应暴露） |

---

## 7. 测试计划

### `tests/llm/test_anthropic_llm.py`（~8 个）

| 测试 | 内容 |
|------|------|
| `test_complete_returns_text` | mock `AsyncAnthropic`，verify `content[0].text` 返回 |
| `test_complete_with_response_format_appends_json_instruction` | system 参数包含 `"Respond with valid JSON only."` |
| `test_complete_system_messages_joined` | 多条 system 消息 `"\n".join` 拼接后传入 `system` |
| `test_complete_no_system_omits_system_param` | 无 system 消息时，`messages.create` 不传 `system` 参数 |
| `test_stream_yields_chunks` | mock `text_stream`，verify async generator 产出 |
| `test_stream_no_system_omits_system_param` | stream 路径同样不传 `system` |
| `test_api_key_env_fallback` | `config.api_key=None`，从 `ANTHROPIC_API_KEY` 环境变量读取 |
| `test_registry_registers_anthropic` | `LLMRegistry.create(LLMConfig(provider="anthropic", ...))` 返回 `AnthropicAdapter` |

---

## 8. 文件变更清单

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| 新建 | `src/tavern/llm/anthropic_llm.py` | ~70 |
| 修改 | `src/tavern/cli/app.py` | +1 |
| 修改 | `config.yaml` | +10（注释） |
| 新建 | `tests/llm/test_anthropic_llm.py` | ~120 |

---

## 9. 不在范围内

- Gemini / Mistral 等其他后端
- 流式 retry（streaming 中途断开不重试）
- 动态切换后端（运行时热切换）
- Anthropic tool_use / function calling（当前不需要）
