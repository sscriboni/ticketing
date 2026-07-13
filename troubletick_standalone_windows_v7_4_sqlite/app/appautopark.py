import os, datetime, urllib.parse
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from core import CFG, templates, BASE_DIR, engine
from utils import ok

# ---------------------------------------------------------------------------
# Webapp Autopark – Login + Prenotazione Automezzi
# Run with:  uvicorn appautopark:app --host 0.0.0.0 --port 5002
# ---------------------------------------------------------------------------

app = FastAPI(title="Autopark App")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey-autopark")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ── helpers ────────────────────────────────────────────────────────────────

def _redirect_err(msg: str, path: str = "/"):
    return RedirectResponse(url=f"{path}?error={urllib.parse.quote(msg)}", status_code=303)


def _redirect_ok(msg: str, path: str = "/"):
    return RedirectResponse(url=f"{path}?msg={msg}", status_code=303)

# ── HOME (prenotazioni) ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(r: Request, msg: str = None, error: str = None):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login")

    uid = user.get("id")
    role = user.get("ruolo")

    with engine.connect() as conn:
        # Get user's own reparto_id
        user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()

        # All vehicles for the dropdown (serialisable for JS filtering)
        veicoli_all = conn.execute(text("""
            SELECT a.automezzo_id, a.targa, a.modello, a.km_attuali,
                   a.stato, a.escluso_prenotazione, a.sede_attuale_id,
                   m.nome AS marca_nome, s.nome AS sede_attuale_nome
            FROM automezzi a
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON a.sede_attuale_id = s.sede_id
            ORDER BY m.nome, a.modello
        """)).mappings().all()

        veicoli_dicts = []
        for v in veicoli_all:
            veicoli_dicts.append({
                "automezzo_id": v["automezzo_id"],
                "targa": v["targa"],
                "marca_nome": v["marca_nome"],
                "modello": v["modello"],
                "km_attuali": v["km_attuali"],
                "stato": v["stato"],
                "escluso_prenotazione": v["escluso_prenotazione"],
                "sede_attuale_id": v["sede_attuale_id"],
                "sede_attuale_nome": v["sede_attuale_nome"] or "N/D",
            })

        # Build query for bookings joining users
        base_query = """
            SELECT v.*, a.modello, a.targa, m.nome AS marca_nome, s.nome AS sede_partenza_nome,
                   u.nome AS driver_nome, u.cognome AS driver_cognome, u.email AS driver_email
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON v.sede_partenza_id = s.sede_id
            JOIN users u ON v.user_id = u.user_id
        """

        if role in ("admin", "global_fleet_manager"):
            bookings_raw = conn.execute(text(base_query + " ORDER BY v.data_viaggio DESC, v.ora_partenza DESC")).mappings().all()
        elif role == "fleet_manager" and user_reparto_id is not None:
            bookings_raw = conn.execute(text(base_query + """
                WHERE u.reparto_id = :rep_id
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"rep_id": user_reparto_id}).mappings().all()
        else:
            bookings_raw = conn.execute(text(base_query + """
                WHERE v.user_id = :uid
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"uid": uid}).mappings().all()

        now = datetime.datetime.now()
        attive_list = []
        passate_list = []

        for p in bookings_raw:
            d = dict(p)
            try:
                reconsegna_dt = datetime.datetime.strptime(f"{p['data_viaggio']} {p['ora_riconsegna_prevista']}", "%Y-%m-%d %H:%M")
                is_past = now > reconsegna_dt
            except Exception:
                is_past = False

            d["is_in_corso"] = False
            d["can_start"] = False
            d["can_complete"] = False

            if is_past:
                passate_list.append(d)
            else:
                attive_list.append(d)

        # All locations
        sedi_list = conn.execute(
            text("SELECT sede_id, nome FROM sedi ORDER BY nome")
        ).mappings().all()

    return templates.TemplateResponse(r, "appautopark_home.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": veicoli_dicts,
        "prenotazioni_attive": attive_list,
        "prenotazioni_passate": passate_list,
        "sedi": sedi_list,
        "msg": msg,
        "error": error,
    })

# ── PRENOTA ───────────────────────────────────────────────────────────────

