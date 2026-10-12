#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BİM SAMSUN — CEO STRATEJİK BRİFİNG v5 (Derinlik Sürümü)
=========================================================
- Türkiye perakende karşılaştırma tablosu (H1 2026)
- Rakip takip (BİM, A101, ŞOK, Migros, Carrefour)
- Global perakende haberleri (Lidl, Aldi, Walmart, Tesco, Carrefour, Rewe)
- TÜİK/TCMB makro veriler
- Teknoloji & inovasyon haberleri
- Kategori içgörüleri
- AI halüsinasyon koruması
"""

import os, re, time, json, smtplib, calendar
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

import feedparser, requests, pandas as pd
from groq import Groq

# ============================================================
# AYARLAR
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

GROQ_MODELLERI = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

HATALAR = []
def hata_yaz(msg):
    print(f"❌ {msg}")
    HATALAR.append(msg)

# ============================================================
# 1. HABER KAYNAKLARI
# ============================================================
def gnews(q):
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=tr&gl=TR&ceid=TR:tr"

KAYNAKLAR = {
    "🏪 Samsun & Bölge": [
        ("Samsun TSO/Sanayi", gnews('Samsun (TSO OR "ticaret odası" OR "sanayi odası" OR ihracat OR istihdam) -spor -maç -transfer -futbol'), False),
        ("Samsun Perakende", gnews('Samsun (AVM OR market OR mağaza OR perakende OR alışveriş) -spor -maç'), False),
    ],
    "🇹🇷 Türkiye Ekonomi": [
        ("AA Ekonomi", "https://www.aa.com.tr/tr/rss/default?cat=ekonomi", False),
        ("Bloomberg HT", "https://www.bloomberght.com/rss", False),
        ("Ekonomim", "https://www.ekonomim.com/rss", False),
    ],
    "📰 Türkiye Gündem": [
        ("AA Güncel", "https://www.aa.com.tr/tr/rss/default?cat=guncel", False),
    ],
    "🏢 BİM & Rakipler": [
        ("BİM Özel", gnews('"BİM" (mağaza OR açılış OR yatırım OR CEO OR satış OR büyüme) -spor -maç'), False),
        ("Migros & A101 & ŞOK", gnews('(Migros OR A101 OR ŞOK) (mağaza OR strateji OR kampanya OR yatırım) -spor -maç -transfer'), False),
    ],
    "🛒 Türkiye Perakende": [
        ("Perakende Güncel", gnews('Türkiye perakende (satış OR tüketici OR mağaza OR kampanya) -spor'), False),
        ("Perakende Sektörü", "https://perakendesektoru.com/feed/", False),
    ],
    "🌍 Global Perakende": [
        ("Retail Dive", "https://www.retaildive.com/feeds/news/", True),
        ("Retail Gazette", "https://retailgazette.com/feed/", True),
        ("Retail Detail EU", "https://www.retaildetail.eu/rss/", True),
    ],
    "🌐 Dünya Ekonomi": [
        ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", True),
    ],
    "🤖 Teknoloji & İnovasyon": [
        ("MIT Tech Review", "https://www.technologyreview.com/feed/", True),
        ("Retail Technology", "https://www.retailtechnology.co.uk/rss.xml", True),
    ],
}

YASAKLI = [
    "spor", "maç", "futbol", "basketbol", "voleybol", "tenis",
    "şampiyon", "gol", "lig", "turnuva", "transfermarkt", "samsunspor",
    "teknik direktör", "stadyum", "taraftar", "derbi",
    "magazin", "ünlü", "dizi", "konser",
    "cinayet", "şehit", "terör",
]

def yasakli_mi(b):
    b = b.lower()
    return any(k in b for k in YASAKLI)

def temizle(m):
    m = re.sub(r"<[^>]+>", " ", m or "")
    return re.sub(r"\s+", " ", m).strip()

def haber_topla():
    sonuc = {}
    for kategori, kaynaklar in KAYNAKLAR.items():
        kayitlar = []
        for ad, url, ing in kaynaklar:
            try:
                feed = feedparser.parse(url, agent=USER_AGENT)
                if feed.bozo and not feed.entries:
                    raise ValueError("RSS okunamadı")
                for e in feed.entries[:8]:
                    tarih = e.get("published_parsed") or e.get("updated_parsed")
                    if not tarih: continue
                    baslik = temizle(e.get("title", ""))
                    if not baslik or yasakli_mi(baslik): continue
                    kayitlar.append({
                        "Kategori": kategori, "Kaynak": ad, "Başlık": baslik,
                        "Özet": temizle(e.get("summary", ""))[:400],
                        "Link": e.get("link", ""), "İngilizce": ing,
                        "Tarih": datetime.fromtimestamp(calendar.timegm(tarih), tz=timezone.utc),
                    })
            except Exception as ex:
                hata_yaz(f"RSS hatası [{ad}]: {str(ex)[:80]}")
        # Tekilleştir
        gorulen = set(); benzersiz = []
        for h in sorted(kayitlar, key=lambda x: x["Tarih"], reverse=True):
            anahtar = re.sub(r"\W+", "", h["Başlık"].lower())[:50]
            if anahtar not in gorulen:
                gorulen.add(anahtar)
                benzersiz.append(h)
        sonuc[kategori] = benzersiz[:6]
        print(f"  {kategori}: {len(benzersiz)} haber")
    return sonuc

# ============================================================
# 2. SABİT SEKTÖR VERİLERİ (H1 2026 — çeyrekte bir güncellenir)
# ============================================================
SABIT_TR_KARSILASTIRMA = [
    {"Market": "BİM", "Satış 2026 (mr TL)": 428.4, "Değişim %": "+44,7", "LFL %": "+36,0", "Mağaza": 13032, "Mağaza Değişim": "+570", "Mağaza/Gün (bin TL)": 179.5, "Net Kâr (mn TL)": 20067, "Marj %": "4,7"},
    {"Market": "ŞOK", "Satış 2026 (mr TL)": 159.7, "Değişim %": "+40,9", "LFL %": "+39,2", "Mağaza": 11175, "Mağaza Değişim": "+138", "Mağaza/Gün (bin TL)": 104.2, "Net Kâr (mn TL)": 221, "Marj %": "0,1"},
    {"Market": "Mopaş", "Satış 2026 (mr TL)": 10.6, "Değişim %": "+38,2", "LFL %": "+35,1", "Mağaza": 133, "Mağaza Değişim": "+3", "Mağaza/Gün (bin TL)": 443.8, "Net Kâr (mn TL)": 136, "Marj %": "1,3"},
    {"Market": "Migros", "Satış 2026 (mr TL)": 229.8, "Değişim %": "+37,7", "LFL %": "+33,5", "Mağaza": 3830, "Mağaza Değişim": "+147", "Mağaza/Gün (bin TL)": 333.3, "Net Kâr (mn TL)": -1174, "Marj %": "-0,5"},
    {"Market": "Gimat Gross", "Satış 2026 (mr TL)": 3.3, "Değişim %": "+15,6", "LFL %": "+15,6", "Mağaza": 22, "Mağaza Değişim": "0", "Mağaza/Gün (bin TL)": 9132.0, "Net Kâr (mn TL)": 82, "Marj %": "2,5"},
    {"Market": "KİM", "Satış 2026 (mr TL)": 8.8, "Değişim %": "+12,8", "LFL %": "+13,6", "Mağaza": 142, "Mağaza Değişim": "-1", "Mağaza/Gün (bin TL)": 345.6, "Net Kâr (mn TL)": 194, "Marj %": "2,2"},
    {"Market": "CarrefourSA", "Satış 2026 (mr TL)": 43.6, "Değişim %": "-10,5", "LFL %": "-14,9", "Mağaza": 1264, "Mağaza Değişim": "+61", "Mağaza/Gün (bin TL)": 191.6, "Net Kâr (mn TL)": -4731, "Marj %": "-10,9"},
    {"Market": "Bizim Toptan", "Satış 2026 (mr TL)": 19.9, "Değişim %": "-16,6", "LFL %": "-14,1", "Mağaza": 166, "Mağaza Değişim": "-5", "Mağaza/Gün (bin TL)": 664.4, "Net Kâr (mn TL)": -500, "Marj %": "-2,5"},
]

KATEGORI_ICGORULERI = [
    {"Kategori": "Atıştırmalık", "Pay %": "16,9", "Değişim": "↑", "Yorum": "Hanelerin cüzdanından en büyük pay. Kraker, çikolata, cips, dondurma."},
    {"Kategori": "Et ve Et Ürünleri", "Pay %": "16,0", "Değişim": "↓", "Yorum": "Yüksek fiyat nedeniyle pazar payı hafif geriledi."},
    {"Kategori": "Süt ve Süt Ürünleri", "Pay %": "13,4", "Değişim": "↓", "Yorum": "İçme sütü üretimi 7 ayda %8,6 arttı ama tüketici harcaması azaldı."},
    {"Kategori": "Yağlar", "Pay %": "11,1", "Değişim": "→", "Yorum": "Fiyat istikrarı sağlandı, hacim korunuyor."},
    {"Kategori": "Çamaşır/Bulaşık", "Pay %": "10,7", "Değişim": "→", "Yorum": "Özel marka payı en yüksek kategorilerden."},
    {"Kategori": "Diğer Gıda", "Pay %": "13,6", "Değişim": "→", "Yorum": "Bakliyat, makarna, konserve. Hacim istikrarlı."},
]

DUNYA_ATLASI = [
    {"Şirket": "Walmart", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr", "Mağaza": "10.500+", "Gelir (mr $)": "648", "Net Marj %": "2,4", "Strateji": "Ölçek + lojistik + retail media"},
    {"Şirket": "Amazon", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr", "Mağaza": "Dijital + Whole Foods", "Gelir (mr $)": "620", "Net Marj %": "8,5", "Strateji": "AWS + otomasyon + AI"},
    {"Şirket": "Costco", "Ülke": "🇺🇸 ABD", "Nüfus": "335 mn", "GSYH": "$27,4 tr", "Mağaza": "870+", "Gelir (mr $)": "254", "Net Marj %": "2,9", "Strateji": "Üyelik modeli + düşük marj"},
    {"Şirket": "Aldi", "Ülke": "🇩🇪 Almanya", "Nüfus": "84 mn", "GSYH": "$4,6 tr", "Mağaza": "7.000+ (DE)", "Gelir (mr €)": "~110", "Net Marj %": "~3", "Strateji": "%90 özel marka"},
    {"Şirket": "Lidl", "Ülke": "🇩🇪 Almanya", "Nüfus": "84 mn", "GSYH": "$4,6 tr", "Mağaza": "13.000+ (global)", "Gelir (mr €)": "140", "Net Marj %": "~3", "Strateji": "Ölçek + otonom lojistik"},
    {"Şirket": "Carrefour", "Ülke": "🇫🇷 Fransa", "Nüfus": "68 mn", "GSYH": "$3,1 tr", "Mağaza": "14.000+ (global)", "Gelir (mr €)": "94", "Net Marj %": "1,5", "Strateji": "Omnichannel + AI sepet"},
    {"Şirket": "Tesco", "Ülke": "🇬🇧 İngiltere", "Nüfus": "68 mn", "GSYH": "$3,3 tr", "Mağaza": "4.000+", "Gelir (mr £)": "68", "Net Marj %": "3,0", "Strateji": "Veri analitiği + Clubcard"},
]

# ============================================================
# 3. SEC + DÜNYA BANKASI
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
        print(f"SEC hata ({ad}): {str(e)[:60]}")
        return {"Şirket": ad, "Gelir (mr $)": "-", "Net Kâr (mr $)": "-", "Dönem": "-"}

def abd_sirketleri():
    s = [("0000104169","Walmart"),("0001018724","Amazon"),("0000909832","Costco"),
         ("0000056873","Kroger"),("0001646972","Albertsons"),("0001611983","Target")]
    return pd.DataFrame([sec_verisi(c,a) for c,a in s])

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
# 4. ÇEVİRİ
# ============================================================
def cevir(haber_dict, client):
    tum = [h for v in haber_dict.values() for h in v]
    cevrilecek = [h for h in tum if h.get("İngilizce")]
    if not cevrilecek or not client: return haber_dict
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
                continue
        if not basarili:
            hata_yaz(f"Çeviri başarısız: {len(grup)} haber")
    return haber_dict

# ============================================================
# 5. AI ÇAĞRI (model fallback + halüsinasyon koruması)
# ============================================================
def ai_cagir(client, sistem, kullanici, max_tok=2500):
    if not client:
        hata_yaz("AI client yok")
        return None
    son_hata = "bilinmiyor"
    for model in GROQ_MODELLERI:
        for deneme in range(2):
            try:
                y = client.chat.completions.create(
                    messages=[{"role":"system","content":sistem},{"role":"user","content":kullanici}],
                    model=model, response_format={"type":"json_object"},
                    max_tokens=max_tok, temperature=0.15)
                return json.loads(y.choices[0].message.content)
            except json.JSONDecodeError as e:
                son_hata = f"JSON parse: {str(e)[:80]}"
                continue
            except Exception as e:
                son_hata = f"{type(e).__name__}: {str(e)[:120]}"
                time.sleep(2)
    hata_yaz(f"AI başarısız. Son: {son_hata}")
    return None

# Halüsinasyon önleyici ortak kural
KURAL_HALUSINASYON = """
KESİN DOĞRULUK KURALLARI (ÇOK ÖNEMLİ):
1. SADECE verilen haber metinlerinde ve veri tablolarında geçen bilgileri kullan.
2. Haberlerde/verilerde OLMAYAN hiçbir şeyi YAZMA:
   - Uydurma mağaza sayısı, ciro, kâr, tarih, isim, şehir YASAK.
   - "Migros şu şehirde şu mağazayı açtı" gibi cümle KURMA eğer kaynakta yoksa.
