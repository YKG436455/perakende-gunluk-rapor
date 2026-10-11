#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BİM SAMSUN — CEO STRATEJİK BRİFİNG
====================================
Bölge Müdürü için her sabah 07:00'de otomatik brifing.
Yerel + ulusal + global + sektörel + teknolojik + stratejik tüm boyutlar.
"""

import os, re, time, json, smtplib, calendar
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from io import BytesIO

import feedparser, requests, pandas as pd
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")
GROQ_MODEL = "llama-3.3-70b-versatile"
SEC_HEADERS = {"User-Agent": "BIM-Samsun-Briefing/1.0 (contact@example.com)"}

# ============================================================
# HABER KAYNAKLARI (Türkçe/İngilizce işaretli)
# ============================================================
def google_news_url(q):
    return f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"

KAYNAKLAR = {
    "🏪 Samsun & Bölge": [
        ("Google News - Samsun", google_news_url("Samsun"), False),
        ("Google News - Samsun Ekonomi", google_news_url("Samsun+ekonomi+OR+ticaret+OR+perakende"), False),
    ],
    "🇹🇷 Türkiye Ekonomi": [
        ("AA Ekonomi", "https://www.aa.com.tr/tr/rss/default?cat=ekonomi", False),
        ("Bloomberg HT", "https://www.bloomberght.com/rss", False),
        ("Dünya Gazetesi", "https://www.dunya.com/rss", False),
    ],
    "📰 Türkiye Gündem": [
        ("AA Güncel", "https://www.aa.com.tr/tr/rss/default?cat=guncel", False),
    ],
    "🌍 Dünya Ekonomi": [
        ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", True),
        ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews", True),
    ],
    "🌐 Dünya Gündem": [
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml", True),
    ],
    "🛒 Perakende": [
        ("Retail Dive", "https://www.retaildive.com/feeds/news/", True),
        ("Perakende Sektörü", "https://perakendesektoru.com/feed/", False),
        ("Retail Gazette", "https://retailgazette.com/feed/", True),
    ],
    "🤖 Teknoloji": [
        ("MIT Technology Review", "https://www.technologyreview.com/feed/", True),
    ],
}

# ============================================================
# DÜNYA PERAKENDECİLERİ ATLASI (statik, güvenilir veri)
# ============================================================
DUNYA_ATLASI = [
    {"Şirket": "Walmart", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr",
     "Dil": "İngilizce", "Geçim": "Hizmet, teknoloji, üretim",
     "Mağaza": "10.500+", "Strateji": "Ölçek + lojistik + retail media"},
    {"Şirket": "Amazon", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr",
     "Dil": "İngilizce", "Geçim": "E-ticaret, bulut (AWS)",
     "Mağaza": "Dijital + Whole Foods", "Strateji": "Otomasyon + AI + lojistik"},
    {"Şirket": "Costco", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr",
     "Dil": "İngilizce", "Geçim": "Üyelik modeli",
     "Mağaza": "870+", "Strateji": "Üyelik sadakati + düşük marj"},
    {"Şirket": "Aldi", "Ülke": "🇩🇪 Almanya", "Nüfus": "84 mn", "GSYH": "$4,6 tr",
     "Dil": "Almanca", "Geçim": "Üretim, ihracat, mühendislik",
     "Mağaza": "7.000+ (Almanya)", "Strateji": "%90 özel marka, maliyet disiplini"},
    {"Şirket": "Lidl", "Ülke": "🇩🇪 Almanya", "Nüfus": "84 mn", "GSYH": "$4,6 tr",
     "Dil": "Almanca", "Geçim": "Üretim, ihracat",
     "Mağaza": "12.000+ (global)", "Strateji": "Mağaza verimliliği"},
    {"Şirket": "Carrefour", "Ülke": "🇫🇷 Fransa", "Nüfus": "68 mn", "GSYH": "$3,1 tr",
     "Dil": "Fransızca", "Geçim": "Hizmet, turizm, tarım",
     "Mağaza": "14.000+ (global)", "Strateji": "Omnichannel + dijital dönüşüm"},
    {"Şirket": "Tesco", "Ülke": "🇬🇧 İngiltere", "Nüfus": "68 mn", "GSYH": "$3,3 tr",
     "Dil": "İngilizce", "Geçim": "Finans, hizmet, teknoloji",
     "Mağaza": "4.000+", "Strateji": "Veri analitiği + müşteri sadakati"},
]

# ============================================================
# SÖZLÜK (20 terim, BİM'e özel yorumlu)
# ============================================================
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza büyümesi. BİM H1 2026: +%37,3 — fiyat kaynaklı.",
     "BİM'de LFL'in çoğu fiyat artışından. Gerçek hacim büyümesi yoksa sürdürülemez."),
    ("Brüt Kâr Marjı", "Satıştan malın maliyeti düşüldükten sonra kalan oran. BİM: %19,1.",
     "Özel marka payını 5 puan artırmak brüt marjı ~1 puan yükseltir. En kolay kâr kaldıracı."),
    ("FAVÖK (EBITDA)", "Faiz/Vergi/Amortisman öncesi kâr. Nakit üretimi. BİM: %5,4.",
     "Türkiye perakendesinde %5+ dünya ortalaması üstü. Kıymetini bilin."),
    ("Özel Marka", "Marketin kendi markası. BİM: %55, ALDI: %90.",
     "ALDI modelinde %90 mümkün. BİM için 5 yıllık hedef %65 olmalı."),
    ("Stok Devir Hızı", "Stok yılda kaç kez yenileniyor. A101: 14, ALDI: 12.",
     "Her 1 puan artış nakit akışına 1-2 mr TL katkı."),
    ("Fire Oranı", "Bozulma/kayıp oranı. Costco: %0,4, sektör: %1,5.",
     "BİM'in taze ürün genişlemesi fire riski getirir. Mağaza bazlı takip şart."),
    ("TMS 29", "Enflasyon muhasebesi. Türkiye'de zorunlu.",
     "Nakit kâr ≠ Muhasebe kârı. BİM Q2'de parasal kazanç var."),
    ("CAPEX", "Uzun vadeli yatırım. BİM: ~%2,5.",
     "BİM son 5 yılda yavaşladı. Yeni format için CAPEX artışı gerekebilir."),
    ("Retail Media", "Raf/uygulama reklam geliri. Walmart: +%38.",
     "BİM'in bu alanda sıfır geliri var. 20 pilot mağaza = yıllık 500 mn TL potansiyel."),
    ("Ajan Tabanlı Ticaret", "AI'ların müşteri adına alışverişi. 2030: 3-5 tr $.",
     "BİM uygulaması 5 yıl içinde AI ajanı kabul etmezse genç müşteri kaybeder."),
    ("ROCE", "Sermaye getirisi. Tesco: %15,2.",
     "BİM'in ROCE'si muhtemelen %25+. Her TL ne kadar verimli kullanılıyor?"),
    ("NPS", "Net Tavsiye Skoru. Tesco: 33.",
     "BİM NPS'i ölçmüyor. Yıllık 10.000 müşteri anketi şart."),
    ("Omnichannel", "Mağaza + online birlikte. Migros: 2.520 online mağaza.",
     "BİM online'a girmedi. Strateji mi, eksiklik mi? 2026 cevap yılı."),
    ("Hard Discount", "Az çeşit, düşük fiyat, sade mağaza. BİM, A101, ŞOK.",
     "Türkiye'de hard discount payı %60+. Zafer ama premium segment boş."),
    ("SKU Yönetimi", "Ürün çeşidi. BİM: ~1.000, Migros: ~10.000.",
     "BİM'in 1.000 SKU disiplini kârlılığın sırrı. Taze üründe korunabilir mi?"),
    ("TEPE", "TEPAV Perakende Güven Endeksi.",
     "TEPE pozitife dönerse tüketici harcaması artar. BİM buna hazır mı?"),
    ("Müşteri Trafiği", "Mağazaya giren müşteri. BİM: +%0,4.",
     "Trafik artmıyor, sepet büyüyor. Bu fiyat kaynaklı — gerçek büyüme değil."),
    ("Ortalama Sepet", "Satış / işlem sayısı.",
     "BİM'de sepet büyüyor ama içi küçülüyor. Tüketici daha az ürün alıyor."),
    ("Raf Bulunurluğu", "İstenen ürünün rafta olma oranı. İdeal: %97-99.",
     "BİM'in sadelik avantajı var ama taze üründe düşebilir. Gizli müşteri şart."),
    ("Stoksuz Kalma", "Talep varken rafın boş olması. İdeal: <%3.",
     "Her %1 stoksuz kalma = %0,5 ciro kaybı. Yıllık 2-3 mr TL demek."),
]

# ============================================================
# HAFTALIK TEMA
# ============================================================
HAFTANIN_TEMASI = {
    0: ("Haftalık Rakip Karşılaştırması", "Mağaza başına ciro ve kârlılık"),
    1: ("Makro Riskler ve Tüketici", "Enflasyon, işsizlik, tüketim eğilimi"),
    2: ("Dijital ve Retail Media", "E-ticaret, uygulama, reklam geliri"),
    3: ("Özel Marka ve Kâr Kalitesi", "Marj yönetimi, tedarik, fiyatlama"),
    4: ("Rekabet ve Düzenleyici", "Rekabet Kurumu, mevzuat, M&A"),
    5: ("Teknoloji ve AI", "AI ajanlar, otomasyon, veri"),
    6: ("Haftalık Değerlendirme", "Geçen hafta + gelecek hafta"),
}

# ============================================================
# VERİ TOPLAMA
# ============================================================
def temizle(m):
    m = re.sub(r"<[^>]+>", " ", m or "")
    return re.sub(r"\s+", " ", m).strip()

def haber_topla():
    sonuc = {}
    for kategori, kaynaklar in KAYNAKLAR.items():
        kayitlar = []
        for ad, url, ing in kaynaklar:
            try:
                feed = feedparser.parse(url, agent="Mozilla/5.0")
                for e in feed.entries[:5]:
                    tarih = e.get("published_parsed") or e.get("updated_parsed")
                    if not tarih:
                        continue
                    kayitlar.append({
                        "Kategori": kategori,
                        "Kaynak": ad,
                        "Başlık": temizle(e.get("title", "")),
                        "Özet": temizle(e.get("summary", ""))[:400],
                        "Link": e.get("link", ""),
                        "İngilizce": ing,
                        "Tarih": datetime.fromtimestamp(
                            calendar.timegm(tarih), tz=timezone.utc),
                    })
            except Exception as ex:
                print(f"RSS hata ({ad}): {ex}")
        # En yeni 6
        kayitlar.sort(key=lambda x: x["Tarih"], reverse=True)
        sonuc[kategori] = kayitlar[:6]
    return sonuc

def sec_verisi(cik, ad):
    try:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        r = requests.get(url, headers=SEC_HEADERS, timeout=30)
        if r.status_code != 200:
            return {"Şirket": ad, "Gelir (mr $)": "-", "Net Kâr (mr $)": "-", "Dönem": "-"}
        f = r.json().get("facts", {}).get("us-gaap", {})
        def sv(k):
            v = f.get(k, {}).get("units", {}).get("USD", [])
            return (round(v[-1]["val"]/1e9, 2), v[-1].get("end", "?")) if v else (None, None)
        g, d = sv("Revenues")
        if g is None: g, d = sv("RevenueFromContractWithCustomerExcludingAssessedTax")
        nk, _ = sv("NetIncomeLoss")
        return {"Şirket": ad, "Gelir (mr $)": g or "-", "Net Kâr (mr $)": nk or "-", "Dönem": d or "-"}
    except Exception as e:
        print(f"SEC hata ({ad}): {e}")
        return {"Şirket": ad, "Gelir (mr $)": "-", "Net Kâr (mr $)": "-", "Dönem": "-"}

def abd_sirketleri():
    s = [("0000104169","Walmart"),("0001018724","Amazon"),("0000909832","Costco"),
         ("0000056873","Kroger"),("0001646972","Albertsons"),("0001611983","Target")]
    return pd.DataFrame([sec_verisi(c,a) for c,a in s])

def turkiye_sirketleri():
    return pd.DataFrame({
        "Firma": ["BİM", "Migros", "ŞOK", "A101", "CarrefourSA"],
        "Dönem": ["H1 2026", "Q2 2026", "H1 2026", "2025/12", "Q2 2026"],
        "Satış (mr TL)": ["449,7", "124,4", "167,8", "~280", "~68"],
        "Mağaza": ["14.851", "3.830", "11.175", "~13.000", "~700"],
        "LFL": ["+%37,3", "Negatif", "+%5", "-", "-"],
        "Net Kâr (mr TL)": ["+15,1", "-0,7", "-1,35", "-", "-"],
    })

def makro():
    g = {"NY.GDP.MKTP.KD.ZG":"GSYİH Büyümesi (%)","FP.CPI.TOTL.ZG":"Enflasyon (%)",
         "SL.UEM.TOTL.ZS":"İşsizlik (%)","NE.CON.PRVT.ZS":"Hane Tüketimi (%)"}
    r = []
    for k, a in g.items():
        try:
            url = f"https://api.worldbank.org/v2/country/TUR/indicator/{k}?format=json&per_page=1&date=2023:2026"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                d = resp.json()
                if len(d) > 1 and d[1] and d[1][0].get("value"):
                    r.append({"Gösterge": a, "Değer": f"{d[1][0]['value']:.1f}", "Yıl": d[1][0].get("date","")})
        except: pass
    return pd.DataFrame(r)

# ============================================================
# TÜRKÇE ÇEVİRİ (Sıkı)
# ============================================================
def turkce_mi(m):
    if not m or len(m) < 15: return False
    if any(c in m.lower() for c in "çğıöşü"): return True
    tr = ["ve","ile","için","bir","bu","da","de","yeni","yıl","satış","pazar","şirket","artış"]
    return sum(1 for k in tr if f" {k} " in f" {m.lower()} ") >= 2

def cevir(haber_dict, client):
    tum = []
    for kategori, kayitlar in haber_dict.items():
        for h in kayitlar:
            tum.append(h)
    cevrilecek = [h for h in tum if h.get("İngilizce")]
    if not cevrilecek or not client:
        return {k: [h for h in v if not h.get("İngilizce") or turkce_mi(h["Başlık"])] for k, v in haber_dict.items()}
    # 3'lü gruplar
    for i in range(0, len(cevrilecek), 3):
        grup = cevrilecek[i:i+3]
        metin = "\n\n".join([f"[{j}]\nBAŞLIK: {h['Başlık']}\nÖZET: {h['Özet'][:300]}" for j, h in enumerate(grup)])
        p = f"""İngilizce perakende/ekonomi haberlerini profesyonel Türkçeye çevir. Şirket isimlerini bırak. JSON döndür:
{{"ceviriler":[{{"id":0,"baslik":"...","ozet":"..."}}]}}

