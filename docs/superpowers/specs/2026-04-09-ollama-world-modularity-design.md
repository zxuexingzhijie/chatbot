# Ollama 适配器 + 世界模块化 — 设计规格文档

> 日期: 2026-04-09
> 状态: 设计完成，待实施
> 依赖: 无

---

## 1. 目标

两个独立功能合为一个 spec：

1. **Ollama 适配器**：用 httpx 直连 Ollama REST API，实现 `complete` + `stream`，使游戏可以跑本地模型
2. **世界模块化**：规范 scenario 目录结构，加元数据文件 + 启动时校验 + `create-scenario` 脚手架生成器

---

## Part 1: Ollama 适配器

### 1.1 实现方式

httpx 直连 Ollama Chat API（`/api/chat`），零额外 SDK 依赖。httpx 需加入 `pyproject.toml` dependencies。

### 1.2 OllamaAdapter 类

```python
class OllamaAdapter:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        base_url = config.base_url or "http://localhost:11434"
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=config.timeout,
        )
        # complete 用 tenacity 重试；stream 不重试
        self._retryer = retry(
            retry=retry_if_exception_type(
                (httpx.ConnectError, httpx.TimeoutException)
            ),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(config.max_retries),
            reraise=True,
        )
```

### 1.3 `complete` 方法

```python
async def complete(
    self,
    messages: list[dict],
    response_format: type[T] | None = None,
) -> T | str:
    return await self._retryer(self._complete)(messages, response_format)

async def _complete(
    self,
    messages: list[dict],
    response_format: type[T] | None = None,
) -> T | str:
    body: dict = {
        "model": self._config.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": self._config.temperature,
        },
    }
    if response_format is not None:
        body["format"] = "json"
        # 追加 JSON 指令到最后一条 system message
        body["messages"] = _append_json_instruction(messages)

    resp = await self._client.post("/api/chat", json=body)
    resp.raise_for_status()
    data = resp.json()
    content = data["message"]["content"]

    if response_format is not None:
        return response_format.model_validate_json(content)
    return content
```

### 1.4 `stream` 方法

不使用 tenacity 重试——已 yield 的 chunk 收不回来，中途失败直接抛 `LLMError`。

```python
async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
    body: dict = {
        "model": self._config.model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": self._config.temperature,
        },
    }
    try:
        async with self._client.stream("POST", "/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk_data = json.loads(line)
                content = chunk_data.get("message", {}).get("content", "")
                if content:
                    yield content
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama stream failed: {exc}") from exc
```

### 1.5 辅助函数

```python
def _append_json_instruction(messages: list[dict]) -> list[dict]:
    """在 system message 末尾追加 JSON 输出指令，不修改原列表。"""
    result = []
    suffix = "Respond with valid JSON only."
    system_appended = False
    for msg in reversed(messages):
        if msg.get("role") == "system" and not system_appended:
            result.append({**msg, "content": msg["content"] + "\n" + suffix})
            system_appended = True
        else:
            result.append(msg)
    result.reverse()
    if not system_appended:
        result.insert(0, {"role": "system", "content": suffix})
    return result
```

### 1.6 LLMError

当前不存在 `LLMError`。在 `adapter.py` 中新增：

```python
class LLMError(Exception):
    """LLM adapter error."""
```

### 1.7 注册

```python
LLMRegistry.register("ollama", OllamaAdapter)
```

`app.py` 中加 `import tavern.llm.ollama_llm as _  # noqa: F401`。

### 1.8 配置示例

```yaml
llm:
  intent:
    provider: ollama
    model: qwen2:7b
    temperature: 0.1
    max_tokens: 200
    base_url: http://localhost:11434
  narrative:
    provider: ollama
    model: llama3:8b
    temperature: 0.8
    max_tokens: 500
```

---

## Part 2: 世界模块化

### 2.1 scenario.yaml 元数据

每个场景目录下放一个 `scenario.yaml`，纯元数据，不含校验规则：

```yaml
name: 奇幻酒馆
description: 在神秘的酒馆中探索，揭开地下室的秘密
author: Tavern Team
version: "1.0"
```

### 2.2 ScenarioMeta 数据类

新建 `src/tavern/world/scenario.py`：

```python
@dataclass(frozen=True)
class ScenarioMeta:
    name: str
    description: str
    author: str
    version: str
    path: Path
```

### 2.3 ScenarioValidator

同在 `scenario.py` 中，硬编码校验规则：

```python
REQUIRED_FILES = ("world.yaml", "characters.yaml")
OPTIONAL_FILES = ("story.yaml",)
OPTIONAL_DIRS = ("skills",)

def validate_scenario(path: Path) -> list[str]:
    """返回错误信息列表。空列表表示校验通过。"""
    errors: list[str] = []

    # 1. scenario.yaml 存在性和可解析性
    meta_path = path / "scenario.yaml"
    if not meta_path.exists():
        errors.append(f"缺少元数据文件: {meta_path}")
    else:
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
            for field in ("name", "description", "author", "version"):
                if not meta.get(field):
                    errors.append(f"scenario.yaml 缺少必需字段: {field}")
        except yaml.YAMLError as exc:
            errors.append(f"scenario.yaml 解析失败: {exc}")

    # 2. 必需文件存在性
    for filename in REQUIRED_FILES:
        file_path = path / filename
        if not file_path.exists():
            errors.append(f"缺少必需文件: {filename}")
        else:
            try:
                yaml.safe_load(file_path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{filename} 解析失败: {exc}")

    # 3. 交叉引用校验（characters 中的 location_id 必须在 world.yaml 的 locations 中）
    ...

    return errors
```