3. Emin olmadığın bilgide "bu konuda veri yok" veya "kaynak belirtilmemiş" yaz.
4. Her cümlenin kaynağı ya haberler ya da tablo olmalı.
5. Yorum yaparken "olabilir/muhtemel/önerilir" diliyle yaz, kesin konuşma.
"""

def ai_core(client, abd_df, tr_kars, makro_df, haber_ozet, tema, terim):
    sistem = f"""Sen BİM Samsun Bölge Müdürü'nün strateji danışmanısın.
Çıktı TAMAMEN TÜRKÇE. Şirket isimleri hariç İngilizce kullanma.
{KURAL_HALUSINASYON}

JSON: {{"manset":"tek cümle","sabah_60_saniye":[{{"sinyal":"","rakam":"","neden_onemli":"","etki":""}}],"haftalik_pusula":"1 paragraf","uyari_seviyesi":"YEŞİL/SARI/KIRMIZI — gerekçe"}}"""
    k = f"""Tarih: {datetime.now().strftime('%d.%m.%Y')} | Bölge: SAMSUN
Tema: {tema[0]}

SEKTÖR (H1 2026 - Türkiye):
{tr_kars}

ABD DEVLERİ (SEC):
{abd_df.to_string(index=False)}

MAKRO:
{makro_df.to_string(index=False) if not makro_df.empty else 'Yok'}

