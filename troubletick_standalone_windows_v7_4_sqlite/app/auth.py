import os, secrets, bcrypt
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, BASE_DIR
from utils import ok
from email_utils import send_email_async

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_form(r: Request, reset: str = None, msg: str = None):
    if "user" in r.session:
        return RedirectResponse(url="/tickets", status_code=303)
    message = None
    error_msg = None
    if reset == "success":
        message = "Password reimpostata con successo! Ora puoi accedere."
    elif msg == "registrazione_ok":
        message = "Registrazione avvenuta con successo! Ti abbiamo inviato un'e-mail con il link di attivazione del tuo account."
    elif msg == "registrazione_operatore_ok":
        message = "Richiesta inviata! Il tuo account è in attesa di approvazione da parte di un amministratore."
    elif msg == "attivazione_ok":
        message = "Account attivato con successo! Ora puoi effettuare l'accesso."
    elif msg == "attivazione_ko":
        error_msg = "Il link di attivazione non è valido o è scaduto."
    return templates.TemplateResponse(r, "login.html", {"request": r, "cfg": CFG, "msg": message, "error": error_msg})

@router.post("/login")
def login_action(r: Request, username: str=Form(...), password: str=Form(...)):
    username = username.strip()
    password = password.strip()
    with engine.connect() as c:
        query = """
            SELECT u.user_id, u.username, u.password_hash, u.nome, u.cognome, u.email, u.ruolo, u.magazzino_id,
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
        r.session["user"] = {"id":row["user_id"],"username":row["username"],"email":row["email"],"nome":row["nome"],"cognome":row["cognome"],"ruolo":row["ruolo"], "reparto_nome":row["reparto_nome"], "sede_nome":row["sede_nome"], "magazzino_id":row["magazzino_id"]}
        ip = r.client.host if r.client else "Sconosciuto"
        with engine.begin() as c_update:
            c_update.execute(text("UPDATE users SET ultimo_accesso = :now, ultimo_ip = :ip WHERE user_id = :uid"), {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ip": ip, "uid": row["user_id"]})
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
    username = username.strip()
    password = password.strip()
    email = email.strip()
    telefono = telefono.strip()
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

    return RedirectResponse(url="/login?msg=registrazione_operatore_ok", status_code=303)

@router.get("/register-utente", response_class=HTMLResponse)
def register_utente_form(r: Request, email: str = None):
    with engine.connect() as c:
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "register_utente.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "prefilled_email": email})

@router.post("/register-utente")
def register_utente_action(r: Request, background_tasks: BackgroundTasks, password: str=Form(...),
                           nome: str=Form(...), cognome: str=Form(...), email: str=Form(...),
                           telefono: str=Form(None), reparto_id: int=Form(...), sede_id: int=Form(...)):
    email = email.strip()
    username = email
    password = password.strip()
    tel_val = telefono.strip() if telefono else None
    with engine.begin() as c:
        existing = c.execute(text("SELECT user_id FROM users WHERE username = :u OR email = :e"), {"u": username, "e": email}).scalar()
        if existing:
            reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
            return templates.TemplateResponse(r, "register_utente.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "error": "Email già in uso."})

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        activation_token = secrets.token_urlsafe(32)
        c.execute(text("""
            INSERT INTO users (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, sede_id, attivo, activation_token)
            VALUES (:u, :h, :n, :c, :e, :tel, 'normale', :rid, :sid, 0, :token)
        """), {"u": username, "h": hashed, "n": nome, "c": cognome, "e": email, "tel": tel_val, "rid": reparto_id, "sid": sede_id, "token": activation_token})

    # Send activation email in background
    subject = f"Attiva il tuo account — {CFG.get('app_title')}"
    base_url = CFG.get("app_url", "").strip() or str(r.base_url)
    if not base_url.endswith("/"):
        base_url += "/"
    activation_link = f"{base_url}attivazione?token={activation_token}"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
            <h2 style="color: #0d6efd; margin-bottom: 20px;">Benvenuto su {CFG.get('app_title')}</h2>
            <p>Ciao {nome},</p>
            <p>Grazie per esserti registrato. Per completare l'attivazione del tuo account e iniziare ad utilizzare la piattaforma, clicca sul pulsante qui sotto:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{activation_link}" style="background-color: #0d6efd; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">Attiva il mio Account</a>
            </div>
            <p>Se il pulsante non funziona, copia e incolla il seguente link nel tuo browser:</p>
            <p><a href="{activation_link}">{activation_link}</a></p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="font-size: 0.8em; color: #777;">Questa è una e-mail automatica, si prega di non rispondere.</p>
        </div>
    </body>
    </html>
    """
    background_tasks.add_task(send_email_async, email, subject, body, "Attivazione account")

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
            base_url = CFG.get("app_url", "").strip() or str(r.base_url)
            if not base_url.endswith("/"):
                base_url += "/"
            print(f"\n--- EMAIL SIMULATA ---\nLink di reset: {base_url}reset-password?token={token}\n----------------------\n")
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

@router.get("/attivazione")
def attivazione_action(r: Request, token: str):
    with engine.begin() as c:
        user = c.execute(text("SELECT user_id FROM users WHERE activation_token = :t"), {"t": token}).mappings().first()
        if not user:
            return RedirectResponse(url="/login?msg=attivazione_ko", status_code=303)
        c.execute(text("UPDATE users SET attivo = 1, activation_token = NULL WHERE user_id = :id"), {"id": user["user_id"]})
    return RedirectResponse(url="/login?msg=attivazione_ok", status_code=303)

@router.get("/logout")
def logout(r: Request):
    r.session.clear()
    return RedirectResponse(url="/", status_code=303)