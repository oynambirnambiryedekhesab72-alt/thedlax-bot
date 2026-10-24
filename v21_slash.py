# -*- coding: utf-8 -*-
"""
THEDLAX BOT v2.1 - Slash menüsü (v20_slash.py'nin YERİNE geçer, onu sil)

Her kategori TEK slash komutudur. Yazınca karşına işlem listesi çıkar:
    /muzik  -> islem: cal / durdur / devam / gec / dur / kuyruk / simdi / ses / dongu ...
               girdi: şarkı adı, sebep, süre... (isteğe bağlı)
    /mod    -> islem: kick / ban / timeout / warn ...   kisi: kişiyi seç
    /ekonomi, /xp, /oda, /sunucu, /etkinlik, /mesaj, /bilgi, /yz, /vip, /koruma

- `td!` ile yazılan komutlar DEĞİŞMEZ. Slash sadece o komutları çalıştırır, yetkiler aynen geçerlidir.
- help, ping, surum, avatar tek başına kalır.
- Listede olmayan komutlar otomatik "diger" menülerine toplanır (hiçbiri kaybolmaz).
- Kapatmak için: SLASH_ACIK = False
"""
import re
import copy
from typing import Optional, Union

import discord
from discord import app_commands

SLASH_ACIK = True
NO_PING = discord.AllowedMentions.none()

# (slash adı, açıklama, komutlar)
KATEGORILER = [
    ("muzik", "🎵 Müzik: çal, durdur, geç, kuyruk, ses, döngü...",
     ["cal", "durdur", "devam", "gec", "dur", "kuyruk", "simdi", "ses", "dongu", "karistir", "kuyrukcikar",
      "muzikdurum"]),
    ("ekonomi", "💰 Ekonomi: bakiye, günlük, çalış, market, banka, kumar...",
     ["bakiye", "gunluk", "calis", "kumar", "gonder", "zenginler", "market", "satinal", "parabas", "slot",
      "marketekle", "marketsil", "soygun", "banka", "yatir", "bankacek"]),
    ("xp", "📈 Seviye ve XP: seviye, profil, sıralama, ödül roller",
     ["seviye", "siralama", "profil", "seviyepanel", "seviyerol", "seviyerolsil", "seviyeroller",
      "xpver", "xpal", "seviyeayarla", "xpsifirla"]),
    ("mod", "🛡️ Moderasyon: kick, ban, uyarı, timeout, temizle, rol...",
     ["kick", "ban", "unban", "timeout", "untimeout", "temizle", "warn", "warnings", "clearwarns", "nick",
      "rolver", "rolal", "toplurolver", "sicil", "lock", "unlock", "gizle", "goster", "yavasmod",
      "kilitherkes", "kilitkaldir", "kanalsil", "snipe"]),
    ("koruma", "🔒 Güvenlik, log, küfür filtresi, muaf kanal/rol",
     ["guvenlik", "logkanal", "logkapat", "kufurekle", "kufursil", "muafkanal", "muafrol", "muaflar"]),
    ("oda", "🔊 Ses odası ayarları: kilit, limit, isim, özel oda",
     ["odakilit", "odalimit", "odaisim", "sessure", "seslider", "ozelsesayarla", "ozelsesbitir"]),
    ("sunucu", "⚙️ Sunucu kurulumu: hoş geldin, otorol, paneller, istatistik",
     ["sunucukur", "hosgeldin", "hosgeldinkapat", "hosgeldinmesaj", "otorol", "otorolkapat", "yenihesapgun",
      "rolpanel", "biletpanel", "biletayar", "serverinfo", "rolbilgi", "kanalbilgi",
      "istatistikkanal", "istatistikkapat", "onerikanal"]),
    ("etkinlik", "🎉 Çekiliş, anket, quiz, aktiflik ve oyunlar",
     ["cekilis", "cekilisbitir", "cekilisyeniden", "anket", "hatirlat", "tkm", "xox", "sayitahmin", "sihirlitop",
      "zar", "yazitura", "sec", "quizkur", "quizsaat", "quizsor", "quizkaynak", "quizkapat",
      "aktiflikkur", "aktiflikaralik", "aktiflikkapat", "aktiflik"]),
    ("mesaj", "✉️ Mesaj: say, embed, dm duyuru, öneri, özel komut",
     ["say", "embed", "fake", "dm", "dmduyuru", "dmkapat", "dmac", "oneri", "onerionay", "onerired",
      "ozelkomutekle", "ozelkomutsil", "ozelkomutlar"]),
    ("bilgi", "ℹ️ Bilgi ve araçlar: kullanıcı, hesap makinesi, çeviri, afk...",
     ["userinfo", "banner", "emojibuyut", "ozet", "cevir", "hesapla", "uptime", "askolcer", "tersyaz",
      "sor", "afk", "modul"]),
    ("yz", "🤖 Yapay zeka: sohbet, çizim, öğretme",
     ["ai", "sohbet", "ogret", "ogretilenler", "aisil", "aitest", "aisifirla", "ciz", "ciztest"]),
    ("vip", "💎 VIP: ver, al, liste, rol, kanal, günlük",
     ["vipkur", "vipver", "vipal", "viplistesi", "vip", "vipgunluk", "viprol", "vipkanal"]),
]

