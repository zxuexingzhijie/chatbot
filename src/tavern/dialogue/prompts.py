from __future__ import annotations

from tavern.dialogue.context import DialogueContext

TONE_TEMPLATES: dict[str, str] = {
    "hostile": (
        "你对玩家持有敌意或强烈不信任。回答简短冷淡，不主动提供任何信息。"
        "若玩家继续骚扰，你会明确表示想结束对话。"
    ),
    "neutral": (
        "你对玩家态度中立。回答基本问题，但不会主动分享秘密或隐私。"
        "保持礼貌但有距离感。"
    ),
    "friendly": (
        "你对玩家非常友好，热情健谈。愿意分享你知道的信息，包括秘密和线索。"
        "乐于帮助玩家。"
    ),
}


def resolve_tone(trust: int) -> str:
    if trust <= -20:
        return "hostile"
    if trust >= 20:
        return "friendly"
    return "neutral"


def build_dialogue_prompt(
    ctx: DialogueContext,
    location_name: str,
    history_summaries: tuple[str, ...],
    is_persuade: bool = False,
) -> str:
    traits_desc = "、".join(ctx.npc_traits) if ctx.npc_traits else "普通人"
    tone_instruction = TONE_TEMPLATES[ctx.tone]

    trust_label = (
        "非常不信任" if ctx.trust <= -20
        else "友好" if ctx.trust >= 20
        else "中立"
    )

    history_section = ""
    if history_summaries:
        history_lines = "\n".join(f"- {s}" for s in history_summaries)
        history_section = f"\n\n【历史对话记录】\n{history_lines}"

    persuade_note = ""
    if is_persuade:
        persuade_note = "\n\n【特殊情境】\n玩家正在尝试说服你，请根据信任关系决定是否被说服。"

    return (
        f"你扮演角色：{ctx.npc_name}\n"
        f"性格特征：{traits_desc}\n"
        f"当前地点：{location_name}\n\n"
        f"【语气指令】\n{tone_instruction}\n\n"
        f"【关系状态】\n"
        f"当前信任值：{ctx.trust}（{trust_label}）"
        f"{history_section}\n\n"
        "【回复格式】\n"
        "必须以JSON格式回复，字段：\n"
        '- "text": 你的回复内容（2-4句话）\n'
        '- "trust_delta": 本轮关系变化，整数，范围 [-5, +5]。'
        "玩家友好、提供有用信息时为正；无理、骚扰时为负；普通对话为0\n"
        '- "mood": 你当前情绪，如 "平静"、"警惕"、"开心"、"不耐烦"\n'
        '- "wants_to_end": 布尔值，当你想结束对话时为 true（玩家反复骚扰、超出话题范围等）\n\n'
        f"保持角色一致性，不要脱离角色。{persuade_note}"
    )


def build_summary_prompt(npc_name: str, messages: list[dict]) -> str:
    dialogue_text = "\n".join(
        f"{'玩家' if m['role'] == 'user' else npc_name}: {m['content']}"
        for m in messages
        if m["role"] in ("user", "assistant")
    )
    return (
        f"以下是玩家与{npc_name}的对话记录：\n\n{dialogue_text}\n\n"
        "请用1-2句话总结关键信息，重点记录：\n"
        "- 玩家获得的重要线索\n"
        "- NPC透露的秘密\n"
        "- 关系变化的关键转折点\n\n"
        "同时提取关键信息点。\n\n"
        "以JSON格式回复：\n"
        '{"summary": "摘要文本", "key_info": ["信息点1", "信息点2"]}'
    )
