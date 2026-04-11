from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tavern.cli.bootstrap import bootstrap
from tavern.cli.renderer import Renderer
from tavern.dialogue.manager import DialogueManager
from tavern.narrator.narrator import Narrator
from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.service import LLMService
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
from tavern.world.scenario import validate_scenario, load_scenario_meta
from tavern.world.memory import MemorySystem
from tavern.world.state import StateManager, WorldState
from tavern.engine.story import StoryEngine, load_story_nodes

logger = logging.getLogger(__name__)

_LLM_CONFIG_FIELDS = set(LLMConfig.model_fields.keys())


def _build_llm_config(raw: dict) -> LLMConfig:
    filtered = {k: v for k, v in raw.items() if k in _LLM_CONFIG_FIELDS}
    return LLMConfig(**filtered)


class GameApp:
    def __init__(self, config_path: str | None = None):
        config = self._load_config(config_path)
        llm_config = config.get("llm", {})
        game_config = config.get("game", {})

        if not llm_config:
            raise SystemExit(
                "未找到 LLM 配置。请先运行 `tavern init` 完成初始化配置。"
            )

        raw_scenario = game_config.get("scenario", "tavern")
        scenario_path = Path(raw_scenario)
        if not scenario_path.is_absolute() and not scenario_path.exists():
            from tavern.data import get_bundled_scenario
            scenario_path = get_bundled_scenario(raw_scenario)
        errors = validate_scenario(scenario_path)
        if errors:
            from rich.console import Console
            err_console = Console(stderr=True)
            for e in errors:
                err_console.print(f"[red]✗ {e}[/]")
            raise SystemExit(1)
        self._scenario_meta = load_scenario_meta(scenario_path)
        initial_state = load_scenario(scenario_path)

        self._state_manager = StateManager(
            initial_state=initial_state,
            max_history=game_config.get("undo_history_size", 50),
        )
        vi_mode = game_config.get("vi_mode", False)
        typewriter_effect = game_config.get("typewriter_effect", False)
        self._renderer = Renderer(
            vi_mode=vi_mode,
            typewriter_effect=typewriter_effect,
            state_provider=lambda: self.state,
        )

        intent_raw = llm_config.get("intent", {
            "provider": "openai", "model": "gpt-4o-mini",
        })
        narrative_raw = llm_config.get("narrative", {
            "provider": "openai", "model": "gpt-4o",
        })
        intent_adapter = LLMRegistry.create(_build_llm_config(intent_raw))
        narrative_adapter = LLMRegistry.create(_build_llm_config(narrative_raw))
        self._adapters = [intent_adapter, narrative_adapter]
        llm_service = LLMService(
            intent_adapter=intent_adapter,
            narrative_adapter=narrative_adapter,
        )
        self._parser = IntentParser(llm_service=llm_service)
        self._dialogue_manager = DialogueManager(llm_service=llm_service)
        self._narrator = Narrator(llm_service=llm_service)
        self._llm_service = llm_service
        skills_dir = scenario_path / "skills"
        from tavern.world.memory_extractor import EXTRACTION_RULES, MemoryExtractor
        self._memory = MemorySystem(
            state=initial_state,
            skills_dir=skills_dir if skills_dir.exists() else None,
            extractor=MemoryExtractor(EXTRACTION_RULES),
        )
        self._scenario_path = scenario_path

        from tavern.content.loader import ContentLoader
        content_dir = scenario_path / "content"
        if content_dir.exists():
            content_loader = ContentLoader()
            content_loader.load_directory(content_dir)
        else:
            content_loader = None

        self._game_config = game_config
        saves_dir = Path(game_config.get("saves_dir", "saves"))
        from tavern.world.persistence import SaveManager
        self._save_manager = SaveManager(saves_dir)

        import uuid
        from tavern.engine.game_logger import GameLogger
        log_dir = Path(game_config.get("log_dir", "logs"))
        self._game_logger = GameLogger(
            log_dir=log_dir,
            session_id=str(uuid.uuid4())[:8],
        )

        story_path = scenario_path / "story.yaml"
        self._story_engine = StoryEngine(
            load_story_nodes(story_path) if story_path.exists() else {}
        )

        debug_config = config.get("debug", {})
        log_level = debug_config.get("log_level", "WARNING")
        logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        self._game_loop = bootstrap(
            state_manager=self._state_manager,
            renderer=self._renderer,
            dialogue_manager=self._dialogue_manager,
            narrator=self._narrator,
            memory=self._memory,
            persistence=self._save_manager,
            story_engine=self._story_engine,
            intent_parser=self._parser,
            logger=logger,
            game_logger=self._game_logger,
            content_loader=content_loader,
        )

    @staticmethod
    def _load_config(path: str | None) -> dict:
        if path is not None:
            p = Path(path)
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            return {}

        import os
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        xdg_path = (Path(xdg) if xdg else Path.home() / ".config") / "tavern" / "config.yaml"
        if xdg_path.exists():
            with open(xdg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        local_path = Path("config.yaml")
        if local_path.exists():
            with open(local_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        from tavern.cli import init as _init_mod
        _init_mod.run_init()

        if xdg_path.exists():
            with open(xdg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        from tavern.data import get_bundled_scenarios_dir
        default_path = get_bundled_scenarios_dir().parent / "default_config.yaml"
        if default_path.exists():
            with open(default_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        return {}

    @property
    def state(self) -> WorldState:
        return self._state_manager.current

    @staticmethod
    def _generate_action_hints_from_state(state: WorldState) -> list[str]:
        player = state.characters.get(state.player_id)
        if player is None:
            return ["环顾四周"]

        location = state.locations.get(player.location_id)
        if location is None:
            return ["环顾四周"]

        hints: list[str] = []
        hint_types_used: set[str] = set()

        for npc_id in location.npcs:
            if len(hints) >= 3:
                break
            npc = state.characters.get(npc_id)
            if npc and "talk" not in hint_types_used:
                hints.append(f"和{npc.name}交谈")
                hint_types_used.add("talk")

        for item_id in location.items:
            if len(hints) >= 3:
                break
            item = state.items.get(item_id)
            if item and "inspect" not in hint_types_used:
                hints.append(f"查看{item.name}")
                hint_types_used.add("inspect")

        for direction in location.exits:
            if len(hints) >= 3:
                break
            if "move" not in hint_types_used:
                hints.append(f"前往{direction}")
                hint_types_used.add("move")

        if not hints:
            hints.append("环顾四周")

        return hints[:3]

    def _generate_action_hints(self) -> list[str]:
        return self._generate_action_hints_from_state(self.state)

    async def _generate_smart_hints(self, last_narrative: str = "") -> list[str]:
        state = self.state
        player = state.characters.get(state.player_id)
        if player is None:
            return self._generate_action_hints()

        location = state.locations.get(player.location_id)
        if location is None:
            return self._generate_action_hints()

        npc_names = []
        for npc_id in location.npcs:
            npc = state.characters.get(npc_id)
            if npc:
                npc_names.append(npc.name)

        item_names = []
        for item_id in location.items:
            item = state.items.get(item_id)
            if item:
                item_names.append(item.name)

        exit_dirs = list(location.exits.keys())

        memory_ctx = self._memory.build_context(
            actor=state.player_id,
            state=state,
        )
        recent_events = ""
        if memory_ctx and memory_ctx.recent_events:
            recent_events = f"\n最近事件: {memory_ctx.recent_events}"

        narrative_section = ""
        if last_narrative:
            narrative_section = f"\n刚发生的事: {last_narrative[:200]}"

        prompt = (
            "你是一个奇幻文字冒险游戏的行动建议生成器。\n"
            f"地点: {location.name}\n"
            f"NPC: {', '.join(npc_names) if npc_names else '无'}\n"
            f"物品: {', '.join(item_names) if item_names else '无'}\n"
            f"出口: {', '.join(exit_dirs) if exit_dirs else '无'}"
            f"{recent_events}{narrative_section}\n\n"
            "请生成2-3个当前情境下最合理的行动建议。\n"
            "要求：每个建议必须精简到10个字以内，用动词开头，如：查看旧告示、询问旅行者、前往吧台。\n"
            '以JSON格式回复: {"hints": ["建议1", "建议2", "建议3"]}'
        )

        try:
            hints = await self._llm_service.generate_action_hints(prompt)
            if hints:
                return hints[:3]
        except Exception:
            logger.warning("Smart hints generation failed, falling back to static")

        return self._generate_action_hints()

    async def run(self) -> None:
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
        self._renderer.render_status_bar(self.state)
        try:
            await self._game_loop.run()
        finally:
            self._game_logger.close()
            for adapter in self._adapters:
                if hasattr(adapter, "aclose"):
                    await adapter.aclose()
