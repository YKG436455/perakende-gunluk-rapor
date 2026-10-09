# -*- coding: utf-8 -*-
"""
TAM OTOMATİK GÜNLÜK PERAKENDE BÜLTENİ (Excel Ekli + HTML Tablolu)
"""

import os
import smtplib
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
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

SEC_HEADERS = {
    "User-Agent": "PerakendeBulten/1.0 (iletisim@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

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
            if resp.status_code == 200:
                data = resp.json()
                gelirler = data.get("facts", {}).get("us-gaap", {}).get(
                    "Revenues", {}
                ).get("units", {}).get("USD", [])
                if not gelirler:
                    gelirler = data.get("facts", {}).get("us-gaap", {}).get(
                        "RevenueFromContractWithCustomerExcludingAssessedTax", {}
                    ).get("units", {}).get("USD", [])
                son_gelir = gelirler[-1] if gelirler else {}
                return {
                    "sirket": sirket_adi,
                    "gelir_mr": round(son_gelir.get("val", 0) / 1e9, 1),
                    "donem": son_gelir.get("end", "Bilinmiyor"),
                }
        except Exception as e:
            print(f"SEC hatası ({sirket_adi}): {e}")
        return {"sirket": sirket_adi, "gelir_mr": 0, "donem": "Veri yok"}
    
    def abd_sirketleri(self) -> pd.DataFrame:
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
                sonuclar.append(veri)
                time.sleep(0.2)
            except Exception as e:
                print(f"Hata: {e}")
        return pd.DataFrame(sonuclar)
    
    def turkiye_sirketleri(self) -> pd.DataFrame:
        """Türkiye şirket verileri (çeyrekte bir manuel güncellenir)."""
        data = {
            "Firma": ["BİM", "Migros", "ŞOK"],
            "Dönem": ["H1 2026", "Q2 2026", "H1 2026"],
            "Satış": ["449,7 mr TL", "124,4 mr TL", "167,8 mr TL"],
            "Mağaza": [14851, 3830, 11175],
            "LFL": ["+%37,3", "Negatif", "+%5"],
            "Net Kâr": ["+15,1 mr TL", "-699 mn TL", "-1,35 mr TL"],
        }
        return pd.DataFrame(data)
    
    def makro_gostergeler(self) -> pd.DataFrame:
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
                            sonuclar.append({"Gösterge": ad, "Değer": f"{deger:.1f}", "Yıl": yil})
            except Exception as e:
                print(f"Dünya Bankası hatası: {e}")
        return pd.DataFrame(sonuclar)
    
    def rss_haberleri(self) -> list:
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
                    ozet = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:250]
                    haberler.append({
                        "Kategori": kategori,
                        "Başlık": entry.title,
                        "Özet": ozet
                    })
            except Exception as e:
                print(f"RSS hatası ({kategori}): {e}")
        return haberler

# ============================================================
# BÖLÜM 2: PERAKENDE SÖZLÜĞÜ
# ============================================================
SOZLUK = [
    ("LFL (Like-for-Like)", "Aynı mağaza satış büyümesi. Yeni açılan/kapanan mağazaları hariç tutarak mevcut mağazaların büyümesini gösterir. BİM Q2 2026: +%37,3"),
    ("Brüt Kâr Marjı", "Satıştan malın maliyeti düşüldükten sonra kalan tutarın satışa oranı. BİM: %19,1"),
    ("FAVÖK / EBITDA", "Faiz, Vergi, Amortisman ve İtfa öncesi kâr. BİM FAVÖK marjı: %5,4"),
    ("Özel Marka (Private Label)", "Marketin kendi markasıyla sattığı ürünler. BİM: %55"),
    ("Stok Devir Hızı", "Stokun yılda kaç kez satılıp yenilendiği. ALDI: 12, A101: 14"),
    ("Fire Oranı", "Bozulma/kayıp nedeniyle satılamayan ürün oranı. Costco: %0,4"),
    ("TMS 29", "Yüksek enflasyonlu ülkelerde finansal tabloların enflasyona göre düzeltilmesi."),
    ("CAPEX", "Mağaza, depo, teknoloji gibi uzun vadeli yatırımlar. Schwarz: 10 mr €+"),
    ("Retail Media", "Marketin tedarikçilere raf/uygulama reklamı satması. Walmart: +%38"),
    ("Ajan Tabanlı Ticaret", "Yapay zeka ajanlarının müşteri adına alışveriş yapması. 2030: 3-5 trilyon $"),
    ("ROCE", "Kullanılan sermayenin getirisi. Tesco: %15,2"),
    ("NPS", "Net Tavsiye Skoru. Tesco: 33"),
    ("Omnichannel", "Mağaza ve online kanalların birlikte çalışması. Migros: 2.520 online mağaza"),
    ("Hard Discount", "Az çeşit, düşük fiyat, sade mağaza. BİM, A101, ŞOK, ALDI, Lidl"),
    ("SKU", "Stok Tutma Birimi. BİM: ~1.000, Migros: ~10.000"),
    ("TEPE", "TEPAV Perakende Güven Endeksi. Haziran 2026: +9,8"),
    ("Müşteri Trafiği", "Mağazaya giren müşteri sayısı. BİM: +%0,4"),
    ("Ortalama Sepet", "Toplam satış / işlem sayısı."),
    ("Raf Bulunurluğu", "Müşterinin istediği ürünün rafta bulunma oranı. İdeal: %97-99"),
    ("Stoksuz Kalma", "Talep varken ürünün rafta olmaması. İdeal: <%3"),
]

