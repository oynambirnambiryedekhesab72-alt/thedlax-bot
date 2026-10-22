# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.0 - Hızlı yapay zeka ve eğitim modülü

main.py bunu v20.py'den sonra otomatik yükler. Bu dosya yoksa bot eski yavaş yöntemle çalışmaya devam eder.
main.py'deki API anahtarına ve istek koduna dokunmaz; sadece `ai_cevapla` fonksiyonunun yerine geçer.

Neden hızlı?
  1) Bağlantı her soruda yeniden kurulmuyor (kalıcı aiohttp oturumu).
  2) Modelin "uzun düşünmesi" kapatılıyor (thinking: minimal), kısa sohbet için bu çok süre kazandırır.
  3) İlk model 5 saniyede cevap vermezse yedek model aynı anda başlıyor (sırayla beklemek yok).
  4) Aynı soru tekrar sorulursa cevap önbellekten geliyor.
  5) Senin öğrettiğin soru-cevaplar yapay zekaya gitmeden ANINDA cevaplanıyor.

Eğitim (Sunucuyu Yönet yetkisi gerekir):
  td!ogret merhaba | Selam {isim}, hoş geldin!   -> hazır cevap (anında, API kullanmaz)
  td!ogret Sunucu kuralı: küfür yasak             -> bilgi (yapay zeka cevap verirken bunu bilir)
  td!ogretilenler  •  td!aisil S3 / B2  •  td!aitest (hız testi)
