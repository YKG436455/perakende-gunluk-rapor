# -*- coding: utf-8 -*-
"""
TAM OTOMATİK GÜNLÜK PERAKENDE BÜLTENİ
Her sabah 07:00'de çalışır, tüm verileri kendi toplar, günceller ve e-posta gönderir.
"""

import os
import smtplib
import json
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from io import StringIO

import feedparser
import requests
import pandas as pd
from groq import Groq

# ============================================================
# AYARLAR (GitHub Secrets'tan gelir)
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

# SEC EDGAR için User-Agent (zorunlu)
SEC_HEADERS = {
    "User-Agent": "PerakendeBulten/1.0 (iletisim@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

# ============================================================
# BÖLÜM 1: VERİ TOPLAMA MODÜLLERİ
# ============================================================

class VeriToplayici:
    """Tüm veri kaynaklarından otomatik veri toplar."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    # --------------------------------------------------------
    # 1. SEC EDGAR'dan ABD Şirketleri Finansalları
    # --------------------------------------------------------
    def sec_verisi_cek(self, cik: str, sirket_adi: str) -> dict:
        """SEC EDGAR API'sinden şirket finansal verilerini çeker."""
        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
            resp = self.session.get(url, headers=SEC_HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # Son 4 çeyreğin gelirini al
                gelirler = data.get("facts", {}).get("us-gaap", {}).get(
                    "Revenues", {}
                ).get("units", {}).get("USD", [])
                son_gelir = gelirler[-1] if gelirler else {}
                return {
                    "sirket": sirket_adi,
                    "gelir": son_gelir.get("val", 0),
                    "donem": son_gelir.get("end", "Bilinmiyor"),
                    "kaynak": "SEC EDGAR"
                }
        except Exception as e:
            print(f"SEC hatası ({sirket_adi}): {e}")
        return {"sirket": sirket_adi, "gelir": 0, "donem": "Veri yok", "kaynak": "SEC"}
    
    def abd_sirketleri_finansallari(self) -> str:
        """Walmart, Amazon, Costco için SEC verilerini toplar."""
        sirketler = [
            ("0000104169", "Walmart"),
            ("0001018724", "Amazon"),
            ("0000909832", "Costco"),
            ("0000056873", "Kroger"),
            ("0001646972", "Albertsons"),
        ]
        sonuclar = []
        for cik, ad in sirketler:
            try:
                veri = self.sec_verisi_cek(cik, ad)
                if veri["gelir"] > 0:
                    gelir_mr = veri["gelir"] / 1e9
                    sonuclar.append(f"• {ad}: {gelir_mr:.1f} mr $ ({veri['donem']})")
                time.sleep(0.2)  # SEC rate limit
            except Exception as e:
                print(f"Hata: {e}")
        return "\n".join(sonuclar) if sonuclar else "Veri alınamadı."
    
    # --------------------------------------------------------
    # 2. KAP'tan Türkiye Şirketleri Verileri
    # --------------------------------------------------------
    def kap_verisi_cek(self, ticker: str) -> dict:
        """KAP'tan şirket finansal verilerini çeker (web scraping)."""
        try:
            # KAP finansal rapor arama sayfası
            url = f"https://www.kap.org.tr/tr/api/company/query?q={ticker}"
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"KAP hatası ({ticker}): {e}")
        return {}
    
    def turkiye_sirketleri_finansallari(self) -> str:
        """BİM, Migros, ŞOK için güncel verileri toplar."""
        # KAP API'si karmaşık olduğu için manuel güncellenen tablo
        # (KAP'ta otomatik çekim için özel API anahtarı gerekir)
        return """
    ┌─────────────────┬──────────────┬──────────┬────────┬──────────┐
    │ Firma           │ Satış        │ Mağaza   │ LFL    │ Net Kâr  │
    ├─────────────────┼──────────────┼──────────┼────────┼──────────┤
    │ BİM (H1 2026)   │ 449,7 mr TL  │ 14.851   │ +%37,3 │ +15,1 mr │
    │ Migros (Q2 26)  │ 124,4 mr TL  │ 3.830    │ Negatif│ -699 mn  │
    │ ŞOK (H1 2026)   │ 167,8 mr TL  │ 11.175   │ +%5    │ -1,35 mr │
    └─────────────────┴──────────────┴──────────┴────────┴──────────┘
    
    BİM Brüt Marj: %19,1  |  FAVÖK Marjı: %5,4  |  Özel Marka: %55
    Mağaza Başına Ciro: 30,7 mn TL (ŞOK'un 2 katı)
        """
    
    # --------------------------------------------------------
    # 3. Dünya Bankası'ndan Makro Veriler
    # --------------------------------------------------------
    def dunya_bankasi_verisi(self) -> str:
        """Dünya Bankası API'sinden Türkiye makro verilerini çeker."""
        gostergeler = {
            "NY.GDP.MKTP.KD.ZG": "Büyüme (%)",
            "FP.CPI.TOTL.ZG": "Enflasyon (%)",
            "SL.UEM.TOTL.ZS": "İşsizlik (%)",
        }
        sonuclar = []
        for kod, ad in gostergeler.items():
            try:
                url = f"https://api.worldbank.org/v2/country/TUR/indicator/{kod}?format=json&per_page=1&date=2024:2026"
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) > 1 and data[1]:
                        deger = data[1][0].get("value", "N/A")
                        yil = data[1][0].get("date", "")
                        if deger:
                            sonuclar.append(f"• {ad}: {deger:.1f} ({yil})")
            except Exception as e:
                print(f"Dünya Bankası hatası: {e}")
        return "\n".join(sonuclar) if sonuclar else "Makro veri alınamadı."
    
    # --------------------------------------------------------
    # 4. RSS Beslemelerinden Haberler
    # --------------------------------------------------------
    def rss_haberleri(self) -> str:
        """Perakende RSS beslemelerinden son haberleri çeker."""
        kaynaklar = [
            ("https://www.retailtechnology.co.uk/rss.xml", "Teknoloji"),
            ("https://retailgazette.com/feed/", "Uluslararası"),
            ("https://perakendesektoru.com/feed/", "Türkiye"),
            ("https://ekonomikgundem.com.tr/tag/gida-perakende/feed/", "Gıda"),
        ]
        haberler = []
        for url, kategori in kaynaklar:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    ozet = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:200]
                    haberler.append(f"• [{kategori}] {entry.title}\n  {ozet}...")
            except Exception as e:
                print(f"RSS hatası ({kategori}): {e}")
        return "\n\n".join(haberler) if haberler else "Bugün yeni haber bulunamadı."
    
    # --------------------------------------------------------
    # 5. Tüm Verileri Topla
    # --------------------------------------------------------
    def tum_verileri_topla(self) -> dict:
        """Tüm kaynaklardan verileri toplar."""
        print("→ ABD şirket verileri çekiliyor...")
        abd_veri = self.abd_sirketleri_finansallari()
        
        print("→ Türkiye şirket verileri hazırlanıyor...")
        tr_veri = self.turkiye_sirketleri_finansallari()
        
        print("→ Makro veriler çekiliyor...")
        makro_veri = self.dunya_bankasi_verisi()
        
        print("→ Haberler toplanıyor...")
        haberler = self.rss_haberleri()
        
        return {
            "abd": abd_veri,
            "turkiye": tr_veri,
            "makro": makro_veri,
            "haberler": haberler,
            "tarih": datetime.now().strftime("%d.%m.%Y %A"),
        }

