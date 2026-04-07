from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


@dataclass(frozen=True)
class ActivationCondition:
    type: str  # "relationship" | "event" | "quest" | "inventory"
    source: str | None = None
    target: str | None = None
    attribute: str | None = None
    operator: str | None = None
    value: int | None = None
    event_id: str | None = None
    check: str | None = None


@dataclass(frozen=True)
class Skill:
    id: str
    character: str
    priority: str  # "high" | "normal" | "low"
    activation: tuple[ActivationCondition, ...]
    facts: tuple[str, ...]
    behavior: MappingProxyType


class ConditionEvaluator:
    @staticmethod
    def evaluate(
        cond: ActivationCondition,
        state: WorldState,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
    ) -> bool:
        if cond.type == "relationship":
            return ConditionEvaluator._eval_relationship(cond, relationships)
        if cond.type == "event":
            return ConditionEvaluator._eval_event(cond, timeline)
        if cond.type == "quest":
            return ConditionEvaluator._eval_quest(cond, state)
        if cond.type == "inventory":
            return ConditionEvaluator._eval_inventory(cond, state)
        logger.warning("ConditionEvaluator: unknown condition type %r", cond.type)
        return False

    @staticmethod
    def _eval_relationship(
        cond: ActivationCondition, relationships: RelationshipGraph
    ) -> bool:
        if cond.source is None or cond.target is None or cond.operator is None or cond.value is None:
            return False
        rel = relationships.get(cond.source, cond.target)
        v = rel.value
        t = cond.value
        op = cond.operator
        if op == "==":
            return v == t
        if op == "!=":
            return v != t
        if op == ">":
            return v > t
        if op == "<":
            return v < t
        if op == ">=":
            return v >= t
        if op == "<=":
            return v <= t
        return False

    @staticmethod
    def _eval_event(cond: ActivationCondition, timeline: EventTimeline) -> bool:
        if cond.event_id is None:
            return False
        exists = timeline.has(cond.event_id)
        if cond.check == "exists":
            return exists
        if cond.check == "not_exists":
            return not exists
        return False

    @staticmethod
    def _eval_quest(cond: ActivationCondition, state: WorldState) -> bool:
        if cond.event_id is None or cond.check is None:
            return False
        quest = state.quests.get(cond.event_id, {})
        return quest.get("status") == cond.check

    @staticmethod
    def _eval_inventory(cond: ActivationCondition, state: WorldState) -> bool:
        if cond.event_id is None:
            return False
        player = state.characters.get(state.player_id)
        if player is None:
            return False
        return cond.event_id in player.inventory


class SkillManager:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def load_skills(self, scenario_path: Path) -> None:
        for yaml_file in sorted(scenario_path.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or "id" not in raw:
                    logger.warning("SkillManager: skipping %s (not a valid skill dict)", yaml_file)
                    continue
                conditions = tuple(
                    ActivationCondition(**c) for c in (raw.get("activation") or [])
                )
                skill = Skill(
                    id=raw["id"],
                    character=raw.get("character", ""),
                    priority=raw.get("priority", "normal"),
                    activation=conditions,
                    facts=tuple(raw.get("facts") or []),
                    behavior=MappingProxyType(dict(raw.get("behavior") or {})),
                )
                self._skills[skill.id] = skill
            except Exception as exc:
                logger.warning("SkillManager: failed to load %s: %s", yaml_file, exc)

    def get_active_skills(
        self,
        char_id: str,
        state: WorldState,
        timeline: EventTimeline,
        relationships: RelationshipGraph,
    ) -> list[Skill]:
        result = []
        for skill in self._skills.values():
            if skill.character != char_id:
                continue
            if all(
                ConditionEvaluator.evaluate(cond, state, timeline, relationships)
                for cond in skill.activation
            ):
                result.append(skill)
        result.sort(key=lambda s: _PRIORITY_ORDER.get(s.priority, 1))
        return result

    def inject_to_prompt(self, skills: list[Skill], max_chars: int = 800) -> str:
        if not skills:
            return ""
        parts: list[str] = []
        total = 0
        for skill in skills:
            lines = list(skill.facts) + [
                f"{k}: {v}" for k, v in skill.behavior.items()
            ]
            chunk = "\n".join(lines)
            if total > 0 and total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)