def gunun_terimleri():
    gun_sayisi = datetime.now().timetuple().tm_yday
    baslangic = (gun_sayisi * 3) % len(SOZLUK)
    return [SOZLUK[(baslangic + i) % len(SOZLUK)] for i in range(3)]

# ============================================================
# BÖLÜM 3: GÜNÜN ODAK KONUSU
# ============================================================
def gunun_odak_konusu():
    gun = datetime.now().weekday()
    konular = {
        0: ("PAZARTESİ - HAFTALIK RAKİP KARŞILAŞTIRMASI",
            ["BİM mağaza başına ciro: 30,7 mn TL (yarıyıl)",
             "ŞOK mağaza başına ciro: 15,1 mn TL",
             "Migros mağaza başına ciro: 63,3 mn TL"],
            "BİM, ŞOK'un 2 katı ciro yaparken brüt marjları neredeyse aynı. Bu fark nereden geliyor?",
            "Gider/satış oranını kalem kalem karşılaştırın."),
        1: ("SALI - MAKRO RİSKLER VE FIRSATLAR",
            ["Enflasyon %28,6'ya revize edildi (IMF)",
             "Büyüme %2,8'e yavaşladı (Dünya Bankası)",
             "TEPE Haziran 2026: +9,8 (pozitife döndü)"],
            "Enflasyon yüksekken tüketici nasıl davranıyor?",
            "Fiyat-hacim esnekliği analizi başlatın."),
        2: ("ÇARŞAMBA - DİJİTAL VE RETAIL MEDIA",
            ["Walmart reklam geliri: +%38",
             "Amazon reklam geliri: 19,8 mr $ (+%26)",
             "BİM'in bu alanda geliri görünmüyor"],
            "BİM neden retail media ağı kurmuyor?",
            "20 pilot mağazada raf/ekran reklam ağı kurun."),
        3: ("PERŞEMBE - ÖZEL MARKA VE KÂR KALİTESİ",
            ["BİM özel marka payı: %55",
             "Q2 net kârında 6,8 mr TL parasal kazanç var",
             "Brüt marj 131 baz puan geriledi"],
            "Özel marka payını %60'a çıkarmak kârı artırır mı?",
            "Yüksek marjlı 5 kategoride genişleme analizi."),
        4: ("CUMA - REKABET VE DÜZENLEYİCİ RİSKLER",
            ["A101/CarrefourSA: 48 mağaza elden çıkarılacak",
             "Rekabet Kurumu: Migros ve ŞOK'a ceza"],
            "Bu soruşturmalar BİM'i etkiler mi?",
            "Rekabet hukuku uyum programı kurun."),
        5: ("CUMARTESİ - TEKNOLOJİ VE GELECEK",
            ["Ajan tabanlı ticaret: 2030'a kadar 3-5 trilyon $",
             "Walmart Sparky AI: sipariş değerini %35 artırıyor"],
            "BİM uygulamasında AI asistanı nasıl olur?",
            "Basit bir AI asistanı pilotu için ekip kurun."),
        6: ("PAZAR - HAFTALIK DEĞERLENDİRME",
            ["BİM Türkiye'de en kârlı gıda perakendecisi",
             "Ancak büyüme fiyat ve sepetten, trafikten değil",
             "Dijital ve retail media'da gelir yok"],
            "Gelecek hafta hangi konuya odaklanmalıyız?",
            "Haftalık toplantıda 3 soruyu tartışın."),
    }
    return konular.get(gun, konular[0])