{metin}"""
        for deneme in range(2):
            try:
                y = client.chat.completions.create(
                    messages=[{"role":"user","content":p}],
                    model=GROQ_MODEL,
                    response_format={"type":"json_object"},
                    max_tokens=1800, temperature=0.1)
                s = json.loads(y.choices[0].message.content)
                for c in s.get("ceviriler", []):
                    j = c.get("id")
                    if j is not None and 0 <= j < len(grup):
                        grup[j]["Başlık"] = c.get("baslik", grup[j]["Başlık"])
                        grup[j]["Özet"] = c.get("ozet", grup[j]["Özet"])
                        grup[j]["İngilizce"] = False
                break
            except Exception as e:
                print(f"Çeviri deneme {deneme+1}: {e}")
                time.sleep(2)
    # Filtrele: İngilizce kalanları at
    return {k: [h for h in v if not h.get("İngilizce") or turkce_mi(h["Başlık"])] for k, v in haber_dict.items()}

# ============================================================
# CEO BRİFİNGİ (AI)
# ============================================================
def ceo_brifing(abd_df, tr_df, makro_df, haberler, terim, tema, client):
    if not client:
        return _bos()
    # Haberleri düzleştir
    tum_haber = []
    for k, v in haberler.items():
        for h in v[:3]:
            tum_haber.append(f"- [{k}] {h['Başlık']}: {h['Özet'][:120]}")
    haber_m = "\n".join(tum_haber[:30])

    sistem = """Sen BİM Samsun Bölge Müdürü'nün baş strateji danışmanısın.
