import os
import json
import urllib.request
import urllib.error
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="td/", intents=intents)

# API Anahtarın
p1 = "AQ.Ab8RN6I7iSnYkqzuoFQj"
p2 = "LXS5N62GbgEWFRELbzQCuj5FCsechg"
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
        # Denenecek modeller
        modeller = [
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash"
        ]
        
        cevap = None
        detayli_hata = ""

        for model in modeller:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
                headers = {"Content-Type": "application/json; charset=utf-8"}
                payload = {
                    "contents": [
                        {"parts": [{"text": soru}]}
                    ]
                }
                
                data_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method='POST')
                
                with urllib.request.urlopen(req) as response:
                    result_json = json.loads(response.read().decode('utf-8'))
                    cevap = result_json['candidates'][0]['content']['parts'][0]['text']
                    if cevap:
                        break
            except urllib.error.HTTPError as e:
                # Google'ın döndüğü gerçek hata metnini oku
                hata_icerigi = e.read().decode('utf-8', errors='ignore')
                detayli_hata = f"HTTP {e.code}: {hata_icerigi}"
                continue
            except Exception as e:
                detayli_hata = str(e)
                continue

        if cevap:
            if len(cevap) > 1900:
                for i in range(0, len(cevap), 1900):
                    await ctx.send(cevap[i:i+1900])
            else:
                await ctx.send(cevap)
        else:
            await ctx.send(f"**API Detaylı Hata:**\n```{detayli_hata[:1800]}```")

# Botu başlat
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")






