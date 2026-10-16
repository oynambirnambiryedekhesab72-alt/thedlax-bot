# -*- coding: utf-8 -*-
"""THEDLAX v1.6 - Müzik sistemi (ses kanalında YouTube'dan müzik).
Gereksinimler (requirements.txt): discord.py[voice]  yt-dlp  imageio-ffmpeg
Bu dosya yoksa bot yine açılır, sadece müzik komutları olmaz. Kontrol için: td/muzikdurum"""
import os
import time
import random
import asyncio
import shutil
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from ytmusicapi import YTMusic   # YouTube Music araması (resmi şarkı sonuçları için)
except ImportError:
    YTMusic = None

KUYRUK_LIMIT = 100       # kuyrukta en fazla şarkı
BOSTA_BEKLEME = 180      # müzik bitince kaç sn sonra ses kanalından çıksın
YALNIZ_BEKLEME = 60      # kanalda sadece bot kalırsa kaç sn sonra çıksın
STREAM_OMRU = 1200       # çözülen ses linki bu kadar sn sonra yenilenir (linkler süresi dolar)
FFMPEG_ONCESI = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"

YDL_AYAR = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "source_address": "0.0.0.0",   # IPv4 (bazı hostlarda IPv6 sorun çıkarır)
    "socket_timeout": 15,
}


def ffmpeg_yolu():
    yol = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
    if yol:
        return yol
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def opus_hazir():
    if discord.opus.is_loaded():
        return True
    for ad in ("libopus.so.0", "libopus.so", "opus", "libopus-0.x64.dll"):
        try:
            discord.opus.load_opus(ad)
        except Exception:
            continue
        if discord.opus.is_loaded():
            return True
    return discord.opus.is_loaded()


def sure_yaz(sn):
    if not sn:
        return "🔴 Canlı"
    sn = int(sn)
    s, kalan = divmod(sn, 3600)
    d, sn = divmod(kalan, 60)
    return f"{s}:{d:02d}:{sn:02d}" if s else f"{d}:{sn:02d}"


_ytm = None


def muzik_ara(sorgu):
    """YouTube Music'te şarkı ara → videoId (olmazsa None, o zaman normal YouTube araması yapılır)."""
    global _ytm
    if YTMusic is None:
        return None
    try:
        if _ytm is None:
            _ytm = YTMusic()
        for r in _ytm.search(sorgu, filter="songs", limit=3):
            if r.get("videoId"):
                return r["videoId"]
    except Exception:
        return None
    return None


def cek(sorgu):
    """Şarkı adı ya da link → şarkı bilgisi (ağır iş, thread'de çalıştırılır)."""
    ayar = dict(YDL_AYAR)
    if os.path.exists("cookies.txt"):
        ayar["cookiefile"] = "cookies.txt"
    if not sorgu.startswith(("http://", "https://")):
        vid = muzik_ara(sorgu)
        sorgu = f"https://www.youtube.com/watch?v={vid}" if vid else f"ytsearch1:{sorgu}"
    with yt_dlp.YoutubeDL(ayar) as ydl:
        bilgi = ydl.extract_info(sorgu, download=False)
    if bilgi and bilgi.get("entries"):
        girdiler = [e for e in bilgi["entries"] if e]
        bilgi = girdiler[0] if girdiler else None
    if not bilgi or not bilgi.get("url"):
        return None
    return {
        "baslik": (bilgi.get("title") or "Bilinmeyen")[:150],
        "sayfa": bilgi.get("webpage_url") or sorgu,
        "stream": bilgi["url"],
        "sure": bilgi.get("duration"),
        "resim": bilgi.get("thumbnail"),
        "zaman": time.time(),
        "isteyen": None,
    }


def hata_mesaji(e):
    t = str(e).lower()
    if "sign in" in t or ("confirm" in t and "bot" in t):
        return ("❌ YouTube bu sunucudan gelen isteği engelledi (bot doğrulaması). Bot-hosting gibi hostların IP'leri "
                "sık engellenir. Çözüm: tarayıcıdan YouTube `cookies.txt` dışa aktarıp bot klasörüne koy.")
    if "private" in t or "unavailable" in t or "not available" in t:
        return "❌ Bu video özel ya da erişilemiyor."
    if "age" in t and "restrict" in t:
        return "❌ Bu video yaş kısıtlamalı."
    return f"❌ Şarkı alınamadı: `{str(e)[:150]}`"


