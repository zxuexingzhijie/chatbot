from __future__ import annotations

import random

ATMOSPHERE_QUOTES: tuple[str, ...] = (
    "酒馆谚语：酒杯见底时，真话才浮出水面。",
    "古老格言：信任是最慢酿成的酒，也是最易碎的杯。",
    "冒险者手记：每扇门背后都有故事，但不是每个故事都有好结局。",
    "酒保低语：在这酒馆里，墙壁也有耳朵……",
    "旅人箴言：最危险的路，往往藏着最珍贵的答案。",
    "酒馆谚语：听得越多的人，说得越少。",
    "古老格言：黑暗中点燃的火把，比正午的太阳更耀眼。",
    "冒险者手记：有些秘密，只在夜深人静时才愿被发现。",
    "旅人箴言：陌生人的善意，有时比老友的承诺更可靠。",
    "酒馆谚语：地下室的门锁了是有原因的。",
    "古老格言：看清一个人，不看他说了什么，看他藏了什么。",
    "冒险者手记：护身符的光芒，往往在最需要它的时候最亮。",
    "旅人箴言：走过的路不会白走，见过的人不会白见。",
    "酒馆谚语：第一杯酒敬勇气，最后一杯酒敬智慧。",
    "古老格言：密道通向的不只是另一个房间，还有另一种真相。",
    "酒保低语：有些客人来喝酒，有些客人来找东西……",
    "旅人箴言：选择比能力更重要，时机比选择更关键。",
    "冒险者手记：地图上没有标记的地方，才是真正的冒险所在。",
    "酒馆谚语：格里姆的沉默比大多数人的话更有分量。",
    "古老格言：帮助他人时种下的种子，总会在意想不到的时候开花。",
)

_last_index: int = -1


def random_quote() -> str:
    global _last_index
    idx = random.randrange(len(ATMOSPHERE_QUOTES))
    while idx == _last_index and len(ATMOSPHERE_QUOTES) > 1:
        idx = random.randrange(len(ATMOSPHERE_QUOTES))
    _last_index = idx
    return ATMOSPHERE_QUOTES[idx]
