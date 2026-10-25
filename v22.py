# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.2 - Yeni özellikler (main.py'deki modül listesine "v22" olarak eklenir)

  ✅ Doğrulama butonu         dogrulamakur @rol [#kanal]  •  dogrulamakapat
  🚨 Raid koruması            raid [ac|kapat|durum|esik <sayı>]
  🎣 RPG ekonomi              balik, maden, envanter, sat, meslek, meslekal, mesai, gelistir, duello
  🪪 Animasyonlu profil kartı kart [@kişi]   (Pillow gerekir: requirements.txt'ye `pillow`)
  🎂 Doğum günü               dogumgunu <gün> <ay>, dogumgunukanal, dogumgunleri, dogumgunusil
  🇹🇷 Türkiye araçları         namaz <şehir>, hava <şehir>, doviz, altin
  📺 YouTube bildirimi        ytekle <kanal> [#duyuru] [@rol], ytliste, ytsil, yttest

Tüm komutlar animasyonludur (mesaj düzenleme animasyonu / GIF).
Spam koruması zaten v15 güvenlik panelinde var (td!guvenlik), burada sadece raid (toplu giriş) koruması eklendi.
"""
import os
import io
import re
import json
import time
import copy
import random
import atexit
import asyncio
import datetime
import xml.etree.ElementTree as ET
from datetime import timedelta, timezone
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from v15 import eko, eko_ekle, para, xp_kayit, seviye_hesapla, siralama_listesi, log, riskli_rol, NO_PING

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_VAR = True
except Exception:                                   # pillow kurulu değilse sadece kart komutu çalışmaz
    PIL_VAR = False

DOSYA = "veri_v22.json"
TR = timezone(timedelta(hours=3))

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
BALIK_BEKLEME = 45
MADEN_BEKLEME = 60
MESAI_BEKLEME = 3600
DUELLO_MIN, DUELLO_MAX = 10, 50000
GELISTIR_MAX = 10
DOGUM_SAAT = 9                  # doğum günü mesajı kaçta atılsın (Türkiye saati)
DOGUM_HEDIYE = 500              # doğum günü hediyesi (0 yaparsan para vermez)
YT_ARALIK = 300                 # YouTube kontrol aralığı (saniye)
YT_MAX = 5                      # sunucuda en fazla kaç YouTube kanalı
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Cookie": "CONSENT=YES+1; SOCS=CAI"}

# ----------------------------------------------------------------------
# Veri
# ----------------------------------------------------------------------
veri = {"sunucu": {}, "env": {}, "dogum": {}, "yt": {}}
kirli = False

VARSAYILAN = {
    "dogrulama": {"rol": None, "kanal": None},
    "raid": {"acik": False, "esik": 6, "saniye": 20, "mod_dk": 10, "bitis": 0},
    "dogum": {"kanal": None, "son": ""},
}


def isaretle22():
    global kirli
    kirli = True


def yukle():
    try:
        with open(DOSYA, "r", encoding="utf-8") as f:
            v = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"v22 verisi okunamadı: {e!r}")
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
        print(f"v22 verisi kaydedilemedi: {e!r}")


def sv(gid):
    d = veri["sunucu"].setdefault(str(gid), {})
    for k, v in VARSAYILAN.items():
        if k not in d:
            d[k] = copy.deepcopy(v)
        else:
            for kk, vv in v.items():
                d[k].setdefault(kk, copy.deepcopy(vv))
    return d


def env(gid, uid):
    e = veri["env"].setdefault(str(gid), {}).setdefault(str(uid), {})
    e.setdefault("esya", {})
    e.setdefault("meslek", None)
    e.setdefault("olta", 1)
    e.setdefault("kazma", 1)
    e.setdefault("cd", {})
    return e


# ----------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------
_TR = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc")


def tr_ascii(t):
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", str(t).translate(_TR).lower()).split())


def sure_yaz(s):
    s = int(s)
    if s >= 3600:
        return f"{s // 3600} sa {(s % 3600) // 60} dk"
    if s >= 60:
        return f"{s // 60} dk {s % 60} sn"
    return f"{s} sn"


def bekleme(e, ad, sure):
    """Beklemesi varsa kalan saniyeyi döner; yoksa sayacı başlatıp 0 döner."""
    simdi = time.time()
    kalan = e["cd"].get(ad, 0) + sure - simdi
    if kalan > 0:
        return int(kalan) + 1
    e["cd"][ad] = simdi
    isaretle22()
    return 0


def bakiye_kontrol(gid, uid, miktar):
    return eko(gid, uid)["bakiye"] >= miktar


async def anim_duzenle(msg, kareler, bekle=0.7):
    """Var olan mesajı kare kare düzenler (animasyon)."""
    for k in kareler:
        await asyncio.sleep(bekle)
        try:
            await msg.edit(embed=k)
        except discord.HTTPException:
            return


async def anim_gonder(ctx, kareler, son, bekle=0.7, view=None):
    """İlk kareyi gönderir, diğerlerini düzenleyerek oynatır, en sonda `son` embed'ini gösterir."""
    msg = await ctx.send(embed=kareler[0])
    await anim_duzenle(msg, kareler[1:], bekle)
    await asyncio.sleep(bekle)
    try:
        await msg.edit(embed=son, view=view)
    except discord.HTTPException:
        msg = await ctx.send(embed=son, view=view)
    return msg


def yukleme_kareleri(baslik, renk, adim=4):
    k = []
    for i in range(adim + 1):
        doluluk = "▰" * (i * 2) + "▱" * ((adim - i) * 2)
        k.append(discord.Embed(title=baslik, description=f"{doluluk} **%{int(i / adim * 100)}**", color=renk))
    return k


async def http_al(url, params=None, json_mi=True, headers=None):
    zaman = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=zaman, headers=headers or {"User-Agent": UA["User-Agent"]}) as s:
        async with s.get(url, params=params) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            return await r.json(content_type=None) if json_mi else await r.text()


# ----------------------------------------------------------------------
# 🎣 RPG: eşyalar
# ----------------------------------------------------------------------
# (ad, emoji, değer, ağırlık)
BALIKLAR = [
    ("Eski Çizme", "🥾", 2, 18), ("Plastik Şişe", "🧴", 3, 12), ("Hamsi", "🐟", 25, 24), ("Sazan", "🐟", 45, 18),
    ("Levrek", "🐠", 80, 12), ("Alabalık", "🐟", 110, 8), ("Lüfer", "🐡", 150, 5),
    ("Kılıç Balığı", "🗡️", 400, 2), ("Hazine Sandığı", "🧰", 1000, 0.6),
]
MADENLER = [
    ("Taş", "🪨", 4, 30), ("Kömür", "⚫", 12, 28), ("Bakır", "🟤", 30, 16), ("Demir", "⚙️", 60, 12),
    ("Altın Parçası", "🟡", 150, 8), ("Elmas", "💎", 500, 2), ("Zümrüt", "💚", 900, 0.8),
]
ESYA = {ad: (emoji, deger) for ad, emoji, deger, _ in BALIKLAR + MADENLER}

# ad: (gereken seviye, en az maaş, en çok maaş, emoji)
MESLEKLER = {
    "Çırak": (0, 150, 250, "🛠️"), "Kasiyer": (2, 250, 400, "🛒"), "Şoför": (4, 350, 550, "🚕"),
    "Garson": (6, 450, 700, "🍽️"), "Yazılımcı": (8, 650, 950, "💻"), "Doktor": (12, 950, 1400, "🩺"),
    "Pilot": (16, 1300, 2000, "✈️"), "Patron": (22, 2000, 3200, "👔"),
}


def nadirlik(deger):
    if deger >= 400:
        return "🌟 EFSANE"
    if deger >= 100:
        return "✨ Nadir"
    if deger >= 40:
        return "🔹 Güzel"
    return "▫️ Sıradan"


def meslek_bul(girdi):
    a = tr_ascii(girdi)
    for ad in MESLEKLER:
        if tr_ascii(ad) == a:
            return ad
    for ad in MESLEKLER:
        if tr_ascii(ad).startswith(a) and a:
            return ad
    return None


# ----------------------------------------------------------------------
# ✅ Doğrulama butonu
# ----------------------------------------------------------------------
class DogrulaButon(discord.ui.DynamicItem[discord.ui.Button], template=r"td22:dogrula"):
    def __init__(self):
        super().__init__(discord.ui.Button(
            label="Doğrula", emoji="✅", style=discord.ButtonStyle.success, custom_id="td22:dogrula"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction):
        guild, uye = interaction.guild, interaction.user
        if guild is None:
            return
        ayar = sv(guild.id)["dogrulama"]
        rol = guild.get_role(ayar["rol"]) if ayar["rol"] else None
        if rol is None:
            return await interaction.response.send_message("❌ Doğrulama rolü ayarlanmamış, yetkililere haber ver.", ephemeral=True)
        if rol in getattr(uye, "roles", []):
            return await interaction.response.send_message("Zaten doğrulanmışsın ✅", ephemeral=True)
        kareler = ["🔎 Hesabın kontrol ediliyor...", "🛡️ Güvenlik taraması yapılıyor...", "🔐 Rol hazırlanıyor..."]
        await interaction.response.send_message(
            embed=discord.Embed(description=f"{kareler[0]}\n▰▱▱▱▱▱", color=discord.Color.blurple()), ephemeral=True)
        for i, k in enumerate(kareler[1:], start=2):
            await asyncio.sleep(0.8)
            await interaction.edit_original_response(
                embed=discord.Embed(description=f"{k}\n{'▰' * (i * 2)}{'▱' * (6 - i * 2)}", color=discord.Color.blurple()))
        try:
            await uye.add_roles(rol, reason="Doğrulama butonu")
        except discord.HTTPException:
            return await interaction.edit_original_response(
                embed=discord.Embed(description="❌ Rolü veremedim. Botun rolü, doğrulama rolünün üstünde olmalı.",
                                    color=discord.Color.red()))
        await asyncio.sleep(0.6)
        await interaction.edit_original_response(embed=discord.Embed(
            title="✅ Doğrulandın!", description=f"Hoş geldin {uye.mention}! {rol.mention} rolünü aldın.\n▰▰▰▰▰▰",
            color=discord.Color.green()))
        await log(guild, "✅ Doğrulama", f"{uye.mention} doğrulandı.", discord.Color.green())


# ----------------------------------------------------------------------
# ⚔️ Düello
# ----------------------------------------------------------------------
class DuelloView(discord.ui.View):
    def __init__(self, rakip):
        super().__init__(timeout=60)
        self.rakip = rakip
        self.sonuc = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.rakip.id:
            await interaction.response.send_message("Bu daveti sadece meydan okunan kişi cevaplayabilir.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Kabul Et", emoji="⚔️", style=discord.ButtonStyle.success)
    async def kabul(self, interaction, button):
        self.sonuc = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Reddet", emoji="🏳️", style=discord.ButtonStyle.secondary)
    async def red(self, interaction, button):
        self.sonuc = False
        await interaction.response.defer()
        self.stop()


# ----------------------------------------------------------------------
# 🪪 Animasyonlu profil kartı (GIF)
# ----------------------------------------------------------------------
def font_al(boyut):
    for yol in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(yol, boyut), True
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=boyut), False
    except TypeError:
        return ImageFont.load_default(), False


def kart_gif(ad, avatar_bytes, seviye, xp_mevcut, xp_gerek, sira, bakiye, mesaj_say):
    """XP çubuğu dolan animasyonlu GIF kartı üretir (BytesIO döner)."""
    W, H = 640, 220
    buyuk, ttf_var = font_al(30)
    kucuk, _ = font_al(19)
    if not ttf_var:                                  # yazı tipi bulunamadıysa Türkçe harfleri sadeleştir
        ad = ad.translate(_TR)
    try:
        av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((128, 128))
    except Exception:
        av = Image.new("RGBA", (128, 128), (88, 101, 242, 255))
    maske = Image.new("L", (128, 128), 0)
    ImageDraw.Draw(maske).ellipse((0, 0, 127, 127), fill=255)
    oran = max(0.0, min(1.0, xp_mevcut / max(1, xp_gerek)))
    adim = 12
    kareler = []
    for i in range(adim + 1):
        o = oran * (i / adim)
        im = Image.new("RGB", (W, H), (24, 26, 38))
        d = ImageDraw.Draw(im)
        for y in range(H):
            d.line([(0, y), (W, y)], fill=(24 + y // 14, 26 + y // 16, 44 + y // 7))
        d.rounded_rectangle((10, 10, W - 10, H - 10), 18, outline=(88, 101, 242), width=3)
        im.paste(av, (34, 46), maske)
        d.ellipse((30, 42, 166, 178), outline=(87, 242, 135), width=3)
        d.text((190, 34), ad[:20], font=buyuk, fill=(255, 255, 255))
        d.text((190, 80), f"Seviye {seviye}   |   Sira #{sira or '-'}", font=kucuk, fill=(200, 205, 255))
        d.text((190, 106), f"Para: {para(bakiye)}   |   Mesaj: {para(mesaj_say)}", font=kucuk, fill=(255, 220, 120))
        bx0, by0, bx1, by1 = 190, 142, 610, 168
        d.rounded_rectangle((bx0, by0, bx1, by1), 13, fill=(50, 53, 70))
        w = int((bx1 - bx0) * o)
        if w >= 26:
            d.rounded_rectangle((bx0, by0, bx0 + w, by1), 13, fill=(87, 242, 135))
        elif w > 0:
            d.rectangle((bx0, by0, bx0 + w, by1), fill=(87, 242, 135))
        d.text((190, 176), f"{int(xp_mevcut * i / adim)} / {xp_gerek} XP", font=kucuk, fill=(235, 235, 245))
        kareler.append(im)
    sureler = [70] * adim + [3000]
    buf = io.BytesIO()
    kareler[0].save(buf, format="GIF", save_all=True, append_images=kareler[1:], duration=sureler, loop=0)
    buf.seek(0)
    return buf


# ----------------------------------------------------------------------
# 🇹🇷 Türkiye araçları: yardımcılar
# ----------------------------------------------------------------------
HAVA_KODLARI = {
    0: ("Açık", "☀️"), 1: ("Çoğunlukla açık", "🌤️"), 2: ("Parçalı bulutlu", "⛅"), 3: ("Kapalı", "☁️"),
    45: ("Sisli", "🌫️"), 48: ("Kırağılı sis", "🌫️"), 51: ("Hafif çisenti", "🌦️"), 53: ("Çisenti", "🌦️"),
    55: ("Yoğun çisenti", "🌧️"), 61: ("Hafif yağmur", "🌧️"), 63: ("Yağmurlu", "🌧️"), 65: ("Şiddetli yağmur", "🌧️"),
    71: ("Hafif kar", "🌨️"), 73: ("Karlı", "❄️"), 75: ("Yoğun kar", "❄️"), 77: ("Kar taneleri", "❄️"),
    80: ("Sağanak", "🌦️"), 81: ("Kuvvetli sağanak", "🌧️"), 82: ("Çok şiddetli sağanak", "⛈️"),
    85: ("Kar sağanağı", "🌨️"), 86: ("Yoğun kar sağanağı", "❄️"), 95: ("Gök gürültülü fırtına", "⛈️"),
    96: ("Dolulu fırtına", "⛈️"), 99: ("Şiddetli dolulu fırtına", "⛈️"),
}
VAKITLER = [("Fajr", "İmsak", "🌙"), ("Sunrise", "Güneş", "🌅"), ("Dhuhr", "Öğle", "☀️"),
            ("Asr", "İkindi", "🌇"), ("Maghrib", "Akşam", "🌆"), ("Isha", "Yatsı", "🌃")]
_onbellek = {}


async def onbellekli(anahtar, sure, getir):
    simdi = time.time()
    if anahtar in _onbellek and simdi - _onbellek[anahtar][0] < sure:
        return _onbellek[anahtar][1]
    sonuc = await getir()
    _onbellek[anahtar] = (simdi, sonuc)
    return sonuc


async def kurlari_al():
    async def getir():
        return (await http_al("https://open.er-api.com/v6/latest/USD"))["rates"]
    return await onbellekli("kur", 300, getir)


async def ons_altin(rates):
    try:
        async def getir():
            return float((await http_al("https://api.gold-api.com/price/XAU"))["price"])
        return await onbellekli("ons", 300, getir)
    except Exception:
        xau = (rates or {}).get("XAU")
        return (1 / float(xau)) if xau else None


# ----------------------------------------------------------------------
# 📺 YouTube yardımcıları
# ----------------------------------------------------------------------
async def yt_kanal_coz(giris):
    giris = giris.strip()
    m = re.search(r"(UC[\w-]{22})", giris)
    if m:
        return m.group(1)
    if giris.startswith("@"):
        url = f"https://www.youtube.com/{giris}"
    elif "youtube.com" in giris or "youtu.be" in giris:
        url = giris if giris.startswith("http") else "https://" + giris
    else:
        url = f"https://www.youtube.com/@{giris.lstrip('@')}"
    html = await http_al(url, json_mi=False, headers=UA)
    for rx in (r"channel_id=(UC[\w-]{22})", r'"channelId":"(UC[\w-]{22})"', r'"externalId":"(UC[\w-]{22})"'):
        m = re.search(rx, html)
        if m:
            return m.group(1)
    return None


def yt_rss_coz(xml_metin):
    """RSS'ten (kanal adı, [video, ...]) çıkarır. Videolar yeniden eskiye sıralıdır."""
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    kok = ET.fromstring(xml_metin)
    kanal = (kok.findtext("a:author/a:name", default="", namespaces=ns) or kok.findtext("a:title", default="", namespaces=ns))
    videolar = []
    for e in kok.findall("a:entry", ns):
        vid = e.findtext("yt:videoId", default="", namespaces=ns)
        if not vid:
            continue
        videolar.append({
            "id": vid,
            "baslik": e.findtext("a:title", default="Yeni video", namespaces=ns),
            "tarih": e.findtext("a:published", default="", namespaces=ns),
            "link": f"https://www.youtube.com/watch?v={vid}",
        })
    return kanal, videolar


async def yt_videolar(kid):
    metin = await http_al(f"https://www.youtube.com/feeds/videos.xml?channel_id={kid}", json_mi=False, headers=UA)
    return yt_rss_coz(metin)


def yt_eski_mi(tarih, gun=3):
    try:
        t = datetime.datetime.fromisoformat(tarih.replace("Z", "+00:00"))
        return (datetime.datetime.now(timezone.utc) - t) > timedelta(days=gun)
    except Exception:
        return False


# ----------------------------------------------------------------------
# Yardım satırları
# ----------------------------------------------------------------------
YARDIM = {
    "🎣 RPG (v2.2)": [
        "`balik` Olta at, balık tut (45 sn)  •  `maden` Maden kaz (60 sn)",
        "`envanter [@kişi]` Eşyaların  •  `sat <eşya|hepsi> [adet]` Eşya sat",
        "`gelistir <olta|kazma>` Aleti geliştir (nadir şansı artar)",
        "`meslek` Meslek listesi  •  `meslekal <ad>`  •  `mesai` Çalış, maaş al (1 saatte bir)  •  `meslekayril`",
        "`duello @kişi <bahis>` Para karşılığı düello (butonlu, animasyonlu)",
    ],
    "🪪 Kart ve Doğum Günü (v2.2)": [
        "`kart [@kişi]` Animasyonlu profil kartı (GIF)",
        "`dogumgunu <gün> <ay>` Doğum gününü kaydet  •  `dogumgunusil`  •  `dogumgunleri`",
        "`dogumgunukanal [#kanal]` Kutlama kanalını seç (Sunucuyu Yönet)",
    ],
    "🇹🇷 Türkiye Araçları (v2.2)": [
        "`namaz <şehir>` Namaz vakitleri ve kalan süre",
        "`hava <şehir>` Hava durumu",
        "`doviz` Dolar, euro, sterlin  •  `altin` Gram, çeyrek, yarım, tam altın (yaklaşık)",
    ],
    "🛡️ Doğrulama ve Raid (v2.2)": [
        "`dogrulamakur @rol [#kanal]` Butonlu doğrulama paneli kur (Sunucuyu Yönet)  •  `dogrulamakapat`",
        "`raid [ac|kapat|durum|esik <sayı>]` Toplu giriş (raid) koruması",
    ],
    "📺 YouTube Bildirimi (v2.2)": [
        "`ytekle <kanal id | @isim | link> [#kanal] [@rol]` Yeni videoda otomatik duyuru",
        "`ytliste`  •  `ytsil <numara>`  •  `yttest <numara>` Son videoyu test olarak at",
    ],
}


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class V22(commands.Cog):
    def __init__(self, bot, g):
        self.bot = bot
        self.g = g
        self.gorev = None
        self.giris = {}              # {sunucu_id: [(zaman, uye_id), ...]}
        self.raid_bildirim = {}

    def cog_unload(self):
        if self.gorev:
            self.gorev.cancel()

    # ------------------------------------------------------------------
    # ✅ Doğrulama
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="dogrulamakur", usage="@rol [#kanal]")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def dogrulamakur(self, ctx, rol: discord.Role, kanal: discord.TextChannel = None):
        """Butonlu doğrulama paneli kur"""
        if rol.is_default() or rol.managed or riskli_rol(rol):
            return await ctx.send("❌ Bu rol doğrulama için uygun değil (yetkili, bot ya da @everyone rolü olmamalı).")
        if rol >= ctx.guild.me.top_role:
            return await ctx.send("❌ Botun rolü bu rolün **üstünde** olmalı. Sunucu Ayarları → Roller'den botun rolünü yukarı taşı.")
        kanal = kanal or ctx.channel
        a = sv(ctx.guild.id)["dogrulama"]
        a["rol"], a["kanal"] = rol.id, kanal.id
        isaretle22()
        embed = discord.Embed(
            title="✅ Sunucuya Hoş Geldin!",
            description=("Sohbete ve kanallara erişmek için aşağıdaki **Doğrula** butonuna bas.\n"
                         f"Doğrulanınca {rol.mention} rolünü alacaksın."),
            color=discord.Color.green())
        embed.set_footer(text=ctx.guild.name)
        v = discord.ui.View(timeout=None)
        v.add_item(DogrulaButon())
        try:
            await kanal.send(embed=embed, view=v, allowed_mentions=NO_PING)
        except discord.HTTPException:
            return await ctx.send("❌ O kanala yazamıyorum.")
        await ctx.send(
            f"✅ Doğrulama paneli {kanal.mention} kanalına kuruldu.\n"
            f"💡 Diğer kanalları **@everyone** için kapatıp sadece {rol.mention} rolüne açarsan yeni gelenler doğrulanmadan göremez.")

    @commands.hybrid_command(name="dogrulamakapat")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def dogrulamakapat(self, ctx):
        """Doğrulama sistemini kapat"""
        a = sv(ctx.guild.id)["dogrulama"]
        a["rol"] = a["kanal"] = None
        isaretle22()
        await ctx.send("✅ Doğrulama kapatıldı. Eski paneldeki buton artık çalışmaz.")

    # ------------------------------------------------------------------
    # 🚨 Raid koruması
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="raid", usage="[ac | kapat | durum | esik <sayı>]")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def raid(self, ctx, islem: str = "durum", sayi: int = 0):
        """Toplu giriş (raid) korumasını ayarla"""
        r = sv(ctx.guild.id)["raid"]
        islem = tr_ascii(islem)
        if islem in ("ac", "aç", "ac"):
            r["acik"] = True
            isaretle22()
            return await ctx.send(
                f"🚨 Raid koruması **açıldı**. {r['saniye']} saniyede **{r['esik']}** kişi girerse raid modu başlar, "
                f"yeni girenlere {r['mod_dk']} dk timeout verilir. (Botun **Üyelere Zaman Aşımı Uygula** yetkisi gerekir.)")
        if islem == "kapat":
            r["acik"], r["bitis"] = False, 0
            isaretle22()
            return await ctx.send("✅ Raid koruması **kapatıldı**.")
        if islem == "esik":
            if not 3 <= sayi <= 50:
                return await ctx.send("❌ Eşik 3 ile 50 arasında olmalı. Örn: `td!raid esik 8`")
            r["esik"] = sayi
            isaretle22()
            return await ctx.send(f"✅ Eşik **{sayi}** kişi / {r['saniye']} saniye olarak ayarlandı.")
        durum = "🟢 Açık" if r["acik"] else "🔴 Kapalı"
        mod = f"\n🚨 **RAID MODU AKTİF** (<t:{int(r['bitis'])}:R> bitecek)" if r["bitis"] > time.time() else ""
        await ctx.send(f"🛡️ **Raid koruması:** {durum}\nEşik: **{r['esik']}** kişi / {r['saniye']} sn • Ceza: {r['mod_dk']} dk timeout{mod}\n"
                       "`td!raid ac` • `td!raid kapat` • `td!raid esik <sayı>`")

    @commands.Cog.listener()
    async def on_member_join(self, uye):
        guild = uye.guild
        r = sv(guild.id)["raid"]
        if not r["acik"]:
            return
        simdi = time.time()
        liste = [(t, u) for t, u in self.giris.get(guild.id, []) if simdi - t < r["saniye"]]
        liste.append((simdi, uye.id))
        self.giris[guild.id] = liste
        if r["bitis"] > simdi:                                  # raid modu zaten açık: yeni girene timeout
            await self.raid_ceza(guild, [uye.id], r)
            return
        if len(liste) >= r["esik"]:
            r["bitis"] = simdi + r["mod_dk"] * 60
            isaretle22()
            await self.raid_ceza(guild, [u for _, u in liste], r)
            aciklama = (f"{r['saniye']} saniyede **{len(liste)}** kişi sunucuya girdi.\n"
                        f"Yeni girenlere {r['mod_dk']} dk timeout verildi. `td!raid kapat` ile koruma kapatılır.")
            await log(guild, "🚨 RAID ALGILANDI", aciklama, discord.Color.red())
            kanal = guild.system_channel
            if kanal is not None:
                try:
                    await kanal.send(f"🚨 **Raid algılandı!** {aciklama}", allowed_mentions=NO_PING)
                except discord.HTTPException:
                    pass

    async def raid_ceza(self, guild, idler, r):
        for uid in idler:
            m = guild.get_member(uid)
            if m is None or m.bot:
                continue
            try:
                await m.timeout(timedelta(minutes=r["mod_dk"]), reason="Otomatik: raid koruması")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # 🎣 Balık / ⛏️ Maden
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="balik", aliases=["balık", "baliktut"])
    @commands.guild_only()
    async def balik(self, ctx):
        """Olta at, balık tut"""
        e = env(ctx.guild.id, ctx.author.id)
        kalan = bekleme(e, "balik", BALIK_BEKLEME)
        if kalan:
            return await ctx.send(f"🎣 Oltayı toplamak için **{sure_yaz(kalan)}** bekle.")
        lvl = e["olta"]
        agirlik = [w * (1 + 0.15 * (lvl - 1)) if d >= 80 else w for _, _, d, w in BALIKLAR]
        ad, emoji, deger, _ = random.choices(BALIKLAR, weights=agirlik)[0]
        e["esya"][ad] = e["esya"].get(ad, 0) + 1
        isaretle22()
        mavi = 0x3498DB
        kareler = [
            discord.Embed(title="🎣 Olta atılıyor...", description="`🌊〰️〰️〰️〰️`", color=mavi),
            discord.Embed(title="🎣 Bekleniyor...", description="`〰️🌊〰️〰️〰️`\n_Sakin ol, balık dikkatli..._", color=mavi),
            discord.Embed(title="🎣 Bir şey yakaladı!", description="`〰️〰️🌊〰️〰️`\n❗ **Çek!**", color=0xFEE75C),
            discord.Embed(title="🎣 Çekiliyor...", description="`〰️〰️〰️🌊〰️`", color=mavi),
        ]
        son = discord.Embed(
            title=f"{emoji} {ad} yakaladın!",
            description=f"{nadirlik(deger)} • Değeri: **{para(deger)}** 🪙\nEnvanterine eklendi. Satmak için `td!sat {ad}`",
            color=0x57F287 if deger >= 40 else 0x95A5A6)
        son.set_footer(text=f"Olta seviyesi: {lvl}/{GELISTIR_MAX}")
        await anim_gonder(ctx, kareler, son, bekle=0.8)

    @commands.hybrid_command(name="maden", aliases=["madenkaz", "kaz"])
    @commands.guild_only()
    async def maden(self, ctx):
        """Maden kaz"""
        e = env(ctx.guild.id, ctx.author.id)
        kalan = bekleme(e, "maden", MADEN_BEKLEME)
        if kalan:
            return await ctx.send(f"⛏️ Kazmayı dinlendirmek için **{sure_yaz(kalan)}** bekle.")
        lvl = e["kazma"]
        agirlik = [w * (1 + 0.15 * (lvl - 1)) if d >= 60 else w for _, _, d, w in MADENLER]
        ad, emoji, deger, _ = random.choices(MADENLER, weights=agirlik)[0]
        miktar = random.randint(1, 3) if deger < 100 else 1
        e["esya"][ad] = e["esya"].get(ad, 0) + miktar
        isaretle22()
        gri = 0x7F8C8D
        kareler = [
            discord.Embed(title="⛏️ Mağaraya giriliyor...", description="`🕳️ ▱▱▱▱▱`", color=gri),
            discord.Embed(title="⛏️ Kazılıyor...", description="`⛏️ ▰▰▱▱▱`\n💥 *tak tak tak*", color=gri),
            discord.Embed(title="⛏️ Kazılıyor...", description="`⛏️ ▰▰▰▰▱`\n💥 *tak tak tak*", color=gri),
            discord.Embed(title="⛏️ Bir şey parlıyor...", description="`✨ ▰▰▰▰▰`", color=0xFEE75C),
        ]
        son = discord.Embed(
            title=f"{emoji} {miktar}x {ad} buldun!",
            description=f"{nadirlik(deger)} • Tanesi **{para(deger)}** 🪙\nSatmak için `td!sat {ad}`",
            color=0x57F287 if deger >= 30 else 0x95A5A6)
        son.set_footer(text=f"Kazma seviyesi: {lvl}/{GELISTIR_MAX}")
        await anim_gonder(ctx, kareler, son, bekle=0.8)

    @commands.hybrid_command(name="envanter", aliases=["env", "çanta", "canta"], usage="[@kişi]")
    @commands.guild_only()
    async def envanter(self, ctx, uye: discord.Member = None):
        """Envanterini göster"""
        uye = uye or ctx.author
        e = env(ctx.guild.id, uye.id)
        satirlar, toplam = [], 0
        for ad, n in sorted(e["esya"].items(), key=lambda x: -ESYA.get(x[0], ("", 0))[1] * x[1]):
            if n <= 0:
                continue
            emoji, deger = ESYA.get(ad, ("📦", 0))
            toplam += deger * n
            satirlar.append(f"{emoji} **{ad}** x{n} — {para(deger * n)} 🪙")
        embed = discord.Embed(title=f"🎒 {uye.display_name} • Envanter", color=discord.Color.gold())
        embed.description = "\n".join(satirlar)[:3800] if satirlar else "_Envanter boş. `td!balik` ve `td!maden` ile eşya topla!_"
        if satirlar:
            embed.add_field(name="💰 Toplam değer", value=f"{para(toplam)} 🪙")
        embed.add_field(name="🛠️ Aletler", value=f"🎣 Olta: **{e['olta']}** • ⛏️ Kazma: **{e['kazma']}**")
        mesl = e["meslek"]
        if mesl in MESLEKLER:
            embed.add_field(name="💼 Meslek", value=f"{MESLEKLER[mesl][3]} {mesl}")
        embed.set_thumbnail(url=uye.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="sat", usage="<eşya | hepsi> [adet]")
    @commands.guild_only()
    async def sat(self, ctx, *, metin: str = "hepsi"):
        """Envanterindeki eşyaları sat"""
        e = env(ctx.guild.id, ctx.author.id)
        adet = None
        parca = metin.rsplit(" ", 1)
        if len(parca) == 2 and parca[1].isdigit():
            metin, adet = parca[0], int(parca[1])
        anahtar = tr_ascii(metin)
        if anahtar in ("hepsi", "hepsini", "tumu", "tumunu", ""):
            secilen = [(ad, n) for ad, n in e["esya"].items() if n > 0]
            adet = None
        else:
            secilen = [(ad, n) for ad, n in e["esya"].items() if n > 0 and anahtar in tr_ascii(ad)][:1]
        if not secilen:
            return await ctx.send("❌ Satacak eşya bulamadım. `td!envanter` yazıp adını kontrol et.")
        toplam, satirlar = 0, []
        for ad, n in secilen:
            sat_n = n if adet is None else max(1, min(adet, n))
            emoji, deger = ESYA.get(ad, ("📦", 0))
            e["esya"][ad] = n - sat_n
            if e["esya"][ad] <= 0:
                e["esya"].pop(ad, None)
            kazanc = deger * sat_n
            toplam += kazanc
            satirlar.append(f"{emoji} {ad} x{sat_n} → **{para(kazanc)}** 🪙")
        eko_ekle(ctx.guild.id, ctx.author.id, toplam)
        isaretle22()
        sari = 0xF1C40F
        kareler = [discord.Embed(title="💰 Pazarlık yapılıyor...", description="`🤝 ▰▱▱`", color=sari),
                   discord.Embed(title="💰 Para sayılıyor...", description="`🪙 ▰▰▱`", color=sari)]
        son = discord.Embed(title="💰 Satış tamam!", description="\n".join(satirlar)[:3500], color=0x57F287)
        son.add_field(name="Toplam kazanç", value=f"**{para(toplam)}** 🪙")
        son.add_field(name="Yeni bakiye", value=f"{para(eko(ctx.guild.id, ctx.author.id)['bakiye'])} 🪙")
        await anim_gonder(ctx, kareler, son, bekle=0.6)

    @commands.hybrid_command(name="gelistir", usage="<olta | kazma>")
    @commands.guild_only()
    async def gelistir(self, ctx, alet: str):
        """Oltanı ya da kazmanı geliştir (nadir şansı artar)"""
        a = tr_ascii(alet)
        if a not in ("olta", "kazma"):
            return await ctx.send("❌ `td!gelistir olta` ya da `td!gelistir kazma` yaz.")
        e = env(ctx.guild.id, ctx.author.id)
        lvl = e[a]
        if lvl >= GELISTIR_MAX:
            return await ctx.send(f"🌟 {a.capitalize()} zaten son seviyede ({GELISTIR_MAX}).")
        bedel = 400 * lvl * lvl
        if not bakiye_kontrol(ctx.guild.id, ctx.author.id, bedel):
            return await ctx.send(f"❌ Bir sonraki seviye **{para(bedel)}** 🪙. Bakiyen yetmiyor.")
        eko_ekle(ctx.guild.id, ctx.author.id, -bedel)
        e[a] = lvl + 1
        isaretle22()
        kareler = [discord.Embed(title="🔧 Geliştiriliyor...", description="`🔨 ▰▱▱▱`", color=0xE67E22),
                   discord.Embed(title="🔧 Geliştiriliyor...", description="`🔨 ▰▰▰▱`", color=0xE67E22)]
        emoji = "🎣" if a == "olta" else "⛏️"
        son = discord.Embed(title=f"{emoji} {a.capitalize()} geliştirildi!",
                            description=f"Seviye **{lvl} → {lvl + 1}** • Ödenen: {para(bedel)} 🪙\nNadir eşya şansın arttı.",
                            color=0x57F287)
        await anim_gonder(ctx, kareler, son, bekle=0.6)

    # ------------------------------------------------------------------
    # 💼 Meslek
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="meslek", aliases=["meslekler"])
    @commands.guild_only()
    async def meslek(self, ctx):
        """Meslek listesi"""
        e = env(ctx.guild.id, ctx.author.id)
        sev = seviye_hesapla(xp_kayit(ctx.guild.id, ctx.author.id)[0])[0]
        satirlar = []
        for ad, (gerek, mn, mx, emoji) in MESLEKLER.items():
            kilit = "✅" if sev >= gerek else f"🔒 (Seviye {gerek})"
            su = " ⬅️ **mesleğin**" if e["meslek"] == ad else ""
            satirlar.append(f"{emoji} **{ad}** — {para(mn)}-{para(mx)} 🪙/saat {kilit}{su}")
        embed = discord.Embed(title="💼 Meslekler", description="\n".join(satirlar), color=discord.Color.blurple())
        embed.set_footer(text=f"Seviyen: {sev} • Seç: td!meslekal <ad> • Çalış: td!mesai")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="meslekal", usage="<meslek adı>")
    @commands.guild_only()
    async def meslekal(self, ctx, *, ad: str):
        """Bir mesleğe gir"""
        m = meslek_bul(ad)
        if m is None:
            return await ctx.send("❌ Böyle bir meslek yok. `td!meslek` ile listeye bak.")
        gerek, mn, mx, emoji = MESLEKLER[m]
        sev = seviye_hesapla(xp_kayit(ctx.guild.id, ctx.author.id)[0])[0]
        if sev < gerek:
            return await ctx.send(f"🔒 **{m}** için **{gerek}. seviye** lazım, sen {sev}. seviyedesin.")
        e = env(ctx.guild.id, ctx.author.id)
        e["meslek"] = m
        isaretle22()
        kareler = [discord.Embed(title="📝 Başvuru yapılıyor...", description="`📄 ▰▱▱`", color=0x3498DB),
                   discord.Embed(title="📝 Mülakat...", description="`🤝 ▰▰▱`", color=0x3498DB)]
        son = discord.Embed(title=f"{emoji} Artık bir {m}'sin!",
                            description=f"Maaş: **{para(mn)}-{para(mx)}** 🪙 / saat\nÇalışmak için `td!mesai` yaz.",
                            color=0x57F287)
        await anim_gonder(ctx, kareler, son, bekle=0.7)

    @commands.hybrid_command(name="mesai", aliases=["mesaiye"])
    @commands.guild_only()
    async def mesai(self, ctx):
        """Mesleğinde çalış, maaş al (1 saatte bir)"""
        e = env(ctx.guild.id, ctx.author.id)
        if e["meslek"] not in MESLEKLER:
            return await ctx.send("💼 Önce bir mesleğe gir: `td!meslek` ve `td!meslekal <ad>`")
        kalan = bekleme(e, "mesai", MESAI_BEKLEME)
        if kalan:
            return await ctx.send(f"⏳ Dinlenmen lazım, **{sure_yaz(kalan)}** sonra tekrar çalışabilirsin.")
        gerek, mn, mx, emoji = MESLEKLER[e["meslek"]]
        maas = random.randint(mn, mx)
        eko_ekle(ctx.guild.id, ctx.author.id, maas)
        kareler = [discord.Embed(title=f"{emoji} İşe gidiliyor...", description="`🚶 ▰▱▱▱▱`", color=0x3498DB),
                   discord.Embed(title=f"{emoji} Çalışılıyor...", description="`⚙️ ▰▰▰▱▱`", color=0x3498DB),
                   discord.Embed(title=f"{emoji} Mesai bitiyor...", description="`🌆 ▰▰▰▰▱`", color=0x3498DB)]
        son = discord.Embed(title=f"{emoji} Mesai bitti!", description=f"**{e['meslek']}** olarak çalıştın ve **{para(maas)}** 🪙 kazandın.",
                            color=0x57F287)
        son.set_footer(text=f"Yeni bakiye: {para(eko(ctx.guild.id, ctx.author.id)['bakiye'])} 🪙")
        await anim_gonder(ctx, kareler, son, bekle=0.7)

    @commands.hybrid_command(name="meslekayril")
    @commands.guild_only()
    async def meslekayril(self, ctx):
        """Mesleğinden ayrıl"""
        e = env(ctx.guild.id, ctx.author.id)
        if e["meslek"] is None:
            return await ctx.send("💼 Zaten bir mesleğin yok.")
        e["meslek"] = None
        isaretle22()
        await ctx.send("👋 Mesleğinden ayrıldın.")

    # ------------------------------------------------------------------
    # ⚔️ Düello
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="duello", aliases=["düello"], usage="@kişi <bahis>")
    @commands.guild_only()
    async def duello(self, ctx, rakip: discord.Member, bahis: int):
        """Para karşılığı düello"""
        if rakip.bot or rakip.id == ctx.author.id:
            return await ctx.send("❌ Kendinle ya da bir botla düello yapamazsın.")
        if not DUELLO_MIN <= bahis <= DUELLO_MAX:
            return await ctx.send(f"❌ Bahis {para(DUELLO_MIN)} ile {para(DUELLO_MAX)} 🪙 arasında olmalı.")
        if not bakiye_kontrol(ctx.guild.id, ctx.author.id, bahis):
            return await ctx.send("❌ Bakiyen bu bahis için yetmiyor.")
        if not bakiye_kontrol(ctx.guild.id, rakip.id, bahis):
            return await ctx.send(f"❌ {rakip.display_name} bu bahis için yeterli paraya sahip değil.")
        view = DuelloView(rakip)
        davet = discord.Embed(
            title="⚔️ Düello Daveti!",
            description=f"{ctx.author.mention}, {rakip.mention} kişisine meydan okudu!\nBahis: **{para(bahis)}** 🪙 (kazanan hepsini alır)",
            color=discord.Color.red())
        davet.set_footer(text="60 saniye içinde cevap ver")
        msg = await ctx.send(content=rakip.mention, embed=davet, view=view,
                             allowed_mentions=discord.AllowedMentions(users=[rakip]))
        await view.wait()
        if view.sonuc is None:
            return await msg.edit(content=None, embed=discord.Embed(description="⌛ Düello daveti zaman aşımına uğradı.", color=0x95A5A6), view=None)
        if view.sonuc is False:
            return await msg.edit(content=None, embed=discord.Embed(description=f"🏳️ {rakip.display_name} düelloyu reddetti.", color=0x95A5A6), view=None)
        if not (bakiye_kontrol(ctx.guild.id, ctx.author.id, bahis) and bakiye_kontrol(ctx.guild.id, rakip.id, bahis)):
            return await msg.edit(content=None, embed=discord.Embed(description="❌ Birinin parası bu arada yetmez oldu, düello iptal.", color=0x95A5A6), view=None)
        sev_a = seviye_hesapla(xp_kayit(ctx.guild.id, ctx.author.id)[0])[0]
        sev_b = seviye_hesapla(xp_kayit(ctx.guild.id, rakip.id)[0])[0]
        sans = 0.5 + max(-0.15, min(0.15, (sev_a - sev_b) * 0.02))       # seviye farkı en fazla %15 avantaj
        kazanan, kaybeden = (ctx.author, rakip) if random.random() < sans else (rakip, ctx.author)
        eko_ekle(ctx.guild.id, kazanan.id, bahis)
        eko_ekle(ctx.guild.id, kaybeden.id, -bahis)
        a, b = ctx.author.display_name, rakip.display_name
        kirmizi = 0xED4245
        kareler = [
            discord.Embed(title="⚔️ Düello başlıyor!", description=f"**{a}** 🆚 **{b}**\n`🗡️ ▱▱▱▱▱ 🗡️`", color=kirmizi),
            discord.Embed(title="⚔️ Kılıçlar çarpışıyor!", description=f"**{a}** 🆚 **{b}**\n`🗡️ ▰▰▱▱▱ 🗡️`\n💥 *çın!*", color=kirmizi),
            discord.Embed(title="⚔️ Savaş kızışıyor!", description=f"**{a}** 🆚 **{b}**\n`🗡️ ▰▰▰▰▱ 🗡️`\n💥💥 *çın çın!*", color=kirmizi),
            discord.Embed(title="⚔️ Son darbe...", description=f"**{a}** 🆚 **{b}**\n`🗡️ ▰▰▰▰▰ 🗡️`\n⚡", color=0xFEE75C),
        ]
        await msg.edit(content=None, embed=kareler[0], view=None)
        await anim_duzenle(msg, kareler[1:], 0.9)
        await asyncio.sleep(0.9)
        son = discord.Embed(
            title=f"🏆 {kazanan.display_name} kazandı!",
            description=f"{kazanan.mention} düelloyu kazandı ve **{para(bahis)}** 🪙 aldı.\n{kaybeden.display_name} kaybetti.",
            color=0x57F287)
        son.set_thumbnail(url=kazanan.display_avatar.url)
        await msg.edit(embed=son, allowed_mentions=NO_PING)

    # ------------------------------------------------------------------
    # 🪪 Kart
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="kart", aliases=["profilkart", "seviyekart"], usage="[@kişi]")
    @commands.guild_only()
    async def kart(self, ctx, uye: discord.Member = None):
        """Animasyonlu profil kartı"""
        if not PIL_VAR:
            return await ctx.send("❌ Kart için `pillow` paketi gerekli. `requirements.txt` dosyasına bir satır `pillow` ekleyip botu yeniden başlat.")
        uye = uye or ctx.author
        async with ctx.typing():
            k = xp_kayit(ctx.guild.id, uye.id)
            sev, mevcut, gerek = seviye_hesapla(k[0])
            sira = next((i + 1 for i, (u, _) in enumerate(siralama_listesi(ctx.guild.id)) if u == str(uye.id)), 0)
            bakiye = eko(ctx.guild.id, uye.id)["bakiye"]
            try:
                avatar = await uye.display_avatar.replace(size=128, format="png").read()
            except discord.HTTPException:
                avatar = b""
            try:
                buf = await asyncio.to_thread(kart_gif, uye.display_name, avatar, sev, mevcut, gerek, sira, bakiye, k[1])
            except Exception as e:
                print(f"kart hatası: {e!r}")
                return await ctx.send("❌ Kart oluşturulamadı.")
        await ctx.send(file=discord.File(buf, filename="kart.gif"))

    # ------------------------------------------------------------------
    # 🎂 Doğum günü
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="dogumgunu", aliases=["doğumgünü", "dogumgunum"], usage="<gün> <ay>")
    @commands.guild_only()
    async def dogumgunu(self, ctx, gun: int, ay: int):
        """Doğum gününü kaydet (sadece gün ve ay)"""
        try:
            datetime.date(2024, ay, gun)
        except ValueError:
            return await ctx.send("❌ Geçersiz tarih. Örnek: `td!dogumgunu 15 7` (15 Temmuz)")
        veri["dogum"].setdefault(str(ctx.guild.id), {})[str(ctx.author.id)] = f"{gun:02d}-{ay:02d}"
        isaretle22()
        ay_adlari = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        kareler = [discord.Embed(title="🎂 Kaydediliyor...", description="`🎈 ▰▱▱`", color=0xEB459E),
                   discord.Embed(title="🎂 Kaydediliyor...", description="`🎈🎈 ▰▰▱`", color=0xEB459E)]
        son = discord.Embed(title="🎉 Doğum günün kaydedildi!", description=f"**{gun} {ay_adlari[ay - 1]}** günü seni kutlayacağım!", color=0x57F287)
        await anim_gonder(ctx, kareler, son, bekle=0.6)

    @commands.hybrid_command(name="dogumgunusil", aliases=["doğumgünüsil"])
    @commands.guild_only()
    async def dogumgunusil(self, ctx):
        """Kayıtlı doğum gününü sil"""
        if veri["dogum"].get(str(ctx.guild.id), {}).pop(str(ctx.author.id), None) is None:
            return await ctx.send("Kayıtlı doğum günün yok.")
        isaretle22()
        await ctx.send("✅ Doğum günün silindi.")

    @commands.hybrid_command(name="dogumgunleri", aliases=["doğumgünleri"])
    @commands.guild_only()
    async def dogumgunleri(self, ctx):
        """Yaklaşan doğum günleri"""
        bugun = datetime.datetime.now(TR).date()
        liste = []
        for uid, t in veri["dogum"].get(str(ctx.guild.id), {}).items():
            uye = ctx.guild.get_member(int(uid))
            if uye is None:
                continue
            g, a = int(t[:2]), int(t[3:])
            for yil in (bugun.year, bugun.year + 1):
                try:
                    d = datetime.date(yil, a, g)
                except ValueError:
                    d = datetime.date(yil, 3, 1)
                if d >= bugun:
                    liste.append(((d - bugun).days, uye, d))
                    break
        liste.sort(key=lambda x: x[0])
        if not liste:
            return await ctx.send("🎂 Kayıtlı doğum günü yok. `td!dogumgunu <gün> <ay>` ile ekle.")
        satirlar = [f"🎈 **{u.display_name}** — {d.day:02d}.{d.month:02d} " + ("(**BUGÜN!** 🎉)" if n == 0 else f"({n} gün sonra)")
                    for n, u, d in liste[:10]]
        await ctx.send(embed=discord.Embed(title="🎂 Yaklaşan Doğum Günleri", description="\n".join(satirlar), color=0xEB459E))

    @commands.hybrid_command(name="dogumgunukanal", usage="[#kanal]")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def dogumgunukanal(self, ctx, kanal: discord.TextChannel = None):
        """Doğum günü kutlama kanalını seç"""
        kanal = kanal or ctx.channel
        sv(ctx.guild.id)["dogum"]["kanal"] = kanal.id
        isaretle22()
        await ctx.send(f"✅ Doğum günleri her gün **{DOGUM_SAAT:02d}:00**'da (Türkiye saati) {kanal.mention} kanalında kutlanacak.")

    async def dogum_kontrol(self, simdi):
        if simdi.hour < DOGUM_SAAT:
            return
        bugun = simdi.strftime("%d-%m")
        gun_anahtar = simdi.strftime("%Y-%m-%d")
        hedefler = [bugun]
        if bugun == "28-02" and simdi.year % 4 != 0:             # artık yıl değilse 29 Şubat doğanları da kutla
            hedefler.append("29-02")
        for gid, kayitlar in list(veri["dogum"].items()):
            ayar = sv(gid)["dogum"]
            if not ayar["kanal"] or ayar["son"] == gun_anahtar:
                continue
            guild = self.bot.get_guild(int(gid))
            kanal = guild.get_channel(ayar["kanal"]) if guild else None
            ayar["son"] = gun_anahtar
            isaretle22()
            if kanal is None:
                continue
            uyeler = [guild.get_member(int(u)) for u, t in kayitlar.items() if t in hedefler]
            for uye in [u for u in uyeler if u is not None and not u.bot]:
                try:
                    await self.dogum_kutla(kanal, uye)
                except discord.HTTPException:
                    pass

    async def dogum_kutla(self, kanal, uye):
        izin = discord.AllowedMentions(users=[uye])
        renk = 0xEB459E
        msg = await kanal.send(content=uye.mention, embed=discord.Embed(title="🎈 Bir şey oluyor...", description="`🎈      `", color=renk),
                               allowed_mentions=izin)
        await anim_duzenle(msg, [discord.Embed(title="🎈🎈 Balonlar şişiyor...", description="`🎈🎈🎈   `", color=renk),
                                 discord.Embed(title="🎈🎈🎈🎈 Konfetiler hazır!", description="`🎊🎈🎊🎈🎊`", color=renk)], 0.9)
        await asyncio.sleep(0.9)
        hediye = f"\n🎁 Hediyen: **{para(DOGUM_HEDIYE)}** 🪙 hesabına yattı!" if DOGUM_HEDIYE else ""
        if DOGUM_HEDIYE:
            eko_ekle(kanal.guild.id, uye.id, DOGUM_HEDIYE)
        son = discord.Embed(title="🎂 DOĞUM GÜNÜN KUTLU OLSUN!",
                            description=f"{uye.mention}, yeni yaşında sağlık, mutluluk ve bol şans!\nTüm **{kanal.guild.name}** ailesi seni kutluyor 🥳{hediye}",
                            color=renk)
        son.set_thumbnail(url=uye.display_avatar.url)
        await msg.edit(embed=son, allowed_mentions=izin)

    # ------------------------------------------------------------------
    # 🇹🇷 Namaz / Hava / Döviz / Altın
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="namaz", aliases=["ezan", "namazvakti"], usage="<şehir>")
    async def namaz(self, ctx, *, sehir: str = "Istanbul"):
        """Namaz vakitleri ve kalan süre"""
        sehir_ascii = tr_ascii(sehir).title() or "Istanbul"
        msg = await ctx.send(embed=yukleme_kareleri("🕌 Vakitler getiriliyor...", 0x2ECC71)[0])
        asyncio.create_task(anim_duzenle(msg, yukleme_kareleri("🕌 Vakitler getiriliyor...", 0x2ECC71)[1:3], 0.5))
        try:
            veri_json = await http_al("https://api.aladhan.com/v1/timingsByCity",
                                      {"city": sehir_ascii, "country": "Turkey", "method": 13})
            t = veri_json["data"]["timings"]
        except Exception as e:
            print(f"namaz hatası: {e!r}")
            return await msg.edit(embed=discord.Embed(description="❌ Vakitleri alamadım. Şehir adını kontrol et (örn. `td!namaz ankara`) ya da biraz sonra tekrar dene.", color=0xED4245))
        simdi = datetime.datetime.now(TR)
        zamanlar = []
        for anahtar, ad, emoji in VAKITLER:
            m = re.search(r"(\d{1,2}):(\d{2})", t.get(anahtar, ""))
            if m:
                zamanlar.append((ad, emoji, simdi.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)))
        if not zamanlar:
            return await msg.edit(embed=discord.Embed(description="❌ Vakit bilgisi okunamadı.", color=0xED4245))
        siradaki = next((z for z in zamanlar if z[2] > simdi), None)
        if siradaki is None:
            siradaki = (zamanlar[0][0], zamanlar[0][1], zamanlar[0][2] + timedelta(days=1))
        kalan = int((siradaki[2] - simdi).total_seconds())
        satirlar = [f"{e} **{a}** — `{z.strftime('%H:%M')}`" + ("  ⬅️ **sıradaki**" if a == siradaki[0] else "") for a, e, z in zamanlar]
        await asyncio.sleep(1.2)
        embed = discord.Embed(title=f"🕌 {sehir_ascii} • Namaz Vakitleri", description="\n".join(satirlar), color=0x2ECC71)
        embed.add_field(name="⏳ Kalan süre", value=f"**{siradaki[0]}** vaktine **{sure_yaz(kalan)}** var")
        embed.set_footer(text="Kaynak: Aladhan (Diyanet yöntemi)")
        await msg.edit(embed=embed)

    @commands.hybrid_command(name="hava", aliases=["havadurumu"], usage="<şehir>")
    async def hava(self, ctx, *, sehir: str = "Istanbul"):
        """Hava durumu"""
        msg = await ctx.send(embed=yukleme_kareleri("🌤️ Hava durumu getiriliyor...", 0x3498DB)[0])
        asyncio.create_task(anim_duzenle(msg, yukleme_kareleri("🌤️ Hava durumu getiriliyor...", 0x3498DB)[1:3], 0.5))
        try:
            yer = None
            for ek in ({"countryCode": "TR"}, {}):
                g = await http_al("https://geocoding-api.open-meteo.com/v1/search",
                                  {"name": sehir, "count": 1, "language": "tr", **ek})
                if g.get("results"):
                    yer = g["results"][0]
                    break
            if yer is None:
                return await msg.edit(embed=discord.Embed(description="❌ Bu şehri bulamadım.", color=0xED4245))
            h = await http_al("https://api.open-meteo.com/v1/forecast", {
                "latitude": yer["latitude"], "longitude": yer["longitude"], "timezone": "auto",
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min"})
            c, d = h["current"], h["daily"]
        except Exception as e:
            print(f"hava hatası: {e!r}")
            return await msg.edit(embed=discord.Embed(description="❌ Hava durumunu alamadım, biraz sonra tekrar dene.", color=0xED4245))
        durum, emoji = HAVA_KODLARI.get(c.get("weather_code"), ("Bilinmiyor", "🌡️"))
        await asyncio.sleep(1.2)
        yer_ad = ", ".join(x for x in (yer.get("name"), yer.get("admin1")) if x)
        embed = discord.Embed(title=f"{emoji} {yer_ad}", description=f"**{durum}**", color=0x3498DB)
        embed.add_field(name="🌡️ Sıcaklık", value=f"**{c['temperature_2m']:.0f}°C** (hissedilen {c['apparent_temperature']:.0f}°C)")
        embed.add_field(name="📈 Bugün", value=f"En düşük {d['temperature_2m_min'][0]:.0f}°C • En yüksek {d['temperature_2m_max'][0]:.0f}°C")
        embed.add_field(name="💧 Nem", value=f"%{c['relative_humidity_2m']}")
        embed.add_field(name="💨 Rüzgar", value=f"{c['wind_speed_10m']:.0f} km/sa")
        embed.set_footer(text="Kaynak: Open-Meteo")
        await msg.edit(embed=embed)

    @commands.hybrid_command(name="doviz", aliases=["döviz", "dolar"])
    async def doviz(self, ctx):
        """Dolar, euro, sterlin kurları"""
        msg = await ctx.send(embed=yukleme_kareleri("💱 Kurlar getiriliyor...", 0x57F287)[0])
        asyncio.create_task(anim_duzenle(msg, yukleme_kareleri("💱 Kurlar getiriliyor...", 0x57F287)[1:3], 0.5))
        try:
            r = await kurlari_al()
            tl = r["TRY"]
            satirlar = [f"💵 **Dolar:** `{tl:,.2f}` ₺", f"💶 **Euro:** `{tl / r['EUR']:,.2f}` ₺",
                        f"💷 **Sterlin:** `{tl / r['GBP']:,.2f}` ₺"]
        except Exception as e:
            print(f"döviz hatası: {e!r}")
            return await msg.edit(embed=discord.Embed(description="❌ Kurları alamadım, biraz sonra tekrar dene.", color=0xED4245))
        await asyncio.sleep(1.2)
        embed = discord.Embed(title="💱 Döviz Kurları", description="\n".join(satirlar).replace(",", "."), color=0x57F287)
        embed.set_footer(text="Uluslararası ortalama kur • banka/kuyumcu fiyatından farklı olabilir")
        await msg.edit(embed=embed)

    @commands.hybrid_command(name="altin", aliases=["altın"])
    async def altin(self, ctx):
        """Gram, çeyrek, yarım, tam altın (yaklaşık)"""
        msg = await ctx.send(embed=yukleme_kareleri("🪙 Altın fiyatları getiriliyor...", 0xF1C40F)[0])
        asyncio.create_task(anim_duzenle(msg, yukleme_kareleri("🪙 Altın fiyatları getiriliyor...", 0xF1C40F)[1:3], 0.5))
        try:
            r = await kurlari_al()
            ons = await ons_altin(r)
            if not ons:
                raise RuntimeError("ons fiyatı yok")
            gram = ons / 31.1035 * r["TRY"]
        except Exception as e:
            print(f"altın hatası: {e!r}")
            return await msg.edit(embed=discord.Embed(description="❌ Altın fiyatını alamadım, biraz sonra tekrar dene.", color=0xED4245))
        ceyrek = gram * 1.6043          # 1,75 gr, 22 ayar (0,916)
        satirlar = [f"🥇 **Gram (24 ayar):** `{gram:,.0f}` ₺", f"🪙 **Çeyrek:** `{ceyrek:,.0f}` ₺",
                    f"🪙 **Yarım:** `{ceyrek * 2:,.0f}` ₺", f"🪙 **Tam:** `{ceyrek * 4:,.0f}` ₺",
                    f"🌍 **Ons:** `{ons:,.0f}` $"]
        await asyncio.sleep(1.2)
        embed = discord.Embed(title="🪙 Altın Fiyatları (yaklaşık)", description="\n".join(satirlar).replace(",", "."), color=0xF1C40F)
        embed.set_footer(text="Uluslararası ons fiyatından hesaplanır • kuyumcu fiyatı işçilik/fark nedeniyle değişir")
        await msg.edit(embed=embed)

    # ------------------------------------------------------------------
    # 📺 YouTube
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="ytekle", usage="<kanal id | @isim | link> [#kanal] [@rol]")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def ytekle(self, ctx, kaynak: str, kanal: discord.TextChannel = None, rol: discord.Role = None):
        """YouTube kanalını ekle, yeni videoda otomatik duyur"""
        liste = veri["yt"].setdefault(str(ctx.guild.id), [])
        if len(liste) >= YT_MAX:
            return await ctx.send(f"❌ En fazla {YT_MAX} YouTube kanalı eklenebilir. `td!ytsil <numara>` ile birini sil.")
        kanal = kanal or ctx.channel
        msg = await ctx.send(embed=discord.Embed(title="📡 YouTube kanalı aranıyor...", description="▰▱▱▱", color=0xFF0000))
        try:
            kid = await yt_kanal_coz(kaynak)
        except Exception as e:
            print(f"yt çözme hatası: {e!r}")
            kid = None
        if not kid:
            return await msg.edit(embed=discord.Embed(
                description=("❌ Kanalı bulamadım. Kanal **ID**'sini (`UC...` ile başlar) yazmayı dene.\n"
                             "YouTube Studio → Ayarlar → Kanal → Gelişmiş ayarlar bölümünde yazar."), color=0xED4245))
        if any(x["kid"] == kid for x in liste):
            return await msg.edit(embed=discord.Embed(description="Bu kanal zaten ekli.", color=0x95A5A6))
        await msg.edit(embed=discord.Embed(title="📡 Videolar okunuyor...", description="▰▰▰▱", color=0xFF0000))
        try:
            ad, videolar = await yt_videolar(kid)
        except Exception as e:
            print(f"yt rss hatası: {e!r}")
            return await msg.edit(embed=discord.Embed(description="❌ Kanalın videolarını okuyamadım. ID doğru mu? Biraz sonra tekrar dene.", color=0xED4245))
        liste.append({"kid": kid, "ad": ad or kid, "kanal": kanal.id, "rol": rol.id if rol else None,
                      "gecmis": [v["id"] for v in videolar]})
        isaretle22()
        embed = discord.Embed(
            title="✅ YouTube bildirimi kuruldu!",
            description=f"📺 **{ad}**\nYeni video çıkınca {kanal.mention} kanalında duyurulacak" + (f" ({rol.mention} etiketlenir)." if rol else "."),
            color=0x57F287)
        embed.set_footer(text=f"Her {YT_ARALIK // 60} dakikada bir kontrol edilir • Test: td!yttest {len(liste)}")
        await msg.edit(embed=embed, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="ytliste")
    @commands.guild_only()
    async def ytliste(self, ctx):
        """Ekli YouTube kanallarını göster"""
        liste = veri["yt"].get(str(ctx.guild.id), [])
        if not liste:
            return await ctx.send("📺 Ekli YouTube kanalı yok. `td!ytekle <kanal> [#kanal] [@rol]`")
        satirlar = [f"**{i}.** 📺 {x['ad']} → <#{x['kanal']}>" + (f" • <@&{x['rol']}>" if x["rol"] else "") for i, x in enumerate(liste, 1)]
        await ctx.send(embed=discord.Embed(title="📺 YouTube Bildirimleri", description="\n".join(satirlar), color=0xFF0000),
                       allowed_mentions=NO_PING)

    @commands.hybrid_command(name="ytsil", usage="<numara>")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def ytsil(self, ctx, numara: int):
        """YouTube bildirimini sil"""
        liste = veri["yt"].get(str(ctx.guild.id), [])
        if not 1 <= numara <= len(liste):
            return await ctx.send("❌ Geçersiz numara. `td!ytliste` ile bak.")
        x = liste.pop(numara - 1)
        isaretle22()
        await ctx.send(f"🗑️ **{x['ad']}** bildirimi silindi.")

    @commands.hybrid_command(name="yttest", usage="<numara>")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def yttest(self, ctx, numara: int = 1):
        """Kanalın son videosunu test olarak duyur"""
        liste = veri["yt"].get(str(ctx.guild.id), [])
        if not 1 <= numara <= len(liste):
            return await ctx.send("❌ Geçersiz numara. `td!ytliste` ile bak.")
        x = liste[numara - 1]
        try:
            ad, videolar = await yt_videolar(x["kid"])
        except Exception:
            return await ctx.send("❌ Videoları okuyamadım.")
        if not videolar:
            return await ctx.send("Bu kanalda video bulamadım.")
        await self.yt_duyur(ctx.guild, x, videolar[0], ad, test=True)
        await ctx.send("✅ Test duyurusu gönderildi.")

    async def yt_duyur(self, guild, x, video, kanal_adi, test=False):
        kanal = guild.get_channel(x["kanal"])
        if kanal is None:
            return
        rol = guild.get_role(x["rol"]) if x["rol"] else None
        icerik = (f"{rol.mention} " if rol else "") + ("🧪 **(Test)** " if test else "") + f"📺 **{kanal_adi or x['ad']}** yeni video yükledi!"
        kirmizi = 0xFF0000
        msg = await kanal.send(content=icerik, embed=discord.Embed(title="📡 Yeni video yakalandı!", description="▰▱▱▱▱", color=kirmizi),
                               allowed_mentions=discord.AllowedMentions(roles=True))
        await anim_duzenle(msg, [discord.Embed(title="📡 Video hazırlanıyor...", description="▰▰▰▱▱", color=kirmizi)], 0.8)
        await asyncio.sleep(0.8)
        embed = discord.Embed(title=video["baslik"][:250], url=video["link"], description="Hemen izlemek için aşağıdaki butona bas! 🍿", color=kirmizi)
        embed.set_image(url=f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg")
        embed.set_author(name=kanal_adi or x["ad"])
        v = discord.ui.View()
        v.add_item(discord.ui.Button(label="Videoyu İzle", emoji="▶️", url=video["link"]))
        await msg.edit(embed=embed, view=v)

    async def yt_kontrol(self):
        for gid, liste in list(veri["yt"].items()):
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue
            for x in liste:
                try:
                    ad, videolar = await yt_videolar(x["kid"])
                except Exception as e:
                    print(f"yt kontrol hatası ({x['ad']}): {str(e)[:100]}")
                    continue
                yeniler = [v for v in videolar if v["id"] not in x["gecmis"]]
                if not yeniler:
                    continue
                for v in videolar:
                    if v["id"] not in x["gecmis"]:
                        x["gecmis"].append(v["id"])
                x["gecmis"] = x["gecmis"][-60:]
                isaretle22()
                for v in reversed(yeniler[:3]):                 # en eskiden yeniye, en fazla 3 duyuru
                    if yt_eski_mi(v["tarih"]):
                        continue
                    try:
                        await self.yt_duyur(guild, x, v, ad)
                    except discord.HTTPException as e:
                        print(f"yt duyuru hatası: {e!r}")

    # ------------------------------------------------------------------
    # Arka plan
    # ------------------------------------------------------------------
    async def dongu(self):
        await self.bot.wait_until_ready()
        sayac = 0
        son_yt = 0.0
        while not self.bot.is_closed():
            try:
                sayac += 1
                simdi = datetime.datetime.now(TR)
                await self.dogum_kontrol(simdi)
                for gid, s in list(veri["sunucu"].items()):          # raid modu bitişi
                    r = s.get("raid", {})
                    if r.get("bitis") and r["bitis"] <= time.time():
                        r["bitis"] = 0
                        isaretle22()
                        guild = self.bot.get_guild(int(gid))
                        if guild is not None:
                            await log(guild, "✅ Raid modu bitti", "Raid modu süresi doldu. Koruma açık kalmaya devam ediyor.", discord.Color.green())
                if time.time() - son_yt >= YT_ARALIK:
                    son_yt = time.time()
                    await self.yt_kontrol()
                if kirli and sayac % 2 == 0:
                    kaydet()
            except Exception as e:
                print(f"v22 arka plan hatası: {e!r}")
            await asyncio.sleep(30)


# ----------------------------------------------------------------------
# Yükleme (main.py setup_hook içinden çağrılır)
# ----------------------------------------------------------------------
async def kur(bot, g):
    yukle()
    bot.add_dynamic_items(DogrulaButon)
    cog = V22(bot, g)
    await bot.add_cog(cog)
    cog.gorev = asyncio.create_task(cog.dongu())
    atexit.register(lambda: kaydet() if kirli else None)
    g["EK_KATEGORILER"].update(YARDIM)
    if not PIL_VAR:
        print("v22: pillow kurulu değil, `kart` komutu çalışmayacak (requirements.txt'ye `pillow` ekle).")