class Durum:
    def __init__(self):
        self.kuyruk = deque()
        self.simdiki = None
        self.dongu = "kapali"    # kapali / tek / kuyruk
        self.ses = 0.5
        self.kanal = None        # bildirimlerin gideceği metin kanalı
        self.atla = False
        self.bosta_id = 0
        self.kilit = asyncio.Lock()


class Muzik(commands.Cog):
    """YouTube'dan müzik çalma"""

    def __init__(self, bot):
        self.bot = bot
        self.durumlar = {}
        self.ffmpeg = ffmpeg_yolu()

    def durum(self, gid):
        return self.durumlar.setdefault(gid, Durum())

    def hazir_mi(self):
        if yt_dlp is None:
            return "❌ `yt-dlp` kurulu değil. requirements.txt'e `yt-dlp` ekleyip botu yeniden başlat."
        if self.ffmpeg is None:
            self.ffmpeg = ffmpeg_yolu()
            if self.ffmpeg is None:
                return "❌ ffmpeg bulunamadı. requirements.txt'e `imageio-ffmpeg` ekleyip botu yeniden başlat."
        if not opus_hazir():
            return ("❌ Opus (ses) kütüphanesi yüklü değil. Bu sunucu müziği desteklemiyor olabilir. "
                    "Ayrıntı için `muzikdurum` yaz.")
        return None

    def kontrol(self, ctx):
        vc = ctx.voice_client
        if vc is None or not vc.is_connected():
            return None, "❌ Şu an ses kanalında değilim."
        v = ctx.author.voice
        if v is None or v.channel != vc.channel:
            return None, "❌ Benimle aynı ses kanalında olmalısın."
        return vc, None

    @staticmethod
    def embed(t, baslik="🎶 Şimdi çalıyor"):
        e = discord.Embed(title=baslik, description=f"[{t['baslik']}]({t['sayfa']})", color=discord.Color.blurple())
        e.add_field(name="Süre", value=sure_yaz(t["sure"]))
        if t.get("isteyen"):
            e.add_field(name="İsteyen", value=f"<@{t['isteyen']}>")
        if t.get("resim"):
            e.set_thumbnail(url=t["resim"])
        return e

    # ---------------- oynatma motoru ----------------
    def bitti(self, guild, err):
        if err:
            print(f"Müzik oynatma hatası: {err!r}")
        asyncio.run_coroutine_threadsafe(self.sonraki(guild), self.bot.loop)

    async def sonraki(self, guild, duyur=True):
        d = self.durum(guild.id)
        async with d.kilit:
            vc = guild.voice_client
            if vc is None or not vc.is_connected():
                d.simdiki = None
                return None
            if vc.is_playing() or vc.is_paused():
                return d.simdiki
            if d.dongu == "tek" and d.simdiki and not d.atla:
                t = d.simdiki
            else:
                if d.dongu == "kuyruk" and d.simdiki:
                    d.kuyruk.append(d.simdiki)
                t = d.kuyruk.popleft() if d.kuyruk else None
            d.atla = False
            d.simdiki = t
            if t is None:
                d.bosta_id += 1
                asyncio.create_task(self.bosta_cik(guild, d.bosta_id))
                return None
            d.bosta_id += 1
            try:
                if time.time() - t["zaman"] > STREAM_OMRU:
                    yeni = await asyncio.to_thread(cek, t["sayfa"])
                    if yeni:
                        t["stream"], t["zaman"] = yeni["stream"], time.time()
                kaynak = discord.FFmpegPCMAudio(t["stream"], executable=self.ffmpeg,
                                                before_options=FFMPEG_ONCESI, options="-vn")
                kaynak = discord.PCMVolumeTransformer(kaynak, volume=d.ses)
                vc.play(kaynak, after=lambda err, g=guild: self.bitti(g, err))
            except Exception as e:
                print(f"Müzik başlatılamadı: {e!r}")
                d.simdiki = None
                if d.kanal:
                    try:
                        await d.kanal.send(f"❌ **{t['baslik']}** çalınamadı, sıradakine geçiyorum.")
                    except discord.HTTPException:
                        pass
                asyncio.create_task(self.sonraki(guild))
                return None
        if duyur and d.kanal:
            try:
                await d.kanal.send(embed=self.embed(t))
            except discord.HTTPException:
                pass
        return t

    async def bosta_cik(self, guild, token):
        await asyncio.sleep(BOSTA_BEKLEME)
        d = self.durum(guild.id)
        vc = guild.voice_client
        if vc is None or d.bosta_id != token or vc.is_playing() or vc.is_paused() or d.kuyruk or d.simdiki:
            return
        if d.kanal:
            try:
                await d.kanal.send("👋 Uzun süre müzik çalmadığı için ses kanalından ayrıldım.")
            except discord.HTTPException:
                pass
        await vc.disconnect()
        self.durumlar.pop(guild.id, None)

    async def yalniz_kontrol(self, guild, kanal):
        await asyncio.sleep(YALNIZ_BEKLEME)
        vc = guild.voice_client
        if vc is not None and vc.channel == kanal and all(m.bot for m in kanal.members):
            await vc.disconnect()
            self.durumlar.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_voice_state_update(self, uye, before, after):
        guild = uye.guild
        if uye.id == self.bot.user.id:
            if after.channel is None:           # bot atıldı / bağlantı koptu
                self.durumlar.pop(guild.id, None)
            return
        vc = guild.voice_client
        if vc is not None and vc.channel is not None and before.channel == vc.channel \
                and after.channel != vc.channel and all(m.bot for m in vc.channel.members):
            asyncio.create_task(self.yalniz_kontrol(guild, vc.channel))

    # ---------------- komutlar ----------------
    @commands.command(name="cal", aliases=["play", "p"], usage="<şarkı adı veya link>")
    @app_commands.describe(sarki="Şarkı adı ya da YouTube linki")
    @commands.guild_only()
    async def cal(self, ctx, *, sarki: str):
        """Şarkı çal ya da kuyruğa ekle"""
        hata = self.hazir_mi()
        if hata:
            return await ctx.send(hata)
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return await ctx.send("❌ Önce bir ses kanalına girmen lazım.")
        kanal = ctx.author.voice.channel
        izin = kanal.permissions_for(ctx.guild.me)
        if not (izin.connect and izin.speak):
            return await ctx.send("❌ O ses kanalına bağlanma ya da konuşma iznim yok.")
        d = self.durum(ctx.guild.id)
        if len(d.kuyruk) >= KUYRUK_LIMIT:
            return await ctx.send(f"❌ Kuyruk dolu (en fazla {KUYRUK_LIMIT} şarkı).")
        vc = ctx.voice_client
        if vc is not None and vc.channel != kanal and (vc.is_playing() or vc.is_paused()):
            return await ctx.send("❌ Şu an başka bir ses kanalında çalıyorum.")
        await ctx.defer()
        try:
            t = await asyncio.to_thread(cek, sarki.strip())
        except Exception as e:
            return await ctx.send(hata_mesaji(e))
        if not t:
            return await ctx.send("❌ Sonuç bulunamadı.")
        t["isteyen"] = ctx.author.id
        try:
            if vc is None:
                vc = await kanal.connect(self_deaf=True, timeout=20)
            elif vc.channel != kanal:
                await vc.move_to(kanal)
        except RuntimeError as e:
            return await ctx.send(f"❌ Ses kütüphanesi eksik: `{e}`. requirements.txt'e `discord.py[voice]` yaz "
                                  f"(PyNaCl ve davey gerekir).")
        except (asyncio.TimeoutError, discord.ClientException, discord.HTTPException) as e:
            return await ctx.send(f"❌ Ses kanalına bağlanamadım: `{e!r}`"[:300])
        d.kanal = ctx.channel
        calisiyor = vc.is_playing() or vc.is_paused() or d.simdiki is not None
        d.kuyruk.append(t)
        if calisiyor:
            return await ctx.send(embed=self.embed(t, f"➕ Kuyruğa eklendi (#{len(d.kuyruk)})"))
        basladi = await self.sonraki(ctx.guild, duyur=False)
        if basladi:
            await ctx.send(embed=self.embed(basladi))
        else:
            await ctx.send("❌ Şarkı başlatılamadı. `muzikdurum` yazıp eksik var mı bak.")

    @commands.command(name="durdur", aliases=["pause"])
    @commands.guild_only()
    async def durdur(self, ctx):
        """Müziği duraklat"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        if not vc.is_playing():
            return await ctx.send("❌ Şu an çalan bir şey yok.")
        vc.pause()
        await ctx.send("⏸️ Duraklatıldı. `devam` ile sürdür.")

    @commands.command(name="devam", aliases=["resume"])
    @commands.guild_only()
    async def devam(self, ctx):
        """Duraklatılan müziği sürdür"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        if not vc.is_paused():
            return await ctx.send("❌ Duraklatılmış bir şey yok.")
        vc.resume()
        await ctx.send("▶️ Devam ediyor.")

    @commands.command(name="atla", aliases=["skip"])
    @commands.guild_only()
    async def atla(self, ctx):
        """Şarkıyı atla"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        d = self.durum(ctx.guild.id)
        if not (vc.is_playing() or vc.is_paused()):
            return await ctx.send("❌ Şu an çalan bir şey yok.")
        ad = d.simdiki["baslik"] if d.simdiki else "şarkı"
        d.atla = True
        vc.stop()
        await ctx.send(f"⏭️ Atlandı: **{ad}**")

    @commands.command(name="dur", aliases=["stop"])
    @commands.guild_only()
    async def dur(self, ctx):
        """Müziği durdur ve kuyruğu temizle (kanalda kalır)"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        d = self.durum(ctx.guild.id)
        d.kuyruk.clear()
        d.simdiki = None
        vc.stop()
        await ctx.send("⏹️ Durdurdum ve kuyruğu temizledim.")

    @commands.command(name="ayril", aliases=["dc", "leave", "disconnect"])
    @commands.guild_only()
    async def ayril(self, ctx):
        """Botu ses kanalından çıkar"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        d = self.durum(ctx.guild.id)
        d.kuyruk.clear()
        d.simdiki = None
        await vc.disconnect()
        self.durumlar.pop(ctx.guild.id, None)
        await ctx.send("👋 Ses kanalından ayrıldım.")

    @commands.command(name="kuyruk", aliases=["queue", "q"], usage="[sayfa]")
    @commands.guild_only()
    async def kuyruk(self, ctx, sayfa: int = 1):
        """Şarkı kuyruğunu göster"""
        d = self.durum(ctx.guild.id)
        if d.simdiki is None and not d.kuyruk:
            return await ctx.send("📭 Kuyruk boş. `cal <şarkı>` ile başla.")
        liste = list(d.kuyruk)
        sayfa_say = max(1, -(-len(liste) // 10))
        sayfa = max(1, min(sayfa, sayfa_say))
        parca = liste[(sayfa - 1) * 10: sayfa * 10]
        satir = [f"**{(sayfa - 1) * 10 + i}.** {t['baslik']} `{sure_yaz(t['sure'])}`" for i, t in enumerate(parca, 1)]
        e = discord.Embed(title="📜 Müzik kuyruğu", color=discord.Color.blurple())
        if d.simdiki:
            e.add_field(name="🎶 Şimdi çalıyor", value=f"{d.simdiki['baslik']} `{sure_yaz(d.simdiki['sure'])}`", inline=False)
        e.add_field(name="Sırada", value="\n".join(satir) or "Sırada şarkı yok.", inline=False)
        toplam = sum(t["sure"] or 0 for t in liste)
        e.set_footer(text=f"Sayfa {sayfa}/{sayfa_say} • {len(liste)} şarkı • Döngü: {d.dongu} • Toplam {sure_yaz(toplam) if toplam else '0:00'}")
        await ctx.send(embed=e)

    @commands.command(name="calan", aliases=["np", "nowplaying"])
    @commands.guild_only()
    async def calan(self, ctx):
        """Şu an çalan şarkıyı göster"""
        d = self.durum(ctx.guild.id)
        if d.simdiki is None:
            return await ctx.send("❌ Şu an çalan bir şey yok.")
        await ctx.send(embed=self.embed(d.simdiki))

    @commands.command(name="ses", aliases=["volume", "vol"], usage="[1-100]")
    @app_commands.describe(sayi="Ses seviyesi (1-100)")
    @commands.guild_only()
    async def ses(self, ctx, sayi: int = None):
        """Ses seviyesini göster / ayarla"""
        d = self.durum(ctx.guild.id)
        if sayi is None:
            return await ctx.send(f"🔊 Ses seviyesi: **%{int(d.ses * 100)}**")
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        if sayi < 1 or sayi > 100:
            return await ctx.send("❌ Ses 1 ile 100 arasında olmalı.")
        d.ses = sayi / 100
        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = d.ses
        await ctx.send(f"🔊 Ses seviyesi: **%{sayi}**")

    @commands.command(name="dongu", aliases=["loop"], usage="[kapali|tek|kuyruk]")
    @app_commands.describe(mod="kapali, tek (şarkıyı tekrarla) ya da kuyruk (tüm listeyi tekrarla)")
    @commands.guild_only()
    async def dongu(self, ctx, mod: str = None):
        """Döngü modu: kapalı / tek şarkı / tüm kuyruk"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        d = self.durum(ctx.guild.id)
        eslesme = {"kapali": "kapali", "kapat": "kapali", "off": "kapali", "tek": "tek", "sarki": "tek",
                   "kuyruk": "kuyruk", "hepsi": "kuyruk", "liste": "kuyruk"}
        if mod is None:
            d.dongu = {"kapali": "tek", "tek": "kuyruk", "kuyruk": "kapali"}[d.dongu]
        elif mod.lower() in eslesme:
            d.dongu = eslesme[mod.lower()]
        else:
            return await ctx.send("❌ Mod: `kapali`, `tek` ya da `kuyruk`.")
        ad = {"kapali": "➡️ Kapalı", "tek": "🔂 Tek şarkı", "kuyruk": "🔁 Tüm kuyruk"}[d.dongu]
        await ctx.send(f"Döngü: **{ad}**")

    @commands.command(name="karistir", aliases=["shuffle"])
    @commands.guild_only()
    async def karistir(self, ctx):
        """Kuyruğu karıştır"""
        vc, hata = self.kontrol(ctx)
        if hata:
            return await ctx.send(hata)
        d = self.durum(ctx.guild.id)
        if len(d.kuyruk) < 2:
            return await ctx.send("❌ Karıştırmak için kuyrukta en az 2 şarkı olmalı.")
        liste = list(d.kuyruk)
        random.shuffle(liste)
        d.kuyruk = deque(liste)
        await ctx.send(f"🔀 {len(liste)} şarkı karıştırıldı.")

    @commands.command(name="muzikdurum", aliases=["muziktest"])
    async def muzikdurum(self, ctx):
        """Müzik için gereken her şey kurulu mu kontrol et"""
        def ok(x):
            return "✅" if x else "❌"
        try:
            import nacl
            nacl_ok = True
        except ImportError:
            nacl_ok = False
        try:
            import davey
            davey_ok = True
        except ImportError:
            davey_ok = False
        ytv = yt_dlp.version.__version__ if yt_dlp else None
        ff = ffmpeg_yolu()
        satir = [
            f"{ok(yt_dlp)} yt-dlp {('(' + ytv + ')') if ytv else '— `yt-dlp` ekle'}",
            f"{ok(ff)} ffmpeg {'bulundu' if ff else '— `imageio-ffmpeg` ekle'}",
            f"{ok(opus_hazir())} Opus ses kütüphanesi",
            f"{'✅' if YTMusic else '➖'} ytmusicapi {'(YouTube Music araması açık)' if YTMusic else 'yok, normal YouTube araması kullanılır'}",
            f"{ok(nacl_ok)} PyNaCl {'' if nacl_ok else '— `discord.py[voice]` yaz'}",
            f"{ok(davey_ok)} davey (Discord ses şifrelemesi) {'' if davey_ok else '— `discord.py[voice]` yaz'}",
            f"{'✅' if os.path.exists('cookies.txt') else '➖'} cookies.txt "
            f"({'var' if os.path.exists('cookies.txt') else 'yok, YouTube engellerse gerekebilir'})",
            f"ℹ️ discord.py {discord.__version__}",
        ]
        await ctx.send(embed=discord.Embed(title="🎵 Müzik sistemi durumu", description="\n".join(satir),
                                            color=discord.Color.blurple()))


async def kur(bot, g):
    await bot.add_cog(Muzik(bot))
    g["EK_KATEGORILER"]["🎵 Müzik"] = [
        "`cal <şarkı/link>` Çal ya da kuyruğa ekle",
        "`durdur` / `devam` Duraklat / sürdür",
        "`atla` / `dur` / `ayril` Atla / durdur+temizle / kanaldan çık",
        "`kuyruk [sayfa]` / `calan` Kuyruk / şimdi çalan",
        "`ses [1-100]` / `dongu` / `karistir` Ses, döngü, karıştır",
        "`muzikdurum` Kurulum kontrolü",
    ]
