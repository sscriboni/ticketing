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

    with engine.connect() as conn:
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

        # User's active bookings (ora_arrivo IS NULL)
        prenotazioni_attive = conn.execute(text("""
            SELECT v.*, a.modello, a.targa, m.nome AS marca_nome,
                   s.nome AS sede_partenza_nome
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON v.sede_partenza_id = s.sede_id
            WHERE v.user_id = :uid AND v.ora_arrivo IS NULL
            ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
        """), {"uid": uid}).mappings().all()

        now = datetime.datetime.now()
        attive_list = []
        for p in prenotazioni_attive:
            d = dict(p)
            try:
                bdt = datetime.datetime.strptime(
                    f"{p['data_viaggio']} {p['ora_partenza']}", "%Y-%m-%d %H:%M"
                )
                d["can_complete"] = now >= bdt
            except Exception:
                d["can_complete"] = True
            attive_list.append(d)

        # User's completed bookings
        prenotazioni_passate = conn.execute(text("""
            SELECT v.*, a.modello, a.targa, m.nome AS marca_nome,
                   sp.nome AS sede_partenza_nome, sa.nome AS sede_arrivo_nome
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi sp ON v.sede_partenza_id = sp.sede_id
            LEFT JOIN sedi sa ON v.sede_arrivo_id = sa.sede_id
            WHERE v.user_id = :uid AND v.ora_arrivo IS NOT NULL
            ORDER BY v.data_viaggio DESC, v.ora_arrivo DESC
        """), {"uid": uid}).mappings().all()

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
        "prenotazioni_passate": prenotazioni_passate,
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
    note: str = Form(None),
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")

    if ora_riconsegna_prevista <= ora_partenza:
        return _redirect_err("L'ora di riconsegna deve essere successiva all'ora di partenza.")

    with engine.begin() as conn:
        car = conn.execute(
            text("SELECT km_attuali, escluso_prenotazione, sede_attuale_id FROM automezzi WHERE automezzo_id = :id"),
            {"id": automezzo_id},
        ).first()

        if not car or car.escluso_prenotazione == 1 or car.sede_attuale_id != sede_partenza_id:
            return _redirect_err("Il veicolo selezionato non è disponibile per questa sede di partenza.")

        # Time-slot overlap check
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

        km_iniziali = car.km_attuali or 0
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista,
                ora_arrivo, km_iniziali, km_finali,
                sede_partenza_id, sede_arrivo_id, user_id, note
            ) VALUES (
                :aid, :dv, :op, :orc, NULL, :km, NULL, :sp, NULL, :uid, :note
            )
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
            "km": km_iniziali, "sp": sede_partenza_id,
            "uid": uid, "note": note,
        })

    return _redirect_ok("booked")

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
            SELECT automezzo_id, km_iniziali, note, data_viaggio, ora_partenza
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()

        if not v:
            return _redirect_err("Prenotazione non trovata o già completata.")

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

    with engine.begin() as conn:
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
