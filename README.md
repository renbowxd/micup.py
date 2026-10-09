# micup

Micup platformu için Python kütüphanesi. Bot yazmak için mesaj, komut, olay, yetki ve ses yönetimini tek yerden sağlar.

## Kurulum

```
pip install micup
```

## Hızlı başlangıç

```python
from micup import Bot

bot = Bot()  # token MICUP_TOKEN ortam değişkeninden okunur

@bot.command("!ping")
async def ping(msg):
    return "pong"

bot.run()
```

Token'ı kodun içine yazma. PowerShell'de:

```powershell
$env:MICUP_TOKEN = "uygulama_id.gizli_anahtar"
python bot.py
```

## Özellikler

- Gateway bağlantısı, kopunca otomatik yeniden bağlanma (resume destekli)
- Komutlar ve olaylar: `@bot.command(...)`, `@bot.on(...)`
- Mesaj işlemleri: gönder, düzenle, sil, toplu sil, listele
- Ham REST erişimi: `bot.rest(...)`
- Ses: kanala katılma, ayrılma, durum okuma (LiveKit medya bağlantısı dahil)
- Durum: `bot.set_presence(...)`
- Yetki bitleri ve snowflake yardımcıları

Ayrıntılı kullanım için <a href="https://micup.renbow.dev">dokümantasyona</a> bak.

## Lisans

Henüz belirlenmedi.
