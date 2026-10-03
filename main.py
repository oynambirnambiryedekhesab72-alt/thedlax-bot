import os
import ast
import json
import time
import random
import asyncio
import operator
import datetime
import urllib.request
import urllib.error
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
PREFIXLER = ("td/", "td!")
bot = commands.Bot(
    command_prefix=list(PREFIXLER),
    intents=intents,
    help_command=None,
    case_insensitive=True,
)

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
BASLANGIC = time.time()

# Bellekte tutulanlar (bot yeniden başlayınca sıfırlanır)
afk_users = {}        # {kullanici_id: (sebep, zaman)}
uyarilar = {}         # {sunucu_id: {kullanici_id: [(sebep, yetkili_id, zaman)]}}
silinenler = {}       # {kanal_id: (yazar, icerik, zaman)}
arkaplan_gorevleri = set()


# ----------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------
def hiyerarsi_kontrol(ctx, hedef):
    """Yetkili ve bot, hedef üyeye işlem yapabilir mi? (ok, hata_mesaji)"""
    if hedef.id == ctx.guild.owner_id:
        return False, "❌ Sunucu sahibine bunu yapamazsın."
    if hedef.id == ctx.author.id:
        return False, "❌ Bunu kendine yapamazsın."
    if hedef.id == ctx.guild.me.id:
        return False, "❌ Bunu bana yapamazsın."
    if ctx.author.id != ctx.guild.owner_id and hedef.top_role >= ctx.author.top_role:
        return False, "❌ Bu kişinin rolü seninkiyle aynı ya da senden yüksek."
    if hedef.top_role >= ctx.guild.me.top_role:
        return False, "❌ Bu kişinin rolü benimkiyle aynı ya da benden yüksek."
    return True, ""


def sure_yaz(saniye):
    saniye = int(saniye)
    gun, saniye = divmod(saniye, 86400)
    saat, saniye = divmod(saniye, 3600)
    dk, saniye = divmod(saniye, 60)
    parcalar = []
    if gun:
        parcalar.append(f"{gun} gün")
    if saat:
        parcalar.append(f"{saat} saat")
    if dk:
        parcalar.append(f"{dk} dakika")
    if saniye or not parcalar:
        parcalar.append(f"{saniye} saniye")
    return " ".join(parcalar)


_ISLEMLER = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def guvenli_hesapla(ifade):
    def _hesap(node):
        if isinstance(node, ast.Expression):
            return _hesap(node.body)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ISLEMLER:
            sol = _hesap(node.left)
            sag = _hesap(node.right)
            if isinstance(node.op, ast.Pow) and (abs(sag) > 100 or abs(sol) > 1e6):
                raise ValueError("Üs çok büyük")
            return _ISLEMLER[type(node.op)](sol, sag)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            deger = _hesap(node.operand)
            return deger if isinstance(node.op, ast.UAdd) else -deger
        raise ValueError("Geçersiz ifade")

    return _hesap(ast.parse(ifade, mode="eval"))


# ----------------------------------------------------------------------
# Genel olaylar
# ----------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Bot {bot.user} olarak sorunsuz aktif!")


@bot.check
async def sadece_sunucu(ctx):
    if ctx.guild is None and ctx.command.name not in ("ai", "help", "ping"):
        raise commands.NoPrivateMessage()
    return True


@bot.event
async def on_command_error(ctx, error):
    # Komutun kendi hata yakalayıcısı varsa karışma
    if ctx.command is not None and ctx.command.has_error_handler():
        return
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    kullanim = ""
    if ctx.command is not None:
        kullanim = f"`td!{ctx.command.name} {ctx.command.usage or ''}`".replace(" `", "`")

    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ Bu komut sadece sunucuda kullanılır.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bunun için yetkin yok.")
    elif isinstance(error, commands.BotMissingPermissions):
        eksik = ", ".join(error.missing_permissions)
        await ctx.send(f"❌ Benim yetkim eksik: `{eksik}`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Eksik bilgi girdin. Kullanım: {kullanim}")
    elif isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
        await ctx.send(f"❌ Geçersiz değer girdin. Kullanım: {kullanim}")
    elif isinstance(error, discord.Forbidden):
        await ctx.send("❌ Discord bu işlemi yapmama izin vermedi (rol sırası ya da yetki sorunu).")
    elif isinstance(error, commands.CheckFailure):
        return
    else:
        print(f"Komut hatası ({ctx.command}): {error!r}")
        await ctx.send("❌ Bir hata oluştu.")