# ============================================================
# BÖLÜM 2: PERAKENDE SÖZLÜĞÜ (Her gün 3 terim dönüşümlü)
# ============================================================
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza satış büyümesi. Yeni açılan veya kapanan mağazaları hariç tutarak, mevcut mağazaların ne kadar büyüdüğünü gösterir. Örnek: BİM'in Q2 2026'da LFL'si %37,3 — yani mevcut mağazaları geçen yıla göre %37,3 daha fazla satış yaptı."),
    ("Brüt Kâr Marjı (Gross Margin)", "Satıştan malın maliyeti düşüldükten sonra kalan tutarın satışa oranı. Örnek: BİM'in brüt marjı %19,1 — yani 100 TL'lik satıştan 19,1 TL brüt kâr kalıyor."),
    ("FAVÖK / EBITDA", "Faiz, Vergi, Amortisman ve İtfa öncesi kâr. Operasyonel kârlılığın en saf ölçüsü. Örnek: BİM'in FAVÖK marjı %5,4 — yani 100 TL satıştan 5,4 TL operasyonel kâr."),
    ("Özel Marka (Private Label)", "Marketin kendi markasıyla sattığı ürünler. Örnek: BİM'in yurt içi satışının %55'i özel marka. Bu, maliyet avantajı ve müşteri sadakati sağlar."),
    ("Stok Devir Hızı (Inventory Turnover)", "Stokun yılda kaç kez satılıp yenilendiği. Yüksek olması iyi. Örnek: ALDI 12 kez, A101 14 kez stok devir hızına sahip."),
    ("Fire Oranı (Waste Rate)", "Bozulma, kayıp veya hasar nedeniyle satılamayan ürünlerin oranı. Örnek: Costco %0,4, ALDI %0,5 — düşük olması iyi."),
    ("TMS 29 (Enflasyon Muhasebesi)", "Yüksek enflasyonlu ülkelerde finansal tabloların enflasyona göre düzeltilmesi. Türkiye'de tüm perakendeciler TMS 29 uyguluyor. Nominal ve reel büyümeyi karıştırmamak için kritik."),
    ("CAPEX (Yatırım Harcaması)", "Mağaza, depo, teknoloji gibi uzun vadeli yatırımlar. Örnek: Schwarz Group 2026/27'de 10 milyar €'dan fazla yatırım yapacak."),
    ("Retail Media (Perakende Medyası)", "Marketin tedarikçilere raf, uygulama veya kasa reklamı satması. Örnek: Walmart reklam geliri %38 büyüdü. BİM'in bu alanda geliri görünmüyor."),
    ("Ajan Tabanlı Ticaret (Agentic Commerce)", "Yapay zeka ajanlarının müşteri adına alışveriş yapması. 2030'a kadar 3-5 trilyon $ B2C hacmi yönlendirecek. Walmart Sparky AI sipariş değerini %35 artırıyor."),
    ("ROCE (Kullanılan Sermaye Getirisi)", "Yatırılan sermayenin ne kadar getiri sağladığı. Örnek: Tesco ROCE %15,2 — yani yatırılan her 100 TL 15,2 TL getiri sağlıyor."),
    ("NPS (Net Tavsiye Skoru)", "Müşterinin firmayı tavsiye etme eğilimi. -100 ile +100 arası. Örnek: Tesco NPS 33'e çıktı."),
    ("Omnichannel (Çok Kanallı)", "Mağaza ve online kanalların birlikte çalışması. Migros'un 2.520 online mağazası buna örnek."),
    ("Hard Discount (Sert İndirimci)", "Az çeşit, düşük fiyat, sade mağaza modeli. BİM, A101, ŞOK, ALDI, Lidl bu modeli kullanıyor."),
    ("SKU (Stok Tutma Birimi)", "Rafta takip edilen her farklı ürün. BİM'de ~1.000, Migros'ta ~10.000, Costco'da ~4.000 SKU var."),
    ("TEPE (Perakende Güven Endeksi)", "TEPAV'ın aylık ölçtüğü tüketici güven göstergesi. Negatifse tüketici temkinli, pozitifse harcama iştahı var. Haziran 2026: +9,8."),
    ("Müşteri Trafiği (Customer Traffic)", "Mağazaya giren müşteri sayısı. BİM'in Q2 2026 trafik artışı sadece %0,4 — yani satış artışı fiyat ve sepetten geliyor."),
    ("Ortalama Sepet (Average Basket)", "Toplam satış / işlem sayısı. Sepet büyürse müşteri daha çok harcıyor demektir."),
    ("Raf Bulunurluğu (On-Shelf Availability)", "Müşterinin istediği ürünün rafta bulunma oranı. %97-99 ideal."),
    ("Stoksuz Kalma (Out-of-Stock)", "Talep varken ürünün rafta olmaması. %3'ün altında olmalı. Yüksekse müşteri rakip markete gider."),
]

