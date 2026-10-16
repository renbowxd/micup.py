# micup — Python Kütüphanesi Dokümantasyonu

Sürüm: 0.1.3
Dil: Python 3.9+

`micup`, Micup platformu için yazılmış bir Python kütüphanesidir. Komutları, olayları, mesaj işlemlerini, moderasyonu, kanal yönetimini, ses kanallarını ve bot durumunu tek bir `Bot` sınıfından yönetir.

Bu doküman kütüphanenin şu an yapabildiklerini ve yapamadıklarını anlatır.

---

## 1. Kurulum

```
pip install micup
```

---

## 2. Hızlı başlangıç

```python
from micup import Bot

TOKEN = "111111.xxxxxxx" # Örnek token kullanımı için değişken

bot = Bot(TOKEN)  # token MICUP_TOKEN ortam değişkeninden okunur ya da kod içine eklenebilir.

@bot.command("!ping")
async def ping(msg):
    return "pong"

bot.run()
```

### MICUP_TOKEN değişkeni nasıl verilir

Token'ı kodun içine yazmak zorunda değilsin. Ortam değişkeni olarak da verebilirsin.

PowerShell (Windows):

```powershell
$env:MICUP_TOKEN = "uygulama_id.gizli_anahtar"
python bot.py
```

Bash (Linux/macOS):

```bash
export MICUP_TOKEN="uygulama_id.gizli_anahtar"
python bot.py
```

Token formatı: `<uygulama_id>.<gizli_anahtar>`

Token yenilenirse eski token hemen geçersiz olur.

---

## 3. Bot sınıfı

### Kurucu

```python
Bot(
    token=None,
    *,
    ignored_events=None,
    origin="https://micup.gg",
    presence=None,
)
```

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `token` | `MICUP_TOKEN` ortam değişkeni | Bot token'ı. İkisi de yoksa `ValueError` fırlatır. |
| `ignored_events` | `["TYPING_START", "PRESENCE_UPDATE"]` | Gateway'den gelmesin istenen olaylar. Liste verirsen varsayılanı tamamen değiştirir. |
| `origin` | `"https://micup.gg"` | Micup sunucu adresi. Keşif belgesi `origin/.well-known/fluxer` adresinden alınır. |
| `presence` | `None` | Bağlanırken gönderilen başlangıç durumu. Ham sözlük olarak verilir. Bağlandıktan sonra değiştirmek için `set_presence` kullan. |

### Özellikler

| Özellik | Tür | Açıklama |
|---|---|---|
| `bot.user` | `User` ya da `None` | Bağlantı kurulunca bot hesabı. Bağlanmadan önce `None`. |
| `bot.session_id` | `str` ya da `None` | Gateway oturum kimliği. |
| `bot.sequence` | `int` ya da `None` | Son alınan olay sırası. |
| `bot.voice` | `Voice` | Ses kanalı yönetimi (bölüm 15). |

### Çalıştırma ve kapatma

| Metot | Açıklama |
|---|---|
| `bot.run()` | Botu başlatır, Ctrl+C'ye kadar bloklar. Ana giriş noktası budur. |
| `await bot.start()` | Asenkron başlatma. Kopunca üstel bekleme ile otomatik yeniden bağlanır. |
| `await bot.close()` | Gateway bağlantısını kapatır ve açık ses odalarını kapatır. |
| `await bot.destroy()` | `close()` ile aynıdır. |
| `bot.is_ready()` | READY olayı geldiyse `True` döner. |

Yeniden bağlanmada READY tekrar gelir. Bu nedenle başlangıç işlerini `ready` olayında yaparken bunların iki kez çalışabileceğini hesaba kat.

---

## 4. Komutlar

```python
@bot.command("!temizle")
async def temizle(msg):
    n = int(msg.args[0]) if msg.args else 10
    ...
    return None
```

Kurallar:

- Bir mesaj verilen önekle başlıyorsa komut çalışır. Önek tam eşleşmeli ya da önek + boşluk olmalıdır (`!ping` `!pingle` komutunu tetiklemez).
- Birden fazla komut önek olarak iç içe ise en uzun önek kazanır.
- Komut bir `str` dönerse, o metin mesaja yanıt olarak gönderilir.
- `None` dönerse otomatik yanıt gönderilmez.
- Bot kendi mesajlarına ve diğer botların mesajlarına komut uygulamaz.
- Komut hata verirse hata loglanır, bot çökmez.

