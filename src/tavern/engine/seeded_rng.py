from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any


class SeededRNG:
    """Mulberry32 deterministic pseudo-random number generator."""

    __slots__ = ("_state",)

    def __init__(self, seed: int):
        self._state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self._state = (self._state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 0x100000000

    def choice(self, options: list[Any]) -> Any:
        if not options:
            raise ValueError("Cannot choose from empty list")
        return options[int(self.next() * len(options))]

    def weighted_choice(self, options: list[tuple[Any, float]]) -> Any:
        if not options:
            raise ValueError("Cannot choose from empty list")
        total = sum(w for _, w in options)
        r = self.next() * total
        cumulative = 0.0
        for item, weight in options:
            cumulative += weight
            if r < cumulative:
                return item
        return options[-1][0]


def make_seed(location_id: str, turn: int, salt: str = "") -> int:
    raw = f"{location_id}\x00{turn}\x00{salt}"
    digest = hashlib.md5(raw.encode()).digest()
    return struct.unpack("<I", digest[:4])[0]


@dataclass(frozen=True)
class AmbienceDetails:
    weather: str
    crowd_level: str
    background_sound: str
    smell: str


_WEATHER_OPTIONS = ["晴朗", "阴沉", "微雨", "大雾"]
_CROWD_OPTIONS = ["冷清", "稍有人气", "热闹", "拥挤"]
_SOUND_OPTIONS = [
    "远处传来马蹄声",
    "炉火噼啪作响",
    "窗外有鸟鸣",
    "隔壁桌传来笑声",
]
_SMELL_OPTIONS = [
    "烤面包的香气",
    "潮湿木头的味道",
    "麦酒的醇厚气息",
    "草药的淡淡清香",
]


def generate_ambience(location_id: str, turn: int) -> AmbienceDetails:
    rng = SeededRNG(make_seed(location_id, turn, "ambience"))
    return AmbienceDetails(
        weather=rng.choice(_WEATHER_OPTIONS),
        crowd_level=rng.choice(_CROWD_OPTIONS),
        background_sound=rng.choice(_SOUND_OPTIONS),
        smell=rng.choice(_SMELL_OPTIONS),
    )


def generate_npc_appearance(npc_id: str) -> dict[str, str | None]:
    rng = SeededRNG(make_seed(npc_id, 0, "appearance"))
    return {
        "scar": rng.choice([None, "左颊", "额头", "下巴"]),
        "hair_detail": rng.choice(["凌乱", "整齐梳理", "扎成马尾", "半遮面"]),
        "clothing_condition": rng.choice(["整洁", "略显陈旧", "满是尘土", "有修补痕迹"]),
    }


def should_trigger_random_event(location_id: str, turn: int) -> bool:
    rng = SeededRNG(make_seed(location_id, turn, "event"))
    return rng.next() < 0.15
