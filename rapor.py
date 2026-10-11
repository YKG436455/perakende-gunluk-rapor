#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BİM SAMSUN — CEO STRATEJİK BRİFİNG v3
- AI hataları mailde görünür
- Samsun için yerel kaynaklar
- AI çökerse şablon brifing
- Çeviri hatası da görünür
"""

import os, re, time, json, smtplib, calendar, traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

import feedparser, requests, pandas as pd
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

# Model fallback zinciri — biri çalışmazsa diğeri denenir
GROQ_MODELLERI = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]

# Global hata kaydı — mailde gösterilecek
HATALAR = []

def hata_yaz(msg):
    print(f"❌ {msg}")
    HATALAR.append(msg)

# ============================================================
# SAMSUN HABERLERİ — Yerel kaynaklara öncelik
# ============================================================
def gnews(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=tr&gl=TR&ceid=TR:tr"

KAYNAKLAR = {
    "🏪 Samsun & Bölge": [
        # Google News'te yerel kaynak domainleri ile sınırla
        ("Samsun (AVM/Market)", gnews('Samsun AVM OR market OR mağaza site:haberler.com OR site:samsunhaber.com OR site:hed ef.com.tr OR site:aksiyon.com.tr'), False),
        ("Samsun Ticaret/Sanayi", gnews('Samsun TSO OR "ticaret odası" OR "sanayi odası" OR ihracat OR istihdam -spor -maç -transfer'), False),
    ],
    "🇹🇷 Türkiye Ekonomi": [
        ("AA Ekonomi", "https://www.aa.com.tr/tr/rss/default?cat=ekonomi", False),
        ("Bloomberg HT", "https://www.bloomberght.com/rss", False),
        ("Ekonomim", "https://www.ekonomim.com/rss", False),
    ],
    "📰 Türkiye Gündem": [
        ("AA Güncel", "https://www.aa.com.tr/tr/rss/default?cat=guncel", False),
    ],
    "🌍 Dünya Ekonomi": [
        ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", True),
    ],
    "🛒 Perakende": [
        ("Retail Dive", "https://www.retaildive.com/feeds/news/", True),
        ("Perakende Sektörü", "https://perakendesektoru.com/feed/", False),
    ],
    "🤖 Teknoloji": [
        ("MIT Tech Review", "https://www.technologyreview.com/feed/", True),
    ],
}

# Yasaklı — sport/magazin/şiddet
YASAKLI = [
    "spor", "sport", "maç", "futbol", "basketbol", "voleybol", "tenis",
    "şampiyon", "gol", "lig", "turnuva", "transfermarkt", "samsunspor",
    "transfer", "teknik direktör", "puan", "kupası", "atletizm", "boks",
    "güreş", "olimpiyat", "stadyum", "taraftar", "derbi",
    "magazin", "ünlü", "dizi", "konser", "oyuncu", "sanatçı",
    "öldü", "cinayet", "yangın", "terör", "şehit", "patlama",
]

def yasakli_mi(baslik):
    b = baslik.lower()
    return any(k in b for k in YASAKLI)

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
                for e in feed.entries[:10]:
                    tarih = e.get("published_parsed") or e.get("updated_parsed")
                    if not tarih:
                        continue
                    baslik = temizle(e.get("title", ""))
                    if not baslik or yasakli_mi(baslik):
                        continue
                    kayitlar.append({
                        "Kategori": kategori, "Kaynak": ad, "Başlık": baslik,
                        "Özet": temizle(e.get("summary", ""))[:400],
                        "Link": e.get("link", ""), "İngilizce": ing,
                        "Tarih": datetime.fromtimestamp(calendar.timegm(tarih), tz=timezone.utc),
                    })
            except Exception as ex:
                hata_yaz(f"RSS hatası [{ad}]: {ex}")
        # Tekrarlıları temizle
        gorulen = set()
        benzersiz = []
        for h in sorted(kayitlar, key=lambda x: x["Tarih"], reverse=True):
            anahtar = re.sub(r"\W+", "", h["Başlık"].lower())[:50]
            if anahtar not in gorulen:
                gorulen.add(anahtar)
                benzersiz.append(h)
        sonuc[kategori] = benzersiz[:5]
        print(f"  {kategori}: {len(benzersiz)} haber")
    return sonuc

# ============================================================
# SEC + MAKRO
# ============================================================
def sec_verisi(cik, ad):
    try:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        r = requests.get(url, headers={"User-Agent": "BIM-Samsun/1.0"}, timeout=25)
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
# ÇEVİRİ — Hata görünür
# ============================================================
def cevir(haber_dict, client):
    tum = [h for v in haber_dict.values() for h in v]
    cevrilecek = [h for h in tum if h.get("İngilizce")]
    if not cevrilecek:
        return haber_dict
    if not client:
        hata_yaz("Çeviri atlandı: Groq client yok")
        return haber_dict
    for i in range(0, len(cevrilecek), 3):
        grup = cevrilecek[i:i+3]
        metin = "\n\n".join([f"[{j}]\nBAŞLIK: {h['Başlık']}\nÖZET: {h['Özet'][:200]}" for j, h in enumerate(grup)])
        p = f'JSON formatında cevap ver. İngilizce haberleri Türkçeye çevir: {{"ceviriler":[{{"id":0,"baslik":"...","ozet":"..."}}]}}\n\n{metin}'
        basarili = False
        for model in GROQ_MODELLERI:
            try:
                y = client.chat.completions.create(
                    messages=[{"role":"user","content":p}],
                    model=model, response_format={"type":"json_object"},
                    max_tokens=1500, temperature=0.1)
                s = json.loads(y.choices[0].message.content)
                for c in s.get("ceviriler", []):
                    j = c.get("id")
                    if j is not None and 0 <= j < len(grup):
                        grup[j]["Başlık"] = c.get("baslik", grup[j]["Başlık"])
                        grup[j]["Özet"] = c.get("ozet", grup[j]["Özet"])
                        grup[j]["İngilizce"] = False
                basarili = True
                break
            except Exception as e:
                print(f"Çeviri {model} hata: {e}")
                continue
        if not basarili:
            hata_yaz(f"Çeviri başarısız: {len(grup)} haber")
    return haber_dict

# ============================================================
# AI — HATA GÖRÜNÜR + MODEL FALLBACK
# ============================================================
def ai_cagir(client, sistem, kullanici, max_tok=2500):
    """Model fallback zinciri + 2 deneme/model."""
    if not client:
        hata_yaz("AI client yok")
        return None
    son_hata = "bilinmiyor"
    for model in GROQ_MODELLERI:
        for deneme in range(2):
            try:
                y = client.chat.completions.create(
                    messages=[
                        {"role":"system","content":sistem},
                        {"role":"user","content":kullanici}
                    ],
                    model=model,
                    response_format={"type":"json_object"},
                    max_tokens=max_tok,
                    temperature=0.15)
                icerik = y.choices[0].message.content
                return json.loads(icerik)
            except json.JSONDecodeError as e:
                son_hata = f"JSON parse: {str(e)[:100]}"
                print(f"  {model} JSON hatası: {e}")
                continue
            except Exception as e:
                son_hata = f"{type(e).__name__}: {str(e)[:150]}"
                print(f"  {model} hata: {son_hata}")
                time.sleep(2)
    hata_yaz(f"AI tüm modellerde başarısız. Son: {son_hata}")
    return None

def ai_core(client, abd_df, tr_df, makro_df, haber_m, tema, terim):
    sistem = """Sen BİM Samsun Bölge Müdürü'nün strateji danışmanısın.
