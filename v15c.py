# -*- coding: utf-8 -*-
"""THEDLAX v1.7 - Ses sistemi (özel ses odaları, ses süresi) + yeni komutlar.
v15b.py bunu kendisi yükler; bu dosya yoksa bot yine açılır (sadece bu özellikler olmaz)."""
import time
import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from v15 import *   # v15.py'deki veri, sa(), isaretle(), NO_PING...

OZEL_ODA_LIMIT = 30      # sunucuda aynı anda en fazla kaç özel oda
OZEL_ODA_BEKLEME = 10    # aynı kişi kaç saniyede bir oda açabilir

TOP_CEVAPLAR = [
    ("🟢", "Kesinlikle evet."), ("🟢", "Bence evet."), ("🟢", "Görünüşe göre evet."),
    ("🟢", "Hiç şüphesiz."), ("🟡", "Şimdi söylemesem daha iyi."), ("🟡", "Tekrar sor, odaklanamadım."),
    ("🟡", "Belirsiz, bir daha dene."), ("🔴", "Pek sanmıyorum."), ("🔴", "Cevabım hayır."),
    ("🔴", "Kaynaklarım hayır diyor."), ("🔴", "Kesinlikle hayır."),
]


def ses_ayar(gid):
    s = sa(gid)
    d = s.setdefault("ses", {})
    d.setdefault("olustur", None)   # "➕ Oda Aç" kanalının ID'si
    d.setdefault("odalar", {})      # {kanal_id: sahip_id}
    d.setdefault("sure", {})        # {kullanici_id: toplam_saniye}
    return d


def ses_sure_yaz(sn):
    sn = int(sn)
    gun, sn = divmod(sn, 86400)
    saat, sn = divmod(sn, 3600)
    dk = sn // 60
    p = []
    if gun:
        p.append(f"{gun}g")
    if saat:
        p.append(f"{saat}sa")
    if dk or not p:
        p.append(f"{dk}dk")
    return " ".join(p)


