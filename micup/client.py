import asyncio
import json
import logging
import os
import random
import aiohttp
from typing import Any, Callable, Dict, List, Optional
from .constants import DEFAULT_IGNORED_EVENTS, DEFAULT_ORIGIN, FATAL_CLOSE_CODES, RATE_LIMIT_CLOSE_CODE, RESET_CLOSE_CODES, log
from .errors import MicupAPIError
from .models import Message, User
from .voice import Voice


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