@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.content:
        return
    silinenler[message.channel.id] = (
        str(message.author),
        message.content,
        int(time.time()),
    )


# ----------------------------------------------------------------------
# AI
# ----------------------------------------------------------------------
@bot.command(name="ai", usage="<soru>")
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


# ----------------------------------------------------------------------
# AFK
# ----------------------------------------------------------------------
@bot.command(name="afk", usage="[sebep]")
async def afk(ctx, *, sebep: str = "Sebep belirtilmedi"):
    """AFK moduna geç"""
    sebep = sebep[:200]
    afk_users[ctx.author.id] = (sebep, int(time.time()))
    await ctx.send(
        f"💤 {ctx.author.mention} artık AFK: **{sebep}**",
        allowed_mentions=NO_PING,
    )


# ----------------------------------------------------------------------
# Kanal yönetimi: yavaş mod, kilit, gizle
# ----------------------------------------------------------------------
@bot.command(name="yavasmod", aliases=["yavaşmod", "slowmode"], usage="<saniye>")
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


@bot.command(name="gizle", aliases=["hide"])
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def gizle(ctx):
    """Kanalı herkesten gizle"""
    await ctx.channel.set_permissions(ctx.guild.me, view_channel=True, send_messages=True)
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.view_channel = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("🙈 Kanal herkesten gizlendi.")


@bot.command(name="goster", aliases=["göster", "show"])
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def goster(ctx):
    """Gizli kanalı tekrar göster"""
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.view_channel = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("👀 Kanal tekrar görünür.")


# ----------------------------------------------------------------------
# Moderasyon
# ----------------------------------------------------------------------
@bot.command(name="kick", aliases=["at"], usage="@kişi [sebep]")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx, uye: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeyi sunucudan at"""
    ok, mesaj = hiyerarsi_kontrol(ctx, uye)
    if not ok:
        return await ctx.send(mesaj)
    await uye.kick(reason=f"{ctx.author}: {sebep}")
    await ctx.send(f"👢 **{uye}** sunucudan atıldı. Sebep: {sebep}", allowed_mentions=NO_PING)


@bot.command(name="ban", aliases=["yasakla"], usage="@kişi/ID [sebep]")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx, kisi: discord.User, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeyi sunucudan yasakla"""
    uye = ctx.guild.get_member(kisi.id)
    if uye is not None:
        ok, mesaj = hiyerarsi_kontrol(ctx, uye)
        if not ok:
            return await ctx.send(mesaj)
    elif kisi.id == ctx.author.id:
        return await ctx.send("❌ Bunu kendine yapamazsın.")
    await ctx.guild.ban(kisi, reason=f"{ctx.author}: {sebep}")
    await ctx.send(f"🔨 **{kisi}** yasaklandı. Sebep: {sebep}", allowed_mentions=NO_PING)


@bot.command(name="unban", aliases=["yasakkaldir"], usage="<kişi ID>")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban(ctx, kisi: discord.User):
    """Yasağı kaldır (kişinin ID'sini yaz)"""
    try:
        await ctx.guild.unban(kisi)
    except discord.NotFound:
        return await ctx.send("❌ Bu kişi yasaklı değil.")
    await ctx.send(f"✅ **{kisi}** kişisinin yasağı kaldırıldı.", allowed_mentions=NO_PING)


