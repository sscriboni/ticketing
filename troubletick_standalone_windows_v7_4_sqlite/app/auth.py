import os, secrets, bcrypt
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, BASE_DIR
from utils import ok

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_form(r: Request, reset: str = None, msg: str = None):
    if "user" in r.session:
        return RedirectResponse(url="/tickets", status_code=303)
    message = None
    if reset == "success": message = "Password reimpostata con successo! Ora puoi accedere."
    elif msg == "registrazione_ok": message = "Registrazione inviata! Il tuo account è in attesa di approvazione da parte di un amministratore."
    return templates.TemplateResponse(r, "login.html", {"request": r, "cfg": CFG, "msg": message})

@router.post("/login")
def login_action(r: Request, username: str=Form(...), password: str=Form(...)):
    with engine.connect() as c:
        query = """
            SELECT u.user_id, u.username, u.password_hash, u.nome, u.cognome, u.ruolo, u.magazzino_id,
                   r.nome AS reparto_nome, s.nome AS sede_nome
            FROM users u
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            LEFT JOIN sedi s ON u.sede_id = s.sede_id
            WHERE {field}=:u AND u.attivo=1
        """
        if "@" in username:
            row = c.execute(text(query.format(field="u.email")), {"u": username}).mappings().first()
        else:
            row = c.execute(text(query.format(field="u.username")), {"u": username}).mappings().first()
    if row and ok(password, row["password_hash"]):
        r.session["user"] = {"id":row["user_id"],"username":row["username"],"nome":row["nome"],"cognome":row["cognome"],"ruolo":row["ruolo"], "reparto_nome":row["reparto_nome"], "sede_nome":row["sede_nome"], "magazzino_id":row["magazzino_id"]}
        with engine.begin() as c_update:
            c_update.execute(text("UPDATE users SET ultimo_accesso = :now WHERE user_id = :uid"), {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "uid": row["user_id"]})
        return RedirectResponse(url="/tickets", status_code=303)
        
    ip = r.client.host if r.client else "Sconosciuto"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(BASE_DIR, "failed_logins.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] IP: {ip} - Tentativo fallito per: {username}\n")
        
    return templates.TemplateResponse(r, "login.html", {"request": r, "cfg": CFG, "error":"Credenziali errate"})

@router.get("/register", response_class=HTMLResponse)
def register_form(r: Request):
    with engine.connect() as c:
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "register.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi})

@router.post("/register")
def register_action(r: Request, username: str=Form(...), password: str=Form(...),
                    nome: str=Form(...), cognome: str=Form(...), email: str=Form(...),
                    telefono: str=Form(...), reparto_id: int=Form(...), sede_id: int=Form(...)):
    with engine.begin() as c:
        existing = c.execute(text("SELECT user_id FROM users WHERE username = :u OR email = :e"), {"u": username, "e": email}).scalar()
        if existing:
            reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
            return templates.TemplateResponse(r, "register.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "error": "Username o Email già in uso."})

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute(text("""
            INSERT INTO users (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, sede_id, attivo)
            VALUES (:u, :h, :n, :c, :e, :tel, 'assistenza', :rid, :sid, 0)
        """), {"u": username, "h": hashed, "n": nome, "c": cognome, "e": email, "tel": telefono, "rid": reparto_id, "sid": sede_id})

    return RedirectResponse(url="/login?msg=registrazione_ok", status_code=303)

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(r: Request):
    return templates.TemplateResponse(r, "forgot_password.html", {"request": r, "cfg": CFG})

@router.post("/forgot-password")
def forgot_password_action(r: Request, email: str = Form(...)):
    with engine.begin() as c:
        user = c.execute(text("SELECT user_id, username FROM users WHERE email = :e"), {"e": email}).mappings().first()
        if user:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now() + timedelta(hours=1)).isoformat()
            c.execute(text("UPDATE users SET reset_token = :t, reset_expires = :ex WHERE user_id = :id"), {"t": token, "ex": expires, "id": user["user_id"]})
            print(f"\n--- EMAIL SIMULATA ---\nLink di reset: {r.base_url}reset-password?token={token}\n----------------------\n")
    return templates.TemplateResponse(r, "forgot_password.html", {"request": r, "cfg": CFG, "success": "Se l'email esiste, ti è stato inviato un link di reset."})

@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_form(r: Request, token: str):
    return templates.TemplateResponse(r, "reset_password.html", {"request": r, "cfg": CFG, "token": token})

@router.post("/reset-password")
def reset_password_action(r: Request, token: str = Form(...), new_password: str = Form(...)):
    with engine.begin() as c:
        user = c.execute(text("SELECT user_id, reset_expires FROM users WHERE reset_token = :t"), {"t": token}).mappings().first()
        if not user or not user["reset_expires"] or datetime.now() > datetime.fromisoformat(user["reset_expires"]):
            return templates.TemplateResponse(r, "reset_password.html", {"request": r, "cfg": CFG, "token": token, "error": "Token invalido o scaduto."})
        c.execute(text("UPDATE users SET password_hash = :h, reset_token = NULL, reset_expires = NULL WHERE user_id = :id"), {"h": bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'), "id": user["user_id"]})
    return RedirectResponse(url="/login?reset=success", status_code=303)

@router.get("/logout")
def logout(r: Request):
    r.session.clear()
    return RedirectResponse(url="/", status_code=303)