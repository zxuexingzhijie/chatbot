from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.engine.fsm import (
    EffectKind,
    GameMode,
    ModeContext,
    PromptConfig,
    SideEffect,
    TransitionResult,
)
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from tavern.world.state import WorldState


def _find_abandoned_quests(state: "WorldState", threshold: int = 20) -> dict[str, dict]:
    updates: dict[str, dict] = {}
    for quest_id, quest in state.quests.items():
        if quest.get("status") != "active":
            continue
        activated_at = quest.get("activated_at")
        if activated_at is None:
            continue
        if state.turn - activated_at >= threshold:
            updates[quest_id] = {"status": "abandoned"}
    return updates


_ABANDON_THRESHOLD = 20
_WARN_BEFORE = 5


def _find_expiring_quests(state: "WorldState") -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for quest_id, quest in state.quests.items():
        if quest.get("status") != "active":
            continue
        activated_at = quest.get("activated_at")
        if activated_at is None:
            continue
        elapsed = state.turn - activated_at
        remaining = _ABANDON_THRESHOLD - elapsed
        if 0 < remaining <= _WARN_BEFORE:
            results.append((quest_id, remaining))
    return results


def _render_expiry_warnings(state: "WorldState", context: ModeContext) -> None:
    from tavern.engine.quest_descriptions import (
        get_quest_display_name,
        get_quest_status_description,
    )
    renderer = context.renderer
    if not hasattr(renderer, "render_quest_expiry_warning"):
        return
    for quest_id, remaining in _find_expiring_quests(state):
        display_name = get_quest_display_name(quest_id)
        desc = get_quest_status_description(quest_id, "active")
        renderer.render_quest_expiry_warning(display_name, remaining, desc)


_ONBOARDING_HINTS: dict[int, str] = {
    1: "试试和酒馆里的人聊天（如'和酒保说话'），建立信任可以解锁更多故事",
    2: "输入 /status 查看角色状态和人际关系，输入 /inventory 查看背包",
}


def _render_onboarding_hint(state: "WorldState", context: ModeContext) -> None:
    renderer = context.renderer
    if not hasattr(renderer, "render_onboarding_hint"):
        return
    hint = _ONBOARDING_HINTS.get(state.turn)
    if hint is not None:
        renderer.render_onboarding_hint(hint)


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

        status = context.renderer.start_thinking_status()

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
            status.stop()
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

        post_state = state.apply(diff) if diff is not None else state

        memory_ctx = context.memory.build_context(
            actor=result.target or post_state.player_id,
            state=post_state,
        )
        narrative_stream = context.narrator.stream_narrative(result, post_state, memory_ctx)
        await context.renderer.render_stream(
            narrative_stream, atmosphere=location.atmosphere, pending_status=status,
        )

        _render_expiry_warnings(post_state, context)

        abandon_updates = _find_abandoned_quests(post_state, threshold=_ABANDON_THRESHOLD)
        if abandon_updates:
            abandon_diff = StateDiff(
                quest_updates=abandon_updates, turn_increment=0,
            )
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": abandon_diff, "action": None},
            ))
            post_state = post_state.apply(abandon_diff)

        story_results = []
        if hasattr(context.story_engine, "check"):
            story_results = context.story_engine.check(
                post_state,
                "passive",
                context.memory.timeline if hasattr(context.memory, "timeline") else (),
                context.memory.relationship_graph if hasattr(context.memory, "relationship_graph") else {},
            ) or []
        for sr in story_results:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_DIFF,
                payload={"diff": sr.diff, "action": None},
            ))

        context.renderer.render_status_bar(post_state)

        _render_onboarding_hint(post_state, context)

        next_mode = GameMode.DIALOGUE if (is_talk and result.target) else None
        return TransitionResult(next_mode=next_mode, side_effects=tuple(effects))

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="> ")

