# Tavern UX 全面升级设计方案

> 日期：2026-04-09
> 状态：待实施

## 概述

针对 Tavern 奇幻酒馆游戏的 6 项用户体验问题进行全面升级，覆盖日志隔离、加载反馈、叙事 Prompt 体系重构、意图失败提示、对话等待反馈、vi_mode 可配置。

---

## 1. 日志隔离

### 问题

`app.py:109` 使用 `logging.basicConfig(level=INFO)` 配置根 logger，导致 httpx、httpcore 等第三方库的 INFO 级别日志直接输出到用户终端：

```
INFO:httpx:HTTP Request: POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"
WARNING:tavern.parser.intent:LLM intent classification failed, falling back to CUSTOM
```

### 方案

**文件：`src/tavern/cli/app.py`**

在 `logging.basicConfig()` 之后，抑制第三方库日志并将默认级别改为 WARNING：

```python
# 现有代码
log_level = debug_config.get("log_level", "INFO")
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

# 改为
log_level = debug_config.get("log_level", "WARNING")
logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
```

**文件：`config.yaml`**

```yaml
debug:
  log_level: WARNING   # 从 INFO 改为 WARNING
```

用户调试时可手动改为 INFO 或 DEBUG。

---

## 2. LLM 等待 Spinner

### 问题

用户输入到 LLM 响应之间完全沉默。意图分类最坏情况（3 次重试 x 10s 超时 = 30 秒）期间无任何视觉反馈。

### 方案

**文件：`src/tavern/cli/renderer.py`**

新增异步上下文管理器，使用 Rich 的 `Status` 组件：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def spinner(self, message: str = "思考中..."):
    with self.console.status(f"[dim]{message}[/]", spinner="dots"):
        yield
```

**文件：`src/tavern/cli/app.py`**

两个调用点：

1. **意图分类**（`_handle_free_input` 中调用 `self._parser.parse()` 时）：

```python
async with self._renderer.spinner("理解中..."):
    request = await self._parser.parse(player_input, scene_context)
```

2. **对话回复**（`_process_dialogue_input` 中调用 LLM 时）：

```python
async with self._renderer.spinner("思考中..."):
    response = await self._dialogue.respond(...)
```

叙事流式输出（streaming）不需要 spinner，因为 streaming 本身就是实时反馈。

---

## 3. 叙事 Prompt 体系重构

### 问题

当前 `prompts.py` 中所有 `NARRATIVE_TEMPLATES` 模板仅 3 行，要求 LLM "用2-3句话"描写，生成文字过短，缺乏沉浸感。

### 方案：拼接式 Prompt 架构

将 `prompts.py` 拆分为 `prompts/` 包，运行时拼接共享基础 (~250 行) + 动作专属 (~50 行)，每次发送 ~300 行 system prompt。

#### 3.1 文件结构

```
src/tavern/narrator/prompts/
├── __init__.py          # re-export build_narrative_prompt, build_ending_prompt
├── base.py              # NARRATIVE_BASE (~250 行)
├── actions.py           # ACTION_TEMPLATES dict (~50 行/每个 action type)
└── builder.py           # build_narrative_prompt(), build_ending_prompt()
```

原 `prompts.py` 删除，所有 import 路径不变（通过 `__init__.py` re-export）。

#### 3.2 NARRATIVE_BASE (~250 行)

共享基础 prompt，所有动作类型共用。覆盖以下章节：

| 章节 | 内容 | 预估行数 |
|------|------|---------|
| 角色定位 | 你是谁、世界观设定、叙事者身份 | ~15 |
| 叙事总纲 | 文学调性、奇幻风格基准、语言风格 | ~20 |
| 视角与人称 | 第二人称规则、「你」的使用、视角一致性 | ~10 |
| 感官描写五维指南 | 视觉（光影/色彩/远近）、听觉（环境音/对白/沉默）、嗅觉（气味层次/记忆联想）、触觉（温度/材质/重量）、味觉（适用场景限制） | ~50 |
| 环境互动 | 光影变化、天气效果、空间纵深、时间流逝感、建筑/自然细节 | ~25 |
| NPC 反应描写 | 微表情、肢体语言、语气变化、潜台词、群体反应 | ~25 |
| 物品描写 | 材质/重量/历史感/魔法气息/使用痕迹/情感联结 | ~20 |
| 氛围营造 | 伏笔暗示技巧、情绪递进、悬念铺设、节奏收放、场景转换 | ~25 |
| 战斗与冲突 | 动作描写节奏、紧张感营造、伤痛表现、战斗环境互动 | ~20 |
| 输出格式与长度 | 段落结构、叙事长度要求、换行规则 | ~15 |
| 禁忌清单 | 不重复动作事实、不破坏角色设定、不剧透、不出戏、不使用现代词汇、不列举选项 | ~25 |

#### 3.3 ACTION_TEMPLATES (~50 行/每个)

每个动作类型的专属指导，叠加在 NARRATIVE_BASE 之上：

- **move** (~50 行)：空间转换叙事（离开旧场景的余韵、路途过渡、进入新场景的第一印象）、新旧场景对比、方向感和距离感、门/通道/阶梯等过渡元素描写
- **look** (~50 行)：观察的层次递进（全景→中景→特写）、隐藏线索暗示技巧、观察角度切换、注意力聚焦、被观察对象的反应
- **take** (~50 行)：拾取动作的仪式感、物品与角色的情感连接、持有感描写、物品来历暗示、背包交互细节
- **search** (~50 行)：探索的紧张感营造、搜索过程描写（翻找/推开/拨开）、发现时的惊喜或失望、线索的呈现方式、失败搜索的叙事价值
- **_default** (~50 行)：通用因果叙事框架、行动→结果→环境反应→气氛变化的叙事链、不同成功/失败程度的表达梯度

#### 3.4 build_narrative_prompt() 运行时拼接

```python
def build_narrative_prompt(ctx, memory_ctx=None, story_hint=None):
    action_specific = ACTION_TEMPLATES.get(ctx.action_type, ACTION_TEMPLATES["_default"])

    system_content = (
        f"{NARRATIVE_BASE}\n\n"
        f"{'=' * 40}\n"
        f"【本次动作专属指导】\n\n"
        f"{action_specific}\n\n"
        f"{'=' * 40}\n"
        f"【当前场景信息】\n"
        f"地点：{ctx.location_name}——{ctx.location_desc}\n"
        f"玩家角色名：{ctx.player_name}"
    )
    # + memory_ctx, story_hint 同现有逻辑
    ...