TEK_BASINA = {"help", "ping", "surum", "avatar"}   # bunlar normal slash olarak kalır
KATEGORI_ADLARI = {k[0] for k in KATEGORILER} | {"diger", "diger2", "diger3", "diger4"}


class SahteMesaj(discord.Message):
    """Slash'tan gelen komutu `td!komut ...` gibi çalıştırmak için kullanılan mesaj."""
    __slots__ = ()

    async def reply(self, content=None, **kwargs):
        kwargs.pop("mention_author", None)
        kwargs.pop("reference", None)
        return await self.channel.send(content, **kwargs)

    async def delete(self, *, delay=None):          # yer tutucu zaten silindi
        return None

    async def add_reaction(self, emoji):
        return None


def kisa_aciklama(cmd):
    metin = (cmd.description or cmd.short_doc or cmd.help or "").strip().split("\n")[0]
    return metin


def secenek_adi(cmd):
    ad = cmd.name
    aciklama = kisa_aciklama(cmd)
    metin = f"{ad} — {aciklama}" if aciklama else ad
    return metin[:100]


def arg_olustur(cmd, girdi, kisi, rol, kanal):
    """Slash'ta seçilen kişi/rol/kanal + yazılan metni, komutun beklediği sıraya koyar."""
    usage = (cmd.usage or "").strip().lower().lstrip("[<( ")
    ozel = []
    if kisi is not None:
        ozel.append(f"<@{kisi.id}>")
    if rol is not None:
        ozel.append(f"<@&{rol.id}>")
    if kanal is not None:
        ozel.append(f"<#{kanal.id}>")
    girdi = (girdi or "").strip()
    # kullanım "<süre> [#kanal]" gibi yazıyla başlıyorsa önce yazı, sonra seçilenler gelir
    yazi_once = bool(usage) and not usage.startswith(("@", "#"))
    parcalar = ([girdi] + ozel) if yazi_once else (ozel + [girdi])
    return " ".join(p for p in parcalar if p)