# ============================================================
# BÖLÜM 4: AI ÖZETİ
# ============================================================
def ai_ozet_olustur(abd_df, makro_df, haberler):
    if not GROQ_API_KEY:
        return "AI özeti oluşturulamadı."
    
    client = Groq(api_key=GROQ_API_KEY)
    
    abd_metin = abd_df.to_string(index=False) if not abd_df.empty else "Veri yok"
    makro_metin = makro_df.to_string(index=False) if not makro_df.empty else "Veri yok"
    haber_metin = "\n".join([f"- {h['Başlık']}" for h in haberler[:10]])
    
    prompt = f"""
    Sen bir perakende sektörü analistisin. BİM CEO'suna günlük brifing hazırla.
    
    ABD ŞİRKETLERİ (SEC EDGAR):
    {abd_metin}
    
    MAKRO GÖSTERGELER:
    {makro_metin}
    
    HABERLER:
    {haber_metin}
    
    Şu formatta yaz (en fazla 400 kelime):
    
    ## GÜNÜN ÖNE ÇIKAN HABERLERİ
    (En önemli 5 haber, kısa açıklamalarla)
    
    ## FİNANSAL GÖRÜNÜM
    (ABD ve Türkiye şirketleriyle ilgili 2-3 cümle)
    
    ## RİSKLER VE FIRSATLAR
    (1 paragraf)
    
    ## BUGÜN ATILACAK ADIM
    (Tek somut aksiyon)
    
    Türkçe, profesyonel dille yaz.
    """
    
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-20b",
            max_tokens=1200,
        )
        return chat.choices[0].message.content
    except Exception as e:
        print(f"AI hatası: {e}")
        return "AI özeti oluşturulamadı."

# ============================================================
# BÖLÜM 5: HTML TABLO YARDIMCISI
# ============================================================
def df_to_html_table(df: pd.DataFrame, baslik: str) -> str:
    """DataFrame'i güzel HTML tabloya çevirir."""
    if df.empty:
        return f"<p><em>{baslik}: Veri yok</em></p>"
    
    html = f'<h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">{baslik}</h3>'
    html += '<table style="border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px;">'
    html += '<thead><tr style="background-color: #34495e; color: white;">'
    for col in df.columns:
        html += f'<th style="padding: 10px; text-align: left; border: 1px solid #bdc3c7;">{col}</th>'
    html += '</tr></thead><tbody>'
    
    for i, row in df.iterrows():
        bg = "#f8f9fa" if i % 2 == 0 else "white"
        html += f'<tr style="background-color: {bg};">'
        for val in row:
            html += f'<td style="padding: 8px; border: 1px solid #ecf0f1;">{val}</td>'
        html += '</tr>'
    
    html += '</tbody></table>'
    return html

def haberler_to_html(haberler: list) -> str:
    """Haberleri HTML listeye çevirir."""
    if not haberler:
        return "<p><em>Bugün yeni haber bulunamadı.</em></p>"
    
    html = '<h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">📰 Günün Haberleri</h3>'
    html += '<ul style="list-style: none; padding: 0;">'
    for h in haberler[:8]:
        html += f'''
        <li style="padding: 10px; margin: 5px 0; background: #f8f9fa; 
        border-left: 4px solid #3498db; border-radius: 4px;">
            <strong style="color: #2c3e50;">[{h['Kategori']}] {h['Başlık']}</strong><br>
            <span style="color: #7f8c8d; font-size: 12px;">{h['Özet']}...</span>
        </li>
        '''
    html += '</ul>'
    return html

# ============================================================
# BÖLÜM 6: EXCEL DOSYASI OLUŞTUR
# ============================================================
def excel_olustur(abd_df, tr_df, makro_df, haberler) -> BytesIO:
    """Tüm verileri tek Excel dosyasında toplar."""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sayfa 1: ABD Şirketleri
        if not abd_df.empty:
            abd_df.to_excel(writer, sheet_name='ABD Sirketleri', index=False)
        
        # Sayfa 2: Türkiye Şirketleri
        tr_df.to_excel(writer, sheet_name='Turkiye Sirketleri', index=False)
        
        # Sayfa 3: Makro Göstergeler
        if not makro_df.empty:
            makro_df.to_excel(writer, sheet_name='Makro Gostergeler', index=False)
        
        # Sayfa 4: Haberler
        if haberler:
            pd.DataFrame(haberler).to_excel(writer, sheet_name='Haberler', index=False)
    
    output.seek(0)
    return output

