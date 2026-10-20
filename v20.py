# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.0 - VIP modülü

main.py bunu v18.py'den sonra otomatik yükler. Bu dosya yoksa bot yine açılır.
İçindekiler:
  - 👑 VIP : vipkur, vipver, vipal, viplistesi, vip, vipgunluk
VIP avantajları:
  - VIP rolü (süreli ya da kalıcı, süre dolunca rol otomatik alınır)
  - `vipgunluk`: sadece VIP'lerin alabildiği günlük bonus (🪙 + XP)
  - Rol marketinde indirim
Veriler veri_v20.json dosyasında tutulur.
"""
import os
import json
import time
import atexit
import asyncio

import discord
from discord.ext import commands
from v15 import eko_ekle, para, xp_ekle, riskli_rol, NO_PING

DOSYA = "veri_v20.json"

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
VIP_ROL_ADI = "👑 VIP"       # vipkur rol vermezsen bu adla rol açar
VIP_GUNLUK_PARA = 500        # vipgunluk: verilen para
VIP_GUNLUK_XP = 100          # vipgunluk: verilen XP
VIP_GUNLUK_SURE = 86400      # vipgunluk bekleme süresi (saniye)
VIP_MARKET_INDIRIM = 0.20    # rol marketinde VIP indirimi (0.20 = %20, 0 yaparsan kapanır)
VIP_MAX_GUN = 3650           # vipver için en fazla gün

# ----------------------------------------------------------------------
# Veri
# ----------------------------------------------------------------------
veri = {"sunucu": {}, "vip": {}, "gunluk": {}}
kirli = False


def isaretle20():
    global kirli
    kirli = True


def yukle():
    try:
        with open(DOSYA, "r", encoding="utf-8") as f:
            v = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"v20 verisi okunamadı: {e!r}")
        return
    for k in veri:
        if isinstance(v.get(k), dict):
            veri[k] = v[k]


def kaydet():
    global kirli
    gecici = DOSYA + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        os.replace(gecici, DOSYA)
        kirli = False
    except Exception as e:
        print(f"v20 verisi kaydedilemedi: {e!r}")


def vip_kayit(gid):
    """{kullanıcı_id: bitiş_zamanı}  (0 = kalıcı)"""
    return veri["vip"].setdefault(str(gid), {})


def vip_mi(gid, uid):
    bitis = veri["vip"].get(str(gid), {}).get(str(uid))
    return bitis is not None and (bitis == 0 or bitis > time.time())


def vip_indirim(gid, uid, fiyat):
    """VIP ise fiyata indirim uygular (v18 satinal kullanır)."""
    if VIP_MARKET_INDIRIM and vip_mi(gid, uid):
        return max(1, int(fiyat * (1 - VIP_MARKET_INDIRIM)))
    return fiyat


def bitis_yaz(bitis):
    return "♾️ kalıcı" if not bitis else f"<t:{int(bitis)}:R>"


# ----------------------------------------------------------------------
# Yardım satırları (/help menüsüne eklenir)
# ----------------------------------------------------------------------
YARDIM = {
    "👑 VIP (v2.0)": [
        "`vipkur [@rol]` VIP rolünü ayarla (boşsa 👑 VIP rolü açılır) (Sunucuyu Yönet)",
        "`vipver @kişi [gün]` VIP ver (gün yazmazsan kalıcı) (Rolleri Yönet)",
        "`vipal @kişi` VIP'liği al  •  `viplistesi` VIP'leri listele",
        "`vip [@kişi]` VIP durumu ve avantajlar",
        f"`vipgunluk` VIP'lere özel günlük bonus (+{VIP_GUNLUK_PARA} 🪙 +{VIP_GUNLUK_XP} XP)",
    ],
}


class V20(commands.Cog):
    def __init__(self, bot, g):
        self.bot = bot
        self.g = g
        self.gorev = None

    def cog_unload(self):
        if self.gorev is not None:
            self.gorev.cancel()

    @staticmethod
    def vip_rol(guild):
        rid = veri["sunucu"].get(str(guild.id), {}).get("rol")
        return guild.get_role(rid) if rid else None

    # ================= 👑 Komutlar =================
    @commands.command(name="vipkur", usage="[@rol]")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def vipkur(self, ctx, rol: discord.Role = None):
        """VIP rolünü ayarla (rol yazmazsan 👑 VIP rolü açılır)"""
        if rol is None:
            try:
                rol = await ctx.guild.create_role(
                    name=VIP_ROL_ADI, colour=discord.Colour.gold(), hoist=True,
                    reason=f"{ctx.author} VIP rolü kurdu")
            except discord.HTTPException:
                return await ctx.send("❌ Rol oluşturulamadı. Botun **Rolleri Yönet** yetkisi var mı?")
        else:
            if rol.managed or rol.is_default() or rol >= ctx.guild.me.top_role:
                return await ctx.send("❌ Bu rolü veremem (rolüm onun altında kalıyor ya da özel bir rol).")
            if riskli_rol(rol):
                return await ctx.send("❌ Yetkili bir rol VIP rolü olamaz.")
            if ctx.author.id != ctx.guild.owner_id and rol >= ctx.author.top_role:
                return await ctx.send("❌ Bu rol senin rolünle aynı ya da senden yüksek.")
        veri["sunucu"].setdefault(str(ctx.guild.id), {})["rol"] = rol.id
        isaretle20()
        await ctx.send(
            f"✅ VIP rolü {rol.mention} olarak ayarlandı.\n"
            f"VIP vermek için: `td!vipver @kişi [gün]`", allowed_mentions=NO_PING)

    @commands.command(name="vipver", aliases=["vipekle"], usage="@kişi [gün]")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def vipver(self, ctx, uye: discord.Member, gun: int = 0):
        """Birine VIP ver (gün yazmazsan kalıcı)"""
        if uye.bot:
            return await ctx.send("🤖 Botlara VIP verilmez.")
        rol = self.vip_rol(ctx.guild)
        if rol is None:
            return await ctx.send("❌ VIP rolü ayarlı değil. Önce `td!vipkur` yaz.")
        if not 0 <= gun <= VIP_MAX_GUN:
            return await ctx.send(f"❌ Gün 0 (kalıcı) ile {VIP_MAX_GUN} arasında olmalı.")
        if rol >= ctx.guild.me.top_role:
            return await ctx.send("❌ VIP rolü benim rolümden yüksek, veremiyorum.")
        kayit = vip_kayit(ctx.guild.id)
        uid = str(uye.id)
        simdi = time.time()
        onceki = kayit.get(uid)
        if onceki == 0 and gun > 0:
            return await ctx.send(f"ℹ️ **{uye.display_name}** zaten kalıcı VIP.", allowed_mentions=NO_PING)
        if gun == 0:
            bitis = 0
        else:
            temel = onceki if (onceki and onceki > simdi) else simdi   # süreli VIP'e gün eklenir
            bitis = temel + gun * 86400
        try:
            if rol not in uye.roles:
                await uye.add_roles(rol, reason=f"{ctx.author} VIP verdi")
        except discord.HTTPException:
            return await ctx.send("❌ Rol verilemedi (rol sırası ya da yetki sorunu).")
        kayit[uid] = bitis
        isaretle20()
        await ctx.send(f"👑 {uye.mention} artık VIP! Süre: {bitis_yaz(bitis)}", allowed_mentions=NO_PING)

    @commands.command(name="vipal", aliases=["vipsil"], usage="@kişi")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def vipal(self, ctx, uye: discord.Member):
        """Birinin VIP'liğini al"""
        rol = self.vip_rol(ctx.guild)
        kayitli = vip_kayit(ctx.guild.id).pop(str(uye.id), None) is not None
        rolde = rol is not None and rol in uye.roles
        if not kayitli and not rolde:
            return await ctx.send("❌ Bu kişi VIP değil.")
        isaretle20()
        if rolde:
            try:
                await uye.remove_roles(rol, reason=f"{ctx.author} VIP'liği aldı")
            except discord.HTTPException:
                return await ctx.send("❌ Rol alınamadı (rol sırası ya da yetki sorunu).")
        await ctx.send(f"✅ {uye.mention} kişisinin VIP'liği alındı.", allowed_mentions=NO_PING)

    @commands.command(name="viplistesi", aliases=["viplist", "viplar"])
    @commands.guild_only()
    async def viplistesi(self, ctx):
        """VIP üyeleri listele"""
        simdi = time.time()
        liste = [(u, b) for u, b in vip_kayit(ctx.guild.id).items() if b == 0 or b > simdi]
        if not liste:
            return await ctx.send("📭 Sunucuda VIP yok.")
        liste.sort(key=lambda x: (x[1] == 0, x[1]))
        satirlar = [f"<@{u}> — {bitis_yaz(b)}" for u, b in liste[:25]]
        e = discord.Embed(title=f"👑 VIP listesi ({len(liste)})", description="\n".join(satirlar),
                          color=discord.Color.gold())
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.command(name="vip", usage="[@kişi]")
    @commands.guild_only()
    async def vip(self, ctx, uye: discord.Member = None):
        """VIP durumunu ve avantajları göster"""
        uye = uye or ctx.author
        bitis = vip_kayit(ctx.guild.id).get(str(uye.id))
        aktif = vip_mi(ctx.guild.id, uye.id)
        e = discord.Embed(
            title=f"👑 {uye.display_name}",
            description=f"Durum: **VIP** ✅ ({bitis_yaz(bitis)})" if aktif else "Durum: VIP değil ❌",
            color=discord.Color.gold() if aktif else discord.Color.dark_grey())
        avantaj = [f"🎁 `vipgunluk`: günde bir **{para(VIP_GUNLUK_PARA)} 🪙 + {VIP_GUNLUK_XP} XP**"]
        if VIP_MARKET_INDIRIM:
            avantaj.append(f"🛒 Rol marketinde **%{VIP_MARKET_INDIRIM * 100:g}** indirim")
        avantaj.append("👑 Özel VIP rolü")
        e.add_field(name="Avantajlar", value="\n".join(avantaj), inline=False)
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.command(name="vipgunluk", aliases=["vipdaily"])
    @commands.guild_only()
    async def vipgunluk(self, ctx):
        """VIP'lere özel günlük bonus"""
        if not vip_mi(ctx.guild.id, ctx.author.id):
            return await ctx.send("👑 Bu komut sadece VIP'ler içindir.")
        d = veri["gunluk"].setdefault(str(ctx.guild.id), {})
        simdi = time.time()
        son = d.get(str(ctx.author.id), 0)
        if simdi - son < VIP_GUNLUK_SURE:
            return await ctx.send(f"⏳ VIP bonusunu zaten aldın. <t:{int(son + VIP_GUNLUK_SURE)}:R> tekrar alabilirsin.")
        d[str(ctx.author.id)] = simdi
        isaretle20()
        eko_ekle(ctx.guild.id, ctx.author.id, VIP_GUNLUK_PARA)
        if VIP_GUNLUK_XP:
            await xp_ekle(ctx.guild, ctx.author, VIP_GUNLUK_XP, ctx.channel)
        await ctx.send(f"👑 VIP bonusun: **{para(VIP_GUNLUK_PARA)} 🪙** ve **{VIP_GUNLUK_XP} XP**!")

    # ================= ⏱️ Olaylar ve döngü =================
    @commands.Cog.listener()
    async def on_member_join(self, uye):
        """Sunucudan çıkıp geri giren VIP'in rolünü geri ver"""
        if uye.bot or not vip_mi(uye.guild.id, uye.id):
            return
        rol = self.vip_rol(uye.guild)
        if rol is not None and rol < uye.guild.me.top_role:
            try:
                await uye.add_roles(rol, reason="VIP rolü geri verildi")
            except discord.HTTPException:
                pass

    async def sure_kontrol(self):
        simdi = time.time()
        for gid, kayit in list(veri["vip"].items()):
            for uid, bitis in list(kayit.items()):
                if not bitis or bitis > simdi:
                    continue
                guild = self.bot.get_guild(int(gid))
                if guild is None:
                    continue                      # sunucu şu an erişilemiyor, sonra tekrar dener
                rol = self.vip_rol(guild)
                uye = guild.get_member(int(uid))
                if rol is not None and uye is not None and rol in uye.roles:
                    try:
                        await uye.remove_roles(rol, reason="VIP süresi doldu")
                    except discord.HTTPException:
                        pass
                kayit.pop(uid, None)
                isaretle20()

    async def dongu(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.sure_kontrol()
                if kirli:
                    kaydet()
            except Exception as e:
                print(f"v20 arka plan hatası: {e!r}")
            await asyncio.sleep(60)


# ----------------------------------------------------------------------
# Yükleme (main.py setup_hook içinden çağrılır)
# ----------------------------------------------------------------------
async def kur(bot, g):
    yukle()
    cog = V20(bot, g)
    await bot.add_cog(cog)
    cog.gorev = asyncio.create_task(cog.dongu())
    atexit.register(lambda: kaydet() if kirli else None)
    g["EK_KATEGORILER"].update(YARDIM)