`msg` bir `Message` nesnesidir (bölüm 6).

---

## 5. Olaylar

```python
@bot.on("message_create")
async def mesaj_geldi(msg):
    print(msg.author.username, msg.content)
```

`bot.on(event)` ile dinleyici eklenir. Aynı olaya birden fazla dinleyici bağlanabilir.

| Olay | Argümanlar | Ne zaman |
|---|---|---|
| `ready` | `(bot)` | Gateway hazır. Yeniden bağlanmada da tekrar gelir. |
| `message_create` | `(Message)` | Yeni mesaj geldi. |
| `disconnect` | `(kod, sebep)` | Bağlantı koptu. Sebep şu an boş string. |
| `error` | `(exception)` | Dinleyici ya da bağlantı katmanında hata oluştu. |
| `voice_state_update` | `(ham dict)` | Bir kullanıcının ses durumu değişti. |
| `voice_server_update` | `(ham dict)` | Ses sunucusu bilgisi (token, endpoint) geldi. |
| Diğer gateway olayları | `(ham dict)` | Olayın adı küçük harfle yazılır. Örn. `guild_member_add`. |

Olay adları büyük/küçük harf duyarsızdır. `bot.on("MESSAGE_CREATE")` de çalışır.

Ham olaylar (`guild_member_add` gibi) gelen veriyi olduğu gibi sözlük olarak verir. Alanlar için Micup gateway belgesine bak.

---

## 6. Veri nesneleri

### `User`

| Alan | Tür | Açıklama |
|---|---|---|
| `id` | `str` | Kullanıcı ID'si |
| `username` | `str` | Kullanıcı adı |
| `global_name` | `str` ya da `None` | Görünen ad |
| `bot` | `bool` | Bot hesabı mı |
| `raw` | `dict` | Ham veri |

### `Message`

| Alan / özellik | Tür | Açıklama |
|---|---|---|
| `id` | `str` | Mesaj ID'si |
| `channel_id` | `str` | Kanal ID'si |
| `guild_id` | `str` ya da `None` | Sunucu ID'si. Özel mesajlarda `None`. |
| `content` | `str` | Mesaj metni |
| `author` | `User` | Yazan kullanıcı |
| `member` | `dict` | Sunucu üyesi bilgisi (ham) |
| `pinned` | `bool` | Sabitlenmiş mi |
| `created_at` | `datetime` | ID'den hesaplanan oluşturulma zamanı |
| `is_bot` | `bool` (özellik) | Yazan bot mu |
| `args` | `List[str]` (özellik) | Komut sonrası kelimeler. `"!temizle 10"` → `["10"]` |

Mesaj metotları:

| Metot | Açıklama |
|---|---|
| `await msg.reply(content=None, **fields)` | Bu mesaja yanıt verir (`message_reference` ile). |
| `await msg.send(content=None, **fields)` | Aynı kanala yeni mesaj gönderir. |
| `await msg.edit(content)` | Mesajı düzenler. Sadece kendi mesajın için çalışır. |
| `await msg.delete()` | Mesajı siler. Kendi mesajın ya da `MANAGE_MESSAGES` yetkisi gerekir. |

---

## 7. Mesaj ve REST metotları

Bu metotlar `Bot` üzerinden çağrılır.

### Mesaj gönderme

```python
await bot.send_message(channel_id, "Merhaba")
await bot.send_message(channel_id, None, embeds=[{"type": "rich", "title": "Başlık"}])
await bot.send_message(channel_id, "Yanıt", reply_to=mesaj_id)
```

- `content` `None` olabilir, ama o zaman `embeds` gibi bir içerik vermelisin.
- `reply_to` verilirse mesaj o mesajın yanıtı olarak gider.
- Diğer alanlar (`embeds`, `attachments`, `flags`, `tts`, `allowed_mentions` vb.) `**fields` ile geçirilir.
- Varsayılan olarak `allowed_mentions` boştur. Bot `@everyone`, `@here` ve kullanıcı etiketleriyle kimseyi bildirim almaya zorlamaz.

