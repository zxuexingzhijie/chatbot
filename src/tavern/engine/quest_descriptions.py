from __future__ import annotations

QUEST_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "cellar_mystery": {
        "_name": "地下室之谜",
        "discovered": "你注意到地下室里有异常的划痕……",
        "revealed": "格里姆终于透露了密道的秘密",
    },
    "traveler_quest": {
        "_name": "寻找护身符",
        "active": "艾琳请你帮她找回丢失的银质护身符",
        "amulet_found": "你找到了艾琳的银质护身符",
        "completed": "艾琳感激地接过护身符，赠予你地图碎片",
        "abandoned": "艾琳似乎已经放弃了等待……",
    },
    "guest_quest": {
        "_name": "神秘旅客的委托",
        "active": "神秘旅客请你调查地下室的秘密",
        "reported": "你把地下室的发现告诉了神秘旅客",
        "completed": "神秘旅客递给你一封密封的信件",
        "abandoned": "神秘旅客似乎不再期待你的消息了……",
    },
    "backyard_search": {
        "_name": "后院探索",
        "found_box": "在废弃马车下发现了一个生锈铁盒",
        "completed": "从铁盒中获得了一把备用钥匙",
    },
    "guest_betrayal": {
        "_name": "背叛抉择",
        "completed": "你将神秘旅客的信件交给了酒保",
    },
    "main_story": {
        "_name": "主线",
        "good_ending": "黎明之路",
        "bad_ending": "暗影独行",
        "neutral_ending": "过客",
    },
}

_INTERNAL_KEYS = {"_story_status", "_name"}

_NOTIFY_STATUSES = {"active", "completed", "abandoned", "discovered"}


def get_quest_display_name(quest_id: str) -> str:
    entry = QUEST_DESCRIPTIONS.get(quest_id, {})
    return entry.get("_name", quest_id)


def get_quest_status_description(quest_id: str, status: str) -> str:
    entry = QUEST_DESCRIPTIONS.get(quest_id, {})
    return entry.get(status, "")


def should_notify(quest_id: str, status: str) -> bool:
    if status in _INTERNAL_KEYS:
        return False
    return status in _NOTIFY_STATUSES or status in QUEST_DESCRIPTIONS.get(quest_id, {})
