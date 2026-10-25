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

Yetenekler:
  - 👁️ Görsel okur: `td!ai bu ne?` yazıp resim ekle (ya da bir resme cevap verip `td!ai` yaz). Yazıları da okur.
  - 🔎 Bilmediği ya da güncel şeyleri Google aramasıyla webde arar ve kaynak gösterir.
  - ✍️ Normalde kısa konuşur ama istersen (hikaye, ödev, açıklama...) 50 cümleyi aşan uzun cevap da yazar.
  - 💬 Komutsuz sohbet: biri "sa" yazarsa "as", "selam" yazarsa "selam sana" der. İstediğin kanallarda
    soruları (sonunda ? olan ya da "nasıl, neden, kim..." ile başlayan) kendiliğinden cevaplar. Ayar: td!sohbet

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
import random
import base64
import asyncio
import difflib
import copy

import aiohttp
from typing import Optional
import discord
from discord.ext import commands
from v15 import NO_PING

# Cevap verirken yazan kişiyi etiketle (yanıt olarak), başkalarını/rolleri/everyone'ı etiketleme
YANIT_PING = discord.AllowedMentions(replied_user=True, users=False, roles=False, everyone=False)

# ---- Komutsuz doğal dil: "ona resim çiz", "kanalı kilitle" ----
RE_CIZ = re.compile(r"\b(ciz|cizer misin|cizsene|cizebilir misin|resmini yap|resim yap|resmi yap|gorsel (yap|olustur|uret)|resmet)\b")
RE_KILIT_AC = re.compile(r"\b(kilidi(ni)? ac|kilit kaldir|kilidi kaldir|kanali ac|sohbeti ac|kilitten cikar)\b")
RE_KILIT = re.compile(r"\b(kilitle|kilitlesene|kilitler misin|kanali kapat|kanali kapatir misin|sohbeti kapat)\b")
CIZ_GEREKSIZ = {"ona", "bana", "bunu", "sunu", "onu", "icin", "bir", "lutfen", "hadi", "sen", "bot", "sana", "ya",
                "ciz", "cizer", "misin", "cizsene", "cizebilir", "yap", "resmini", "resim", "resmi", "gorsel",
                "olustur", "uret", "resmet", "bi", "de", "da", "bak", "su", "bu"}


# ---- Komutsuz doğal dil (v2.1): her komut için ----
# (regex, komut, ses kanalında olmak gerekir mi, en fazla kelime)
NIYET_TABLO = [
    (r"\b(sarkiyi gec|sonrakine gec|siradakine gec|sonraki sarki|bir sonraki sarki|atla|skip)\b", "gec", True, 6),
    (r"\b(muzigi durdur|sarkiyi durdur|muzigi duraklat|sarkiyi duraklat|duraklat)\b", "durdur", True, 6),
    (r"\b(muzige devam|sarkiya devam|devam ettir|muzigi devam ettir)\b", "devam", True, 6),
    (r"\b(muzigi kapat|muzigi bitir|muzigi sonlandir|sesten cik|ses kanalindan cik|botu cikar)\b", "dur", True, 6),
    (r"\b(kuyrugu karistir|sarkilari karistir)\b", "karistir", True, 6),
    (r"\b(kuyrugu goster|siradaki sarkilar|sirada ne var|kuyruk)\b", "kuyruk", True, 6),
    (r"\b(ne caliyor|hangi sarki caliyor|calan sarki|simdi ne caliyor)\b", "simdi", True, 6),
    (r"\b(bakiyem|param ne kadar|kac param var|kac liram var|bakiyemi goster|kasamda ne kadar)\b", "bakiye", False, 8),
    (r"\b(gunluk odul|gunlugumu al|gunluk para|gunluk al)\b", "gunluk", False, 6),
    (r"\b(en zenginler|zenginler listesi|zengin siralamasi)\b", "zenginler", False, 6),
    (r"\b(seviyem|kacinci seviyeyim|kac xpm|xp durumum)\b", "seviye", False, 6),
    (r"\b(liderlik tablosu|xp siralamasi|en cok xp)\b", "siralama", False, 6),
    (r"\b(vip durumum|vipim|vip bilgim)\b", "vip", False, 6),
    (r"\b(ping|gecikmen kac|ping kac)\b", "ping", False, 4),
    (r"\b(ne kadar suredir acik|uptime)\b", "uptime", False, 6),
    (r"\b(sunucu bilgisi|sunucu bilgileri|sunucu hakkinda)\b", "serverinfo", False, 6),
    (r"\b(komutlar neler|komut listesi|komutlari goster|neler yapabilirsin|yardim menusu)\b", "help", False, 6),
    (r"\b(yazi mi tura mi|yazi tura|yazitura)\b", "yazitura", False, 6),
    (r"\b(avatar|avatari|avatarim|avatarimi|profil fotom|profil fotosu)\b", "avatar", False, 4),
    (r"\b(kullanici bilgisi|kullanici bilgileri|hesap bilgim)\b", "userinfo", False, 6),
    (r"\b(balik tut|balik avla|oltayi at|balik avina)\b", "balik", False, 5),
    (r"\b(madene git|maden kaz|madencilik yap|kazi yap)\b", "maden", False, 5),
    (r"\b(envanterim|cantam|esyalarim)\b", "envanter", False, 4),
    (r"\b(mesaiye git|mesai yap|maasimi al)\b", "mesai", False, 5),
    (r"\b(kartim|profil kartim|kartimi goster)\b", "kart", False, 4),
    (r"\b(dolar kac|euro kac|dolar ne kadar|euro ne kadar|doviz kurlari|doviz)\b", "doviz", False, 5),
    (r"\b(altin kac|altin ne kadar|gram altin|ceyrek altin)\b", "altin", False, 5),
    (r"\b(dogum gunlerini goster|yaklasan dogum gunleri)\b", "dogumgunleri", False, 5),
]
NIYET_TABLO = [(re.compile(r), k, v, m) for r, k, v, m in NIYET_TABLO]
CAL_GEREKSIZ = {"cal", "calsana", "calar", "misin", "calabilir", "calsin", "oynat", "bana", "bir", "lutfen", "hadi",
                "sarki", "sarkisini", "sarkiyi", "sarkisi", "muzik", "muzigi", "bot", "su", "bu", "ya", "bi", "de",
                "da", "ac", "acsana", "dinlemek", "istiyorum", "istiyom", "ver"}
