from enum import Enum


class ActionType(str, Enum):
    MOVE = "move"
    LOOK = "look"
    SEARCH = "search"
    TALK = "talk"
    PERSUADE = "persuade"
    TRADE = "trade"
    TAKE = "take"
    USE = "use"
    GIVE = "give"
    STEALTH = "stealth"
    COMBAT = "combat"
    CUSTOM = "custom"