Veriler veri_ai.json dosyasında tutulur.
"""
import os
import re
import json
import time
import asyncio
import difflib

import aiohttp
import discord
from discord.ext import commands
from v15 import NO_PING

DOSYA = "veri_ai.json"

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
AI_ISTEK_SURE = 15        # tek bir istek en fazla kaç saniye beklesin
AI_YEDEK_BEKLEME = 5      # ilk model bu kadar sürede cevap vermezse yedek model de başlar
AI_MAX_TOKEN = 300        # cevap uzunluk sınırı (sistem zaten kısa cevap istiyor)
AI_ONBELLEK_SURE = 600    # aynı soru kaç saniye önbellekte kalsın
AI_ONBELLEK_MAX = 300
ESLESME = 0.82            # öğretilen soruya ne kadar benzerse anında cevap verilsin (0-1)
MAX_SORU = 200            # sunucu başına en fazla soru-cevap
MAX_BILGI = 40            # sunucu başına en fazla bilgi

veri = {"sunucu": {}}

_TR = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc")


def norm(t):
    """Küçük harf, Türkçe karakter ve noktalama farkı olmadan karşılaştırma için."""
    t = t.translate(_TR).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def yukle():
    try:
        with open(DOSYA, "r", encoding="utf-8") as f:
            v = json.load(f)
        if isinstance(v.get("sunucu"), dict):
            veri["sunucu"] = v["sunucu"]
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"v20_ai verisi okunamadı: {e!r}")


def kaydet():
    gecici = DOSYA + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        os.replace(gecici, DOSYA)
    except Exception as e:
        print(f"v20_ai verisi kaydedilemedi: {e!r}")


def sunucu(gid):
    return veri["sunucu"].setdefault(str(gid), {"sorular": [], "bilgiler": [], "sayac": 0})


def ogretilen_cevap(gid, soru):
    """Öğretilmiş bir soruya yeterince benziyorsa cevabı döner, yoksa None."""
    n = norm(soru)
    if not n:
        return None
    en_iyi, en_oran = None, 0.0
    for k in sunucu(gid)["sorular"]:
        kn = k.get("n") or norm(k["s"])
        oran = 1.0 if kn == n else difflib.SequenceMatcher(None, n, kn).ratio()
        if oran > en_oran:
            en_iyi, en_oran = k, oran
    return en_iyi["c"] if en_iyi is not None and en_oran >= ESLESME else None


def baglam(gid, soru):
    """Yapay zekanın sistem mesajına eklenecek öğretilmiş bilgiler."""
    d = sunucu(gid)
    metin = ""
    if d["bilgiler"]:
        metin += "\nSana öğretilen bilgiler (ilgili olduğunda bunlara göre cevap ver):\n"
        metin += "\n".join(f"- {b['t']}" for b in d["bilgiler"][-MAX_BILGI:])
    kelimeler = {w for w in norm(soru).split() if len(w) > 2}
    if kelimeler and d["sorular"]:
        ilgili = []
        for k in d["sorular"]:
            ortak = len(kelimeler & set((k.get("n") or norm(k["s"])).split()))
            if ortak:
                ilgili.append((ortak, k))
        ilgili.sort(key=lambda x: -x[0])
        if ilgili:
            metin += "\nÖğretilmiş örnek cevaplar (tarzını ve içeriğini kullan):\n"
            metin += "\n".join(f"Soru: {k['s']} -> Cevap: {k['c']}" for _, k in ilgili[:5])
    return metin


YARDIM = {
    "🧠 Yapay Zeka Eğitimi (v2.0)": [
        "`ogret <soru> | <cevap>` hazır cevap öğret, anında cevaplanır. `{isim}` yazarsan kişinin adı gelir (Sunucuyu Yönet)",
        "`ogret <bilgi>` bilgi öğret (`|` koymazsan), yapay zeka cevap verirken bunu bilir (Sunucuyu Yönet)",
        "`ogretilenler [sayfa]` öğretilenleri listele  •  `aisil S3` ya da `aisil B2` sil",
        "`aitest` yapay zeka hız testi (Sunucuyu Yönet)",
    ],
}


class HizliAI(commands.Cog):
    def __init__(self, bot, g):
        self.bot = bot
        self.g = g
        self.session = None
        self.dusunme_yok = set()      # "thinking" ayarını kabul etmeyen modeller
        self.onbellek = {}

    async def cog_unload(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()

    def oturum(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=AI_ISTEK_SURE),
                connector=aiohttp.TCPConnector(keepalive_timeout=300),
            )
        return self.session

    # ================= Gemini isteği =================
    async def tek_model(self, model, contents, sistem):
        """Tek bir modele sorar. (cevap, hata) döner, asla hata fırlatmaz."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        basliklar = {"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": self.g["GEMINI_KEY"]}
        denemeler = [False] if model in self.dusunme_yok else [True, False]
        son = "bilinmiyor"
        for dusunme in denemeler:
            cfg = {"maxOutputTokens": AI_MAX_TOKEN}
            if dusunme:
                cfg["thinkingConfig"] = {"thinkingLevel": "minimal"}
            payload = {
                "systemInstruction": {"parts": [{"text": sistem}]},
                "contents": contents,
                "generationConfig": cfg,
            }
            try:
                async with self.oturum().post(
                        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=basliklar) as r:
                    govde = await r.text()
                    if r.status == 200:
                        sonuc = json.loads(govde)
                        adaylar = sonuc.get("candidates") or []
                        parcalar = (adaylar[0].get("content", {}).get("parts") or []) if adaylar else []
                        metin = "".join(p.get("text", "") for p in parcalar).strip()
                        if metin:
                            return metin, ""
                        son = "bos"
                        continue
                    if r.status == 400 and dusunme:      # model thinking ayarını sevmedi, bir daha deneme
                        self.dusunme_yok.add(model)
                        continue
                    print(f"Gemini hatası ({model}) HTTP {r.status}: {govde[:300]}")
                    return None, f"HTTP {r.status}"
            except asyncio.TimeoutError:
                return None, "zaman aşımı"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Gemini hatası ({model}): {e!r}")
                son = type(e).__name__
                break
        return None, son

    async def hizli_istek(self, contents, sistem):
        """İlk model yavaşsa ya da hata verirse yedek modeli beklemeden başlatır."""
        modeller = list(self.g.get("AI_MODELLER") or [])
        if not modeller:
            return None, "model yok"
        beklenen = {asyncio.create_task(self.tek_model(modeller[0], contents, sistem))}
        sira = 1
        son_hata = "bilinmiyor"
        try:
            while beklenen:
                zaman = AI_YEDEK_BEKLEME if sira < len(modeller) else None
                bitenler, beklenen = await asyncio.wait(beklenen, timeout=zaman, return_when=asyncio.FIRST_COMPLETED)
                for t in bitenler:
                    cevap, hata = t.result()
                    if cevap:
                        return cevap, ""
                    son_hata = hata
                if (not bitenler or not beklenen) and sira < len(modeller):
                    beklenen.add(asyncio.create_task(self.tek_model(modeller[sira], contents, sistem)))
                    sira += 1
            return None, son_hata
        finally:
            for t in beklenen:
                t.cancel()

    # ================= main.py'deki ai_cevapla'nın yerine geçer =================
    async def ai_cevapla(self, kullanici, kanal_id, soru):
        """Her zaman gönderilecek bir metin döner (cevap ya da hata mesajı)."""
        g = self.g
        simdi = time.time()
        son_soru, gecmis = g["ai_son_soru"], g["ai_gecmis"]
        kalan = g["AI_BEKLEME"] - (simdi - son_soru.get(kullanici.id, 0))
        if kalan > 0:
            return f"⏳ Biraz yavaş, {int(kalan) + 1} saniye sonra tekrar sor."
        son_soru[kullanici.id] = simdi

        soru = soru.strip()[:1500]
        gid = getattr(getattr(kullanici, "guild", None), "id", 0)
        ad = kullanici.display_name

        hazir = ogretilen_cevap(gid, soru)             # senin öğrettiğin cevap: API'ye gitmeden anında
        if hazir:
            return hazir.replace("{isim}", ad)

        anahtar = (kanal_id, kullanici.id)
        kayit = gecmis.get(anahtar)
        if kayit and simdi - kayit["son"] > g["AI_HAFIZA_SURE"]:
            kayit = None
        mesajlar = list(kayit["mesajlar"]) if kayit else []

        onb = (gid, norm(soru)) if not mesajlar else None   # sadece sohbetin ilk sorusu önbelleğe girer
        cevap, hata = None, ""
        if onb:
            hit = self.onbellek.get(onb)
            if hit and simdi - hit[0] < AI_ONBELLEK_SURE:
                cevap = hit[1]

        mesajlar.append(("user", soru))
        if not cevap:
            contents = [{"role": r, "parts": [{"text": t}]} for r, t in mesajlar]
            sistem = g["SISTEM"] + f" Şu an konuştuğun kişinin adı: {ad}." + baglam(gid, soru)
            cevap, hata = await self.hizli_istek(contents, sistem)
            if cevap and onb and ad.lower() not in cevap.lower():
                if len(self.onbellek) >= AI_ONBELLEK_MAX:
                    self.onbellek.pop(next(iter(self.onbellek)))
                self.onbellek[onb] = (simdi, cevap)

        if cevap:
            mesajlar.append(("model", cevap))
            mesajlar = mesajlar[-g["AI_HAFIZA_MAX"]:]
            while mesajlar and mesajlar[0][0] != "user":
                mesajlar.pop(0)
            gecmis[anahtar] = {"mesajlar": mesajlar, "son": simdi}
            return cevap
        if hata == "HTTP 429":
            return "⏳ Şu an çok fazla istek var, biraz sonra tekrar dene."
        if hata == "bos":
            return "🤐 Buna cevap veremedim, başka türlü sor."
        return f"😵 Şu an cevap veremiyorum. ({hata})"

    # ================= 🧠 Eğitim komutları =================
    @commands.hybrid_command(name="ogret", aliases=["öğret", "aiegit"], with_app_command=False,
                             usage="<soru> | <cevap>   ya da   <bilgi>")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def ogret(self, ctx, *, metin: str):
        """Yapay zekaya hazır cevap ya da bilgi öğret"""
        d = sunucu(ctx.guild.id)
        if "|" in metin:
            soru, cevap = (x.strip() for x in metin.split("|", 1))
            if len(soru) < 2 or not cevap:
                return await ctx.send("❌ Şöyle yaz: `td!ogret merhaba | Selam {isim}!`")
            if len(soru) > 150 or len(cevap) > 500:
                return await ctx.send("❌ Soru en fazla 150, cevap en fazla 500 karakter olabilir.")
            n = norm(soru)
            for k in d["sorular"]:
                if (k.get("n") or norm(k["s"])) == n:
                    k["c"] = cevap
                    kaydet()
                    return await ctx.send(f"♻️ **S{k['id']}** güncellendi.")
            if len(d["sorular"]) >= MAX_SORU:
                return await ctx.send(f"❌ En fazla {MAX_SORU} soru-cevap öğretilebilir, eskilerini `td!aisil` ile sil.")
            d["sayac"] += 1
            d["sorular"].append({"id": d["sayac"], "s": soru, "c": cevap, "n": n})
            kaydet()
            return await ctx.send(f"✅ Öğrendim! **S{d['sayac']}**: biri bunu sorarsa anında cevaplarım.")
        bilgi = metin.strip()
        if len(bilgi) < 5 or len(bilgi) > 300:
            return await ctx.send("❌ Bilgi 5 ile 300 karakter arasında olmalı.")
        if len(d["bilgiler"]) >= MAX_BILGI:
            return await ctx.send(f"❌ En fazla {MAX_BILGI} bilgi öğretilebilir, eskilerini `td!aisil` ile sil.")
        d["sayac"] += 1
        d["bilgiler"].append({"id": d["sayac"], "t": bilgi})
        kaydet()
        await ctx.send(f"✅ Öğrendim! **B{d['sayac']}**: artık cevap verirken bunu da bilirim.")

    @commands.hybrid_command(name="ogretilenler", aliases=["öğretilenler", "aibilgiler"], with_app_command=False,
                             usage="[sayfa]")
    @commands.guild_only()
    async def ogretilenler(self, ctx, sayfa: int = 1):
        """Yapay zekaya öğretilenleri listele"""
        d = sunucu(ctx.guild.id)
        satirlar = [f"**S{k['id']}** {k['s'][:60]} → {k['c'][:80]}" for k in d["sorular"]]
        satirlar += [f"**B{b['id']}** {b['t'][:120]}" for b in d["bilgiler"]]
        if not satirlar:
            return await ctx.send("📭 Henüz bir şey öğretilmedi. Başlamak için: `td!ogret merhaba | Selam {isim}!`")
        toplam = (len(satirlar) + 9) // 10
        sayfa = max(1, min(sayfa, toplam))
        await ctx.send(
            f"🧠 **Öğretilenler** (S = soru-cevap, B = bilgi) • sayfa {sayfa}/{toplam}\n"
            + "\n".join(satirlar[(sayfa - 1) * 10:sayfa * 10]), allowed_mentions=NO_PING)

    @commands.hybrid_command(name="aisil", with_app_command=False, usage="<S3 ya da B2>")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def aisil(self, ctx, kod: str):
        """Öğretilen bir soru-cevabı ya da bilgiyi sil (örnek: S3, B2)"""
        m = re.fullmatch(r"([SB])(\d+)", kod.strip().upper())
        if not m:
            return await ctx.send("❌ `td!aisil S3` ya da `td!aisil B2` şeklinde yaz (`td!ogretilenler`'de kodlar var).")
        d = sunucu(ctx.guild.id)
        liste = d["sorular"] if m.group(1) == "S" else d["bilgiler"]
        for i, k in enumerate(liste):
            if k["id"] == int(m.group(2)):
                liste.pop(i)
                kaydet()
                return await ctx.send(f"🗑️ **{m.group(1)}{m.group(2)}** silindi.")
        await ctx.send("❌ Böyle bir kayıt yok.")

    @commands.hybrid_command(name="aitest", with_app_command=False)
    @commands.has_permissions(manage_guild=True)
    async def aitest(self, ctx):
        """Yapay zeka modellerinin hızını ölç"""
        satirlar = []
        async with ctx.typing():
            for model in list(self.g.get("AI_MODELLER") or []):
                t0 = time.perf_counter()
                cevap, hata = await self.tek_model(
                    model, [{"role": "user", "parts": [{"text": "Sadece 'tamam' de."}]}], "Kısa cevap ver.")
                ms = int((time.perf_counter() - t0) * 1000)
                satirlar.append(f"✅ `{model}`: **{ms} ms**" if cevap else f"❌ `{model}`: {hata} ({ms} ms)")
        await ctx.send("⚡ **Hız testi**\n" + "\n".join(satirlar or ["Hiç model tanımlı değil."]))


# ----------------------------------------------------------------------
# Yükleme (main.py setup_hook içinden çağrılır)
# ----------------------------------------------------------------------
async def kur(bot, g):
    yukle()
    cog = HizliAI(bot, g)
    await bot.add_cog(cog)
    g["ai_cevapla"] = cog.ai_cevapla          # main.py'deki `ai` komutu artık bunu kullanır
    g["EK_KATEGORILER"].update(YARDIM)