交叉引用校验项：
- characters.yaml 中每个角色的 `location_id` 必须存在于 world.yaml 的 `locations` 中
- world.yaml 中 location 的 `npcs` 列表中的 ID 必须存在于 characters.yaml 中
- world.yaml 中 location 的 `exits.target` 必须引用有效的 location ID
- world.yaml 中 location 的 `exits.key_item` 必须存在于 items 中

### 2.4 加载元数据

```python
def load_scenario_meta(path: Path) -> ScenarioMeta:
    meta_path = path / "scenario.yaml"
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    return ScenarioMeta(
        name=raw["name"],
        description=raw["description"],
        author=raw["author"],
        version=raw["version"],
        path=path,
    )
```

### 2.5 app.py 启动时校验

```python
errors = validate_scenario(scenario_path)
if errors:
    for e in errors:
        console.print(f"[red]✗ {e}[/]")
    raise SystemExit(1)
meta = load_scenario_meta(scenario_path)
```

`render_welcome` 中可以用 `meta.name` 替代硬编码的"醉龙酒馆"。

### 2.6 create-scenario CLI 子命令

#### 2.6.1 __main__.py 改造

现有 `__main__.py` 只有无参数的 `main()`。改造为 argparse 子命令：

```python
import argparse
import asyncio

def main():
    parser = argparse.ArgumentParser(prog="tavern", description="CLI 互动小说游戏")
    sub = parser.add_subparsers(dest="command")

    # 默认: run（无子命令时）
    run_parser = sub.add_parser("run", help="启动游戏")
    run_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    # create-scenario
    create_parser = sub.add_parser("create-scenario", help="创建新场景模板")
    create_parser.add_argument("name", help="场景名称（用作目录名）")
    create_parser.add_argument(
        "--dir", default="data/scenarios",
        help="场景父目录（默认: data/scenarios）",
    )

    args = parser.parse_args()

    if args.command == "create-scenario":
        from tavern.world.scenario import scaffold_scenario
        scaffold_scenario(args.name, Path(args.dir))
    else:
        # 无子命令 或 "run" → 启动游戏
        from tavern.cli.app import GameApp
        config_path = getattr(args, "config", "config.yaml")
        app = GameApp(config_path=config_path)
        asyncio.run(app.run())
```

`tavern`（无参数）和 `tavern run` 都启动游戏，保持向后兼容。

#### 2.6.2 scaffold_scenario 模板生成

```python
def scaffold_scenario(name: str, parent: Path) -> Path:
    """在 parent/name/ 下生成场景模板文件，返回场景目录路径。"""
    target = parent / name
    if target.exists():
        raise FileExistsError(f"目录已存在: {target}")
    target.mkdir(parents=True)
    (target / "skills").mkdir()

    # scenario.yaml
    (target / "scenario.yaml").write_text(SCENARIO_TEMPLATE.format(name=name), encoding="utf-8")
    # world.yaml
    (target / "world.yaml").write_text(WORLD_TEMPLATE, encoding="utf-8")
    # characters.yaml
    (target / "characters.yaml").write_text(CHARACTERS_TEMPLATE, encoding="utf-8")
    # story.yaml
    (target / "story.yaml").write_text(STORY_TEMPLATE, encoding="utf-8")

    return target
```

模板内容为带注释的最小可运行 YAML（一个地点、一个玩家角色、空 story nodes），注释说明每个字段的用途。

### 2.7 为 tavern 场景补充 scenario.yaml

```yaml
name: 奇幻酒馆
description: 在神秘的酒馆中探索，揭开地下室的秘密。多NPC对话驱动，地下室之谜主线。
author: Tavern Team
version: "1.0"
```

---

## 3. 代码改动范围

### Part 1: Ollama 适配器

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/tavern/llm/ollama_llm.py` | Create | OllamaAdapter 实现 |
| `src/tavern/llm/adapter.py` | Modify | 新增 `LLMError` 异常类（如果不存在） |
| `src/tavern/cli/app.py:17-18` | Modify | 加 import 触发 ollama 注册 |
| `pyproject.toml` | Modify | dependencies 加 `httpx>=0.27` |
| `tests/llm/test_ollama_llm.py` | Create | 覆盖 complete / stream / 重试策略 / JSON 解析 |

### Part 2: 世界模块化

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/tavern/world/scenario.py` | Create | ScenarioMeta + validate_scenario + scaffold_scenario + 模板常量 |
| `src/tavern/__main__.py` | Modify | argparse 子命令分发 |
| `src/tavern/cli/app.py:45-46` | Modify | 启动时 validate_scenario + 加载 meta |
| `src/tavern/cli/renderer.py:79-88` | Modify | render_welcome 使用 ScenarioMeta.name |
| `data/scenarios/tavern/scenario.yaml` | Create | 酒馆场景元数据 |
| `tests/world/test_scenario.py` | Create | validate / load_meta / scaffold 测试 |
| `tests/test_main.py` | Create | argparse 分发测试 |

---

## 4. 不做的事情

- 不做 ollama SDK 集成（用 httpx 直连）
- stream 模式不重试（幂等性问题）
- scenario.yaml 不包含 required_files / optional_files（validator 硬编码规则）
- 不做场景选择 UI / CLI 菜单（仅配置化 + 脚手架）
- 不做场景热加载（需要重启游戏切换场景）
- 不做场景版本迁移（version 字段留备用）
