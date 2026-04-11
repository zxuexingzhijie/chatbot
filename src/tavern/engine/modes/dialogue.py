from __future__ import annotations

from typing import TYPE_CHECKING

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

_BYE_PHRASES = frozenset({"bye", "leave", "再见", "离开", "结束对话"})


class DialogueModeHandler:
    def __init__(self, dialogue_manager) -> None:
        self._dm = dialogue_manager

    @property
    def mode(self) -> GameMode:
        return GameMode.DIALOGUE

    async def handle_input(
        self,
        raw: str,
        state: WorldState,
        context: ModeContext,
    ) -> TransitionResult:
        stripped = raw.strip()

        if stripped.startswith("/"):
            await context.command_registry.handle_command(
                stripped, self.mode, context,
            )
            return TransitionResult()

        if not stripped:
            return TransitionResult()

        if stripped == "\x1b":
            return await self._end_dialogue(state, context)

        active_ctx = self._dm._active
        if active_ctx is None:
            await context.renderer.render_error("没有进行中的对话")
            return TransitionResult(next_mode=GameMode.EXPLORING)

        if stripped.lower() in _BYE_PHRASES:
            return await self._end_dialogue(state, context)

        memory_ctx = context.memory.build_context(actor=active_ctx.npc_id, state=state)
        new_ctx, response = await self._dm.respond(active_ctx, stripped, state, memory_ctx)
        await context.renderer.render_dialogue_with_typewriter(active_ctx.npc_name, response)

        effects: list[SideEffect] = []
        if response.trust_delta != 0:
            effects.append(SideEffect(
                kind=EffectKind.APPLY_TRUST,
                payload={"npc_id": active_ctx.npc_id, "delta": response.trust_delta},
            ))

        if response.wants_to_end:
            summary = await self._dm.end(new_ctx)
            context.renderer.render_dialogue_end(summary)
            effects.append(SideEffect(
                kind=EffectKind.END_DIALOGUE,
                payload={"npc_id": active_ctx.npc_id},
            ))
            return TransitionResult(next_mode=GameMode.EXPLORING, side_effects=tuple(effects))

        return TransitionResult(side_effects=tuple(effects))

    async def _end_dialogue(self, state: WorldState, context: ModeContext) -> TransitionResult:
        active_ctx = self._dm._active
        npc_id = active_ctx.npc_id if active_ctx else "unknown"
        if active_ctx is not None:
            summary = await self._dm.end(active_ctx)
            context.renderer.render_dialogue_end(summary)
        return TransitionResult(
            next_mode=GameMode.EXPLORING,
            side_effects=(SideEffect(kind=EffectKind.END_DIALOGUE, payload={"npc_id": npc_id}),),
        )

    def get_prompt_config(self, state: WorldState) -> PromptConfig:
        return PromptConfig(prompt_text="对话> ", show_status_bar=False)

    def get_keybindings(self) -> list[Keybinding]:
        return [
            Keybinding("1", "select_hint_1", "选择提示1", allow_in_text=True),
            Keybinding("2", "select_hint_2", "选择提示2", allow_in_text=True),
            Keybinding("3", "select_hint_3", "选择提示3", allow_in_text=True),
            Keybinding("escape", "end_dialogue", "结束对话", allow_in_text=True),
        ]
