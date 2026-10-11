# -*- coding: utf-8 -*-
"""THEDLAX v1.5 - ikinci parça (v15.py'nin devamı). v15.py bunu kendisi yükler."""
import time
from datetime import timedelta
import random
import asyncio
import discord
from collections import deque
from discord import app_commands
from discord.ext import commands
from v15 import *   # v15.py'deki her şey (veri, yardımcılar, butonlar...)

# ----------------------------------------------------------------------
# Sunucu kurma paneli v2
# ----------------------------------------------------------------------
SABLONLAR = {
    "topluluk": {
        "ad": "🏘️ Topluluk", "aciklama": "Genel sohbet, eğlence ve yetkili alanı olan klasik sunucu",
        "yapi": [
            ("📌 BİLGİ", ["kurallar", "duyurular", "etkinlikler"], [], False),
            ("💬 SOHBET", ["genel-sohbet", "medya", "bot-komutlari", "öneriler"], ["Sohbet 1", "Sohbet 2", "Müzik"], False),
            ("🎮 EĞLENCE", ["oyun-sohbet", "meme"], ["Oyun Odası"], False),
            ("🛡️ YETKİLİ", ["yetkili-sohbet", "log"], ["Yetkili Ses"], True),
        ],
    },
    "oyun": {
        "ad": "🎮 Oyun", "aciklama": "Takım arama, klip ve oyun odaları olan oyuncu sunucusu",
        "yapi": [
            ("📌 BİLGİ", ["kurallar", "duyurular", "patch-notlari"], [], False),
            ("🎮 OYUN SOHBET", ["genel", "takim-ara", "klip-ve-ss", "strateji"], [], False),
            ("🔊 SES ODALARI", [], ["Lobi", "Takım 1", "Takım 2", "Takım 3", "AFK"], False),
            ("🛡️ YETKİLİ", ["yetkili-sohbet", "log"], [], True),
        ],
    },
    "calisma": {
        "ad": "📚 Çalışma / Eğitim", "aciklama": "Ders kanalları ve sessiz çalışma odaları",
        "yapi": [
            ("📌 BİLGİ", ["kurallar", "duyurular"], [], False),
            ("📚 DERSLER", ["matematik", "fen", "edebiyat", "yazilim", "odev-yardim"], [], False),
            ("💬 SOHBET", ["genel-sohbet", "kaynaklar"], [], False),
            ("🔊 ÇALIŞMA", [], ["Sessiz Çalışma 1", "Sessiz Çalışma 2", "Grup Çalışması"], False),
            ("🛡️ YETKİLİ", ["yetkili-sohbet", "log"], [], True),
        ],
    },
    "magaza": {
        "ad": "🛒 Mağaza / Destek", "aciklama": "Ürün, fiyat, destek ve yorum kanalları",
        "yapi": [
            ("📌 BİLGİ", ["kurallar", "duyurular", "urunler"], [], False),
            ("🛒 MAĞAZA", ["satin-al", "fiyat-listesi", "yorumlar"], [], False),
            ("🎫 DESTEK", ["destek", "sss"], [], False),
            ("💬 TOPLULUK", ["genel-sohbet"], ["Sohbet"], False),
            ("🛡️ YETKİLİ", ["yetkili-sohbet", "log"], [], True),
        ],
    },
    "yayinci": {
        "ad": "📺 Yayıncı", "aciklama": "Yayın bildirimi, klip ve hayran kanalları",
        "yapi": [
            ("📌 BİLGİ", ["kurallar", "duyurular", "yayin-bildirim"], [], False),
            ("📺 YAYINCI", ["genel-sohbet", "klipler", "fan-art", "sorular"], ["Yayın Sohbet", "Sessiz Oda"], False),
            ("🛡️ YETKİLİ", ["yetkili-sohbet", "log"], [], True),
        ],
    },
}

ROL_SABLONU = [
    ("🛡️ Moderatör", 0x3498DB,
     dict(kick_members=True, ban_members=True, manage_messages=True, moderate_members=True,
          manage_nicknames=True, view_audit_log=True), True),
    ("🧪 Yardımcı", 0x2ECC71, dict(manage_messages=True, moderate_members=True), True),
    ("✅ Üye", 0x95A5A6, dict(), False),
    ("🤖 Botlar", 0x9B59B6, dict(), True),
]


def yapi_say(yapi):
    return sum(1 + len(m) + len(s) for _, m, s, _ in yapi)


def kanal_adi(ad):
    return ad.lower().replace(" ", "-")


async def sablon_uygula(guild, yapi, yapan):
    sebep = f"{yapan} sunucu kurma panelini kullandı"
    yeni = atlanan = 0
    for kat_ad, metinler, sesler, gizli in yapi:
        kat = discord.utils.find(lambda c: c.name.lower() == kat_ad.lower(), guild.categories)
        if kat is None:
            ow = {}
            if gizli:
                ow = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                }
            kat = await guild.create_category(kat_ad[:100], overwrites=ow, reason=sebep)
            yeni += 1
        var = {c.name.lower() for c in kat.channels}
        for m in metinler:
            if kanal_adi(m) in var:
                atlanan += 1
                continue
            k = await guild.create_text_channel(m[:100], category=kat, reason=sebep)
            yeni += 1
            if m == "log" and not sunucu_ayar(guild.id)["log"]:
                sunucu_ayar(guild.id)["log"] = k.id
                veri_kaydet()
        for s in sesler:
            if s.lower() in var:
                atlanan += 1
                continue
            await guild.create_voice_channel(s[:100], category=kat, reason=sebep)
            yeni += 1
    return yeni, atlanan


def sablon_onizleme(anahtar):
    s = SABLONLAR[anahtar]
    satirlar = []
    for kat, m, ses, gizli in s["yapi"]:
        parca = " ".join([f"#{x}" for x in m] + [f"🔊{x}" for x in ses]) or "—"
        satirlar.append(f"**{kat}**{' 🔒' if gizli else ''}\n{parca}")
    e = discord.Embed(
        title=f"{s['ad']} şablonu",
        description="\n\n".join(satirlar)[:3900] + "\n\n*Var olan kanallar atlanır, hiçbir şey silinmez.*",
        color=discord.Color.blurple(),
    )
    e.set_footer(text=f"Toplam {yapi_say(s['yapi'])} kategori/kanal")
    return e