HABERLER:
{haber_ozet}

3 sinyal + manşet + haftalık pusula + uyarı seviyesi. SADECE verilen bilgiyi kullan."""
    r = ai_cagir(client, sistem, k, 2200)
    return r or {"manset":"AI çöktü","sabah_60_saniye":[],"haftalik_pusula":"","uyari_seviyesi":"SARI — AI hatası"}

def ai_strateji(client, tr_kars, haber_ozet):
    sistem = f"""BİM Samsun strateji danışmanı. Türkçe, karar odaklı.
{KURAL_HALUSINASYON}

JSON: {{"karar_gundemi":[{{"konu":"","seçenek_a":"","seçenek_b":"","öneri":"","gerekçe":""}}],"rakip_radari":[{{"rakip":"","hamle":"","bim_icin_ders":"","kaynak_var":true}}],"makro_pusu":[{{"gösterge":"","veri":"","yorum":"","aksiyon":""}}],"sektör_nabzi":[{{"gelişme":"","etki":"","aksiyon":""}}]}}"""
    k = f"""TÜRKİYE SEKTÖR VERİSİ (H1 2026):
{tr_kars}

HABERLER:
{haber_ozet}

2-3 karar + 2-3 rakip (SADECE haberde geçen) + 2-3 makro + 2-3 sektör gelişmesi. Veri uydurma."""
    r = ai_cagir(client, sistem, k, 2800)
    return r or {"karar_gundemi":[],"rakip_radari":[],"makro_pusu":[],"sektör_nabzi":[]}

def ai_global(client, dunya_haber, dunya_atlas):
    sistem = f"""Global perakende analisti. Türkçe.
{KURAL_HALUSINASYON}

