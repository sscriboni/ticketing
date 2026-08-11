import os
import smtplib
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from core import CFG, BASE_DIR, LOG_DIR

def _log_email_event(log_message: str):
    """Scrive un messaggio sia su emails.log che su app_events.log per garantire il tracciamento completo"""
    log_file_path = os.path.join(LOG_DIR, "emails.log")
    app_events_path = os.path.join(LOG_DIR, "app_events.log")
    
    for path in [log_file_path, app_events_path]:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        except Exception:
            pass

def send_email_async(dest_email: str, subject: str, body: str, reason: str = None, cc_email: str = None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    motivazione = reason if reason else subject
    cc_log = f" (CC: {cc_email})" if cc_email else ""
    
    # Validazione Indirizzo Destinatario
    if not dest_email or not str(dest_email).strip():
        err_msg = f"[{now_str}] FAILURE - Dest: (Mancante) - Motivo: {motivazione} - Errore: Indirizzo email destinatario mancante o vuoto"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    dest_email = str(dest_email).strip()
    
    # Controllo Configurazione Server SMTP
    smtp_server = CFG.get("smtp_server")
    if not smtp_server or not str(smtp_server).strip():
        skip_msg = f"[{now_str}] SKIPPED - Dest: {dest_email}{cc_log} - Motivo: {motivazione} (SMTP non configurato)"
        _log_email_event(skip_msg)
        return False
        
    sender_email = CFG.get("helpdesk_email", "noreply@troubletick.local")
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = dest_email
        if cc_email:
            msg['Cc'] = cc_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
    except Exception as err:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email}{cc_log} - Motivo: {motivazione} - Errore Formattazione Messaggio ({type(err).__name__}): {str(err)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False
    
    try:
        port_val = CFG.get("smtp_port") or 25
        try:
            port = int(port_val)
        except (ValueError, TypeError):
            port = 25

        server = smtplib.SMTP(str(smtp_server).strip(), port, timeout=15)
        
        if CFG.get("smtp_tls"):
            server.starttls()
            
        user = CFG.get("smtp_user")
        pwd = CFG.get("smtp_password")
        if user and pwd:
            server.login(str(user), str(pwd))
            
        server.send_message(msg)
        server.quit()
        
        success_msg = f"[{now_str}] SUCCESS - Dest: {dest_email}{cc_log} - Motivo: {motivazione}"
        _log_email_event(success_msg)
        return True

    except smtplib.SMTPAuthenticationError as e:
        smtp_err_text = e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email}{cc_log} - Motivo: {motivazione} - Errore Autenticazione SMTP ({e.smtp_code}): {smtp_err_text}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except smtplib.SMTPRecipientsRefused as e:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email}{cc_log} - Motivo: {motivazione} - Errore Rifiuto Destinatario: {str(e.recipients)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except smtplib.SMTPServerDisconnected as e:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email}{cc_log} - Motivo: {motivazione} - Errore Disconnessione Server SMTP: {str(e)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except Exception as e:
        err_detail = f"{type(e).__name__}: {str(e)}"
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email}{cc_log} - Motivo: {motivazione} - Errore Invio SMTP: {err_detail}"
        print(f"Errore invio email ticket: {err_detail}")
        _log_email_event(err_msg)
        return False

# Alias di compatibilità
send_email = send_email_async