class Ses(commands.Cog):
    """Özel ses odaları + ses süresi sıralaması + birkaç ek komut"""

    def __init__(self, bot, g):
        self.bot = bot
        self.g = g
        self.giris = {}    # {(sunucu, kullanıcı): sayaç başlangıcı}
        self.bekle = {}    # {(sunucu, kullanıcı): son oda açma zamanı}

    # ---------------- yardımcılar ----------------
    @staticmethod
    def sayilir(guild, kanal):
        return kanal is not None and kanal != guild.afk_channel

    async def oda_sil(self, kanal, d):
        d["odalar"].pop(str(kanal.id), None)
        isaretle()
        try:
            await kanal.delete(reason="Özel oda boşaldı")
        except discord.HTTPException:
            pass

    async def oda_olustur(self, uye, kanal, d):
        guild = uye.guild
        anahtar = (guild.id, uye.id)
        simdi = time.time()

        async def at():
            try:
                await uye.move_to(None)
            except discord.HTTPException:
                pass

        if simdi - self.bekle.get(anahtar, 0) < OZEL_ODA_BEKLEME or len(d["odalar"]) >= OZEL_ODA_LIMIT:
            return await at()
        izin = guild.me.guild_permissions
        if not (izin.manage_channels and izin.move_members):
            return
        self.bekle[anahtar] = simdi
        ow = {uye: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)}
        try:
            yeni = await guild.create_voice_channel(
                name=f"🔊 {uye.display_name}"[:100], category=kanal.category,
                overwrites=ow, reason=f"Özel ses odası ({uye})")
        except discord.HTTPException:
            return await at()
        d["odalar"][str(yeni.id)] = uye.id
        isaretle()
        try:
            await uye.move_to(yeni)
        except discord.HTTPException:     # kişi bu arada çıkmış olabilir
            await self.oda_sil(yeni, d)

    def kendi_oda(self, ctx):
        """(kanal, ayar) ya da (None, hata mesajı)"""
        v = ctx.author.voice
        if v is None or v.channel is None:
            return None, "❌ Önce kendi özel odana girmen lazım."
        d = ses_ayar(ctx.guild.id)
        sahip = d["odalar"].get(str(v.channel.id))
        if sahip is None:
            return None, "❌ Bu kanal özel bir oda değil."
        if sahip != ctx.author.id and ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.manage_channels:
            return None, "❌ Bu odanın sahibi sen değilsin."
        return v.channel, d

    # ---------------- olaylar ----------------
    @commands.Cog.listener()
    async def on_ready(self):
        simdi = time.time()
        for guild in self.bot.guilds:
            d = ses_ayar(guild.id)
            for cid in list(d["odalar"]):          # bot kapalıyken boşalan/silinen odaları temizle
                kanal = guild.get_channel(int(cid))
                if kanal is None:
                    d["odalar"].pop(cid, None)
                    isaretle()
                elif not kanal.members:
                    await self.oda_sil(kanal, d)
            for vc in guild.voice_channels:        # şu an seste olanların sayacını başlat
                if self.sayilir(guild, vc):
                    for m in vc.members:
                        if not m.bot:
                            self.giris.setdefault((guild.id, m.id), simdi)

    @commands.Cog.listener()
    async def on_voice_state_update(self, uye, before, after):
        if uye.bot:
            return
        guild = uye.guild
        d = ses_ayar(guild.id)
        anahtar = (guild.id, uye.id)
        simdi = time.time()

        once = self.sayilir(guild, before.channel)
        simdi_mi = self.sayilir(guild, after.channel)
        if not once and simdi_mi:
            self.giris[anahtar] = simdi
        elif once and not simdi_mi:
            t = self.giris.pop(anahtar, None)
            if t:
                d["sure"][str(uye.id)] = d["sure"].get(str(uye.id), 0) + int(simdi - t)
                isaretle()

        if after.channel is not None and after.channel.id == d["olustur"] \
                and (before.channel is None or before.channel.id != after.channel.id):
            await self.oda_olustur(uye, after.channel, d)
        if before.channel is not None and str(before.channel.id) in d["odalar"] and not before.channel.members:
            await self.oda_sil(before.channel, d)

    # ---------------- özel ses odaları ----------------
    @commands.command(name="ozelsesayarla", aliases=["ozelses"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True, move_members=True)
    async def ozelsesayarla(self, ctx):
        """Özel ses odası sistemini kur (➕ Oda Aç kanalı)"""
        d = ses_ayar(ctx.guild.id)
        try:
            kat = await ctx.guild.create_category("🔊 Özel Odalar", reason="Özel ses sistemi")
            kanal = await ctx.guild.create_voice_channel("➕ Oda Aç", category=kat, reason="Özel ses sistemi")
        except discord.HTTPException:
            return await ctx.send("❌ Kanalları oluşturamadım. Botun **Kanalları Yönet** yetkisi var mı?")
        d["olustur"] = kanal.id
        isaretle()
        await ctx.send(f"✅ Hazır! {kanal.mention} kanalına giren herkese kendine ait bir ses odası açılır, "
                       f"oda boşalınca otomatik silinir.\nOda sahibi komutları: `odakilit` `odalimit` `odaisim`")

    @commands.command(name="ozelsesbitir")
    @commands.has_permissions(manage_guild=True)
    async def ozelsesbitir(self, ctx):
        """Özel ses odası sistemini kapat"""
        d = ses_ayar(ctx.guild.id)
        kanal = ctx.guild.get_channel(d["olustur"]) if d["olustur"] else None
        d["olustur"] = None
        isaretle()
        if kanal is not None:
            try:
                await kanal.delete(reason="Özel ses sistemi kapatıldı")
            except discord.HTTPException:
                pass
        await ctx.send("✅ Özel ses sistemi kapatıldı. Açık odalar boşalınca silinir.")

    @commands.hybrid_command(name="odakilit", aliases=["odakilitle"])
    async def odakilit(self, ctx):
        """Özel odanı kilitle / kilidini aç"""
        await ctx.defer()
        kanal, d = self.kendi_oda(ctx)
        if kanal is None:
            return await ctx.send(d)
        rol = ctx.guild.default_role
        ow = kanal.overwrites_for(rol)
        kilitli = ow.connect is False
        ow.connect = None if kilitli else False
        try:
            await kanal.set_permissions(rol, overwrite=ow, reason=f"Oda kilidi ({ctx.author})")
        except discord.HTTPException:
            return await ctx.send("❌ İzinleri değiştiremedim.")
        await ctx.send("🔓 Oda kilidi açıldı, herkes girebilir." if kilitli else "🔒 Oda kilitlendi, yeni kimse giremez.")

    @commands.hybrid_command(name="odalimit", usage="<0-99>")
    @app_commands.describe(sayi="Kişi limiti (0 = sınırsız)")
    async def odalimit(self, ctx, sayi: int):
        """Özel odanın kişi limitini ayarla"""
        await ctx.defer()
        kanal, d = self.kendi_oda(ctx)
        if kanal is None:
            return await ctx.send(d)
        if sayi < 0 or sayi > 99:
            return await ctx.send("❌ Limit 0 ile 99 arasında olmalı (0 = sınırsız).")
        try:
            await kanal.edit(user_limit=sayi, reason=f"Oda limiti ({ctx.author})")
        except discord.HTTPException:
            return await ctx.send("❌ Limiti değiştiremedim.")
        await ctx.send(f"👥 Oda limiti: **{sayi if sayi else 'sınırsız'}**")

    @commands.hybrid_command(name="odaisim", usage="<yeni isim>")
    @app_commands.describe(isim="Odanın yeni adı")
    async def odaisim(self, ctx, *, isim: str):
        """Özel odanın adını değiştir"""
        await ctx.defer()
        kanal, d = self.kendi_oda(ctx)
        if kanal is None:
            return await ctx.send(d)
        isim = isim.strip()[:90]
        if not isim:
            return await ctx.send("❌ İsim boş olamaz.")
        try:
            await kanal.edit(name=f"🔊 {isim}", reason=f"Oda adı ({ctx.author})")
        except discord.HTTPException:
            return await ctx.send("❌ Adı değiştiremedim (Discord kanal adını sık değiştirmeye izin vermez, biraz bekle).")
        await ctx.send(f"✏️ Oda adı: **{isim}**")

    # ---------------- ses süresi ----------------
    def toplam_sure(self, guild, uid):
        d = ses_ayar(guild.id)
        toplam = d["sure"].get(str(uid), 0)
        t = self.giris.get((guild.id, uid))
        if t:
            toplam += int(time.time() - t)
        return toplam

    @commands.hybrid_command(name="sessure", aliases=["sesstat", "sesistatistik"], usage="[@kişi]")
    @app_commands.describe(uye="Bakılacak kişi (boşsa sen)")
    async def sessure(self, ctx, uye: discord.Member = None):
        """Seste geçirdiğin toplam süre ve sıran"""
        uye = uye or ctx.author
        d = ses_ayar(ctx.guild.id)
        benim = self.toplam_sure(ctx.guild, uye.id)
        if benim <= 0:
            return await ctx.send(f"🎙️ {uye.display_name} henüz seste süre biriktirmemiş.", allowed_mentions=NO_PING)
        tum = {int(u): s for u, s in d["sure"].items()}
        for (gid, uid), t in self.giris.items():
            if gid == ctx.guild.id:
                tum[uid] = tum.get(uid, 0) + int(time.time() - t)
        sira = 1 + sum(1 for s in tum.values() if s > benim)
        e = discord.Embed(title=f"🎙️ {uye.display_name} — Ses istatistiği", color=discord.Color.blurple())
        e.add_field(name="Toplam süre", value=f"**{ses_sure_yaz(benim)}**")
        e.add_field(name="Sunucu sırası", value=f"**#{sira}** / {len(tum)}")
        e.set_thumbnail(url=uye.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="seslider", aliases=["sesliderlik"])
    async def seslider(self, ctx):
        """Seste en çok vakit geçirenler"""
        d = ses_ayar(ctx.guild.id)
        tum = {int(u): s for u, s in d["sure"].items()}
        simdi = time.time()
        for (gid, uid), t in self.giris.items():
            if gid == ctx.guild.id:
                tum[uid] = tum.get(uid, 0) + int(simdi - t)
        liste = sorted(((u, s) for u, s in tum.items() if s >= 60), key=lambda x: -x[1])[:10]
        if not liste:
            return await ctx.send("📭 Henüz kimse seste süre biriktirmemiş.")
        madalya = {1: "🥇", 2: "🥈", 3: "🥉"}
        satir = [f"{madalya.get(i, f'**{i}.**')} <@{u}> — **{ses_sure_yaz(s)}**" for i, (u, s) in enumerate(liste, 1)]
        await ctx.send(embed=discord.Embed(title="🎙️ Ses liderleri", description="\n".join(satir),
                                            color=discord.Color.gold()), allowed_mentions=NO_PING)

    # dm ve kanalbilgi komutları v151.py içinde (çakışmasın diye buradan kaldırıldı)
    @commands.hybrid_command(name="sihirlitop", usage="<soru>")
    @app_commands.describe(soru="Sihirli topa sorun")
    async def sihirlitop(self, ctx, *, soru: str):
        """Sihirli 8 topa evet/hayır sorusu sor"""
        simge, cevap = random.choice(TOP_CEVAPLAR)
        e = discord.Embed(color=discord.Color.dark_purple())
        e.add_field(name="❓ Soru", value=soru[:500], inline=False)
        e.add_field(name="🎱 Cevap", value=f"{simge} {cevap}", inline=False)
        await ctx.send(embed=e)


async def kur(bot, g):
    await bot.add_cog(Ses(bot, g))
    # müzik sistemi v151.py içinde (muzik.py ile çakıştığı için buradan yüklenmiyor)
    g["EK_KATEGORILER"]["🔊 Ses (v1.7)"] = [
        "`ozelsesayarla` ➕ Oda Aç kanalı kur (girene özel oda açılır)",
        "`ozelsesbitir` Sistemi kapat",
        "`odakilit` / `odalimit <n>` / `odaisim <ad>` Oda sahibi komutları",
        "`sessure [@kişi]` Seste geçen süre ve sıra",
        "`seslider` Seste en çok vakit geçirenler",
    ]
    g["EK_KATEGORILER"]["✨ Yeni (v1.7)"] = [
        "`sihirlitop <soru>` Sihirli 8 top",
    ]
