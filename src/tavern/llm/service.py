from __future__ import annotations

import json

from tavern.dialogue.context import DialogueResponse
from tavern.llm.adapter import LLMAdapter
from tavern.world.models import ActionRequest

INTENT_SYSTEM_PROMPT = """\
你是一个奇幻文字冒险游戏的意图分析器。根据玩家的输入，分析其意图并返回JSON。

当前场景信息：
- 位置: {location}
- 在场NPC: {npcs}
- 可见物品: {items}
- 可用出口: {exits}

动作类型:
- move: 移动到另一个位置
- look: 观察环境或某个对象
- search: 搜索隐藏物品
- talk: 与NPC对话
- persuade: 说服NPC
- trade: 与NPC交易
- take: 拾取物品
- use: 使用物品
- give: 给予物品
- stealth: 潜行
- combat: 战斗
- custom: 其他（无法归类时使用）

返回JSON格式: {{"action": "<动作类型>", "target": "<目标ID或null>", \
"detail": "<补充描述>", "confidence": <0.0-1.0>}}

示例:
- 输入: "走到吧台那边" -> {{"action": "move", "target": "bar_area", \
"detail": "走向吧台", "confidence": 0.95}}
- 输入: "看看四周有什么" -> {{"action": "look", "target": null, \
"detail": "观察周围环境", "confidence": 0.9}}
- 输入: "捡起那张告示" -> {{"action": "take", "target": "old_notice", \
"detail": "拾取旧告示", "confidence": 0.95}}
- 输入: "和旅行者聊聊" -> {{"action": "talk", "target": "traveler", \
"detail": "与旅行者对话", "confidence": 0.9}}
- 输入: "用钥匙开地下室的门" -> {{"action": "use", "target": "cellar_key", \
"detail": "cellar_door", "confidence": 0.95}}
- 输入: "使用铁盒" -> {{"action": "use", "target": "rusty_box", \
"detail": null, "confidence": 0.9}}
"""


class LLMService:
    def __init__(
        self,
        intent_adapter: LLMAdapter,
        narrative_adapter: LLMAdapter,
    ) -> None:
        self._intent = intent_adapter
        self._narrative = narrative_adapter

    async def classify_intent(
        self,
        player_input: str,
        scene_context: dict,
    ) -> ActionRequest:
        system_msg = INTENT_SYSTEM_PROMPT.format(
            location=scene_context.get("location", "unknown"),
            npcs=", ".join(scene_context.get("npcs", [])) or "无",
            items=", ".join(scene_context.get("items", [])) or "无",
            exits=", ".join(scene_context.get("exits", [])) or "无",
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": player_input},
        ]
        return await self._intent.complete(messages, response_format=ActionRequest)

    async def generate_dialogue(
        self,
        system_prompt: str,
        messages: list[dict],
    ) -> DialogueResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        raw = await self._narrative.complete(full_messages)
        try:
            data = json.loads(raw if isinstance(raw, str) else str(raw))
            trust_delta = max(-5, min(5, int(data.get("trust_delta", 0))))
            return DialogueResponse(
                text=str(data.get("text", "...沉默不语")),
                trust_delta=trust_delta,
                mood=str(data.get("mood", "neutral")),
                wants_to_end=bool(data.get("wants_to_end", False)),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return DialogueResponse(
                text="...沉默不语",
                trust_delta=0,
                mood="neutral",
                wants_to_end=False,
            )

    async def generate_summary(
        self,
        summary_prompt: str,
    ) -> dict:
        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": "请生成摘要。"},
        ]
        raw = await self._intent.complete(messages)
        try:
            return json.loads(raw if isinstance(raw, str) else str(raw))
        except (json.JSONDecodeError, ValueError):
            return {"summary": "进行了一段对话", "key_info": []}

    async def stream_narrative(
        self,
        system_prompt: str,
        action_message: str,
    ):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": action_message},
        ]
        async for chunk in self._narrative.stream(messages):
            yield chunk
