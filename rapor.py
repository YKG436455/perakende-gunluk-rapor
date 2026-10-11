#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CEO PUSULASI — Perakende Strateji Brifingi
==========================================
Her sabah 07:00'de BİM üst yönetimi için stratejik brifing üretir.

Kaynaklar:
  - SEC EDGAR (ABD rakipleri, canlı)
  - Dünya Bankası (makro, canlı)
  - TCMB/TÜİK (bilinen son veriler)
  - RSS (4 kanal, İngilizce→Türkçe çevrilir)
  - Groq AI (ücretsiz, analiz + çeviri)

Çıktı: 7 bölümlü HTML mail + Excel eki
"""

import os
import re
import time
import json
import smtplib
import calendar
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from io import BytesIO

import feedparser
import requests
import pandas as pd
from groq import Groq

# ============================================================
# AYARLAR
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

GROQ_MODEL = "llama-3.3-70b-versatile"
SEC_HEADERS = {
    "User-Agent": "BIM-CEO-Briefing/1.0 (contact@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Haftanın teması (her gün farklı stratejik konu)
HAFTANIN_TEMASI = {
    0: ("Haftalık Rakip Karşılaştırması", "Mağaza başına ciro ve kârlılık farkları"),
    1: ("Makro Riskler ve Tüketici Davranışı", "Enflasyon, işsizlik, tüketim eğilimi"),
    2: ("Dijital Dönüşüm ve Retail Media", "E-ticaret, uygulama, reklam gelirleri"),
    3: ("Özel Marka ve Kâr Kalitesi", "Marj yönetimi, tedarik zinciri, fiyatlama"),
    4: ("Rekabet ve Düzenleyici Riskler", "Rekabet Kurumu, mevzuat, M&A"),
    5: ("Teknoloji ve Yapay Zekâ", "AI ajanlar, otomasyon, veri altyapısı"),
    6: ("Haftalık Stratejik Değerlendirme", "Geçen hafta ne öğrendik, gelecek hafta odak"),
}

# Perakende terimleri (20 kavram, döngüsel)
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza büyümesi. Yeni/kapanan mağazaları hariç tutar. BİM H1 2026: +%37,3 — fiyat kaynaklı, hacim değil.", "BİM'de LFL'in %75'i fiyat artışından geliyor. Hacim büyümesi yoksa bu sürdürülemez. Sepet içi ürün sayısına bakın."),
    ("Brüt Kâr Marjı", "Satıştan malın maliyeti düşüldükten sonra kalan tutarın satışa oranı. BİM: %19,1.", "Özel marka payını 5 puan artırmak brüt marjı 0,8-1,2 puan yükseltir. En kolay kâr kaldıracı."),
    ("FAVÖK (EBITDA)", "Faiz, Vergi, Amortisman, İtfa öncesi kâr. Nakit üretim göstergesi. BİM: %5,4.", "Türkiye perakendesinde %5+ FAVÖK marjı dünya ortalamasının üstü. Kıymetini bilin."),
    ("Özel Marka (Private Label)", "Marketin kendi markası. BİM: ~%55, ALDI: %90, Tesco: %50.", "ALDI modelinde %90'a çıkılabiliyor. BİM için 5 yıllık hedef %65 olmalı."),
    ("Stok Devir Hızı", "Stok yılda kaç kez yenileniyor. A101: 14, ALDI: 12, Migros: 8.", "BİM muhtemelen 12-13 aralığında. Her 1 puan artış nakit akışına 1-2 mr TL katkı demek."),
    ("Fire Oranı", "Bozulma/kayıp nedeniyle satılamayan oranı. Costco: %0,4, sektör ort.: %1,5.", "BİM'in taze ürün genişlemesi fire riski getirir. Mağaza bazında takip şart."),
    ("TMS 29", "Enflasyon muhasebesi. Türkiye'de zorunlu.", "BİM'in Q2 net kârında 6,8 mr TL parasal kazanç var. Nakit kâr ≠ Muhasebe kârı. Ayrımı iyi yapın."),
    ("CAPEX Yoğunluğu", "Yatırım / Satış oranı. BİM: ~%2,5.", "BİM son 5 yılda mağaza açılışını yavaşlattı. Yeni format (BİM Cell, taze) için CAPEX artışı gerekebilir."),
    ("Retail Media", "Raf/uygulama reklam geliri. Walmart: 3,4 mr $ (+%38).", "BİM'in bu alanda sıfır geliri var. 20 pilot mağazada raf ekranı = yıllık 500 mn TL potansiyel."),
    ("Ajan Tabanlı Ticaret", "AI'ların müşteri adına alışverişi. 2030: 3-5 trilyon $.", "BİM uygulaması 5 yıl içinde AI ajanı kabul etmezse, genç müşteriyi kaybeder."),
    ("ROCE", "Kullanılan sermayenin getirisi. Tesco: %15,2.", "BİM'in ROCE'si muhtemelen %25+. Bu, her TL'nin ne kadar verimli kullanıldığını gösterir."),
    ("NPS (Net Tavsiye Skoru)", "Müşteri sadakat ölçüsü. Tesco: 33, Lidl: 25.", "BİM NPS'i hiç ölçmüyor. Yıllık 10.000 müşteri anketi şart."),
    ("Omnichannel", "Mağaza + online birlikte. Migros: 2.520 online mağaza.", "BİM online'a girmedi. Bu strateji mi, eksiklik mi? 2026'da cevap gerekiyor."),
    ("Hard Discount", "Az çeşit, düşük fiyat, sade mağaza. BİM, A101, ŞOK, ALDI, Lidl.", "Türkiye'de hard discount pazar payı %60+. Bu bir zafer ama premium segment boş."),
    ("SKU Yönetimi", "Stok birimi sayısı. BİM: ~1.000, Migros: ~10.000.", "BİM'in 1.000 SKU disiplini kârlılığın sırrı. Taze üründe bu disiplini koruyabilir mi?"),
    ("TEPE", "TEPAV Perakende Güven Endeksi. Aylık açıklanır.", "TEPE pozitife dönerse tüketici harcaması artar. BİM buna hazır mı?"),
    ("Müşteri Trafiği", "Mağazaya giren müşteri. BİM: +%0,4 (zayıf).", "Trafik artmıyor, sepet büyüyor. Bu fiyat kaynaklı — gerçek büyüme değil."),
    ("Ortalama Sepet", "Satış / işlem sayısı.", "BİM'de sepet büyüyor ama içi küçülüyor. Tüketici daha az ürün alıyor, daha ucuz marka seçiyor."),
    ("Raf Bulunurluğu", "İstenen ürünün rafta olma oranı. İdeal: %97-99.", "BİM'in sadelik avantajı var ama taze üründe bu oran düşebilir. Gizli müşteri şart."),
    ("Stoksuz Kalma", "Talep varken rafın boş olması. İdeal: <%3.", "Her %1 stoksuz kalma = %0,5 ciro kaybı. Yıllık 2-3 mr TL demek."),
]


# ============================================================
# BÖLÜM 1: VERİ TOPLAMA
# ============================================================
class VeriToplayici:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def sec_verisi_cek(self, cik: str, sirket_adi: str) -> dict:
        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
            resp = self.session.get(url, headers=SEC_HEADERS, timeout=30)
            if resp.status_code != 200:
                return {"Şirket": sirket_adi, "Gelir (mr $)": "-", "Net Kâr (mr $)": "-", "Dönem": "-"}
            facts = resp.json().get("facts", {}).get("us-gaap", {})

            def son_deger(anahtar):
                veri = facts.get(anahtar, {}).get("units", {}).get("USD", [])
                if not veri:
                    return None, None
                son = veri[-1]
                return round(son.get("val", 0) / 1e9, 2), son.get("end", "?")

            gelir, donem = son_deger("Revenues")
            if gelir is None:
                gelir, donem = son_deger("RevenueFromContractWithCustomerExcludingAssessedTax")
            net_kar, _ = son_deger("NetIncomeLoss")
            return {
                "Şirket": sirket_adi,
                "Gelir (mr $)": gelir if gelir is not None else "-",
                "Net Kâr (mr $)": net_kar if net_kar is not None else "-",
                "Dönem": donem or "-",
            }
        except Exception as e:
            print(f"SEC hatası ({sirket_adi}): {e}")
            return {"Şirket": sirket_adi, "Gelir (mr $)": "-", "Net Kâr (mr $)": "-", "Dönem": "-"}

    def abd_sirketleri(self) -> pd.DataFrame:
        sirketler = [
            ("0000104169", "Walmart"),
            ("0001018724", "Amazon"),
            ("0000909832", "Costco"),
            ("0000056873", "Kroger"),
            ("0001646972", "Albertsons"),
            ("0001611983", "Target"),
        ]
        return pd.DataFrame([self.sec_verisi_cek(c, a) for c, a in sirketler])

    def turkiye_sirketleri(self) -> pd.DataFrame:
        data = {
            "Firma": ["BİM", "Migros", "ŞOK", "A101", "CarrefourSA"],
            "Dönem": ["H1 2026", "Q2 2026", "H1 2026", "2025/12", "Q2 2026"],
            "Satış (mr TL)": ["449,7", "124,4", "167,8", "~280", "~68"],
            "Mağaza": ["14.851", "3.830", "11.175", "~13.000", "~700"],
            "LFL Büyüme": ["+%37,3", "Negatif", "+%5", "-", "-"],
            "Net Kâr (mr TL)": ["+15,1", "-0,7", "-1,35", "-", "-"],
            "Mağaza Başı Ciro (mn TL)": ["30,7", "63,3", "15,1", "~21", "~97"],
        }
        return pd.DataFrame(data)

    def makro_gostergeler(self) -> pd.DataFrame:
        gostergeler = {
            "NY.GDP.MKTP.KD.ZG": "GSYİH Büyümesi (%)",
            "FP.CPI.TOTL.ZG": "Enflasyon (%)",
            "SL.UEM.TOTL.ZS": "İşsizlik (%)",
            "NE.CON.PRVT.ZS": "Hane Tüketimi (GSYİH %)",
        }
        sonuclar = []
        for kod, ad in gostergeler.items():
            try:
                url = f"https://api.worldbank.org/v2/country/TUR/indicator/{kod}?format=json&per_page=1&date=2023:2026"
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) > 1 and data[1] and data[1][0].get("value"):
                        d = data[1][0]
                        sonuclar.append({"Gösterge": ad, "Değer": f"{d['value']:.1f}", "Yıl": d.get("date", "")})
            except Exception as e:
                print(f"Dünya Bankası hatası: {e}")
        return pd.DataFrame(sonuclar)

    def rss_haberleri(self) -> list:
        kaynaklar = [
            ("https://www.retailtechnology.co.uk/rss.xml", "Teknoloji", True),
            ("https://retailgazette.com/feed/", "Global Perakende", True),
            ("https://perakendesektoru.com/feed/", "Türkiye Perakende", False),
            ("https://ekonomikgundem.com.tr/tag/gida-perakende/feed/", "Gıda", False),
        ]
        haberler = []
        for url, kategori, ingilizce in kaynaklar:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:4]:
                    ozet = re.sub("<[^<]+?>", "", entry.get("summary", ""))[:400]
                    haberler.append({
                        "Kategori": kategori,
                        "Başlık": entry.title,
                        "Özet": ozet,
                        "Link": entry.get("link", ""),
                        "İngilizce": ingilizce,
                    })
            except Exception as e:
                print(f"RSS hatası ({kategori}): {e}")
        return haberler


# ============================================================
# BÖLÜM 2: TÜRKÇE ÇEVİRİ
# ============================================================
def haberleri_turkceye_cevir(haberler: list, client: Groq) -> list:
    cevrilecek = [h for h in haberler if h.get("İngilizce")]
    if not cevrilecek or not client:
        return haberler
    metin = "\n\n".join([f"[{i}]\nBAŞLIK: {h['Başlık']}\nÖZET: {h['Özet']}" for i, h in enumerate(cevrilecek)])
    prompt = f"""Aşağıdaki İngilizce perakende haberlerini profesyonel Türkçeye çevir.
