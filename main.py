import os
import discord
from discord.ext import commands

# Bot yetkileri (Intents)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Bot aktif! Giriş yapıldı: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Bota etiket atıldığında yanıt verme
    if bot.user in message.mentions:
        await message.channel.send(f'Efendim {message.author.mention}? Dinliyorum!')

    await bot.process_commands(message)

# Render üzerindeki DISCORD_TOKEN değişkenini güvenli şekilde alma
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    bot.run(TOKEN)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")


