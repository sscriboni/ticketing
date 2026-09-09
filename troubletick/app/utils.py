import bcrypt
import os, shutil, uuid
from fastapi import Request, UploadFile
from fastapi.responses import RedirectResponse
from core import UPLOAD_DIR

def ok(password: str, hashed: str) -> bool:
    if not hashed or not password:
        return False
    hashed = str(hashed).strip()
    try:
        if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        return password == hashed
    except Exception:
        return False

def current_user(r: Request):
    return r.session.get("user")

def require_superuser(r: Request):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/tickets")
    return user

def user_has_tag(user: dict, tag_name: str) -> bool:
    """Verifica se l'utente possiede uno specifico tag assegnato (case-insensitive)"""
    if not user:
        return False
    uid = user.get("id") or user.get("user_id")
    if not uid:
        return False
    try:
        from core import engine
        from sqlalchemy import text
        with engine.connect() as c:
            count = c.execute(text("""
                SELECT COUNT(*) 
                FROM operatori_tag ot
                JOIN tag_operatori t ON ot.tag_id = t.tag_id
                WHERE ot.user_id = :uid AND UPPER(t.nome) = :tag_name
            """), {"uid": uid, "tag_name": tag_name.strip().upper()}).scalar() or 0
            return count > 0
    except Exception:
        return False

def user_has_tag_dec(user: dict) -> bool:
    """Verifica se l'utente possiede il tag DEC assegnato"""
    return user_has_tag(user, "DEC")

def user_has_tag_amministrazione(user: dict) -> bool:
    """Verifica se l'utente possiede il tag Amministrazione assegnato"""
    return user_has_tag(user, "AMMINISTRAZIONE")

def user_can_manage_fornitori(user: dict) -> bool:
    """Verifica se l'utente ha diritto alla gestione completa dei fornitori (admin, o utente con tag DEC o Amministrazione)"""
    if not user:
        return False
    if user.get("ruolo") == "admin":
        return True
    return user_has_tag_dec(user) or user_has_tag_amministrazione(user)

def require_fornitori_manager(r: Request):
    """Richiede permessi di gestione fornitori: admin o utente con tag DEC o Amministrazione"""
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not user_can_manage_fornitori(user):
        return RedirectResponse(url="/fornitori?error=accesso_non_autorizzato", status_code=303)
    return user

def safe_int(val, default=None):
    """Converte in modo sicuro una stringa o valore in int, restituendo default se vuoto o non valido"""
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default
    try:
        return int(s)
    except (ValueError, TypeError):
        return default

def safe_float(val, default=None):
    """Converte in modo sicuro una stringa o valore in float, restituendo default se vuoto o non valido"""
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default



def save_upload(upload_file: UploadFile):
    if upload_file and upload_file.filename:
        ext = os.path.splitext(upload_file.filename)[1].lower()
        dangerous_exts = {".exe", ".bat", ".cmd", ".sh", ".msi", ".vbs", ".js", ".ps1", ".scr", ".pif", ".com"}
        if ext in dangerous_exts: return None
            
        upload_file.file.seek(0, 2)
        if upload_file.file.tell() > 10 * 1024 * 1024: return None
        upload_file.file.seek(0)
        
        filename = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return filename
    return None

def save_user_roles(conn, user_id, roles):
    from sqlalchemy import text
    if not isinstance(roles, list):
        if roles:
            roles = [roles]
        else:
            roles = []
    
    # filter out empty values
    roles = [r.strip() for r in roles if r and str(r).strip()]
    if not roles:
        roles = ['normale']
        
    # Delete existing roles
    conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": user_id})
    for r in roles:
        try:
            conn.execute(text("INSERT INTO user_roles (user_id, ruolo) VALUES (:uid, :ruolo)"), {"uid": user_id, "ruolo": r})
        except Exception:
            pass