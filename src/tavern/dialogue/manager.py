from __future__ import annotations

from tavern.dialogue.context import (
    DialogueContext,
    DialogueResponse,
    DialogueSummary,
    Message,
)
from tavern.dialogue.prompts import build_dialogue_prompt, build_summary_prompt, resolve_tone
from tavern.llm.service import LLMService
from tavern.world.state import WorldState

MAX_TURNS = 20


class DialogueManager:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service
        self._active: DialogueContext | None = None

    @property
    def is_active(self) -> bool:
        return self._active is not None

    async def start(
        self, state: WorldState, npc_id: str
    ) -> tuple[DialogueContext, DialogueResponse]:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        if npc_id not in state.characters:
            raise ValueError(f"未知角色: {npc_id}")
        if npc_id not in location.npcs:
            raise ValueError(f"{npc_id} 不在当前地点")

        npc = state.characters[npc_id]
        trust = int(npc.stats.get("trust", 0))
        tone = resolve_tone(trust)

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == npc_id
        )

        ctx = DialogueContext(
            npc_id=npc_id,
            npc_name=npc.name,
            npc_traits=npc.traits,
            trust=trust,
            tone=tone,
            messages=(),
            location_id=player.location_id,
            turn_entered=state.turn,
        )

        system_prompt = build_dialogue_prompt(ctx, location.name, history_summaries)
        response = await self._llm.generate_dialogue(system_prompt, messages=[])

        opening_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        new_trust = trust + response.trust_delta
        ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=new_trust,
            tone=resolve_tone(new_trust),
            messages=(opening_msg,),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = ctx
        return ctx, response

    async def respond(
        self, ctx: DialogueContext, player_input: str, state: WorldState
    ) -> tuple[DialogueContext, DialogueResponse]:
        if len(ctx.messages) >= MAX_TURNS:
            response = DialogueResponse(
                text="我觉得我们已经聊了很多了，请让我休息一下。",
                trust_delta=0,
                mood="疲惫",
                wants_to_end=True,
            )
            return ctx, response

        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        history_summaries = tuple(
            e.description
            for e in state.timeline
            if e.type == "dialogue_summary" and e.actor == ctx.npc_id
        )

        system_prompt = build_dialogue_prompt(ctx, location.name, history_summaries)

        llm_messages = [
            {
                "role": "user" if m.role == "player" else "assistant",
                "content": m.content,
            }
            for m in ctx.messages
        ]
        llm_messages.append({"role": "user", "content": player_input})

        response = await self._llm.generate_dialogue(system_prompt, llm_messages)

        player_msg = Message(
            role="player", content=player_input, trust_delta=0, turn=state.turn
        )
        npc_msg = Message(
            role="npc",
            content=response.text,
            trust_delta=response.trust_delta,
            turn=state.turn,
        )
        new_trust = ctx.trust + response.trust_delta
        new_ctx = DialogueContext(
            npc_id=ctx.npc_id,
            npc_name=ctx.npc_name,
            npc_traits=ctx.npc_traits,
            trust=new_trust,
            tone=resolve_tone(new_trust),
            messages=ctx.messages + (player_msg, npc_msg),
            location_id=ctx.location_id,
            turn_entered=ctx.turn_entered,
        )

        self._active = new_ctx
        return new_ctx, response

    async def end(self, ctx: DialogueContext) -> DialogueSummary:
        llm_messages = [
            {
                "role": "user" if m.role == "player" else "assistant",
                "content": m.content,
            }
            for m in ctx.messages
        ]

        summary_prompt = build_summary_prompt(ctx.npc_name, llm_messages)
        summary_data = await self._llm.generate_summary(summary_prompt)

        total_trust_delta = sum(m.trust_delta for m in ctx.messages)

        self._active = None
        return DialogueSummary(
            npc_id=ctx.npc_id,
            summary_text=summary_data.get("summary", f"与{ctx.npc_name}进行了对话"),
            total_trust_delta=total_trust_delta,
            key_info=tuple(summary_data.get("key_info", [])),
            turns_count=len(ctx.messages),
        )
