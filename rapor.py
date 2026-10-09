import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
from groq import Groq
from datetime import datetime
import re

# API ve E-posta Ayarları
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

def perakende_haberleri_topla():
    """Sadece perakende sektörüne odaklanan kaynaklardan haber toplar."""
    rss_kaynaklari = [
        # Uluslararası perakende
        {"url": "https://www.retailtechnology.co.uk/rss.xml", "kategori": "Uluslararası Perakende Teknolojisi"},
        {"url": "https://retailgazette.com/feed/", "kategori": "Uluslararası Perakende"},
        # Türkiye perakende
        {"url": "https://perakendesektoru.com/feed/", "kategori": "Türkiye Perakende Gündemi"},
        {"url": "https://ekonomikgundem.com.tr/tag/gida-perakende/feed/", "kategori": "Türkiye Gıda Perakende"},
        # Resmi kurumlar
        {"url": "https://www.tusiad.org/tr/yayinlar/raporlar/itemlist/tag/Perakende%20CG?format=feed", "kategori": "TÜSİAD Perakende Raporları"},
    ]
    
    haberler = []
    for kaynak in rss_kaynaklari:
        try:
            feed = feedparser.parse(kaynak["url"])
            for entry in feed.entries[:8]:  # Her kaynaktan son 8 haber
                ozet = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:400]
                haberler.append(f"[{kaynak['kategori']}] {entry.title}\n{ozet}...")
        except Exception as e:
            print(f"RSS Hatası ({kaynak['url']}): {e}")
    
    return "\n\n".join(haberler)

def yonetici_ozeti_olustur(haber_metni):
    """Perakende sektörüne özel yönetici özeti oluşturur."""
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""
    Sen bir perakende sektörü analistisin. Aşağıda uluslararası ve Türkiye perakende sektöründen derlenmiş güncel haberler yer alıyor.
    
    Bu haberleri kullanarak bir YÖNETİCİ ÖZETİ hazırla. Özet şu bölümlerden oluşsun:
    
    ## 1. ULUSLARARASI PERAKENDECİLER
    Walmart, Costco, Amazon, Carrefour, Tesco, Kroger, ALDI, Lidl, Schwarz Group gibi küresel perakendecilerle ilgili öne çıkan gelişmeler.
    
    ## 2. TÜRKİYE PERAKENDECİLERİ
    BİM, A101, Şok, Migros, CarrefourSA hakkında finansal sonuçlar, mağaza açılışları, stratejik hamleler.
    
    ## 3. RESMİ KURUMLAR VE SEKTÖREL VERİLER
    TÜİK, TEPAV, Rekabet Kurumu, TÜSİAD gibi kurumların perakende sektörüne yönelik açıklamaları ve verileri.
    
    ## 4. SEKTÖRÜ BEKLEYEN TEHDİTLER
    Enflasyon, maliyet baskısı, rekabet soruşturmaları, tüketici harcamalarındaki daralma, tedarik zinciri riskleri.
    
    ## 5. FIRSATLAR VE MÜŞTERİ BEKLENTİLERİ
    Yapay zeka, hızlı ticaret, özel marka, sürdürülebilirlik, omnichannel gibi alanlardaki fırsatlar.
    
    ## 6. STRATEJİK ÇIKARIMLAR
    Yönetici olarak atılması gereken adımlar ve proje önerileri.
    
    HABERLER:
    {haber_metni}
    
    Özeti Türkçe olarak, profesyonel bir dille ve madde işaretleri kullanarak yaz.
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-20b",
    )
    return chat_completion.choices[0].message.content

def mail_gonder(icerik):
    """HTML formatında e-posta gönderir."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📊 Günlük Perakende Yönetici Özeti - {datetime.now().strftime('%d.%m.%Y')}"
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_TO

    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 900px; margin: auto;">
    <h2 style="color: #2c3e50;">📊 Günlük Perakende Yönetici Özeti</h2>
    <p style="color: #7f8c8d;">{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
    <hr>
    <div style="white-space: pre-wrap; line-height: 1.6;">{icerik}</div>
    <hr>
    <p style="font-size: 12px; color: #95a5a6;">Bu rapor otomatik olarak oluşturulmuştur. Kaynak: Retail Technology, Retail Gazette, Perakende Sektörü, Ekonomik Gündem, TÜSİAD.</p>
    </body></html>
    """
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
        print("E-posta başarıyla gönderildi.")
    except Exception as e:
        print(f"E-posta gönderilemedi: {e}")

if __name__ == "__main__":
    print("Perakende haberleri toplanıyor...")
    haberler = perakende_haberleri_topla()
    print("Yapay zeka perakende özeti çıkarıyor...")
    ozet = yonetici_ozeti_olustur(haberler)
    print("E-posta gönderiliyor...")
    mail_gonder(ozet)