Görev: Sabah 07:00'de 60 saniyede okunacak NET, KARAR ODAKLI brifing.

FELSEFEN:
- "Ne oldu?" değil, "Bu BİM Samsun için ne demek, ne yapmalıyım?"
- Yerel gelişmeleri (Samsun) mutlaka BİM operasyonuna bağla.
- Rakamları BİM'e göre yorumla. "Walmart %38 büyüdü" değil,
  "BİM'in retail media fırsatı yıllık 500 mn TL olabilir" de.
- Her bölüm bir karar önerisiyle bitsin.

KESİN KURALLAR:
1. Sadece verilen verilere dayan, uydurma.
2. ÇIKTININ TAMAMI TÜRKÇE OLSUN. İngilizce tek kelime bile kullanma.
   (Şirket isimleri: Walmart, Amazon vb. hariç.)
3. Yorumlar "olabilir/muhtemel/önerilir" diliyle.
4. JSON döndür.

JSON ŞEMASI:
{
  "manset": "Bugünün tek cümlelik kritik mesajı",
  "sabah_60_saniye": [
    {"sinyal": "Kısa başlık", "rakam": "Somut sayı", "neden_onemli": "BİM Samsun için", "etki": "Olası etki"}
  ],
  "samsun_odak": {
    "gelisme": "Samsun/bölge ile ilgili öne çıkan",
    "bim_etkisi": "BİM Samsun operasyonuna etki",
    "aksiyon": "Somut öneri"
  },
  "karar_gundemi": [
    {"konu": "...", "seçenek_a": "...", "seçenek_b": "...", "öneri": "...", "gerekçe": "..."}
  ],
  "rakip_radari": [
    {"rakip": "...", "hamle": "...", "bim_icin_ders": "..."}
  ],
  "makro_pusu": [
    {"gösterge": "...", "veri": "...", "yorum": "...", "aksiyon": "..."}
  ],
  "senaryolar": [
    {"tetikleyici": "...", "iyimser": "...", "baz": "...", "kotumser": "...", "hazırlık": "..."}
  ],
  "saha_nabzi": {"gozlem": "...", "soru": "...", "beklenti": "..."},
  "haftalik_pusula": "Bu haftanın stratejik odağı (1 paragraf)",
  "uyari_seviyesi": "YEŞİL | SARI | KIRMIZI — gerekçesiyle"
}"""

    k = f"""Bugün: {datetime.now().strftime('%d.%m.%Y %A')}