RE_CAL = re.compile(r"\b(cal|calsana|calar misin|calabilir misin|calsin|oynat|muzik ac|sarki ac)\b")
RE_MENTION = re.compile(r"<@!?(\d+)>")
RE_HESAP = re.compile(r"^\s*([\d\s\.\,\+\-\*/x×÷\(\)\^]+?)\s*(kac eder|kactir|kac yapar|=|\?)\s*$", re.I)
RE_ZAR = re.compile(r"\bzar (at|atsana|atar misin)\b")
RE_AFK = re.compile(r"^(afkyim|afk giriyorum|afk oluyorum|ben afk)\b")
RE_SURE = re.compile(r"(\d+)\s*(dk|dakika|saat|sa|sn|saniye|gun|g)\b")
RE_MOD = [
    (re.compile(r"\b(banla|banlasana|yasakla|sunucudan yasakla)\b"), "ban"),
    (re.compile(r"\b(kickle|kicklesene|sunucudan at|sunucudan kov)\b"), "kick"),
    (re.compile(r"\b(susturmayi kaldir|susturmasini kaldir|susturmasini ac|unmute)\b"), "untimeout"),
    (re.compile(r"\b(sustur|susturur musun|timeoutla|timeout at)\b"), "timeout"),
    (re.compile(r"\b(uyar|uyarsana|uyari ver)\b"), "warn"),
]
RE_TEMIZLE = re.compile(r"\b(\d{1,3}) (mesaji|mesaj) (sil|temizle)\b")

def aktiflik_kanali_mi(mesaj):
    """Aktiflik kanalıysa bot sohbete her zaman katılır (soru olmasa da)."""
    try:
        import v18
        ayar = v18.veri["sunucu"].get(str(mesaj.guild.id), {}).get("aktiflik", {})
        return bool(ayar.get("kanal")) and ayar["kanal"] == mesaj.channel.id
    except Exception:
        return False


DOSYA = "veri_ai.json"

# ----------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------
AI_ISTEK_SURE = 60        # tek bir istek en fazla kaç saniye beklesin (uzun cevap/web araması için)
AI_YEDEK_BEKLEME = 12     # ilk model bu kadar sürede cevap vermezse yedek model de başlar
AI_MAX_TOKEN = 4000       # cevap uzunluk sınırı (50 cümle rahat sığar; kısa sorulara yine kısa cevap verir)
AI_ARAMA = True           # bilmediğinde Google aramasını kullansın mı
GORSEL_MAX = 3            # bir soruda en fazla kaç görsel
GORSEL_MAX_MB = 4         # görsel başına en fazla MB
GORSEL_TURLER = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}
KAYNAK_ONEK = "\n\n🔎 Webde aradım: "
AI_ONBELLEK_SURE = 600    # aynı soru kaç saniye önbellekte kalsın
AI_ONBELLEK_MAX = 300
ESLESME = 0.82            # öğretilen soruya ne kadar benzerse anında cevap verilsin (0-1)
MAX_SORU = 200            # sunucu başına en fazla soru-cevap
MAX_BILGI = 40            # sunucu başına en fazla bilgi

veri = {"sunucu": {}, "sohbet": {}}

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
        for anahtar in veri:
            if isinstance(v.get(anahtar), dict):
                veri[anahtar] = v[anahtar]
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


def sikistir(n):
    """'saaa' -> 'sa', 'selaaam' -> 'selam', 'heyyy' -> 'hey' (tekrarlanan harfleri azalt)."""
    n = re.sub(r"([aeiou])\1+", r"\1", n)
    return re.sub(r"([^aeiou\s])\1+", r"\1", n)


# Anahtarlar norm() biçiminde yazılır (küçük harf, Türkçe karakter yok). Biri bunlardan BİRİNİ TEK BAŞINA yazarsa cevap verilir.
SELAM_GRUPLARI = [
    ({"sa", "s a", "sea", "selamun aleykum", "selamunaleykum", "selamin aleykum"},
     ["as", "Aleyküm selam {isim}!", "Aleyküm selam, hoş geldin 👋", "as {isim}"]),
    ({"selam", "slm", "selamlar", "selam herkese", "selam millet", "selam arkadaslar"},
     ["Selam sana {isim}! 👋", "Selam sana!", "Selam {isim}, hoş geldin!"]),
    ({"merhaba", "mrb", "meraba", "merhabalar", "mrhaba", "hey", "hi", "hello"},
     ["Merhaba {isim}! 👋", "Merhaba, hoş geldin!", "Selam sana {isim}!"]),
    ({"naber", "nbr", "ne haber", "nasilsin", "nasilsiniz", "nasil gidiyor", "ne var ne yok"},
     ["İyidir, sen nasılsın {isim}?", "İyiyim sağ ol, sen nasılsın?", "Güzel gidiyor, sende ne var ne yok?"]),
    ({"gunaydin", "gunaydinlar"},
     ["Günaydın {isim}! ☀️", "Günaydın, günün güzel geçsin!"]),
    ({"iyi geceler", "iyi geceler herkese", "hayirli geceler", "tatli ruyalar"},
     ["İyi geceler {isim}, tatlı rüyalar 🌙", "İyi geceler! 🌙"]),
    ({"iyi aksamlar", "hayirli aksamlar"}, ["İyi akşamlar {isim}! 🌆"]),
    ({"iyi gunler", "hayirli gunler"}, ["İyi günler {isim}! 🌞"]),
    ({"gorusuruz", "gorusuruz herkese", "hoscakal", "hoscakalin", "gule gule", "bb", "bye", "kib"},
     ["Görüşürüz {isim}! 👋", "Hoşça kal {isim}!", "Kendine iyi bak! 👋"]),
    ({"geldim", "ben geldim"}, ["Hoş geldin {isim}! 🎉"]),
]
SELAM_HARITA = {sikistir(k): cevaplar for kume, cevaplar in SELAM_GRUPLARI for k in kume}