class SablonOnay(discord.ui.View):
    def __init__(self, anahtar):
        super().__init__(timeout=120)
        self.anahtar = anahtar

    @discord.ui.button(label="Kur", emoji="✅", style=discord.ButtonStyle.success)
    async def kur(self, interaction, button):
        guild = interaction.guild
        yapi = SABLONLAR[self.anahtar]["yapi"]
        if len(guild.channels) + yapi_say(yapi) > 500:
            return await interaction.response.edit_message(content="❌ Kanal sınırı (500) aşılır, şablon kurulamaz.", embed=None, view=None)
        await interaction.response.edit_message(content="⏳ Kuruluyor...", embed=None, view=None)
        try:
            yeni, atlanan = await sablon_uygula(guild, yapi, interaction.user)
        except discord.Forbidden:
            return await interaction.edit_original_response(content="❌ Benim **Kanalları Yönet** yetkim yok.")
        except discord.HTTPException as e:
            return await interaction.edit_original_response(content=f"❌ Şablon yarım kaldı: {getattr(e, 'text', e)}"[:200])
        await interaction.edit_original_response(
            content=f"✅ Şablon kuruldu: **{yeni}** yeni kategori/kanal, **{atlanan}** zaten vardı.")
        await log(guild, "🧩 Şablon kuruldu", f"{interaction.user.mention} → {SABLONLAR[self.anahtar]['ad']}", discord.Color.green())

    @discord.ui.button(label="İptal", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def iptal(self, interaction, button):
        await interaction.response.edit_message(content="İptal edildi.", embed=None, view=None)


class SablonSecim(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="🧩 Hazır şablon seç (önce önizleme gösterilir)...",
            options=[discord.SelectOption(label=v["ad"], value=k, description=v["aciklama"][:100]) for k, v in SABLONLAR.items()],
            row=2,
        )

    async def callback(self, interaction):
        anahtar = self.values[0]
        await interaction.response.send_message(embed=sablon_onizleme(anahtar), view=SablonOnay(anahtar), ephemeral=True)


class TopluModal(discord.ui.Modal, title="Toplu kanal oluştur"):
    metin = discord.ui.TextInput(
        label="Her satır bir kategori",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        placeholder="💬 SOHBET > genel, medya, 🔊Ses 1\n🎮 OYUN > lfg, klipler, 🔊Lobi",
    )

    async def on_submit(self, interaction):
        yapi = []
        for satir in self.metin.value.splitlines()[:15]:
            if not satir.strip():
                continue
            kat, _, geri = satir.partition(">")
            kat = kat.strip()
            if not kat:
                continue
            metinler, sesler = [], []
            for oge in geri.split(","):
                oge = oge.strip()
                if not oge:
                    continue
                if oge.startswith("🔊"):
                    sesler.append(oge.lstrip("🔊").strip()[:100] or "Ses")
                else:
                    metinler.append(oge[:100])
            yapi.append((kat[:100], metinler, sesler, False))
        if not yapi:
            return await interaction.response.send_message("❌ Anlaşılır bir satır bulamadım.", ephemeral=True)
        if yapi_say(yapi) > 45:
            return await interaction.response.send_message("❌ Tek seferde en fazla 45 kategori/kanal.", ephemeral=True)
        if len(interaction.guild.channels) + yapi_say(yapi) > 500:
            return await interaction.response.send_message("❌ Kanal sınırı (500) aşılır.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            yeni, atlanan = await sablon_uygula(interaction.guild, yapi, interaction.user)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Benim **Kanalları Yönet** yetkim yok.", ephemeral=True)
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Yarım kaldı: {getattr(e, 'text', e)}"[:200], ephemeral=True)
        await interaction.followup.send(f"✅ **{yeni}** yeni kategori/kanal oluşturuldu, {atlanan} zaten vardı.", ephemeral=True)


async def rol_sablonu_kur(guild, yapan):
    if not yapan.guild_permissions.administrator:
        return "❌ Yetkili rol şablonu için **Yönetici** yetkisi gerekir."
    if not guild.me.guild_permissions.manage_roles:
        return "❌ Benim **Rolleri Yönet** yetkim yok."
    olusan = []
    for ad, renk, izin, hoist in ROL_SABLONU:
        if discord.utils.get(guild.roles, name=ad):
            continue
        await guild.create_role(
            name=ad, colour=discord.Colour(renk), permissions=discord.Permissions(**izin),
            hoist=hoist, reason=f"{yapan} rol şablonu kurdu",
        )
        olusan.append(ad)
    if not olusan:
        return "ℹ️ Şablondaki roller zaten var."
    return "✅ Oluşturulan roller: " + ", ".join(olusan) + "\n(Rolleri kimseye vermedim, sırasını sunucu ayarlarından düzenleyebilirsin.)"


async def hosgeldin_kur(guild, yapan):
    if not yapan.guild_permissions.manage_guild:
        return "❌ Bunun için **Sunucuyu Yönet** yetkin olmalı."
    kanal = discord.utils.get(guild.text_channels, name="hoş-geldin")
    if kanal is None:
        kanal = await guild.create_text_channel(
            "hoş-geldin", reason=f"{yapan} hoş geldin kurdu",
            overwrites={guild.default_role: discord.PermissionOverwrite(send_messages=False)},
        )
    sa(guild.id)["hosgeldin"]["kanal"] = kanal.id
    isaretle()
    return f"✅ Hoş geldin mesajları {kanal.mention} kanalına gelecek. Mesajı değiştirmek: `td!hosgeldinmesaj`"


async def bilet_kur(guild, yapan):
    if not yapan.guild_permissions.manage_guild:
        return "❌ Bunun için **Sunucuyu Yönet** yetkin olmalı."
    sebep = f"{yapan} bilet sistemi kurdu"
    PO = discord.PermissionOverwrite
    rol = discord.utils.get(guild.roles, name="🎧 Destek Ekibi")
    if rol is None and guild.me.guild_permissions.manage_roles:
        rol = await guild.create_role(name="🎧 Destek Ekibi", colour=discord.Colour(0xE67E22), reason=sebep)
    b = sa(guild.id)["bilet"]
    kat = guild.get_channel(b["kategori"]) if b["kategori"] else None
    if kat is None:
        ow = {guild.default_role: PO(view_channel=False), guild.me: PO(view_channel=True, send_messages=True, manage_channels=True)}
        if rol:
            ow[rol] = PO(view_channel=True, send_messages=True)
        kat = await guild.create_category("🎫 BİLETLER", overwrites=ow, reason=sebep)
    destek = discord.utils.find(lambda c: c.name == "🎫 DESTEK", guild.categories)
    if destek is None:
        destek = await guild.create_category("🎫 DESTEK", reason=sebep)
    kanal = discord.utils.get(destek.text_channels, name="bilet-aç")
    if kanal is None:
        kanal = await guild.create_text_channel(
            "bilet-aç", category=destek, reason=sebep,
            overwrites={guild.default_role: PO(send_messages=False, add_reactions=False)},
        )
    b["kategori"] = kat.id
    b["rol"] = rol.id if rol else b["rol"]
    isaretle()
    await kanal.send(embed=bilet_panel_embed(), view=bilet_view())
    return f"✅ Bilet sistemi kuruldu: {kanal.mention}" + (f"\nDestek rolü: {rol.mention}" if rol else "")


async def guvenlik_oner(guild, yapan):
    if not yapan.guild_permissions.manage_guild:
        return "❌ Bunun için **Sunucuyu Yönet** yetkin olmalı."
    a = sunucu_ayar(guild.id)["guvenlik"]
    acilan = ["kufur", "spam", "davet", "etiket", "tekrar", "dosya", "zalgo"]
    for k in acilan:
        a[k] = True
    veri_kaydet()
    return "✅ Önerilen koruma açıldı: " + ", ".join(MODULLER[k] for k in acilan) + "\nDiğerleri için: `td!guvenlik`"


async def seviye_kur(guild, yapan):
    if not yapan.guild_permissions.manage_guild:
        return "❌ Bunun için **Sunucuyu Yönet** yetkin olmalı."
    kanal = discord.utils.get(guild.text_channels, name="seviye")
    if kanal is None:
        kanal = await guild.create_text_channel("seviye", reason=f"{yapan} seviye sistemi kurdu")
    s = sa(guild.id)["seviye"]
    s["acik"] = True
    s["mod"] = "kanal"
    s["kanal"] = kanal.id
    isaretle()
    return f"✅ Seviye sistemi açık, seviye atlama mesajları {kanal.mention} kanalına gidecek.\nAyarlar: `td!seviyepanel`"


async def calistir(interaction, fonksiyon):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        mesaj = await fonksiyon(interaction.guild, interaction.user)
    except discord.Forbidden:
        mesaj = "❌ Yetkim yetmedi (Kanalları/Rolleri Yönet gerekebilir)."
    except discord.HTTPException as e:
        mesaj = f"❌ Hata: {getattr(e, 'text', e)}"[:200]
    await interaction.followup.send(mesaj, ephemeral=True)


def kur_embed(guild):
    me = guild.me.guild_permissions
    a = sunucu_ayar(guild.id)["guvenlik"]
    s = sa(guild.id)
    acik = sum(1 for k in MODULLER if a.get(k))
    log_ok = sunucu_ayar(guild.id)["log"]
    e = discord.Embed(
        title="🧱 Sunucu Kurma Paneli",
        description="Butonlarla kanal, rol ve hazır sistemler kur. **Hiçbir buton var olan bir şeyi silmez.**",
        color=discord.Color.blurple(),
    )
    e.add_field(
        name="📊 Sunucu",
        value=f"Kanal: **{len(guild.channels)}**/500 • Kategori: **{len(guild.categories)}** • Rol: **{len(guild.roles)}**",
        inline=False,
    )
    e.add_field(
        name="🔑 Yetkilerim",
        value=f"{'✅' if me.manage_channels else '❌'} Kanalları Yönet • {'✅' if me.manage_roles else '❌'} Rolleri Yönet • "
              f"{'✅' if me.moderate_members else '❌'} Üyeleri Sustur • {'✅' if me.kick_members else '❌'} At",
        inline=False,
    )
    e.add_field(
        name="⚙️ Sistemler",
        value=(
            f"{'🟢' if s['seviye']['acik'] else '🔴'} Seviye • "
            f"{'🟢' if log_ok else '🔴'} Log • "
            f"{'🟢' if s['hosgeldin']['kanal'] else '🔴'} Hoş geldin • "
            f"{'🟢' if s['bilet']['kategori'] else '🔴'} Bilet • "
            f"🛡️ Güvenlik {acik}/{len(MODULLER)}"
        ),
        inline=False,
    )
    return e


class KurView2(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)
        self.add_item(SablonSecim())

    async def interaction_check(self, interaction):
        if interaction.guild and interaction.user.guild_permissions.manage_channels:
            return True
        await interaction.response.send_message("❌ Bunun için **Kanalları Yönet** yetkin olmalı.", ephemeral=True)
        return False

    @discord.ui.button(label="Metin Kanalı", emoji="💬", style=discord.ButtonStyle.primary, row=0)
    async def b_metin(self, interaction, button):
        await interaction.response.send_modal(KanalModal("text"))

    @discord.ui.button(label="Ses Kanalı", emoji="🔊", style=discord.ButtonStyle.primary, row=0)
    async def b_ses(self, interaction, button):
        await interaction.response.send_modal(KanalModal("voice"))

    @discord.ui.button(label="Kategori", emoji="📁", style=discord.ButtonStyle.primary, row=0)
    async def b_kategori(self, interaction, button):
        await interaction.response.send_modal(KanalModal("category"))

    @discord.ui.button(label="Rol", emoji="🏷️", style=discord.ButtonStyle.secondary, row=0)
    async def b_rol(self, interaction, button):
        await interaction.response.send_modal(RolModal())

    @discord.ui.button(label="Toplu Kanal", emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def b_toplu(self, interaction, button):
        await interaction.response.send_modal(TopluModal())

    @discord.ui.button(label="Yetkili Rolleri", emoji="🛡️", style=discord.ButtonStyle.secondary, row=1)
    async def b_rolsablon(self, interaction, button):
        await calistir(interaction, rol_sablonu_kur)

    @discord.ui.button(label="Hoş Geldin", emoji="👋", style=discord.ButtonStyle.success, row=1)
    async def b_hosgeldin(self, interaction, button):
        await calistir(interaction, hosgeldin_kur)

    @discord.ui.button(label="Bilet", emoji="🎫", style=discord.ButtonStyle.success, row=1)
    async def b_bilet(self, interaction, button):
        await calistir(interaction, bilet_kur)

    @discord.ui.button(label="Güvenlik Öner", emoji="🔐", style=discord.ButtonStyle.success, row=1)
    async def b_guvenlik(self, interaction, button):
        await calistir(interaction, guvenlik_oner)

    @discord.ui.button(label="Seviye", emoji="📈", style=discord.ButtonStyle.success, row=1)
    async def b_seviye(self, interaction, button):
        await calistir(interaction, seviye_kur)

    @discord.ui.button(label="Durumu Yenile", emoji="🔄", style=discord.ButtonStyle.secondary, row=3)
    async def b_yenile(self, interaction, button):
        await interaction.response.edit_message(embed=kur_embed(interaction.guild), view=self)


async def kur_panel(ctx):
    await ctx.send(embed=kur_embed(ctx.guild), view=KurView2())


# ----------------------------------------------------------------------
# Seviye paneli
# ----------------------------------------------------------------------
CARPANLAR = [1.0, 1.5, 2.0, 3.0]
MOD_ADLARI = {"kanal": "Kanalda", "dm": "DM'den", "kapali": "Kapalı"}
MOD_SIRA = ["kanal", "dm", "kapali"]


def seviye_panel_embed(guild):
    s = sa(guild.id)["seviye"]
    roller = sorted(((int(l), r) for l, r in s["roller"].items()))
    rol_yazi = "\n".join(f"**{l}.** seviye → <@&{r}>" for l, r in roller) or "Yok (`td!seviyerol <seviye> @rol`)"
    kanal = f"<#{s['kanal']}>" if s["kanal"] else "Mesajın yazıldığı kanal"
    e = discord.Embed(
        title="📈 Seviye Sistemi",
        description=(
            f"{'🟢 Açık' if s['acik'] else '🔴 Kapalı'} • XP çarpanı: **{s['carpan']:g}x**\n"
            f"Duyuru: **{MOD_ADLARI[s['mod']]}** • Duyuru kanalı: {kanal}\n"
            f"XP kapalı kanal sayısı: **{len(s['yasak_kanal'])}**"
        ),
        color=discord.Color.gold(),
    )
    e.add_field(name="🏷️ Seviye rolleri", value=rol_yazi[:1000], inline=False)
    e.set_footer(text=f"Mesaj başı {XP_MIN}-{XP_MAX} XP ({XP_BEKLEME} sn arayla) • Ses: dakikada {SES_XP_DK} XP")
    return e


class SeviyePanel(discord.ui.View):
    def __init__(self, gid, kanal_id):
        super().__init__(timeout=300)
        self.gid = gid
        self.kanal_id = kanal_id
        self.kur()

    def kur(self):
        self.clear_items()
        s = sa(self.gid)["seviye"]
        ayarlar = [
            (f"Sistem: {'AÇIK' if s['acik'] else 'KAPALI'}", s["acik"], "ac"),
            (f"Duyuru: {MOD_ADLARI[s['mod']]}", True, "mod"),
            (f"XP çarpanı: {s['carpan']:g}x", True, "carpan"),
            (f"Bu kanalda XP: {'KAPALI' if self.kanal_id in s['yasak_kanal'] else 'AÇIK'}",
             self.kanal_id not in s["yasak_kanal"], "kanal"),
        ]
        for etiket, acik, anahtar in ayarlar:
            b = discord.ui.Button(
                label=etiket, style=discord.ButtonStyle.success if acik else discord.ButtonStyle.secondary)
            b.callback = self.cevir(anahtar)
            self.add_item(b)

    def cevir(self, anahtar):
        async def cb(interaction):
            s = sa(self.gid)["seviye"]
            if anahtar == "ac":
                s["acik"] = not s["acik"]
            elif anahtar == "mod":
                s["mod"] = MOD_SIRA[(MOD_SIRA.index(s["mod"]) + 1) % len(MOD_SIRA)]
            elif anahtar == "carpan":
                i = CARPANLAR.index(s["carpan"]) if s["carpan"] in CARPANLAR else -1
                s["carpan"] = CARPANLAR[(i + 1) % len(CARPANLAR)]
            elif anahtar == "kanal":
                if self.kanal_id in s["yasak_kanal"]:
                    s["yasak_kanal"].remove(self.kanal_id)
                else:
                    s["yasak_kanal"].append(self.kanal_id)
            isaretle()
            self.kur()
            await interaction.response.edit_message(embed=seviye_panel_embed(interaction.guild), view=self)
        return cb

    async def interaction_check(self, interaction):
        if interaction.guild and interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("❌ Bunun için **Sunucuyu Yönet** yetkin olmalı.", ephemeral=True)
        return False


# ----------------------------------------------------------------------
# Yardım satırları (main.py'deki /help menüsüne eklenir)
# ----------------------------------------------------------------------
YARDIM = {
    "📈 Seviye": [
        "`seviye [@kişi]` Seviye kartı",
        "`siralama [sayfa]` Sunucu sıralaması",
        "`profil [@kişi]` Seviye + bakiye profili",
        "`seviyepanel` Seviye ayar paneli (butonlu)",
        "`seviyerol <seviye> @rol` Seviyeye rol bağla",
        "`seviyerolsil <seviye>` / `seviyeroller` Rol bağlarını sil / listele",
        "`xpver @kişi <miktar>` / `xpal @kişi <miktar>` XP ver / al",
        "`seviyeayarla @kişi <seviye>` Seviyeyi ayarla",
        "`xpsifirla @kişi` XP sıfırla",
    ],
    "💰 Ekonomi": [
        "`bakiye [@kişi]` Cüzdan",
        "`gunluk` Günlük ödül (24 saatte bir)",
        "`calis` Çalış, para kazan (30 dk'da bir)",
        "`kumar <miktar|hepsi>` Kumar oyna (%45 şans, 2x)",
        "`gonder @kişi <miktar>` Para gönder",
        "`zenginler` En zengin 10 kişi",
    ],
    "🎉 Çekiliş / Bilet / Rol": [
        "`cekilis <süre> <kazanan sayısı> <ödül>` Butonlu çekiliş",
        "`cekilisbitir <mesaj ID>` / `cekilisyeniden <mesaj ID>` Bitir / yeniden çek",
        "`biletpanel [#kanal]` Bilet paneli gönder",
        "`biletayar @rol` Destek ekibi rolünü ayarla",
        "`rolpanel @rol1 [@rol2 ...]` Butonla rol alma paneli (en fazla 5)",
    ],
    "👋 Karşılama": [
        "`hosgeldin [#kanal]` Hoş geldin kanalı (kapatmak: `hosgeldinkapat`)",
        "`hosgeldinmesaj <metin>` Mesaj: `{uye}` `{isim}` `{sunucu}` `{sayi}`",
        "`otorol @rol` Girene otomatik rol (kapatmak: `otorolkapat`)",
    ],
    "🛡️ Güvenlik+": [
        "`guvenlik` panelinde yeni filtreler: büyük harf, toplu etiket, emoji spam, tekrar mesaj, tehlikeli dosya, bozuk yazı, raid, yeni hesap",
        "`yenihesapgun <gün>` Yeni hesap engeli kaç günlük hesabı atsın",
        "`muafkanal #kanal` Kanalı filtrelerden muaf tut / geri al",
        "`muafrol @rol` Rolü filtrelerden muaf tut / geri al",
        "`muaflar` Muaf liste",
    ],
}


# ----------------------------------------------------------------------
# Komutlar ve olaylar
# ----------------------------------------------------------------------
IS_METINLERI = [
    "kargo taşıdın", "bir kafede çalıştın", "yazılım hatası düzelttin", "bahçe işi yaptın",
    "taksi sürdün", "video kurgusu yaptın", "market rafı dizdin", "ders verdin",
]


def hosgeldin_metni(metin, uye):
    return (
        metin.replace("{uye}", uye.mention).replace("{isim}", uye.display_name)
        .replace("{sunucu}", uye.guild.name).replace("{sayi}", str(uye.guild.member_count))
    )[:1900]


async def raid_at(uye, sebep):
    me = uye.guild.me
    if not me.guild_permissions.kick_members or uye.top_role >= me.top_role or uye.id == uye.guild.owner_id:
        return False
    sessiz_ayril.add((uye.guild.id, uye.id))
    try:
        await uye.send(f"🚫 **{uye.guild.name}** sunucusuna şu an giriş kısıtlı ({sebep}). Biraz sonra tekrar dene.")
    except discord.HTTPException:
        pass
    try:
        await uye.kick(reason=f"Otomatik: {sebep}")
        return True
    except discord.HTTPException:
        sessiz_ayril.discard((uye.guild.id, uye.id))
        return False


class KanalSilOnay(discord.ui.View):
    """Toplu kanal silme onayı (sadece komutu yazan kişi basabilir)."""

    def __init__(self, yazar_id, saat):
        super().__init__(timeout=30)
        self.yazar_id = yazar_id
        self.saat = saat
        self.bitti = False

    async def interaction_check(self, it):
        if it.user.id != self.yazar_id:
            await it.response.send_message("❌ Bu buton senin için değil.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Evet, sil", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def evet(self, it, btn):
        if self.bitti:
            return
        self.bitti = True
        self.stop()
        sinir = discord.utils.utcnow() - timedelta(hours=self.saat) if self.saat else None
        hedef = [c for c in it.guild.channels
                 if c.id != it.channel_id and (sinir is None or c.created_at >= sinir)]
        await it.response.edit_message(content=f"🗑️ **{len(hedef)}** kanal siliniyor, bekle...", view=None)
        silinen = hata = 0
        for c in hedef:
            try:
                await c.delete(reason=f"Toplu kanal temizliği ({it.user})")
                silinen += 1
            except discord.HTTPException:
                hata += 1
            await asyncio.sleep(0.4)
        try:
            await it.channel.send(f"✅ Bitti: **{silinen}** kanal silindi" + (f", **{hata}** silinemedi" if hata else "")
                                  + ". Şu an bulunduğun kanalı elle silebilirsin.")
        except discord.HTTPException:
            pass

    @discord.ui.button(label="İptal", style=discord.ButtonStyle.secondary, emoji="❎")
    async def iptal(self, it, btn):
        self.bitti = True
        self.stop()
        await it.response.edit_message(content="❎ İptal edildi.", view=None)


class V15(commands.Cog):
    def __init__(self, bot, g):
        self.bot = bot
        self.g = g

    # ---------------- Seviye ----------------
    @commands.hybrid_command(name="seviye", aliases=["rank", "level", "rutbe"], usage="[@kişi]")
    @app_commands.describe(uye="Kimin seviyesine bakılacak")
    async def seviye(self, ctx, uye: discord.Member = None):
        """Seviye kartını göster"""
        uye = uye or ctx.author
        if uye.bot:
            return await ctx.send("🤖 Botların seviyesi yok.")
        k = veri["xp"].get(str(ctx.guild.id), {}).get(str(uye.id), [0, 0])
        sv, kalan, gerek = seviye_hesapla(k[0])
        liste = siralama_listesi(ctx.guild.id)
        sira = next((i for i, (u, _) in enumerate(liste, 1) if u == str(uye.id)), None)
        e = discord.Embed(title=f"⭐ {uye.display_name}", color=uye.color)
        e.set_thumbnail(url=uye.display_avatar.url)
        e.add_field(name="Seviye", value=f"**{sv}**", inline=True)
        e.add_field(name="Sıra", value=f"**#{sira}** / {len(liste)}" if sira else "—", inline=True)
        e.add_field(name="Toplam XP", value=para(k[0]), inline=True)
        e.add_field(
            name=f"{sv + 1}. seviyeye",
            value=f"{bar(kalan / gerek)} {para(kalan)} / {para(gerek)} XP", inline=False)
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="siralama", aliases=["top", "lb", "leaderboard"], usage="[sayfa]")
    @app_commands.describe(sayfa="Sayfa numarası")
    async def siralama(self, ctx, sayfa: int = 1):
        """Sunucunun seviye sıralaması"""
        liste = siralama_listesi(ctx.guild.id)
        if not liste:
            return await ctx.send("📭 Henüz kimse XP kazanmadı.")
        toplam_sayfa = (len(liste) - 1) // 10 + 1
        sayfa = max(1, min(sayfa, toplam_sayfa))
        baslangic = (sayfa - 1) * 10
        madalya = {1: "🥇", 2: "🥈", 3: "🥉"}
        satirlar = []
        for i, (uid, (xp, _)) in enumerate(liste[baslangic:baslangic + 10], baslangic + 1):
            satirlar.append(f"{madalya.get(i, f'**{i}.**')} <@{uid}> — Sv. **{seviye_hesapla(xp)[0]}** • {para(xp)} XP")
        e = discord.Embed(title=f"🏆 {ctx.guild.name} sıralaması", description="\n".join(satirlar), color=discord.Color.gold())
        e.set_footer(text=f"Sayfa {sayfa}/{toplam_sayfa}")
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="profil", aliases=["profile"], usage="[@kişi]")
    @app_commands.describe(uye="Kimin profiline bakılacak")
    async def profil(self, ctx, uye: discord.Member = None):
        """Seviye, bakiye ve katılım bilgisi"""
        uye = uye or ctx.author
        if uye.bot:
            return await ctx.send("🤖 Botların profili yok.")
        k = veri["xp"].get(str(ctx.guild.id), {}).get(str(uye.id), [0, 0])
        sv = seviye_hesapla(k[0])[0]
        bakiye = veri["eko"].get(str(ctx.guild.id), {}).get(str(uye.id), {}).get("bakiye", 0)
        e = discord.Embed(title=f"👤 {uye.display_name}", color=uye.color)
        e.set_thumbnail(url=uye.display_avatar.url)
        e.add_field(name="Seviye", value=f"{sv} ({para(k[0])} XP)", inline=True)
        e.add_field(name="Bakiye", value=f"{para(bakiye)} 🪙", inline=True)
        e.add_field(name="Hesap açılışı", value=discord.utils.format_dt(uye.created_at, "R"), inline=True)
        if uye.joined_at:
            e.add_field(name="Sunucuya katılış", value=discord.utils.format_dt(uye.joined_at, "R"), inline=True)
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="seviyepanel", aliases=["seviyeayar"])
    @commands.has_permissions(manage_guild=True)
    async def seviyepanel(self, ctx):
        """Seviye sistemi ayar paneli"""
        await ctx.send(embed=seviye_panel_embed(ctx.guild), view=SeviyePanel(ctx.guild.id, ctx.channel.id))

    @commands.hybrid_command(name="seviyerol", usage="<seviye> @rol")
    @app_commands.describe(seviye="Kaçıncı seviyede verilsin", rol="Verilecek rol")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def seviyerol(self, ctx, seviye: int, rol: discord.Role):
        """Bir seviyeye ulaşınca verilecek rolü ayarla"""
        if seviye < 1 or seviye > 500:
            return await ctx.send("❌ Seviye 1 ile 500 arasında olmalı.")
        if rol.managed or rol.is_default() or rol >= ctx.guild.me.top_role:
            return await ctx.send("❌ Bu rolü veremem (rolüm onun altında kalıyor ya da özel bir rol).")
        if ctx.author.id != ctx.guild.owner_id and rol >= ctx.author.top_role:
            return await ctx.send("❌ Bu rol senin rolünle aynı ya da senden yüksek.")
        sa(ctx.guild.id)["seviye"]["roller"][str(seviye)] = rol.id
        isaretle()
        await ctx.send(f"✅ **{seviye}. seviyeye** ulaşanlara {rol.mention} verilecek.", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="seviyerolsil", usage="<seviye>")
    @app_commands.describe(seviye="Hangi seviyenin rol bağı silinsin")
    @commands.has_permissions(manage_guild=True)
    async def seviyerolsil(self, ctx, seviye: int):
        """Seviye rolü bağını sil"""
        if sa(ctx.guild.id)["seviye"]["roller"].pop(str(seviye), None) is None:
            return await ctx.send("❌ Bu seviyede bağlı rol yok.")
        isaretle()
        await ctx.send("✅ Seviye rolü bağı silindi.")

    @commands.hybrid_command(name="seviyeroller")
    async def seviyeroller(self, ctx):
        """Seviye rollerini listele"""
        roller = sorted((int(l), r) for l, r in sa(ctx.guild.id)["seviye"]["roller"].items())
        if not roller:
            return await ctx.send("📭 Seviye rolü ayarlı değil.")
        await ctx.send("\n".join(f"**{l}.** seviye → <@&{r}>" for l, r in roller), allowed_mentions=NO_PING)

    @commands.hybrid_command(name="xpver", usage="@kişi <miktar>")
    @app_commands.describe(uye="Kişi", miktar="Verilecek XP")
    @commands.has_permissions(manage_guild=True)
    async def xpver(self, ctx, uye: discord.Member, miktar: int):
        """Kişiye XP ver"""
        if uye.bot or miktar < 1 or miktar > 1_000_000:
            return await ctx.send("❌ Miktar 1 ile 1.000.000 arasında olmalı (botlara verilemez).")
        await xp_ekle(ctx.guild, uye, miktar, duyur=False)
        sv = seviye_hesapla(xp_kayit(ctx.guild.id, uye.id)[0])[0]
        await ctx.send(f"✅ {uye.mention} kişisine **{para(miktar)} XP** verildi (şimdi {sv}. seviye).", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="xpal", usage="@kişi <miktar>")
    @app_commands.describe(uye="Kişi", miktar="Alınacak XP")
    @commands.has_permissions(manage_guild=True)
    async def xpal(self, ctx, uye: discord.Member, miktar: int):
        """Kişiden XP al"""
        if uye.bot or miktar < 1 or miktar > 1_000_000:
            return await ctx.send("❌ Miktar 1 ile 1.000.000 arasında olmalı.")
        await xp_ekle(ctx.guild, uye, -miktar, duyur=False)
        sv = seviye_hesapla(xp_kayit(ctx.guild.id, uye.id)[0])[0]
        await ctx.send(f"✅ {uye.mention} kişisinden **{para(miktar)} XP** alındı (şimdi {sv}. seviye).", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="seviyeayarla", usage="@kişi <seviye>")
    @app_commands.describe(uye="Kişi", seviye="Yeni seviye")
    @commands.has_permissions(manage_guild=True)
    async def seviyeayarla(self, ctx, uye: discord.Member, seviye: int):
        """Kişinin seviyesini ayarla"""
        if uye.bot or seviye < 0 or seviye > 500:
            return await ctx.send("❌ Seviye 0 ile 500 arasında olmalı.")
        k = xp_kayit(ctx.guild.id, uye.id)
        await xp_ekle(ctx.guild, uye, toplam_xp(seviye) - k[0], duyur=False)
        await ctx.send(f"✅ {uye.mention} artık **{seviye}. seviye**.", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="xpsifirla", usage="@kişi")
    @app_commands.describe(uye="XP'si sıfırlanacak kişi")
    @commands.has_permissions(manage_guild=True)
    async def xpsifirla(self, ctx, uye: discord.Member):
        """Kişinin XP'sini sıfırla"""
        k = xp_kayit(ctx.guild.id, uye.id)
        await xp_ekle(ctx.guild, uye, -k[0], duyur=False)
        k[1] = 0
        await ctx.send(f"🧽 {uye.mention} kişisinin XP'si sıfırlandı.", allowed_mentions=NO_PING)

    # ---------------- Ekonomi ----------------
    @commands.hybrid_command(name="bakiye", aliases=["para", "cuzdan"], usage="[@kişi]")
    @app_commands.describe(uye="Kimin bakiyesine bakılacak")
    async def bakiye(self, ctx, uye: discord.Member = None):
        """Cüzdanını göster"""
        uye = uye or ctx.author
        if uye.bot:
            return await ctx.send("🤖 Botların cüzdanı yok.")
        await ctx.send(f"👛 **{uye.display_name}** bakiyesi: **{para(eko(ctx.guild.id, uye.id)['bakiye'])} 🪙**", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="gunluk", aliases=["daily"])
    async def gunluk(self, ctx):
        """Günlük ödülünü al (24 saatte bir)"""
        e = eko(ctx.guild.id, ctx.author.id)
        simdi = time.time()
        if simdi - e["gunluk"] < 86400:
            return await ctx.send(f"⏳ Günlük ödülünü zaten aldın. <t:{int(e['gunluk'] + 86400)}:R> tekrar alabilirsin.")
        miktar = random.randint(200, 400)
        e["bakiye"] += miktar
        e["gunluk"] = simdi
        isaretle()
        await ctx.send(f"🎁 Günlük ödülün: **{miktar} 🪙** (bakiye: {para(e['bakiye'])})")

    @commands.hybrid_command(name="calis", aliases=["work"])
    async def calis(self, ctx):
        """Çalışıp para kazan (30 dakikada bir)"""
        e = eko(ctx.guild.id, ctx.author.id)
        simdi = time.time()
        if simdi - e["calis"] < 1800:
            return await ctx.send(f"⏳ Yorgunsun. <t:{int(e['calis'] + 1800)}:R> tekrar çalışabilirsin.")
        miktar = random.randint(40, 120)
        e["bakiye"] += miktar
        e["calis"] = simdi
        isaretle()
        await ctx.send(f"💼 {random.choice(IS_METINLERI)} ve **{miktar} 🪙** kazandın.")

    @commands.hybrid_command(name="kumar", aliases=["gamble", "bahis"], usage="<miktar|hepsi>")
    @app_commands.describe(miktar="Bahis miktarı ya da 'hepsi'")
    async def kumar(self, ctx, miktar: str):
        """Kumar oyna: %45 şansla paran 2 katı olur"""
        e = eko(ctx.guild.id, ctx.author.id)
        if miktar.lower() in ("hepsi", "all"):
            m = e["bakiye"]
        else:
            try:
                m = int(miktar.replace(".", "").replace(",", ""))
            except ValueError:
                return await ctx.send("❌ Miktarı sayı ya da `hepsi` olarak yaz.")
        if m < 10:
            return await ctx.send("❌ En az **10 🪙** bahis yapabilirsin.")
        if m > e["bakiye"]:
            return await ctx.send(f"❌ Yeterli paran yok (bakiye: {para(e['bakiye'])} 🪙).")
        if m > 50000:
            return await ctx.send("❌ Tek seferde en fazla **50.000 🪙** bahis yapabilirsin.")
        if random.random() < 0.45:
            e["bakiye"] += m
            sonuc = f"🎰 **Kazandın!** +{para(m)} 🪙"
        else:
            e["bakiye"] -= m
            sonuc = f"💸 **Kaybettin.** -{para(m)} 🪙"
        isaretle()
        await ctx.send(f"{sonuc}\n👛 Bakiye: **{para(e['bakiye'])} 🪙**")

    @commands.hybrid_command(name="gonder", aliases=["pay", "yolla"], usage="@kişi <miktar>")
    @app_commands.describe(uye="Para gönderilecek kişi", miktar="Gönderilecek miktar")
    async def gonder(self, ctx, uye: discord.Member, miktar: int):
        """Birine para gönder"""
        if uye.bot or uye.id == ctx.author.id:
            return await ctx.send("❌ Kendine ya da bota para gönderemezsin.")
        if miktar < 1 or miktar > 10_000_000:
            return await ctx.send("❌ Miktar 1 ile 10.000.000 arasında olmalı.")
        e = eko(ctx.guild.id, ctx.author.id)
        if miktar > e["bakiye"]:
            return await ctx.send(f"❌ Yeterli paran yok (bakiye: {para(e['bakiye'])} 🪙).")
        e["bakiye"] -= miktar
        eko_ekle(ctx.guild.id, uye.id, miktar)
        await ctx.send(
            f"💸 {ctx.author.mention} → {uye.mention}: **{para(miktar)} 🪙** gönderdi.",
            allowed_mentions=NO_PING)

    @commands.hybrid_command(name="zenginler", aliases=["zengin", "richest"])
    async def zenginler(self, ctx):
        """Sunucunun en zengin 10 kişisi"""
        liste = sorted(
            ((u, d["bakiye"]) for u, d in veri["eko"].get(str(ctx.guild.id), {}).items() if d["bakiye"] > 0),
            key=lambda x: -x[1])[:10]
        if not liste:
            return await ctx.send("📭 Henüz kimsenin parası yok.")
        madalya = {1: "🥇", 2: "🥈", 3: "🥉"}
        satirlar = [f"{madalya.get(i, f'**{i}.**')} <@{u}> — **{para(b)} 🪙**" for i, (u, b) in enumerate(liste, 1)]
        e = discord.Embed(title="💰 En zenginler", description="\n".join(satirlar), color=discord.Color.gold())
        await ctx.send(embed=e, allowed_mentions=NO_PING)

    # ---------------- Çekiliş ----------------
    @commands.hybrid_command(name="cekilis", aliases=["çekiliş", "giveaway"], usage="<süre> <kazanan sayısı> <ödül>")
    @app_commands.describe(sure="Süre (örn: 30m, 2h, 1d)", kazanan="Kazanan sayısı", odul="Ödül")
    @commands.has_permissions(manage_guild=True)
    async def cekilis(self, ctx, sure: str, kazanan: int, *, odul: str):
        """Butonlu çekiliş başlat"""
        sn = self.g["sure_coz"](sure)
        if sn is None or sn < 10 or sn > 30 * 86400:
            return await ctx.send("❌ Süre 10 saniye ile 30 gün arasında olmalı. Örnek: `30m` `2h` `1d`")
        if kazanan < 1 or kazanan > 20:
            return await ctx.send("❌ Kazanan sayısı 1 ile 20 arasında olmalı.")
        c = {
            "odul": odul[:200], "bitis": time.time() + sn, "kazanan": kazanan, "host": ctx.author.id,
            "katilanlar": [], "bitti": False, "kanal": ctx.channel.id, "sunucu": ctx.guild.id, "kazananlar": [],
        }
        v = discord.ui.View(timeout=None)
        v.add_item(CekilisButonu())
        msg = await ctx.send(embed=cekilis_embed(c), view=v)
        veri["cekilis"][str(msg.id)] = c
        isaretle()

    @commands.hybrid_command(name="cekilisbitir", usage="<mesaj ID>")
    @app_commands.describe(mesaj_id="Çekiliş mesajının ID'si")
    @commands.has_permissions(manage_guild=True)
    async def cekilisbitir(self, ctx, mesaj_id: str):
        """Çekilişi hemen bitir"""
        c = veri["cekilis"].get(mesaj_id.strip())
        if not c or c.get("sunucu") != ctx.guild.id:
            return await ctx.send("❌ Bu sunucuda bu ID'ye ait çekiliş yok.")
        if c["bitti"]:
            return await ctx.send("❌ Bu çekiliş zaten bitmiş. Yeniden çekmek için `cekilisyeniden`.")
        await ctx.send("✅ Çekiliş bitiriliyor...")
        await cekilis_bitir(self.bot, mesaj_id.strip())

    @commands.hybrid_command(name="cekilisyeniden", usage="<mesaj ID>")
    @app_commands.describe(mesaj_id="Çekiliş mesajının ID'si")
    @commands.has_permissions(manage_guild=True)
    async def cekilisyeniden(self, ctx, mesaj_id: str):
        """Bitmiş çekilişte yeniden kazanan seç"""
        c = veri["cekilis"].get(mesaj_id.strip())
        if not c or c.get("sunucu") != ctx.guild.id:
            return await ctx.send("❌ Bu sunucuda bu ID'ye ait çekiliş yok.")
        if not c["bitti"]:
            return await ctx.send("❌ Bu çekiliş henüz bitmedi.")
        await ctx.send("🔁 Yeniden çekiliyor...")
        await cekilis_bitir(self.bot, mesaj_id.strip(), yeniden=True)

    # ---------------- Bilet / Rol paneli ----------------
    @commands.hybrid_command(name="biletpanel", usage="[#kanal]")
    @app_commands.describe(kanal="Panelin gönderileceği kanal (boşsa bu kanal)")
    @commands.has_permissions(manage_guild=True)
    async def biletpanel(self, ctx, kanal: discord.TextChannel = None):
        """Bilet (destek) paneli gönder"""
        kanal = kanal or ctx.channel
        try:
            await kanal.send(embed=bilet_panel_embed(), view=bilet_view())
        except discord.HTTPException:
            return await ctx.send("❌ O kanala mesaj gönderemedim.")
        await ctx.send(f"✅ Bilet paneli {kanal.mention} kanalına gönderildi.")

    @commands.hybrid_command(name="biletayar", usage="@rol")
    @app_commands.describe(rol="Biletleri görecek destek ekibi rolü")
    @commands.has_permissions(manage_guild=True)
    async def biletayar(self, ctx, rol: discord.Role):
        """Destek ekibi rolünü ayarla"""
        sa(ctx.guild.id)["bilet"]["rol"] = rol.id
        isaretle()
        await ctx.send(f"✅ Destek ekibi rolü {rol.mention} olarak ayarlandı.", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="rolpanel", usage="@rol1 [@rol2 ...]")
    @app_commands.describe(rol1="Birinci rol", rol2="İkinci rol", rol3="Üçüncü rol", rol4="Dördüncü rol", rol5="Beşinci rol")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rolpanel(self, ctx, rol1: discord.Role, rol2: discord.Role = None, rol3: discord.Role = None,
                       rol4: discord.Role = None, rol5: discord.Role = None):
        """Butonla rol alınan panel gönder (en fazla 5 rol)"""
        roller = []
        for r in (rol1, rol2, rol3, rol4, rol5):
            if r is not None and r not in roller:
                roller.append(r)
        for r in roller:
            if r.managed or r.is_default() or r >= ctx.guild.me.top_role:
                return await ctx.send(f"❌ {r.mention} rolünü veremem (rolüm onun altında kalıyor ya da özel bir rol).", allowed_mentions=NO_PING)
            if riskli_rol(r):
                return await ctx.send(f"❌ {r.mention} yetkili bir rol, buton paneline konamaz.", allowed_mentions=NO_PING)
            if ctx.author.id != ctx.guild.owner_id and r >= ctx.author.top_role:
                return await ctx.send(f"❌ {r.mention} senin rolünle aynı ya da senden yüksek.", allowed_mentions=NO_PING)
        v = discord.ui.View(timeout=None)
        for r in roller:
            v.add_item(RolButonu(r.id, r.name))
        e = discord.Embed(
            title="🏷️ Rol Seç",
            description="Aşağıdaki butonlara basarak rol alabilir, tekrar basarak geri verebilirsin.\n"
                        + "\n".join(r.mention for r in roller),
            color=discord.Color.blurple())
        await ctx.send(embed=e, view=v, allowed_mentions=NO_PING)

    # ---------------- Karşılama ----------------
    @commands.hybrid_command(name="hosgeldin", aliases=["welcome"], usage="[#kanal]")
    @app_commands.describe(kanal="Hoş geldin mesajı kanalı (boşsa bu kanal)")
    @commands.has_permissions(manage_guild=True)
    async def hosgeldin(self, ctx, kanal: discord.TextChannel = None):
        """Hoş geldin kanalını ayarla"""
        kanal = kanal or ctx.channel
        sa(ctx.guild.id)["hosgeldin"]["kanal"] = kanal.id
        isaretle()
        await ctx.send(f"✅ Hoş geldin mesajları {kanal.mention} kanalına gidecek.")

    @commands.hybrid_command(name="hosgeldinkapat")
    @commands.has_permissions(manage_guild=True)
    async def hosgeldinkapat(self, ctx):
        """Hoş geldin mesajını kapat"""
        sa(ctx.guild.id)["hosgeldin"]["kanal"] = None
        isaretle()
        await ctx.send("✅ Hoş geldin mesajı kapatıldı.")

    @commands.hybrid_command(name="hosgeldinmesaj", usage="<metin>")
    @app_commands.describe(metin="Mesaj: {uye} {isim} {sunucu} {sayi}")
    @commands.has_permissions(manage_guild=True)
    async def hosgeldinmesaj(self, ctx, *, metin: str):
        """Hoş geldin mesajının metnini değiştir"""
        sa(ctx.guild.id)["hosgeldin"]["mesaj"] = metin[:1000]
        isaretle()
        await ctx.send("✅ Hoş geldin mesajı güncellendi. Önizleme:\n" + hosgeldin_metni(metin[:1000], ctx.author),
                       allowed_mentions=NO_PING)

    @commands.hybrid_command(name="otorol", usage="@rol")
    @app_commands.describe(rol="Sunucuya girene otomatik verilecek rol")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def otorol(self, ctx, rol: discord.Role):
        """Girene otomatik rol ver"""
        if rol.managed or rol.is_default() or rol >= ctx.guild.me.top_role:
            return await ctx.send("❌ Bu rolü veremem (rolüm onun altında kalıyor ya da özel bir rol).")
        if riskli_rol(rol):
            return await ctx.send("❌ Yetkili bir rol otomatik verilemez.")
        sa(ctx.guild.id)["otorol"] = rol.id
        isaretle()
        await ctx.send(f"✅ Yeni gelenlere {rol.mention} verilecek.", allowed_mentions=NO_PING)

    @commands.hybrid_command(name="otorolkapat")
    @commands.has_permissions(manage_guild=True)
    async def otorolkapat(self, ctx):
        """Otomatik rolü kapat"""
        sa(ctx.guild.id)["otorol"] = None
        isaretle()
        await ctx.send("✅ Otomatik rol kapatıldı.")

    # ---------------- Güvenlik+ ----------------
    @commands.hybrid_command(name="yenihesapgun", usage="<gün>")
    @app_commands.describe(gun="Kaç günden yeni hesaplar atılsın (1-90)")
    @commands.has_permissions(manage_guild=True)
    async def yenihesapgun(self, ctx, gun: int):
        """Yeni hesap engeli için gün sınırı"""
        if gun < 1 or gun > 90:
            return await ctx.send("❌ Gün 1 ile 90 arasında olmalı.")
        sa(ctx.guild.id)["yenihesap_gun"] = gun
        isaretle()
        await ctx.send(f"✅ {gun} günden yeni hesaplar atılacak (filtre `td!guvenlik` panelinden açılır).")

    @commands.hybrid_command(name="muafkanal", usage="#kanal")
    @app_commands.describe(kanal="Filtrelerden muaf tutulacak kanal")
    @commands.has_permissions(manage_guild=True)
    async def muafkanal(self, ctx, kanal: discord.TextChannel):
        """Kanalı güvenlik filtrelerinden muaf tut / geri al"""
        liste = sa(ctx.guild.id)["muaf_kanal"]
        if kanal.id in liste:
            liste.remove(kanal.id)
            sonuc = f"✅ {kanal.mention} artık filtrelere tabi."
        else:
            liste.append(kanal.id)
            sonuc = f"✅ {kanal.mention} filtrelerden muaf."
        isaretle()
        await ctx.send(sonuc)

    @commands.hybrid_command(name="muafrol", usage="@rol")
    @app_commands.describe(rol="Filtrelerden muaf tutulacak rol")
    @commands.has_permissions(manage_guild=True)
    async def muafrol(self, ctx, rol: discord.Role):
        """Rolü güvenlik filtrelerinden muaf tut / geri al"""
        liste = sa(ctx.guild.id)["muaf_rol"]
        if rol.id in liste:
            liste.remove(rol.id)
            sonuc = f"✅ {rol.mention} artık filtrelere tabi."
        else:
            liste.append(rol.id)
            sonuc = f"✅ {rol.mention} filtrelerden muaf."
        isaretle()
        await ctx.send(sonuc, allowed_mentions=NO_PING)

    @commands.hybrid_command(name="muaflar")
    @commands.has_permissions(manage_guild=True)
    async def muaflar(self, ctx):
        """Muaf kanal ve rolleri listele"""
        s = sa(ctx.guild.id)
        kanallar = " ".join(f"<#{k}>" for k in s["muaf_kanal"]) or "Yok"
        roller = " ".join(f"<@&{r}>" for r in s["muaf_rol"]) or "Yok"
        await ctx.send(f"🛡️ **Muaf kanallar:** {kanallar}\n🛡️ **Muaf roller:** {roller}", allowed_mentions=NO_PING)

    # ---------------- Toplu kanal silme (raid temizliği) ----------------
    @commands.hybrid_command(name="kanalsil", aliases=["kanaltemizle"], usage="[saat]")
    @app_commands.describe(saat="Sadece son X saatte açılan kanalları sil (boş bırakırsan HEPSİ silinir)")
    @commands.bot_has_permissions(manage_channels=True)
    async def kanalsil(self, ctx, saat: int = 0):
        """Kanalları toplu sil (sadece sunucu sahibi)"""
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("❌ Bu komutu sadece sunucu sahibi kullanabilir.")
        if saat < 0 or saat > 720:
            return await ctx.send("❌ Saat 0 ile 720 arasında olmalı (0 = hepsi).")
        sinir = discord.utils.utcnow() - timedelta(hours=saat) if saat else None
        sayi = sum(1 for c in ctx.guild.channels if c.id != ctx.channel.id and (sinir is None or c.created_at >= sinir))
        if sayi == 0:
            return await ctx.send("📭 Silinecek kanal yok.")
        kapsam = f"son **{saat} saatte** açılan" if saat else "**TÜM**"
        await ctx.send(
            f"⚠️ {kapsam} **{sayi}** kanal/kategori silinecek (şu an yazdığın kanal hariç). "
            f"Bu işlem **geri alınamaz.** Emin misin?",
            view=KanalSilOnay(ctx.author.id, saat))

    # ---------------- Olaylar ----------------
    @commands.Cog.listener()
    async def on_member_join(self, uye):
        if uye.bot:
            return
        guild = uye.guild
        a = sunucu_ayar(guild.id)["guvenlik"]
        s = sa(guild.id)
        simdi = time.time()

        dq = raid_katilim.setdefault(guild.id, deque(maxlen=50))
        dq.append((simdi, uye.id))
        if sum(1 for t, _ in dq if simdi - t <= RAID_SANIYE) >= RAID_SAYI and simdi >= raid_bitis.get(guild.id, 0):
            raid_bitis[guild.id] = simdi + RAID_SURE
            if a.get("raid"):
                await log(guild, "🚨 Raid algılandı", f"{RAID_SANIYE} sn içinde {RAID_SAYI}+ kişi girdi. "
                          f"{RAID_SURE // 60} dk boyunca yeni girenler atılacak.", discord.Color.red())
        if a.get("raid") and simdi < raid_bitis.get(guild.id, 0):
            if await raid_at(uye, "raid koruması"):
                await log(guild, "🚨 Raid: üye atıldı", f"{uye.mention} ({uye})", discord.Color.red())
                return
        if a.get("yenihesap"):
            yas = (discord.utils.utcnow() - uye.created_at).days
            if yas < s["yenihesap_gun"]:
                if await raid_at(uye, f"hesabın {s['yenihesap_gun']} günden yeni"):
                    await log(guild, "🆕 Yeni hesap atıldı", f"{uye.mention} ({uye}) — hesap {yas} günlük", discord.Color.orange())
                    return

        if s["otorol"] and guild.me.guild_permissions.manage_roles:
            rol = guild.get_role(s["otorol"])
            if rol is not None and not rol.managed and rol < guild.me.top_role and not riskli_rol(rol):
                try:
                    await uye.add_roles(rol, reason="Otorol")
                except discord.HTTPException:
                    pass
        h = s["hosgeldin"]
        if h["kanal"]:
            kanal = guild.get_channel(h["kanal"])
            if kanal is not None:
                try:
                    await kanal.send(hosgeldin_metni(h["mesaj"], uye), allowed_mentions=discord.AllowedMentions(users=[uye]))
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, uye):
        if (uye.guild.id, uye.id) in sessiz_ayril:
            sessiz_ayril.discard((uye.guild.id, uye.id))
            return
        if uye.bot:
            return
        h = sa(uye.guild.id)["hosgeldin"]
        if h["kanal"] and h["ayril"]:
            kanal = uye.guild.get_channel(h["kanal"])
            if kanal is not None:
                try:
                    await kanal.send(f"👋 **{uye.display_name}** aramızdan ayrıldı.", allowed_mentions=NO_PING)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, uye, before, after):
        if uye.bot:
            return
        a = (uye.guild.id, uye.id)
        simdi = time.time()
        if before.channel is None and after.channel is not None:
            ses_giris[a] = simdi
        elif before.channel is not None and after.channel is None:
            giris = ses_giris.pop(a, None)
            if giris is None or before.channel == uye.guild.afk_channel:
                return
            if not sa(uye.guild.id)["seviye"]["acik"]:
                return
            dk = min(int((simdi - giris) // 60), SES_XP_MAX_DK)
            if dk > 0:
                await xp_ekle(uye.guild, uye, dk * SES_XP_DK, duyur=True)


async def kur(bot, g):
    async def hepsi(message):
        if muaf_mi(message):
            return False
        if await otomod(message):
            return True
        return await otomod15(message)

    g["OTOMOD"] = hepsi
    g["SEVIYE_HOOK"] = mesaj_xp
    g["KUR_PANEL"] = kur_panel
    g["EK_KATEGORILER"].update(YARDIM)

    bot.add_dynamic_items(BiletAcButonu, BiletKapatButonu, RolButonu, CekilisButonu)
    await bot.add_cog(V15(bot, g))
