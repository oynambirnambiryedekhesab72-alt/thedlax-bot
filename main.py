import os
import json
import time
import urllib.request
import urllib.error
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
PREFIXLER = ("td/", "td!")
bot = commands.Bot(command_prefix=list(PREFIXLER), intents=intents)

# API Anahtarın
p1 = "AQ.Ab8RN6I7iSnYkqzuoFQj"
p2 = "LXS5N62GbgEWFRELbzQCuj5FCsechg"
GEMINI_KEY = p1 + p2

SISTEM = (
    "Senin adın THEDLAX. Seni thedlax yarattı, sahibin odur. "
    "Her zaman Türkçe konuş. Samimi, günlük dille ve çok KISA cevap ver, "
    "en fazla 2-3 cümle. Robot gibi resmi konuşma, uzun açıklama yapma, "
    "kullanıcı özellikle detay istemedikçe madde madde yazma."
)

NO_PING = discord.AllowedMentions.none()

# AFK listesi: {kullanici_id: (sebep, zaman)}
afk_users = {}


@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak sorunsuz aktif!")


@bot.command()
async def ai(ctx, *, soru: str = None):
    """Gemini AI ile sohbet etme komutu"""
    if not soru:
        await ctx.send("Efendim? Sorunu yazmak için: `td/ai <sorun>`")
        return

    async with ctx.typing():
        modeller = ["gemini-3.1-flash-lite"]

        cevap = None
        detayli_hata = ""

        for model in modeller:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
                headers = {"Content-Type": "application/json; charset=utf-8"}
                payload = {
                    "systemInstruction": {"parts": [{"text": SISTEM}]},
                    "contents": [{"parts": [{"text": soru}]}],
                    "generationConfig": {"maxOutputTokens": 400},
                }

                data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

                with urllib.request.urlopen(req) as response:
                    result_json = json.loads(response.read().decode("utf-8"))
                    cevap = result_json["candidates"][0]["content"]["parts"][0]["text"]
                    if cevap:
                        break
            except urllib.error.HTTPError as e:
                hata_icerigi = e.read().decode("utf-8", errors="ignore")
                detayli_hata = f"HTTP {e.code}: {hata_icerigi}"
                continue
            except Exception as e:
                detayli_hata = str(e)
                continue

        if cevap:
            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i + 1900], allowed_mentions=NO_PING)
            else:
                await ctx.send(cevap, allowed_mentions=NO_PING)
        else:
            await ctx.send(f"**API Detaylı Hata:**\n```{detayli_hata[:1800]}```")


@bot.command(name="afk")
async def afk(ctx, *, sebep: str = "Sebep belirtilmedi"):
    """AFK moduna geç"""
    sebep = sebep[:200]
    afk_users[ctx.author.id] = (sebep, int(time.time()))
    await ctx.send(
        f"💤 {ctx.author.mention} artık AFK: **{sebep}**",
        allowed_mentions=NO_PING,
    )


@bot.command(name="yavasmod", aliases=["yavaşmod", "slowmode"])
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def yavasmod(ctx, saniye: int):
    """Kanalın yavaş modunu ayarla (0 = kapat)"""
    if saniye < 0 or saniye > 21600:
        await ctx.send("❌ 0 ile 21600 saniye arasında bir sayı gir.")
        return
    await ctx.channel.edit(slowmode_delay=saniye)
    if saniye == 0:
        await ctx.send("✅ Yavaş mod kapatıldı.")
    else:
        await ctx.send(f"🐢 Yavaş mod **{saniye} saniye** olarak ayarlandı.")


@yavasmod.error
async def yavasmod_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bunun için **Kanalları Yönet** yetkin olmalı.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Benim **Kanalları Yönet** yetkim yok.")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send("Kullanım: `td!yavasmod <saniye>` (kapatmak için `0`)")


@bot.command(name="lock", aliases=["kilitle"])
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lock(ctx):
    """Kanalı kilitle (herkesin mesaj yazmasını kapat)"""
    # Bot kilitlenen kanalda yazmaya devam edebilsin
    await ctx.channel.set_permissions(ctx.guild.me, send_messages=True)
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("🔒 Bu kanal kilitlendi. Kimse mesaj yazamaz.")


