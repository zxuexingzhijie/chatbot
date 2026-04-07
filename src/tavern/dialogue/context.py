from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    role: str           # "player" | "npc"
    content: str
    trust_delta: int    # delta for this turn (player messages are always 0)
    turn: int


@dataclass(frozen=True)
class DialogueContext:
    npc_id: str
    npc_name: str
    npc_traits: tuple[str, ...]
    trust: int
    tone: str           # "hostile" | "neutral" | "friendly"
    messages: tuple[Message, ...]
    location_id: str
    turn_entered: int


@dataclass(frozen=True)
class DialogueResponse:
    text: str
    trust_delta: int
    mood: str
    wants_to_end: bool


@dataclass(frozen=True)
class DialogueSummary:
    npc_id: str
    summary_text: str
    total_trust_delta: int
    key_info: tuple[str, ...]
    turns_count: int
