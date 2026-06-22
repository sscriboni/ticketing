import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from core import CFG, BASE_DIR

def send_email_async(dest_email: str, subject: str, body: str, reason: str = None):
    log_file_path = os.path.join(BASE_DIR, "emails.log")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    motivazione = reason if reason else subject
    
    if not CFG.get("smtp_server"):
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] SKIPPED - Dest: {dest_email} - Motivo: {motivazione} (SMTP non configurato)\n")
        except Exception:
            pass
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
        
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] SUCCESS - Dest: {dest_email} - Motivo: {motivazione}\n")
        except Exception:
            pass
    except Exception as e:
        print(f"Errore invio email ticket: {e}")
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] FAILURE - Dest: {dest_email} - Motivo: {motivazione} - Errore: {str(e)}\n")
        except Exception:
            pass