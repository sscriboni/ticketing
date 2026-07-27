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
        return RedirectResponse(url="/", status_code=303)
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
            SELECT u.user_id, u.username, u.password_hash, u.nome, u.cognome, u.email, u.ruolo, u.magazzino_id, u.sede_id,
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
        # Fetch user roles
        with engine.connect() as c_roles:
            roles_rows = c_roles.execute(text("SELECT ruolo FROM user_roles WHERE user_id = :uid"), {"uid": row["user_id"]}).mappings().all()
            roles = [rr["ruolo"] for rr in roles_rows]
            
        if not roles:
            # Fallback
            roles = [row["ruolo"] or "normale"]
            
        if len(roles) > 1:
            # Redirect to role selection page
            r.session["pending_login_user"] = {
                "id": row["user_id"],
                "username": row["username"],
                "email": row["email"],
                "nome": row["nome"],
                "cognome": row["cognome"],
                "reparto_nome": row["reparto_nome"],
                "sede_nome": row["sede_nome"],
                "sede_id": row["sede_id"],
                "magazzino_id": row["magazzino_id"],
                "roles": roles
            }
            return RedirectResponse(url="/login/select-role", status_code=303)
            
        # Single role login
        r.session["user"] = {
            "id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "nome": row["nome"],
            "cognome": row["cognome"],
            "ruolo": roles[0],
            "reparto_nome": row["reparto_nome"],
            "sede_nome": row["sede_nome"],
            "sede_id": row["sede_id"],
            "magazzino_id": row["magazzino_id"],
            "roles": roles
        }
        ip = r.client.host if r.client else "Sconosciuto"
        with engine.begin() as c_update:
            c_update.execute(text("UPDATE users SET ultimo_accesso = :now, ultimo_ip = :ip WHERE user_id = :uid"), {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ip": ip, "uid": row["user_id"]})
        return RedirectResponse(url="/", status_code=303)
        
    ip = r.client.host if r.client else "Sconosciuto"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(BASE_DIR, "failed_logins.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] IP: {ip} - Tentativo fallito per: {username}\n")
        
    return templates.TemplateResponse(r, "login.html", {"request": r, "cfg": CFG, "error":"Credenziali errate"})

@router.get("/login/select-role", response_class=HTMLResponse)
def select_role_form(r: Request):
    pending = r.session.get("pending_login_user")
    user = r.session.get("user")
    
    if not pending and not user:
        return RedirectResponse(url="/login")
        
    roles = pending["roles"] if pending else user.get("roles", [])
    if not roles:
        return RedirectResponse(url="/login")
        
    with engine.connect() as c:
        ruoli_rows = c.execute(text("SELECT nome, descrizione FROM ruoli")).mappings().all()
        ruoli_dict = {rr["nome"]: rr["descrizione"] for rr in ruoli_rows}
        
    roles_data = [{"nome": role, "descrizione": ruoli_dict.get(role, role)} for role in roles]
    return templates.TemplateResponse(r, "select_role.html", {"request": r, "cfg": CFG, "roles": roles_data, "user": user})

@router.post("/login/select-role")
def select_role_action(r: Request, ruolo: str = Form(...)):
    pending = r.session.get("pending_login_user")
    user = r.session.get("user")
    
    if not pending and not user:
        return RedirectResponse(url="/login")
        
    roles = pending["roles"] if pending else user.get("roles", [])
    if ruolo not in roles:
        return RedirectResponse(url="/login")
        
    if pending:
        # Complete login
        r.session["user"] = {
            "id": pending["id"],
            "username": pending["username"],
            "email": pending["email"],
            "nome": pending["nome"],
            "cognome": pending["cognome"],
            "ruolo": ruolo,
            "reparto_nome": pending["reparto_nome"],
            "sede_nome": pending["sede_nome"],
            "sede_id": pending.get("sede_id"),
            "magazzino_id": pending["magazzino_id"],
            "roles": roles
        }
        r.session.pop("pending_login_user", None)
        
        # Update last login info
        ip = r.client.host if r.client else "Sconosciuto"
        with engine.begin() as c_update:
            c_update.execute(text("UPDATE users SET ultimo_accesso = :now, ultimo_ip = :ip WHERE user_id = :uid"), {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": ip,
                "uid": pending["id"]
            })
    else:
        # Switch active role
        user["ruolo"] = ruolo
        r.session["user"] = user
        
    return RedirectResponse(url="/", status_code=303)

@router.get("/register", response_class=HTMLResponse)
def register_form(r: Request):
    with engine.connect() as c:
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "register.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi})

@router.post("/register")
def register_action(r: Request, password: str=Form(...),
                    nome: str=Form(...), cognome: str=Form(...), email: str=Form(...),
                    telefono: str=Form(...), reparto_id: int=Form(...), sede_id: int=Form(...),
                    username: str=Form(None)):
    email = (email or "").strip()
    username = (username or "").strip() or email
    password = (password or "").strip()
    nome = (nome or "").strip()
    cognome = (cognome or "").strip()
    telefono = (telefono or "").strip()

    error_msg = None
    if not password or not nome or not cognome or not email or not telefono:
        error_msg = "Tutti i campi obbligatori devono essere compilati e non possono contenere solo spazi."
    elif len(nome) < 2:
        error_msg = "Il nome deve contenere almeno 2 caratteri (dopo il trim)."
    elif len(cognome) < 2:
        error_msg = "Il cognome deve contenere almeno 2 caratteri (dopo il trim)."
    elif len(password) < 5:
        error_msg = "La password deve contenere almeno 5 caratteri."
    elif not any(c.isalpha() for c in nome):
        error_msg = "Il nome non può essere composto solo da caratteri speciali o numeri."
    elif not any(c.isalpha() for c in cognome):
        error_msg = "Il cognome non può essere composto solo da caratteri speciali o numeri."

    if error_msg:
        with engine.connect() as c:
            reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        return templates.TemplateResponse(r, "register.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "error": error_msg})

    with engine.begin() as c:
        existing = c.execute(text("SELECT user_id FROM users WHERE username = :u OR email = :e"), {"u": username, "e": email}).scalar()
        if existing:
            reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
            return templates.TemplateResponse(r, "register.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "error": "Indirizzo Email già registrato nel sistema."})

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute(text("""
            INSERT INTO users (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, sede_id, attivo)
            VALUES (:u, :h, :n, :c, :e, :tel, 'assistenza', :rid, :sid, 0)
        """), {"u": username, "h": hashed, "n": nome, "c": cognome, "e": email, "tel": telefono, "rid": reparto_id, "sid": sede_id})
        
        user_id = c.execute(text("SELECT user_id FROM users WHERE username = :u"), {"u": username}).scalar()
        if user_id:
            from utils import save_user_roles
            save_user_roles(c, user_id, ['assistenza'])

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
    email = (email or "").strip()
    username = email
    password = (password or "").strip()
    nome = (nome or "").strip()
    cognome = (cognome or "").strip()
    tel_val = (telefono or "").strip() if telefono else None

    error_msg = None
    if not email or not password or not nome or not cognome:
        error_msg = "Tutti i campi obbligatori devono essere compilati e non possono contenere solo spazi."
    elif len(nome) < 2:
        error_msg = "Il nome deve contenere almeno 2 caratteri (dopo il trim)."
    elif len(cognome) < 2:
        error_msg = "Il cognome deve contenere almeno 2 caratteri (dopo il trim)."
    elif len(password) < 5:
        error_msg = "La password deve contenere almeno 5 caratteri."
    elif not any(c.isalpha() for c in nome):
        error_msg = "Il nome non può essere composto solo da caratteri speciali o numeri."
    elif not any(c.isalpha() for c in cognome):
        error_msg = "Il cognome non può essere composto solo da caratteri speciali o numeri."

    if error_msg:
        with engine.connect() as c:
            reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        return templates.TemplateResponse(r, "register_utente.html", {"request": r, "cfg": CFG, "reparti": reparti, "sedi": sedi, "error": error_msg, "prefilled_email": email})

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

        user_id = c.execute(text("SELECT user_id FROM users WHERE username = :u"), {"u": username}).scalar()
        if user_id:
            from utils import save_user_roles
            save_user_roles(c, user_id, ['normale'])

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
        user = c.execute(text("SELECT user_id, username, nome, cognome FROM users WHERE email = :e"), {"e": email}).mappings().first()
        if user:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now() + timedelta(hours=1)).isoformat()
            
            # Save token and expiry in database
            c.execute(text("UPDATE users SET reset_token = :token, reset_expires = :expires WHERE user_id = :uid"), {
                "token": token, "expires": expires, "uid": user["user_id"]
            })
            
            base_url = CFG.get("app_url", "").strip() or str(r.base_url)
            if not base_url.endswith("/"):
                base_url += "/"
            reset_link = f"{base_url}reset-password?token={token}"
            
            nome_utente = f"{user.get('nome', '')} {user.get('cognome', '')}".strip() or user.get("username", "Utente")
            app_title = CFG.get("app_title", "Troubletick")
            
            body = f"""
            <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2563eb;">🔑 Reset Password — {app_title}</h2>
                    <p>Ciao <strong>{nome_utente}</strong>,</p>
                    <p>Abbiamo ricevuto una richiesta di reset della tua password. Clicca sul pulsante qui sotto per impostare una nuova password:</p>
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
                            Reimposta la password
                        </a>
                    </p>
                    <p style="font-size: 0.9em; color: #666;">
                        Se non hai richiesto il reset della password, ignora questa email. Il link scadrà tra <strong>1 ora</strong>.
                    </p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="font-size: 0.8em; color: #999;">
                        Se il pulsante non funziona, copia e incolla il seguente link nel browser:<br>
                        <a href="{reset_link}" style="color: #2563eb;">{reset_link}</a>
                    </p>
                </div>
            </body></html>
            """
            
            send_email_async(
                dest_email=email,
                subject=f"Reset Password — {app_title}",
                body=body,
                reason="Reset password richiesto dall'utente"
            )
            
    return templates.TemplateResponse(r, "forgot_password.html", {"request": r, "cfg": CFG, "success": "Se l'email esiste nel sistema, ti è stato inviato un link per reimpostare la password. Controlla anche la cartella spam."})

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