@app.post("/prenota")
def prenota(
    r: Request,
    automezzo_id: int = Form(...),
    data_viaggio: str = Form(...),
    ora_partenza: str = Form(...),
    ora_riconsegna_prevista: str = Form(...),
    sede_partenza_id: int = Form(...),
    email_conducente: str = Form(None),
    note: str = Form(None)
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")
    current_email = user.get("email")

    if ora_riconsegna_prevista <= ora_partenza:
        return _redirect_err("L'ora di riconsegna deve essere successiva all'ora di partenza.")

    # 1. Resolve final_email of the driver based on role permissions
    if role in ("admin", "fleet_manager", "global_fleet_manager") and email_conducente:
        final_email = email_conducente.strip().lower()
    else:
        final_email = current_email.strip().lower() if current_email else ""

    with engine.connect() as conn:
        # Check if the driver user exists and is active
        driver = conn.execute(text("""
            SELECT user_id, reparto_id, email, nome, cognome 
            FROM users 
            WHERE LOWER(email) = LOWER(:email) AND attivo = 1
        """), {"email": final_email}).first()

    if not driver:
        return _redirect_err("Nessun utente attivo trovato con l'email del conducente indicata.")

    with engine.begin() as conn:
        # 2. Check department constraint for fleet manager
        if role == "fleet_manager":
            fm_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
            if driver.reparto_id != fm_reparto_id:
                return _redirect_err("Puoi prenotare solo per utenti appartenenti al tuo stesso reparto.")

        # 3. Check if the vehicle exists, is not excluded, and is at the correct location
        car = conn.execute(
            text("SELECT km_attuali, escluso_prenotazione, sede_attuale_id FROM automezzi WHERE automezzo_id = :id"),
            {"id": automezzo_id},
        ).first()

        if not car or car.escluso_prenotazione == 1 or car.sede_attuale_id != sede_partenza_id:
            return _redirect_err("Il veicolo selezionato non è disponibile per questa sede di partenza.")

        # 4. Check for time-slot overlap with existing bookings for this vehicle on this date
        overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE automezzo_id = :aid AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()

        if overlap:
            return _redirect_err("Il veicolo è già prenotato in questa fascia oraria.")

        # 5. Check for driver time-slot overlap on this date
        driver_overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :driver_id AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "driver_id": driver.user_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()

        if driver_overlap:
            return _redirect_err("Il guidatore indicato ha già un'altra prenotazione attiva in questa fascia oraria.")

        # 6. Insert new voyage record
        km_iniziali = car.km_attuali or 0
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista,
                ora_arrivo, km_iniziali, km_finali,
                sede_partenza_id, sede_arrivo_id, user_id, email_conducente, ora_partenza_effettiva, note
            ) VALUES (
                :aid, :dv, :op, :orc, NULL, :km, NULL, :sp, NULL, :driver_uid, :email, NULL, :note
            )
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
            "km": km_iniziali, "sp": sede_partenza_id,
            "driver_uid": driver.user_id, "email": driver.email, "note": note,
        })

    return _redirect_ok("booked")

# ── PARTI ────────────────────────────────────────────────────────────────────────