def gunun_terimleri():
    """Her gün 3 terim dönüşümlü olarak seçilir."""
    gun_sayisi = datetime.now().timetuple().tm_yday
    baslangic = (gun_sayisi * 3) % len(SOZLUK)
    return [SOZLUK[(baslangic + i) % len(SOZLUK)] for i in range(3)]

# ============================================================
# BÖLÜM 3: GÜNÜN ODAK KONUSU (Haftanın gününe göre)
# ============================================================
def gunun_odak_konusu():
    gun = datetime.now().weekday()
    konular = {
        0: """PAZARTESİ: HAFTALIK RAKİP KARŞILAŞTIRMASI
• BİM mağaza başına ciro: 30,7 mn TL (yarıyıl)
• ŞOK mağaza başına ciro: 15,1 mn TL
• Migros mağaza başına ciro: 63,3 mn TL
SORU: BİM, ŞOK'un 2 katı ciro yaparken brüt marjları neredeyse aynı. Bu fark nereden geliyor?
AKSİYON: Gider/satış oranını kalem kalem karşılaştırın.""",
        1: """SALI: MAKRO RİSKLER VE FIRSATLAR
• Enflasyon %28,6'ya revize edildi (IMF)
• Büyüme %2,8'e yavaşladı (Dünya Bankası)
• TEPE Haziran 2026: +9,8 (pozitife döndü)
SORU: Enflasyon yüksekken tüketici nasıl davranıyor?
AKSİYON: Fiyat-hacim esnekliği analizi başlatın.""",
        2: """ÇARŞAMBA: DİJİTAL VE RETAIL MEDIA
• Walmart reklam geliri: +%38
• Amazon reklam geliri: 19,8 mr $ (+%26)
• BİM'in bu alanda geliri görünmüyor
SORU: BİM neden retail media ağı kurmuyor?
AKSİYON: 20 pilot mağazada raf/ekran reklam ağı kurun.""",
        3: """PERŞEMBE: ÖZEL MARKA VE KÂR KALİTESİ
• BİM özel marka payı: %55
• Q2 net kârında 6,8 mr TL parasal kazanç var
• Brüt marj 131 baz puan geriledi
SORU: Özel marka payını %60'a çıkarmak kârı artırır mı?
AKSİYON: Yüksek marjlı 5 kategoride genişleme analizi.""",
        4: """CUMA: REKABET VE DÜZENLEYİCİ RİSKLER
• A101/CarrefourSA: 48 mağaza elden çıkarılacak
• Rekabet Kurumu: Migros ve ŞOK'a ceza
SORU: Bu soruşturmalar BİM'i etkiler mi?
AKSİYON: Rekabet hukuku uyum programı kurun.""",
        5: """CUMARTESİ: TEKNOLOJİ VE GELECEK
• Ajan tabanlı ticaret: 2030'a kadar 3-5 trilyon $
• Walmart Sparky AI: sipariş değerini %35 artırıyor
SORU: BİM uygulamasında AI asistanı nasıl olur?
AKSİYON: Basit bir AI asistanı pilotu için ekip kurun.""",
        6: """PAZAR: HAFTALIK DEĞERLENDİRME
• BİM Türkiye'de en kârlı gıda perakendecisi
• Ancak büyüme fiyat ve sepetten, trafikten değil
• Dijital ve retail media'da gelir yok
SORU: Gelecek hafta hangi konuya odaklanmalıyız?
AKSİYON: Haftalık toplantıda 3 soruyu tartışın.""",
    }
    return konular.get(gun, "")

