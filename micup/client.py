import asyncio
import json
import logging
import mimetypes
import os
import random
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
import aiohttp
from typing import Any, Callable, Dict, List, Optional
from .constants import DEFAULT_IGNORED_EVENTS, DEFAULT_ORIGIN, FATAL_CLOSE_CODES, RATE_LIMIT_CLOSE_CODE, RESET_CLOSE_CODES, log
from .errors import MicupAPIError
from .models import Message, User
from .overwrites import merge_overwrites
from .voice import Voice


def _iso_utc(dt: datetime) -> str:
    """Zamanı Micup'ın beklediği UTC biçimine çevirir: 2026-10-10T12:00:00Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Bot:
    def __init__(
        self,
        token: Optional[str] = None,
        *,
        ignored_events: Optional[List[str]] = None,
        origin: str = DEFAULT_ORIGIN,
        presence: Optional[Dict[str, Any]] = None,
    ):
        self.token = token or os.environ.get("MICUP_TOKEN")
        if not self.token:
            raise ValueError("Token yok. Bot(token) ver ya da MICUP_TOKEN ortam değişkenini ayarla.")

        self.origin = origin.rstrip("/")
        self.ignored_events = list(DEFAULT_IGNORED_EVENTS if ignored_events is None else ignored_events)
        self.presence = presence

        self.user: Optional[User] = None
        self.session_id: Optional[str] = None
        self.sequence: Optional[int] = None
        self.voice = Voice(self)

        self._api_url: Optional[str] = None
        self._gateway_url: Optional[str] = None
        self._http: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._heartbeat_interval: Optional[float] = None
        self._running = False
        self._ready = False
        self._handlers: Dict[str, List[Callable]] = {}
        self._commands: Dict[str, Callable] = {}


    def command(self, prefix: str):
        def decorator(func: Callable):
            self._commands[prefix] = func
            return func
        return decorator

    def on(self, event: str):
        def decorator(func: Callable):
            self._handlers.setdefault(event.lower(), []).append(func)
            return func
        return decorator

    def is_ready(self) -> bool:
        return self._ready


    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._http is None or self._api_url is None:
            raise RuntimeError("Bot bağlı değil. Önce bot.run() ile başlat.")
        headers = {"Authorization": f"Bot {self.token}"}
        extra = kwargs.pop("extra_headers", None)
        if extra:
            headers.update(extra)
        url = f"{self._api_url}{path}"

        for _ in range(5):
            async with self._http.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 204:
                    return None
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None

                if resp.status == 429:
                    body = data if isinstance(data, dict) else {}
                    wait = float(body.get("retry_after", 1))
                    log.warning("Rate limit: %.2f sn bekleniyor (%s)", wait, path)
                    await asyncio.sleep(wait + 0.05)
                    continue

                if resp.status >= 400:
                    body = data if isinstance(data, dict) else {}
                    raise MicupAPIError(
                        resp.status,
                        body.get("code", ""),
                        body.get("message", resp.reason or ""),
                        body,
                    )
                return data

        raise MicupAPIError(429, "RATE_LIMITED", "Çok fazla yeniden deneme")

    async def rest(self, method: str, path: str, body: Any = None) -> Any:
        kwargs: Dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        return await self._request(method.upper(), f"/v1{path}", **kwargs)

    async def send_message(
        self,
        channel_id: str,
        content: Optional[str] = None,
        reply_to: Optional[str] = None,
        **fields: Any,
    ) -> Message:
        body: Dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        if content is not None:
            body["content"] = content
        body.setdefault("allowed_mentions", {"parse": []})
        if reply_to:
            body["message_reference"] = {"message_id": reply_to, "channel_id": channel_id}
        data = await self._request("POST", f"/v1/channels/{channel_id}/messages", json=body)
        return Message(data, self)

    def _audit(self, reason: Optional[str]) -> Dict[str, Any]:
        """Denetim kaydı nedeni için başlık (X-Audit-Log-Reason).

        Değer olduğu gibi gönderilir (URL-encode edilmez). Baştaki/sondaki boşluklar
        kırpılır; boş veya 512 karakteri aşan neden yok sayılır.
        """
        if not reason:
            return {}
        value = reason.strip()
        if not value or len(value) > 512:
            return {}
        return {"extra_headers": {"X-Audit-Log-Reason": value}}

    async def pin_message(self, channel_id: str, message_id: str, *, reason: Optional[str] = None) -> None:
        """Mesajı sabitler. Sadece DEFAULT ve REPLY mesajları sabitlenebilir. İdempotent."""
        await self._request("PUT", f"/v1/channels/{channel_id}/pins/{message_id}", **self._audit(reason))

    async def unpin_message(self, channel_id: str, message_id: str, *, reason: Optional[str] = None) -> None:
        """Sabitlemeyi kaldırır. İdempotent."""
        await self._request("DELETE", f"/v1/channels/{channel_id}/pins/{message_id}", **self._audit(reason))

    async def list_pins(self, channel_id: str, *, limit: int = 50, before: Optional[str] = None) -> Dict[str, Any]:
        """Sabitlenmiş mesajları sayfa sayfa döner: {"items": [...], "has_more": bool}.
        Sayfalamak için before'a son öğenin pinned_at değerini ver. Aynı zaman damgalı
        öğeler tekrar gelebilir, message id ile tekilleştir."""
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 50))}
        if before:
            params["before"] = before
        return await self._request("GET", f"/v1/channels/{channel_id}/messages/pins", params=params)

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str,
                           *, session_id: Optional[str] = None) -> None:
        """Mesaja tepki ekler. Unicode emoji ya da 'isim:id' (özel emoji). İdempotent.
        Yeni tepki grubu açmak için ADD_REACTIONS gerekir. Bot e-postası doğrulanmış olmalı."""
        params = {"session_id": session_id} if session_id else None
        await self._request(
            "PUT", f"/v1/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me",
            params=params,
        )

    async def remove_own_reaction(self, channel_id: str, message_id: str, emoji: str,
                                  *, session_id: Optional[str] = None) -> None:
        """Botun kendi tepkisini kaldırır."""
        params = {"session_id": session_id} if session_id else None
        await self._request(
            "DELETE", f"/v1/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me",
            params=params,
        )

    async def remove_user_reaction(self, channel_id: str, message_id: str, emoji: str, user_id: str,
                                   *, session_id: Optional[str] = None) -> None:
        """Başka bir kullanıcının tepkisini kaldırır. Sadece sunucu kanallarında, MANAGE_MESSAGES gerekir."""
        params = {"session_id": session_id} if session_id else None
        await self._request(
            "DELETE",
            f"/v1/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/{user_id}",
            params=params,
        )

    async def remove_emoji_reactions(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Bir emojiye ait tüm tepkileri kaldırır. MANAGE_MESSAGES gerekir."""
        await self._request(
            "DELETE", f"/v1/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}"
        )

    async def remove_all_reactions(self, channel_id: str, message_id: str) -> None:
        """Mesajdaki tüm tepkileri kaldırır. MANAGE_MESSAGES gerekir."""
        await self._request("DELETE", f"/v1/channels/{channel_id}/messages/{message_id}/reactions")

    async def list_reaction_users(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
        *,
        limit: int = 25,
        after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bir tepkiyi ekleyen kullanıcıları döner: {"items": [...], "has_more": bool, "next_after": ...}.
        emoji Unicode karakter ya da 'isim:id' biçimindeki özel emoji olabilir."""
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if after:
            params["after"] = after
        encoded = quote(emoji, safe="")
        return await self._request(
            "GET", f"/v1/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/users", params=params
        )

    async def upload_attachment(
        self,
        channel_id: str,
        path: str,
        *,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dosyayı kanala yükler ve mesaja eklenebilecek ek nesnesi döner.
        Şimdilik 10 MB'a kadar dosyalar desteklenir (tek parça yükleme).
        Dönen nesneyi send_message(..., attachments=[...]) içine verebilirsin."""
        with open(path, "rb") as f:
            data = f.read()
        size = len(data)
        if size > 10 * 1024 * 1024:
            raise MicupAPIError(0, "FILE_TOO_LARGE", "Şimdilik 10 MB'tan büyük dosyalar desteklenmiyor")

        name = filename or os.path.basename(path)
        ctype = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"

        plan = await self._request(
            "POST",
            f"/v1/channels/{channel_id}/attachments",
            json={"attachments": [{"id": 0, "filename": name, "file_size": size, "content_type": ctype}]},
        )
        item = ((plan or {}).get("attachments") or [{}])[0]
        if item.get("upload_mode") != "singlepart" or not item.get("upload_url"):
            raise MicupAPIError(0, "UNEXPECTED_UPLOAD_PLAN", "Sunucu beklenmeyen bir yükleme planı döndü")

        url = item["upload_url"]
        if url.startswith("/"):
            url = f"{self.origin}{url}"
        # Önceden imzalı adrese Bot başlığı gönderilmez
        async with aiohttp.ClientSession() as session:
            async with session.put(url, data=data, headers={"Content-Type": ctype}) as resp:
                if resp.status >= 300:
                    text = await resp.text()
                    raise MicupAPIError(resp.status, "UPLOAD_FAILED", text[:300])

        return {
            "id": 0,
            "filename": name,
            "upload_filename": item["upload_filename"],
            "file_size": size,
            "content_type": ctype,
        }

    async def send_file(self, channel_id: str, path: str, content: Optional[str] = None, **fields: Any) -> Message:
        """Dosyayı yükleyip mesaj olarak gönderir (10 MB'a kadar)."""
        attachment = await self.upload_attachment(channel_id, path)
        return await self.send_message(channel_id, content, attachments=[attachment], **fields)

    async def edit_message(self, channel_id: str, message_id: str, content: str) -> Message:
        data = await self._request(
            "PATCH", f"/v1/channels/{channel_id}/messages/{message_id}", json={"content": content}
        )
        return Message(data, self)

    async def delete_message(self, channel_id: str, message_id: str) -> None:
        await self._request("DELETE", f"/v1/channels/{channel_id}/messages/{message_id}")

    async def bulk_delete(self, channel_id: str, message_ids: List[str]) -> int:
        ids = list(message_ids)
        for i in range(0, len(ids), 100):
            await self._request(
                "POST",
                f"/v1/channels/{channel_id}/messages/bulk-delete",
                json={"message_ids": ids[i:i + 100]},
            )
        return len(ids)

    async def get_messages(
        self,
        channel_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
        around: Optional[str] = None,
    ) -> List[Message]:
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if around:
            params["around"] = around
        data = await self._request("GET", f"/v1/channels/{channel_id}/messages", params=params)
        return [Message(m, self) for m in data or []]

    async def get_channel(self, channel_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/v1/channels/{channel_id}")

    async def create_channel(
        self,
        guild_id: str,
        name: str,
        *,
        type: int = 0,
        topic: Optional[str] = None,
        parent_id: Optional[str] = None,
        **fields: Any,
    ) -> Dict[str, Any]:
        """Sunucuda yeni kanal açar. type: 0 metin, 2 ses, 4 kategori, 998 bağlantı.
        Bot MANAGE_CHANNELS yetkisine sahip olmalı."""
        body: Dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body.update({"type": type, "name": name})
        if topic is not None:
            body["topic"] = topic
        if parent_id is not None:
            body["parent_id"] = parent_id
        return await self._request("POST", f"/v1/guilds/{guild_id}/channels", json=body)

    async def set_slowmode(self, channel_id: str, seconds: int) -> Dict[str, Any]:
        """Kanalın yavaş mod aralığını ayarlar (0 - 21600 saniye). 0 kapatır.
        Bot kanalda VIEW_CHANNEL ve MANAGE_CHANNELS yetkisine sahip olmalı."""
        if not 0 <= seconds <= 21600:
            raise ValueError("Yavaş mod 0 ile 21600 saniye arasında olmalı")
        return await self._request("PATCH", f"/v1/channels/{channel_id}", json={"rate_limit_per_user": seconds})

    async def set_channel_permission(
        self,
        channel_id: str,
        target_id: str,
        *,
        allow: int = 0,
        deny: int = 0,
        type: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Bir rol ya da üye için kanal iznini ayarlar (allow/deny bit maskeleri).

        Önce kanalın mevcut izinlerini okur, yalnızca `target_id` girişini değiştirir, sonra tüm listeyi geri gönderir.
        type: 0 rol, 1 üye. Verilmezse mevcut tip korunur, yoksa 0 kullanılır.
        Bot kanalda MANAGE_ROLES (ya da MANAGE_CHANNELS) yetkisine ve hedef rolün üstünde bir role sahip olmalı.
        Örnek: bot.set_channel_permission(kanal, rol, deny=Permissions.VIEW_CHANNEL)
        """
        channel = await self.get_channel(channel_id)
        overwrites = merge_overwrites(
            channel.get("permission_overwrites") or [], target_id,
            allow=allow, deny=deny, type=type,
        )
        return await self._request("PATCH", f"/v1/channels/{channel_id}", json={"permission_overwrites": overwrites})

    async def clear_channel_permission(self, channel_id: str, target_id: str) -> Dict[str, Any]:
        """Bir rol ya da üye için kanal izin girişini tamamen kaldırır (varsayılan izinlere döner)."""
        channel = await self.get_channel(channel_id)
        overwrites = merge_overwrites(
            channel.get("permission_overwrites") or [], target_id, remove=True,
        )
        return await self._request("PATCH", f"/v1/channels/{channel_id}", json={"permission_overwrites": overwrites})

    async def edit_channel(self, channel_id: str, **fields: Any) -> Dict[str, Any]:
        """Kanal ayarlarını değiştirir (name, topic, parent_id, rate_limit_per_user vb.).
        Verilmeyen alanlar değişmez. Yetkiler için dokümana bak."""
        body = {k: v for k, v in fields.items() if v is not None}
        return await self._request("PATCH", f"/v1/channels/{channel_id}", json=body)

    async def delete_channel(self, channel_id: str) -> None:
        """Kanalı kalıcı olarak siler. Geri alınamaz."""
        await self._request("DELETE", f"/v1/channels/{channel_id}")

    async def purge(self, channel_id: str, limit: int = 10) -> int:
        """Kanaldaki son `limit` mesajı (en fazla 100) toplu siler. Silinen sayıyı döner."""
        messages = await self.get_messages(channel_id, limit=limit)
        ids = [m.id for m in messages]
        if not ids:
            return 0
        return await self.bulk_delete(channel_id, ids)

    async def ban(
        self,
        guild_id: str,
        user_id: str,
        *,
        reason: Optional[str] = None,
        delete_message_seconds: int = 0,
        duration_seconds: Optional[int] = None,
    ) -> None:
        """Kullanıcıyı banlar. duration_seconds verilmezse kalıcı ban olur (60 - 63072000 arası).
        delete_message_seconds: son kaç saniyenin mesajları silinsin (0 - 604800)."""
        body: Dict[str, Any] = {"delete_message_seconds": delete_message_seconds}
        if reason:
            body["reason"] = reason[:512]
        if duration_seconds is not None:
            body["ban_duration_seconds"] = duration_seconds
        await self._request("PUT", f"/v1/guilds/{guild_id}/bans/{user_id}", json=body)

    async def unban(self, guild_id: str, user_id: str) -> None:
        await self._request("DELETE", f"/v1/guilds/{guild_id}/bans/{user_id}")

    async def list_bans(self, guild_id: str) -> List[Dict[str, Any]]:
        return await self._request("GET", f"/v1/guilds/{guild_id}/bans") or []

    async def list_audit_logs(
        self,
        guild_id: str,
        *,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
        user_id: Optional[str] = None,
        action_type: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Denetim kaydı sayfasını döner: {"audit_log_entries": [...], "users": [...], "webhooks": [...]}.

        Gerekli yetki: VIEW_AUDIT_LOG. limit 0-100 (varsayılan 50). before ve after birlikte
        verilemez. Sonraki sayfa için before'a son girdinin id'sini ver. user_id veya
        action_type filtresi mesaj silme birleştirmesini kapatır. action_type için
        micup.AuditAction sabitlerini kullanabilirsin.
        """
        if not 0 <= int(limit) <= 100:
            raise ValueError("limit 0 ile 100 arasında olmalı.")
        if before and after:
            raise ValueError("before ve after birlikte verilemez.")
        params: Dict[str, Any] = {"limit": int(limit)}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if user_id:
            params["user_id"] = user_id
        if action_type is not None:
            params["action_type"] = int(action_type)
        return await self._request("GET", f"/v1/guilds/{guild_id}/audit-logs", params=params)

    async def kick(self, guild_id: str, user_id: str) -> None:
        """Üyeyi sunucudan atar (ban değildir, tekrar katılabilir)."""
        await self._request("DELETE", f"/v1/guilds/{guild_id}/members/{user_id}")

    async def timeout(
        self,
        guild_id: str,
        user_id: str,
        *,
        minutes: Optional[int] = None,
        until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Üyeyi susturur (mesaj gönderemez). minutes ya da until verilmeli.
        Süre en fazla 365 gün olabilir. Bot MODERATE_MEMBERS yetkisine sahip olmalı."""
        if until is None:
            if minutes is None:
                raise ValueError("minutes ya da until verilmelidir")
            until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        body: Dict[str, Any] = {"communication_disabled_until": _iso_utc(until)}
        if reason:
            body["timeout_reason"] = reason[:512]
        return await self._request("PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json=body)

    async def clear_timeout(self, guild_id: str, user_id: str) -> Dict[str, Any]:
        """Susturmayı kaldırır."""
        return await self._request(
            "PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json={"communication_disabled_until": None}
        )

    async def set_voice_mute(self, guild_id: str, user_id: str, mute: bool) -> Dict[str, Any]:
        """Sunucu genelinde sesli mute (MUTE_MEMBERS yetkisi gerekir)."""
        return await self._request("PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json={"mute": mute})

    async def set_voice_deaf(self, guild_id: str, user_id: str, deaf: bool) -> Dict[str, Any]:
        """Sunucu genelinde sağırlaştırma (DEAFEN_MEMBERS yetkisi gerekir)."""
        return await self._request("PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json={"deaf": deaf})

    async def add_role(self, guild_id: str, user_id: str, role_id: str) -> None:
        """Üyeye rol verir. MANAGE_ROLES yetkisi ve rol hiyerarşisi gerekir."""
        await self._request("PUT", f"/v1/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

    async def remove_role(self, guild_id: str, user_id: str, role_id: str) -> None:
        """Üyeden rol alır. MANAGE_ROLES yetkisi ve rol hiyerarşisi gerekir."""
        await self._request("DELETE", f"/v1/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

    async def disconnect_member(self, guild_id: str, user_id: str, connection_id: Optional[str] = None) -> Dict[str, Any]:
        """Üyeyi ses kanalından çıkarır. connection_id verilmezse tüm ses bağlantılarını kapatır.
        Bot MOVE_MEMBERS yetkisine ve rol hiyerarşisine sahip olmalı."""
        body: Dict[str, Any] = {"channel_id": None}
        if connection_id is not None:
            body["connection_id"] = connection_id
        return await self._request("PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json=body)

    async def move_member(self, guild_id: str, user_id: str, channel_id: str,
                          connection_id: Optional[str] = None) -> Dict[str, Any]:
        """Üyeyi başka bir ses kanalına taşır. Hedef kanal ses kanalı olmalı."""
        body: Dict[str, Any] = {"channel_id": channel_id}
        if connection_id is not None:
            body["connection_id"] = connection_id
        return await self._request("PATCH", f"/v1/guilds/{guild_id}/members/{user_id}", json=body)

    async def get_user(self, user_id: str) -> User:
        return User(await self._request("GET", f"/v1/users/{user_id}"))


    async def set_presence(
        self,
        status: str,
        *,
        afk: bool = False,
        mobile: bool = False,
        custom_status: Optional[Any] = None,
    ) -> None:
        valid = {"online", "idle", "dnd", "invisible", "offline"}
        if status not in valid:
            raise ValueError(f"Geçersiz durum: {status}. Şunlardan biri olmalı: {sorted(valid)}")
        d: Dict[str, Any] = {"status": status, "afk": afk, "mobile": mobile}
        if custom_status is not None:
            d["custom_status"] = {"text": custom_status} if isinstance(custom_status, str) else custom_status
        await self._send({"op": 3, "d": d})

    async def _discover(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.origin}/.well-known/fluxer") as resp:
                if resp.status != 200:
                    raise MicupAPIError(resp.status, "DISCOVERY_FAILED", "Keşif belgesi alınamadı")
                data = await resp.json(content_type=None)
        self._api_url = data["endpoints"]["api_public"].rstrip("/")
        self._gateway_url = data["endpoints"]["gateway"]

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("Gateway bağlantısı yok")
        await self._ws.send_json(payload)

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            await asyncio.sleep(self._heartbeat_interval * random.random())
            while True:
                await ws.send_json({"op": 1, "d": self.sequence})
                await asyncio.sleep(self._heartbeat_interval)
        except Exception:
            return

    async def _identify(self) -> None:
        await self._send({
            "op": 2,
            "d": {
                "token": self.token,
                "properties": {"os": "linux", "browser": "micup.py", "device": "micup.py"},
                "presence": self.presence or {"status": "online", "afk": False, "mobile": False},
                "ignored_events": self.ignored_events,
                "flags": 0,
            },
        })

    async def _resume(self) -> None:
        await self._send({
            "op": 6,
            "d": {"token": self.token, "session_id": self.session_id, "seq": self.sequence},
        })

    async def _connect(self) -> Optional[int]:
        async with self._http.ws_connect(f"{self._gateway_url}?v=1&encoding=json", max_msg_size=0) as ws:
            self._ws = ws
            hello = await ws.receive_json()
            if hello.get("op") != 10:
                raise MicupAPIError(0, "INVALID_HELLO", "Hello (op 10) bekleniyordu")
            self._heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0

            hb = asyncio.create_task(self._heartbeat(ws))
            try:
                if self.session_id and self.sequence is not None:
                    await self._resume()
                else:
                    await self._identify()

                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        await self._handle(json.loads(raw.data))
                    elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            finally:
                hb.cancel()
                self._ws = None

        close_code = ws.close_code
        if close_code in RESET_CLOSE_CODES:
            self.session_id = None
            self.sequence = None
        return close_code

    async def _handle(self, msg: Dict[str, Any]) -> None:
        op = msg.get("op")
        if op == 0:
            await self._dispatch(msg.get("t"), msg.get("d") or {}, msg.get("s"))
        elif op == 1:
            await self._send({"op": 1, "d": self.sequence})
        elif op == 7:
            await self._ws.close()
        elif op == 9:
            if not msg.get("d"):
                self.session_id = None
                self.sequence = None
            await self._ws.close()
        elif op == 11:
            pass
        else:
            log.debug("Bilinmeyen opcode: %s", op)

    async def _dispatch(self, event: Optional[str], data: Dict[str, Any], seq: Optional[int]) -> None:
        if seq is not None:
            self.sequence = seq
        if not event:
            return

        if event == "READY":
            self.session_id = data.get("session_id")
            self.user = User(data.get("user") or {})
            self._ready = True
            log.info("Bağlandı: %s", self.user.username)
            await self._emit("ready", self)
            return

        if event == "RESUMED":
            self._ready = True
            log.info("Oturum devam ettirildi")
            return

        if event == "MESSAGE_CREATE":
            msg = Message(data, self)
            await self._emit("message_create", msg)
            try:
                await self._run_commands(msg)
            except Exception:
                log.exception("Komut işlenirken hata")
            return

        if event == "GUILD_CREATE":
            self.voice._load_guild(data)
        elif event == "VOICE_STATE_UPDATE":
            self.voice._on_state(data)
        elif event == "VOICE_SERVER_UPDATE":
            self.voice._on_server(data)

        await self._emit(event.lower(), data)

    async def _emit(self, name: str, *args: Any) -> None:
        for handler in self._handlers.get(name, []):
            await self._call(handler, *args)

    async def _call(self, func: Callable, *args: Any) -> Any:
        try:
            result = func(*args)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception:
            log.exception("Handler hatası: %s", getattr(func, "__name__", func))
            return None

    async def _run_commands(self, msg: Message) -> None:
        if msg.author.bot or (self.user and msg.author.id == self.user.id):
            return
        for prefix in sorted(self._commands, key=len, reverse=True):
            if msg.content == prefix or msg.content.startswith(prefix + " "):
                result = await self._call(self._commands[prefix], msg)
                if isinstance(result, str) and result:
                    await msg.reply(result)
                return


    async def start(self) -> None:
        self._running = True
        self._http = aiohttp.ClientSession()
        delay = 1.0
        try:
            while self._running:
                try:
                    await self._discover()
                    code = await self._connect()
                    self._ready = False
                    await self._emit("disconnect", code, "")
                    if not self._running:
                        break
                    if code in FATAL_CLOSE_CODES:
                        log.error("Gateway kalıcı olarak kapattı (%s). Bot durduruldu.", code)
                        break
                    if code == RATE_LIMIT_CLOSE_CODE:
                        log.warning("Çok sık bağlanıldı, 30 sn bekleniyor.")
                        await asyncio.sleep(30)
                    else:
                        await asyncio.sleep(1)
                    delay = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._ready = False
                    if not self._running:
                        break
                    await self._emit("error", e)
                    log.warning("Bağlantı hatası: %s (%.0f sn sonra tekrar)", e, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
        finally:
            self._running = False
            self._ready = False
            if self._http is not None:
                await self._http.close()
                self._http = None

    async def close(self) -> None:
        self._running = False
        await self.voice.disconnect_all()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

    async def destroy(self) -> None:
        await self.close()

    def run(self) -> None:
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            log.info("Bot durduruldu")