### Diğer mesaj metotları

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.edit_message(channel_id, message_id, content)` | `Message` | Mesajı düzenler. |
| `await bot.delete_message(channel_id, message_id)` | `None` | Tek mesajı siler. |
| `await bot.bulk_delete(channel_id, message_ids)` | `int` | Toplu siler. 100'lük parçalar halinde çalışır, silinen sayıyı döner. Sadece sunucu kanallarında çalışır, `MANAGE_MESSAGES` gerekir. |
| `await bot.get_messages(channel_id, limit=50, before=None, after=None, around=None)` | `List[Message]` | Mesaj listesi. `limit` 1–100 arasına sıkıştırılır. |

### Kullanıcı

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.get_user(user_id)` | `User` | Kullanıcı bilgisi. |

### Ham REST

```python
await bot.rest("GET", "/guilds/123/members/456")
await bot.rest("PUT", "/guilds/123/members/456/roles/789")
await bot.rest("PATCH", "/guilds/123/members/456", {"communication_disabled_until": "2026-10-10T12:00:00Z"})
```

- Yol `/v1` öneki olmadan verilir, kütüphane otomatik ekler.
- Gövde (`body`) sözlük olarak verilir, JSON'a çevrilir.
- Dönen veri JSON olarak döner. 204 yanıtlarda `None`.
- Hata alırsan `MicupAPIError` fırlatılır.

Hız sınırında (429) sunucunun `retry_after` değeri kadar bekleyip otomatik yeniden dener.

---

## 8. Denetim nedeni (audit reason)

Moderasyon ve kanal metotlarının çoğu `reason` parametresi alır. Bu neden sunucunun denetim kaydına (audit log) yazılır.

- Neden ham olarak gönderilir, URL-encode edilmez.
- Baş ve sondaki boşluklar kırpılır.
- Boş veya 512 karakteri aşan neden yok sayılır. Hata vermez, işlem yine de başarılı olur.

```python
await bot.ban(guild_id, user_id, reason="Spam yaptı")
```

---

## 9. Moderasyon

Bu metotlar botun ilgili yetkilere sahip olmasını gerektirir (ban için ban yetkisi, timeout için üye susturma yetkisi gibi). Yetki eksikse `MicupAPIError` fırlatılır.

### Ban

```python
await bot.ban(guild_id, user_id, reason="Spam", delete_message_seconds=0, duration_seconds=None)
```

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `reason` | `None` | Denetim kaydı nedeni. |
| `delete_message_seconds` | `0` | Son kaç saniyenin mesajlarını silsin (0–604800). |
| `duration_seconds` | `None` | Süre. `None` kalıcı ban. Verilirse 60–63072000 arası olmalı. |

### Ban kaldırma ve listeleme

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.unban(guild_id, user_id)` | `None` | Banı kaldırır. |
| `await bot.list_bans(guild_id)` | `List[dict]` | Sunucudaki banlar. |

### Atma (kick)

```python
await bot.kick(guild_id, user_id)
```

Üyeyi sunucudan çıkarır. Ban değildir, kullanıcı tekrar katılabilir.

### Susturma (timeout)

```python
from datetime import datetime, timedelta, timezone

await bot.timeout(guild_id, user_id, minutes=10, reason="Küfür")
await bot.timeout(guild_id, user_id, until=datetime.now(timezone.utc) + timedelta(hours=1))
await bot.clear_timeout(guild_id, user_id)
```

- `minutes` ya da `until` verilmeli. İkisi de yoksa `ValueError` fırlatır.
- Süre en fazla 365 gün olabilir.
- Susturulan kullanıcı mesaj gönderemez.

---

## 10. Roller ve sesli üyeler

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.add_role(guild_id, user_id, role_id)` | `None` | Üyeye rol verir. |
| `await bot.remove_role(guild_id, user_id, role_id)` | `None` | Üyeden rolü alır. |
| `await bot.set_voice_mute(guild_id, user_id, mute)` | `dict` | Sunucu genelinde mikrofonu kapatır/açar. |
| `await bot.set_voice_deaf(guild_id, user_id, deaf)` | `dict` | Sunucu genelinde kulaklığı kapatır/açar. |
| `await bot.disconnect_member(guild_id, user_id, connection_id=None)` | `dict` | Üyeyi ses kanalından çıkarır. `connection_id` yoksa tüm bağlantılarını kapatır. |
| `await bot.move_member(guild_id, user_id, channel_id, connection_id=None)` | `dict` | Üyeyi başka bir ses kanalına taşır. Hedef ses kanalı olmalı. |

Rol işlemleri için botun rol yönetimi yetkisine ve rol hiyerarşisinde üstünlüğe sahip olması gerekir.

---

