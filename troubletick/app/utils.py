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