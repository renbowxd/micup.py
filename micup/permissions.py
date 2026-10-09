from typing import Any


class Permissions:

    ADMINISTRATOR = 1 << 3
    MANAGE_CHANNELS = 1 << 4
    ADD_REACTIONS = 1 << 6
    VIEW_CHANNEL = 1 << 10
    SEND_MESSAGES = 1 << 11
    MANAGE_MESSAGES = 1 << 13
    EMBED_LINKS = 1 << 14
    ATTACH_FILES = 1 << 15
    READ_MESSAGE_HISTORY = 1 << 16
    MENTION_EVERYONE = 1 << 17
    CONNECT = 1 << 20
    SPEAK = 1 << 21
    MUTE_MEMBERS = 1 << 22
    DEAFEN_MEMBERS = 1 << 23
    MOVE_MEMBERS = 1 << 24
    MANAGE_ROLES = 1 << 28
    STREAM = 1 << 37
    PIN_MESSAGES = 1 << 51

    @staticmethod
    def has(mask: Any, perm: int) -> bool:
        mask = int(mask)
        if mask & Permissions.ADMINISTRATOR:
            return True
        return (mask & perm) == perm