async def calistir(bot, interaction, grup_adi, komut_adi, girdi, kisi, rol, kanal, dosya):
    cmd = bot.get_command(komut_adi)
    if cmd is None:
        return await interaction.response.send_message(f"❌ `{komut_adi}` komutu şu an yüklü değil.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)

    kanal_obj = interaction.channel
    if kanal_obj is None:
        try:
            kanal_obj = await bot.fetch_channel(interaction.channel_id)
        except discord.HTTPException:
            return await interaction.edit_original_response(content="❌ Kanalı bulamadım.")
    try:
        yer = await kanal_obj.send(f"⏳ {interaction.user.display_name}: `/{grup_adi} {komut_adi}`",
                                   allowed_mentions=NO_PING)
    except discord.HTTPException:
        return await interaction.edit_original_response(content="❌ Bu kanala yazma iznim yok.")

    sahte = copy.copy(yer)
    sahte.__class__ = SahteMesaj
    sahte.author = interaction.user
    sahte.content = f"td!{komut_adi} {arg_olustur(cmd, girdi, kisi, rol, kanal)}".strip()
    sahte.attachments = [dosya] if dosya is not None else []
    try:
        await yer.delete()                       # yer tutucuyu hemen sil, komut cevabı normal mesaj olarak gelir
    except discord.HTTPException:
        pass

    try:
        ctx = await bot.get_context(sahte)
        if ctx.command is None:
            return await interaction.edit_original_response(content=f"❌ `{komut_adi}` çalıştırılamadı.")
        await bot.invoke(ctx)
        await interaction.edit_original_response(content="✅ Tamam.")
    except Exception as e:
        print(f"Slash komutu hatası (/{grup_adi} {komut_adi}): {e!r}")
        try:
            await interaction.edit_original_response(content="❌ Bir hata oluştu.")
        except discord.HTTPException:
            pass


def kategori_komutu(bot, ad, aciklama, komutlar):
    secenekler = [app_commands.Choice(name=secenek_adi(bot.get_command(k)), value=k) for k in komutlar]

    @app_commands.command(name=ad, description=aciklama[:100])
    @app_commands.describe(
        islem="Ne yapmak istiyorsun? (listeden seç)",
        girdi="Ek bilgi: şarkı adı, sebep, süre, soru, miktar... (isteğe bağlı)",
        kisi="Kişi seç (isteğe bağlı)",
        rol="Rol seç (isteğe bağlı)",
        kanal="Kanal seç (isteğe bağlı)",
        dosya="Resim / dosya (isteğe bağlı)",
    )
    @app_commands.choices(islem=secenekler)
    @app_commands.guild_only()
    async def slash(interaction: discord.Interaction, islem: app_commands.Choice[str],
                    girdi: Optional[str] = None, kisi: Optional[discord.Member] = None,
                    rol: Optional[discord.Role] = None,
                    kanal: Optional[Union[discord.TextChannel, discord.VoiceChannel]] = None,
                    dosya: Optional[discord.Attachment] = None):
        await calistir(bot, interaction, ad, islem.value, girdi, kisi, rol, kanal, dosya)

    return slash


def slashtan_cikar(bot, komut_adi):
    try:
        bot.tree.remove_command(komut_adi)
    except Exception:
        pass


async def kur(bot, g):
    if not SLASH_ACIK:
        print("Slash menüsü kapalı (SLASH_ACIK = False).")
        return
    once = len(bot.tree.get_commands())
    ozet = {}
    kullanilan = set()

    def kategori_ekle(ad, aciklama, adaylar):
        adaylar = [k for k in adaylar if bot.get_command(k) is not None and k not in kullanilan]
        for i in range(0, len(adaylar), 25):             # Discord: bir listede en fazla 25 seçenek
            parca = adaylar[i:i + 25]
            slash_adi = ad if i == 0 else f"{ad}{i // 25 + 1}"
            cakisan = bot.tree.get_command(slash_adi)
            if cakisan is not None and cakisan.name not in parca:
                print(f"Slash '{slash_adi}' başka bir komutla çakışıyor, atlandı.")
                continue
            for k in parca:
                slashtan_cikar(bot, k)
            if bot.tree.get_command(slash_adi) is not None:
                slashtan_cikar(bot, slash_adi)
            try:
                bot.tree.add_command(kategori_komutu(bot, slash_adi, aciklama, parca))
            except Exception as e:
                print(f"Slash '{slash_adi}' kurulamadı: {e!r}")
                continue
            ozet[slash_adi] = parca
            kullanilan.update(parca)

    for ad, aciklama, komutlar in KATEGORILER:
        kategori_ekle(ad, aciklama, komutlar)

    # Listede olmayan ama slash'ı olan komutlar da "diger" menüsüne girsin (hiçbiri kaybolmasın)
    kalan = [c.name for c in bot.tree.get_commands()
             if isinstance(c, app_commands.Command) and c.name not in TEK_BASINA
             and c.name not in KATEGORI_ADLARI and bot.get_command(c.name) is not None]
    kategori_ekle("diger", "📦 Diğer komutlar", kalan)

    sonra = len(bot.tree.get_commands())
    print(f"Slash menüsü: {sum(len(v) for v in ozet.values())} komut {len(ozet)} menüye toplandı. "
          f"Slash hakkı: {once} -> {sonra} / 100")
    g["EK_KATEGORILER"]["🔀 Slash Menüsü"] = (
        ["`/` yazınca kategori seç (örn. `/muzik`), sonra **islem** listesinden komutu seç, gerekirse **girdi** yaz "
         "(örn. `/muzik islem:cal girdi:despacito`). `td!cal despacito` yazımı aynen çalışır.",
         "Komut yazmadan da olur: `despacito çal`, `kırmızı araba çiz`, `bakiyem ne kadar`, `sa`..."]
        + [f"`/{ad}` → " + ", ".join(k) for ad, k in ozet.items()]
    )