JSON: {{"global_perakende":[{{"şirket":"","gelişme":"","bim_icin_ders":"","kaynak_var":true}}],"teknoloji_inovasyon":[{{"başlık":"","özet":"","bim_uygulama":""}}]}}"""
    k = f"""GLOBAL PERAKENDE VERİSİ:
{pd.DataFrame(dunya_atlas).to_string(index=False)}

GLOBAL HABERLER:
{dunya_haber}

3-4 global perakende hamlesi + 2-3 teknoloji gelişmesi. SADECE haberde geçen şirketler."""
    r = ai_cagir(client, sistem, k, 2200)
    return r or {"global_perakende":[],"teknoloji_inovasyon":[]}

def ai_yerel(client, samsun_haber, kategori_icgoru, terim):
    sistem = f"""BİM Samsun strateji danışmanı. Türkçe.
{KURAL_HALUSINASYON}

JSON: {{"samsun_odak":{{"gelisme":"","bim_etkisi":"","aksiyon":""}},"senaryolar":[{{"tetikleyici":"","iyimser":"","baz":"","kotumser":"","hazırlık":""}}],"saha_nabzi":{{"gozlem":"","soru":"","beklenti":""}},"kategori_yorumu":"2-3 cümle"}}"""
    k = f"""Bölge: SAMSUN
Terim: {terim[0]}

SAMSUN HABERLERİ:
{samsun_haber if samsun_haber else 'Bugün Samsun haberi yok'}

KATEGORİ İÇGÖRÜLERİ (Ipsos):
{kategori_icgoru}