Çıktı TAMAMEN TÜRKÇE olmalı. Şirket isimleri hariç İngilizce kelime kullanma.

JSON formatında cevap ver:
{"manset":"tek cümle","sabah_60_saniye":[{"sinyal":"","rakam":"","neden_onemli":"","etki":""}],"haftalik_pusula":"1 paragraf","uyari_seviyesi":"YEŞİL veya SARI veya KIRMIZI — gerekçesi"}"""
    k = f"""Tarih: {datetime.now().strftime('%d.%m.%Y')} | Bölge: SAMSUN
Tema: {tema[0]}

ABD: {abd_df.to_string(index=False)}
TR: {tr_df.to_string(index=False)}
Makro: {makro_df.to_string(index=False) if not makro_df.empty else 'Yok'}

HABERLER:
{haber_m}

3 sinyal + manşet + haftalık pusula + uyarı seviyesi. JSON döndür."""
    r = ai_cagir(client, sistem, k, 2000)
    return r or {"manset":"AI çöktü — bkz. hata raporu","sabah_60_saniye":[],"haftalik_pusula":"","uyari_seviyesi":"SARI — AI hatası"}

def ai_strateji(client, tr_df, haber_m, terim):
    sistem = """BİM Samsun strateji danışmanı. Türkçe, karar odaklı.
