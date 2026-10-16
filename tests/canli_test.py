"""Canlı test: gerçek Micup sunucusunda yeni metotları dener.

Gereken .env (script klasöründe):
  MICUP_TOKEN=...
  MICUP_GUILD_ID=...
  MICUP_TEST_CHANNEL_ID=...   (botun yazabildiği bir metin kanalı)

Test kanal oluşturur/siler ve mesajları geçici olarak değiştirir; sonunda temizler.
Ban/kick gibi kullanıcıya dokunan işlemler bilerek YOK.
"""
import asyncio
import os
from pathlib import Path

from micup import Bot, AuditAction, MicupAPIError


def load_env():
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


async def step(name, coro):
    try:
        result = await coro
        print(f"[OK]   {name}" + (f" -> {result}" if result is not None else ""))
        return result
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        return None


async def main():
    load_env()
    guild = os.environ["MICUP_GUILD_ID"]
    chan = os.environ["MICUP_TEST_CHANNEL_ID"]
    bot = Bot(os.environ["MICUP_TOKEN"])

    @bot.on("ready")
    async def on_ready():
        print("Bağlandı, testler başlıyor...\n")
        msg = await step("send_message", bot.send_message(chan, "micup testi başlıyor"))
        if msg is None:
            await bot.close(); return
        mid = msg.id

        await step("pin_message", bot.pin_message(chan, mid, reason="test sabitleme"))
        pins = await step("list_pins", bot.list_pins(chan, limit=5))
        await step("unpin_message", bot.unpin_message(chan, mid))

        await step("add_reaction", bot.add_reaction(chan, mid, "👍"))
        await step("list_reaction_users", bot.list_reaction_users(chan, mid, "👍", limit=5))
        await step("remove_own_reaction", bot.remove_own_reaction(chan, mid, "👍"))

        await step("set_slowmode(5)", bot.set_slowmode(chan, 5))
        await step("set_slowmode(0)", bot.set_slowmode(chan, 0))

        new = await step("create_channel", bot.create_channel(guild, "micup-test-geçici", type=0))
        if new:
            await step("delete_channel", bot.delete_channel(new.id if hasattr(new, "id") else new["id"]))

        await step("list_bans", bot.list_bans(guild))
        logs = await step("list_audit_logs", bot.list_audit_logs(guild, limit=5))
        await step("list_audit_logs (MESSAGE_PIN)",
                   bot.list_audit_logs(guild, limit=5, action_type=AuditAction.MESSAGE_PIN))

        await step("delete_message (test)", bot.delete_message(chan, mid, reason="test bitti"))
        await bot.close()
        print("\nBitti.")

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