```

#### 3.5 max_tokens 无上限

**文件：`src/tavern/llm/adapter.py`**

```python
# 现有
max_tokens: int = 500

# 改为
max_tokens: int | None = None
```

**文件：`src/tavern/llm/openai_llm.py`**

`_complete()` 和 `stream()` 中，仅当 `max_tokens is not None` 时才传入：

```python
kwargs: dict = {
    "model": self._config.model,
    "messages": messages,
    "temperature": self._config.temperature,
}
if self._config.max_tokens is not None:
    kwargs["max_tokens"] = self._config.max_tokens
```

**文件：`src/tavern/llm/anthropic_llm.py`**

Anthropic API **必须**传 max_tokens，为 None 时使用 `8192` 作为默认上限：

```python
"max_tokens": self._config.max_tokens or 8192,
```

`_complete()` 和 `stream()` 两处同样处理。

**文件：`src/tavern/llm/ollama_llm.py`**

Ollama 当前未传 max_tokens（在 options 中仅传 temperature），无需改动。如果未来需要支持，同 OpenAI 方式处理。

**文件：`config.yaml`**

删除 intent 和 narrative 中的 `max_tokens` 行：

```yaml
llm:
  intent:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1
    max_retries: 3
    timeout: 10.0
  narrative:
    provider: openai
    model: gpt-4o
    temperature: 0.8
    max_retries: 2
    timeout: 30.0
    stream: true
```

注释中的 Ollama 示例同样删除 `max_tokens` 行。

**文件：`src/tavern/cli/init.py`**

`_build_llm_config()` 中删除 intent 和 narrative 字典的 `"max_tokens"` 键。

**文件：`tests/llm/test_adapter.py`**

测试中构造 `LLMConfig` 时删除 `max_tokens=200` 参数（将使用默认值 None）。

---

## 4. 意图失败友好提示

### 问题

LLM 意图分类失败或低置信度时，用户只看到 "你尝试了: {原文}"，完全不知道是理解失败。

### 方案

**文件：`src/tavern/parser/intent.py`**

在 `ActionRequest` 模型或 `parse()` 返回中增加 `is_fallback: bool` 标记：

```python
# parse() 返回值改为 tuple
async def parse(self, player_input, scene_context) -> ActionRequest:
    ...
    # exception fallback
    except Exception:
        logger.warning(...)
        return ActionRequest(
            action=ActionType.CUSTOM,
            detail=player_input,
            confidence=0.0,
            is_fallback=True,   # 新增字段
        )

    # low confidence fallback
    if result.confidence < CONFIDENCE_THRESHOLD:
        ...
        return ActionRequest(
            action=ActionType.CUSTOM,
            detail=player_input,
            confidence=result.confidence,
            is_fallback=True,   # 新增字段
        )

    return result  # is_fallback 默认 False