SORU_KELIMELERI = {"ne", "nedir", "neden", "niye", "nicin", "nasil", "kim", "kime", "kimin", "kimi", "kac", "kacta",
                   "nerede", "nereye", "nereden", "hangi", "hangisi", "ne zaman", "neresi", "kimdir"}
SELAM_KULLANICI_BEKLEME = 30   # aynı kişiye otomatik selam cevabı arası (saniye)
SELAM_KANAL_BEKLEME = 3        # aynı kanalda iki otomatik cevap arası
SORU_KANAL_BEKLEME = 8         # soru cevaplama kanalında iki cevap arası


def soru_mu(icerik, n):
    """Mesaj bir soruya benziyor mu? (sonu ?, soru kelimesiyle başlıyor ya da mi/mı ile bitiyor)"""
    if icerik.rstrip().endswith("?"):
        return True
    kelimeler = n.split()
    if not kelimeler:
        return False
    if kelimeler[0] in SORU_KELIMELERI:
        return True
    return len(kelimeler) >= 2 and kelimeler[-1] in ("mi", "mu")


def ogretilen_tam(gid, n):
    """Öğretilmiş sorulardan birine birebir (norm sonrası) eşitse cevabı döner."""
    for k in sunucu(gid)["sorular"]:
        if (k.get("n") or norm(k["s"])) == n:
            return k["c"]
    return None


def vip_bilgi(gid, uid):
    """(VIP mi, kademe simgesi). v20.py yoksa ya da DM ise (False, '')."""
    if not gid:
        return False, ""
    try:
        import v20
        if v20.vip_mi(gid, uid):
            return True, v20.KADEMELER[v20.kademe_al(gid, uid)]["emoji"]
    except Exception:
        pass
    return False, ""


STIL = (
    "Her zaman Türkçe konuş. Samimi, günlük dille konuş, robot gibi resmi olma. "
    "Normalde KISA cevap ver (1-3 cümle). Ama kullanıcı ayrıntı, açıklama, hikaye, makale, ödev, "
    "karşılaştırma ya da uzun bir şey isterse, ya da konu gerçekten uzun anlatım gerektiriyorsa "
    "istediğin kadar uzun (gerekirse 50 cümle) ve düzenli yaz; bu durumda kısa konuşma kuralı geçerli değil. "
    "Bilmediğin ya da güncel olabilecek (haber, skor, fiyat, tarih, yeni çıkan şey, kişi ve yer bilgisi) "
    "konularda emin değilsen web aramasını kullan, asla bilgi uydurma. "
    "Kullanıcı görsel gönderirse görseli dikkatle incele; yazı varsa oku, sorusuna göre anlat."
)


def sistem_metni(g):
    """main.py'deki kimlik bilgilerini koru, kısalık kuralını bu modülün kurallarıyla değiştir."""
    ana = g["SISTEM"]
    k = ana.find("Her zaman Türkçe konuş.")
    return (ana[:k] if k != -1 else ana) + STIL


def parcala(metin, sinir=1900, en_fazla=8):
    """Uzun cevabı Discord sınırına göre cümle/satır sonlarından böler."""
    parcalar = []
    while len(metin) > sinir and len(parcalar) < en_fazla - 1:
        kes = metin.rfind("\n", 0, sinir)
        if kes < sinir // 2:
            kes = metin.rfind(". ", 0, sinir) + 1
            if kes < sinir // 2:
                kes = metin.rfind(" ", 0, sinir)
                if kes < sinir // 2:
                    kes = sinir
        parcalar.append(metin[:kes].rstrip())
        metin = metin[kes:].lstrip()
    if metin.strip():
        parcalar.append(metin)
    return parcalar


