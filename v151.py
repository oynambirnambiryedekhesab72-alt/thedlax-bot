# -*- coding: utf-8 -*-
"""
THEDLAX BOT v1.5.1 FINAL - son güncelleme modülü

main.py bunu otomatik yükler (v15.py'den sonra). İçindekiler:
  - 🎵 Müzik sistemi : cal, durdur, devam, gec, dur, kuyruk, simdi, ses, dongu, karistir, kuyrukcikar
  - ✉️ DM sistemi    : dm, dmduyuru, dmkapat, dmac
  - 🧩 5 yeni komut  : banner, emojibuyut, askolcer, tersyaz, kanalbilgi

Müzik için gerekenler (requirements.txt'te var): discord.py[voice], yt-dlp, PyNaCl, imageio-ffmpeg
Not: Sunucuda libopus kurulu olmalı (Linux: apt install libopus0). ffmpeg yoksa imageio-ffmpeg kullanılır.
"""
import os
import re
import json
import time
import shutil
import random
import asyncio
import hashlib
import ctypes.util
from collections import deque
from typing import Union

import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except Exception:
    yt_dlp = None

try:
    import nacl  # noqa: F401
    NACL_VAR = True
except Exception:
    NACL_VAR = False

NO_PING = discord.AllowedMentions.none()
DOSYA = "veri_v151.json"

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
KUYRUK_MAX = 50              # Sunucu başına kuyruktaki en fazla şarkı
SARKI_MAX_SN = 3 * 3600      # Bundan uzun videolar çalınmaz
BOSTA_SN = 180               # Çalan yoksa kaç saniye sonra kanaldan çıksın
YALNIZ_SN = 60               # Kanalda kimse kalmazsa kaç saniye sonra çıksın
DM_TOPLU_MAX = 100           # dmduyuru tek seferde en fazla kaç kişiye
DM_ARALIK = 1.5              # dmduyuru'da iki mesaj arası saniye (Discord limiti için)

veri = {"dm_kapali": []}
ARKA = set()


# ----------------------------------------------------------------------
# Veri
# ----------------------------------------------------------------------
def veri_yukle():
    try:
        with open(DOSYA, "r", encoding="utf-8") as f:
            v = json.load(f)
        veri["dm_kapali"] = [int(x) for x in v.get("dm_kapali", [])]
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"v151 verisi okunamadı: {e!r}")


def veri_kaydet():
    gecici = DOSYA + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        os.replace(gecici, DOSYA)
    except Exception as e:
        print(f"v151 verisi kaydedilemedi: {e!r}")


# ----------------------------------------------------------------------
# Müzik altyapısı
# ----------------------------------------------------------------------
YDL_AYAR = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
    "retries": 3,
    "source_address": "0.0.0.0",
}
FF_ONCE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"


def ffmpeg_yolu():
    yol = shutil.which("ffmpeg")
    if yol:
        return yol
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def opus_hazirla():
    if discord.opus.is_loaded():
        return True
    adaylar = [ctypes.util.find_library("opus"), "libopus.so.0", "libopus.so",
               "libopus-0.dll", "libopus.0.dylib", "/opt/homebrew/lib/libopus.dylib"]
    for ad in adaylar:
        if not ad:
            continue
        try:
            discord.opus.load_opus(ad)
            if discord.opus.is_loaded():
                return True
        except Exception:
            continue
    return discord.opus.is_loaded()


def muzik_hata():
    """Müzik için eksik bir şey varsa açıklama döndürür, her şey tamamsa None."""
    if yt_dlp is None:
        return "❌ Müzik için `yt-dlp` kurulu değil. `requirements.txt` içindekileri yükle."
    if not NACL_VAR:
        return "❌ Müzik için `PyNaCl` kurulu değil (`discord.py[voice]`)."
    if ffmpeg_yolu() is None:
        return "❌ `ffmpeg` bulunamadı. `imageio-ffmpeg` paketini yükle ya da ffmpeg kur."
    if not opus_hazirla():
        return "❌ `libopus` bulunamadı. Sunucuya kur (Linux: `apt install libopus0`)."
    return None


