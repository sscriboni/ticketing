import bcrypt
import os, shutil, uuid
from fastapi import Request, UploadFile
from fastapi.responses import RedirectResponse
from core import UPLOAD_DIR

def ok(p, h):
    try: return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except: return False

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