# ============================================================
# BÖLÜM 7: E-POSTA GÖNDER
# ============================================================
def e_posta_gonder(abd_df, tr_df, makro_df, haberler, terimler, odak_tuple, ai_ozet):
    tarih = datetime.now().strftime('%d.%m.%Y %A')
    
    odak_baslik, odak_maddeler, odak_soru, odak_aksiyon = odak_tuple
    odak_html = f'''
    <h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">
    🎯 Günün Odak Konusu: {odak_baslik}</h3>
    <ul>'''
    for m in odak_maddeler:
        odak_html += f'<li>{m}</li>'
    odak_html += f'''</ul>
    <p style="background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; border-radius: 4px;">
    <strong>SORU:</strong> {odak_soru}</p>
    <p style="background: #d4edda; padding: 10px; border-left: 4px solid #28a745; border-radius: 4px;">
    <strong>AKSİYON:</strong> {odak_aksiyon}</p>
    '''
    
    terim_html = '<h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">📖 Günün Terimleri</h3><ul>'
    for terim, aciklama in terimler:
        terim_html += f'<li style="padding: 8px; margin: 5px 0; background: #f8f9fa; border-radius: 4px;"><strong>{terim}:</strong> {aciklama}</li>'
    terim_html += '</ul>'
    
    ai_html = ai_ozet.replace('\n', '<br>').replace('##', '<h4 style="color: #2c3e50;">').replace('<h4', '</h4><h4')
    
    html_body = f'''
    <html><body style="font-family: Arial, Helvetica, sans-serif; max-width: 950px; 
    margin: auto; background-color: #ecf0f1; padding: 20px;">
    
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); 
    color: white; padding: 25px; border-radius: 12px;">
        <h1 style="margin: 0; font-size: 24px;">📊 Günlük Perakende Bülteni</h1>
        <p style="margin: 8px 0 0 0; opacity: 0.9;">{tarih}</p>
    </div>
    
    <div style="background: white; padding: 25px; margin-top: 15px; border-radius: 12px;">
    {terim_html}
    </div>
    
    <div style="background: white; padding: 25px; margin-top: 15px; border-radius: 12px;">
    {df_to_html_table(tr_df, "🇹🇷 Türkiye Perakendecileri")}
    {df_to_html_table(abd_df, "🌍 ABD Perakendecileri (SEC EDGAR - Canlı)")}
    {df_to_html_table(makro_df, "📈 Makro Göstergeler (Dünya Bankası - Canlı)")}
    </div>
    
    <div style="background: white; padding: 25px; margin-top: 15px; border-radius: 12px;">
    {haberler_to_html(haberler)}
    </div>
    
    <div style="background: white; padding: 25px; margin-top: 15px; border-radius: 12px;">
    {odak_html}
    </div>
    
    <div style="background: white; padding: 25px; margin-top: 15px; border-radius: 12px;">
    <h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">🤖 Yapay Zeka Analizi</h3>
    <div style="line-height: 1.7; color: #333;">{ai_html}</div>
    </div>
    
    <div style="background: #34495e; color: white; padding: 15px; margin-top: 15px; 
    border-radius: 12px; font-size: 11px; text-align: center;">
    Bu bülten otomatik oluşturulmuştur.<br>
    Veri Kaynakları: SEC EDGAR, KAP, Dünya Bankası, RSS Beslemeleri<br>
    📎 Detaylı veriler Excel ektedir.
    </div>
    
    </body></html>
    '''
    
    # E-posta oluştur
    msg = MIMEMultipart('mixed')
    msg['Subject'] = f"📊 Perakende Bülteni - {datetime.now().strftime('%d.%m.%Y')}"
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_TO
    
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    # Excel eki
    try:
        excel_data = excel_olustur(abd_df, tr_df, makro_df, haberler)
        excel_ek = MIMEApplication(excel_data.read(), _subtype='xlsx')
        excel_ek.add_header('Content-Disposition', 'attachment', 
                            filename=f'perakende_verileri_{datetime.now().strftime("%Y%m%d")}.xlsx')
        msg.attach(excel_ek)
        print("✅ Excel eki hazırlandı.")
    except Exception as e:
        print(f"Excel eki hatası: {e}")
    
    # Gönder
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
    
    toplayici = VeriToplayici()
    
    print("\n[1/6] ABD şirket verileri çekiliyor...")
    abd_df = toplayici.abd_sirketleri()
    
    print("[2/6] Türkiye şirket verileri hazırlanıyor...")
    tr_df = toplayici.turkiye_sirketleri()
    
    print("[3/6] Makro veriler çekiliyor...")
    makro_df = toplayici.makro_gostergeler()
    
    print("[4/6] Haberler toplanıyor...")
    haberler = toplayici.rss_haberleri()
    
    print("[5/6] Terimler ve odak konusu hazırlanıyor...")
    terimler = gunun_terimleri()
    odak = gunun_odak_konusu()
    
    print("[6/6] AI özeti oluşturuluyor...")
    ai_ozet = ai_ozet_olustur(abd_df, makro_df, haberler)
    
    print("\n📧 E-posta ve Excel gönderiliyor...")
    e_posta_gonder(abd_df, tr_df, makro_df, haberler, terimler, odak, ai_ozet)
    
    print("\n✅ İşlem tamamlandı!")

if __name__ == "__main__":
    main()