Sadece çevir, yorum ekleme. JSON döndür: {{"ceviriler":[{{"id":0,"baslik":"...","ozet":"..."}}]}}

{metin}"""
    try:
        yanit = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            max_tokens=3500,
            temperature=0.2,
        )
        sonuc = json.loads(yanit.choices[0].message.content)
        for c in sonuc.get("ceviriler", []):
            i = c.get("id")
            if i is not None and 0 <= i < len(cevrilecek):
                cevrilecek[i]["Başlık"] = c.get("baslik", cevrilecek[i]["Başlık"])
                cevrilecek[i]["Özet"] = c.get("ozet", cevrilecek[i]["Özet"])
    except Exception as e:
        print(f"Çeviri hatası: {e}")
    return haberler


# ============================================================
# BÖLÜM 3: CEO BRİFİNGİ (AI)
# ============================================================
def ceo_brifingi_uret(abd_df, tr_df, makro_df, haberler, terim, tema, client):
    if not client:
        return _bos_brifing()

    abd_m = abd_df.to_string(index=False)
    tr_m = tr_df.to_string(index=False)
    makro_m = makro_df.to_string(index=False)
    haber_m = "\n".join([f"- [{h['Kategori']}] {h['Başlık']}: {h['Özet'][:150]}" for h in haberler[:12]])

    sistem = """Sen BİM (Türkiye'nin en büyük hard-discount perakende zinciri) CEO'sunun
baş strateji danışmanısın. Görevi: sabah 07:00'de CEO'nun 60 saniyede okuyacağı
NET, KARAR ODAKLI bir brifing hazırlamak.

FELSEFEN:
- CEO'nun zamanı kıymetli: her cümle bir işe yaramalı.
- "Ne oldu?" değil, "Bu ne demek, ne yapmalıyım?" sorularına cevap ver.
- Rakamları BİM'e göre yorumla: "Walmart %38 büyüdü" değil, "BİM'in retail media
  fırsatı yıllık 500 mn TL olabilir" de.
- Karar öner: her bölüm bir sonuca bağlansın.

KESİN KURALLAR:
1. Sadece verilen verilere dayan. Uydurma.
2. Türkçe, profesyonel, net.
3. Yorumları "olabilir/muhtemel/önerilir" diliyle yaz.
4. Sayı verirken kaynağı belirt (SEC/Dünya Bankası/RSS).
5. Çıktı SADECE geçerli JSON.

JSON ŞEMASI:
{
  "manset": "Bugünün en kritik mesajı — 1 cümle, net bir iddia/uyarı",
  "sabah_60_saniye": [
    {"sinyal": "Kısa başlık", "rakam": "Somut sayı/veri", "neden_onemli": "BİM için neden önemli", "etki": "BİM'e olası etkisi"}
  ],
  "karar_gundemi": [
    {"konu": "...", "seçenek_a": "...", "seçenek_b": "...", "öneri": "...", "gerekçe": "..."}
  ],
  "rakip_radari": [
    {"rakip": "Migros", "hamle": "Ne yaptı", "bim_icin_ders": "BİM ne öğrenmeli/ne yapmalı"}
  ],
  "makro_pusu": [
    {"gösterge": "Enflasyon", "veri": "...", "yorum": "BİM için ne anlatıyor", "aksiyon": "Ne yapmalı"}
  ],
  "senaryolar": [
    {"tetikleyici": "Ne olursa", "iyimser": "...", "baz": "...", "kotumser": "...", "hazırlık": "Önceden ne yapmalı"}
  ],
  "saha_nabzi": {
    "gozlem": "Bugün mağazada bakılacak somut şey",
    "soru": "Mağaza müdürüne sorulacak tek soru",
    "beklenti": "Cevap ne olmalı, ne olursa alarm"
  },
  "haftalik_pusula": "Bu haftanın stratejik odağı — 1 paragraf",
  "uyari_seviyesi": "YEŞİL | SARI | KIRMIZI — gerekçesiyle"
}"""

    kullanici = f"""Bugün: {datetime.now().strftime('%d.%m.%Y %A')}
Haftanın teması: {tema[0]} — {tema[1]}
Günün terimi: {terim[0]} — {terim[1]}

=== ABD RAKİPLERİ (SEC EDGAR, canlı) ===
{abd_m}

=== TÜRKİYE PERAKENDECİLERİ ===
{tr_m}

=== MAKRO GÖSTERGELER (Dünya Bankası) ===
{makro_m}

=== GÜNÜN HABERLERİ ===
{haber_m}

Bu verilerle CEO brifingini JSON olarak üret. BİM odaklı, karar odaklı, net."""

    try:
        yanit = client.chat.completions.create(
            messages=[
                {"role": "system", "content": sistem},
                {"role": "user", "content": kullanici},
            ],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            max_tokens=5000,
            temperature=0.4,
        )
        return json.loads(yanit.choices[0].message.content)
    except Exception as e:
        print(f"AI brifing hatası: {e}")
        return _bos_brifing()


def _bos_brifing():
    return {
        "manset": "Brifing üretilemedi.",
        "sabah_60_saniye": [],
        "karar_gundemi": [],
        "rakip_radari": [],
        "makro_pusu": [],
        "senaryolar": [],
        "saha_nabzi": {"gozlem": "", "soru": "", "beklenti": ""},
        "haftalik_pusula": "",
        "uyari_seviyesi": "SARI — veri eksik",
    }


def gunun_terimi():
    gun = datetime.now().timetuple().tm_yday
    return SOZLUK[gun % len(SOZLUK)]


# ============================================================
# BÖLÜM 4: HTML ÜRETİCİLERİ
# ============================================================
def df_to_table(df, baslik):
    if df.empty:
        return f"<p><em>{baslik}: veri yok.</em></p>"
    h = f'<h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:24px">{baslik}</h3>'
    h += '<table style="border-collapse:collapse;width:100%;font-size:12px;font-family:Segoe UI,Arial">'
    h += '<thead><tr style="background:#1e293b;color:white">'
    for c in df.columns:
        h += f'<th style="padding:8px;text-align:left;border:1px solid #334155">{c}</th>'
    h += '</tr></thead><tbody>'
    for i, row in df.iterrows():
        bg = "#f8fafc" if i % 2 == 0 else "white"
        h += f'<tr style="background:{bg}">'
        for v in row:
            h += f'<td style="padding:6px;border:1px solid #e2e8f0">{v}</td>'
        h += '</tr>'
    h += '</tbody></table>'
    return h


def uyari_renk(seviye):
    s = (seviye or "").upper()
    if "KIRMIZI" in s:
        return "#dc2626", "#fee2e2"
    if "SARI" in s or "SARI" in s:
        return "#d97706", "#fef3c7"
    return "#16a34a", "#dcfce7"


def brifing_html(brifing, abd_df, tr_df, makro_df, haberler, terim, tema):
    tarih = datetime.now().strftime("%d.%m.%Y %A")
    renk, bg = uyari_renk(brifing.get("uyari_seviyesi", ""))

    # Sabah 60 saniye
    sinyaller = ""
    for s in brifing.get("sabah_60_saniye", []):
        sinyaller += f'''
        <div style="padding:14px;margin:10px 0;background:white;border-left:5px solid #3b82f6;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
            <div style="display:flex;justify-content:space-between;align-items:start">
                <div style="font-weight:700;color:#0f172a;font-size:15px">{s.get("sinyal","")}</div>
                <div style="background:#eff6ff;color:#1e40af;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap;margin-left:8px">{s.get("rakam","")}</div>
            </div>
            <div style="color:#475569;margin-top:8px;font-size:13px;line-height:1.6">{s.get("neden_onemli","")}</div>
            <div style="color:#7c2d12;font-style:italic;font-size:13px;margin-top:6px;padding-top:6px;border-top:1px dashed #e2e8f0">→ {s.get("etki","")}</div>
        </div>'''

    # Karar gündemi
    kararlar = ""
    for k in brifing.get("karar_gundemi", []):
        kararlar += f'''
        <div style="padding:16px;margin:10px 0;background:#fffbeb;border-left:5px solid #f59e0b;border-radius:6px">
            <div style="font-weight:700;color:#78350f;font-size:15px;margin-bottom:10px">⚖️ {k.get("konu","")}</div>
            <table style="width:100%;font-size:13px;border-collapse:collapse">
                <tr><td style="padding:4px 8px 4px 0;color:#64748b;width:110px"><b>Seçenek A</b></td><td style="color:#334155">{k.get("seçenek_a","")}</td></tr>
                <tr><td style="padding:4px 8px 4px 0;color:#64748b"><b>Seçenek B</b></td><td style="color:#334155">{k.get("seçenek_b","")}</td></tr>
            </table>
            <div style="background:#fef3c7;padding:10px;border-radius:4px;margin-top:10px;font-size:13px">
                <b style="color:#78350f">💡 Öneri:</b> {k.get("öneri","")}<br>
                <span style="color:#92400e;font-size:12px"><i>{k.get("gerekçe","")}</i></span>
            </div>
        </div>'''

    # Rakip radarı
    rakipler = ""
    for r in brifing.get("rakip_radari", []):
        rakipler += f'''
        <div style="padding:12px;margin:8px 0;background:#f0f9ff;border-left:4px solid #0284c7;border-radius:6px">
            <div style="font-weight:700;color:#0c4a6e">{r.get("rakip","")}</div>
            <div style="color:#334155;font-size:13px;margin:6px 0">{r.get("hamle","")}</div>
            <div style="color:#166534;font-size:13px;background:#dcfce7;padding:8px;border-radius:4px;margin-top:6px">
                <b>BİM için ders:</b> {r.get("bim_icin_ders","")}
            </div>
        </div>'''

    # Makro pusu
    makrolar = ""
    for m in brifing.get("makro_pusu", []):
        makrolar += f'''
        <div style="padding:12px;margin:8px 0;background:#faf5ff;border-left:4px solid #9333ea;border-radius:6px">
            <div style="display:flex;justify-content:space-between">
                <div style="font-weight:700;color:#581c87">{m.get("gösterge","")}</div>
                <div style="color:#7e22ce;font-weight:600">{m.get("veri","")}</div>
            </div>
            <div style="color:#4c1d95;font-size:13px;margin-top:6px">{m.get("yorum","")}</div>
            <div style="color:#166534;font-size:12px;margin-top:6px;padding-top:6px;border-top:1px dashed #c4b5fd">
                <b>Aksiyon:</b> {m.get("aksiyon","")}
            </div>
        </div>'''

    # Senaryolar
    senaryolar = ""
    for s in brifing.get("senaryolar", []):
        senaryolar += f'''
        <div style="padding:16px;margin:12px 0;background:white;border:1px solid #e2e8f0;border-radius:8px">
            <div style="font-weight:700;color:#0f172a;margin-bottom:12px;font-size:15px">🎯 {s.get("tetikleyici","")}</div>
            <table style="width:100%;font-size:13px;border-collapse:collapse">
                <tr><td style="color:#047857;padding:6px 10px 6px 0;width:110px;vertical-align:top"><b>✅ İyimser</b></td><td style="color:#334155;padding:6px 0">{s.get("iyimser","")}</td></tr>
                <tr><td style="color:#1d4ed8;padding:6px 10px 6px 0;vertical-align:top"><b>⚖️ Baz</b></td><td style="color:#334155;padding:6px 0">{s.get("baz","")}</td></tr>
                <tr><td style="color:#b91c1c;padding:6px 10px 6px 0;vertical-align:top"><b>⚠️ Kötümser</b></td><td style="color:#334155;padding:6px 0">{s.get("kotumser","")}</td></tr>
            </table>
            <div style="background:#eff6ff;padding:10px;border-radius:4px;margin-top:10px;font-size:12px;color:#1e40af">
                <b>🛡️ Hazırlık:</b> {s.get("hazırlık","")}
            </div>
        </div>'''

    # Saha nabzı
    saha = brifing.get("saha_nabzi", {})
    saha_html = f'''
    <div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:5px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:8px">🔍 Bugün Mağazada Ne Bakmalı?</div>
        <div style="color:#334155;font-size:13px;margin-bottom:10px">{saha.get("gozlem","")}</div>
        <div style="background:white;padding:10px;border-radius:4px;font-size:13px">
            <b style="color:#92400e">Mağaza müdürüne soru:</b> {saha.get("soru","")}<br>
            <span style="color:#64748b;font-size:12px;font-style:italic">{saha.get("beklenti","")}</span>
        </div>
    </div>'''

    # Haftalık pusula
    pusula = brifing.get("haftalik_pusula", "")

    # Uyarı
    uyari = brifing.get("uyari_seviyesi", "")

    # Haberler
    haber_html = ""
    for h in haberler[:6]:
        link = h.get("Link", "")
        baslik = f'<a href="{link}" style="color:#1e40af;text-decoration:none">{h["Başlık"]}</a>' if link else h["Başlık"]
        haber_html += f'''
        <div style="padding:12px;margin:6px 0;background:#f8fafc;border-left:3px solid #3b82f6;border-radius:4px">
            <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px">{h['Kategori']}</div>
            <div style="font-weight:600;color:#0f172a;margin:4px 0;font-size:14px">{baslik}</div>
            <div style="color:#475569;font-size:12px;line-height:1.5">{h['Özet'][:200]}</div>
        </div>'''

    return f'''<html><body style="font-family:'Segoe UI',Arial,sans-serif;max-width:780px;margin:auto;background:#f1f5f9;padding:20px;color:#0f172a;line-height:1.5">

    <!-- BAŞLIK -->
    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);color:white;padding:32px;border-radius:14px">
        <div style="font-size:11px;opacity:0.7;letter-spacing:3px">CEO PUSULASI · BİM STRATEJİ BRİFİNGİ</div>
        <h1 style="margin:8px 0 0 0;font-size:28px;font-weight:700">{tarih}</h1>
        <div style="margin-top:16px;padding:12px 16px;background:rgba(255,255,255,0.1);border-radius:8px;border-left:4px solid #fbbf24">
            <div style="font-size:11px;opacity:0.8;letter-spacing:1px">BUGÜNÜN MANŞETİ</div>
            <div style="font-size:16px;font-weight:600;margin-top:4px">{brifing.get("manset","")}</div>
        </div>
    </div>

    <!-- UYARI SEVİYESİ -->
    <div style="background:{bg};border:2px solid {renk};padding:14px;border-radius:10px;margin-top:14px;text-align:center">
        <span style="font-size:11px;color:{renk};letter-spacing:2px;font-weight:700">DURUM</span>
        <div style="font-size:15px;font-weight:700;color:{renk};margin-top:4px">{uyari}</div>
    </div>

    <!-- HAFTALIK PUSULA -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🧭 Haftalık Pusula</h3>
        <div style="font-size:11px;color:#64748b;letter-spacing:1px">{tema[0]}</div>
        <div style="color:#334155;font-size:14px;margin-top:8px;line-height:1.7">{pusula}</div>
    </div>

    <!-- SABAH 60 SANİYE -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⏱️ Sabah 60 Saniye</h3>
        {sinyaller}
    </div>

    <!-- KARAR GÜNDEMİ -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⚖️ Bugünün Karar Gündemi</h3>
        {kararlar}
    </div>

    <!-- RAKİP RADARI -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎯 Rakip Radarı</h3>
        {rakipler}
    </div>

    <!-- MAKRO PUSU -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📡 Makro Pusu</h3>
        {makrolar}
    </div>

    <!-- SENARYOLAR -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎲 Senaryo Laboratuvarı</h3>
        {senaryolar}
    </div>

    <!-- SAHA NABZI -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🏪 Saha Nabzı</h3>
        {saha_html}
    </div>

    <!-- GÜNÜN TERİMİ -->
    <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:white;padding:20px;margin-top:14px;border-radius:12px">
        <div style="font-size:11px;opacity:0.7;letter-spacing:2px">GÜNÜN TERİMİ</div>
        <div style="font-size:20px;font-weight:700;margin:6px 0">{terim[0]}</div>
        <div style="font-size:14px;opacity:0.9;line-height:1.6">{terim[1]}</div>
        <div style="background:rgba(59,130,246,0.2);padding:12px;border-radius:6px;margin-top:12px;border-left:3px solid #60a5fa;font-size:13px">
            <b>💡 BİM için anlamı:</b> {terim[2]}
        </div>
    </div>

    <!-- VERİ TABLOLARI -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        {df_to_table(tr_df, "🇹🇷 Türkiye Perakendecileri")}
        {df_to_table(abd_df, "🌍 ABD Devleri (SEC EDGAR - Canlı)")}
        {df_to_table(makro_df, "📈 Makro Göstergeler (Dünya Bankası)")}
    </div>

    <!-- HABERLER -->
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📰 Günün Haberleri</h3>
        {haber_html}
    </div>

    <!-- ALT BİLGİ -->
    <div style="background:#0f172a;color:#94a3b8;padding:20px;margin-top:14px;border-radius:12px;font-size:11px;text-align:center;line-height:1.7">
        <b style="color:#e2e8f0">CEO PUSULASI</b> · Otomatik oluşturulmuştur<br>
        Kaynaklar: SEC EDGAR · Dünya Bankası · RSS · Groq AI<br>
        📎 Detaylı veriler Excel ektedir<br>
        <span style="color:#64748b;font-size:10px">Bu brifing yapay zekâ destekli analizdir. Kritik kararlar öncesi resmî verileri (TÜİK, TCMB, KAP) doğrulayın.</span>
    </div>

    </body></html>'''


# ============================================================
# BÖLÜM 5: EXCEL
# ============================================================
def excel_olustur(abd_df, tr_df, makro_df, haberler, brifing):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as w:
        if not abd_df.empty:
            abd_df.to_excel(w, sheet_name="ABD Rakipler", index=False)
        tr_df.to_excel(w, sheet_name="Turkiye Perakende", index=False)
        if not makro_df.empty:
            makro_df.to_excel(w, sheet_name="Makro", index=False)
        if brifing.get("sabah_60_saniye"):
            pd.DataFrame(brifing["sabah_60_saniye"]).to_excel(w, sheet_name="60 Saniye", index=False)
        if brifing.get("karar_gundemi"):
            pd.DataFrame(brifing["karar_gundemi"]).to_excel(w, sheet_name="Karar Gundemi", index=False)
        if brifing.get("rakip_radari"):
            pd.DataFrame(brifing["rakip_radari"]).to_excel(w, sheet_name="Rakip Radari", index=False)
        if haberler:
            pd.DataFrame(haberler).drop(columns=["İngilizce"], errors="ignore").to_excel(
                w, sheet_name="Haberler", index=False)
    output.seek(0)
    return output


# ============================================================
# BÖLÜM 6: MAIL
# ============================================================
def mail_gonder(html_body, excel_data):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"🧭 CEO Pusulası — {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"] = MAIL_USER
    msg["To"] = MAIL_TO
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    if excel_data:
        ek = MIMEApplication(excel_data.read(), _subtype="xlsx")
        ek.add_header("Content-Disposition", "attachment",
                      filename=f"ceo_pusulasi_{datetime.now().strftime('%Y%m%d')}.xlsx")
        msg.attach(ek)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(MAIL_USER, MAIL_PASS)
        s.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
    print("✅ Mail gönderildi.")


# ============================================================
# ANA AKIŞ
# ============================================================
def main():
    print("=" * 60)
    print(f"🧭 CEO PUSULASI — {datetime.now()}")
    print("=" * 60)

    toplayici = VeriToplayici()
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    tema = HAFTANIN_TEMASI.get(datetime.now().weekday(), HAFTANIN_TEMASI[0])
    terim = gunun_terimi()

    print("[1/6] ABD rakipler (SEC EDGAR)...")
    abd_df = toplayici.abd_sirketleri()

    print("[2/6] Türkiye perakende...")
    tr_df = toplayici.turkiye_sirketleri()

    print("[3/6] Makro göstergeler (Dünya Bankası)...")
    makro_df = toplayici.makro_gostergeler()

    print("[4/6] Haberler toplanıyor...")
    haberler = toplayici.rss_haberleri()

    print("[5/6] İngilizce haberler Türkçeye çevriliyor...")
    haberler = haberleri_turkceye_cevir(haberler, client)

    print("[6/6] CEO brifingi üretiliyor (Groq)...")
    brifing = ceo_brifingi_uret(abd_df, tr_df, makro_df, haberler, terim, tema, client)

    print("📧 HTML hazırlanıyor...")
    html_body = brifing_html(brifing, abd_df, tr_df, makro_df, haberler, terim, tema)

    print("📊 Excel hazırlanıyor...")
    try:
        excel_data = excel_olustur(abd_df, tr_df, makro_df, haberler, brifing)
    except Exception as e:
        print(f"Excel hatası: {e}")
        excel_data = None

    print("📤 Mail gönderiliyor...")
    mail_gonder(html_body, excel_data)
    print("✅ Tamamlandı.")


if __name__ == "__main__":
    main()
