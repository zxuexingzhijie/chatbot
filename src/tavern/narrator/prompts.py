from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tavern.world.memory import MemoryContext
    from tavern.world.state import WorldState

NARRATIVE_TEMPLATES: dict[str, str] = {
    "move": (
        "你是一位奇幻小说叙述者。玩家刚刚进入了一个新地点。"
        "用2-3句话描写玩家进入该地点时的氛围感：环境细节、光线、声音、气味。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "look": (
        "你是一位奇幻小说叙述者。玩家正在仔细观察周围。"
        "用2-3句话侧重感官细节：视觉、听觉、触觉体验，营造沉浸感。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "take": (
        "你是一位奇幻小说叙述者。玩家刚刚拾起了一件物品。"
        "用2-3句话简短描写拾取动作和物品质感：重量、材质、感觉。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
    "_default": (
        "你是一位奇幻小说叙述者。玩家刚刚完成了一个行动。"
        "用2-3句话简短描写结果：点题即止，带一点情境感。"
        "第二人称（「你」），中文，不重复动作事实本身。"
    ),
}


@dataclass(frozen=True)
class NarrativeContext:
    action_type: str
    action_message: str
    location_name: str
    location_desc: str
    player_name: str
    target: str | None


def build_narrative_prompt(
    ctx: NarrativeContext,
    memory_ctx: MemoryContext | None = None,
    story_hint: str | None = None,
) -> list[dict[str, str]]:
    system_style = NARRATIVE_TEMPLATES.get(ctx.action_type, NARRATIVE_TEMPLATES["_default"])

    system_content = (
        f"{system_style}\n\n"
        f"当前地点：{ctx.location_name}——{ctx.location_desc}\n"
        f"玩家角色名：{ctx.player_name}"
    )

    if memory_ctx is not None:
        system_content += f"\n\n【近期历史】\n{memory_ctx.recent_events}"
        system_content += f"\n\n【关系状态】\n{memory_ctx.relationship_summary}"

    if story_hint is not None:
        system_content += f"\n\n【剧情提示】\n{story_hint}"

    user_parts = [ctx.action_message]
    if ctx.target:
        user_parts.append(f"（涉及对象：{ctx.target}）")
    user_content = "\n".join(user_parts)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


ENDING_TEMPLATE = (
    "你是一位叙事大师，正在为这段冒险故事画上句号。\n"
    "用200-300字的篇幅，以第二人称（「你」）写一段结局叙事。\n"
    "风格：富有余韵的收束感，不要戛然而止，也不要拖沓。中文。"
)


def build_ending_prompt(
    ending_id: str,
    narrator_hint: str,
    state: WorldState,
    memory: MemoryContext | None = None,
) -> list[dict[str, str]]:
    quest_lines = []
    for qid, q in state.quests.items():
        status = q.get("status", "unknown")
        quest_lines.append(f"  {qid}: {status}")
    quest_text = "\n".join(quest_lines) if quest_lines else "  无"

    player = state.characters.get(state.player_id)
    inv_text = ", ".join(player.inventory) if player and player.inventory else "无"

    system_content = (
        f"{ENDING_TEMPLATE}\n\n"
        f"【任务状态】\n{quest_text}\n\n"
        f"【持有物品】\n  {inv_text}"
    )

    if memory is not None:
        system_content += f"\n\n【近期历史】\n{memory.recent_events}"
        system_content += f"\n\n【关系状态】\n{memory.relationship_summary}"

    user_content = f"结局ID: {ending_id}\n\n叙事方向: {narrator_hint}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