```

**文件：`src/tavern/cli/app.py`**

在 `_handle_free_input` 中，渲染结果前检查 fallback：

```python
if request.is_fallback:
    self._renderer.console.print("[dim]（未能完全理解你的意图，尝试自由行动...）[/]")
```

**文件：`src/tavern/engine/rules.py`**

`_handle_custom` 的默认消息从：
```
你尝试了: {detail}
```
改为更叙事化的：
```
你尝试{detail}，但结果不太明朗。
```

---

## 5. 对话等待 Spinner

### 问题

NPC 对话是阻塞式 JSON 响应，等待期间无反馈。

### 方案

复用第 2 节的 spinner 组件。在 `app.py` 的 `_process_dialogue_input` 中：

```python
async with self._renderer.spinner("思考中..."):
    response = await self._dialogue.respond(ctx, player_input)
```

不改对话为真正的流式输出，原因：
- 对话需返回结构化 JSON（text + trust_delta + mood + wants_to_end），streaming 解析困难
- 对话单次响应较短，延迟低于叙事
- Spinner 已解决核心痛点（沉默等待）

---

## 6. vi_mode 可配置

### 问题

`renderer.py:55` 硬编码 `vi_mode=True`，非 Vim 用户操作不便。

### 方案

**文件：`config.yaml`**

`game` 段新增：

```yaml
game:
  vi_mode: false   # 默认关闭
  ...
```

**文件：`src/tavern/cli/renderer.py`**

`Renderer.__init__` 接收 `vi_mode` 参数：

```python
def __init__(self, vi_mode: bool = False) -> None:
    self.console = Console()
    self._session = PromptSession(vi_mode=vi_mode, completer=SlashCommandCompleter())
```

**文件：`src/tavern/cli/app.py`**

从 game_config 读取并传入：

```python
vi_mode = game_config.get("vi_mode", False)
self._renderer = Renderer(vi_mode=vi_mode)
```

---

## 涉及文件总览

| 文件 | 改动类型 | 改动内容 |
|------|---------|---------|
| `src/tavern/cli/app.py` | 修改 | 日志配置、spinner 调用、fallback 提示、vi_mode 传递 |
| `src/tavern/cli/renderer.py` | 修改 | 新增 spinner 方法、vi_mode 参数化 |
| `src/tavern/narrator/prompts.py` | 删除 | 拆分为 prompts/ 包 |
| `src/tavern/narrator/prompts/__init__.py` | 新建 | re-export |
| `src/tavern/narrator/prompts/base.py` | 新建 | NARRATIVE_BASE (~250 行) |
| `src/tavern/narrator/prompts/actions.py` | 新建 | ACTION_TEMPLATES (~250 行，5 个 action 各 ~50) |
| `src/tavern/narrator/prompts/builder.py` | 新建 | build_narrative_prompt(), build_ending_prompt() |
| `src/tavern/parser/intent.py` | 修改 | ActionRequest 增加 is_fallback 字段 |
| `src/tavern/engine/rules.py` | 修改 | custom action 提示文案 |
| `src/tavern/llm/adapter.py` | 修改 | max_tokens 改为 Optional[int] = None |
| `src/tavern/llm/openai_llm.py` | 修改 | max_tokens 条件传参 |
| `src/tavern/llm/anthropic_llm.py` | 修改 | max_tokens None 时用 8192 |
| `src/tavern/cli/init.py` | 修改 | 删除 max_tokens 字段 |
| `config.yaml` | 修改 | 删除 max_tokens、加 vi_mode、改 log_level |
| `tests/llm/test_adapter.py` | 修改 | 删除 max_tokens 测试参数 |

## 实施顺序建议

1. **日志隔离**（第 1 节）— 最小改动，立即见效
2. **max_tokens 无上限**（第 3.5 节）— adapter 层改动，为后续 prompt 加长铺路
3. **Prompt 体系重构**（第 3.1-3.4 节）— 新建 prompts/ 包，编写详细模板
4. **Spinner**（第 2、5 节）— renderer + app 改动
5. **意图失败提示**（第 4 节）— intent + rules + app 改动
6. **vi_mode 可配置**（第 6 节）— 最后收尾
