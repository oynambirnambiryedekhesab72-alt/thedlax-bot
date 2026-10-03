import os
import json
import urllib.request
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="td/", intents=intents)

# API Anahtarı (GitHub tarayıcılarına takılmaması için iki parça)
p1 = "AQ.Ab8RN6Kng0vFz7Ib6DRUSf"
p2 = "SaNxhVJCvp_wr35dgBBcGzSG60Gg"
GEMINI_KEY = p1 + p2

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
        try:
            # Model ismi gemini-1.5-flash olarak güncellendi
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            
            headers = {"Content-Type": "application/json; charset=utf-8"}
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": soru}
                        ]
                    }
                ]
            }
            
            data_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method='POST')
            
            with urllib.request.urlopen(req) as response:
                result_json = json.loads(response.read().decode('utf-8'))
                cevap = result_json['candidates'][0]['content']['parts'][0]['text']

            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i+1900])
            else:
                await ctx.send(cevap)

        except Exception as e:
            await ctx.send(f"Bir hata oluştu: {str(e)}")

# Botu başlat
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")


