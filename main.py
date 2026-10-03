import os
import discord
from discord.ext import commands
from google import genai

# Discord Bot Kurulumu
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="td/", intents=intents)

# API Anahtarın (Buraya önceden çalışan API anahtarını tırnak içine yapıştır)
API_KEY = "BURAYA_KENDI_API_KEYINI_YAPIŞTIR"

try:
    ai_client = genai.Client(api_key=API_KEY)
except Exception as e:
    ai_client = None
    print(f"API Hatası: {e}")

@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak aktif!")

@bot.command()
async def ai(ctx, *, soru: str = None):
    if not soru:
        await ctx.send("Efendim? Dinliyorum, sorunu yaz: `td/ai <sorun>`")
        return

    if not ai_client:
        await ctx.send("Hata: AI istemcisi başlatılamadı.")
        return

    async with ctx.typing():
        try:
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=soru,
            )
            cevap = response.text
            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i+1900])
            else:
                await ctx.send(cevap)
        except Exception as e:
            await ctx.send(f"Bir hata oluştu: {e}")

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
