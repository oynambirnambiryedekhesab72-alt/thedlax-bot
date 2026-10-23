# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.0 - Slash komut grupları

Discord en fazla 100 slash komutuna izin verir. Bu modül mevcut komutları gruplara toplar:
bir grup 1 hak harcar, içine 25'e kadar alt komut girer.
    /muzik cal, /muzik gec, /muzik kuyruk ...   (11 komut = 1 hak)
    /ekonomi bakiye, /mod kick, /xp profil ...

- `td!` ile yazılan komutlar DEĞİŞMEZ (td!cal, td!kick ... aynen çalışır).
- Sadece `/` tarafı gruplanır. help, ping, surum, avatar gibi çok kullanılanlar tek başına kalır.
- main.py komutları yükledikten sonra, slash'lar Discord'a gönderilmeden hemen önce çalışır.
- Bir şey ters giderse o grup geri alınır ve komutlar eskisi gibi tek başına kalır.
- Kapatmak için: GRUPLAMA_ACIK = False
"""
from discord import app_commands

GRUPLAMA_ACIK = True

# (grup adı, açıklama (en fazla 100 karakter), taşınacak komutlar)
GRUPLAR = [
    ("muzik", "🎵 Müzik: çal, geç, kuyruk, ses, döngü...",
     ["cal", "durdur", "devam", "gec", "dur", "kuyruk", "simdi", "ses", "dongu", "karistir", "kuyrukcikar"]),
    ("ekonomi", "💰 Ekonomi: bakiye, günlük, çalış, market, kumar...",
     ["bakiye", "gunluk", "calis", "kumar", "gonder", "zenginler", "market", "satinal", "parabas", "slot"]),
    ("xp", "📈 Seviye ve XP: seviye, profil, sıralama, ödül roller",
     ["seviye", "siralama", "profil", "seviyepanel", "seviyerol", "seviyerolsil", "seviyeroller",
      "xpver", "xpal", "seviyeayarla", "xpsifirla"]),
    ("mod", "🛡️ Moderasyon ve güvenlik: kick, ban, uyarı, küfür filtresi...",
     ["kick", "ban", "unban", "timeout", "untimeout", "temizle", "warn", "warnings", "clearwarns", "nick",
      "rolver", "rolal", "kanalsil", "muafkanal", "muafrol", "muaflar", "kufurekle", "kufursil",
      "guvenlik", "logkanal", "logkapat", "sicil"]),
    ("ses", "🔊 Ses odası ayarları: kilit, limit, isim, susturma",
     ["odakilit", "odalimit", "odaisim", "sessure", "seslider"]),
    ("sunucu", "⚙️ Sunucu kurulumu: hoş geldin, otorol, paneller, bilgi",
     ["sunucukur", "hosgeldin", "hosgeldinkapat", "hosgeldinmesaj", "otorol", "otorolkapat", "yenihesapgun",
      "rolpanel", "biletpanel", "biletayar", "serverinfo", "rolbilgi"]),
    ("etkinlik", "🎉 Çekiliş, anket, hatırlatıcı ve oyunlar",
     ["cekilis", "cekilisbitir", "cekilisyeniden", "anket", "hatirlat", "tkm", "xox", "sayitahmin", "sihirlitop"]),
    ("mesaj", "✉️ Mesaj gönderme: say, embed, dm duyuru",
     ["say", "embed", "fake", "dm", "dmduyuru", "dmkapat", "dmac"]),
    ("bilgi", "ℹ️ Bilgi ve araçlar: kullanıcı bilgisi, hesap makinesi, çeviri...",
     ["userinfo", "banner", "emojibuyut", "ozet", "cevir", "hesapla", "oneri"]),
]

# Gruplanmayan (tek başına kalan) komutlar: help, ping, surum, avatar


def grupla(bot, ad, aciklama, komutlar):
    """Komutları tek bir slash grubuna toplar. (taşınanlar, notlar) döner. Hata olursa her şeyi geri alır."""
    adaylar, notlar = [], []
    for k in komutlar:
        cmd = bot.get_command(k)
        app = getattr(cmd, "app_command", None) if cmd is not None else None
        if app is None or bot.tree.get_command(k) is not app:
            notlar.append(f"{k} (slash komutu yok ya da zaten taşınmış)")
            continue
        adaylar.append((k, app))
    if not adaylar:
        return [], notlar
    if len(adaylar) > 25:                                   # Discord sınırı: grup başına 25 alt komut
        notlar += [f"{k} (25 sınırı, tek başına kaldı)" for k, _ in adaylar[25:]]
        adaylar = adaylar[:25]

    # Grup adıyla aynı isimli bir üst düzey komut kalıyorsa çakışır (taşınacaklar hariç)
    cakisan = bot.tree.get_command(ad)
    if cakisan is not None and all(cakisan is not app for _, app in adaylar):
        return [], notlar + [f"grup adı '{ad}' başka bir komutla çakışıyor, grup kurulmadı"]

    try:
        grup = app_commands.Group(name=ad, description=aciklama[:100], guild_only=True)
    except TypeError:                                       # eski sürümlerde guild_only parametresi yok
        grup = app_commands.Group(name=ad, description=aciklama[:100])

    cikarilan = []
    try:
        for k, app in adaylar:
            bot.tree.remove_command(k)
            cikarilan.append((k, app))
        for k, app in adaylar:
            grup.add_command(app)
        bot.tree.add_command(grup)
    except Exception as e:                                  # her şeyi eski haline döndür
        for k, app in cikarilan:
            try:
                grup.remove_command(k)
            except Exception:
                pass
            app.parent = None
            if bot.tree.get_command(k) is None:
                bot.tree.add_command(app)
        if bot.tree.get_command(ad) is grup:
            bot.tree.remove_command(ad)
        return [], notlar + [f"hata, geri alındı: {e!r}"]
    return [k for k, _ in adaylar], notlar


async def kur(bot, g):
    if not GRUPLAMA_ACIK:
        print("Slash gruplama kapalı (GRUPLAMA_ACIK = False).")
        return
    once = len(bot.tree.get_commands())
    ozet = {}
    for ad, aciklama, komutlar in GRUPLAR:
        tasinan, notlar = grupla(bot, ad, aciklama, komutlar)
        if tasinan:
            ozet[ad] = tasinan
        for n in notlar:
            print(f"Slash grup '{ad}': {n}")
    sonra = len(bot.tree.get_commands())
    print(f"Slash gruplama: {sum(len(v) for v in ozet.values())} komut {len(ozet)} gruba toplandı. "
          f"Slash hakkı: {once} -> {sonra} / 100")
    if ozet:
        g["EK_KATEGORILER"]["🔀 Slash Grupları"] = (
            ["`/` ile yazarken komutlar gruplar halinde: önce grup, sonra komut (örn. `/muzik cal`). "
             "`td!cal` gibi prefix yazımı aynen çalışır."]
            + [f"`/{ad}` → " + ", ".join(k) for ad, k in ozet.items()]
        )