@bot.command(name="timeout", aliases=["sustur", "mute"], usage="@kişi <dakika> [sebep]")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def timeout(ctx, uye: discord.Member, dakika: int, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeyi belirli dakika susturur (en fazla 40320 dk = 28 gün)"""
    if dakika < 1 or dakika > 40320:
        return await ctx.send("❌ Süre 1 ile 40320 dakika arasında olmalı.")
    ok, mesaj = hiyerarsi_kontrol(ctx, uye)
    if not ok:
        return await ctx.send(mesaj)
    await uye.timeout(datetime.timedelta(minutes=dakika), reason=f"{ctx.author}: {sebep}")
    await ctx.send(
        f"🔇 **{uye}** {dakika} dakika susturuldu. Sebep: {sebep}",
        allowed_mentions=NO_PING,
    )


@bot.command(name="untimeout", aliases=["unmute", "susturkaldir"], usage="@kişi")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def untimeout(ctx, uye: discord.Member):
    """Susturmayı kaldır"""
    await uye.timeout(None, reason=f"{ctx.author} susturmayı kaldırdı")
    await ctx.send(f"🔊 **{uye}** susturması kaldırıldı.", allowed_mentions=NO_PING)


@bot.command(name="temizle", aliases=["sil", "purge", "clear"], usage="<1-100>")
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def temizle(ctx, adet: int):
    """Kanaldan toplu mesaj sil"""
    if adet < 1 or adet > 100:
        return await ctx.send("❌ 1 ile 100 arasında bir sayı gir.")
    silinen = await ctx.channel.purge(limit=adet + 1)
    await ctx.send(f"🧹 {max(len(silinen) - 1, 0)} mesaj silindi.", delete_after=5)


@bot.command(name="warn", aliases=["uyar"], usage="@kişi [sebep]")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, uye: discord.Member, *, sebep: str = "Sebep belirtilmedi"):
    """Üyeyi uyar (uyarı listesine ekler)"""
    if uye.bot:
        return await ctx.send("❌ Botları uyaramazsın.")
    liste = uyarilar.setdefault(ctx.guild.id, {}).setdefault(uye.id, [])
    liste.append((sebep[:200], ctx.author.id, int(time.time())))
    await ctx.send(
        f"⚠️ **{uye}** uyarıldı ({len(liste)}. uyarı). Sebep: {sebep}",
        allowed_mentions=NO_PING,
    )


@bot.command(name="warnings", aliases=["uyarilar", "uyarılar"], usage="[@kişi]")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, uye: discord.Member = None):
    """Üyenin uyarılarını göster"""
    uye = uye or ctx.author
    liste = uyarilar.get(ctx.guild.id, {}).get(uye.id, [])
    if not liste:
        return await ctx.send(f"✅ **{uye}** kişisinin uyarısı yok.", allowed_mentions=NO_PING)
    satirlar = [
        f"**{i}.** {sebep} — <@{yetkili}> (<t:{zaman}:R>)"
        for i, (sebep, yetkili, zaman) in enumerate(liste[-10:], start=1)
    ]
    embed = discord.Embed(
        title=f"⚠️ {uye} uyarıları ({len(liste)})",
        description="\n".join(satirlar),
        color=discord.Color.orange(),
    )
    await ctx.send(embed=embed, allowed_mentions=NO_PING)


@bot.command(name="clearwarns", aliases=["uyarisil", "uyarısil"], usage="@kişi")
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, uye: discord.Member):
    """Üyenin tüm uyarılarını sil"""
    uyarilar.get(ctx.guild.id, {}).pop(uye.id, None)
    await ctx.send(f"🧽 **{uye}** kişisinin uyarıları silindi.", allowed_mentions=NO_PING)


@bot.command(name="nick", aliases=["takmaad"], usage="@kişi [yeni isim]")
@commands.has_permissions(manage_nicknames=True)
@commands.bot_has_permissions(manage_nicknames=True)
async def nick(ctx, uye: discord.Member, *, isim: str = None):
    """Üyenin takma adını değiştir (isim yazmazsan sıfırlanır)"""
    ok, mesaj = hiyerarsi_kontrol(ctx, uye)
    if not ok and uye.id != ctx.author.id:
        return await ctx.send(mesaj)
    await uye.edit(nick=isim[:32] if isim else None, reason=f"{ctx.author}")
    if isim:
        await ctx.send(f"✏️ Takma ad **{isim[:32]}** olarak değiştirildi.", allowed_mentions=NO_PING)
    else:
        await ctx.send("✏️ Takma ad sıfırlandı.")


@bot.command(name="rolver", aliases=["addrole"], usage="@kişi @rol")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def rolver(ctx, uye: discord.Member, rol: discord.Role):
    """Üyeye rol ver"""
    if rol >= ctx.guild.me.top_role or (
        ctx.author.id != ctx.guild.owner_id and rol >= ctx.author.top_role
    ):
        return await ctx.send("❌ Bu rol senin ya da benim yetkimin üstünde.")
    await uye.add_roles(rol, reason=f"{ctx.author}")
    await ctx.send(f"✅ **{uye}** kişisine **{rol.name}** rolü verildi.", allowed_mentions=NO_PING)


@bot.command(name="rolal", aliases=["removerole"], usage="@kişi @rol")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def rolal(ctx, uye: discord.Member, rol: discord.Role):
    """Üyeden rol al"""
    if rol >= ctx.guild.me.top_role or (
        ctx.author.id != ctx.guild.owner_id and rol >= ctx.author.top_role
    ):
        return await ctx.send("❌ Bu rol senin ya da benim yetkimin üstünde.")
    await uye.remove_roles(rol, reason=f"{ctx.author}")
    await ctx.send(f"✅ **{uye}** kişisinden **{rol.name}** rolü alındı.", allowed_mentions=NO_PING)


# ----------------------------------------------------------------------
# Bilgi komutları
# ----------------------------------------------------------------------
@bot.command(name="ping")
async def ping(ctx):
    """Botun gecikmesi"""
    await ctx.send(f"🏓 Pong! **{round(bot.latency * 1000)} ms**")


@bot.command(name="uptime", aliases=["calisma"])
async def uptime(ctx):
    """Bot ne kadardır açık"""
    await ctx.send(f"⏱️ Bot **{sure_yaz(time.time() - BASLANGIC)}** önce başladı.")


@bot.command(name="avatar", aliases=["pp"], usage="[@kişi]")
async def avatar(ctx, uye: discord.Member = None):
    """Profil fotoğrafını büyük göster"""
    uye = uye or ctx.author
    embed = discord.Embed(title=f"🖼️ {uye.display_name}", color=discord.Color.blurple())
    embed.set_image(url=uye.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="userinfo", aliases=["kullanici", "kullanıcı", "ui"], usage="[@kişi]")
async def userinfo(ctx, uye: discord.Member = None):
    """Kullanıcı bilgileri"""
    uye = uye or ctx.author
    roller = [r.mention for r in reversed(uye.roles) if r != ctx.guild.default_role]
    embed = discord.Embed(title=f"👤 {uye}", color=uye.color)
    embed.set_thumbnail(url=uye.display_avatar.url)
    embed.add_field(name="ID", value=str(uye.id), inline=True)
    embed.add_field(name="Bot mu?", value="Evet" if uye.bot else "Hayır", inline=True)
    embed.add_field(
        name="Hesap açılışı",
        value=discord.utils.format_dt(uye.created_at, "F"),
        inline=False,
    )
    if uye.joined_at:
        embed.add_field(
            name="Sunucuya katılış",
            value=discord.utils.format_dt(uye.joined_at, "F"),
            inline=False,
        )
    roller_yazi = " ".join(roller[:15]) or "Yok"
    if len(roller) > 15:
        roller_yazi += f" (+{len(roller) - 15})"
    embed.add_field(name=f"Roller ({len(roller)})", value=roller_yazi, inline=False)
    await ctx.send(embed=embed, allowed_mentions=NO_PING)


@bot.command(name="serverinfo", aliases=["sunucu", "si"])
async def serverinfo(ctx):
    """Sunucu bilgileri"""
    g = ctx.guild
    embed = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Sahip", value=f"<@{g.owner_id}>", inline=True)
    embed.add_field(name="Üye sayısı", value=str(g.member_count), inline=True)
    embed.add_field(name="Kanal", value=f"{len(g.text_channels)} yazı / {len(g.voice_channels)} ses", inline=True)
    embed.add_field(name="Rol sayısı", value=str(len(g.roles)), inline=True)
    embed.add_field(name="Boost", value=f"Seviye {g.premium_tier} ({g.premium_subscription_count})", inline=True)
    embed.add_field(name="ID", value=str(g.id), inline=True)
    embed.add_field(name="Kuruluş", value=discord.utils.format_dt(g.created_at, "F"), inline=False)
    await ctx.send(embed=embed, allowed_mentions=NO_PING)


@bot.command(name="rolbilgi", aliases=["roleinfo"], usage="@rol")
async def rolbilgi(ctx, rol: discord.Role):
    """Rol bilgileri"""
    embed = discord.Embed(title=f"🏷️ {rol.name}", color=rol.color)
    embed.add_field(name="ID", value=str(rol.id), inline=True)
    embed.add_field(name="Üye sayısı", value=str(len(rol.members)), inline=True)
    embed.add_field(name="Sıra", value=str(rol.position), inline=True)
    embed.add_field(name="Etiketlenebilir", value="Evet" if rol.mentionable else "Hayır", inline=True)
    embed.add_field(name="Ayrı gösterilir", value="Evet" if rol.hoist else "Hayır", inline=True)
    embed.add_field(name="Oluşturulma", value=discord.utils.format_dt(rol.created_at, "F"), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="snipe", aliases=["sonsilinen"])
async def snipe(ctx):
    """Kanalda en son silinen mesajı göster"""
    veri = silinenler.get(ctx.channel.id)
    if not veri:
        return await ctx.send("🤷 Bu kanalda silinen mesaj bulamadım.")
    yazar, icerik, zaman = veri
    embed = discord.Embed(description=icerik[:2000], color=discord.Color.red())
    embed.set_author(name=yazar)
    embed.set_footer(text="Son silinen mesaj")
    embed.timestamp = datetime.datetime.fromtimestamp(zaman, datetime.timezone.utc)
    await ctx.send(embed=embed, allowed_mentions=NO_PING)


# ----------------------------------------------------------------------
# Araçlar ve eğlence
# ----------------------------------------------------------------------
@bot.command(name="say", aliases=["söyle", "soyle"], usage="<mesaj>")
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, mesaj: str):
    """Bot senin yazdığını söylesin"""
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(mesaj[:2000], allowed_mentions=NO_PING)


@bot.command(name="embed", usage="Başlık | Açıklama")
@commands.has_permissions(manage_messages=True)
async def embed_komutu(ctx, *, metin: str):
    """Şık bir embed mesaj gönder"""
    if "|" in metin:
        baslik, aciklama = [p.strip() for p in metin.split("|", 1)]
    else:
        baslik, aciklama = "", metin.strip()
    embed = discord.Embed(
        title=baslik[:256] or None,
        description=aciklama[:4000] or None,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"{ctx.author.display_name} tarafından")
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(embed=embed, allowed_mentions=NO_PING)


@bot.command(name="anket", aliases=["poll"], usage="Soru | Seçenek1 | Seçenek2 ...")
@commands.has_permissions(manage_messages=True)
async def anket(ctx, *, metin: str):
    """Anket başlat (seçenek yazmazsan 👍/👎 olur, en fazla 10 seçenek)"""
    parcalar = [p.strip() for p in metin.split("|") if p.strip()]
    soru, secenekler = parcalar[0], parcalar[1:11]
    emojiler = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if secenekler:
        aciklama = "\n".join(f"{emojiler[i]} {s}" for i, s in enumerate(secenekler))
    else:
        aciklama = "👍 Evet   |   👎 Hayır"
    embed = discord.Embed(title=f"📊 {soru[:250]}", description=aciklama, color=discord.Color.green())
    embed.set_footer(text=f"{ctx.author.display_name} başlattı")
    mesaj = await ctx.send(embed=embed)
    tepkiler = emojiler[: len(secenekler)] if secenekler else ["👍", "👎"]
    for e in tepkiler:
        try:
            await mesaj.add_reaction(e)
        except discord.HTTPException:
            break


@bot.command(name="zar", aliases=["dice"], usage="[kaç yüzlü, varsayılan 6]")
async def zar(ctx, yuz: int = 6):
    """Zar at"""
    if yuz < 2 or yuz > 1000000:
        return await ctx.send("❌ Zarın yüz sayısı 2 ile 1000000 arasında olmalı.")
    await ctx.send(f"🎲 {ctx.author.mention} zar attı: **{random.randint(1, yuz)}** (1-{yuz})", allowed_mentions=NO_PING)


@bot.command(name="yazitura", aliases=["yazıtura", "coinflip"])
async def yazitura(ctx):
    """Yazı tura at"""
    await ctx.send(f"🪙 **{random.choice(['Yazı', 'Tura'])}** geldi!")


@bot.command(name="sec", aliases=["seç", "choose"], usage="seçenek1 | seçenek2 | ...")
async def sec(ctx, *, secenekler: str):
    """Seçeneklerden birini rastgele seç"""
    liste = [s.strip() for s in secenekler.split("|") if s.strip()]
    if len(liste) < 2:
        return await ctx.send("❌ En az 2 seçenek yaz, aralarına `|` koy.")
    await ctx.send(f"🤔 Bence: **{random.choice(liste)[:500]}**", allowed_mentions=NO_PING)


@bot.command(name="sor", aliases=["8ball"], usage="<soru>")
async def sor(ctx, *, soru: str):
    """Sihirli 8 topa soru sor"""
    cevaplar = [
        "Kesinlikle evet.", "Bence evet.", "Büyük ihtimalle.", "Görünüşe göre evet.",
        "Şu an belli değil, tekrar sor.", "Bilemiyorum.", "Şimdi söylemesem daha iyi.",
        "Pek sanmıyorum.", "Cevabım hayır.", "Kesinlikle hayır.", "Hiç sanmıyorum.",
    ]
    await ctx.send(f"🎱 {random.choice(cevaplar)}")


@bot.command(name="hesapla", aliases=["calc"], usage="<işlem>  örn: 5*(3+2)")
async def hesapla(ctx, *, ifade: str):
    """Hesap makinesi (+ - * / // % ** ^)"""
    ifade = ifade.replace("^", "**").replace(",", ".").replace("x", "*").replace("×", "*")
    if len(ifade) > 100:
        return await ctx.send("❌ İfade çok uzun.")
    try:
        sonuc = guvenli_hesapla(ifade)
    except Exception:
        return await ctx.send("❌ Hesaplayamadım. Örnek: `td!hesapla 5*(3+2)`")
    if isinstance(sonuc, float) and sonuc.is_integer():
        sonuc = int(sonuc)
    await ctx.send(f"🧮 `{ifade}` = **{str(sonuc)[:200]}**")


@bot.command(name="hatirlat", aliases=["hatırlat", "remind"], usage="<dakika> <mesaj>")
async def hatirlat(ctx, dakika: int, *, mesaj: str):
    """Belirli dakika sonra seni etiketleyip hatırlatır (en fazla 1440 dk)"""
    if dakika < 1 or dakika > 1440:
        return await ctx.send("❌ Süre 1 ile 1440 dakika arasında olmalı.")
    await ctx.send(f"⏰ Tamam, **{dakika} dakika** sonra hatırlatacağım.")

    async def _bekle():
        await asyncio.sleep(dakika * 60)
        try:
            await ctx.channel.send(
                f"⏰ {ctx.author.mention} hatırlatma: {mesaj[:1500]}",
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )
        except Exception:
            pass

    gorev = asyncio.create_task(_bekle())
    arkaplan_gorevleri.add(gorev)
    gorev.add_done_callback(arkaplan_gorevleri.discard)


@bot.command(name="fake", aliases=["fakemesaj"], usage="@kişi <mesaj>")
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


# ----------------------------------------------------------------------
# Yardım
# ----------------------------------------------------------------------
@bot.command(name="help", aliases=["yardim", "yardım", "komutlar"])
async def help_komutu(ctx):
    """Tüm komutları göster"""
    embed = discord.Embed(
        title="📖 THEDLAX Komutları",
        description=(
            "Prefix: `td!` ya da `td/`\n"
            "`< >` zorunlu, `[ ]` isteğe bağlı bilgidir. Etiket için `@` yazıp listeden seç."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🛡️ Moderasyon",
        value=(
            "`kick @kişi [sebep]` Sunucudan at\n"
            "`ban @kişi/ID [sebep]` Yasakla\n"
            "`unban <ID>` Yasağı kaldır\n"
            "`timeout @kişi <dk> [sebep]` Sustur\n"
            "`untimeout @kişi` Susturmayı kaldır\n"
            "`temizle <1-100>` Mesaj sil\n"
            "`warn @kişi [sebep]` Uyar\n"
            "`warnings [@kişi]` Uyarıları göster\n"
            "`clearwarns @kişi` Uyarıları sil\n"
            "`nick @kişi [isim]` Takma ad\n"
            "`rolver @kişi @rol` Rol ver\n"
            "`rolal @kişi @rol` Rol al"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔧 Kanal",
        value=(
            "`yavasmod <saniye>` Yavaş mod (0 = kapat)\n"
            "`lock` / `unlock` Kanalı kilitle / aç\n"
            "`gizle` / `goster` Kanalı gizle / göster"
        ),
        inline=False,
    )
    embed.add_field(
        name="ℹ️ Bilgi",
        value=(
            "`ping` Gecikme\n"
            "`uptime` Bot ne kadardır açık\n"
            "`avatar [@kişi]` Profil fotoğrafı\n"
            "`userinfo [@kişi]` Kullanıcı bilgisi\n"
            "`serverinfo` Sunucu bilgisi\n"
            "`rolbilgi @rol` Rol bilgisi\n"
            "`snipe` Son silinen mesaj"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎮 Araçlar ve Eğlence",
        value=(
            "`ai <soru>` Yapay zekayla sohbet (botu etiketleyebilir ya da mesajına yanıt verebilirsin)\n"
            "`afk [sebep]` AFK ol (mesaj yazınca çıkarsın)\n"
            "`say <mesaj>` Bot söylesin\n"
            "`embed Başlık | Açıklama` Embed mesaj\n"
            "`anket Soru | Seçenek1 | Seçenek2` Anket\n"
            "`zar [yüz]` Zar at\n"
            "`yazitura` Yazı tura\n"
            "`sec a | b | c` Rastgele seç\n"
            "`sor <soru>` Sihirli 8 top\n"
            "`hesapla <işlem>` Hesap makinesi\n"
            "`hatirlat <dk> <mesaj>` Hatırlatıcı\n"
            "`fake @kişi <mesaj>` Kişinin adıyla mesaj"
        ),
        inline=False,
    )
    embed.set_footer(text="Yetki gereken komutlarda ilgili yetkin olmalı.")
    await ctx.send(embed=embed)


# ----------------------------------------------------------------------
# Mesaj dinleyici: AFK + AI (etiket / yanıt)
# ----------------------------------------------------------------------
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
    print("HATA: DISCORD_TOKEN bulunamadı!")