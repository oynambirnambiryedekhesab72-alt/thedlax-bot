# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.0 - VIP modülü

main.py bunu v18.py'den sonra otomatik yükler. Bu dosya yoksa bot yine açılır.
Komutlar (hepsi hem td!komut hem /komut):
  👑 VIP   : vipkur, vipver, vipal, viplistesi, vip, vipgunluk  (3 kademe: VIP, VIP+, VIP MAX)
  ✨ VIP+  : viprol (kişisel renkli rol), vipkanal (VIP'lere özel kanal)
  🎨 Çizim : ciz (yapay zekayla resim çizer, sadece VIP)

VIP avantajları:
  - VIP rolü (süreli ya da kalıcı, süre dolunca rol otomatik alınır, bitmeden 1 gün önce DM uyarısı)
  - vipgunluk: günlük bonus + her gün üst üste alırsan seri bonusu
  - Rol marketinde indirim
  - Kişisel rol (kendi adın + istediğin renk) ve VIP'lere özel sohbet kanalı
  - ciz: yapay zekayla resim çizme (Gemini)
  - Ülke Topları'nda günlük bedava top ve daha iyi bonuslar (v20_toplar.py)
Veriler veri_v20.json dosyasında tutulur.
"""
import io
import os
import json
import time
import atexit
import asyncio
import base64
import datetime
import urllib.request
import urllib.error

import discord
from discord import app_commands
from discord.ext import commands
from v15 import eko_ekle, para, xp_ekle, riskli_rol, NO_PING

DOSYA = "veri_v20.json"
TR = datetime.timezone(datetime.timedelta(hours=3))

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
VIP_ROL_ADI = "👑 VIP"       # vipkur rol vermezsen bu adla rol açar
VIP_GUNLUK_PARA = 500        # vipgunluk: verilen para
VIP_GUNLUK_XP = 100          # vipgunluk: verilen XP
VIP_GUNLUK_SURE = 86400      # vipgunluk bekleme süresi (saniye)
VIP_SERI_BONUS = 0.10        # her seri günü için +%10 (en fazla VIP_SERI_MAX gün sayılır)
VIP_SERI_MAX = 10
VIP_MAX_GUN = 3650           # vipver için en fazla gün
VIP_UYARI_SURE = 86400       # bitmeye kaç saniye kala DM ile haber verilsin

CIZ_BEKLEME = 30             # ciz: kişi başı bekleme (saniye)
CIZ_MAX_HARF = 500           # tarif en fazla kaç karakter
CIZ_ZAMAN_ASIMI = 75         # çizim en fazla kaç saniye beklensin (sonra hata mesajı verilir)
# Sırayla denenir; model bulunamazsa (404) bir sonrakine geçer.
RESIM_MODELLER = ["gemini-3.1-flash-image", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]

# VIP kademeleri: gunluk = günlük bonus çarpanı, indirim = rol marketi indirimi, ciz = günlük resim hakkı
KADEMELER = {
    1: {"ad": "VIP", "emoji": "👑", "gunluk": 1.0, "indirim": 0.20, "ciz": 10},
    2: {"ad": "VIP+", "emoji": "💎", "gunluk": 1.5, "indirim": 0.30, "ciz": 20},
    3: {"ad": "VIP MAX", "emoji": "🔥", "gunluk": 2.0, "indirim": 0.40, "ciz": 40},
}

GEMINI_KEY = None            # kur() içinde main.py'den alınır (API koduna dokunulmaz)

RENKLER = {
    "kirmizi": 0xE74C3C, "kırmızı": 0xE74C3C, "mavi": 0x3498DB, "yesil": 0x2ECC71, "yeşil": 0x2ECC71,
    "sari": 0xF1C40F, "sarı": 0xF1C40F, "mor": 0x9B59B6, "turuncu": 0xE67E22, "pembe": 0xFF69B4,
    "siyah": 0x23272A, "beyaz": 0xFFFFFF, "altin": 0xFFD700, "altın": 0xFFD700, "turkuaz": 0x1ABC9C,
    "gri": 0x95A5A6, "lacivert": 0x1F3A93, "bordo": 0x800020,
}

# ----------------------------------------------------------------------
# Veri
# ----------------------------------------------------------------------
veri = {"sunucu": {}, "vip": {}, "gunluk": {}, "kisisel": {}, "ciz": {}, "uyari": {}, "kademe": {}}
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


def kademe_al(gid, uid):
    """Kişinin VIP kademesi (1-3). Kademe kaydı yoksa 1."""
    k = veri["kademe"].get(str(gid), {}).get(str(uid), 1)
    return k if k in KADEMELER else 1


def kademe_ad(k):
    b = KADEMELER[k]
    return f"{b['emoji']} {b['ad']}"


def vip_indirim(gid, uid, fiyat):
    """VIP ise fiyata kademesine göre indirim uygular (v18 satinal kullanır)."""
    if vip_mi(gid, uid):
        oran = KADEMELER[kademe_al(gid, uid)]["indirim"]
        if oran:
            return max(1, int(fiyat * (1 - oran)))
    return fiyat


def bitis_yaz(bitis):
    return "♾️ kalıcı" if not bitis else f"<t:{int(bitis)}:R>"


def renk_coz(metin):
    """'#ff8800', 'ff8800' ya da 'kırmızı' -> sayı. Olmazsa None."""
    m = metin.strip().lower()
    if m in RENKLER:
        return RENKLER[m]
    m = m.lstrip("#")
    if len(m) == 6:
        try:
            return int(m, 16)
        except ValueError:
            return None
    return None


# ----------------------------------------------------------------------
# 🎨 Yapay zekayla resim çizme (Gemini)
# ----------------------------------------------------------------------
def resim_cikar(sonuc):
    """Gemini cevabından resmi çıkarır. (bayt, neden) döner; neden: '', 'engel', 'bos'."""
    if (sonuc.get("promptFeedback") or {}).get("blockReason"):
        return None, "engel"
    adaylar = sonuc.get("candidates") or []
    if not adaylar:
        return None, "bos"
    for parca in (adaylar[0].get("content") or {}).get("parts") or []:
        inline = parca.get("inlineData") or parca.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), ""
    if str(adaylar[0].get("finishReason", "")).upper() in ("SAFETY", "IMAGE_SAFETY", "PROHIBITED_CONTENT"):
        return None, "engel"
    return None, "bos"


def resim_model(model, tarif):
    """Tek bir modele sorar (ayrı thread'de çalışır). (png_bayt, hata_kodu, detay) döner."""
    if not GEMINI_KEY:
        return None, "anahtar", "API anahtarı bulunamadı"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": tarif}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": GEMINI_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=40) as r:
            sonuc = json.loads(r.read().decode("utf-8"))
        bayt, neden = resim_cikar(sonuc)
        if bayt:
            return bayt, "", ""
        return None, neden, "model resim döndürmedi" if neden == "bos" else "güvenlik filtresi"
    except urllib.error.HTTPError as e:
        govde = e.read().decode("utf-8", errors="ignore")
        try:
            detay = json.loads(govde).get("error", {}).get("message", govde)
        except Exception:
            detay = govde
        print(f"Resim hatası ({model}) HTTP {e.code}: {detay[:300]}")
        kod = "kota" if e.code == 429 else ("yetki" if e.code in (400, 403) else f"HTTP {e.code}")
        return None, kod, f"HTTP {e.code}: {detay[:200]}"
    except Exception as e:
        print(f"Resim hatası ({model}): {e!r}")
        return None, type(e).__name__, repr(e)[:200]


def resim_uret(tarif):
    """Modelleri sırayla dener. (png_bayt, hata_kodu) döner."""
    son = "bilinmiyor"
    for model in RESIM_MODELLER:
        bayt, kod, _ = resim_model(model, tarif)
        if bayt:
            return bayt, ""
        if kod in ("engel", "kota", "anahtar"):
            return None, kod              # başka model denemenin faydası yok
        son = kod
    return None, son


CIZ_HATA = {
    "anahtar": "❌ Yapay zeka anahtarı bulunamadı.",
    "engel": "🚫 Bu isteği çizemem (güvenlik filtresine takıldı). Başka bir şey dene.",
    "kota": "⏳ Yapay zeka şu an çok yoğun ya da günlük kotası doldu. Biraz sonra tekrar dene.",
    "yetki": "❌ Anahtarın resim üretmeye yetkisi yok gibi görünüyor (ücretli plan gerekebilir).",
    "bos": "❌ Yapay zeka bu sefer resim üretemedi, tarifi değiştirip tekrar dene.",
    "zaman": "⏳ Çizim çok uzun sürdü, bir daha dene.",
}


# ----------------------------------------------------------------------
# Yardım satırları (/help menüsüne eklenir)
# ----------------------------------------------------------------------
YARDIM = {
    "👑 VIP (v2.0)": [
        "`vipkur [@rol]` VIP rolünü ayarla (boşsa 👑 VIP rolü açılır) (Sunucuyu Yönet)",
        "`vipver @kişi [gün] [kademe 1-3]` VIP ver: 1=VIP, 2=VIP+, 3=VIP MAX (gün yazmazsan kalıcı) (Rolleri Yönet)",
        "`vipal @kişi` VIP'liği al  •  `viplistesi` VIP'leri listele",
        "`vipkanal` VIP'lere özel sohbet kanalı aç (Kanalları Yönet)",
        "`vip [@kişi]` VIP durumu ve avantajlar",
        f"`vipgunluk` günlük VIP bonusu (+{VIP_GUNLUK_PARA} 🪙 +{VIP_GUNLUK_XP} XP, seri bonuslu)",
        "`viprol <renk> [isim]` kendi renkli rolünü yap (VIP)",
        "`ciz <tarif>` yapay zekayla resim çiz (VIP)  •  `ciztest` çizim hatasını göster (Sunucuyu Yönet)",
    ],
}


class V20(commands.Cog):
    def __init__(self, bot, g):
        self.bot = bot
        self.g = g
        self.gorev = None
        self.ciz_son = {}

    def cog_unload(self):
        if self.gorev is not None:
            self.gorev.cancel()

    @staticmethod
    def vip_rol(guild):
        rid = veri["sunucu"].get(str(guild.id), {}).get("rol")
        return guild.get_role(rid) if rid else None

    @staticmethod
    async def kisisel_sil(guild, uid):
        rid = veri["kisisel"].get(str(guild.id), {}).pop(str(uid), None)
        if rid is None:
            return
        isaretle20()
        rol = guild.get_role(rid)
        if rol is not None:
            try:
                await rol.delete(reason="VIP bitti, kişisel rol silindi")
            except discord.HTTPException:
                pass

    # ================= 👑 Komutlar =================
    @commands.hybrid_command(name="vipkur", usage="[@rol]")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def vipkur(self, ctx, rol: discord.Role = None):
        """VIP rolünü ayarla (rol yazmazsan 👑 VIP rolü açılır)"""
        await ctx.defer()
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

    @commands.hybrid_command(name="vipver", aliases=["vipekle"], usage="@kişi [gün] [kademe 1-3]")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def vipver(self, ctx, uye: discord.Member, gun: int = 0, kademe: int = 1):
        """Birine VIP ver: gün (0=kalıcı) ve kademe (1=VIP, 2=VIP+, 3=VIP MAX)"""
        if uye.bot:
            return await ctx.send("🤖 Botlara VIP verilmez.")
        rol = self.vip_rol(ctx.guild)
        if rol is None:
            return await ctx.send("❌ VIP rolü ayarlı değil. Önce `td!vipkur` yaz.")
        if not 0 <= gun <= VIP_MAX_GUN:
            return await ctx.send(f"❌ Gün 0 (kalıcı) ile {VIP_MAX_GUN} arasında olmalı.")
        if kademe not in KADEMELER:
            return await ctx.send("❌ Kademe 1 (VIP), 2 (VIP+) ya da 3 (VIP MAX) olmalı.")
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
        veri["kademe"].setdefault(str(ctx.guild.id), {})[uid] = kademe
        isaretle20()
        await ctx.send(f"{KADEMELER[kademe]['emoji']} {uye.mention} artık **{KADEMELER[kademe]['ad']}**! "
                       f"Süre: {bitis_yaz(bitis)}", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="vipal", aliases=["vipsil"], usage="@kişi")
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
        veri["kademe"].get(str(ctx.guild.id), {}).pop(str(uye.id), None)
        isaretle20()
        await self.kisisel_sil(ctx.guild, uye.id)
        if rolde:
            try:
                await uye.remove_roles(rol, reason=f"{ctx.author} VIP'liği aldı")
            except discord.HTTPException:
                return await ctx.send("❌ Rol alınamadı (rol sırası ya da yetki sorunu).")
        await ctx.send(f"✅ {uye.mention} kişisinin VIP'liği alındı.", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="viplistesi", aliases=["viplist", "viplar"])
    @commands.guild_only()
    async def viplistesi(self, ctx):
        """VIP üyeleri listele"""
        simdi = time.time()
        liste = [(u, b) for u, b in vip_kayit(ctx.guild.id).items() if b == 0 or b > simdi]
        if not liste:
            return await ctx.send("📭 Sunucuda VIP yok.")
        liste.sort(key=lambda x: (x[1] == 0, x[1]))
        satirlar = [f"{kademe_ad(kademe_al(ctx.guild.id, u))} <@{u}> — {bitis_yaz(b)}" for u, b in liste[:25]]
        e = discord.Embed(title=f"👑 VIP listesi ({len(liste)})", description="\n".join(satirlar),
                          color=discord.Color.gold())
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="vip", usage="[@kişi]")
    @commands.guild_only()
    async def vip(self, ctx, uye: discord.Member = None):
        """VIP durumunu ve avantajları göster"""
        uye = uye or ctx.author
        bitis = vip_kayit(ctx.guild.id).get(str(uye.id))
        aktif = vip_mi(ctx.guild.id, uye.id)
        k = kademe_al(ctx.guild.id, uye.id)
        b = KADEMELER[k]
        e = discord.Embed(
            title=f"{b['emoji']} {uye.display_name}",
            description=f"Durum: **{kademe_ad(k)}** ✅ ({bitis_yaz(bitis)})" if aktif else "Durum: VIP değil ❌",
            color=discord.Color.gold() if aktif else discord.Color.dark_grey())
        seri = veri["gunluk"].get(str(ctx.guild.id), {}).get(str(uye.id))
        seri_yazi = f" (🔥 {seri['seri']} gün serisi)" if aktif and isinstance(seri, dict) and seri.get("seri", 0) > 1 else ""
        avantaj = [
            f"🎁 `vipgunluk`: günde bir **{para(int(VIP_GUNLUK_PARA * b['gunluk']))} 🪙 + "
            f"{int(VIP_GUNLUK_XP * b['gunluk'])} XP**, üst üste alırsan seri bonusu{seri_yazi}",
        ]
        if b["indirim"]:
            avantaj.append(f"🛒 Rol marketinde **%{b['indirim'] * 100:g}** indirim")
        avantaj += [
            f"🎨 `ciz`: yapay zekayla günde **{b['ciz']}** resim çiz",
            "✨ `viprol`: kendi adın ve renginle kişisel rol",
            "💬 VIP'lere özel sohbet kanalı (`vipkanal` ile açılır)",
            "🌍 Ülke Topları: günlük bedava `vipball` ve daha iyi bonuslar",
            "👑 Özel VIP rolü",
        ]
        if aktif and k < max(KADEMELER):
            sonraki = KADEMELER[k + 1]
            avantaj.append(f"⬆️ Sıradaki kademe **{sonraki['emoji']} {sonraki['ad']}**: "
                           f"günlük bonus x{sonraki['gunluk']:g}, %{sonraki['indirim'] * 100:g} indirim, "
                           f"günde {sonraki['ciz']} resim")
        e.add_field(name="Avantajlar", value="\n".join(avantaj), inline=False)
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="vipgunluk", aliases=["vipdaily"])
    @commands.guild_only()
    async def vipgunluk(self, ctx):
        """VIP'lere özel günlük bonus (seri bonuslu)"""
        if not vip_mi(ctx.guild.id, ctx.author.id):
            return await ctx.send("👑 Bu komut sadece VIP'ler içindir.")
        d = veri["gunluk"].setdefault(str(ctx.guild.id), {})
        simdi = time.time()
        kayit = d.get(str(ctx.author.id), 0)
        if isinstance(kayit, dict):                 # yeni biçim
            son, seri = kayit.get("son", 0), kayit.get("seri", 0)
        else:                                       # eski biçim (sadece zaman)
            son, seri = kayit, (1 if kayit else 0)
        if simdi - son < VIP_GUNLUK_SURE:
            return await ctx.send(f"⏳ VIP bonusunu zaten aldın. <t:{int(son + VIP_GUNLUK_SURE)}:R> tekrar alabilirsin.")
        seri = seri + 1 if (son and simdi - son <= VIP_GUNLUK_SURE * 2) else 1
        d[str(ctx.author.id)] = {"son": simdi, "seri": seri}
        isaretle20()
        kc = KADEMELER[kademe_al(ctx.guild.id, ctx.author.id)]["gunluk"]
        carpan = 1 + VIP_SERI_BONUS * (min(seri, VIP_SERI_MAX) - 1)
        miktar = int(VIP_GUNLUK_PARA * kc * carpan)
        xp = int(VIP_GUNLUK_XP * kc * carpan)
        eko_ekle(ctx.guild.id, ctx.author.id, miktar)
        if xp:
            await xp_ekle(ctx.guild, ctx.author, xp, ctx.channel)
        seri_yazi = f"\n🔥 **{seri}. gün serisi** (+%{(carpan - 1) * 100:g} bonus)" if seri > 1 else ""
        await ctx.send(f"{KADEMELER[kademe_al(ctx.guild.id, ctx.author.id)]['emoji']} VIP bonusun: "
                       f"**{para(miktar)} 🪙** ve **{xp} XP**!{seri_yazi}")

    @commands.hybrid_command(name="viprol", usage="<renk> [isim]")
    @app_commands.describe(renk="#ff8800 gibi kod ya da kırmızı, mavi, yeşil, mor...",
                           isim="Rolünde yazacak isim (boşsa adın)")
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def viprol(self, ctx, renk: str, *, isim: str = None):
        """VIP'ler için kişisel renkli rol (adın ve renk seç)"""
        if not vip_mi(ctx.guild.id, ctx.author.id):
            return await ctx.send("👑 Bu komut sadece VIP'ler içindir.")
        vrol = self.vip_rol(ctx.guild)
        if vrol is None or vrol >= ctx.guild.me.top_role:
            return await ctx.send("❌ VIP rolü ayarlı değil ya da benim rolümden yüksek.")
        deger = renk_coz(renk)
        if deger is None:
            return await ctx.send("❌ Renk anlaşılmadı. Örnek: `td!viprol #ff8800` ya da `td!viprol mor Kral`")
        ad = (isim or ctx.author.display_name).replace("@", "").strip()[:28] or "VIP"
        ad = f"👑 {ad}"
        await ctx.defer()
        harita = veri["kisisel"].setdefault(str(ctx.guild.id), {})
        rol = ctx.guild.get_role(harita.get(str(ctx.author.id), 0))
        try:
            if rol is None:
                rol = await ctx.guild.create_role(name=ad, colour=discord.Colour(deger),
                                                  reason=f"{ctx.author} kişisel VIP rolü")
                try:
                    await rol.edit(position=max(1, vrol.position))
                except discord.HTTPException:
                    pass
            else:
                await rol.edit(name=ad, colour=discord.Colour(deger), reason=f"{ctx.author} kişisel rolünü değiştirdi")
            if rol not in ctx.author.roles:
                await ctx.author.add_roles(rol, reason="Kişisel VIP rolü")
        except discord.HTTPException:
            return await ctx.send("❌ Rol oluşturulamadı ya da verilemedi (yetki ya da rol sırası sorunu).")
        harita[str(ctx.author.id)] = rol.id
        isaretle20()
        await ctx.send(f"✨ Kişisel rolün hazır: {rol.mention}", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="vipkanal")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def vipkanal(self, ctx):
        """Sadece VIP'lerin görebildiği sohbet kanalı aç"""
        rol = self.vip_rol(ctx.guild)
        if rol is None:
            return await ctx.send("❌ Önce `td!vipkur` ile VIP rolünü ayarla.")
        ayar = veri["sunucu"].setdefault(str(ctx.guild.id), {})
        mevcut = ctx.guild.get_channel(ayar.get("kanal", 0))
        if mevcut is not None:
            return await ctx.send(f"ℹ️ VIP kanalı zaten var: {mevcut.mention}")
        await ctx.defer()
        izinler = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            rol: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        try:
            kanal = await ctx.guild.create_text_channel(
                "👑┃vip-sohbet", overwrites=izinler, topic="Sadece VIP'lere özel sohbet",
                reason=f"{ctx.author} VIP kanalı açtı")
        except discord.HTTPException:
            return await ctx.send("❌ Kanal açılamadı.")
        ayar["kanal"] = kanal.id
        isaretle20()
        await ctx.send(f"✅ VIP kanalı açıldı: {kanal.mention}")

    @commands.hybrid_command(name="ciz", aliases=["çiz", "draw"], usage="<ne çizilsin>")
    @app_commands.describe(tarif="Ne çizilsin? Ne kadar ayrıntılı yazarsan o kadar güzel olur")
    @commands.guild_only()
    async def ciz(self, ctx, *, tarif: str):
        """VIP'lere özel: yapay zekayla yazdığın şeyin resmini çiz"""
        if not vip_mi(ctx.guild.id, ctx.author.id):
            return await ctx.send("👑 Bu komut sadece VIP'ler içindir.")
        tarif = tarif.strip()
        if len(tarif) < 3:
            return await ctx.send("❌ Ne çizeyim? Biraz daha ayrıntı yaz.")
        if len(tarif) > CIZ_MAX_HARF:
            return await ctx.send(f"❌ Tarif en fazla {CIZ_MAX_HARF} karakter olabilir.")
        simdi = time.time()
        kalan = CIZ_BEKLEME - (simdi - self.ciz_son.get(ctx.author.id, 0))
        if kalan > 0:
            return await ctx.send(f"⏳ {kalan:.0f} saniye sonra tekrar dene.")
        bugun = datetime.datetime.now(TR).strftime("%Y-%m-%d")
        kayit = veri["ciz"].setdefault(str(ctx.author.id), {"gun": bugun, "adet": 0})
        if kayit["gun"] != bugun:
            kayit["gun"], kayit["adet"] = bugun, 0
        limit = KADEMELER[kademe_al(ctx.guild.id, ctx.author.id)]["ciz"]
        if kayit["adet"] >= limit:
            return await ctx.send(f"🎨 Bugünkü {limit} resim hakkını kullandın, yarın tekrar gel.")
        self.ciz_son[ctx.author.id] = simdi
        kayit["adet"] += 1
        isaretle20()
        await ctx.defer()
        durum = await ctx.send("🎨 Çiziyorum... (10-40 saniye sürebilir)")
        try:
            bayt, hata = await asyncio.wait_for(asyncio.to_thread(resim_uret, tarif), CIZ_ZAMAN_ASIMI)
        except asyncio.TimeoutError:
            bayt, hata = None, "zaman"
        except Exception as e:
            print(f"ciz hatası: {e!r}")
            bayt, hata = None, type(e).__name__
        if not bayt:
            kayit["adet"] = max(0, kayit["adet"] - 1)      # başarısız denemeler hakkından düşmez
            self.ciz_son.pop(ctx.author.id, None)
            isaretle20()
            yazi = CIZ_HATA.get(hata, f"❌ Resim çizilemedi ({hata}). Sebebini görmek için yetkili `td!ciztest` yazabilir.")
            try:
                return await durum.edit(content=yazi)
            except discord.HTTPException:
                return await ctx.send(yazi)
        kalan_hak = limit - kayit["adet"]
        await ctx.send(
            f"🎨 **{tarif[:200]}**\n_Yapay zeka ile çizildi • bugün {kalan_hak} hakkın kaldı_",
            file=discord.File(io.BytesIO(bayt), filename="resim.png"),
            allowed_mentions=NO_PING)
        try:
            await durum.delete()
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="ciztest", with_app_command=False)
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def ciztest(self, ctx):
        """Resim çizme modellerini dene ve tam hatayı göster (yetkili)"""
        await ctx.send(f"🔎 {len(RESIM_MODELLER)} model deneniyor, bu bir dakika sürebilir...")
        satirlar = []
        for model in RESIM_MODELLER:
            t0 = time.perf_counter()
            try:
                bayt, kod, detay = await asyncio.wait_for(
                    asyncio.to_thread(resim_model, model, "kırmızı bir elma"), 60)
            except asyncio.TimeoutError:
                bayt, kod, detay = None, "zaman", "60 saniyede cevap gelmedi"
            sn = time.perf_counter() - t0
            satirlar.append(f"✅ `{model}` çizdi ({sn:.1f} sn)" if bayt else f"❌ `{model}`: {kod} — {detay[:180]}")
        await ctx.send("🎨 **Çizim testi**\n" + "\n".join(satirlar))

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
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue                          # sunucu şu an erişilemiyor, sonra tekrar dener
            uyarilar = veri["uyari"].setdefault(gid, {})
            for uid, bitis in list(kayit.items()):
                if not bitis:
                    continue
                uye = guild.get_member(int(uid))
                if bitis > simdi:
                    # bitmeye 1 gün kala bir kere DM ile haber ver
                    if bitis - simdi <= VIP_UYARI_SURE and uyarilar.get(uid) != bitis and uye is not None:
                        uyarilar[uid] = bitis
                        isaretle20()
                        try:
                            await uye.send(f"👑 **{guild.name}** sunucusundaki VIP süren {bitis_yaz(bitis)} bitecek.")
                        except discord.HTTPException:
                            pass
                    continue
                rol = self.vip_rol(guild)
                if rol is not None and uye is not None and rol in uye.roles:
                    try:
                        await uye.remove_roles(rol, reason="VIP süresi doldu")
                    except discord.HTTPException:
                        pass
                await self.kisisel_sil(guild, uid)
                kayit.pop(uid, None)
                uyarilar.pop(uid, None)
                veri["kademe"].get(gid, {}).pop(uid, None)
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
    global GEMINI_KEY
    GEMINI_KEY = g.get("GEMINI_KEY")      # main.py'deki mevcut anahtar; API koduna dokunulmaz
    yukle()
    cog = V20(bot, g)
    await bot.add_cog(cog)
    cog.gorev = asyncio.create_task(cog.dongu())
    atexit.register(lambda: kaydet() if kirli else None)
    g["EK_KATEGORILER"].update(YARDIM)
    print(f"v20 yüklendi: VIP + ciz komutları hazır (anahtar {'var' if GEMINI_KEY else 'YOK'}).")

    # Discord en fazla 100 slash komutuna izin verir; aşılırsa HİÇBİRİ kaydolmaz.
    # Sınır aşılırsa v20 komutlarının slash halini (td! halı kalır) önem sırasına göre çıkar.
    fazla = len(bot.tree.get_commands()) - 100
    if fazla > 0:
        cikarilan = []
        for ad in ("viprol", "vipkanal", "vipal", "vipver", "vipkur", "viplistesi", "vipgunluk", "vip", "ciz"):
            if fazla <= 0:
                break
            if bot.tree.remove_command(ad) is not None:
                cikarilan.append(ad)
                fazla -= 1
        print(f"Slash sınırı (100) aşıldı, şu komutlar sadece td! ile çalışacak: {', '.join(cikarilan)}")
