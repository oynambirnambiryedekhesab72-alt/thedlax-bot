import os
import json
import asyncio
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

MODELLER = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]


def gemini_sor(soru: str):
    hata = ""
    for model in MODELLER:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "x-goog-api-key": GEMINI_KEY,
            }
            payload = {"contents": [{"parts": [{"text": soru}]}]}
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                sonuc = json.loads(r.read().decode("utf-8"))
            return sonuc["candidates"][0]["content"]["parts"][0]["text"], ""
        except urllib.error.HTTPError as e:
            govde = e.read().decode("utf-8", errors="ignore")
            hata = f"{model} -> HTTP {e.code}: {govde}"
        except Exception as e:
            hata = f"{model} -> {e}"
    return None, hata


@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak aktif!")


@bot.command()
async def ai(ctx, *, soru: str = None):
    if not soru:
        return await ctx.send("Efendim? Kullanım: `td/ai <sorun>`")

    async with ctx.typing():
        cevap, hata = await asyncio.to_thread(gemini_sor, soru)

    if cevap:
        for i in range(0, len(cevap), 1900):
            await ctx.send(cevap[i:i + 1900])
    else:
        await ctx.send(f"**API Hatası:**\n```{hata[:1800]}```")


token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")






