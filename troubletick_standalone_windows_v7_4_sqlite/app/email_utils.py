import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from core import CFG

def send_email_async(dest_email: str, subject: str, body: str):
    if not CFG.get("smtp_server"):
        return
    msg = MIMEMultipart()
    msg['From'] = CFG.get("helpdesk_email", "noreply@troubletick.local")
    msg['To'] = dest_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))
    
    try:
        port = int(CFG.get("smtp_port") or 25)
        server = smtplib.SMTP(CFG.get("smtp_server"), port)
        if CFG.get("smtp_tls"):
            server.starttls()
        user = CFG.get("smtp_user")
        pwd = CFG.get("smtp_password")
        if user and pwd:
            server.login(user, pwd)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Errore invio email ticket: {e}")