JSON döndür: {"karar_gundemi":[{"konu":"","seçenek_a":"","seçenek_b":"","öneri":"","gerekçe":""}],"rakip_radari":[{"rakip":"","hamle":"","bim_icin_ders":""}],"makro_pusu":[{"gösterge":"","veri":"","yorum":"","aksiyon":""}]}"""
    k = f"""TR Rakipler: {tr_df.to_string(index=False)}

HABERLER:
{haber_m}

2-3 karar + 2-3 rakip + 2-3 makro. JSON döndür."""
    r = ai_cagir(client, sistem, k, 2500)
    return r or {"karar_gundemi":[],"rakip_radari":[],"makro_pusu":[]}

def ai_yerel(client, samsun_haber, terim):
    sistem = """BİM Samsun strateji danışmanı. Türkçe.
Samsun haberleri BİM operasyonuna nasıl yansır? Somut öneri.
JSON döndür: {"samsun_odak":{"gelisme":"","bim_etkisi":"","aksiyon":""},"senaryolar":[{"tetikleyici":"","iyimser":"","baz":"","kotumser":"","hazırlık":""}],"saha_nabzi":{"gozlem":"","soru":"","beklenti":""}}"""
    k = f"""Bölge: SAMSUN
Terim: {terim[0]}

SAMSUN HABERLERİ:
{samsun_haber if samsun_haber else 'Bugün Samsun haberi yok'}

