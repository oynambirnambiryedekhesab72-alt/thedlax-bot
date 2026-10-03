import os
import discord
from discord.ext import commands
from google import genai

# Discord Bot Kurulumu - Prefix "td/" olarak ayarlandı
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="td/", intents=intents)

# Gemini API Kurulumu
gemini_key = os.getenv("GEMINI_API_KEY")
ai_client = genai.Client(api_key=gemini_key) if gemini_key else None

@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak sorunsuz giriş yaptı!")

# td/ai <soru> komutu
@bot.command()
async def ai(ctx, *, soru: str = None):
    """Gemini AI ile sohbet etme komutu"""
    if not soru:
        await ctx.send("Efendim? Sorunu yazmak için: `td/ai <sorun>`")
        return

    if not ai_client:
        await ctx.send("Hata: GEMINI_API_KEY Render panelinde ekli değil!")
        return

    async with ctx.typing():
        try:
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=soru,
            )
            cevap = response.text
            
            # Discord mesaj karakter sınırı kontrolü (2000 harf)
            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i+1900])
            else:
                await ctx.send(cevap)
        except Exception as e:
            await ctx.send(f"Bir hata oluştu: {e}")

# Etiketlenme ve Komut İşleyici
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) and not message.mention_everyone:
        await message.channel.send("Efendim? Dinliyorum! Benimle konuşmak için `td/ai <sorun>` yazabilirsin.")

    await bot.process_commands(message)

# Botu başlat
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")
