from typing import Any, Dict, List, Optional
from .utils import snowflake_to_datetime


class User:

    def __init__(self, data: Dict[str, Any]):
        self.raw = data
        self.id: Optional[str] = data.get("id")
        self.username: Optional[str] = data.get("username")
        self.global_name: Optional[str] = data.get("global_name")
        self.bot: bool = bool(data.get("bot", False))

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.id})>"


class Message:

    def __init__(self, data: Dict[str, Any], bot: "Bot"):
        self._bot = bot
        self.raw = data
        self.id: str = data["id"]
        self.channel_id: str = data["channel_id"]
        self.guild_id: Optional[str] = data.get("guild_id")
        self.member: Optional[Dict[str, Any]] = data.get("member")
        self.content: str = data.get("content", "")
        self.author = User(data.get("author") or {})
        self.pinned: bool = bool(data.get("pinned", False))
        self.created_at = snowflake_to_datetime(self.id)

    @property
    def is_bot(self) -> bool:
        return self.author.bot

    @property
    def args(self) -> List[str]:
        return self.content.split()[1:]

    async def reply(self, content: Optional[str] = None, **fields: Any) -> "Message":
        return await self._bot.send_message(self.channel_id, content, reply_to=self.id, **fields)

    async def send(self, content: Optional[str] = None, **fields: Any) -> "Message":
        return await self._bot.send_message(self.channel_id, content, **fields)

    async def edit(self, content: str) -> "Message":
        return await self._bot.edit_message(self.channel_id, self.id, content)

    async def delete(self) -> None:
        await self._bot.delete_message(self.channel_id, self.id)
