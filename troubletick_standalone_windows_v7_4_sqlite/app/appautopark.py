import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from core import CFG, templates, BASE_DIR, engine
from utils import ok

# Register Jinja global functions required by navbar.html
def get_new_tickets_count(user):
    if not user or user.get("ruolo") == "normale":
        return 0
    try:
        with engine.connect() as c:
            uid = user.get("id")
            return c.execute(text("""
                SELECT COUNT(*) FROM tickets 
                 WHERE stato = 'nuova' 
                   AND servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid)
            """), {"uid": uid}).scalar() or 0
    except Exception:
        pass
    return 0

def get_operators_count(user):
    if not user or user.get("ruolo") == "normale":
        return 0
    try:
        with engine.connect() as c:
            uid = user.get("id")
            if user.get("ruolo") == "admin":
                return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND user_id != 1 AND ruolo != 'normale'")).scalar() or 0
            elif user.get("ruolo") == "responsabile":
                user_rep = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
                if user_rep:
                    return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND user_id != 1 AND ruolo != 'normale' AND reparto_id = :rep"), {"rep": user_rep}).scalar() or 0
                return 0
            elif user.get("ruolo") == "assistenza":
                return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND user_id != 1 AND ruolo != 'normale'")).scalar() or 0
    except Exception:
        pass
    return 0

def get_users_count(user):
    if not user or user.get("ruolo") == "normale":
        return 0
    try:
        with engine.connect() as c:
            uid = user.get("id")
            if user.get("ruolo") == "admin":
                return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND ruolo = 'normale'")).scalar() or 0
            elif user.get("ruolo") == "responsabile":
                user_rep = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
                if user_rep:
                    return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND ruolo = 'normale' AND reparto_id = :rep"), {"rep": user_rep}).scalar() or 0
                return 0
            elif user.get("ruolo") == "assistenza":
                return c.execute(text("SELECT COUNT(*) FROM users WHERE attivo = 0 AND ruolo = 'normale'")).scalar() or 0
    except Exception:
        pass
    return 0

def get_pending_requests_count(user):
    if not user or user.get("ruolo") == "normale":
        return 0
    try:
        with engine.connect() as c:
            uid = user.get("id")
            if user.get("ruolo") == "admin":
                return c.execute(text("SELECT COUNT(*) FROM richieste_materiale WHERE stato NOT IN ('evasa', 'annullata')")).scalar() or 0
            else:
                user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": uid}).scalars().all()
                if not user_mag_ids:
                    return 0
                from sqlalchemy import bindparam
                stmt = text("SELECT COUNT(*) FROM richieste_materiale WHERE stato NOT IN ('evasa', 'annullata') AND magazzino_id IN :mids").bindparams(bindparam("mids", expanding=True))
                return c.execute(stmt, {"mids": list(user_mag_ids)}).scalar() or 0
    except Exception:
        pass
    return 0

templates.env.globals["get_new_tickets_count"] = get_new_tickets_count
templates.env.globals["get_operators_count"] = get_operators_count
templates.env.globals["get_users_count"] = get_users_count
templates.env.globals["get_pending_requests_count"] = get_pending_requests_count

app = FastAPI(title="Autopark Standalone")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Mock data for premium experience
veicoli = [
    {
        "id": 1,
        "modello": "Tesla Model 3",
        "targa": "GF345KK",
        "tipo": "Elettrica",
        "alimentazione_icon": "bi-lightning-charge-fill",
        "autonomia": "450 km (92%)",
        "posti": 5,
        "stato": "Disponibile",
        "stato_classe": "success",
        "colore": "#198754",
        "immagine": "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 2,
        "modello": "Audi A4 Avant",
        "targa": "FN123XX",
        "tipo": "Diesel (Mild Hybrid)",
        "alimentazione_icon": "bi-fuel-pump-fill",
        "autonomia": "850 km (75%)",
        "posti": 5,
        "stato": "In Uso",
        "stato_classe": "warning",
        "colore": "#fd7e14",
        "assegnato_a": "Mario Rossi",
        "rientro_previsto": "Oggi, ore 18:30",
        "immagine": "https://images.unsplash.com/photo-1606896328318-ee0877a94f6f?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 3,
        "modello": "Fiat 500 Hybrid",
        "targa": "GE987YY",
        "tipo": "Ibrida",
        "alimentazione_icon": "bi-fuel-pump-fill",
        "autonomia": "320 km (45%)",
        "posti": 4,
        "stato": "Disponibile",
        "stato_classe": "success",
        "colore": "#198754",
        "immagine": "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 4,
        "modello": "Jeep Compass 4xe",
        "targa": "GJ567ZZ",
        "tipo": "Plug-in Hybrid",
        "alimentazione_icon": "bi-lightning-charge-fill",
        "autonomia": "45 km (elettrico) / 500 km",
        "posti": 5,
        "stato": "In Manutenzione",
        "stato_classe": "danger",
        "colore": "#dc3545",
        "immagine": "https://images.unsplash.com/photo-1579250280907-73d810842cae?w=400&auto=format&fit=crop&q=60"
    }
]

prenotazioni_attive = [
    {
        "veicolo": "Audi A4 Avant (FN123XX)",
        "operatore": "Mario Rossi",
        "inizio": "Oggi, ore 08:30",
        "fine": "Oggi, ore 18:30",
        "destinazione": "Sede Cliente Milano"
    },
    {
        "veicolo": "Fiat 500 Hybrid (GE987YY)",
        "operatore": "Luigi Bianchi",
        "inizio": "Domani, ore 09:00",
        "fine": "Domani, ore 13:00",
        "destinazione": "Ufficio Postale centrale"
    }
]

@app.get("/", response_class=HTMLResponse)
def get_appautopark(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    return templates.TemplateResponse(r, "appautopark.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": veicoli,
        "prenotazioni": prenotazioni_attive
    })

@app.get("/login", response_class=HTMLResponse)
def login_form(r: Request, error: str = None):
    if "user" in r.session:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(r, "appautopark_login.html", {"request": r, "cfg": CFG, "error": error})

@app.post("/login")
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
            WHERE u.username=:u AND u.attivo=1
        """
        row = c.execute(text(query), {"u": username}).mappings().first()
        
    if row and ok(password, row["password_hash"]):
        r.session["user"] = {
            "id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "nome": row["nome"],
            "cognome": row["cognome"],
            "ruolo": row["ruolo"],
            "reparto_nome": row["reparto_nome"],
            "sede_nome": row["sede_nome"],
            "magazzino_id": row["magazzino_id"]
        }
        return RedirectResponse(url="/", status_code=303)
    else:
        return templates.TemplateResponse(r, "appautopark_login.html", {
            "request": r,
            "cfg": CFG,
            "error": "Credenziali non valide o utente non attivo."
        })

@app.get("/logout")
def logout_action(r: Request):
    r.session.clear()
    return RedirectResponse(url="/login")