## 11. Kanallar

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.get_channel(channel_id)` | `dict` | Kanal bilgisi (ham). |
| `await bot.create_channel(guild_id, name, *, type=0, topic=None, parent_id=None, **fields)` | `dict` | Kanal oluşturur. `type`: 0 metin, 2 ses, 4 kategori. |
| `await bot.edit_channel(channel_id, **fields)` | `dict` | Kanal ayarlarını değiştirir (ör. `name`, `topic`). |
| `await bot.delete_channel(channel_id)` | `None` | Kanalı siler. |
| `await bot.set_slowmode(channel_id, seconds)` | `dict` | Yavaş mod. 0–21600 saniye arası. 0 kapatır. |
| `await bot.purge(channel_id, limit=10)` | `int` | Son `limit` mesajı (en fazla 100) toplu siler. Silinen sayıyı döner. |
| `await bot.set_channel_permission(channel_id, target_id, *, allow=0, deny=0, type=None)` | `dict` | Bir rol ya da üye için kanal iznini ayarlar. Yalnızca hedef girişi değiştirir, diğer izinlere dokunmaz. `type`: 0 rol, 1 üye. Verilmezse mevcut tip korunur. |
| `await bot.clear_channel_permission(channel_id, target_id)` | `dict` | Hedefin kanal izin girişini kaldırır (varsayılanlara döner). |

```python
await bot.set_slowmode(kanal_id, 10)   # 10 saniyede bir mesaj
await bot.set_slowmode(kanal_id, 0)    # yavaş modu kapat
```

Kanal izinleri bit maskeleriyle çalışır. `micup.Permissions` sabitlerini `|` ile birleştirebilirsin:

```python
from micup import Permissions

# Bir rol için ses kanalına girmeyi aç, konuşmayı kapat
await bot.set_channel_permission(
    kanal_id, rol_id,
    allow=Permissions.CONNECT,
    deny=Permissions.SPEAK,
)

# Bir üyeyi kanalda mesaj yazmaktan men et (type=1: üye)
await bot.set_channel_permission(kanal_id, uye_id, type=1, deny=Permissions.SEND_MESSAGES)

# Hedefin kanal izin girişini tamamen kaldır
await bot.clear_channel_permission(kanal_id, rol_id)
```

Metot, kanalın mevcut `permission_overwrites` listesini okuyup yalnızca hedef girişi değiştirerek tüm listeyi geri gönderir. Bir bit aynı anda hem `allow` hem `deny` içinde olamaz; bu durumda `ValueError` alırsın. Bot kanalda MANAGE_ROLES (ya da MANAGE_CHANNELS) yetkisine ve hedef rolün üstünde bir role sahip olmalı.

---

## 12. Sabitleme

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.pin_message(channel_id, message_id, reason=None)` | `None` | Mesajı sabitler. |
| `await bot.unpin_message(channel_id, message_id, reason=None)` | `None` | Sabitlemeyi kaldırır. |
| `await bot.list_pins(channel_id, limit=50, before=None)` | `dict` | Sabitlenmiş mesajlar. `{"items": [...], "has_more": bool}` döner. |

Sayfalama için `before` değerine son öğenin `pinned_at` zaman damgasını ver. Aynı zaman damgalı öğeler tekrar gelebilir, mesaj ID'siyle tekilleştir.

---

## 13. Tepkiler (reactions)

Emoji ya da Unicode emoji (ör. `"👍"`) veya özel emoji için `"isim:id"` biçimi kullanılır. Kütüphane emojiyi URL'ye uygun hale getirir.

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.add_reaction(channel_id, message_id, emoji, session_id=None)` | `None` | Kendi tepkini ekler. |
| `await bot.remove_own_reaction(channel_id, message_id, emoji, session_id=None)` | `None` | Kendi tepkini kaldırır. |
| `await bot.remove_user_reaction(channel_id, message_id, emoji, user_id, session_id=None)` | `None` | Başka bir kullanıcının tepkisini kaldırır. `MANAGE_MESSAGES` gerekir. |
| `await bot.remove_emoji_reactions(channel_id, message_id, emoji)` | `None` | Bu emojiye ait tüm tepkileri kaldırır. |
| `await bot.remove_all_reactions(channel_id, message_id)` | `None` | Mesajdaki tüm tepkileri kaldırır. |
| `await bot.list_reaction_users(channel_id, message_id, emoji, limit=25, after=None)` | `List[dict]` | Bu emojiye tepki veren kullanıcılar. |

---

## 14. Dosya gönderme ve denetim kaydı

### Dosya gönderme

```python
await bot.send_file(channel_id, "rapor.pdf", content="Rapor ektedir")
```

| Metot | Dönüş | Açıklama |
|---|---|---|
| `await bot.send_file(channel_id, path, content=None, **fields)` | `Message` | Dosyayı yükleyip mesaj olarak gönderir. |
| `await bot.upload_attachment(channel_id, path, filename=None, content_type=None)` | `dict` | Sadece yükler, mesajda kullanılacak ek nesnesini döner. Sonra `send_message(..., attachments=[...])` ile gönderebilirsin. |

- Dosya boyutu en fazla 10 MB. Daha büyük dosyalar `MicupAPIError` ile reddedilir.
- Dosya adı ve içerik türü verilmezse dosya yolundan tahmin edilir.

### Denetim kaydı (audit log) okuma

```python
from micup import AuditAction

