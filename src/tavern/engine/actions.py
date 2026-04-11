from enum import Enum


class ActionType(str, Enum):
    MOVE = "move"
    LOOK = "look"
    SEARCH = "search"
    TALK = "talk"
    PERSUADE = "persuade"
    TAKE = "take"
    USE = "use"
    CUSTOM = "custom"
