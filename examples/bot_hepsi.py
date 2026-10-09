import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from micup import Bot, MicupAPIError


def _env_oku() -> dict:
    """Ayarları doğrudan .env dosyasından okur. Ortam değişkenlerine bakmaz.

    Önce bu dosyanın yanındaki .env, yoksa çalışma klasöründeki .env denenir.
    """
    adaylar = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for dosya in adaylar:
        if not os.path.isfile(dosya):
            continue
        ayarlar = {}
        with open(dosya, encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if not satir or satir.startswith("#") or "=" not in satir:
                    continue
                anahtar, deger = satir.split("=", 1)
                ayarlar[anahtar.strip()] = deger.strip().strip('"').strip("'")
        return ayarlar
    raise SystemExit(f".env bulunamadı. Denenen yerler: {adaylar}")


AYAR = _env_oku()
TOKEN = AYAR["MICUP_TOKEN"]
GUILD_ID = AYAR["MICUP_GUILD_ID"]
VOICE_CHANNEL_ID = AYAR["MICUP_VOICE_CHANNEL_ID"]
AUTO_ROLE_ID = AYAR["MICUP_AUTO_ROLE_ID"]
WELCOME_CHANNEL_ID = AYAR.get("MICUP_WELCOME_CHANNEL_ID", "")  # boşsa hoşgeldin mesajı atılmaz
UPDATE_CHANNEL_ID = AYAR.get("MICUP_UPDATE_CHANNEL_ID", "")    # güncelleme duyurusu kanalı

log = logging.getLogger("bot_hepsi")

bot = Bot(TOKEN)

DURUMLAR = [
    ("online", "Merhaba"),
    ("idle", "Micup'ta"),
    ("dnd", "Python ile çalışıyorum"),
]

_presence_gorevi = None
_ses_gorevi = None


async def presence_dongusu(aralik=2.0):
    i = 0
    while True:
        status, metin = DURUMLAR[i % len(DURUMLAR)]
        try:
            await bot.set_presence(status, afk=(status == "idle"), custom_status=metin)
        except Exception as e:
            log.warning("Durum güncellenemedi: %s", e)
        i += 1
        await asyncio.sleep(aralik)


async def sesde_tut():
    while True:
        try:
            await bot.voice.join(GUILD_ID, VOICE_CHANNEL_ID, self_mute=True, self_deaf=False)
            log.info("Ses kanalına girildi")
            return
        except MicupAPIError as e:
            log.warning("Ses girişi başarısız (%s): %s. 10 sn sonra tekrar.", e.code, e.message)
            await asyncio.sleep(10)


@bot.on("ready")
async def hazir(b):
    global _presence_gorevi, _ses_gorevi
    # READY her yeniden bağlanmada gelir. Görevleri sadece bir kez başlat.
    if _presence_gorevi is None or _presence_gorevi.done():
        _presence_gorevi = asyncio.create_task(presence_dongusu(aralik=2.0))
    if _ses_gorevi is None or _ses_gorevi.done():
        _ses_gorevi = asyncio.create_task(sesde_tut())


@bot.on("guild_member_add")
async def yeni_uye(data):
    if data.get("guild_id") != GUILD_ID:
        return
    user = data.get("user") or {}
    user_id = user.get("id")
    if not user_id or user.get("bot"):
        return
    try:
        await bot.rest("PUT", f"/guilds/{GUILD_ID}/members/{user_id}/roles/{AUTO_ROLE_ID}")
        log.info("Rol verildi: %s", user_id)
    except MicupAPIError as e:
        log.warning("Rol verilemedi (%s): %s %s", user_id, e.code, e.message)


@bot.on("guild_member_add")
async def hos_geldin(data):
    """Yeni üyeye, ayarlanan kanala embed ile hoşgeldin mesajı atar."""
    if not WELCOME_CHANNEL_ID or data.get("guild_id") != GUILD_ID:
        return
    user = data.get("user") or {}
    user_id = user.get("id")
    if not user_id or user.get("bot"):
        return

    ad = user.get("global_name") or user.get("username") or "yeni üye"
    embed = {
        "type": "rich",
        "title": f"Hoş geldin, {ad}!",
        "description": f"<@{user_id}> sunucuya katıldı. Aramıza hoş geldin.",
        "color": 5793266,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        await bot.send_message(WELCOME_CHANNEL_ID, None, embeds=[embed])
        log.info("Hoşgeldin mesajı atıldı: %s", user_id)
    except MicupAPIError as e:
        log.warning("Hoşgeldin mesajı atılamadı (%s): %s", user_id, _hata_metni(e))


# ---------------------------------------------------------------------------
# Moderasyon komutları
#   !ban <kullanıcı_id> [sebep]
#   !kick <kullanıcı_id>
#   !mute <kullanıcı_id> <dakika>     (1 - 40320 dk, yani en fazla 28 gün)
#   !unmute <kullanıcı_id>
# Sadece MICUP_ADMIN_IDS içindeki kullanıcılar kullanabilir (virgülle ayır).
# ---------------------------------------------------------------------------

ADMIN_IDS = {x.strip() for x in AYAR.get("MICUP_ADMIN_IDS", "").split(",") if x.strip()}


def _kullanici_id(ham: str):
    """'<@123>', '<@!123>' ya da düz '123' biçimlerinden ID çıkarır."""
    ham = ham.strip()
    if ham.startswith("<@") and ham.endswith(">"):
        ham = ham.strip("<@!>")
    return ham if ham.isdigit() else None


def _yetkili(msg) -> bool:
    return msg.author.id in ADMIN_IDS


def _hata_metni(e: MicupAPIError) -> str:
    """Hata kodunu ve varsa doğrulama ayrıntısını (hangi alan) döndürür."""
    detay = ""
    errs = (e.body or {}).get("errors") if isinstance(e.body, dict) else None
    if errs:
        detay = " " + str(errs)[:300]
    return f"{e.code}{detay}".strip()


@bot.command("!ban")
async def ban(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if not msg.args:
        return "Kullanım: !ban <kullanıcı_id> [sebep]"
    uid = _kullanici_id(msg.args[0])
    if not uid:
        return "Geçersiz kullanıcı ID'si."
    sebep = " ".join(msg.args[1:])[:512] or None
    body = {"delete_message_seconds": 0}
    if sebep:
        body["reason"] = sebep
    try:
        await bot.rest("PUT", f"/guilds/{GUILD_ID}/bans/{uid}", body)
    except MicupAPIError as e:
        return f"Ban başarısız: {e.code}"
    return f"{uid} banlandı." + (f" Sebep: {sebep}" if sebep else "")


@bot.command("!kick")
async def kick(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if not msg.args:
        return "Kullanım: !kick <kullanıcı_id>"
    uid = _kullanici_id(msg.args[0])
    if not uid:
        return "Geçersiz kullanıcı ID'si."
    try:
        await bot.rest("DELETE", f"/guilds/{GUILD_ID}/members/{uid}")
    except MicupAPIError as e:
        return f"Kick başarısız: {e.code}"
    return f"{uid} sunucudan atıldı."


@bot.command("!mute")
async def mute(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if len(msg.args) < 2:
        return "Kullanım: !mute <kullanıcı_id> <dakika>"
    uid = _kullanici_id(msg.args[0])
    if not uid:
        return "Geçersiz kullanıcı ID'si."
    try:
        dakika = int(msg.args[1])
    except ValueError:
        return "Dakika bir sayı olmalı."
    if not 1 <= dakika <= 40320:
        return "Dakika 1 ile 40320 arasında olmalı (en fazla 28 gün)."
    bitis = datetime.now(timezone.utc) + timedelta(minutes=dakika)
    try:
        await bot.rest("PATCH", f"/guilds/{GUILD_ID}/members/{uid}", {
            "communication_disabled_until": bitis.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    except MicupAPIError as e:
        return f"Mute başarısız: {_hata_metni(e)}"
    return f"{uid} {dakika} dakika susturuldu."


@bot.command("!unmute")
async def unmute(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if not msg.args:
        return "Kullanım: !unmute <kullanıcı_id>"
    uid = _kullanici_id(msg.args[0])
    if not uid:
        return "Geçersiz kullanıcı ID'si."
    try:
        await bot.rest("PATCH", f"/guilds/{GUILD_ID}/members/{uid}", {"communication_disabled_until": None})
    except MicupAPIError as e:
        return f"Unmute başarısız: {e.code}"
    return f"{uid} susturması kaldırıldı."


@bot.command("!unban")
async def unban(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if not msg.args:
        return "Kullanım: !unban <kullanıcı_id>"
    uid = _kullanici_id(msg.args[0])
    if not uid:
        return "Geçersiz kullanıcı ID'si."
    try:
        await bot.rest("DELETE", f"/guilds/{GUILD_ID}/bans/{uid}")
    except MicupAPIError as e:
        return f"Unban başarısız: {_hata_metni(e)}"
    return f"{uid} banı kaldırıldı."


@bot.command("!temizle")
async def temizle(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    try:
        n = int(msg.args[0]) if msg.args else 10
    except ValueError:
        return "Kullanım: !temizle 10"
    n = max(1, min(n, 100))
    try:
        mesajlar = await bot.get_messages(msg.channel_id, limit=n)
        ids = [m.id for m in mesajlar]
        if not ids:
            return "Silinecek mesaj yok."
        silinen = await bot.bulk_delete(msg.channel_id, ids)
    except MicupAPIError as e:
        return f"Temizleme başarısız: {_hata_metni(e)}"
    return f"{silinen} mesaj silindi."


SURUM_BASLIK = "micup 0.1.0 — İlk sürüm"
SURUM_OZELLIKLER = [
    ("Bağlantı", "Micup gateway'ine bağlanır, kopunca otomatik yeniden bağlanır (resume destekli)."),
    ("Komutlar", "@bot.command(\"!komut\") ile komut tanımla. Dönen metin otomatik yanıt olarak gönderilir."),
    ("Olaylar", "@bot.on(\"ready\" / \"message_create\" / ...) ile olay dinle. ignored_events ile gereksizleri kapat."),
    ("Mesajlar", "send_message, edit_message, delete_message, bulk_delete, get_messages ve Message.reply/send/edit/delete."),
    ("REST", "bot.rest(metod, yol, gövde) ile Micup HTTP API'sinin tamamına ham erişim."),
    ("Ses", "voice.join / leave / update / get_states. join LiveKit odasına bağlanır."),
    ("Durum", "bot.set_presence(durum, afk, mobile, custom_status) ile durum ve özel metin."),
    ("Yardımcılar", "Permissions (yetki bitleri), snowflake_to_datetime, MicupAPIError."),
]


@bot.command("!surum")
async def surum(msg):
    if not _yetkili(msg):
        return "Bu komutu kullanma yetkin yok."
    if not UPDATE_CHANNEL_ID:
        return "MICUP_UPDATE_CHANNEL_ID ayarlı değil."
    embed = {
        "type": "rich",
        "title": SURUM_BASLIK,
        "description": "İlk sürümde eklenen özellikler:",
        "color": 5793266,
        "fields": [{"name": ad, "value": aciklama, "inline": False} for ad, aciklama in SURUM_OZELLIKLER],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        await bot.send_message(UPDATE_CHANNEL_ID, None, embeds=[embed])
    except MicupAPIError as e:
        return f"Duyuru gönderilemedi: {_hata_metni(e)}"
    return "Sürüm duyurusu gönderildi."


bot.run()