@app.post("/parti/{id}")
def parti(id: int, r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")

    with engine.begin() as conn:
        v = conn.execute(text("""
            SELECT viaggio_id, ora_partenza_effettiva
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()

        if not v:
            return _redirect_err("Prenotazione non trovata.")
        if v.ora_partenza_effettiva:
            return _redirect_err("Il viaggio è già stato avviato.")

        now_str = datetime.datetime.now().strftime("%H:%M")
        conn.execute(text("""
            UPDATE viaggi_automezzi SET ora_partenza_effettiva = :ora WHERE viaggio_id = :id
        """), {"ora": now_str, "id": id})

    return _redirect_ok("started")

# ── COMPLETA ──────────────────────────────────────────────────────────────

@app.post("/completa/{id}")
def completa(
    id: int, r: Request,
    ora_arrivo: str = Form(...),
    km_finali: int = Form(...),
    sede_arrivo_id: int = Form(...),
    note_finali: str = Form(None),
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")

    with engine.begin() as conn:
        v = conn.execute(text("""
            SELECT automezzo_id, km_iniziali, note, data_viaggio, ora_partenza, ora_partenza_effettiva
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()

        if not v:
            return _redirect_err("Prenotazione non trovata o già completata.")

        if not v.ora_partenza_effettiva:
            return _redirect_err("Devi prima avviare il viaggio con il pulsante Parti.")

        try:
            bdt = datetime.datetime.strptime(f"{v.data_viaggio} {v.ora_partenza}", "%Y-%m-%d %H:%M")
            if datetime.datetime.now() < bdt:
                return _redirect_err("Non puoi terminare un viaggio prima della data e ora di prenotazione.")
        except Exception:
            pass

        if km_finali < v.km_iniziali:
            return _redirect_err(f"I km finali ({km_finali}) non possono essere inferiori a quelli iniziali ({v.km_iniziali}).")

        note_complete = (v.note or "") + (f" | Rientro: {note_finali}" if note_finali else "")

        conn.execute(text("""
            UPDATE viaggi_automezzi
            SET ora_arrivo = :oa, km_finali = :kf, sede_arrivo_id = :sa, note = :n
            WHERE viaggio_id = :id
        """), {"id": id, "oa": ora_arrivo.strip(), "kf": km_finali, "sa": sede_arrivo_id, "n": note_complete})

        conn.execute(text("""
            UPDATE automezzi
            SET km_attuali = MAX(km_attuali, :kf), sede_attuale_id = :sa
            WHERE automezzo_id = :aid
        """), {"aid": v.automezzo_id, "kf": km_finali, "sa": sede_arrivo_id})

    return _redirect_ok("completed")

# ── ELIMINA ───────────────────────────────────────────────────────────────

@app.post("/elimina/{id}")
def elimina(id: int, r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")

    with engine.begin() as conn:
        if role in ("admin", "global_fleet_manager"):
            v = conn.execute(
                text("SELECT automezzo_id FROM viaggi_automezzi WHERE viaggio_id = :id"),
                {"id": id},
            ).first()
        elif role == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar() or 0
            v = conn.execute(text("""
                SELECT v.automezzo_id
                FROM viaggi_automezzi v
                JOIN users u ON v.user_id = u.user_id
                WHERE v.viaggio_id = :id AND u.reparto_id = :rep
            """), {"id": id, "rep": user_reparto_id}).first()
        else:
            v = conn.execute(
                text("SELECT automezzo_id FROM viaggi_automezzi WHERE viaggio_id = :id AND user_id = :uid"),
                {"id": id, "uid": uid},
            ).first()

        if v:
            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})

    return _redirect_ok("deleted")

# ── LOGIN / LOGOUT ────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_form(r: Request, error: str = None):
    if "user" in r.session:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(r, "appautopark_login.html", {
        "request": r, "cfg": CFG, "error": error,
    })


@app.post("/login")
def login_action(r: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    password = password.strip()

    with engine.connect() as c:
        row = c.execute(text("""
            SELECT u.user_id, u.username, u.password_hash, u.nome, u.cognome,
                   u.email, u.ruolo, u.magazzino_id, u.reparto_id,
                   r.nome AS reparto_nome, s.nome AS sede_nome
            FROM users u
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            LEFT JOIN sedi s ON u.sede_id = s.sede_id
            WHERE u.username = :u AND u.attivo = 1
        """), {"u": username}).mappings().first()

    if row and ok(password, row["password_hash"]):
        r.session["user"] = {
            "id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "nome": row["nome"],
            "cognome": row["cognome"],
            "ruolo": row["ruolo"],
            "reparto_id": row["reparto_id"],
            "reparto_nome": row["reparto_nome"],
            "sede_nome": row["sede_nome"],
            "magazzino_id": row["magazzino_id"],
        }
        return RedirectResponse(url="/", status_code=303)
    else:
        return templates.TemplateResponse(r, "appautopark_login.html", {
            "request": r, "cfg": CFG,
            "error": "Credenziali non valide o utente non attivo.",
        })


@app.get("/logout")
def logout_action(r: Request):
    r.session.clear()
    return RedirectResponse(url="/login")
