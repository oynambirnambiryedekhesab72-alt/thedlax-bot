import os
from discord.ext import commands

# Bot Yetkileri (Intents)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="td!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} adıyla bot sorunsuz aktif edildi!')

# ---------------------------------------------------
# 1. KOMUT: td!fake @kişi mesaj (Webhook ile Taklit Etme)
# ---------------------------------------------------
@bot.command()
@commands.has_permissions(manage_webhooks=True)
@commands.bot_has_permissions(manage_webhooks=True)
async def fake(ctx, uye: discord.Member = None, *, mesaj: str = None):
    if not uye or not mesaj:
        await ctx.send("❌ Kullanım: `td!fake @kişi mesaj`", delete_after=5)
        return
    
    if "@everyone" in mesaj or "@here" in mesaj:
        await ctx.send("❌ Etiket (@everyone / @here) kullanamazsın.", delete_after=5)
        return

    # Komut mesajını sil
    try:
        await ctx.message.delete()
    except:
        pass

    # Webhook oluştur, profil resmini ve adını kopyalayıp mesajı at
    webhook = await ctx.channel.create_webhook(name=uye.display_name)
    await webhook.send(
        content=mesaj,
        username=uye.display_name,
        avatar_url=uye.display_avatar.url
    )
    await webhook.delete()

# ---------------------------------------------------
# 2. KOMUT: td!ai [mesaj] VEYA Etiketleme / Yanıt Verme
# ---------------------------------------------------
@bot.command()
async def ai(ctx, *, mesaj: str = None):
    if not mesaj:
        await ctx.send("❌ Lütfen bir mesaj girin. Örn: `td!ai merhaba`")
        return
    
    await ctx.send(f"🤖 **AI Yanıtı:** {mesaj}")

# Etiketlenme ve Yanıt (Reply) Durumları
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Bota etiket atıldıysa veya yanıt verildiyse
    if bot.user.mentioned_in(message) and not message.content.startswith("td!"):
        temiz_mesaj = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if temiz_mesaj:
            await message.channel.send(f"💬 {message.author.mention}, mesajını aldım: **{temiz_mesaj}**")
        else:
            await message.channel.send(f"Efendim {message.author.mention}? Bana `td!ai [mesaj]` yazarak ulaşabilirsin.")

    await bot.process_commands(message)


bot.run(os.environ.get("DISCORD_TOKEN"))