sayfa = await bot.list_audit_logs(guild_id, limit=20, action_type=AuditAction.MEMBER_BAN_ADD)
for girdi in sayfa["audit_log_entries"]:
    print(girdi["id"], girdi["user_id"], girdi.get("reason"))
```

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `limit` | `50` | 0–100 arası. |
| `before` | `None` | Bu girdinin ID'sinden daha eski kayıtlar. |
| `after` | `None` | Bu girdinin ID'sinden daha yeni kayıtlar. `before` ile birlikte verilemez. |
| `user_id` | `None` | Sadece bu kullanıcının yaptığı işlemler. |
| `action_type` | `None` | Sadece bu işlem türü (`AuditAction` sabitleri). |

Dönen sözlük: `audit_log_entries`, `users`, `webhooks`. Kayıtlar 45 gün saklanır. Gerekli yetki: sunucu denetim kaydını görme.

`AuditAction` içinde sık kullanılan değerler: `MEMBER_KICK`, `MEMBER_BAN_ADD`, `MEMBER_BAN_REMOVE`, `MEMBER_UPDATE`, `MEMBER_ROLE_UPDATE`, `MEMBER_MOVE`, `MEMBER_DISCONNECT`, `MESSAGE_DELETE`, `MESSAGE_BULK_DELETE`, `MESSAGE_PIN`, `MESSAGE_UNPIN`.

---

## 15. Ses

### Önemli bilgi

Ses kanalına girmek iki adımdan oluşur:

1. Sunucu botun ses bağlantısı için bir "grant" (token ve endpoint) verir.
2. Bot bu bilgiyle LiveKit odasına bağlanır.

Botun ses kanalında görünmesi için LiveKit bağlantısı gerekir. Bu kütüphane 2. adımı `join()` içinde kendisi yapar. Medya kurulumunu test ettiğimizde bot, LiveKit bağlantısı kurulduktan sonra kanalda göründü.

### `await bot.voice.join(guild_id, channel_id, *, self_mute=False, self_deaf=False, self_video=False, timeout=15.0, state_timeout=60.0, media=True)`

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `guild_id` | — | Sunucu ID'si |
| `channel_id` | — | Ses kanalı ID'si |
| `self_mute` | `False` | Başlangıçta mikrofon kapalı mı |
| `self_deaf` | `False` | Başlangıçta kulaklık kapalı mı |
| `self_video` | `False` | Video durumu. Video yayınlanmaz, sadece durum bildirilir. |
| `timeout` | `15.0` | Sunucudan grant gelmesini bekleme süresi (sn). Dolarsa `VOICE_TIMEOUT` fırlatır. |
| `state_timeout` | `60.0` | Botun kendi ses durumu gelmesini bekleme süresi (sn). Dolarsa uyarı yazar ve devam eder, hata fırlatmaz. |
| `media` | `True` | LiveKit odasına bağlanılsın mı. `False` ise sadece grant alınır. |

Akış:

1. Katılma isteği (op 4) gönderilir.
2. Grant beklenir (`timeout`).
3. `media=True` ise LiveKit odasına bağlanılır. Bağlantı için `livekit` paketi gerekir, yoksa `LIVEKIT_MISSING` fırlatılır.
4. Botun ses durumu beklenir (`state_timeout`).

Dönüş değeri:

```python
{
    "guild_id": "...",
    "channel_id": "...",
    "connection_id": "...",
    "session_id": "...",   # bilinmiyorsa None
    "endpoint": "wss://...",
    "token": "...",
}
```

### Diğer ses metotları

| Metot | Dönüş | Açıklama |
|---|---|---|
| `bot.voice.get_states(guild_id)` | `List[dict]` | Sunucudaki bilinen ses durumları. |
| `await bot.voice.update(guild_id, self_mute=None, self_deaf=None, self_video=None)` | `None` | Bağlıyken mikrofon, kulaklık ve video durumunu değiştirir. `None` olan alan değişmez. |
| `await bot.voice.leave(guild_id)` | `None` | Ses bağlantısını ve LiveKit odasını kapatır. Bağlı değilsen `VOICE_NOT_CONNECTED` fırlatır. |
| `await bot.voice.play_wav(guild_id, path)` | `None` | Bağlı olduğun ses kanalında bir WAV dosyasını çalar (16-bit PCM). `livekit` paketi gerekir. |
| `await bot.voice.disconnect_all()` | `None` | Açık tüm LiveKit odalarını kapatır. `bot.close()` bunu otomatik çağırır. |

`leave`, `update` ve `play_wav`, `join` sırasında saklanan bağlantı bilgisini kullanır. Sunucu ses durumu göndermese bile çalışır.

### Ses kanalında kalma

Kütüphane bağlantıyı açık tutmaz. Bot kapanırsa ya da LiveKit kopsa kendiliğinden yeniden girmez. Kalıcı kalmasını istiyorsan `ready` olayında `join` çağır ve bağlantı kopmasını izle. Örnek için `examples/bot_hepsi.py` dosyasına bak.

---

## 16. Durum (presence)

```python
await bot.set_presence("dnd", afk=False, mobile=False, custom_status="Çalışıyorum")
await bot.set_presence("idle", afk=True, custom_status={"text": "Uzakta", "emoji_name": "💤"})
```

| Parametre | Tür | Açıklama |
|---|---|---|
| `status` | `str` | `online`, `idle`, `dnd`, `invisible`, `offline`. Başka değer `ValueError` verir. |
| `afk` | `bool` | Uzakta mı. Varsayılan `False`. |
| `mobile` | `bool` | Mobil mi. Varsayılan `False`. |
| `custom_status` | `str` ya da `dict` | Metin ya da `{"text", "emoji_name", ...}` sözlüğü. Verilmezse mevcut özel durum değişmez. |

Bağlı değilken çağrılırsa hata verir. Belgede hız sınırı yazmıyor. Sık değiştirirsen sunucu isteği reddedebilir. Uygulamada 2 saniyede bir değiştirmek çalıştı.

---

## 17. Yetki bitleri

```python
from micup import Permissions