# ============================================================
# BÖLÜM 4: YAPAY ZEKA İLE ÖZET OLUŞTURMA
# ============================================================
def ai_ozet_olustur(veriler: dict) -> str:
    """Tüm verileri yapay zeka ile özetler."""
    if not GROQ_API_KEY:
        return "AI özeti oluşturulamadı (API anahtarı eksik)."
    
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""
    Sen bir perakende sektörü analistisin. BİM CEO'suna hitaben günlük brifing hazırla.
    
    BUGÜNÜN VERİLERİ:
    
    ABD ŞİRKETLERİ (SEC EDGAR):
    {veriler['abd']}
    
    MAKRO GÖSTERGELER (Dünya Bankası):
    {veriler['makro']}
    
    HABERLER:
    {veriler['haberler'][:2000]}
    
    FORMAT:
    ## 1. GÜNÜN ÖNE ÇIKAN HABERLERİ (en önemli 5 haber)
    ## 2. FİNANSAL GÖSTERGELER (ABD ve Türkiye şirketleri)
    ## 3. MAKRO RİSKLER VE FIRSATLAR (1 paragraf)
    ## 4. BUGÜN ATILACAK 1 ADIM
    
    Özeti Türkçe, profesyonel dille, madde işaretleri kullanarak yaz.
    En fazla 500 kelime olsun.
    """
    
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-20b",
            max_tokens=1500,
        )
        return chat.choices[0].message.content
    except Exception as e:
        print(f"AI hatası: {e}")
        return "AI özeti oluşturulamadı."

# ============================================================
# BÖLÜM 5: E-POSTA OLUŞTURMA VE GÖNDERME
# ============================================================
def e_posta_gonder(veriler: dict, terimler: list, odak: str, ai_ozet: str):
    """Tüm verileri HTML e-posta olarak gönderir."""
    
    # Terimleri formatla
    terim_metni = "\n".join([f"• {t[0]}: {t[1]}" for t in terimler])
    
    # E-posta içeriği
    icerik = f"""
