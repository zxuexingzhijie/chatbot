from __future__ import annotations

import logging
from pathlib import Path

import yaml

import uuid

from tavern.cli.renderer import Renderer
from tavern.dialogue.context import DialogueContext
from tavern.dialogue.manager import DialogueManager
from tavern.narrator.narrator import Narrator
from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.service import LLMService
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
from tavern.world.scenario import validate_scenario, load_scenario_meta
from tavern.world.memory import MemorySystem
from tavern.world.models import ActionRequest, ActionResult, Event
from tavern.world.state import StateManager, StateDiff, WorldState
from tavern.engine.story import StoryEngine, StoryResult, load_story_nodes

logger = logging.getLogger(__name__)

SYSTEM_COMMANDS = {"look", "inventory", "status", "hint", "undo", "help", "quit", "save", "load", "saves", "continue"}

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
        self._rules = RulesEngine()
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
        llm_service = LLMService(
            intent_adapter=intent_adapter,
            narrative_adapter=narrative_adapter,
        )
        self._parser = IntentParser(llm_service=llm_service)
        self._dialogue_manager = DialogueManager(llm_service=llm_service)
        self._narrator = Narrator(llm_service=llm_service)
        skills_dir = scenario_path / "skills"
        self._memory = MemorySystem(
            state=initial_state,
            skills_dir=skills_dir if skills_dir.exists() else None,
        )
        self._dialogue_ctx: DialogueContext | None = None
        self._scenario_path = scenario_path
        self._game_config = game_config
        saves_dir = Path(game_config.get("saves_dir", "saves"))
        from tavern.world.persistence import SaveManager
        self._save_manager = SaveManager(saves_dir)

        story_path = scenario_path / "story.yaml"
        self._story_engine = StoryEngine(
            load_story_nodes(story_path) if story_path.exists() else {}
        )
        self._pending_story_hints: list[str] = []
        self._ending_triggered: tuple[str, str] | None = None
        self._game_over = False
        self._last_hints: list[str] = []

        debug_config = config.get("debug", {})
        self._show_intent = debug_config.get("show_intent_json", False)
        log_level = debug_config.get("log_level", "WARNING")
        logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

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

    async def run(self) -> None:
        self._renderer.render_welcome(self.state, self._scenario_meta.name)
        self._renderer.render_status_bar(self.state)

        while not self._game_over:
            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                user_input = await self._renderer.get_dialogue_input()
            else:
                user_input = await self._renderer.get_input()

            if not user_input:
                continue

            if (
                user_input in ("1", "2", "3")
                and self._last_hints
                and not (self._dialogue_manager.is_active and self._dialogue_ctx is not None)
            ):
                idx = int(user_input) - 1
                if 0 <= idx < len(self._last_hints):
                    user_input = self._last_hints[idx]

            command = user_input.lower().strip()

            if command == "/quit":
                self._renderer.console.print("\n[dim]再见，冒险者。[/]\n")
                break

            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                await self._process_dialogue_input(user_input, self._dialogue_ctx)
                continue

            if not command.startswith("/"):
                await self._handle_free_input(user_input)
                continue

            parts = command[1:].split()
            cmd_name = parts[0] if parts else ""
            slot_arg = parts[1] if len(parts) > 1 else "autosave"

            if cmd_name in SYSTEM_COMMANDS:
                await self._handle_system_command(cmd_name, slot_arg)
            else:
                self._renderer.console.print(
                    f"\n[red]未知命令: /{cmd_name}[/]  输入 [cyan]/help[/] 查看可用命令。\n"
                )

    async def _handle_system_command(self, command: str, slot: str = "autosave") -> None:
        if command == "look":
            request = ActionRequest(action=ActionType.LOOK)
            result, _ = self._rules.validate(request, self.state)
            self._renderer.render_result(result)

        elif command == "inventory":
            self._renderer.render_inventory(self.state)

        elif command == "status":
            relationships = self._memory.get_player_relationships(self.state.player_id)
            self._renderer.render_status(self.state, relationships)

        elif command == "hint":
            self._renderer.console.print(
                "\n[dim italic]尝试和酒馆里的人聊聊天，也许能发现什么线索...[/]\n"
            )

        elif command == "undo":
            try:
                self._state_manager.undo()
                self._renderer.console.print("\n[dim]已回退上一步。[/]\n")
                request = ActionRequest(action=ActionType.LOOK)
                result, _ = self._rules.validate(request, self.state)
                self._renderer.render_result(result)
            except IndexError:
                self._renderer.console.print("\n[red]没有可以回退的步骤。[/]\n")

        elif command == "continue":
            story_results = self._story_engine.check(
                self.state, "continue",
                self._memory._timeline, self._memory._relationship_graph,
            )
            if not story_results:
                self._renderer.console.print("\n[dim]目前没有新的剧情推进。[/]\n")
            else:
                self._apply_story_results_sync(story_results)
                if self._ending_triggered is not None:
                    ending_id, ending_hint = self._ending_triggered
                    memory_ctx = self._memory.build_context(
                        actor=self.state.player_id,
                        state=self.state,
                    )
                    await self._renderer.render_stream(
                        self._narrator.stream_ending_narrative(
                            ending_id, ending_hint, self.state, memory_ctx,
                        )
                    )
                    self._renderer.render_ending(ending_id)
                    self._game_over = True
            self._update_story_active_since()

        elif command == "help":
            self._renderer.render_help()

        elif command == "save":
            try:
                new_state = self._memory.sync_to_state(self.state)
                path = self._save_manager.save(new_state, slot)
                self._renderer.render_save_success(slot, path)
            except OSError as e:
                self._renderer.console.print(f"\n[red]存档失败：{e}[/]\n")

        elif command == "saves":
            saves = self._save_manager.list_saves()
            self._renderer.render_saves_list(saves)

        elif command == "load":
            if self._dialogue_manager.is_active:
                self._renderer.console.print("\n[red]请先结束当前对话再加载存档。[/]\n")
            else:
                try:
                    loaded_state, timestamp = self._save_manager.load(slot)
                    self._state_manager = StateManager(
                        initial_state=loaded_state,
                        max_history=self._game_config.get("undo_history_size", 50),
                    )
                    skills_dir = self._scenario_path / "skills"
                    self._memory = MemorySystem(
                        state=loaded_state,
                        skills_dir=skills_dir if skills_dir.exists() else None,
                    )
                    self._dialogue_ctx = None
                    self._renderer.render_load_success(slot, timestamp)
                except (FileNotFoundError, ValueError) as e:
                    self._renderer.console.print(f"\n[red]{e}[/]\n")

        self._renderer.render_status_bar(self.state)

    async def _handle_free_input(self, user_input: str) -> None:
        player = self.state.characters[self.state.player_id]
        location = self.state.locations[player.location_id]

        async with self._renderer.spinner("理解中..."):
            request = await self._parser.parse(
                user_input,
                location_id=player.location_id,
                npcs=list(location.npcs),
                items=list(location.items),
                exits=list(location.exits.keys()),
            )

        if self._show_intent:
            self._renderer.console.print(
                f"[dim]Intent: {request.model_dump_json()}[/]"
            )

        if request.is_fallback:
            self._renderer.console.print("[dim]（未能完全理解你的意图，尝试自由行动...）[/]")

        result, diff = self._rules.validate(request, self.state)

        if diff is not None:
            self._state_manager.commit(diff, result)
            self._memory.apply_diff(diff, self.state)
            if result.success and request.action not in (ActionType.TALK, ActionType.PERSUADE):
                try:
                    new_state = self._memory.sync_to_state(self.state)
                    self._save_manager.save(new_state, "autosave")
                except OSError as e:
                    logger.warning("autosave failed: %s", e)

        if result.success and request.action in (
            ActionType.TALK, ActionType.PERSUADE
        ) and result.target:
            self._update_story_active_since()
            try:
                memory_ctx = self._memory.build_context(
                    actor=result.target,
                    state=self.state,
                )
                ctx, opening_response = await self._dialogue_manager.start(
                    self.state, result.target,
                    is_persuade=(request.action == ActionType.PERSUADE),
                    memory_ctx=memory_ctx,
                )
                self._dialogue_ctx = ctx
                self._renderer.render_dialogue_start(ctx, opening_response)
                self._renderer.render_status_bar(self.state)
                return
            except ValueError as e:
                self._renderer.console.print(f"\n[red]{e}[/]\n")
                return

        if result.success and not self._dialogue_manager.is_active:
            story_results = self._story_engine.check(
                self.state, "passive",
                self._memory._timeline, self._memory._relationship_graph,
            )
            story_results += self._story_engine.check_fail_forward(self.state)
            await self._apply_story_results(story_results)
            self._update_story_active_since()

            if self._ending_triggered is not None:
                ending_id, ending_hint = self._ending_triggered
                memory_ctx = self._memory.build_context(
                    actor=self.state.player_id,
                    state=self.state,
                )
                await self._renderer.render_stream(
                    self._narrator.stream_ending_narrative(
                        ending_id, ending_hint, self.state, memory_ctx,
                    ),
                    atmosphere=location.atmosphere,
                )
                self._renderer.render_ending(ending_id)
                self._game_over = True
                return

            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
            )
            combined_hint = "\n".join(self._pending_story_hints) or None
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint),
                atmosphere=location.atmosphere,
            )
        else:
            self._renderer.render_result(result)
        self._pending_story_hints.clear()
        self._last_hints = self._generate_action_hints()
        self._renderer.render_action_hints(self._last_hints)
        self._renderer.render_status_bar(self.state)

    async def _process_dialogue_input(
        self, user_input: str, ctx: DialogueContext
    ) -> None:
        bye_phrases = {"bye", "leave", "再见", "离开", "结束对话"}
        if user_input.lower().strip() in bye_phrases:
            summary = await self._dialogue_manager.end(ctx)
            self._dialogue_ctx = None
            self._renderer.render_dialogue_end(summary)
            self._apply_dialogue_end(summary)
            self._renderer.render_status_bar(self.state)
            return

        memory_ctx = self._memory.build_context(
            actor=ctx.npc_id,
            state=self.state,
        )
        async with self._renderer.spinner("思考中..."):
            new_ctx, response = await self._dialogue_manager.respond(
                ctx, user_input, self.state, memory_ctx
            )
        self._dialogue_ctx = new_ctx
        self._renderer.render_dialogue(response)

        if response.wants_to_end:
            summary = await self._dialogue_manager.end(new_ctx)
            self._dialogue_ctx = None
            self._renderer.render_dialogue_end(summary)
            self._apply_dialogue_end(summary)
            self._renderer.render_status_bar(self.state)

    def _apply_dialogue_end(self, summary) -> None:
        state = self.state
        npc = state.characters.get(summary.npc_id)
        if npc is not None:
            old_trust = int(npc.stats.get("trust", 0))
            new_trust = max(-100, min(100, old_trust + summary.total_trust_delta))
            new_stats = {**dict(npc.stats), "trust": new_trust}
            trust_diff = StateDiff(
                updated_characters={summary.npc_id: {"stats": new_stats}},
                relationship_changes=(
                    {"src": state.player_id, "tgt": summary.npc_id, "delta": summary.total_trust_delta},
                ),
                turn_increment=0,
            )
            self._state_manager.commit(
                trust_diff,
                ActionResult(
                    success=True,
                    action=ActionType.TALK,
                    message=f"与{npc.name}的对话结束",
                    target=summary.npc_id,
                ),
            )
            self._memory.apply_diff(trust_diff, self.state)
        else:
            logger.warning("_apply_dialogue_end: NPC %s not found in state, skipping trust update", summary.npc_id)

        event = Event(
            id=f"dialogue_{summary.npc_id}_{uuid.uuid4().hex[:8]}",
            turn=self.state.turn,
            type="dialogue_summary",
            actor=summary.npc_id,
            description=summary.summary_text,
            consequences=summary.key_info,
        )
        talked_event = Event(
            id=f"talked_to_{summary.npc_id}",
            turn=self.state.turn,
            type="dialogue_trigger",
            actor=summary.npc_id,
            description=f"与{npc.name if npc else summary.npc_id}进行了对话",
        )
        extra_events: list[Event] = [talked_event]

        _KEY_INFO_EVENT_KEYWORDS = {
            "letter": f"talked_to_{summary.npc_id}_about_letter",
            "信件": f"talked_to_{summary.npc_id}_about_letter",
        }
        seen_event_ids: set[str] = set()
        for info in (summary.key_info or ()):
            info_lower = info.lower()
            for keyword, event_id in _KEY_INFO_EVENT_KEYWORDS.items():
                if keyword in info_lower and event_id not in seen_event_ids:
                    seen_event_ids.add(event_id)
                    extra_events.append(Event(
                        id=event_id,
                        turn=self.state.turn,
                        type="dialogue_topic",
                        actor=summary.npc_id,
                        description=info,
                    ))

        event_diff = StateDiff(new_events=(event, *extra_events), turn_increment=0)
        self._state_manager.commit(
            event_diff,
            ActionResult(
                success=True,
                action=ActionType.TALK,
                message="对话摘要已记录",
                target=summary.npc_id,
            ),
        )
        self._memory.apply_diff(event_diff, self.state)
        try:
            new_state = self._memory.sync_to_state(self.state)
            self._save_manager.save(new_state, "autosave")
        except OSError as e:
            logger.warning("autosave failed: %s", e)

    async def _apply_story_results(self, results: list[StoryResult]) -> None:
        self._apply_story_results_sync(results)

    def _apply_story_results_sync(self, results: list[StoryResult]) -> None:
        for r in results:
            self._state_manager.commit(
                r.diff,
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message=f"剧情节点触发：{r.node_id}",
                ),
            )
            self._memory.apply_diff(r.diff, self.state)
            if r.narrator_hint:
                self._pending_story_hints.append(r.narrator_hint)
            if r.diff.new_endings:
                self._ending_triggered = (r.diff.new_endings[0], r.narrator_hint or "")
                break

    def _update_story_active_since(self) -> None:
        new_active = self._story_engine.get_active_nodes(self.state)
        since_updates = {
            nid: self.state.turn
            for nid in new_active
            if nid not in self.state.story_active_since
        }
        if since_updates:
            diff = StateDiff(story_active_since_updates=since_updates, turn_increment=0)
            self._state_manager.commit(
                diff,
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message="故事进度更新",
                ),
            )
            self._memory.apply_diff(diff, self.state)