Permissions.has(mask, Permissions.MANAGE_MESSAGES)
```

`mask` tam sayı ya da sayı içeren string olabilir (API yetkileri string olarak verir).
`ADMINISTRATOR` yetkisi olan maske her yetkiyi karşılar.

| Sabit | Bit | Açıklama |
|---|---|---|
| `ADMINISTRATOR` | 1 << 3 | Yönetici |
| `MANAGE_CHANNELS` | 1 << 4 | Kanalları yönet |
| `ADD_REACTIONS` | 1 << 6 | Tepki ekle |
| `VIEW_CHANNEL` | 1 << 10 | Kanalı gör |
| `SEND_MESSAGES` | 1 << 11 | Mesaj gönder |
| `MANAGE_MESSAGES` | 1 << 13 | Mesajları yönet |
| `EMBED_LINKS` | 1 << 14 | Bağlantı önizlemesi |
| `CONNECT` | 1 << 20 | Ses kanalına bağlan |
| `SPEAK` | 1 << 21 | Konuşma |
| `MUTE_MEMBERS` | 1 << 22 | Üyeleri sustur |
| `DEAFEN_MEMBERS` | 1 << 23 | Üyeleri sağırlaştır |
| `MOVE_MEMBERS` | 1 << 24 | Üyeleri taşı |
| `MANAGE_ROLES` | 1 << 28 | Rolleri yönet |

Kütüphanede tüm sabitler `Permissions` sınıfında tanımlıdır. Yukarıdaki liste sık kullanılanlardır.

Yetki bitlerinin resmi değerlerini Micup belgesinden doğrula. Bu tabloda yazılanlar kütüphane kodundaki değerlerdir.

---

## 18. Snowflake yardımcısı

```python
from micup import snowflake_to_datetime