Bölge: SAMSUN (BİM)
Haftanın teması: {tema[0]}
Günün terimi: {terim[0]}

=== ABD RAKİPLER (SEC) ===
{abd_df.to_string(index=False)}

=== TÜRKİYE PERAKENDECİLERİ ===
{tr_df.to_string(index=False)}

=== MAKRO (Dünya Bankası) ===
{makro_df.to_string(index=False) if not makro_df.empty else 'Veri yok'}

=== GÜNÜN HABERLERİ (Kategori bazlı) ===
{haber_m}

CEO brifingini JSON olarak üret."""

    try:
        y = client.chat.completions.create(
            messages=[{"role":"system","content":sistem},{"role":"user","content":k}],
            model=GROQ_MODEL, response_format={"type":"json_object"},
            max_tokens=5500, temperature=0.4)
        return json.loads(y.choices[0].message.content)
    except Exception as e:
        print(f"AI hata: {e}")
        return _bos()

def _bos():
    return {"manset":"Brifing üretilemedi.","sabah_60_saniye":[],"samsun_odak":{"gelisme":"","bim_etkisi":"","aksiyon":""},
            "karar_gundemi":[],"rakip_radari":[],"makro_pusu":[],"senaryolar":[],
            "saha_nabzi":{"gozlem":"","soru":"","beklenti":""},"haftalik_pusula":"","uyari_seviyesi":"SARI"}

def gunun_terimi():
    return SOZLUK[datetime.now().timetuple().tm_yday % len(SOZLUK)]

# ============================================================
# HTML ÜRETİCİ
# ============================================================
def df_table(df, baslik):
    if df.empty: return f"<p><em>{baslik}: veri yok.</em></p>"
    h = f'<h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:22px">{baslik}</h3>'
    h += '<table style="border-collapse:collapse;width:100%;font-size:12px;font-family:Segoe UI,Arial">'
    h += '<thead><tr style="background:#1e293b;color:white">'
    for c in df.columns: h += f'<th style="padding:8px;text-align:left;border:1px solid #334155">{c}</th>'
    h += '</tr></thead><tbody>'
    for i, row in df.iterrows():
        bg = "#f8fafc" if i % 2 == 0 else "white"
        h += f'<tr style="background:{bg}">'
        for v in row: h += f'<td style="padding:6px;border:1px solid #e2e8f0">{v}</td>'
        h += '</tr>'
    return h + '</tbody></table>'

def uyari_renk(s):
    s = (s or "").upper()
    if "KIRMIZI" in s: return "#dc2626", "#fee2e2"
    if "SARI" in s: return "#d97706", "#fef3c7"
    return "#16a34a", "#dcfce7"

def html_uret(br, abd_df, tr_df, makro_df, haberler, terim, tema):
    tarih = datetime.now().strftime("%d.%m.%Y %A")
    renk, bg = uyari_renk(br.get("uyari_seviyesi",""))

    # Sinyaller
    sinyaller = "".join([f'''
    <div style="padding:14px;margin:10px 0;background:white;border-left:5px solid #3b82f6;border-radius:6px">
        <div style="display:flex;justify-content:space-between;align-items:start;gap:10px">
            <div style="font-weight:700;color:#0f172a;font-size:15px">{s.get("sinyal","")}</div>
            <div style="background:#eff6ff;color:#1e40af;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap">{s.get("rakam","")}</div>
        </div>
        <div style="color:#475569;margin-top:8px;font-size:13px;line-height:1.6">{s.get("neden_onemli","")}</div>
        <div style="color:#7c2d12;font-style:italic;font-size:13px;margin-top:6px;padding-top:6px;border-top:1px dashed #e2e8f0">→ {s.get("etki","")}</div>
    </div>''' for s in br.get("sabah_60_saniye",[])])

    # Samsun
    so = br.get("samsun_odak",{})
    samsun_html = f'''
    <div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:5px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:10px">🏪 Samsun & Bölge Odağı</div>
        <div style="color:#334155;font-size:13px;margin-bottom:10px"><b>Gelişme:</b> {so.get("gelisme","")}</div>
        <div style="background:white;padding:10px;border-radius:4px;font-size:13px;margin-bottom:8px">
            <b style="color:#92400e">BİM Samsun'a etkisi:</b> {so.get("bim_etkisi","")}
        </div>
        <div style="background:#dcfce7;padding:10px;border-radius:4px;font-size:13px">
            <b style="color:#166534">Öneri:</b> {so.get("aksiyon","")}
        </div>
    </div>'''

    # Kararlar
    kararlar = "".join([f'''
    <div style="padding:16px;margin:10px 0;background:#fffbeb;border-left:5px solid #f59e0b;border-radius:6px">
        <div style="font-weight:700;color:#78350f;font-size:15px;margin-bottom:10px">⚖️ {k.get("konu","")}</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="padding:4px 8px 4px 0;color:#64748b;width:110px"><b>Seçenek A</b></td><td style="color:#334155">{k.get("seçenek_a","")}</td></tr>
            <tr><td style="padding:4px 8px 4px 0;color:#64748b"><b>Seçenek B</b></td><td style="color:#334155">{k.get("seçenek_b","")}</td></tr>
        </table>
        <div style="background:#fef3c7;padding:10px;border-radius:4px;margin-top:10px;font-size:13px">
            <b>💡 Öneri:</b> {k.get("öneri","")}<br>
            <span style="color:#92400e;font-size:12px"><i>{k.get("gerekçe","")}</i></span>
        </div>
    </div>''' for k in br.get("karar_gundemi",[])])

    # Rakipler
    rakipler = "".join([f'''
    <div style="padding:12px;margin:8px 0;background:#f0f9ff;border-left:4px solid #0284c7;border-radius:6px">
        <div style="font-weight:700;color:#0c4a6e">{r.get("rakip","")}</div>
        <div style="color:#334155;font-size:13px;margin:6px 0">{r.get("hamle","")}</div>
        <div style="color:#166534;font-size:13px;background:#dcfce7;padding:8px;border-radius:4px;margin-top:6px">
            <b>BİM için ders:</b> {r.get("bim_icin_ders","")}
        </div>
    </div>''' for r in br.get("rakip_radari",[])])

    # Makro
    makrolar = "".join([f'''
    <div style="padding:12px;margin:8px 0;background:#faf5ff;border-left:4px solid #9333ea;border-radius:6px">
        <div style="display:flex;justify-content:space-between">
            <div style="font-weight:700;color:#581c87">{m.get("gösterge","")}</div>
            <div style="color:#7e22ce;font-weight:600">{m.get("veri","")}</div>
        </div>
        <div style="color:#4c1d95;font-size:13px;margin-top:6px">{m.get("yorum","")}</div>
        <div style="color:#166534;font-size:12px;margin-top:6px;padding-top:6px;border-top:1px dashed #c4b5fd">
            <b>Aksiyon:</b> {m.get("aksiyon","")}
        </div>
    </div>''' for m in br.get("makro_pusu",[])])

    # Senaryolar
    senaryolar = "".join([f'''
    <div style="padding:16px;margin:12px 0;background:white;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-weight:700;color:#0f172a;margin-bottom:12px">🎯 {s.get("tetikleyici","")}</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="color:#047857;padding:6px 10px 6px 0;width:110px;vertical-align:top"><b>✅ İyimser</b></td><td style="color:#334155;padding:6px 0">{s.get("iyimser","")}</td></tr>
            <tr><td style="color:#1d4ed8;padding:6px 10px 6px 0;vertical-align:top"><b>⚖️ Baz</b></td><td style="color:#334155;padding:6px 0">{s.get("baz","")}</td></tr>
            <tr><td style="color:#b91c1c;padding:6px 10px 6px 0;vertical-align:top"><b>⚠️ Kötümser</b></td><td style="color:#334155;padding:6px 0">{s.get("kotumser","")}</td></tr>
        </table>
        <div style="background:#eff6ff;padding:10px;border-radius:4px;margin-top:10px;font-size:12px;color:#1e40af">
            <b>🛡️ Hazırlık:</b> {s.get("hazırlık","")}
        </div>
    </div>''' for s in br.get("senaryolar",[])])

    # Saha
    sh = br.get("saha_nabzi",{})
    saha_html = f'''
    <div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:5px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:8px">🔍 Bugün Mağazada</div>
        <div style="color:#334155;font-size:13px;margin-bottom:10px">{sh.get("gozlem","")}</div>
        <div style="background:white;padding:10px;border-radius:4px;font-size:13px">
            <b style="color:#92400e">Müdüre soru:</b> {sh.get("soru","")}<br>
            <span style="color:#64748b;font-size:12px;font-style:italic">{sh.get("beklenti","")}</span>
        </div>
    </div>'''

    # Dünya Atlası (HTML tablo)
    atlas_html = '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:10px">'
    atlas_html += '<thead><tr style="background:#1e293b;color:white">'
    for k in DUNYA_ATLASI[0].keys():
        atlas_html += f'<th style="padding:6px;border:1px solid #334155;text-align:left">{k}</th>'
    atlas_html += '</tr></thead><tbody>'
    for i, s in enumerate(DUNYA_ATLASI):
        bg = "#f8fafc" if i % 2 == 0 else "white"
        atlas_html += f'<tr style="background:{bg}">'
        for v in s.values():
            atlas_html += f'<td style="padding:5px;border:1px solid #e2e8f0">{v}</td>'
        atlas_html += '</tr>'
    atlas_html += '</tbody></table>'

    # Haberler (kategori bazlı)
    haber_html = ""
    for kategori, kayitlar in haberler.items():
        if not kayitlar: continue
        haber_html += f'<div style="margin-top:14px"><div style="font-weight:700;color:#1e40af;font-size:13px;margin-bottom:6px">{kategori}</div>'
        for h in kayitlar[:3]:
            link = h.get("Link","")
            baslik = f'<a href="{link}" style="color:#1e40af;text-decoration:none">{h["Başlık"]}</a>' if link else h["Başlık"]
            haber_html += f'''
            <div style="padding:10px;margin:6px 0;background:#f8fafc;border-left:3px solid #3b82f6;border-radius:4px">
                <div style="font-weight:600;color:#0f172a;font-size:13px">{baslik}</div>
                <div style="color:#64748b;font-size:11px;margin-top:4px">{h['Özet'][:180]}</div>
                <div style="color:#94a3b8;font-size:10px;margin-top:4px">{h['Kaynak']}</div>
            </div>'''
        haber_html += '</div>'

    return f'''<html><body style="font-family:'Segoe UI',Arial,sans-serif;max-width:820px;margin:auto;background:#f1f5f9;padding:20px;color:#0f172a;line-height:1.5">

    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);color:white;padding:32px;border-radius:14px">
        <div style="font-size:11px;opacity:0.7;letter-spacing:3px">BİM SAMSUN · CEO STRATEJİK BRİFİNG</div>
        <h1 style="margin:8px 0 0 0;font-size:26px;font-weight:700">{tarih}</h1>
        <div style="margin-top:16px;padding:12px 16px;background:rgba(255,255,255,0.1);border-radius:8px;border-left:4px solid #fbbf24">
            <div style="font-size:11px;opacity:0.8;letter-spacing:1px">BUGÜNÜN MANŞETİ</div>
            <div style="font-size:15px;font-weight:600;margin-top:4px">{br.get("manset","")}</div>
        </div>
    </div>

    <div style="background:{bg};border:2px solid {renk};padding:14px;border-radius:10px;margin-top:14px;text-align:center">
        <span style="font-size:11px;color:{renk};letter-spacing:2px;font-weight:700">DURUM</span>
        <div style="font-size:15px;font-weight:700;color:{renk};margin-top:4px">{br.get("uyari_seviyesi","")}</div>
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🧭 Haftalık Pusula</h3>
        <div style="font-size:11px;color:#64748b;letter-spacing:1px">{tema[0]}</div>
        <div style="color:#334155;font-size:14px;margin-top:8px;line-height:1.7">{br.get("haftalik_pusula","")}</div>
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⏱️ Sabah 60 Saniye</h3>
        {sinyaller}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        {samsun_html}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⚖️ Bugünün Karar Gündemi</h3>
        {kararlar}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎯 Rakip Radarı</h3>
        {rakipler}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📡 Makro Pusu</h3>
        {makrolar}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎲 Senaryo Laboratuvarı</h3>
        {senaryolar}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🏪 Saha Nabzı</h3>
        {saha_html}
    </div>

    <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:white;padding:20px;margin-top:14px;border-radius:12px">
        <div style="font-size:11px;opacity:0.7;letter-spacing:2px">GÜNÜN TERİMİ</div>
        <div style="font-size:20px;font-weight:700;margin:6px 0">{terim[0]}</div>
        <div style="font-size:14px;opacity:0.9;line-height:1.6">{terim[1]}</div>
        <div style="background:rgba(59,130,246,0.2);padding:12px;border-radius:6px;margin-top:12px;border-left:3px solid #60a5fa;font-size:13px">
            <b>💡 BİM için anlamı:</b> {terim[2]}
        </div>
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        {df_table(tr_df, "🇹🇷 Türkiye Perakendecileri")}
        {df_table(abd_df, "🌍 ABD Devleri (SEC)")}
        {df_table(makro_df, "📈 Makro (Dünya Bankası)")}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🌐 Dünya Perakendecileri Atlası</h3>
        {atlas_html}
    </div>

    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">
        <h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📰 Günün Haberleri (Kategori Bazlı)</h3>
        {haber_html}
    </div>

    <div style="background:#0f172a;color:#94a3b8;padding:20px;margin-top:14px;border-radius:12px;font-size:11px;text-align:center;line-height:1.7">
        <b style="color:#e2e8f0">BİM SAMSUN CEO BRİFİNG</b> · Otomatik oluşturulmuştur<br>
        Kaynaklar: SEC · Dünya Bankası · AA · Bloomberg HT · BBC · Reuters · Google News · Groq AI<br>
        📎 Excel eki: detaylı veriler<br>
        <span style="color:#64748b;font-size:10px">Yapay zekâ destekli analizdir. Kritik kararlar öncesi TÜİK, TCMB, KAP verilerini doğrulayın.</span>
    </div>

    </body></html>'''

# ============================================================
# EXCEL
# ============================================================
def excel(abd_df, tr_df, makro_df, haberler, br):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        if not abd_df.empty: abd_df.to_excel(w, sheet_name="ABD Rakipler", index=False)
        tr_df.to_excel(w, sheet_name="Turkiye Perakende", index=False)
        if not makro_df.empty: makro_df.to_excel(w, sheet_name="Makro", index=False)
        pd.DataFrame(DUNYA_ATLASI).to_excel(w, sheet_name="Dunya Atlasi", index=False)
        if br.get("sabah_60_saniye"): pd.DataFrame(br["sabah_60_saniye"]).to_excel(w, sheet_name="60 Saniye", index=False)
        if br.get("karar_gundemi"): pd.DataFrame(br["karar_gundemi"]).to_excel(w, sheet_name="Karar Gundemi", index=False)
        if br.get("rakip_radari"): pd.DataFrame(br["rakip_radari"]).to_excel(w, sheet_name="Rakip Radari", index=False)
        # Haberler tek sayfa
        tum = []
        for k, v in haberler.items():
            for h in v:
                tum.append({**h, "Kategori": k})
        if tum:
            pd.DataFrame(tum).drop(columns=["İngilizce"], errors="ignore").to_excel(w, sheet_name="Haberler", index=False)
    buf.seek(0); return buf

# ============================================================
# MAIL
# ============================================================
def mail(html, excel_data):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"🧭 BİM Samsun Brifing — {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"] = MAIL_USER; msg["To"] = MAIL_TO
    alt = MIMEMultipart("alternative"); alt.attach(MIMEText(html, "html", "utf-8")); msg.attach(alt)
    if excel_data:
        ek = MIMEApplication(excel_data.read(), _subtype="xlsx")
        ek.add_header("Content-Disposition", "attachment",
                      filename=f"bim_samsun_{datetime.now().strftime('%Y%m%d')}.xlsx")
        msg.attach(ek)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(MAIL_USER, MAIL_PASS)
        s.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
    print("✅ Mail gönderildi.")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print(f"BİM SAMSUN BRİFİNG — {datetime.now()}")
    print("=" * 60)
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    tema = HAFTANIN_TEMASI.get(datetime.now().weekday(), HAFTANIN_TEMASI[0])
    terim = gunun_terimi()

    print("[1/6] Haberler toplanıyor...")
    haberler = haber_topla()

    print("[2/6] İngilizce haberler çevriliyor...")
    haberler = cevir(haberler, client)

    print("[3/6] ABD rakipler (SEC)...")
    abd_df = abd_sirketleri()

    print("[4/6] Türkiye perakende...")
    tr_df = turkiye_sirketleri()

    print("[5/6] Makro (Dünya Bankası)...")
    makro_df = makro()

    print("[6/6] CEO brifingi (Groq)...")
    br = ceo_brifing(abd_df, tr_df, makro_df, haberler, terim, tema, client)

    print("📧 HTML + Excel hazırlanıyor...")
    html = html_uret(br, abd_df, tr_df, makro_df, haberler, terim, tema)
    try:
        ex = excel(abd_df, tr_df, makro_df, haberler, br)
    except Exception as e:
        print(f"Excel hatası: {e}"); ex = None

    print("📤 Mail gönderiliyor...")
    mail(html, ex)
    print("✅ Tamamlandı.")

if __name__ == "__main__":
    main()