def sure_str(sn):
    if not sn:
        return "🔴 CANLI"
    sn = int(sn)
    s, d = sn % 60, (sn // 60) % 60
    h = sn // 3600
    return f"{h}:{d:02d}:{s:02d}" if h else f"{d}:{s:02d}"


def ilerleme(gecen, toplam, n=14):
    if not toplam:
        return "🔴 CANLI"
    k = min(int(n * min(gecen / toplam, 1)), n - 1)
    return "▬" * k + "🔘" + "▬" * (n - k - 1)


def _cozumle(sorgu):
    ayar = dict(YDL_AYAR)
    if os.path.exists("cookies.txt"):          # YouTube "bot değilim" engeli için (isteğe bağlı)
        ayar["cookiefile"] = "cookies.txt"
    link = bool(re.match(r"https?://", sorgu))

    def cikar(hedef):
        with yt_dlp.YoutubeDL(ayar) as ydl:
            return ydl.extract_info(hedef, download=False)

    if link:
        b = cikar(sorgu)
    else:
        try:
            b = cikar(f"ytsearch1:{sorgu}")
        except Exception as e:      # YouTube engelledi ya da hata verdi -> SoundCloud'u dene
            print(f"YouTube araması başarısız, SoundCloud deneniyor: {str(e)[:300]}")
            b = cikar(f"scsearch1:{sorgu}")
    if b is not None and b.get("entries"):
        b = next((e for e in b["entries"] if e), None)
    if b is None:
        raise ValueError("Sonuç bulunamadı")
    stream = b.get("url")
    if not stream:
        raise ValueError("Ses akışı bulunamadı")
    return {
        "baslik": b.get("title") or "Bilinmeyen",
        "sayfa": b.get("webpage_url") or sorgu,
        "sure": b.get("duration") or 0,
        "canli": bool(b.get("is_live")),
        "kucuk": b.get("thumbnail"),
        "stream": stream,
    }


async def cozumle(sorgu):
    dongu = asyncio.get_running_loop()
    return await asyncio.wait_for(dongu.run_in_executor(None, _cozumle, sorgu), timeout=45)


class Sarki:
    __slots__ = ("baslik", "sayfa", "sure", "kucuk", "ekleyen", "stream", "stream_zaman")

    def __init__(self, bilgi, ekleyen):
        self.baslik = bilgi["baslik"]
        self.sayfa = bilgi["sayfa"]
        self.sure = bilgi["sure"]
        self.kucuk = bilgi["kucuk"]
        self.stream = bilgi["stream"]
        self.stream_zaman = time.time()
        self.ekleyen = ekleyen


DONGU_ADI = {"kapali": "Kapalı", "sarki": "🔂 Şarkı", "kuyruk": "🔁 Kuyruk"}


class MuzikView(discord.ui.View):
    def __init__(self, o):
        super().__init__(timeout=None)
        self.o = o

    async def interaction_check(self, it):
        vc = it.guild.voice_client if it.guild else None
        if vc is None or getattr(it.user, "voice", None) is None or it.user.voice.channel != vc.channel:
            await it.response.send_message("❌ Benimle aynı ses kanalında olmalısın.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary)
    async def b_duraklat(self, it, btn):
        vc = it.guild.voice_client
        if vc.is_paused():
            self.o.devam_et()
            await it.response.send_message("▶️ Devam ediyor.", ephemeral=True)
        elif vc.is_playing():
            self.o.duraklat()
            await it.response.send_message("⏸️ Duraklatıldı.", ephemeral=True)
        else:
            await it.response.send_message("Şu an çalan bir şey yok.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def b_gec(self, it, btn):
        if self.o.gec():
            await it.response.send_message("⏭️ Geçildi.", ephemeral=True)
        else:
            await it.response.send_message("Şu an çalan bir şey yok.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def b_dongu(self, it, btn):
        sira = ["kapali", "sarki", "kuyruk"]
        self.o.dongu = sira[(sira.index(self.o.dongu) + 1) % 3]
        await it.response.send_message(f"Döngü: **{DONGU_ADI[self.o.dongu]}**", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def b_dur(self, it, btn):
        await it.response.send_message("⏹️ Müzik durduruldu, kanaldan ayrılıyorum.", ephemeral=True)
        await self.o.hepsini_durdur()


class Oynatici:
    """Her sunucu için ayrı müzik oynatıcı (kuyruk, ses seviyesi, döngü)."""

    def __init__(self, cog, guild):
        self.cog = cog
        self.guild = guild
        self.kuyruk = deque()
        self.simdi = None
        self.ses = 0.5
        self.dongu = "kapali"          # kapali / sarki / kuyruk
        self.kanal = None              # bildirimlerin gideceği metin kanalı
        self.baslangic = 0.0
        self.durak_zaman = None
        self.duraklama = 0.0
        self.atla = False
        self.np_mesaj = None
        self.np_view = None
        self.bosta = None
        self.kilit = asyncio.Lock()

    # ---------------- Süre takibi ----------------
    def gecen(self):
        if not self.simdi:
            return 0
        son = self.durak_zaman or time.time()
        return max(0, son - self.baslangic - self.duraklama)

    # ---------------- Kontroller ----------------
    def duraklat(self):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            self.durak_zaman = time.time()

    def devam_et(self):
        vc = self.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            if self.durak_zaman:
                self.duraklama += time.time() - self.durak_zaman
            self.durak_zaman = None

    def gec(self):
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.atla = True
            if vc.is_paused():
                self.devam_et()
            vc.stop()
            return True
        return False

    def ses_ayarla(self, yuzde):
        self.ses = yuzde / 100
        vc = self.guild.voice_client
        if vc and vc.source is not None and hasattr(vc.source, "volume"):
            vc.source.volume = self.ses

    async def hepsini_durdur(self):
        self.kuyruk.clear()
        self.simdi = None
        self.dongu = "kapali"
        vc = self.guild.voice_client
        if vc is not None:
            try:
                await vc.disconnect()
            except Exception:
                pass
        await self.temizle()

    # ---------------- Yardımcılar ----------------
    async def yaz(self, metin=None, **kw):
        if self.kanal is None:
            return None
        try:
            return await self.kanal.send(metin, allowed_mentions=NO_PING, **kw)
        except discord.HTTPException:
            return None

    async def np_temizle(self):
        if self.np_view is not None:
            self.np_view.stop()
            self.np_view = None
        if self.np_mesaj is not None:
            try:
                await self.np_mesaj.edit(view=None)
            except discord.HTTPException:
                pass
            self.np_mesaj = None

    def bosta_iptal(self):
        if self.bosta is not None:
            self.bosta.cancel()
            self.bosta = None

    async def temizle(self):
        self.bosta_iptal()
        self.simdi = None
        await self.np_temizle()

    def bosta_baslat(self):
        self.bosta_iptal()
        self.bosta = asyncio.create_task(self._bosta_bekle())

    async def _bosta_bekle(self):
        try:
            await asyncio.sleep(BOSTA_SN)
        except asyncio.CancelledError:
            return
        vc = self.guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused() and not self.kuyruk:
            await self.yaz("👋 Uzun süredir çalan bir şey olmadığı için kanaldan ayrıldım.")
            try:
                await vc.disconnect()
            except Exception:
                pass

    # ---------------- Çalma ----------------
    async def kaynak(self, s):
        if not s.stream or time.time() - s.stream_zaman > 300:   # akış linkleri süresi dolar, yenile
            bilgi = await cozumle(s.sayfa)
            s.stream = bilgi["stream"]
            s.stream_zaman = time.time()
        src = discord.FFmpegPCMAudio(
            s.stream, executable=ffmpeg_yolu(), before_options=FF_ONCE, options="-vn")
        return discord.PCMVolumeTransformer(src, volume=self.ses)

    def bitti(self, hata):
        if hata:
            print(f"Müzik oynatma hatası: {hata!r}")
        asyncio.run_coroutine_threadsafe(self.sonraki(), self.cog.bot.loop)

    async def sonraki(self):
        async with self.kilit:
            vc = self.guild.voice_client
            if vc is None or not vc.is_connected():
                await self.temizle()
                self.kuyruk.clear()
                return
            if vc.is_playing() or vc.is_paused():
                return
            while True:
                if self.simdi and self.dongu == "sarki" and not self.atla:
                    sarki = self.simdi
                else:
                    if self.simdi and self.dongu == "kuyruk":
                        self.kuyruk.append(self.simdi)
                    sarki = self.kuyruk.popleft() if self.kuyruk else None
                self.atla = False
                self.simdi = sarki
                if sarki is None:
                    await self.np_temizle()
                    self.bosta_baslat()
                    return
                try:
                    src = await self.kaynak(sarki)
                except Exception as e:
                    print(f"Şarkı açılamadı: {e!r}")
                    await self.yaz(f"❌ **{discord.utils.escape_markdown(sarki.baslik)}** çalınamadı, sıradakine geçiyorum.")
                    self.simdi = None
                    continue
                self.bosta_iptal()
                self.baslangic = time.time()
                self.duraklama = 0.0
                self.durak_zaman = None
                vc.play(src, after=self.bitti)
                await self.np_gonder(sarki)
                return

    def np_embed(self, s):
        e = discord.Embed(
            title="🎵 Şu an çalıyor",
            description=f"**[{discord.utils.escape_markdown(s.baslik)}]({s.sayfa})**",
            color=discord.Color.blurple(),
        )
        e.add_field(name="Süre", value=sure_str(s.sure), inline=True)
        e.add_field(name="Ekleyen", value=s.ekleyen.mention, inline=True)
        e.add_field(name="Ses / Döngü", value=f"%{int(self.ses * 100)} • {DONGU_ADI[self.dongu]}", inline=True)
        if s.kucuk:
            e.set_thumbnail(url=s.kucuk)
        if self.kuyruk:
            e.set_footer(text=f"Sırada {len(self.kuyruk)} şarkı var")
        return e

    async def np_gonder(self, s):
        await self.np_temizle()
        self.np_view = MuzikView(self)
        self.np_mesaj = await self.yaz(embed=self.np_embed(s), view=self.np_view)


class Onay(discord.ui.View):
    def __init__(self, yazar_id):
        super().__init__(timeout=60)
        self.yazar_id = yazar_id
        self.sonuc = False

    async def interaction_check(self, it):
        if it.user.id == self.yazar_id:
            return True
        await it.response.send_message("Bu onay sana ait değil.", ephemeral=True)
        return False

    @discord.ui.button(label="Gönder", emoji="📨", style=discord.ButtonStyle.success)
    async def evet(self, it, btn):
        self.sonuc = True
        self.stop()
        await it.response.edit_message(content="📨 Gönderiliyor...", embed=None, view=None)

    @discord.ui.button(label="İptal", style=discord.ButtonStyle.danger)
    async def hayir(self, it, btn):
        self.stop()
        await it.response.edit_message(content="❎ İptal edildi.", embed=None, view=None)


# ----------------------------------------------------------------------
# Yardım satırları (/help menüsüne eklenir)
# ----------------------------------------------------------------------
YARDIM = {
    "🎵 Müzik": [
        "`cal <şarkı adı / link>` Şarkı çal ya da kuyruğa ekle (ses kanalında olmalısın)",
        "`durdur` / `devam` Duraklat / devam ettir",
        "`gec` Şarkıyı geç",
        "`dur` Müziği bitir ve kanaldan çık",
        "`kuyruk [sayfa]` Sıradaki şarkılar",
        "`simdi` Çalan şarkı ve süre çubuğu",
        "`ses [1-100]` Ses seviyesi",
        "`dongu [kapali/sarki/kuyruk]` Döngü modu",
        "`karistir` Kuyruğu karıştır",
        "`kuyrukcikar <sıra>` Kuyruktan şarkı çıkar",
        "Çalan şarkının mesajındaki butonlarla da yönetebilirsin ⏯️ ⏭️ 🔁 ⏹️",
    ],
    "✉️ DM": [
        "`dm @kişi <mesaj>` Botla özelden mesaj gönder (Mesajları Yönet)",
        "`dmduyuru @rol <mesaj>` Roldeki herkese özelden duyuru (Yönetici, onaylı)",
        "`dmkapat` Sunucudan DM almayı kapat",
        "`dmac` DM almayı tekrar aç",
    ],
    "🧩 Ekstra": [
        "`banner [@kişi]` Profil banner'ı",
        "`emojibuyut <emoji>` Sunucu emojisini büyüt",
        "`askolcer @kişi` Aşk ölçer 💘",
        "`tersyaz <metin>` Yazıyı ters çevir",
        "`kanalbilgi [#kanal]` Kanal bilgisi",
    ],
}


# ----------------------------------------------------------------------
# Komutlar
# ----------------------------------------------------------------------
class V151(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.oynaticilar = {}

    def oynatici(self, guild):
        o = self.oynaticilar.get(guild.id)
        if o is None:
            o = self.oynaticilar[guild.id] = Oynatici(self, guild)
        return o

    @staticmethod
    def ayni_kanal_hata(ctx):
        vc = ctx.guild.voice_client
        if vc is None:
            return "❌ Şu an bir ses kanalında değilim."
        if ctx.author.voice is None or ctx.author.voice.channel != vc.channel:
            return "❌ Benimle aynı ses kanalında olmalısın."
        return None

    def cog_unload(self):
        for o in self.oynaticilar.values():
            o.bosta_iptal()

    # ================= 🎵 Müzik =================
    @commands.hybrid_command(name="cal", aliases=["çal", "play", "p"], usage="<şarkı adı ya da link>")
    @app_commands.describe(sorgu="Şarkı adı ya da YouTube linki")
    @commands.guild_only()
    async def cal(self, ctx, *, sorgu: str):
        """Şarkı çal ya da kuyruğa ekle"""
        hata = muzik_hata()
        if hata:
            return await ctx.send(hata)
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return await ctx.send("❌ Önce bir ses kanalına girmelisin.")
        kanal = ctx.author.voice.channel
        izin = kanal.permissions_for(ctx.guild.me)
        if not (izin.connect and izin.speak):
            return await ctx.send(f"❌ **{kanal.name}** kanalına bağlanma ya da konuşma iznim yok.")
        vc = ctx.guild.voice_client
        if vc is not None and vc.channel != kanal and (vc.is_playing() or vc.is_paused()):
            return await ctx.send(f"❌ Şu an **{vc.channel.name}** kanalında çalıyorum, oraya gelmelisin.")
        o = self.oynatici(ctx.guild)
        if len(o.kuyruk) >= KUYRUK_MAX:
            return await ctx.send(f"❌ Kuyruk dolu (en fazla {KUYRUK_MAX} şarkı).")

        await ctx.defer()
        try:
            bilgi = await cozumle(sorgu.strip())
        except asyncio.TimeoutError:
            return await ctx.send("⏳ Şarkı çok geç bulundu, tekrar dene.")
        except Exception as e:
            mesaj = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            print(f"Müzik arama hatası: {mesaj[:500]}")
            if "Sign in to confirm" in mesaj:
                return await ctx.send("❌ YouTube bu sunucuyu engelledi. Link yerine **şarkı adını** yaz (SoundCloud'dan arayacağım).")
            sebep = mesaj.replace("ERROR: ", "").replace("`", "'")[:180]
            return await ctx.send(f"❌ Şarkı açılamadı.\n`{sebep}`")
        if bilgi["canli"]:
            return await ctx.send("❌ Canlı yayınlar desteklenmiyor.")
        if bilgi["sure"] and bilgi["sure"] > SARKI_MAX_SN:
            return await ctx.send(f"❌ Şarkı çok uzun (en fazla {SARKI_MAX_SN // 3600} saat).")

        try:
            vc = ctx.guild.voice_client
            if vc is None:
                vc = await kanal.connect(self_deaf=True)
            elif vc.channel != kanal:
                await vc.move_to(kanal)
        except Exception as e:
            print(f"Ses kanalına bağlanılamadı: {e!r}")
            return await ctx.send("❌ Ses kanalına bağlanamadım.")

        o.kanal = ctx.channel
        sarki = Sarki(bilgi, ctx.author)
        o.kuyruk.append(sarki)
        if vc.is_playing() or vc.is_paused():
            e = discord.Embed(
                title="➕ Kuyruğa eklendi",
                description=f"**[{discord.utils.escape_markdown(sarki.baslik)}]({sarki.sayfa})**",
                color=discord.Color.green())
            e.add_field(name="Süre", value=sure_str(sarki.sure), inline=True)
            e.add_field(name="Sıra", value=f"#{len(o.kuyruk)}", inline=True)
            if sarki.kucuk:
                e.set_thumbnail(url=sarki.kucuk)
            await ctx.send(embed=e)
        else:
            await ctx.send(f"🔎 Bulundu: **{discord.utils.escape_markdown(sarki.baslik)}**")
            await o.sonraki()

    @commands.hybrid_command(name="durdur", aliases=["pause", "duraklat"])
    @commands.guild_only()
    async def durdur(self, ctx):
        """Müziği duraklat"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        vc = ctx.guild.voice_client
        if not vc.is_playing():
            return await ctx.send("Şu an çalan bir şey yok.")
        self.oynatici(ctx.guild).duraklat()
        await ctx.send("⏸️ Duraklatıldı. Devam için `devam`.")

    @commands.hybrid_command(name="devam", aliases=["resume", "surdur"])
    @commands.guild_only()
    async def devam(self, ctx):
        """Duraklatılan müziği devam ettir"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        vc = ctx.guild.voice_client
        if not vc.is_paused():
            return await ctx.send("Duraklatılmış bir şey yok.")
        self.oynatici(ctx.guild).devam_et()
        await ctx.send("▶️ Devam ediyor.")

    @commands.hybrid_command(name="gec", aliases=["geç", "skip", "s"])
    @commands.guild_only()
    async def gec(self, ctx):
        """Şarkıyı geç"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        if self.oynatici(ctx.guild).gec():
            await ctx.send("⏭️ Geçildi.")
        else:
            await ctx.send("Şu an çalan bir şey yok.")

    @commands.hybrid_command(name="dur", aliases=["stop", "ayril", "ayrıl", "leave"])
    @commands.guild_only()
    async def dur(self, ctx):
        """Müziği bitir, kuyruğu temizle ve kanaldan çık"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        await ctx.send("⏹️ Müzik durduruldu, kanaldan ayrılıyorum.")
        await self.oynatici(ctx.guild).hepsini_durdur()

    @commands.hybrid_command(name="kuyruk", aliases=["queue", "q"], usage="[sayfa]")
    @app_commands.describe(sayfa="Sayfa numarası")
    @commands.guild_only()
    async def kuyruk(self, ctx, sayfa: int = 1):
        """Sıradaki şarkıları göster"""
        o = self.oynaticilar.get(ctx.guild.id)
        if o is None or (o.simdi is None and not o.kuyruk):
            return await ctx.send("📭 Kuyruk boş. `cal <şarkı>` ile ekle.")
        liste = list(o.kuyruk)
        sayfa_sayisi = max(1, -(-len(liste) // 10))
        sayfa = max(1, min(sayfa, sayfa_sayisi))
        parca = liste[(sayfa - 1) * 10: sayfa * 10]
        satirlar = []
        if o.simdi:
            satirlar.append(f"▶️ **{discord.utils.escape_markdown(o.simdi.baslik)[:80]}** `{sure_str(o.simdi.sure)}`\n")
        for i, s in enumerate(parca, (sayfa - 1) * 10 + 1):
            satirlar.append(f"`{i}.` {discord.utils.escape_markdown(s.baslik)[:80]} `{sure_str(s.sure)}`")
        if not parca:
            satirlar.append("Sırada başka şarkı yok.")
        e = discord.Embed(title="📜 Müzik kuyruğu", description="\n".join(satirlar)[:4000], color=discord.Color.blurple())
        e.set_footer(text=f"Sayfa {sayfa}/{sayfa_sayisi} • Döngü: {DONGU_ADI[o.dongu]}")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="simdi", aliases=["np", "calan", "çalan"])
    @commands.guild_only()
    async def simdi(self, ctx):
        """Çalan şarkıyı göster"""
        o = self.oynaticilar.get(ctx.guild.id)
        vc = ctx.guild.voice_client
        if o is None or o.simdi is None or vc is None:
            return await ctx.send("Şu an çalan bir şey yok.")
        e = o.np_embed(o.simdi)
        e.add_field(
            name="İlerleme",
            value=f"{ilerleme(o.gecen(), o.simdi.sure)}\n`{sure_str(o.gecen())} / {sure_str(o.simdi.sure)}`"
                  + ("  ⏸️" if vc.is_paused() else ""),
            inline=False)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="ses", aliases=["volume", "vol"], usage="[1-100]")
    @app_commands.describe(deger="Ses seviyesi (1-100), boşsa mevcut seviye gösterilir")
    @commands.guild_only()
    async def ses(self, ctx, deger: int = None):
        """Ses seviyesini ayarla"""
        o = self.oynatici(ctx.guild)
        if deger is None:
            return await ctx.send(f"🔊 Ses seviyesi: **%{int(o.ses * 100)}**")
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        if not 1 <= deger <= 100:
            return await ctx.send("❌ Ses 1 ile 100 arasında olmalı.")
        o.ses_ayarla(deger)
        await ctx.send(f"🔊 Ses seviyesi **%{deger}** yapıldı.")

    @commands.hybrid_command(name="dongu", aliases=["döngü", "loop"], usage="[kapali/sarki/kuyruk]")
    @app_commands.describe(mod="Döngü modu (boşsa sıradaki moda geçer)")
    @app_commands.choices(mod=[
        app_commands.Choice(name="Kapalı", value="kapali"),
        app_commands.Choice(name="Şarkı", value="sarki"),
        app_commands.Choice(name="Kuyruk", value="kuyruk"),
    ])
    @commands.guild_only()
    async def dongu(self, ctx, mod: str = None):
        """Döngü modunu ayarla"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        o = self.oynatici(ctx.guild)
        takma = {"kapali": "kapali", "kapalı": "kapali", "kapat": "kapali", "off": "kapali",
                 "sarki": "sarki", "şarkı": "sarki", "tek": "sarki", "song": "sarki",
                 "kuyruk": "kuyruk", "hepsi": "kuyruk", "queue": "kuyruk", "all": "kuyruk"}
        if mod is None:
            sira = ["kapali", "sarki", "kuyruk"]
            o.dongu = sira[(sira.index(o.dongu) + 1) % 3]
        elif mod.lower() in takma:
            o.dongu = takma[mod.lower()]
        else:
            return await ctx.send("❌ Mod: `kapali`, `sarki` ya da `kuyruk`")
        await ctx.send(f"🔁 Döngü: **{DONGU_ADI[o.dongu]}**")

    @commands.hybrid_command(name="karistir", with_app_command=False, aliases=["karıştır", "shuffle"])
    @commands.guild_only()
    async def karistir(self, ctx):
        """Kuyruğu karıştır"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        o = self.oynatici(ctx.guild)
        if len(o.kuyruk) < 2:
            return await ctx.send("Karıştırmak için kuyrukta en az 2 şarkı olmalı.")
        liste = list(o.kuyruk)
        random.shuffle(liste)
        o.kuyruk = deque(liste)
        await ctx.send(f"🔀 Kuyruk karıştırıldı ({len(liste)} şarkı).")

    @commands.hybrid_command(name="kuyrukcikar", with_app_command=False, aliases=["kuyrukçıkar", "remove"], usage="<sıra>")
    @commands.guild_only()
    async def kuyrukcikar(self, ctx, sira: int):
        """Kuyruktan şarkı çıkar"""
        hata = self.ayni_kanal_hata(ctx)
        if hata:
            return await ctx.send(hata)
        o = self.oynatici(ctx.guild)
        if not 1 <= sira <= len(o.kuyruk):
            return await ctx.send("❌ Geçersiz sıra. Numaralara `kuyruk` ile bak.")
        liste = list(o.kuyruk)
        s = liste.pop(sira - 1)
        o.kuyruk = deque(liste)
        await ctx.send(f"🗑️ Çıkarıldı: **{discord.utils.escape_markdown(s.baslik)}**")

    # ---- Müzik olayları: kanalda kimse kalmazsa / bot atılırsa ----
    @commands.Cog.listener()
    async def on_voice_state_update(self, uye, before, after):
        guild = uye.guild
        if self.bot.user is not None and uye.id == self.bot.user.id and after.channel is None:
            o = self.oynaticilar.pop(guild.id, None)
            if o is not None:
                o.kuyruk.clear()
                await o.temizle()
            return
        vc = guild.voice_client
        if vc is None or uye.bot:
            return
        if before.channel == vc.channel and after.channel != vc.channel:
            if any(not m.bot for m in vc.channel.members):
                return
            await asyncio.sleep(YALNIZ_SN)
            vc = guild.voice_client
            if vc is not None and vc.is_connected() and not any(not m.bot for m in vc.channel.members):
                o = self.oynaticilar.get(guild.id)
                if o is not None:
                    await o.yaz("👋 Kanalda kimse kalmadığı için ayrıldım.")
                try:
                    await vc.disconnect()
                except Exception:
                    pass

    # ================= ✉️ DM =================
    @commands.hybrid_command(name="dm", usage="@kişi <mesaj>")
    @app_commands.describe(uye="Mesaj gönderilecek kişi", mesaj="Gönderilecek mesaj")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def dm(self, ctx, uye: discord.Member, *, mesaj: str):
        """Botla bir kişiye özelden mesaj gönder"""
        if uye.bot:
            return await ctx.send("🤖 Botlara DM atamam.", ephemeral=True)
        if uye.id in veri["dm_kapali"]:
            return await ctx.send("🔕 Bu kişi DM almayı kapatmış.", ephemeral=True)
        e = discord.Embed(description=mesaj[:3800], color=discord.Color.blurple())
        e.set_author(name=f"{ctx.guild.name} sunucusundan mesaj",
                     icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        e.set_footer(text=f"Gönderen yetkili: {ctx.author} • DM almak istemiyorsan sunucuda td!dmkapat yaz")
        try:
            await uye.send(embed=e)
        except discord.Forbidden:
            return await ctx.send("❌ Mesaj gönderilemedi, kişinin DM'leri kapalı.", ephemeral=True)
        except discord.HTTPException:
            return await ctx.send("❌ Mesaj gönderilemedi.", ephemeral=True)
        await ctx.send(f"✅ **{uye.display_name}** kişisine özelden mesaj gönderildi.", ephemeral=True,
                       allowed_mentions=NO_PING)

    @commands.hybrid_command(name="dmduyuru", aliases=["dmtoplu"], usage="@rol <mesaj>")
    @app_commands.describe(rol="Duyurunun gideceği rol", mesaj="Duyuru metni")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @commands.cooldown(1, 600, commands.BucketType.guild)
    async def dmduyuru(self, ctx, rol: discord.Role, *, mesaj: str):
        """Roldeki herkese özelden duyuru gönder"""
        if rol.is_default():
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("❌ `@everyone` kullanılamaz, belirli bir rol seç.")
        hedef = [m for m in rol.members
                 if not m.bot and m.id not in veri["dm_kapali"] and m.id != ctx.author.id]
        if not hedef:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("❌ Bu rolde mesaj gönderilebilecek kimse yok.")
        if len(hedef) > DM_TOPLU_MAX:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(f"❌ Tek seferde en fazla **{DM_TOPLU_MAX}** kişiye gönderilir (bu rolde {len(hedef)} kişi var). "
                                  "Discord toplu DM'i spam sayabilir, daha küçük bir rol seç.")

        e = discord.Embed(description=mesaj[:3800], color=discord.Color.orange())
        e.set_author(name=f"{ctx.guild.name} duyurusu",
                     icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        e.set_footer(text="DM almak istemiyorsan sunucuda td!dmkapat yaz")

        view = Onay(ctx.author.id)
        onay_mesaji = await ctx.send(
            f"📨 **{rol.name}** rolündeki **{len(hedef)}** kişiye özelden gönderilecek. Önizleme:",
            embed=e, view=view, allowed_mentions=NO_PING)
        await view.wait()
        if not view.sonuc:
            ctx.command.reset_cooldown(ctx)
            try:
                await onay_mesaji.edit(content="❎ İptal edildi ya da süre doldu.", embed=None, view=None)
            except discord.HTTPException:
                pass
            return

        gorev = asyncio.create_task(self._toplu_dm(ctx, onay_mesaji, hedef, e))
        ARKA.add(gorev)
        gorev.add_done_callback(ARKA.discard)

    async def _toplu_dm(self, ctx, onay_mesaji, hedef, embed):
        basarili = hatali = 0
        for m in hedef:
            try:
                await m.send(embed=embed)
                basarili += 1
            except discord.HTTPException:
                hatali += 1
            await asyncio.sleep(DM_ARALIK)
        sonuc = f"✅ Duyuru bitti: **{basarili}** kişiye gitti, **{hatali}** kişiye gönderilemedi (DM kapalı)."
        try:
            await onay_mesaji.edit(content=sonuc)
        except discord.HTTPException:
            await ctx.channel.send(sonuc)

    @commands.hybrid_command(name="dmkapat", aliases=["dmoff"])
    @commands.guild_only()
    async def dmkapat(self, ctx):
        """Bottan DM almayı kapat"""
        if ctx.author.id not in veri["dm_kapali"]:
            veri["dm_kapali"].append(ctx.author.id)
            veri_kaydet()
        await ctx.send("🔕 Artık bottan DM almayacaksın. Tekrar açmak için `dmac`.", ephemeral=True)

    @commands.hybrid_command(name="dmac", aliases=["dmon", "dmaç"])
    @commands.guild_only()
    async def dmac(self, ctx):
        """Bottan DM almayı tekrar aç"""
        if ctx.author.id in veri["dm_kapali"]:
            veri["dm_kapali"].remove(ctx.author.id)
            veri_kaydet()
        await ctx.send("🔔 Bottan DM almayı tekrar açtın.", ephemeral=True)

    # ================= 🧩 5 yeni komut =================
    @commands.hybrid_command(name="banner", usage="[@kişi]")
    @app_commands.describe(uye="Kimin bannerına bakılacak (boşsa sen)")
    @commands.guild_only()
    async def banner(self, ctx, uye: discord.Member = None):
        """Profil banner'ını göster"""
        uye = uye or ctx.author
        try:
            kullanici = await self.bot.fetch_user(uye.id)
        except discord.HTTPException:
            return await ctx.send("❌ Banner alınamadı.")
        if kullanici.banner is None:
            return await ctx.send(f"🖼️ **{uye.display_name}** kişisinin banner'ı yok.", allowed_mentions=NO_PING)
        e = discord.Embed(title=f"🖼️ {uye.display_name} banner'ı", color=kullanici.accent_color or discord.Color.blurple())
        e.set_image(url=kullanici.banner.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="emojibuyut", with_app_command=False, aliases=["emoji", "buyut"], usage="<emoji>")
    @commands.guild_only()
    async def emojibuyut(self, ctx, emoji: str):
        """Özel (sunucu) emojisini büyüt"""
        m = re.search(r"<(a?):(\w+):(\d+)>", emoji)
        if not m:
            return await ctx.send("❌ Bir sunucu emojisi gir. (Standart emojiler desteklenmiyor.)")
        animasyonlu, ad, eid = m.group(1) == "a", m.group(2), m.group(3)
        url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animasyonlu else 'png'}?size=256"
        e = discord.Embed(title=f":{ad}:", color=discord.Color.blurple())
        e.set_image(url=url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="askolcer", with_app_command=False, aliases=["aşkölçer", "ask", "love"], usage="@kişi")
    @commands.guild_only()
    async def askolcer(self, ctx, uye: discord.Member):
        """İki kişi arasındaki aşkı ölç 💘"""
        a, b = sorted([ctx.author.id, uye.id])
        yuzde = int(hashlib.md5(f"{a}-{b}".encode()).hexdigest(), 16) % 101
        dolu = yuzde // 10
        cubuk = "❤️" * dolu + "🖤" * (10 - dolu)
        if yuzde >= 90:
            yorum = "Ruh eşi! 💍"
        elif yuzde >= 70:
            yorum = "Çok tatlı bir çift olursunuz 😍"
        elif yuzde >= 50:
            yorum = "Fena değil, şans verin 😉"
        elif yuzde >= 25:
            yorum = "Biraz çaba lazım 😅"
        else:
            yorum = "Arkadaş kalın bence 😬"
        e = discord.Embed(
            title="💘 Aşk Ölçer",
            description=f"{ctx.author.mention} ❤️ {uye.mention}\n\n{cubuk}\n**%{yuzde}** — {yorum}",
            color=discord.Color.from_rgb(255, 105, 180))
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="tersyaz", with_app_command=False, aliases=["ters", "reverse"], usage="<metin>")
    async def tersyaz(self, ctx, *, metin: str):
        """Yazıyı tersten yaz"""
        if len(metin) > 1000:
            return await ctx.send("❌ En fazla 1000 karakter.")
        await ctx.send(f"🔄 {metin[::-1]}", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="kanalbilgi", with_app_command=False, aliases=["channelinfo", "kanal"], usage="[#kanal]")
    @commands.guild_only()
    async def kanalbilgi(self, ctx, kanal: Union[discord.TextChannel, discord.VoiceChannel] = None):
        """Kanal bilgisini göster"""
        kanal = kanal or ctx.channel
        tur = "🔊 Ses" if isinstance(kanal, discord.VoiceChannel) else "💬 Metin"
        e = discord.Embed(title=f"{tur} kanalı: {kanal.name}", color=discord.Color.blurple())
        e.add_field(name="ID", value=f"`{kanal.id}`", inline=True)
        e.add_field(name="Kategori", value=kanal.category.name if kanal.category else "Yok", inline=True)
        e.add_field(name="Oluşturulma", value=discord.utils.format_dt(kanal.created_at, "R"), inline=True)
        if isinstance(kanal, discord.TextChannel):
            e.add_field(name="Yavaş mod", value=f"{kanal.slowmode_delay} sn" if kanal.slowmode_delay else "Kapalı", inline=True)
            e.add_field(name="NSFW", value="Evet" if kanal.is_nsfw() else "Hayır", inline=True)
            if kanal.topic:
                e.add_field(name="Konu", value=kanal.topic[:500], inline=False)
        else:
            e.add_field(name="Kişi sınırı", value=str(kanal.user_limit) if kanal.user_limit else "Sınırsız", inline=True)
            e.add_field(name="Bitrate", value=f"{kanal.bitrate // 1000} kbps", inline=True)
            e.add_field(name="Şu an içeride", value=str(len(kanal.members)), inline=True)
        await ctx.send(embed=e)


# ----------------------------------------------------------------------
# Yükleme (main.py setup_hook içinden çağrılır)
# ----------------------------------------------------------------------
async def kur(bot, g):
    veri_yukle()
    opus_hazirla()
    hata = muzik_hata()
    if hata:
        print(f"Müzik sistemi uyarısı: {hata}")
    g["EK_KATEGORILER"].update(YARDIM)
    await bot.add_cog(V151(bot))