snowflake_to_datetime("1501320000000000000")  # datetime nesnesi
```

ID'den oluşturulma zamanını hesaplar. Epoch: 2015-01-01 UTC.

---

## 19. Hatalar

### `MicupAPIError`

Tüm kütüphane hataları bu sınıftan türer.

| Alan | Açıklama |
|---|---|
| `status` | HTTP durum kodu. Yerel hatalarda `0`. |
| `code` | Hata kodu (aşağıdaki tablo ya da sunucudan gelen kod). |
| `message` | İnsan okunabilir mesaj. |
| `body` | Sunucudan gelen ham yanıt. Doğrulama hatalarında `errors` listesi burada olur. |

`MicupError` aynı sınıfın kısa adıdır.

```python
from micup import MicupAPIError

try:
    await bot.rest("PATCH", ...)
except MicupAPIError as e:
    print(e.code, e.message)
    print(e.body.get("errors"))  # hangi alan hatalı
```

### Kütüphane hata kodları

| Kod | Anlamı |
|---|---|
| `VOICE_TIMEOUT` | Grant `timeout` içinde gelmedi. |
| `VOICE_NOT_CONNECTED` | Bu sunucuda bağlı bir ses bağlantısı yok. |
| `LIVEKIT_MISSING` | `livekit` paketi kurulu değil. |
| `DISCOVERY_FAILED` | Micup keşif belgesi alınamadı. |
| `RATE_LIMITED` | Yeniden deneme sınırı aşıldı. |

### Sunucu hata kodları (örnekler)

| Kod | Anlamı |
|---|---|
| `INVALID_FORM_BODY` | Gövde geçersiz. `body["errors"]` hangi alanın sorunlu olduğunu gösterir. |
| `MISSING_PERMISSIONS` | Bot gerekli yetkiye sahip değil. |
| `UNKNOWN_MEMBER` | Üye bulunamadı. |
| `UNKNOWN_GUILD` | Sunucu bulunamadı. |
| `TWO_FACTOR_REQUIRED` | Sunucu 2FA istiyor. |

### Gateway kapanma kodları

| Kod | Davranış |
|---|---|
| 4004, 4010, 4011, 4012 | Yeniden denenmez. Örn. 4004 geçersiz token. |
| 4001, 4002, 4003, 4005, 4007 | Oturum sıfırlanır, yeniden kimlik doğrulanır. |
| 4008 | Hız sınırı. 30 saniye beklenir. |

---

## 20. Tam örnek (yalnızca kütüphane)

```python
from micup import Bot

bot = Bot(ignored_events=["TYPING_START"])

@bot.on("ready")
async def hazir(b):
    print("Bağlandı:", b.user.username)
    await b.set_presence("online", custom_status="Merhaba")

@bot.command("!ping")
async def ping(msg):
    return "pong"

@bot.command("!ban")
async def ban_komutu(msg):
    if not msg.guild_id or not msg.args:
        return "Kullanım: !ban <kullanıcı_id> [sebep]"
    sebep = " ".join(msg.args[1:]) or None
    await bot.ban(msg.guild_id, msg.args[0], reason=sebep)
    return "Banlandı."

@bot.command("!ses")
async def ses(msg):
    if not msg.guild_id:
        return "Bu komut sunucuda kullanılmalı."
    await bot.voice.join(msg.guild_id, "SES_KANALI_ID")
    return "Ses kanalına katıldım."

bot.run()
```

---

## 21. Örnek uygulama: `examples/bot_hepsi.py`

Bu dosya kütüphanenin nasıl kullanılacağını gösterir. Ayarlar `.env` dosyasından okunur:

```
MICUP_TOKEN=uygulama_id.gizli_anahtar
MICUP_GUILD_ID=sunucu_id
MICUP_VOICE_CHANNEL_ID=ses_kanali_id
MICUP_AUTO_ROLE_ID=rol_id
MICUP_WELCOME_CHANNEL_ID=hosgeldin_kanal_id
MICUP_UPDATE_CHANNEL_ID=guncelleme_kanal_id
MICUP_ADMIN_IDS=kendi_kullanici_id
```

İçerdiği komutlar:

| Komut | Yetki | Açıklama |
|---|---|---|
| `!ban <id> [sebep]` | Admin | Kalıcı ban. |
| `!unban <id>` | Admin | Banı kaldırır. |
| `!kick <id>` | Admin | Sunucudan atar. |
| `!mute <id> <dakika>` | Admin | 1–40320 dakika susturur. |
| `!unmute <id>` | Admin | Susturmayı kaldırır. |
| `!temizle [sayı]` | Admin | Son mesajları toplu siler (varsayılan 10, en fazla 100). |
| `!surum` | Admin | Sürüm duyurusunu güncelleme kanalına gönderir. |

Olaylar:

- `ready`: durum döngüsünü ve ses kanalına girmeyi başlatır.
- `guild_member_add`: yeni üyeye rol verir ve hoşgeldin mesajı atar (botlara vermez).

Bu uygulamada durum, her iki saniyede bir sırayla değişen bir döngüdür.

---

## 22. Hızlı başvuru

```python
from micup import Bot, Permissions, MicupAPIError, Message, User, Voice, AuditAction
from micup import snowflake_to_datetime