Samsun odağı + 1-2 senaryo (hazırlık alanı MUTLAKA dolu) + saha nabzı + kategori yorumu."""
    r = ai_cagir(client, sistem, k, 2200)
    return r or {"samsun_odak":{"gelisme":"","bim_etkisi":"","aksiyon":""},"senaryolar":[],"saha_nabzi":{"gozlem":"","soru":"","beklenti":""},"kategori_yorumu":""}

def ceo_brifing(abd_df, tr_kars, makro_df, haberler, kategori_icgoru, dunya_atlas, terim, tema, client):
    # Haberleri kategorilere göre grupla
    oncelikli = ["🇹🇷 Türkiye Ekonomi", "🏢 BİM & Rakipler", "🛒 Türkiye Perakende"]
    haber_ozet_list = []
    for kat in oncelikli:
        for h in haberler.get(kat, [])[:4]:
            haber_ozet_list.append(f"[{kat}] {h['Başlık']}: {h['Özet'][:100]}")
    haber_ozet = "\n".join(haber_ozet_list[:15])

    dunya_ozet = []
    for kat in ["🌍 Global Perakende", "🤖 Teknoloji & İnovasyon"]:
        for h in haberler.get(kat, [])[:4]:
            dunya_ozet.append(f"[{h['Kaynak']}] {h['Başlık']}: {h['Özet'][:100]}")
    dunya_haber = "\n".join(dunya_ozet[:10])

    samsun_haber = "\n".join([f"- {h['Başlık']}: {h['Özet'][:150]}" for h in haberler.get("🏪 Samsun & Bölge", [])[:5]])

    print("  → AI Core...")
    core = ai_core(client, abd_df, tr_kars, makro_df, haber_ozet, tema, terim)
    print("  → AI Strateji...")
    strat = ai_strateji(client, tr_kars, haber_ozet)
    print("  → AI Global...")
    glob = ai_global(client, dunya_haber, dunya_atlas)
    print("  → AI Yerel...")
    yerel = ai_yerel(client, samsun_haber, kategori_icgoru, terim)

    return {**core, **strat, **glob, **yerel}

# ============================================================
# 6. SÖZLÜK + TEMA
# ============================================================
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza büyümesi. BİM H1 2026: +%36,0 (TMS 29 hariç).", "BİM'de LFL'in çoğu fiyat artışından. Gerçek hacim büyümesi yoksa sürdürülemez."),
    ("Brüt Kâr Marjı", "Mal maliyeti düşüldükten sonra kalan oran. BİM: %19 civarı.", "Özel marka payını 5 puan artırmak brüt marjı ~1 puan yükseltir."),
    ("TMS 29", "Enflasyon muhasebesi. Türkiye'de zorunlu.", "Nakit kâr ≠ Muhasebe kârı. BİM net kârında parasal kazanç etkisi var."),
    ("Özel Marka (PL)", "Marketin kendi markası. BİM: %55, ALDI: %90.", "Türkiye'de PL payı yükseliyor. BİM hedef %65 olmalı."),
    ("Stok Devir Hızı", "Stok yılda kaç kez yenilenir. A101: 14, ALDI: 12.", "Her 1 puan artış nakit akışına 1-2 mr TL katkı."),
    ("Retail Media", "Raf/uygulama reklam geliri. Walmart: güçlü büyüme.", "BİM'in bu alanda sıfır geliri var. 20 pilot mağaza = 500 mn TL potansiyel."),
    ("Mağaza Başı Ciro", "Toplam satış / mağaza sayısı. BİM: 179,5 bin TL/gün.", "Migros 333 bin TL, BİM 179 bin TL. Fark operasyonel verimlilikte."),
    ("Reel Büyüme", "Enflasyondan arındırılmış büyüme. Sektör: %2,1.", "Ciro büyüyor ama reel büyüme sınırlı. Verimlilik kritik."),
    ("Hard Discount", "Az çeşit, düşük fiyat. BİM, A101, ŞOK, Aldi, Lidl.", "Türkiye'de pay %60+. Global trend de aynı yönde."),
    ("Omnichannel", "Mağaza + online birlikte. Migros: 2.520 online mağaza.", "BİM online'a girmedi. Strateji mi, eksiklik mi?"),
    ("Kategori Yönetimi", "Hangi kategoriler ne kadar pay alıyor. Atıştırmalık %16,9.", "En yüksek paylı kategoriye göre mağaza düzeni ve stok."),
    ("Otonom Lojistik", "Sürücüsüz kamyon. Lidl ilk denemeyi yaptı.", "Türkiye'de henüz yok ama 2030'a kadar gelecek."),
    ("AI Self-Checkout", "Kamera + AI ile ürün tanıma. Morrisons 200 mağaza.", "Kasa maliyetini düşürür, kayıpları azaltır."),
    ("Smart Cart", "Akıllı alışveriş sepeti. Carrefour Belçika test ediyor.", "Türkiye'de ilk deneyen rekabet avantajı yakalar."),
    ("Dinamik Fiyat", "Raf fiyatını anlık güncelleme. Avrupa'da yaygın.", "Türkiye'de e-raf etiketi yatırımı düşünülmeli."),
    ("Müşteri Sadakat Programı", "Tesco Clubcard, Migros Money, A101 mobil.", "BİM'de yok. A101 bunu 2 yılda 20 mn kullanıcıya ulaştırdı."),
    ("Sepet İçi Değişim", "Sepet tutarı büyüyor ama içi küçülüyor.", "Tüketici daha az ürün alıyor, daha ucuz marka seçiyor."),
    ("Tüketici Güven Endeksi", "TÜİK+TCMB anketi. Eylül 2026: 91,9.", "2018'den beri en yüksek. Harcama isteği artıyor."),
    ("Gıda Enflasyonu", "TÜİK gıda ve alkolsüz içecek. Ağustos: %33,79.", "Genel TÜFE'den 2,28 puan yüksek. Gıda pahalanıyor."),
    ("Raf Bulunurluğu", "Ürünün rafta olma oranı. İdeal: %97-99.", "BİM'in sadelik avantajı var ama taze üründe düşebilir."),
]

def gunun_terimi():
    return SOZLUK[datetime.now().timetuple().tm_yday % len(SOZLUK)]

HAFTANIN_TEMASI = {
    0: ("Haftalık Rakip Karşılaştırması", ""),
    1: ("Makro Riskler ve Tüketici", ""),
    2: ("Dijital ve Retail Media", ""),
    3: ("Özel Marka ve Kâr Kalitesi", ""),
    4: ("Rekabet ve Düzenleyici", ""),
    5: ("Teknoloji ve AI", ""),
    6: ("Haftalık Değerlendirme", ""),
}

# ============================================================
# 7. HTML ÜRETİCİ
# ============================================================
def df_table(df, baslik):
    if df.empty: return f"<p><em>{baslik}: veri yok.</em></p>"
    h = f'<h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:22px">{baslik}</h3>'
    h += '<table style="border-collapse:collapse;width:100%;font-size:11px"><thead><tr style="background:#1e293b;color:white">'
    for c in df.columns: h += f'<th style="padding:6px;text-align:left;border:1px solid #334155">{c}</th>'
    h += '</tr></thead><tbody>'
    for i, row in df.iterrows():
        bg = "#f8fafc" if i % 2 == 0 else "white"
        h += f'<tr style="background:{bg}">'
        for v in row: h += f'<td style="padding:5px;border:1px solid #e2e8f0">{v}</td>'
        h += '</tr>'
    return h + '</tbody></table>'

def kart_listesi(items, icon, anahtar_baslik, alt_alanlar, renk="#3b82f6"):
    """Genel kart listesi üretici."""
    if not items: return "<em>Veri yok.</em>"
    html = ""
    for it in items:
        html += f'''<div style="padding:12px;margin:8px 0;background:#f8fafc;border-left:4px solid {renk};border-radius:6px">
            <div style="font-weight:700;color:#0f172a">{icon} {it.get(anahtar_baslik,"")}</div>'''
        for alan, baslik, style in alt_alanlar:
            val = it.get(alan, "")
            if val:
                html += f'<div style="color:#334155;font-size:13px;margin-top:6px;{style}"><b>{baslik}:</b> {val}</div>'
        html += '</div>'
    return html

def uyari_renk(s):
    s = (s or "").upper()
    if "KIRMIZI" in s: return "#dc2626", "#fee2e2"
    if "SARI" in s: return "#d97706", "#fef3c7"
    return "#16a34a", "#dcfce7"

def html_uret(br, abd_df, makro_df, haberler, terim, tema):
    tarih = datetime.now().strftime("%d.%m.%Y %A")
    renk, bg = uyari_renk(br.get("uyari_seviyesi",""))

    # Hata
    hata_html = ""
    if HATALAR:
        hata_html = f'''<div style="background:#fee2e2;border:2px solid #dc2626;padding:12px;border-radius:8px;margin-top:12px">
            <div style="font-weight:700;color:#991b1b;margin-bottom:6px;font-size:13px">⚠️ Sistem Uyarıları ({len(HATALAR)})</div>
            <ul style="margin:0;padding-left:18px;color:#7f1d1d;font-size:11px;line-height:1.5">
            {"".join(f"<li>{h}</li>" for h in HATALAR[:8])}
            </ul></div>'''

    # Sinyaller
    sinyaller = "".join([f'''<div style="padding:12px;margin:8px 0;background:white;border-left:4px solid #3b82f6;border-radius:6px">
        <div style="display:flex;justify-content:space-between;gap:10px">
            <div style="font-weight:700;color:#0f172a;font-size:14px">{s.get("sinyal","")}</div>
            <div style="background:#eff6ff;color:#1e40af;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap">{s.get("rakam","")}</div>
        </div>
        <div style="color:#475569;margin-top:6px;font-size:12px">{s.get("neden_onemli","")}</div>
        <div style="color:#7c2d12;font-style:italic;font-size:12px;margin-top:4px;padding-top:4px;border-top:1px dashed #e2e8f0">→ {s.get("etki","")}</div>
    </div>''' for s in br.get("sabah_60_saniye",[])])

    # Samsun
    so = br.get("samsun_odak",{})
    samsun_html = f'''<div style="background:#fef3c7;padding:14px;border-radius:8px;border-left:4px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:8px">🏪 Samsun & Bölge</div>
        <div style="color:#334155;font-size:12px;margin-bottom:8px"><b>Gelişme:</b> {so.get("gelisme","") or "-"}</div>
        <div style="background:white;padding:8px;border-radius:4px;font-size:12px;margin-bottom:6px"><b>BİM etkisi:</b> {so.get("bim_etkisi","") or "-"}</div>
        <div style="background:#dcfce7;padding:8px;border-radius:4px;font-size:12px"><b>Öneri:</b> {so.get("aksiyon","") or "-"}</div>
    </div>'''

    # Kararlar
    kararlar = kart_listesi(
        br.get("karar_gundemi", []), "⚖️", "konu",
        [("seçenek_a", "A", "color:#334155"), ("seçenek_b", "B", "color:#334155"),
         ("öneri", "Öneri", "background:#fef3c7;padding:6px;border-radius:4px;margin-top:6px"),
         ("gerekçe", "Gerekçe", "color:#92400e;font-size:11px;font-style:italic")],
        "#f59e0b"
    )

    # Rakipler
    rakipler = kart_listesi(
        br.get("rakip_radari", []), "🎯", "rakip",
        [("hamle", "Hamle", "color:#334155"), ("bim_icin_ders", "BİM için ders", "color:#166534;background:#dcfce7;padding:6px;border-radius:4px;margin-top:6px")],
        "#0284c7"
    )

    # Makro
    makrolar = "".join([f'''<div style="padding:10px;margin:6px 0;background:#faf5ff;border-left:3px solid #9333ea;border-radius:6px">
        <div style="display:flex;justify-content:space-between"><b style="color:#581c87;font-size:13px">{m.get("gösterge","")}</b><span style="color:#7e22ce;font-weight:600;font-size:12px">{m.get("veri","")}</span></div>
        <div style="color:#4c1d95;font-size:12px;margin-top:4px">{m.get("yorum","")}</div>
        <div style="color:#166534;font-size:11px;margin-top:4px"><b>Aksiyon:</b> {m.get("aksiyon","")}</div>
    </div>''' for m in br.get("makro_pusu",[])])

    # SEKTÖR NABZI (YENİ)
    sektor = kart_listesi(
        br.get("sektör_nabzi", []), "📊", "gelişme",
        [("etki", "BİM'e etki", "color:#334155"), ("aksiyon", "Aksiyon", "color:#166534;background:#dcfce7;padding:6px;border-radius:4px;margin-top:6px")],
        "#7c3aed"
    )

    # GLOBAL PERAKENDE (YENİ)
    global_per = kart_listesi(
        br.get("global_perakende", []), "🌍", "şirket",
        [("gelişme", "Gelişme", "color:#334155"), ("bim_icin_ders", "BİM için ders", "color:#1e40af;background:#dbeafe;padding:6px;border-radius:4px;margin-top:6px")],
        "#1d4ed8"
    )

    # TEKNOLOJİ (YENİ)
    teknoloji = kart_listesi(
        br.get("teknoloji_inovasyon", []), "🤖", "başlık",
        [("özet", "Özet", "color:#334155"), ("bim_uygulama", "BİM'de uygulama", "color:#7c2d12;background:#fed7aa;padding:6px;border-radius:4px;margin-top:6px")],
        "#ea580c"
    )

    # KATEGORİ İÇGÖRÜLERİ (YENİ)
    kat_rows = "".join([f'''<tr style="background:{"#f8fafc" if i%2==0 else "white"}">
        <td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">{k["Kategori"]}</td>
        <td style="padding:6px;border:1px solid #e2e8f0;text-align:center">%{k["Pay %"]}</td>
        <td style="padding:6px;border:1px solid #e2e8f0;text-align:center">{k["Değişim"]}</td>
        <td style="padding:6px;border:1px solid #e2e8f0;font-size:11px">{k["Yorum"]}</td>
    </tr>''' for i, k in enumerate(KATEGORI_ICGORULERI)])
    kategori_html = f'''<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:#1e293b;color:white">
            <th style="padding:6px;text-align:left">Kategori</th>
            <th style="padding:6px;text-align:center">Pay</th>
            <th style="padding:6px;text-align:center">Trend</th>
            <th style="padding:6px;text-align:left">Yorum</th>
        </tr></thead><tbody>{kat_rows}</tbody></table>'''

    # Senaryolar
    senaryolar = "".join([f'''<div style="padding:12px;margin:8px 0;background:white;border:1px solid #e2e8f0;border-radius:6px">
        <div style="font-weight:700;color:#0f172a;margin-bottom:8px;font-size:13px">🎯 {s.get("tetikleyici","")}</div>
        <table style="width:100%;font-size:12px;border-collapse:collapse">
            <tr><td style="color:#047857;padding:4px 8px 4px 0;width:100px;vertical-align:top"><b>✅ İyimser</b></td><td style="color:#334155">{s.get("iyimser","")}</td></tr>
            <tr><td style="color:#1d4ed8;padding:4px 8px 4px 0;vertical-align:top"><b>⚖️ Baz</b></td><td style="color:#334155">{s.get("baz","")}</td></tr>
            <tr><td style="color:#b91c1c;padding:4px 8px 4px 0;vertical-align:top"><b>⚠️ Kötümser</b></td><td style="color:#334155">{s.get("kotumser","")}</td></tr>
        </table>
        <div style="background:#eff6ff;padding:8px;border-radius:4px;margin-top:8px;font-size:11px;color:#1e40af"><b>🛡️ Hazırlık:</b> {s.get("hazırlık","") or "Önceden senaryo hazırlığı yapılmalı"}</div>
    </div>''' for s in br.get("senaryolar",[])])

    # Saha
    sh = br.get("saha_nabzi",{})
    saha_html = f'''<div style="background:#fef3c7;padding:14px;border-radius:8px;border-left:4px solid #f59e0b">
        <div style="font-weight:700;color:#78350f;margin-bottom:6px">🔍 Bugün Mağazada</div>
        <div style="color:#334155;font-size:12px;margin-bottom:8px">{sh.get("gozlem","") or "-"}</div>
        <div style="background:white;padding:8px;border-radius:4px;font-size:12px"><b>Müdüre soru:</b> {sh.get("soru","") or "-"}<br><span style="color:#64748b;font-size:11px;font-style:italic">{sh.get("beklenti","")}</span></div>
    </div>'''

    # Türkiye karşılaştırma tablosu
    tr_df = pd.DataFrame(SABIT_TR_KARSILASTIRMA)
    tr_html = df_table(tr_df, "🇹🇷 Türkiye Perakende Karşılaştırma (H1 2026)")

    # Dünya atlası
    dunya_df = pd.DataFrame(DUNYA_ATLASI)
    dunya_html = df_table(dunya_df, "🌐 Dünya Perakende Devleri")

    # Haberler
    haber_html = ""
    for kategori, kayitlar in haberler.items():
        if not kayitlar: continue
        haber_html += f'<div style="margin-top:12px"><div style="font-weight:700;color:#1e40af;font-size:12px;margin-bottom:4px">{kategori}</div>'
        for h in kayitlar[:3]:
            link = h.get("Link","")
            baslik = f'<a href="{link}" style="color:#1e40af;text-decoration:none">{h["Başlık"]}</a>' if link else h["Başlık"]
            haber_html += f'<div style="padding:8px;margin:4px 0;background:#f8fafc;border-left:3px solid #3b82f6;border-radius:4px"><div style="font-weight:600;color:#0f172a;font-size:12px">{baslik}</div><div style="color:#64748b;font-size:10px;margin-top:3px">{h["Özet"][:150]}</div><div style="color:#94a3b8;font-size:9px;margin-top:3px">{h["Kaynak"]}</div></div>'
        haber_html += '</div>'

    return f'''<html><body style="font-family:'Segoe UI',Arial,sans-serif;max-width:850px;margin:auto;background:#f1f5f9;padding:20px;color:#0f172a;line-height:1.5">
    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);color:white;padding:28px;border-radius:14px">
        <div style="font-size:10px;opacity:0.7;letter-spacing:3px">BİM SAMSUN · CEO STRATEJİK BRİFİNG</div>
        <h1 style="margin:6px 0 0 0;font-size:24px;font-weight:700">{tarih}</h1>
        <div style="margin-top:14px;padding:10px 14px;background:rgba(255,255,255,0.1);border-radius:8px;border-left:4px solid #fbbf24"><div style="font-size:10px;opacity:0.8;letter-spacing:1px">BUGÜNÜN MANŞETİ</div><div style="font-size:14px;font-weight:600;margin-top:3px">{br.get("manset","")}</div></div>
    </div>
    {hata_html}
    <div style="background:{bg};border:2px solid {renk};padding:12px;border-radius:10px;margin-top:12px;text-align:center"><span style="font-size:10px;color:{renk};letter-spacing:2px;font-weight:700">DURUM</span><div style="font-size:14px;font-weight:700;color:{renk};margin-top:3px">{br.get("uyari_seviyesi","")}</div></div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🧭 Haftalık Pusula</h3><div style="font-size:10px;color:#64748b">{tema[0]}</div><div style="color:#334155;font-size:13px;margin-top:6px">{br.get("haftalik_pusula","") or "(AI üretemedi)"}</div></div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">⏱️ Sabah 60 Saniye</h3>{sinyaller or "<em>AI üretemedi.</em>"}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px">{samsun_html}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">⚖️ Bugünün Karar Gündemi</h3>{kararlar}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🎯 Rakip Radarı</h3>{rakipler}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">📊 Sektör Nabzı</h3>{sektor}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🌍 Global Perakende</h3>{global_per}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🤖 Teknoloji & İnovasyon</h3>{teknoloji}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">📡 Makro Pusu</h3>{makrolar or "<em>AI üretemedi.</em>"}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🛒 Kategori İçgörüleri</h3>{kategori_html}<div style="margin-top:10px;padding:10px;background:#f0f9ff;border-radius:6px;font-size:12px;color:#1e40af"><b>AI Yorumu:</b> {br.get("kategori_yorumu","-")}</div></div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🎲 Senaryo Laboratuvarı</h3>{senaryolar or "<em>AI üretemedi.</em>"}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">🏪 Saha Nabzı</h3>{saha_html}</div>
    
    <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:white;padding:18px;margin-top:12px;border-radius:12px"><div style="font-size:10px;opacity:0.7;letter-spacing:2px">GÜNÜN TERİMİ</div><div style="font-size:18px;font-weight:700;margin:4px 0">{terim[0]}</div><div style="font-size:13px;opacity:0.9">{terim[1]}</div><div style="background:rgba(59,130,246,0.2);padding:10px;border-radius:6px;margin-top:10px;border-left:3px solid #60a5fa;font-size:12px"><b>💡 BİM için:</b> {terim[2]}</div></div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px">{tr_html}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px">{df_table(abd_df, "🌍 ABD Devleri (SEC - Canlı)")}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px">{df_table(makro_df, "📈 Makro (Dünya Bankası)")}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px">{dunya_html}</div>
    
    <div style="background:white;padding:18px;margin-top:12px;border-radius:12px"><h3 style="color:#0f172a;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-top:0;font-size:15px">📰 Günün Haberleri</h3>{haber_html}</div>
    
    <div style="background:#0f172a;color:#94a3b8;padding:16px;margin-top:12px;border-radius:12px;font-size:10px;text-align:center;line-height:1.6"><b style="color:#e2e8f0">BİM SAMSUN CEO BRİFİNG v5</b><br>Kaynaklar: SEC · Dünya Bankası · AA · Bloomberg HT · Ekonomim · BBC · Retail Dive · Retail Gazette · Retail Detail · MIT · Retail Technology · Google News · Groq AI<br>📎 Excel eki<br><span style="color:#64748b;font-size:9px">Kritik kararlar öncesi TÜİK, TCMB, KAP doğrulayın.</span></div>
    </body></html>'''

# ============================================================
# 8. EXCEL
# ============================================================
def excel(abd_df, makro_df, haberler, br):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        def _tz(df):
            df = df.copy()
            for c in df.columns:
                if df[c].dtype == "object":
                    df[c] = df[c].apply(lambda x: x.replace(tzinfo=None) if hasattr(x,"tzinfo") and x.tzinfo else x)
            return df
        _tz(abd_df).to_excel(w, sheet_name="ABD Rakipler", index=False)
        _tz(makro_df).to_excel(w, sheet_name="Makro", index=False)
        pd.DataFrame(SABIT_TR_KARSILASTIRMA).to_excel(w, sheet_name="TR Karsilastirma H1-2026", index=False)
        pd.DataFrame(DUNYA_ATLASI).to_excel(w, sheet_name="Dunya Atlas", index=False)
        pd.DataFrame(KATEGORI_ICGORULERI).to_excel(w, sheet_name="Kategori Icgoruleri", index=False)
        if br.get("sabah_60_saniye"):
            pd.DataFrame(br["sabah_60_saniye"]).to_excel(w, sheet_name="60 Saniye", index=False)
        if br.get("karar_gundemi"):
            pd.DataFrame(br["karar_gundemi"]).to_excel(w, sheet_name="Karar Gundemi", index=False)
        if br.get("rakip_radari"):
            pd.DataFrame(br["rakip_radari"]).to_excel(w, sheet_name="Rakip Radari", index=False)
        if br.get("sektör_nabzi"):
            pd.DataFrame(br["sektör_nabzi"]).to_excel(w, sheet_name="Sektor Nabzi", index=False)
        if br.get("global_perakende"):
            pd.DataFrame(br["global_perakende"]).to_excel(w, sheet_name="Global Perakende", index=False)
        if br.get("teknoloji_inovasyon"):
            pd.DataFrame(br["teknoloji_inovasyon"]).to_excel(w, sheet_name="Teknoloji", index=False)
        tum = []
        for k, v in haberler.items():
            for h in v: tum.append({**h, "Kategori": k})
        if tum:
            hdf = pd.DataFrame(tum).drop(columns=["İngilizce"], errors="ignore")
            if "Tarih" in hdf.columns:
                hdf["Tarih"] = hdf["Tarih"].apply(lambda x: x.replace(tzinfo=None) if hasattr(x,"tzinfo") and x.tzinfo else x)
            hdf.to_excel(w, sheet_name="Haberler", index=False)
        if HATALAR:
            pd.DataFrame({"Hata": HATALAR}).to_excel(w, sheet_name="Sistem Uyarilari", index=False)
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

# ============================================================
# ANA AKIŞ
# ============================================================
def main():
    print("=" * 60); print(f"BİM SAMSUN BRİFİNG v5 — {datetime.now()}"); print("=" * 60)
    if not GROQ_API_KEY:
        hata_yaz("GROQ_API_KEY BOŞ!")
    client = None
    try:
        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            print("✓ Groq client hazır")
    except Exception as e:
        hata_yaz(f"Groq client hatası: {str(e)[:80]}")

    tema = HAFTANIN_TEMASI.get(datetime.now().weekday(), HAFTANIN_TEMASI[0])
    terim = gunun_terimi()

    print("[1/6] Haberler...")
    haberler = haber_topla()

    print("[2/6] Çeviri...")
    haberler = cevir(haberler, client)

    print("[3/6] ABD rakipler (SEC)...")
    abd_df = abd_sirketleri()

    print("[4/6] Makro (Dünya Bankası)...")
    makro_df = makro()

    print("[5/6] CEO brifing (4 AI çağrı)...")
    br = ceo_brifing(abd_df, SABIT_TR_KARSILASTIRMA, makro_df, haberler, KATEGORI_ICGORULERI, DUNYA_ATLASI, terim, tema, client)

    print(f"⚠️ Toplam {len(HATALAR)} hata/uyarı")
    print("[6/6] HTML + Excel...")
    html = html_uret(br, abd_df, makro_df, haberler, terim, tema)
    try:
        ex = excel(abd_df, makro_df, haberler, br)
    except Exception as e:
        hata_yaz(f"Excel hatası: {str(e)[:80]}"); ex = None

    print("📤 Mail...")
    mail(html, ex)
    print("✅ Tamamlandı.")

if __name__ == "__main__":
    main()
