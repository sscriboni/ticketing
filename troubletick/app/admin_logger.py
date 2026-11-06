import os
from datetime import datetime
from fastapi import Request
from core import LOG_DIR

# Scrive sia su admin_log che su admin_log.log per garantire massima compatibilità
ADMIN_LOG_FILES = [
    os.path.join(LOG_DIR, "admin_log"),
    os.path.join(LOG_DIR, "admin_log.log")
]

def get_admin_log_filepath() -> str:
    """Restituisce il path del file log preferenziale esistente o il primo di default"""
    for p in ADMIN_LOG_FILES:
        if os.path.exists(p):
            return p
    return ADMIN_LOG_FILES[0]

def get_client_ip(request: Request) -> str:
    """Estrae in modo affidabile l'IP del client anche dietro proxy / reverse proxy"""
    if not request:
        return "Sconosciuto"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "Sconosciuto"

def log_admin_action(user_or_req, azione: str, dettagli: str = "", esito: str = "SUCCESS"):
    """
    Traccia un'operazione amministrativa sul file admin_log.
    user_or_req può essere un oggetto Request di FastAPI oppure un dizionario utente.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = "N/D"
    username = "Sistema"
    uid = "N/D"
    ruolo = "N/D"

    if isinstance(user_or_req, Request):
        ip = get_client_ip(user_or_req)
        user = None
        try:
            if hasattr(user_or_req, "session"):
                user = user_or_req.session.get("user")
        except Exception:
            user = None
        if user:
            username = user.get("username", "Anonimo")
            uid = user.get("id") or user.get("user_id") or "N/D"
            ruolo = user.get("ruolo", "N/D")
    elif isinstance(user_or_req, dict):
        user = user_or_req
        username = user.get("username", "Anonimo")
        uid = user.get("id") or user.get("user_id") or "N/D"
        ruolo = user.get("ruolo", "N/D")

    dettagli_str = f" | {str(dettagli).strip()}" if dettagli else ""
    log_line = f"[{now}] [IP: {ip}] [ADMIN: {username} (ID: {uid}, Ruolo: {ruolo})] [{esito}] [{azione}]{dettagli_str}\n"

    for path in ADMIN_LOG_FILES:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(f"Errore scrittura admin_log su {path}:", e)

def get_recent_admin_logs(limit: int = 300) -> list[str]:
    """Legge le ultime righe dal file di log delle operazioni amministrative"""
    filepath = get_admin_log_filepath()
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return lines[-limit:]
    except Exception as e:
        return [f"Errore lettura log: {e}"]