@bot.command(name="unlock", aliases=["kilitac", "kilitaç"])
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock(ctx):
    """Kanal kilidini aç"""
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.send_messages = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("🔓 Kanal kilidi açıldı.")


@lock.error
@unlock.error
async def kilit_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bunun için **Kanalları Yönet** yetkin olmalı.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Benim **Kanalları Yönet** yetkim yok.")


@bot.command(name="fake", aliases=["fakemesaj"])
@commands.bot_has_permissions(manage_webhooks=True)
async def fake(ctx, kisi: discord.Member, *, mesaj: str):
    """Etiketlenen kişinin adı ve profil fotoğrafıyla mesaj at"""
    mesaj = mesaj[:2000]

    # Thread içindeyse webhook ana kanalda aranır
    thread = None
    kanal = ctx.channel
    if isinstance(ctx.channel, discord.Thread):
        thread = ctx.channel
        kanal = ctx.channel.parent

    # Kanalda botun webhook'u varsa onu kullan, yoksa oluştur
    hooks = await kanal.webhooks()
    hook = next(
        (h for h in hooks if h.name == "THEDLAX-fake" and h.user and h.user.id == bot.user.id),
        None,
    )
    if hook is None:
        hook = await kanal.create_webhook(name="THEDLAX-fake")

    kwargs = {}
    if thread is not None:
        kwargs["thread"] = thread

    try:
        await hook.send(
            content=mesaj,
            username=kisi.display_name[:80],
            avatar_url=kisi.display_avatar.url,
            allowed_mentions=NO_PING,
            **kwargs,
        )
    except discord.HTTPException:
        await ctx.send("❌ Bu kişinin adıyla mesaj atılamadı (isim Discord kurallarına uymuyor olabilir).")
        return

    # Komut mesajını sil (yetki yoksa sessizce geç)
    try:
        await ctx.message.delete()
    except Exception:
        pass


@fake.error
async def fake_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Kişiyi bulamadım. Etiketle: `td!fake @kişi mesaj`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Kullanım: `td!fake @kişi mesaj`")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Benim **Webhook Yönet** yetkim yok.")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    icerik = message.content.lower()
    afk_komutu = icerik.startswith(("td!afk", "td/afk"))

    # Cevap verilen mesajı bul (varsa)
    ref = None
    if message.reference and message.reference.message_id:
        ref = message.reference.resolved
        if not isinstance(ref, discord.Message):
            try:
                ref = await message.channel.fetch_message(message.reference.message_id)
            except Exception:
                ref = None

    # 1) Yazan kişi AFK ise modu kapat
    if message.author.id in afk_users and not afk_komutu:
        del afk_users[message.author.id]
        await message.channel.send(
            f"👋 Hoş geldin {message.author.mention}, AFK modundan çıktın.",
            allowed_mentions=NO_PING,
            delete_after=10,
        )

    # 2) Etiketlenen ya da yanıtlanan kişi AFK mı?
    hedefler = {u.id: u for u in message.mentions}
    if ref is not None:
        hedefler[ref.author.id] = ref.author
    for uid, user in hedefler.items():
        if uid in afk_users and uid != message.author.id:
            sebep, zaman = afk_users[uid]
            await message.reply(
                f"💤 **{user.display_name}** şu an AFK: {sebep} (<t:{zaman}:R>)",
                mention_author=False,
                allowed_mentions=NO_PING,
            )

    # 3) Komutlar
    if message.content.startswith(PREFIXLER):
        await bot.process_commands(message)
        return

    # 4) Bot etiketlendi ya da botun mesajına yanıt verildi -> AI cevap versin
    etiketlendi = bot.user in message.mentions
    yanit = ref is not None and ref.author.id == bot.user.id

    if etiketlendi or yanit:
        soru = (
            message.content
            .replace(f"<@{bot.user.id}>", "")
            .replace(f"<@!{bot.user.id}>", "")
            .strip()
        )
        ctx = await bot.get_context(message)
        await ctx.invoke(ai, soru=soru or None)
        return

    await bot.process_commands(message)


# Botu başlat
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!"))