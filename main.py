import os
import sys
import discord
from discord.ext import commands
from google import genai

# Sistem varsayılan kodlamasını UTF-8'e zorla
os.environ["PYTHONIOENCODING"] = "utf-8"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="td/", intents=intents)

# API Anahtarını birleştiriyoruz
p1 = "AQ.Ab8RN6Kng0vFz7Ib6DRUSf"
p2 = "SaNxhVJCvp_wr35dgBBcGzSG60Gg"
GEMINI_KEY = p1 + p2

try:
    ai_client = genai.Client(api_key=GEMINI_KEY)
except Exception as e:
    ai_client = None
    print(f"Gemini Başlatma Hatası: {e}")

@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak sorunsuz giriş yaptı!")

@bot.command()
async def ai(ctx, *, soru: str = None):
    """Gemini AI ile sohbet etme komutu"""
    if not soru:
        await ctx.send("Efendim? Sorunu yazmak için: `td/ai <sorun>`")
        return

    if not ai_client:
        await ctx.send("Hata: Gemini istemcisi başlatılamadı!")
        return

    async with ctx.typing():
        try:
            # Gelen metni UTF-8 olarak güvenli formata çevirip gönderiyoruz
            soru_utf8 = soru.encode("utf-8").decode("utf-8")
            
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=soru_utf8,
            )
            
            cevap = response.text
            
            # Cevap metnini UTF-8 formatında doğrula
            if isinstance(cevap, bytes):
                cevap = cevap.decode("utf-8", errors="replace")

            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i+1900])
            else:
                await ctx.send(cevap)

        except Exception as e:
            await ctx.send(f"Bir hata oluştu: {str(e)}")

token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")