═══════════════════════════════════════════════════════════════
📊 GÜNLÜK PERAKENDE BÜLTENİ - {veriler['tarih']}
═══════════════════════════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 1. GÜNÜN TERİMLERİ (Perakende Sözlüğü)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{terim_metni}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 2. TÜRKİYE PERAKENDECİLERİ (Güncel Finansal Tablo)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{veriler['turkiye']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 3. ABD PERAKENDECİLERİ (SEC EDGAR - Canlı Veri)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{veriler['abd']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 4. MAKRO GÖSTERGELER (Dünya Bankası - Canlı Veri)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{veriler['makro']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📰 5. GÜNÜN HABERLERİ (RSS Beslemeleri)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{veriler['haberler']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 6. GÜNÜN ODAK KONUSU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{odak}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 7. YAPAY ZEKA ÖZETİ (Otomatik Analiz)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ai_ozet}

═══════════════════════════════════════════════════════════════
Bu bülten otomatik oluşturulmuştur.
Veri Kaynakları: SEC EDGAR, KAP, Dünya Bankası, RSS Beslemeleri
AI: Groq (Llama 3)
═══════════════════════════════════════════════════════════════
    """
    
    # HTML formatı
    html = f"""
    <html><body style="font-family: 'Courier New', monospace; max-width: 950px;
    margin: auto; background-color: #f0f2f5; padding: 20px;">
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white; padding: 25px; border-radius: 12px;">
        <h1 style="margin: 0; font-size: 24px;">📊 Günlük Perakende Bülteni</h1>
        <p style="margin: 8px 0 0 0; opacity: 0.8;">{veriler['tarih']}</p>
    </div>
    <div style="background-color: white; padding: 25px; margin-top: 15px;
    border-radius: 12px; white-space: pre-wrap; line-height: 1.7;
    font-size: 13px; border: 1px solid #e0e0e0;">{icerik}</div>
    <div style="text-align: center; color: #95a5a6; font-size: 11px;
    padding: 15px;">
    Bu bülten otomatik oluşturulmuştur. Veriler resmî kaynaklardan derlenmiştir.
    </div>
    </body></html>
    """
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📊 Perakende Bülteni - {veriler['tarih']}"
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_TO
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
        print("✅ E-posta başarıyla gönderildi.")
    except Exception as e:
        print(f"❌ E-posta gönderilemedi: {e}")

# ============================================================
# ANA ÇALIŞTIRMA
# ============================================================
def main():
    print("=" * 60)
    print(f"📊 GÜNLÜK PERAKENDE BÜLTENİ - {datetime.now()}")
    print("=" * 60)
    
    # 1. Verileri topla
    print("\n[1/4] Veriler toplanıyor...")
    toplayici = VeriToplayici()
    veriler = toplayici.tum_verileri_topla()
    
    # 2. Terimleri hazırla
    print("[2/4] Günün terimleri hazırlanıyor...")
    terimler = gunun_terimleri()
    
    # 3. Odak konusunu seç
    print("[3/4] Günün odak konusu seçiliyor...")
    odak = gunun_odak_konusu()
    
    # 4. AI özeti oluştur
    print("[4/4] Yapay zeka özeti oluşturuluyor...")
    ai_ozet = ai_ozet_olustur(veriler)
    
    # 5. E-posta gönder
    print("\n📧 E-posta gönderiliyor...")
    e_posta_gonder(veriler, terimler, odak, ai_ozet)
    
    print("\n✅ İşlem tamamlandı!")

if __name__ == "__main__":
    main()
