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
        # Denenecek modeller (SADECE BU KISIM DEĞİŞTİ)
        modeller = [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite"
        ]
        
        cevap = None
        detayli_hata = ""

        for model in modeller:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
                headers = {"Content-Type"