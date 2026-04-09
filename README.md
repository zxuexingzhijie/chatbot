# Tavern (酒馆)

CLI 互动式小说游戏 — 在奇幻酒馆中自由探索，与 NPC 对话，揭开地下室的秘密。

采用混合管道架构（规则引擎 + LLM），在保障剧情可控的前提下提供开放式叙事体验。

## 安装

### Homebrew（macOS / Linux）

```bash
brew tap zxuexingzhijie/tavern
brew install tavern-game
```

### pip

```bash
# OpenAI 后端（默认）
pip install tavern-game[openai]

# Anthropic 后端
pip install tavern-game[anthropic]

# Ollama 本地模型
pip install tavern-game[ollama]

# 全部后端
pip install tavern-game[all]
```

### 从源码安装

```bash
git clone https://github.com/zxuexingzhijie/chatbot.git
cd chatbot
pip install -e ".[dev]"
```

## 快速开始

```bash
# 首次使用 — 交互式配置向导
tavern init

# 启动游戏
tavern
```

`tavern init` 会引导你选择 LLM 提供商、输入 API Key，并将配置保存到 `~/.config/tavern/config.yaml`。

## 系统要求

- Python >= 3.12
- LLM 后端（三选一）：
  - OpenAI API（默认）
  - Anthropic API
  - [Ollama](https://ollama.com/)（本地部署，零成本）

## 配置

配置文件搜索顺序：`--config` 显式指定 → `~/.config/tavern/config.yaml` → `./config.yaml` → 内置默认配置

```yaml
llm:
  intent:        # 意图解析（推荐轻量模型）
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1
  narrative:     # 叙事生成（推荐创意模型）
    provider: openai
    model: gpt-4o
    temperature: 0.8

game:
  scenario: tavern          # 场景名称
  auto_save_interval: 5
  undo_history_size: 50
```

### 使用 Ollama（本地模型）

```yaml
llm:
  intent:
    provider: ollama
    model: qwen2:7b
    base_url: http://localhost:11434
  narrative:
    provider: ollama
    model: llama3:8b
```

### 使用 Anthropic

```yaml
llm:
  intent:
    provider: anthropic
    model: claude-haiku-4-5-20251001
  narrative:
    provider: anthropic
    model: claude-sonnet-4-6
```

## 游戏玩法

输入自然语言与世界互动，例如：

- `走向吧台` — 移动到吧台区
- `和酒保聊天` — 进入对话模式
- `拿起桌上的告示` — 拾取物品
- `用钥匙打开地下室的门` — 使用物品

### 系统命令

| 命令 | 说明 |
|------|------|
| `look` | 查看当前环境 |
| `inventory` | 查看背包 |
| `status` | 角色状态（属性、人际关系、任务进度） |
| `hint` | 获取提示 |
| `undo` | 回退上一步 |
| `save [名称]` | 存档（默认: autosave） |
| `load [名称]` | 读档 |
| `saves` | 列出所有存档 |
| `help` | 显示帮助 |
| `quit` | 退出 |

## 内置场景：奇幻酒馆

- **5 个地点**：酒馆大厅、吧台区、客房走廊、后院、地下室（需钥匙）
- **3 个 NPC**：旅行者艾琳、酒保格里姆、神秘旅客
- **主线任务**：地下室之谜 — 获得酒保信任(关系值 >= 30)以获取钥匙
- **3 条支线**：旅行者的护身符、神秘旅客的委托、后院探索
- **3 个结局**：黎明之路（善）、暗影独行（恶）、过客（中立）
- **失败推进**：卡住时自动触发提示事件

## 创建自定义场景

```bash
# 生成场景模板
tavern create-scenario my_adventure

# 编辑场景文件
# data/scenarios/my_adventure/
#   scenario.yaml    — 元数据
#   world.yaml       — 地点和物品
#   characters.yaml  — 角色定义
#   story.yaml       — 剧情节点
#   skills/          — NPC 知识模块

# 用自定义场景启动
tavern run --config my_config.yaml
```

场景启动时会自动校验文件完整性和交叉引用一致性。

## 架构

```
玩家输入 (Rich CLI)
       ↓
┌─────────────────┐
│ ① 意图解析层     │  LLM 分类 → ActionRequest
└────────┬────────┘
         ↓
┌─────────────────┐
│ ② 规则引擎层     │  世界规则验证 → StateDiff
└────────┬────────┘
         ↓
┌─────────────────┐
│ ③ 叙事生成层     │  LLM 流式生成场景描述
└────────┬────────┘
         ↓
   Rich 渲染输出
```

**双 LLM 设计**：轻量模型解析意图（快+准），创意模型生成叙事（流式打字机效果）。

**不可变状态**：所有状态变更通过 `StateDiff` 产生新对象，支持 undo/redo。

**记忆系统**：事件时间线 + 关系图 + 动态知识注入，NPC 对话根据上下文自适应。

## 项目结构

```
src/tavern/
├── cli/           # 游戏主循环 + Rich 渲染
├── data/          # 内置场景数据 + 默认配置
├── dialogue/      # NPC 对话系统
├── engine/        # 规则引擎 + 剧情节点引擎
├── llm/           # LLM 适配器（OpenAI / Anthropic / Ollama）
├── narrator/      # 叙事生成
├── parser/        # 自然语言意图解析
└── world/         # 世界模型、状态管理、记忆、存档、场景校验
```

## 开发

```bash
# 安装开发依赖（含全部 LLM 后端）
pip install -e ".[dev]"

# 运行测试
pytest

# 运行测试（带覆盖率）
pytest --cov=tavern
```

## 核心依赖

| 库 | 用途 |
|----|------|
| rich | 终端 UI 渲染 |
| pydantic | 数据模型与校验 |
| pyyaml | YAML 场景文件解析 |
| tenacity | 重试机制 |

### 可选依赖（按 LLM 后端）

| 库 | 安装方式 |
|----|---------|
| openai | `pip install tavern-game[openai]` |
| anthropic | `pip install tavern-game[anthropic]` |
| httpx | `pip install tavern-game[ollama]` |

## License

MIT
