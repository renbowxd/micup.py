import asyncio
import logging
import os
from datetime import datetime, timezone

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
WELCOME_CHANNEL_ID = AYAR.get("MICUP_WELCOME_CHANNEL_ID", "")
UPDATE_CHANNEL_ID = AYAR.get("MICUP_UPDATE_CHANNEL_ID", "")
ADMIN_IDS = {x.strip() for x in AYAR.get("MICUP_ADMIN_IDS", "").split(",") if x.strip()}

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
        await bot.add_role(GUILD_ID, user_id, AUTO_ROLE_ID)
        log.info("Rol verildi: %s", user_id)
    except MicupAPIError as e:
        log.warning("Rol verilemedi (%s): %s", user_id, _hata_metni(e))


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
    try:
        await bot.ban(GUILD_ID, uid, reason=sebep)
    except MicupAPIError as e:
        return f"Ban başarısız: {_hata_metni(e)}"
    return f"{uid} banlandı." + (f" Sebep: {sebep}" if sebep else "")


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
        await bot.unban(GUILD_ID, uid)
    except MicupAPIError as e:
        return f"Unban başarısız: {_hata_metni(e)}"
    return f"{uid} banı kaldırıldı."


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
        await bot.kick(GUILD_ID, uid)
    except MicupAPIError as e:
        return f"Kick başarısız: {_hata_metni(e)}"
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
    try:
        await bot.timeout(GUILD_ID, uid, minutes=dakika)
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
        await bot.clear_timeout(GUILD_ID, uid)
    except MicupAPIError as e:
        return f"Unmute başarısız: {_hata_metni(e)}"
    return f"{uid} susturması kaldırıldı."


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
        silinen = await bot.purge(msg.channel_id, limit=n)
    except MicupAPIError as e:
        return f"Temizleme başarısız: {_hata_metni(e)}"
    if not silinen:
        return "Silinecek mesaj yok."
    return f"{silinen} mesaj silindi."


SURUM_BASLIK = "micup 0.1.4 güncellemesi"
SURUM_OZELLIKLER = [
    ("Yayın izni düzeltildi", "Yayın (ekran paylaşımı) izni artık doğru yetkiyi veriyor. Önceki sürümde yanlış bir izin veriliyordu."),
    ("Mesaj düzenleme", "Bir mesajın hem yazısı hem embed'i düzenlenebiliyor."),
    ("Kanal izinleri", "Kanal bazında rol ve üyelere özel izin verilip kaldırılabiliyor."),
    ("Moderasyon", "Ban, ban kaldırma, atma, zaman aşımı ve ban listesi işlemleri destekleniyor."),
    ("Kanal yönetimi", "Kanal oluşturma, düzenleme, silme, yavaş mod ve toplu mesaj silme."),
    ("Tepki ve sabitleme", "Tepki ekleme ve kaldırma, mesaj sabitleme ve sabitlenenleri listeleme."),
    ("Ses", "Sesli kanalda WAV dosyası çalınabiliyor."),
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
        "description": "Bu sürümde eklenen özellikler:",
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
