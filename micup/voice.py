import asyncio
import wave
from typing import Any, Dict, List, Optional
from .constants import log
from .errors import MicupAPIError


class Voice:

    def __init__(self, bot: "Bot"):
        self._bot = bot
        self._states: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._grants: Dict[str, asyncio.Future] = {}
        self._mine: Dict[str, Dict[str, Any]] = {}
        self._rooms: Dict[str, Any] = {}

    async def _connect_media(self, guild_id: str, grant: Dict[str, Any]) -> None:
        try:
            from livekit import rtc
        except ImportError:
            raise MicupAPIError(0, "LIVEKIT_MISSING", "Ses medyası için 'pip install livekit' gerekli")

        old = self._rooms.pop(guild_id, None)
        if old is not None:
            await old.disconnect()

        room = rtc.Room()
        await room.connect(grant["endpoint"], grant["token"])
        self._rooms[guild_id] = room
        log.info("LiveKit odasına bağlandı (guild %s)", guild_id)

    async def disconnect_all(self) -> None:
        for guild_id in list(self._rooms):
            room = self._rooms.pop(guild_id)
            try:
                await room.disconnect()
            except Exception as e:
                log.warning("LiveKit kapatma hatası (%s): %s", guild_id, e)


    def _load_guild(self, guild: Dict[str, Any]) -> None:
        gid = guild.get("id")
        for st in guild.get("voice_states") or []:
            self._on_state(dict(st, guild_id=st.get("guild_id") or gid))

    def _on_state(self, st: Dict[str, Any]) -> None:
        gid = st.get("guild_id")
        if gid is None:
            return
        key = st.get("connection_id") or st.get("user_id")
        if not key:
            return
        states = self._states.setdefault(gid, {})
        is_me = self._bot.user is not None and st.get("user_id") == self._bot.user.id
        if st.get("channel_id") is None:
            states.pop(key, None)
            if is_me:
                self._mine.pop(gid, None)
        else:
            states[key] = st
            if is_me and gid in self._mine and st.get("connection_id") == self._mine[gid].get("connection_id"):
                self._mine[gid]["channel_id"] = st.get("channel_id")

    def _on_server(self, data: Dict[str, Any]) -> None:
        fut = self._grants.get(data.get("channel_id"))
        if fut is not None and not fut.done():
            fut.set_result(data)


    def _own_state(self, guild_id: str) -> Optional[Dict[str, Any]]:
        if self._bot.user is None:
            return None
        for st in self._states.get(guild_id, {}).values():
            if st.get("user_id") == self._bot.user.id:
                return st
        return None


    def get_states(self, guild_id: str) -> List[Dict[str, Any]]:
        return list(self._states.get(guild_id, {}).values())

    async def join(
        self,
        guild_id: str,
        channel_id: str,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
        self_video: bool = False,
        timeout: float = 15.0,
        state_timeout: float = 60.0,
        media: bool = True,
    ) -> Dict[str, Any]:
        fut = asyncio.get_running_loop().create_future()
        self._grants[channel_id] = fut
        try:
            await self._bot._send({
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": self_mute,
                    "self_deaf": self_deaf,
                    "self_video": self_video,
                    "self_stream": False,
                },
            })
            grant = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise MicupAPIError(0, "VOICE_TIMEOUT", f"{channel_id} için ses bilgisi gelmedi")
        finally:
            self._grants.pop(channel_id, None)

        if media:
            await self._connect_media(guild_id, grant)

        connection_id = grant.get("connection_id")
        waited = 0.0
        while connection_id not in self._states.get(guild_id, {}):
            if waited >= state_timeout:
                print(f"[micup] UYARI: {state_timeout:.0f} sn içinde kendi ses durumu gelmedi, grant ile devam ediliyor")
                break
            await asyncio.sleep(0.5)
            waited += 0.5
        own = self._own_state(guild_id) or {}
        self._mine[guild_id] = {
            "channel_id": channel_id,
            "connection_id": connection_id,
            "self_mute": self_mute,
            "self_deaf": self_deaf,
            "self_video": self_video,
            "self_stream": False,
        }
        return {
            "guild_id": grant.get("guild_id", guild_id),
            "channel_id": channel_id,
            "connection_id": connection_id,
            "session_id": own.get("session_id"),
            "endpoint": grant.get("endpoint"),
            "token": grant.get("token"),
        }

    def _own_link(self, guild_id: str) -> Optional[Dict[str, Any]]:
        if guild_id in self._mine:
            return self._mine[guild_id]
        st = self._own_state(guild_id)
        if st and st.get("connection_id"):
            return {
                "channel_id": st.get("channel_id"),
                "connection_id": st["connection_id"],
                "self_mute": st.get("self_mute", False),
                "self_deaf": st.get("self_deaf", False),
                "self_video": st.get("self_video", False),
                "self_stream": st.get("self_stream", False),
            }
        return None

    async def leave(self, guild_id: str) -> None:
        link = self._own_link(guild_id)
        if not link or not link.get("connection_id"):
            raise MicupAPIError(0, "VOICE_NOT_CONNECTED", "Bu sunucuda bağlı bir ses bağlantın yok")
        await self._bot._send({
            "op": 4,
            "d": {"guild_id": guild_id, "channel_id": None, "connection_id": link["connection_id"]},
        })
        self._mine.pop(guild_id, None)
        room = self._rooms.pop(guild_id, None)
        if room is not None:
            await room.disconnect()

    async def update(self, guild_id: str, *, self_mute: Optional[bool] = None, self_deaf: Optional[bool] = None,
                     self_video: Optional[bool] = None) -> None:
        link = self._own_link(guild_id)
        if not link or not link.get("connection_id"):
            raise MicupAPIError(0, "VOICE_NOT_CONNECTED", "Bu sunucuda bağlı bir ses bağlantın yok")
        new = {
            "self_mute": link.get("self_mute", False) if self_mute is None else self_mute,
            "self_deaf": link.get("self_deaf", False) if self_deaf is None else self_deaf,
            "self_video": link.get("self_video", False) if self_video is None else self_video,
        }
        await self._bot._send({
            "op": 4,
            "d": {
                "guild_id": guild_id,
                "channel_id": link["channel_id"],
                "connection_id": link["connection_id"],
                **new,
                "self_stream": link.get("self_stream", False),
            },
        })
        link.update(new)

    async def play_wav(self, guild_id: str, path: str) -> None:
        """Bağlı olunan ses kanalında bir WAV dosyasını çalar (16-bit PCM).

        Önce join(media=True) ile LiveKit odasına bağlı olmalısın.
        Çalma bitince ses parçası kaldırılır. MP3 gibi formatlar desteklenmez.
        Bu metot LiveKit SDK'sının API'sine göre yazıldı ve henüz sunucuda denenmedi.
        """
        try:
            from livekit import rtc
        except ImportError:
            raise MicupAPIError(0, "LIVEKIT_MISSING", "Ses çalmak için 'pip install livekit' gerekli")

        room = self._rooms.get(guild_id)
        if room is None:
            raise MicupAPIError(0, "VOICE_NOT_CONNECTED", "Bu sunucuda LiveKit odası yok, önce join çağır")

        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                raise MicupAPIError(0, "UNSUPPORTED_WAV", "Yalnızca 16-bit PCM WAV desteklenir")
            rate, channels = w.getframerate(), w.getnchannels()
            data = w.readframes(w.getnframes())

        source = rtc.AudioSource(rate, channels)
        track = rtc.LocalAudioTrack.create_audio_track("micup-audio", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        publication = await room.local_participant.publish_track(track, options)
        try:
            # 10 ms'lik kareler halinde gönder
            spc = rate // 100
            frame_bytes = spc * channels * 2
            for i in range(0, len(data), frame_bytes):
                chunk = data[i:i + frame_bytes]
                if len(chunk) < frame_bytes:
                    chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
                frame = rtc.AudioFrame(data=chunk, sample_rate=rate, num_channels=channels, samples_per_channel=spc)
                await source.capture_frame(frame)
            await source.wait_for_playout()
        finally:
            await room.local_participant.unpublish_track(publication.sid)