YARDIM = {
    "🧠 Yapay Zeka Eğitimi (v2.0)": [
        "💡 Komutsuz: botu etiketle ya da mesajına yanıt ver → `ona resim çiz` (VIP), `kanalı kilitle` / `kilidi aç` (Kanalları Yönet yetkisi gerekir)",
        "`ai <soru>` sohbet: görsel okur (resim ekle ya da resme cevap ver), bilmediğini webde arar, istersen uzun yazar",
        "`sohbet [ac|kapat|herkes|dogal|kanal]` komutsuz sohbet: sa → as, selam → selam sana; `kanal` ile o kanalda sorulara da cevap verir (Sunucuyu Yönet)",
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
        self.kapali = {}              # {("dusunme"/"arama", model): bu zamana kadar kapalı}
        self.onbellek = {}
        self.selam_kullanici = {}
        self.selam_kanal = {}
        self.soru_kanal = {}
        self.niyet_kullanici = {}

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
    def aktif_mi(self, ozellik, model):
        return self.kapali.get((ozellik, model), 0) <= time.time()

    @staticmethod
    def cevap_cikar(govde):
        """Gemini cevabından metni ve (varsa) web kaynaklarını çıkarır."""
        sonuc = json.loads(govde)
        adaylar = sonuc.get("candidates") or []
        if not adaylar:
            return ""
        parcalar = (adaylar[0].get("content", {}).get("parts") or [])
        metin = "".join(p.get("text", "") for p in parcalar).strip()
        if not metin:
            return ""
        gm = adaylar[0].get("groundingMetadata") or {}
        kaynaklar, goruldu = [], set()
        for c in gm.get("groundingChunks") or []:
            w = c.get("web") or {}
            baslik = (w.get("title") or "kaynak").replace("[", "").replace("]", "")[:40]
            if w.get("uri") and baslik not in goruldu:
                goruldu.add(baslik)
                kaynaklar.append(f"[{baslik}](<{w['uri']}>)")
        if gm.get("webSearchQueries") and kaynaklar:
            metin += KAYNAK_ONEK + ", ".join(kaynaklar[:3])
        return metin

    def ogren(self, model, basarisiz, t, s):
        """Hata veren ayarı bir süre kapat, bir sonraki soruda boşuna deneme."""
        simdi = time.time()
        if not s and any(bs for _, bs in basarisiz):
            self.kapali[("arama", model)] = simdi + 900
        if not t and any(bt for bt, _ in basarisiz):
            self.kapali[("dusunme", model)] = simdi + 3600

    async def tek_model(self, model, contents, sistem, arama=True):
        """Tek bir modele sorar. (cevap, hata) döner, asla hata fırlatmaz.
        Önce hızlı ayarlarla (az düşünme + web araması) dener; model kabul etmezse sırayla kapatır."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        basliklar = {"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": self.g["GEMINI_KEY"]}
        denemeler = []
        for t, s in ((True, True), (False, True), (True, False), (False, False)):
            if t and not self.aktif_mi("dusunme", model):
                continue
            if s and (not arama or not self.aktif_mi("arama", model)):
                continue
            denemeler.append((t, s))
        basarisiz, son, arama_yasak = [], "bilinmiyor", False
        for t, s in denemeler:
            if s and arama_yasak:
                continue
            cfg = {"maxOutputTokens": AI_MAX_TOKEN}
            if t:
                cfg["thinkingConfig"] = {"thinkingLevel": "minimal"}
            payload = {"systemInstruction": {"parts": [{"text": sistem}]}, "contents": contents,
                       "generationConfig": cfg}
            if s:
                payload["tools"] = [{"google_search": {}}]
            try:
                async with self.oturum().post(
                        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=basliklar) as r:
                    govde = await r.text()
                    if r.status == 200:
                        metin = self.cevap_cikar(govde)
                        if metin:
                            self.ogren(model, basarisiz, t, s)
                            return metin, ""
                        son = "bos"
                        continue
                    if r.status in (400, 403, 429):
                        print(f"Gemini hatası ({model}, düşünme={t}, arama={s}) HTTP {r.status}: {govde[:200]}")
                        son = f"HTTP {r.status}"
                        if r.status == 429 and not s:
                            return None, son              # genel kota, başka ayar fayda etmez
                        if r.status in (403, 429):
                            arama_yasak = True            # arama kotası/izni yok: aramasız dene
                        basarisiz.append((t, s))
                        continue
                    print(f"Gemini hatası ({model}) HTTP {r.status}: {govde[:200]}")
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

    async def hizli_istek(self, contents, sistem, arama=True):
        """İlk model yavaşsa ya da hata verirse yedek modeli beklemeden başlatır."""
        modeller = list(self.g.get("AI_MODELLER") or [])
        if not modeller:
            return None, "model yok"
        beklenen = {asyncio.create_task(self.tek_model(modeller[0], contents, sistem, arama))}
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
                    beklenen.add(asyncio.create_task(self.tek_model(modeller[sira], contents, sistem, arama)))
                    sira += 1
            return None, son_hata
        finally:
            for t in beklenen:
                t.cancel()

    # ================= main.py'deki ai_cevapla'nın yerine geçer =================
    async def ai_cevapla(self, kullanici, kanal_id, soru, resimler=None, sessiz=False):
        """Her zaman gönderilecek bir metin döner (cevap ya da hata mesajı).
        resimler: [(mime_tipi, bayt), ...]. sessiz=True ise (kendiliğinden sohbet) hata/bekleme mesajı yerine None döner."""
        g = self.g
        resimler = resimler or []
        simdi = time.time()
        son_soru, gecmis = g["ai_son_soru"], g["ai_gecmis"]
        gid = getattr(getattr(kullanici, "guild", None), "id", 0)
        vip, _ = vip_bilgi(gid, kullanici.id)
        bekleme = min(g["AI_BEKLEME"], 1) if vip else g["AI_BEKLEME"]     # 👑 VIP'ler daha az bekler
        kalan = bekleme - (simdi - son_soru.get(kullanici.id, 0))
        if kalan > 0:
            return None if sessiz else f"⏳ Biraz yavaş, {int(kalan) + 1} saniye sonra tekrar sor."
        son_soru[kullanici.id] = simdi

        soru = soru.strip()[:1500]
        ad = kullanici.display_name

        if not resimler:
            hazir = ogretilen_cevap(gid, soru)         # senin öğrettiğin cevap: API'ye gitmeden anında
            if hazir:
                return hazir.replace("{isim}", ad)

        anahtar = (kanal_id, kullanici.id)
        kayit = gecmis.get(anahtar)
        if kayit and simdi - kayit["son"] > g["AI_HAFIZA_SURE"]:
            kayit = None
        mesajlar = list(kayit["mesajlar"]) if kayit else []

        onb = (gid, norm(soru)) if (not mesajlar and not resimler) else None   # sadece sohbetin ilk (görselsiz) sorusu
        cevap, hata = None, ""
        if onb:
            hit = self.onbellek.get(onb)
            if hit and simdi - hit[0] < AI_ONBELLEK_SURE:
                cevap = hit[1]

        mesajlar.append(("user", soru + (" [görsel gönderdi]" if resimler else "")))
        if not cevap:
            contents = [{"role": r, "parts": [{"text": t}]} for r, t in mesajlar]
            contents[-1]["parts"][0]["text"] = soru            # görsel işareti sadece hafıza içindi
            for mime, bayt in resimler:
                contents[-1]["parts"].append({"inline_data": {"mime_type": mime,
                                                              "data": base64.b64encode(bayt).decode()}})
            sistem = sistem_metni(g) + f" Şu an konuştuğun kişinin adı: {ad}." + baglam(gid, soru)
            cevap, hata = await self.hizli_istek(contents, sistem, AI_ARAMA)
            if cevap and onb and KAYNAK_ONEK not in cevap and ad.lower() not in cevap.lower():
                if len(self.onbellek) >= AI_ONBELLEK_MAX:
                    self.onbellek.pop(next(iter(self.onbellek)))
                self.onbellek[onb] = (simdi, cevap)

        if cevap:
            mesajlar.append(("model", cevap.split(KAYNAK_ONEK)[0]))   # kaynak linkleri hafızaya girmesin
            mesajlar = mesajlar[-g["AI_HAFIZA_MAX"]:]
            while mesajlar and mesajlar[0][0] != "user":
                mesajlar.pop(0)
            gecmis[anahtar] = {"mesajlar": mesajlar, "son": simdi}
            return cevap
        if sessiz:
            return None
        if hata == "HTTP 429":
            return "⏳ Şu an çok fazla istek var, biraz sonra tekrar dene."
        if hata == "bos":
            return "🤐 Buna cevap veremedim, başka türlü sor."
        return f"😵 Şu an cevap veremiyorum. ({hata})"

    # ================= 💬 Komutsuz sohbet (sa -> as, soru cevaplama) =================
    @staticmethod
    def sohbet_ayar(gid):
        return veri["sohbet"].setdefault(str(gid), {"acik": True, "kanallar": []})

    @staticmethod
    async def hala_var(mesaj):
        """Mesaj hâlâ duruyor mu? (otomod sildiyse ona cevap verme)"""
        try:
            await mesaj.channel.fetch_message(mesaj.id)
            return True
        except discord.NotFound:
            return False
        except discord.HTTPException:
            return True

    async def guvenli_cevap(self, mesaj, parcalar):
        if not await self.hala_var(mesaj):
            return
        if not mesaj.channel.permissions_for(mesaj.guild.me).send_messages:
            return
        for i, p in enumerate(parcalar):
            try:
                if i == 0:
                    await mesaj.reply(p, mention_author=True, allowed_mentions=YANIT_PING)
                else:
                    await mesaj.channel.send(p, allowed_mentions=NO_PING)
            except discord.HTTPException:
                return

    @commands.Cog.listener()
    async def on_message(self, mesaj):
        if mesaj.author.bot or mesaj.guild is None or not mesaj.content:
            return
        icerik = mesaj.content.strip()
        prefixler = tuple(self.g.get("PREFIXLER", ("td/", "td!")))
        if icerik.startswith(prefixler) or len(icerik) > 400 or mesaj.reference is not None:
            return                                   # komutlar ve yanıtlar (etiket/yanıt main.py'de) burada değil
        if self.bot.user in mesaj.mentions:
            return                                   # bota etiket: main.py halleder
        d = self.sohbet_ayar(mesaj.guild.id)
        n = norm(icerik)
        if not n:
            return
        simdi = time.time()
        gid, uid = mesaj.guild.id, mesaj.author.id

        # 1) Hazır selamlaşma ya da senin öğrettiğin birebir tetikleyici (API kullanmaz, anında)
        cevap = None
        if d["acik"]:
            if len(icerik) <= 60 and len(n) >= 2:
                secenekler = SELAM_HARITA.get(sikistir(n))
                if secenekler:
                    cevap = random.choice(secenekler)
            if cevap is None:
                cevap = ogretilen_tam(gid, n)
        if cevap:
            if (simdi - self.selam_kullanici.get(uid, 0) < SELAM_KULLANICI_BEKLEME
                    or simdi - self.selam_kanal.get(mesaj.channel.id, 0) < SELAM_KANAL_BEKLEME):
                return
            self.selam_kullanici[uid] = self.selam_kanal[mesaj.channel.id] = simdi
            cevap = cevap.replace("{isim}", mesaj.author.display_name)
            vip, simge = vip_bilgi(gid, uid)
            if vip:
                cevap += f" {simge}"
            await self.guvenli_cevap(mesaj, [cevap[:1900]])
            return

        # 1.5) Komutsuz doğal dil: "resim çiz", "despacito çal", "bakiyem ne kadar", "ping" ...
        if d.get("dogal", True) and len(icerik) <= 200 and simdi - self.niyet_kullanici.get(uid, 0) >= 2:
            try:
                ctx = await self.bot.get_context(mesaj)
                if await self.niyet_calistir(ctx, icerik, dogrudan=False):
                    self.niyet_kullanici[uid] = simdi
                    return
            except Exception as e:
                print(f"Doğal dil komutu hatası: {e!r}")

        # 2) Soru cevaplama: varsayılan olarak HER kanalda soruya benzeyen mesajı yapay zeka cevaplar
        sohbet_kanali = aktiflik_kanali_mi(mesaj)
        if (((d.get("herkes", True) or mesaj.channel.id in d["kanallar"]) and len(icerik) >= 6 and soru_mu(icerik, n)
                or (sohbet_kanali and len(icerik) >= 3))
                and simdi - self.soru_kanal.get(mesaj.channel.id, 0) >= SORU_KANAL_BEKLEME):
            self.soru_kanal[mesaj.channel.id] = simdi
            async with mesaj.channel.typing():
                cevap = await self.ai_cevapla(mesaj.author, mesaj.channel.id, icerik, None, sessiz=True)
            if cevap:
                await self.guvenli_cevap(mesaj, parcala(cevap)[:3])

    @commands.hybrid_command(name="sohbet", usage="[ac | kapat | herkes | dogal | kanal]")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def sohbet(self, ctx, islem: str = None):
        """Otomatik sohbet: selamlaşma (sa → as) ve seçili kanallarda soru cevaplama"""
        d = self.sohbet_ayar(ctx.guild.id)
        islem = norm(islem or "")
        if islem == "ac":
            d["acik"] = True
            kaydet()
            return await ctx.send("✅ Otomatik selamlaşma **açıldı**. (sa → as, selam → selam sana ...)")
        if islem == "kapat":
            d["acik"] = False
            kaydet()
            return await ctx.send("🔕 Otomatik selamlaşma **kapatıldı**.")
        if islem == "herkes":
            d["herkes"] = not d.get("herkes", True)
            kaydet()
            return await ctx.send("✅ Her kanalda sorulara cevap verme **açıldı**." if d["herkes"]
                                  else "🔕 Sorulara sadece `td!sohbet kanal` ile seçilen kanallarda cevap vereceğim.")
        if islem == "dogal":
            d["dogal"] = not d.get("dogal", True)
            kaydet()
            return await ctx.send("✅ Komutsuz komutlar (resim çiz, şarkı çal...) **açıldı**." if d["dogal"]
                                  else "🔕 Komutsuz komutlar **kapatıldı**. (Etiketlersen yine anlarım.)")
        if islem == "kanal":
            if ctx.channel.id in d["kanallar"]:
                d["kanallar"].remove(ctx.channel.id)
                kaydet()
                return await ctx.send("🔕 Bu kanalda artık sorulara kendiliğinden cevap vermeyeceğim.")
            d["kanallar"].append(ctx.channel.id)
            kaydet()
            return await ctx.send("✅ Bu kanalda soru gibi görünen mesajlara kendiliğinden cevap vereceğim.")
        kanallar = ", ".join(f"<#{k}>" for k in d["kanallar"]) or "yok"
        await ctx.send(
            "💬 **Otomatik sohbet**\n"
            f"• Selamlaşma (sa → as, selam → selam sana): **{'açık' if d['acik'] else 'kapalı'}**\n"
            f"• Her kanalda soru cevaplama: **{'açık' if d.get('herkes', True) else 'kapalı'}** (`td!sohbet herkes`)\n"
            f"• Komutsuz komutlar (resim çiz, şarkı çal...): **{'açık' if d.get('dogal', True) else 'kapalı'}** (`td!sohbet dogal`)\n"
            f"• Sadece şu kanallarda cevap (herkes kapalıysa): {kanallar}\n"
            "Komutlar: `td!sohbet ac`, `td!sohbet kapat`, `td!sohbet kanal` (bulunduğun kanalı ekler/çıkarır).\n"
            "Yeni tetikleyici öğretmek için: `td!ogret sa | as` (mesaj birebir aynı yazılırsa cevap verir).",
            allowed_mentions=NO_PING)

    # ================= 💬 ai komutu (main.py'dekinin yerine: görsel okur) =================
    async def resimleri_al(self, mesaj, ek=None):
        """Mesajdaki (ve cevap verilen mesajdaki) görselleri indirir. (resimler, atlanan_sayi) döner.
        mesaj None olabilir (slash); ek: slash'taki resim parametresi."""
        adaylar = list(mesaj.attachments) if mesaj is not None else []
        if ek is not None:
            adaylar.append(ek)
        ref = mesaj.reference if mesaj is not None else None
        if ref is not None and ref.message_id:
            hedef = ref.resolved if isinstance(ref.resolved, discord.Message) else None
            if hedef is None:
                try:
                    hedef = await mesaj.channel.fetch_message(ref.message_id)
                except discord.HTTPException:
                    hedef = None
            if hedef is not None:
                adaylar += list(hedef.attachments)
        resimler, atlanan = [], 0
        for a in adaylar:
            tur = (a.content_type or "").split(";")[0].lower()
            if not tur.startswith("image/"):
                continue
            if tur not in GORSEL_TURLER or a.size > GORSEL_MAX_MB * 1024 * 1024 or len(resimler) >= GORSEL_MAX:
                atlanan += 1
                continue
            try:
                resimler.append((tur, await a.read()))
            except discord.HTTPException:
                atlanan += 1
        return resimler, atlanan

    @commands.hybrid_command(name="ai", usage="<soru>  (resim de ekleyebilirsin)")
    async def ai(self, ctx, *, soru: str = None, resim: Optional[discord.Attachment] = None):
        """Yapay zekayla sohbet et: görsel okur, bilmediğini webde arar (konuşmayı hatırlar)"""
        resimler, atlanan = ([], 0)
        mesaj = ctx.message if getattr(ctx, "interaction", None) is None else None
        if mesaj is not None or resim is not None:
            resimler, atlanan = await self.resimleri_al(mesaj, resim)
        if atlanan:
            await ctx.send(f"🖼️ {atlanan} görseli okuyamadım (png, jpg ya da webp olmalı, en fazla {GORSEL_MAX_MB} MB, "
                           f"en fazla {GORSEL_MAX} tane).")
        if not soru and not resimler:
            if not atlanan:
                await ctx.send("Efendim? Sorunu yazmak için: `td/ai <sorun>` (resim de ekleyebilirsin)")
            return
        if not soru:
            soru = "Bu görselde ne var? Yazı varsa oku, kısaca anlat."
        if not resimler and await self.niyet_calistir(ctx, soru):
            return
        async with ctx.typing():
            cevap = await self.ai_cevapla(ctx.author, ctx.channel.id, soru, resimler)
        await self.yanitla(ctx, parcala(cevap))

    async def yanitla(self, ctx, parcalar):
        """Mesaja yanıt vererek ve yazan kişiyi etiketleyerek cevap verir (slash'ta normal gönderir)."""
        mesaj = ctx.message if getattr(ctx, "interaction", None) is None else None
        for i, parca in enumerate(parcalar):
            if i == 0 and mesaj is not None:
                try:
                    await mesaj.reply(parca, mention_author=True, allowed_mentions=YANIT_PING)
                    continue
                except discord.HTTPException:
                    pass                                      # asıl mesaj silinmiş olabilir
            if i == 0:
                await ctx.send(f"{ctx.author.mention} {parca}"[:2000], allowed_mentions=YANIT_PING)
            else:
                await ctx.send(parca, allowed_mentions=NO_PING)

    async def niyet_calistir(self, ctx, soru, dogrudan=True):
        """Komut yazmadan istenen işleri yapar. Bir şey yaptıysa True döner.
        - "ona resim çiz", "kedi çiz" -> çiz komutu (VIP kuralları aynen geçerli)
        - "kanalı kilitle" / "kilidi aç" -> sadece Kanalları Yönet yetkisi olanlar için"""
        if ctx.guild is None or not soru:
            return False
        n = norm(soru)
        kisa = len(n.split()) <= 8

        # kilit: sadece kısa, net cümleler ("kanalı kilitle", "kilidi aç") ve yetkili kişi
        if kisa and (RE_KILIT_AC.search(n) or RE_KILIT.search(n)):
            ac = bool(RE_KILIT_AC.search(n))
            if not ctx.author.guild_permissions.manage_channels:
                await self.yanitla(ctx, ["❌ Kanalı kilitlemek/açmak için **Kanalları Yönet** yetkin olmalı."])
                return True
            komut = self.bot.get_command("unlock" if ac else "lock")
            if komut is None:
                return False
            try:
                await ctx.invoke(komut)
            except discord.Forbidden:
                await self.yanitla(ctx, ["❌ Benim **Kanalları Yönet** yetkim yok."])
            except discord.HTTPException:
                await self.yanitla(ctx, ["❌ Kanal ayarı değiştirilemedi."])
            return True

        # çizim
        if RE_CIZ.search(n) and (dogrudan or len(n.split()) <= 12):
            komut = self.bot.get_command("ciz")
            if komut is None:
                return False
            tarif = " ".join(k for k in soru.split() if norm(k) and norm(k) not in CIZ_GEREKSIZ)
            # "ona resim çiz" gibi konu söylenmediyse: yanıt verilen mesajın metnini/adını kullan
            hedef_kisi = None
            ref = ctx.message.reference if getattr(ctx, "interaction", None) is None else None
            if ref is not None and ref.message_id:
                hedef = ref.resolved if isinstance(ref.resolved, discord.Message) else None
                if hedef is None:
                    try:
                        hedef = await ctx.channel.fetch_message(ref.message_id)
                    except discord.HTTPException:
                        hedef = None
                if hedef is not None:
                    hedef_kisi = hedef.author
                    if len(tarif) < 3 and hedef.content and not hedef.author.bot:
                        tarif = hedef.content.strip()[:300]
                    elif len(tarif) < 3 and not hedef.author.bot:
                        tarif = f"{hedef.author.display_name} için sevimli, renkli bir illüstrasyon"
            if len(tarif) < 3:
                await self.yanitla(ctx, ["🎨 Ne çizeyim? Örn: `@bot kırmızı bir spor araba çiz`"])
                return True
            if hedef_kisi is not None and hedef_kisi.id != ctx.author.id and not hedef_kisi.bot:
                tarif = f"{tarif} ({hedef_kisi.display_name} için)"
            await ctx.invoke(komut, tarif=tarif)
            return True
        return await self.komut_niyeti(ctx, soru, n, dogrudan)

    async def komut_yap(self, ctx, komut, arg=""):
        """Komutu `td!komut arg` yazılmış gibi çalıştırır (yetki, süre, argüman kontrolleri aynen geçerli)."""
        if getattr(ctx, "interaction", None) is not None or ctx.message is None:
            return False
        if self.bot.get_command(komut) is None:
            return False
        sahte = copy.copy(ctx.message)
        sahte.content = f"td!{komut} {arg}".strip()
        yeni = await self.bot.get_context(sahte)
        if yeni.command is None:
            return False
        await self.bot.invoke(yeni)
        return True

    async def komut_niyeti(self, ctx, soru, n, dogrudan):
        """Mesajdan hangi komutun istendiğini anlar ve çalıştırır. Bir şey yaptıysa True döner.
        dogrudan=False (etiketsiz sıradan mesaj) iken müzik komutları sadece ses kanalındakilere çalışır."""
        if ctx.guild is None or not n:
            return False
        kelime_sayisi = len(n.split())
        sesli = getattr(ctx.author, "voice", None) is not None and ctx.author.voice.channel is not None
        mentionlar = [f"<@{m}>" for m in RE_MENTION.findall(soru)]

        # müzik çal: "despacito çal", "çal sezen aksu", "bana bir şarkı çal tarkan"
        if kelime_sayisi <= 12 and RE_CAL.search(n) and (dogrudan or sesli):
            sarki = " ".join(k for k in soru.split() if norm(k) not in CAL_GEREKSIZ)
            if len(sarki) >= 2:
                return await self.komut_yap(ctx, "cal", sarki)

        # hesap makinesi: "5*(3+2) kaç eder"
        m = RE_HESAP.match(soru.lower().replace("kaç", "kac"))
        if m and re.search(r"\d\s*[\+\-\*/x×÷\^]\s*[\d\(]", m.group(1)):
            return await self.komut_yap(ctx, "hesapla", m.group(1).strip())

        # zar
        if kelime_sayisi <= 5 and RE_ZAR.search(n):
            sayi = re.search(r"\b(\d{1,4})\b", n)
            return await self.komut_yap(ctx, "zar", sayi.group(1) if sayi else "")

        # afk
        m = RE_AFK.match(n)
        if m:
            sebep = n[m.end():].strip()
            return await self.komut_yap(ctx, "afk", sebep)

        # moderasyon (etiketli kişi gerekir; yetkini komutun kendisi kontrol eder)
        if mentionlar and kelime_sayisi <= 12:
            for rx, komut in RE_MOD:
                if rx.search(n):
                    arg = mentionlar[0]
                    if komut == "timeout":
                        sure = RE_SURE.search(n)
                        if sure:
                            birim = {"dk": "m", "dakika": "m", "saat": "h", "sa": "h", "sn": "s", "saniye": "s",
                                     "gun": "d", "g": "d"}[sure.group(2)]
                            arg += f" {sure.group(1)}{birim}"
                        else:
                            arg += " 10m"
                    return await self.komut_yap(ctx, komut, arg)

        # mesaj sil: "20 mesaj sil"
        m = RE_TEMIZLE.search(n)
        if m and kelime_sayisi <= 5:
            return await self.komut_yap(ctx, "temizle", m.group(1))

        # şehir isteyen araçlar: "hava durumu ankara", "ankara hava durumu", "istanbul namaz vakti"
        m = re.search(r"^(\w+)\s+hava(?: durumu)?$", n) or re.search(r"\bhava(?: durumu)?\s+(?:nasil\s+)?(\w+)$", n)
        if m and kelime_sayisi <= 4 and m.group(1) not in ("nasil", "durumu", "bugun", "yarin", "ne", "mi"):
            return await self.komut_yap(ctx, "hava", m.group(1))
        m = re.search(r"^(\w+)\s+namaz(?: vakti| vakitleri)?$", n) or re.search(r"\bnamaz(?: vakti| vakitleri)?\s+(\w+)$", n)
        if m and kelime_sayisi <= 4 and m.group(1) not in ("vakti", "vakitleri", "kacta", "ne"):
            return await self.komut_yap(ctx, "namaz", m.group(1))
        if kelime_sayisi <= 4 and re.search(r"\b(namaz vakti|namaz vakitleri|ezan ne zaman)\b", n):
            return await self.komut_yap(ctx, "namaz", "")
        if kelime_sayisi <= 4 and re.search(r"\bhava durumu\b", n):
            return await self.komut_yap(ctx, "hava", "")

        # kalan basit komutlar (tablo)
        for rx, komut, ses_gerekli, en_fazla in NIYET_TABLO:
            if kelime_sayisi <= en_fazla and rx.search(n):
                if ses_gerekli and not dogrudan and not sesli:
                    continue
                if komut == "avatar" and mentionlar:
                    return await self.komut_yap(ctx, komut, mentionlar[0])
                return await self.komut_yap(ctx, komut, "")
        return False

    # ================= 🧠 Eğitim komutları =================
    @commands.hybrid_command(name="ogret", aliases=["öğret", "aiegit"],
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

    @commands.hybrid_command(name="ogretilenler", aliases=["öğretilenler", "aibilgiler"],
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

    @commands.hybrid_command(name="aisil", usage="<S3 ya da B2>")
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

    @commands.hybrid_command(name="aitest")
    @commands.has_permissions(manage_guild=True)
    async def aitest(self, ctx):
        """Yapay zeka modellerinin hızını ölç"""
        satirlar = []
        async with ctx.typing():
            for model in list(self.g.get("AI_MODELLER") or []):
                t0 = time.perf_counter()
                cevap, hata = await self.tek_model(
                    model, [{"role": "user", "parts": [{"text": "Sadece 'tamam' de."}]}], "Kısa cevap ver.", arama=False)
                ms = int((time.perf_counter() - t0) * 1000)
                satirlar.append(f"✅ `{model}`: **{ms} ms**" if cevap else f"❌ `{model}`: {hata} ({ms} ms)")
        await ctx.send("⚡ **Hız testi**\n" + "\n".join(satirlar or ["Hiç model tanımlı değil."]))


# ----------------------------------------------------------------------
# Yükleme (main.py setup_hook içinden çağrılır)
# ----------------------------------------------------------------------
async def kur(bot, g):
    yukle()
    cog = HizliAI(bot, g)
    eski_ai = bot.remove_command("ai")        # main.py'deki eski `ai` komutu, görsel okuyan yenisiyle değişir
    try:
        await bot.add_cog(cog)
    except Exception:
        if eski_ai is not None:
            bot.add_command(eski_ai)          # hata olursa eski komut geri gelsin
        raise
    g["ai_cevapla"] = cog.ai_cevapla          # eski kod yolu için
    g["ai"] = cog.ai                           # main.py etiket/yanıt kodu `ai` adını kullanır: yeni (görsel okuyan) komut
    g["EK_KATEGORILER"].update(YARDIM)
