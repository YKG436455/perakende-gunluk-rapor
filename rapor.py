import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
from groq import Groq
from datetime import datetime
import re

# API ve E-posta Ayarları (GitHub Secrets'tan gelecek)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAIL_USER = os.environ.get("MAIL_USER")
MAIL_PASS = os.environ.get("MAIL_PASS")
MAIL_TO = os.environ.get("MAIL_TO")

def haberleri_topla():
    rss_kaynaklari = [
        "https://www.retaildive.com/feeds/news/",
        "https://www.retailgazette.co.uk/feed/",
        "https://www.dunya.com/rss/perakende"
    ]
    haberler = []
    for url in rss_kaynaklari:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]: # Her kaynaktan son 5 haber
                ozet = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:300]
                haberler.append(f"- {entry.title} ({ozet}...)")
        except Exception as e:
            print(f"RSS Hatası ({url}): {e}")
    return "\n".join(haberler)

def yonetici_ozeti_olustur(haber_metni):
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
    Aşağıda perakende sektörüyle ilgili son haberler yer alıyor.
    Bunları kullanarak bir yönetici özeti hazırla. Özet şu bölümlerden oluşsun:
    1. GÜNLÜK ÖNE ÇIKAN HABERLER (en önemli 5 haber, kısa açıklamalarla)
    2. STRATEJİK ÇIKARIMLAR (1-2 paragraf)
    3. RİSKLER VE FIRSATLAR
    
    HABERLER:
    {haber_metni}
    
    Özeti Türkçe olarak, profesyonel bir dille yaz.
    """
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
    )
    return chat_completion.choices[0].message.content

def mail_gonder(icerik):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📊 Günlük Perakende Yönetici Özeti - {datetime.now().strftime('%d.%m.%Y')}"
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_TO

    html = f"""
    <html><body style="font-family: Arial, sans-serif;">
    <h2>📊 Günlük Perakende Yönetici Özeti</h2>
    <p>{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
    <hr>
    <div style="white-space: pre-wrap;">{icerik}</div>
    <hr>
    <p style="font-size: 12px; color: gray;">Bu rapor otomatik olarak oluşturulmuştur.</p>
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
    print("Haberler toplanıyor...")
    haberler = haberleri_topla()
    print("Yapay zeka özet çıkarıyor...")
    ozet = yonetici_ozeti_olustur(haberler)
    print("E-posta gönderiliyor...")
    mail_gonder(ozet)