bot = Bot(token=None, ignored_events=None, origin="https://micup.gg", presence=None)

@bot.command("!prefix")
async def komut(msg): ...

@bot.on("message_create")
async def olay(msg): ...

bot.run()                                   # başlat
await bot.start()                           # asenkron başlat
await bot.close()                           # kapat
bot.is_ready()

# Mesaj
await bot.send_message(ch, "metin", reply_to=None, **fields)
await bot.edit_message(ch, mid, "yeni metin")
await bot.delete_message(ch, mid)
await bot.bulk_delete(ch, [id1, id2])
await bot.get_messages(ch, limit=50, before=None, after=None, around=None)
await bot.get_user(uid)
await bot.rest("GET", "/yol", body=None)

# Moderasyon
await bot.ban(gid, uid, reason=None, delete_message_seconds=0, duration_seconds=None)
await bot.unban(gid, uid)
await bot.list_bans(gid)
await bot.kick(gid, uid)
await bot.timeout(gid, uid, minutes=None, until=None, reason=None)
await bot.clear_timeout(gid, uid)

# Roller ve sesli üyeler
await bot.add_role(gid, uid, rid)
await bot.remove_role(gid, uid, rid)
await bot.set_voice_mute(gid, uid, True)
await bot.set_voice_deaf(gid, uid, True)
await bot.disconnect_member(gid, uid, connection_id=None)
await bot.move_member(gid, uid, ch, connection_id=None)

# Kanallar
await bot.get_channel(ch)
await bot.create_channel(gid, "ad", type=0, topic=None, parent_id=None)
await bot.edit_channel(ch, name="yeni ad")
await bot.delete_channel(ch)
await bot.set_slowmode(ch, 10)              # 0-21600, 0 kapatır
await bot.purge(ch, limit=10)

# Sabitleme
await bot.pin_message(ch, mid, reason=None)
await bot.unpin_message(ch, mid, reason=None)
await bot.list_pins(ch, limit=50, before=None)

# Tepkiler
await bot.add_reaction(ch, mid, "👍")
await bot.remove_own_reaction(ch, mid, "👍")
await bot.remove_user_reaction(ch, mid, "👍", uid)
await bot.remove_emoji_reactions(ch, mid, "👍")
await bot.remove_all_reactions(ch, mid)
await bot.list_reaction_users(ch, mid, "👍", limit=25, after=None)

# Dosya ve denetim kaydı
await bot.send_file(ch, "dosya.pdf", content="açıklama")
await bot.upload_attachment(ch, "dosya.pdf")
await bot.list_audit_logs(gid, limit=50, before=None, after=None, user_id=None, action_type=None)

# Durum
await bot.set_presence("online", afk=False, mobile=False, custom_status=None)

# Ses
await bot.voice.join(gid, ch, self_mute=False, self_deaf=False, self_video=False,
                     timeout=15.0, state_timeout=60.0, media=True)
bot.voice.get_states(gid)
await bot.voice.update(gid, self_mute=None, self_deaf=None, self_video=None)
await bot.voice.play_wav(gid, "ses.wav")
await bot.voice.leave(gid)
await bot.voice.disconnect_all()

# Mesaj nesnesi
await msg.reply("metin"); await msg.send("metin"); await msg.edit("metin"); await msg.delete()
msg.args; msg.content; msg.author; msg.channel_id; msg.guild_id; msg.is_bot

Permissions.has(mask, Permissions.MANAGE_MESSAGES)
snowflake_to_datetime("ID")
```
