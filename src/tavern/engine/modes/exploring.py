from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    Keybinding,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)

if TYPE_CHECKING:
    from tavern.world.state import WorldState


class ExploringModeHandler:
    @property
    def mode(self) -> GameMode:
        return GameMode.EXPLORING

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()
        if not stripped:
            return TransitionResult()

        if stripped.startswith("/"):
            handled = await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            if not handled:
                await context.renderer.render_error(
                    f"未知命令: {stripped.split()[0]}"
                )
            return TransitionResult()

        return await self._handle_free_text(stripped, state, context)

    async def _handle_free_text(
        self, text: str, state: WorldState, context: ModeContext,
    ) -> TransitionResult:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        request = await context.intent_parser.parse(
            text,
            location_id=player.location_id,
            npcs=list(location.npcs),
            items=list(location.items),
            exits=list(location.exits.keys()),
            state=state,
        )

        result, diff = context.action_registry.validate_and_execute(request, state)

        if not result.success:
            context.renderer.render_result(result)
            return TransitionResult()

        effects: list[SideEffect] = []

        if diff is not None:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": diff, "action": result},
            ))

        is_talk = request.action in (ActionType.TALK, ActionType.PERSUADE)
        if is_talk and result.target:
            effects.append(SideEffect(
                kind=EffectKind.START_DIALOGUE,
                payload={"npc_id": result.target},
            ))

        memory_ctx = context.memory.build_context(
            actor=result.target or state.player_id,
            state=state,
        )
        narrative_stream = context.narrator.stream_narrative(result, state, memory_ctx)
        await context.renderer.render_stream(
            narrative_stream, atmosphere=location.atmosphere,
        )

        story_results = []
        if hasattr(context.story_engine, "check"):
            story_results = context.story_engine.check(
                state,
                "passive",
                context.memory.timeline if hasattr(context.memory, "timeline") else (),
                context.memory.relationship_graph if hasattr(context.memory, "relationship_graph") else {},
            ) or []
        for sr in story_results:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": sr.diff, "action": None},
            ))

        context.renderer.render_status_bar(state)

        next_mode = GameMode.DIALOGUE if (is_talk and result.target) else None
        return TransitionResult(next_mode=next_mode, side_effects=tuple(effects))

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="> ", show_status_bar=True)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("n", "move_north", "向北移动"),
            Keybinding("s", "move_south", "向南移动"),
            Keybinding("e", "move_east", "向东移动"),
            Keybinding("w", "move_west", "向西移动"),
            Keybinding("l", "look_around", "查看四周"),
            Keybinding("i", "open_inventory", "打开背包"),
            Keybinding("t", "talk_nearest", "与最近的NPC交谈"),
            Keybinding("?", "show_help", "显示帮助"),
        ]