Samsun odağı + 1-2 senaryo + saha nabzı. JSON döndür."""
    r = ai_cagir(client, sistem, k, 2000)
    return r or {"samsun_odak":{"gelisme":"","bim_etkisi":"","aksiyon":""},"senaryolar":[],"saha_nabzi":{"gozlem":"","soru":"","beklenti":""}}

def ceo_brifing(abd_df, tr_df, makro_df, haberler, terim, tema, client):
    tum = []
    for k, v in haberler.items():
        for h in v[:3]:
            tum.append(f"[{k}] {h['Başlık']}: {h['Özet'][:100]}")
    haber_m = "\n".join(tum[:25])
    samsun_haber = "\n".join([f"- {h['Başlık']}: {h['Özet'][:150]}" for h in haberler.get("🏪 Samsun & Bölge", [])[:5]])

    print("  → AI Core...")
    core = ai_core(client, abd_df, tr_df, makro_df, haber_m, tema, terim)
    print("  → AI Strateji...")
    strat = ai_strateji(client, tr_df, haber_m, terim)
    print("  → AI Yerel...")
    yerel = ai_yerel(client, samsun_haber, terim)

    return {**core, **strat, **yerel}

# ============================================================
# SÖZLÜK
# ============================================================
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza büyümesi. BİM H1 2026: +%37,3 — fiyat kaynaklı.", "BİM'de LFL'in çoğu fiyat artışından. Gerçek hacim büyümesi yoksa sürdürülemez."),
    ("Brüt Kâr Marjı", "Malın maliyeti düşüldükten sonra kalan oran. BİM: %19,1.", "Özel marka payını 5 puan artırmak brüt marjı ~1 puan yükseltir."),
    ("FAVÖK (EBITDA)", "Faiz/Vergi/Amortisman öncesi kâr. BİM: %5,4.", "Türkiye perakendesinde %5+ dünya ortalaması üstü."),
    ("Özel Marka", "Marketin kendi markası. BİM: %55, ALDI: %90.", "ALDI modelinde %90 mümkün. BİM için hedef %65 olmalı."),
    ("Stok Devir Hızı", "Stok yılda kaç kez yenileniyor. A101: 14, ALDI: 12.", "Her 1 puan artış nakit akışına 1-2 mr TL katkı."),
    ("Fire Oranı", "Bozulma/kayıp oranı. Costco: %0,4, sektör: %1,5.", "BİM'in taze ürün genişlemesi fire riski getirir."),
    ("TMS 29", "Enflasyon muhasebesi. Türkiye'de zorunlu.", "Nakit kâr ≠ Muhasebe kârı."),
    ("CAPEX", "Uzun vadeli yatırım. BİM: ~%2,5.", "BİM son 5 yılda yavaşladı."),
    ("Retail Media", "Raf/uygulama reklam geliri. Walmart: +%38.", "BİM'in bu alanda sıfır geliri var."),
    ("Ajan Tabanlı Ticaret", "AI'ların müşteri adına alışverişi.", "BİM uygulaması AI ajanı kabul etmeli."),
    ("ROCE", "Sermaye getirisi. Tesco: %15,2.", "BİM'in ROCE'si muhtemelen %25+."),
    ("NPS", "Net Tavsiye Skoru. Tesco: 33.", "BİM NPS'i ölçmüyor."),
    ("Omnichannel", "Mağaza + online. Migros: 2.520 online.", "BİM online'a girmedi."),
    ("Hard Discount", "Az çeşit, düşük fiyat. BİM, A101, ŞOK.", "Türkiye'de pay %60+."),
    ("SKU Yönetimi", "Ürün çeşidi. BİM: ~1.000, Migros: ~10.000.", "1.000 SKU disiplini kârlılığın sırrı."),
    ("TEPE", "TEPAV Perakende Güven Endeksi.", "Pozitife dönerse harcama artar."),
    ("Müşteri Trafiği", "Mağazaya giren müşteri. BİM: +%0,4.", "Trafik artmıyor, sepet büyüyor."),
    ("Ortalama Sepet", "Satış / işlem sayısı.", "BİM'de sepet içi küçülüyor."),
    ("Raf Bulunurluğu", "Ürünün rafta olma oranı. İdeal: %97-99.", "Taze üründe düşebilir."),
    ("Stoksuz Kalma", "Talep varken rafın boş olması. İdeal: <%3.", "Her %1 kayıp = %0,5 ciro."),
]

HAFTANIN_TEMASI = {
    0: ("Haftalık Rakip Karşılaştırması", ""), 1: ("Makro Riskler ve Tüketici", ""),
    2: ("Dijital ve Retail Media", ""), 3: ("Özel Marka ve Kâr Kalitesi", ""),
    4: ("Rekabet ve Düzenleyici", ""), 5: ("Teknoloji ve AI", ""),
    6: ("Haftalık Değerlendirme", ""),
}

def gunun_terimi():
    return SOZLUK[datetime.now().timetuple().tm_yday % len(SOZLUK)]

DUNYA_ATLASI = [
    {"Şirket":"Walmart","Ülke":"🇺🇸 ABD","Nüfus":"335 mn","GSYH":"$27,4 tr","Dil":"İngilizce","Geçim":"Hizmet, teknoloji, üretim","Mağaza":"10.500+","Strateji":"Ölçek + lojistik + retail media"},
    {"Şirket":"Amazon","Ülke":"🇺🇸 ABD","Nüfus":"335 mn","GSYH":"$27,4 tr","Dil":"İngilizce","Geçim":"E-ticaret, bulut","Mağaza":"Dijital","Strateji":"Otomasyon + AI + lojistik"},
    {"Şirket":"Costco","Ülke":"🇺🇸 ABD","Nüfus":"335 mn","GSYH":"$27,4 tr","Dil":"İngilizce","Geçim":"Üyelik modeli","Mağaza":"870+","Strateji":"Üyelik sadakati"},
    {"Şirket":"Aldi","Ülke":"🇩🇪 Almanya","Nüfus":"84 mn","GSYH":"$4,6 tr","Dil":"Almanca","Geçim":"Üretim, ihracat","Mağaza":"7.000+","Strateji":"%90 özel marka"},
    {"Şirket":"Lidl","Ülke":"🇩🇪 Almanya","Nüfus":"84 mn","GSYH":"$4,6 tr","Dil":"Almanca","Geçim":"Üretim, ihracat","Mağaza":"12.000+","Strateji":"Mağaza verimliliği"},
    {"Şirket":"Carrefour","Ülke":"🇫🇷 Fransa","Nüfus":"68 mn","GSYH":"$3,1 tr","Dil":"Fransızca","Geçim":"Hizmet, turizm","Mağaza":"14.000+","Strateji":"Omnichannel"},
    {"Şirket":"Tesco","Ülke":"🇬🇧 İngiltere","Nüfus":"68 mn","GSYH":"$3,3 tr","Dil":"İngilizce","Geçim":"Finans, hizmet","Mağaza":"4.000+","Strateji":"Veri analitiği"},
]

# ============================================================
# HTML
# ============================================================
def df_table(df, baslik):
    if df.empty: return f"<p><em>{baslik}: veri yok.</em></p>"
    h = f'<h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:22px">{baslik}</h3>'
    h += '<table style="border-collapse:collapse;width:100%;font-size:12px"><thead><tr style="background:#1e293b;color:white">'
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

    # HATA RAPORU — varsa en üstte göster
    hata_html = ""
    if HATALAR:
        hata_html = f'''<div style="background:#fee2e2;border:2px solid #dc2626;padding:14px;border-radius:8px;margin-top:14px">
            <div style="font-weight:700;color:#991b1b;margin-bottom:8px">⚠️ Sistem Uyarıları ({len(HATALAR)})</div>
            <ul style="margin:0;padding-left:20px;color:#7f1d1d;font-size:12px;line-height:1.6">
            {"".join(f"<li>{h}</li>" for h in HATALAR)}
            </ul></div>'''

    sinyaller = "".join([f'''<div style="padding:14px;margin:10px 0;background:white;border-left:5px solid #3b82f6;border-radius:6px">
        <div style="display:flex;justify-content:space-between;gap:10px">
            <div style="font-weight:700;color:#0f172a;font-size:15px">{s.get("sinyal","")}</div>
            <div style="background:#eff6ff;color:#1e40af;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap">{s.get("rakam","")}</div>
        </div>
        <div style="color:#475569;margin-top:8px;font-size:13px">{s.get("neden_onemli","")}</div>
        <div style="color:#7c2d12;font-style:italic;font-size:13px;margin-top:6px;padding-top:6px;border-top:1px dashed #e2e8f0">→ {s.get("etki","")}</div>
    </div>''' for s in br.get("sabah_60_saniye",[])])

    so = br.get("samsun_odak",{})
    samsun_html = f'''<div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:5px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:10px">🏪 Samsun & Bölge Odağı</div>
        <div style="color:#334155;font-size:13px;margin-bottom:10px"><b>Gelişme:</b> {so.get("gelisme","") or "(haber yok)"}</div>
        <div style="background:white;padding:10px;border-radius:4px;font-size:13px;margin-bottom:8px"><b style="color:#92400e">BİM Samsun'a etkisi:</b> {so.get("bim_etkisi","") or "-"}</div>
        <div style="background:#dcfce7;padding:10px;border-radius:4px;font-size:13px"><b style="color:#166534">Öneri:</b> {so.get("aksiyon","") or "-"}</div>
    </div>'''

    kararlar = "".join([f'''<div style="padding:16px;margin:10px 0;background:#fffbeb;border-left:5px solid #f59e0b;border-radius:6px">
        <div style="font-weight:700;color:#78350f;font-size:15px;margin-bottom:10px">⚖️ {k.get("konu","")}</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="padding:4px 8px 4px 0;color:#64748b;width:110px"><b>Seçenek A</b></td><td style="color:#334155">{k.get("seçenek_a","")}</td></tr>
            <tr><td style="padding:4px 8px 4px 0;color:#64748b"><b>Seçenek B</b></td><td style="color:#334155">{k.get("seçenek_b","")}</td></tr>
        </table>
        <div style="background:#fef3c7;padding:10px;border-radius:4px;margin-top:10px;font-size:13px"><b>💡 Öneri:</b> {k.get("öneri","")}<br><span style="color:#92400e;font-size:12px"><i>{k.get("gerekçe","")}</i></span></div>
    </div>''' for k in br.get("karar_gundemi",[])])

    rakipler = "".join([f'''<div style="padding:12px;margin:8px 0;background:#f0f9ff;border-left:4px solid #0284c7;border-radius:6px">
        <div style="font-weight:700;color:#0c4a6e">{r.get("rakip","")}</div>
        <div style="color:#334155;font-size:13px;margin:6px 0">{r.get("hamle","")}</div>
        <div style="color:#166534;font-size:13px;background:#dcfce7;padding:8px;border-radius:4px;margin-top:6px"><b>BİM için ders:</b> {r.get("bim_icin_ders","")}</div>
    </div>''' for r in br.get("rakip_radari",[])])

    makrolar = "".join([f'''<div style="padding:12px;margin:8px 0;background:#faf5ff;border-left:4px solid #9333ea;border-radius:6px">
        <div style="display:flex;justify-content:space-between"><div style="font-weight:700;color:#581c87">{m.get("gösterge","")}</div><div style="color:#7e22ce;font-weight:600">{m.get("veri","")}</div></div>
        <div style="color:#4c1d95;font-size:13px;margin-top:6px">{m.get("yorum","")}</div>
        <div style="color:#166534;font-size:12px;margin-top:6px;padding-top:6px;border-top:1px dashed #c4b5fd"><b>Aksiyon:</b> {m.get("aksiyon","")}</div>
    </div>''' for m in br.get("makro_pusu",[])])

    senaryolar = "".join([f'''<div style="padding:16px;margin:12px 0;background:white;border:1px solid #e2e8f0;border-radius:8px">
        <div style="font-weight:700;color:#0f172a;margin-bottom:12px">🎯 {s.get("tetikleyici","")}</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="color:#047857;padding:6px 10px 6px 0;width:110px"><b>✅ İyimser</b></td><td style="color:#334155">{s.get("iyimser","")}</td></tr>
            <tr><td style="color:#1d4ed8;padding:6px 10px 6px 0"><b>⚖️ Baz</b></td><td style="color:#334155">{s.get("baz","")}</td></tr>
            <tr><td style="color:#b91c1c;padding:6px 10px 6px 0"><b>⚠️ Kötümser</b></td><td style="color:#334155">{s.get("kotumser","")}</td></tr>
        </table>
        <div style="background:#eff6ff;padding:10px;border-radius:4px;margin-top:10px;font-size:12px;color:#1e40af"><b>🛡️ Hazırlık:</b> {s.get("hazırlık","")}</div>
    </div>''' for s in br.get("senaryolar",[])])

    sh = br.get("saha_nabzi",{})
    saha_html = f'''<div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:5px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:8px">🔍 Bugün Mağazada</div>
        <div style="color:#334155;font-size:13px;margin-bottom:10px">{sh.get("gozlem","") or "-"}</div>
        <div style="background:white;padding:10px;border-radius:4px;font-size:13px"><b style="color:#92400e">Müdüre soru:</b> {sh.get("soru","") or "-"}<br><span style="color:#64748b;font-size:12px;font-style:italic">{sh.get("beklenti","")}</span></div>
    </div>'''

    atlas_html = '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:10px"><thead><tr style="background:#1e293b;color:white">'
    for k in DUNYA_ATLASI[0].keys(): atlas_html += f'<th style="padding:6px;border:1px solid #334155;text-align:left">{k}</th>'
    atlas_html += '</tr></thead><tbody>'
    for i, s in enumerate(DUNYA_ATLASI):
        bg2 = "#f8fafc" if i % 2 == 0 else "white"
        atlas_html += f'<tr style="background:{bg2}">'
        for v in s.values(): atlas_html += f'<td style="padding:5px;border:1px solid #e2e8f0">{v}</td>'
        atlas_html += '</tr>'
    atlas_html += '</tbody></table>'

    haber_html = ""
    for kategori, kayitlar in haberler.items():
        if not kayitlar:
            haber_html += f'<div style="margin-top:14px"><div style="font-weight:700;color:#1e40af;font-size:13px">{kategori}</div><div style="color:#94a3b8;font-size:12px;padding:8px">(Bu kategoride haber bulunamadı)</div></div>'
            continue
        haber_html += f'<div style="margin-top:14px"><div style="font-weight:700;color:#1e40af;font-size:13px;margin-bottom:6px">{kategori}</div>'
        for h in kayitlar[:3]:
            link = h.get("Link","")
            baslik = f'<a href="{link}" style="color:#1e40af;text-decoration:none">{h["Başlık"]}</a>' if link else h["Başlık"]
            haber_html += f'<div style="padding:10px;margin:6px 0;background:#f8fafc;border-left:3px solid #3b82f6;border-radius:4px"><div style="font-weight:600;color:#0f172a;font-size:13px">{baslik}</div><div style="color:#64748b;font-size:11px;margin-top:4px">{h["Özet"][:180]}</div><div style="color:#94a3b8;font-size:10px;margin-top:4px">{h["Kaynak"]}</div></div>'
        haber_html += '</div>'

    return f'''<html><body style="font-family:'Segoe UI',Arial,sans-serif;max-width:820px;margin:auto;background:#f1f5f9;padding:20px;color:#0f172a;line-height:1.5">
    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);color:white;padding:32px;border-radius:14px">
        <div style="font-size:11px;opacity:0.7;letter-spacing:3px">BİM SAMSUN · CEO STRATEJİK BRİFİNG</div>
        <h1 style="margin:8px 0 0 0;font-size:26px;font-weight:700">{tarih}</h1>
        <div style="margin-top:16px;padding:12px 16px;background:rgba(255,255,255,0.1);border-radius:8px;border-left:4px solid #fbbf24"><div style="font-size:11px;opacity:0.8;letter-spacing:1px">BUGÜNÜN MANŞETİ</div><div style="font-size:15px;font-weight:600;margin-top:4px">{br.get("manset","")}</div></div>
    </div>
    {hata_html}
    <div style="background:{bg};border:2px solid {renk};padding:14px;border-radius:10px;margin-top:14px;text-align:center"><span style="font-size:11px;color:{renk};letter-spacing:2px;font-weight:700">DURUM</span><div style="font-size:15px;font-weight:700;color:{renk};margin-top:4px">{br.get("uyari_seviyesi","")}</div></div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🧭 Haftalık Pusula</h3><div style="font-size:11px;color:#64748b">{tema[0]}</div><div style="color:#334155;font-size:14px;margin-top:8px">{br.get("haftalik_pusula","") or "(AI özet üretemedi)"}</div></div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⏱️ Sabah 60 Saniye</h3>{sinyaller or "<em>AI sinyal üretemedi.</em>"}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">{samsun_html}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">⚖️ Bugünün Karar Gündemi</h3>{kararlar or "<em>AI karar üretemedi.</em>"}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎯 Rakip Radarı</h3>{rakipler or "<em>AI rakip üretemedi.</em>"}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📡 Makro Pusu</h3>{makrolar or "<em>AI makro üretemedi.</em>"}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🎲 Senaryo Laboratuvarı</h3>{senaryolar or "<em>AI senaryo üretemedi.</em>"}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🏪 Saha Nabzı</h3>{saha_html}</div>
    <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:white;padding:20px;margin-top:14px;border-radius:12px"><div style="font-size:11px;opacity:0.7;letter-spacing:2px">GÜNÜN TERİMİ</div><div style="font-size:20px;font-weight:700;margin:6px 0">{terim[0]}</div><div style="font-size:14px;opacity:0.9;line-height:1.6">{terim[1]}</div><div style="background:rgba(59,130,246,0.2);padding:12px;border-radius:6px;margin-top:12px;border-left:3px solid #60a5fa;font-size:13px"><b>💡 BİM için anlamı:</b> {terim[2]}</div></div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px">{df_table(tr_df, "🇹🇷 Türkiye Perakendecileri")}{df_table(abd_df, "🌍 ABD Devleri (SEC)")}{df_table(makro_df, "📈 Makro (Dünya Bankası)")}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">🌐 Dünya Perakendecileri Atlası</h3>{atlas_html}</div>
    <div style="background:white;padding:20px;margin-top:14px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0">📰 Günün Haberleri</h3>{haber_html}</div>
    <div style="background:#0f172a;color:#94a3b8;padding:20px;margin-top:14px;border-radius:12px;font-size:11px;text-align:center;line-height:1.7"><b style="color:#e2e8f0">BİM SAMSUN CEO BRİFİNG</b><br>Kaynaklar: SEC · Dünya Bankası · AA · Bloomberg HT · BBC · Google News · Groq<br>📎 Excel eki<br><span style="color:#64748b;font-size:10px">Kritik kararlar öncesi TÜİK, TCMB, KAP doğrulayın.</span></div>
    </body></html>'''

def excel(abd_df, tr_df, makro_df, haberler, br):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        if not abd_df.empty: abd_df.to_excel(w, sheet_name="ABD Rakipler", index=False)
        tr_df.to_excel(w, sheet_name="Turkiye Perakende", index=False)
        if not makro_df.empty: makro_df.to_excel(w, sheet_name="Makro", index=False)
        pd.DataFrame(DUNYA_ATLASI).to_excel(w, sheet_name="Dunya Atlasi", index=False)
        if br.get("sabah_60_saniye"): pd.DataFrame(br["sabah_60_saniye"]).to_excel(w, sheet_name="60 Saniye", index=False)
        if br.get("karar_gundemi"): pd.DataFrame(br["karar_gundemi"]).to_excel(w, sheet_name="Karar Gundemi", index=False)
        if HATALAR: pd.DataFrame({"Hata": HATALAR}).to_excel(w, sheet_name="Sistem Uyarilari", index=False)
        tum = []
        for k, v in haberler.items():
            for h in v: tum.append({**h, "Kategori": k})
        if tum: pd.DataFrame(tum).drop(columns=["İngilizce"], errors="ignore").to_excel(w, sheet_name="Haberler", index=False)
    buf.seek(0); return buf

def mail(html, excel_data):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"🧭 BİM Samsun Brifing — {datetime.now().strftime('%d.%m.%Y')}"
    msg["From"] = MAIL_USER; msg["To"] = MAIL_TO
    alt = MIMEMultipart("alternative"); alt.attach(MIMEText(html, "html", "utf-8")); msg.attach(alt)
    if excel_data:
        ek = MIMEApplication(excel_data.read(), _subtype="xlsx")
        ek.add_header("Content-Disposition", "attachment", filename=f"bim_samsun_{datetime.now().strftime('%Y%m%d')}.xlsx")
        msg.attach(ek)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(MAIL_USER, MAIL_PASS)
        s.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
    print("✅ Mail gönderildi.")

def main():
    print("=" * 60); print(f"BİM SAMSUN BRİFİNG — {datetime.now()}"); print("=" * 60)

    if not GROQ_API_KEY:
        hata_yaz("GROQ_API_KEY ortam değişkeni BOŞ!")

    client = None
    try:
        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            print("✓ Groq client oluşturuldu")
    except Exception as e:
        hata_yaz(f"Groq client hatası: {e}")

    tema = HAFTANIN_TEMASI.get(datetime.now().weekday(), HAFTANIN_TEMASI[0])
    terim = gunun_terimi()

    print("[1/6] Haberler...")
    haberler = haber_topla()

    print("[2/6] Çeviri...")
    haberler = cevir(haberler, client)

    print("[3/6] ABD rakipler...")
    abd_df = abd_sirketleri()

    print("[4/6] Türkiye perakende...")
    tr_df = turkiye_sirketleri()

    print("[5/6] Makro...")
    makro_df = makro()

    print("[6/6] AI brifing (3 çağrı)...")
    br = ceo_brifing(abd_df, tr_df, makro_df, haberler, terim, tema, client)

    print(f"⚠️ Toplam {len(HATALAR)} hata/uyarı")
    print("📧 HTML + Excel...")
    html = html_uret(br, abd_df, tr_df, makro_df, haberler, terim, tema)
    try:
        ex = excel(abd_df, tr_df, makro_df, haberler, br)
    except Exception as e:
        hata_yaz(f"Excel hatası: {e}"); ex = None

    print("📤 Mail...")
    mail(html, ex)
    print("✅ Tamamlandı.")

if __name__ == "__main__":
    main()
