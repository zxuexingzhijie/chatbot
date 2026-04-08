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
from tavern.llm.openai_llm import OpenAIAdapter  # noqa: F401 — triggers registration
from tavern.llm.service import LLMService
from tavern.parser.intent import IntentParser
from tavern.world.loader import load_scenario
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
    def __init__(self, config_path: str = "config.yaml"):
        config = self._load_config(config_path)
        llm_config = config.get("llm", {})
        game_config = config.get("game", {})

        scenario_path = Path(game_config.get("scenario", "data/scenarios/tavern"))
        initial_state = load_scenario(scenario_path)

        self._state_manager = StateManager(
            initial_state=initial_state,
            max_history=game_config.get("undo_history_size", 50),
        )
        self._rules = RulesEngine()
        self._renderer = Renderer()

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

        debug_config = config.get("debug", {})
        self._show_intent = debug_config.get("show_intent_json", False)
        log_level = debug_config.get("log_level", "INFO")
        logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

    @staticmethod
    def _load_config(path: str) -> dict:
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @property
    def state(self) -> WorldState:
        return self._state_manager.current

    async def run(self) -> None:
        self._renderer.render_welcome(self.state)
        self._renderer.render_status_bar(self.state)

        while True:
            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                user_input = self._renderer.get_dialogue_input()
            else:
                user_input = self._renderer.get_input()

            if not user_input:
                continue

            command = user_input.lower().strip()

            if command == "quit":
                self._renderer.console.print("\n[dim]再见，冒险者。[/]\n")
                break

            if self._dialogue_manager.is_active and self._dialogue_ctx is not None:
                await self._process_dialogue_input(user_input, self._dialogue_ctx)
                continue

            parts = user_input.strip().split()
            first_word = parts[0].lower() if parts else ""
            slot_arg = parts[1] if len(parts) > 1 else "autosave"

            if first_word in SYSTEM_COMMANDS:
                self._handle_system_command(first_word, slot_arg)
                continue

            await self._handle_free_input(user_input)

    def _handle_system_command(self, command: str, slot: str = "autosave") -> None:
        if command == "look":
            request = ActionRequest(action=ActionType.LOOK)
            result, _ = self._rules.validate(request, self.state)
            self._renderer.render_result(result)

        elif command == "inventory":
            self._renderer.render_inventory(self.state)

        elif command == "status":
            self._renderer.render_status(self.state)

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

            memory_ctx = self._memory.build_context(
                actor=result.target or self.state.player_id,
                state=self.state,
            )
            combined_hint = "\n".join(self._pending_story_hints) or None
            await self._renderer.render_stream(
                self._narrator.stream_narrative(result, self.state, memory_ctx, story_hint=combined_hint)
            )
        else:
            self._renderer.render_result(result)
        self._pending_story_hints.clear()
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
                    {"src": summary.npc_id, "tgt": state.player_id, "delta": summary.total_trust_delta},
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
        event_diff = StateDiff(new_events=(event,), turn_increment=0)
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

    def _update_story_active_since(self) -> None:
        new_active = self._story_engine.get_active_nodes(self.state)
        since_updates = {
            nid: self.state.turn
            for nid in new_active
            if nid not in self.state.story_active_since
        }
        if since_updates:
            self._state_manager.commit(
                StateDiff(story_active_since_updates=since_updates, turn_increment=0),
                ActionResult(
                    success=True,
                    action=ActionType.CUSTOM,
                    message="故事进度更新",
                ),
            )
