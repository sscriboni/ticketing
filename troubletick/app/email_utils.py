import os
import mimetypes
import smtplib
import traceback
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
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

def send_email_async(
    dest_email: str, 
    subject: str, 
    body: str, 
    reason: str = None, 
    cc_email: str = None, 
    bcc_email: str = None,
    attachment_path: str = None
):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    motivazione = reason if reason else subject
    
    # Preparazione e normalizzazione liste destinatari
    to_list = [e.strip() for e in str(dest_email or "").split(",") if e.strip()]
    
    cc_list = []
    if cc_email:
        if isinstance(cc_email, (list, tuple, set)):
            cc_list = [e.strip() for e in cc_email if e and str(e).strip()]
        else:
            cc_list = [e.strip() for e in str(cc_email).split(",") if e.strip()]
            
    bcc_list = []
    if bcc_email:
        if isinstance(bcc_email, (list, tuple, set)):
            bcc_list = [e.strip() for e in bcc_email if e and str(e).strip()]
        else:
            bcc_list = [e.strip() for e in str(bcc_email).split(",") if e.strip()]

    cc_log = f" (CC: {', '.join(cc_list)})" if cc_list else ""
    bcc_log = f" (BCC: {', '.join(bcc_list)})" if bcc_list else ""
    
    # Validazione Indirizzo Destinatario Principale
    if not to_list:
        err_msg = f"[{now_str}] FAILURE - Dest: (Mancante) - Motivo: {motivazione} - Errore: Indirizzo email destinatario mancante o vuoto"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    dest_email_header = ", ".join(to_list)
    
    # Controllo Configurazione Server SMTP
    smtp_server = CFG.get("smtp_server")
    if not smtp_server or not str(smtp_server).strip():
        skip_msg = f"[{now_str}] SKIPPED - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} (SMTP non configurato)"
        _log_email_event(skip_msg)
        return False
        
    sender_email = CFG.get("helpdesk_email", "noreply@troubletick.local")
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = dest_email_header
        if cc_list:
            msg['Cc'] = ", ".join(cc_list)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        # Allegato facoltativo
        if attachment_path and os.path.isfile(attachment_path):
            try:
                filename = os.path.basename(attachment_path)
                ctype, encoding = mimetypes.guess_type(attachment_path)
                if ctype is None or encoding is not None:
                    ctype = 'application/octet-stream'
                maintype, subtype = ctype.split('/', 1)

                with open(attachment_path, 'rb') as f:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)
            except Exception as att_err:
                print(f"Avviso: Impossibile allegare file {attachment_path}: {att_err}")
    except Exception as err:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} - Errore Formattazione Messaggio ({type(err).__name__}): {str(err)}"
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
            
        # Lista cumulativa di tutti i destinatari effettivi per il trasporto SMTP
        # (I destinatari BCC non sono presenti negli header To/Cc del messaggio per preservare la privacy)
        all_recipients = list(dict.fromkeys(to_list + cc_list + bcc_list))

        server.send_message(msg, to_addrs=all_recipients)
        server.quit()
        
        success_msg = f"[{now_str}] SUCCESS - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione}"
        _log_email_event(success_msg)
        return True

    except smtplib.SMTPAuthenticationError as e:
        smtp_err_text = e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} - Errore Autenticazione SMTP ({e.smtp_code}): {smtp_err_text}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except smtplib.SMTPRecipientsRefused as e:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} - Errore Rifiuto Destinatario: {str(e.recipients)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except smtplib.SMTPServerDisconnected as e:
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} - Errore Disconnessione Server SMTP: {str(e)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False

    except Exception as e:
        err_detail = f"{type(e).__name__}: {str(e)}"
        err_msg = f"[{now_str}] FAILURE - Dest: {dest_email_header}{cc_log}{bcc_log} - Motivo: {motivazione} - Errore Invio SMTP: {err_detail}"
        print(f"Errore invio email ticket: {err_detail}")
        _log_email_event(err_msg)
        return False

# Alias di compatibilità
send_email = send_email_async
