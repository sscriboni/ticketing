import os, datetime, urllib.parse
from fastapi import FastAPI, Request, Form, Query
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

    if user.get("ruolo") == "admin" or "admin" in user.get("roles", []):
        r.session.pop("user", None)
        err_msg = urllib.parse.quote("Per motivi di sicurezza, gli utenti con ruolo Admin non possono accedere alla webapp.")
        return RedirectResponse(url=f"/login?error={err_msg}")

    uid = user.get("id")
    role = user.get("ruolo")

    with engine.connect() as conn:
        # Get user's own reparto_id and sede_id
        user_row = conn.execute(text("SELECT reparto_id, sede_id FROM users WHERE user_id = :uid"), {"uid": uid}).mappings().first()
        user_reparto_id = user_row["reparto_id"] if user_row else None
        user_sede_id = user_row["sede_id"] if user_row else None
        user_ctx = {**user, "sede_id": user_sede_id} if user_sede_id else user

        # All vehicles for the dropdown (serialisable for JS filtering)
        veicoli_all = conn.execute(text("""
            SELECT a.automezzo_id, a.targa, a.modello, a.km_attuali,
                   a.stato, a.escluso_prenotazione,
                   COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0), 0) AS sede_attuale_id_resolved,
                   m.nome AS marca_nome, s.nome AS sede_attuale_nome
            FROM automezzi a
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0)) = s.sede_id
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
                "sede_attuale_id": v["sede_attuale_id_resolved"],
                "sede_attuale_nome": v["sede_attuale_nome"] or "Tutte le Sedi",
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
            has_started = bool(p.get("ora_partenza_effettiva"))
            has_ended = bool(p.get("ora_arrivo"))
            
            d["is_in_corso"] = has_started and not has_ended
            d["in_pausa"] = bool(p.get("in_pausa", 0))
            d["can_start"] = not has_started and not has_ended
            d["can_complete"] = has_started and not has_ended

            if has_ended:
                passate_list.append(d)
            else:
                attive_list.append(d)

        # All locations with count of available vehicles assigned to the location
        sedi_list = conn.execute(text("""
            SELECT s.sede_id, s.nome, c.nome AS comune_nome,
                   (SELECT COUNT(*) FROM automezzi a 
                    WHERE COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0), 0) = s.sede_id
                      AND a.stato = 'Disponibile' 
                      AND a.escluso_prenotazione = 0) AS auto_disponibili
            FROM sedi s
            LEFT JOIN comuni c ON s.comune_id = c.comune_id
            ORDER BY COALESCE(c.nome, s.nome) ASC, s.nome ASC
        """)).mappings().all()

        instant_mode = r.query_params.get("instant") == "1"
        instant_date = now.strftime("%Y-%m-%d")
        instant_hour = now.strftime("%H:00")
        instant_actual_time = now.strftime("%H:%M")
        info = r.query_params.get("info")

    return templates.TemplateResponse(r, "appautopark_home.html", {
        "request": r,
        "cfg": CFG,
        "user": user_ctx,
        "veicoli": veicoli_dicts,
        "prenotazioni_attive": attive_list,
        "prenotazioni_passate": passate_list,
        "sedi": sedi_list,
        "msg": msg,
        "error": error,
        "info": info,
        "instant": instant_mode,
        "instant_date": instant_date,
        "instant_hour": instant_hour,
        "instant_actual_time": instant_actual_time,
        "today_str": now.strftime("%Y-%m-%d")
    })


@app.get("/stampa-indisponibilita", response_class=HTMLResponse)
def stampa_indisponibilita_app(
    r: Request,
    sede_id: int = Query(...),
    data_viaggio: str = Query(...),
    ora_partenza: str = Query(...),
    ora_riconsegna_prevista: str = Query(...),
    note: str = Query(None),
    email_conducente: str = Query(None)
):
    user_session = r.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login", status_code=303)
    
    driver_email = email_conducente or user_session.get("email")
    driver_nome = user_session.get("nome", "")
    driver_cognome = user_session.get("cognome", "")
    driver_ruolo = user_session.get("ruolo", "Utente")
    driver_sede_nome = ""

    sede_nome = "Sede Non Trovata"

    with engine.begin() as conn:
        s_row = conn.execute(text("SELECT nome FROM sedi WHERE sede_id = :sid"), {"sid": sede_id}).mappings().first()
        if s_row:
            sede_nome = s_row["nome"]
            
        if driver_email:
            u_row = conn.execute(text("""
                SELECT u.nome, u.cognome, u.ruolo, s.nome AS sede_nome
                FROM utenti u
                LEFT JOIN sedi s ON u.sede_id = s.sede_id
                WHERE u.email = :email
            """), {"email": driver_email}).mappings().first()
            if u_row:
                driver_nome = u_row["nome"]
                driver_cognome = u_row["cognome"]
                driver_ruolo = u_row["ruolo"]
                driver_sede_nome = u_row["sede_nome"]

    formatted_date = data_viaggio
    try:
        parts = data_viaggio.split("-")
        if len(parts) == 3:
            formatted_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass

    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    return templates.TemplateResponse(r, "stampa_indisponibilita.html", {
        "request": r,
        "driver_nome": driver_nome,
        "driver_cognome": driver_cognome,
        "driver_email": driver_email,
        "driver_ruolo": driver_ruolo,
        "driver_sede_nome": driver_sede_nome,
        "sede_nome": sede_nome,
        "data_viaggio_formatted": formatted_date,
        "ora_partenza": ora_partenza,
        "ora_riconsegna_prevista": ora_riconsegna_prevista,
        "note": note,
        "ora_generazione": now_str
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

    try:
        travel_dt = datetime.datetime.strptime(f"{data_viaggio} {ora_partenza}", "%Y-%m-%d %H:%M")
        if travel_dt <= datetime.datetime.now():
            return _redirect_err("La data e l'ora di partenza devono essere nel futuro.")
    except Exception:
        return _redirect_err("Formato data o ora non valido.")

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
            text("SELECT km_attuali, escluso_prenotazione, sede_attuale_id, sede_assegnata_id FROM automezzi WHERE automezzo_id = :id"),
            {"id": automezzo_id},
        ).first()
        car_sede = (car.sede_attuale_id if car and car.sede_attuale_id else (car.sede_assegnata_id if car else 0)) or 0

        if not car or car.escluso_prenotazione == 1 or (car_sede != 0 and car_sede != sede_partenza_id):
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


@app.post("/registra-viaggio/{id}")
def registra_viaggio_posteriori(
    id: int,
    r: Request,
    ora_partenza: str = Form(...),
    km_iniziali: int = Form(...),
    km_finali: int = Form(...),
    ora_arrivo: str = Form(...),
    note: str = Form(None),
    sede_arrivo_id: int = Form(None)
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")

    with engine.begin() as conn:
        v = conn.execute(text("""
            SELECT automezzo_id, data_viaggio, km_iniziali, user_id, sede_partenza_id
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND ora_arrivo IS NULL
        """), {"id": id}).mappings().first()

        if not v:
            return _redirect_err("Prenotazione non trovata o già completata.")

        if v["user_id"] != uid and role not in ("admin", "fleet_manager", "global_fleet_manager"):
            return _redirect_err("Non sei autorizzato a registrare questo viaggio.")

        if ora_arrivo <= ora_partenza:
            return _redirect_err(f"L'orario di ritorno ({ora_arrivo}) deve essere successivo all'orario di partenza ({ora_partenza}).")

        if km_finali < km_iniziali:
            return _redirect_err(f"I km di arrivo ({km_finali}) non possono essere inferiori ai km di partenza ({km_iniziali}).")

        # Check if there is already a completed trip for this vehicle in a later date/time
        later_trip = conn.execute(text("""
            SELECT viaggio_id, data_viaggio, ora_partenza, ora_arrivo
            FROM viaggi_automezzi
            WHERE automezzo_id = :aid
              AND viaggio_id != :id
              AND ora_arrivo IS NOT NULL
              AND (
                  data_viaggio > :data_v
                  OR (data_viaggio = :data_v AND ora_partenza > :ora_p)
              )
            ORDER BY data_viaggio ASC, ora_partenza ASC
            LIMIT 1
        """), {
            "aid": v["automezzo_id"],
            "id": id,
            "data_v": v["data_viaggio"],
            "ora_p": ora_partenza
        }).mappings().first()

        if later_trip:
            formatted_later_date = later_trip['data_viaggio']
            try:
                parts = later_trip['data_viaggio'].split("-")
                if len(parts) == 3:
                    formatted_later_date = f"{parts[2]}/{parts[1]}/{parts[0]}"
            except Exception:
                pass
            err_msg = f"Impossibile registrare il viaggio: è già presente un viaggio completato in data/ora successiva ({formatted_later_date} alle {later_trip['ora_partenza']}) per questo veicolo."
            return _redirect_err(err_msg)

        final_sede_arrivo = sede_arrivo_id or v["sede_partenza_id"]

        conn.execute(text("""
            UPDATE viaggi_automezzi
            SET ora_partenza = :op,
                ora_partenza_effettiva = :op,
                ora_arrivo = :oa,
                km_iniziali = :ki,
                km_finali = :kf,
                sede_arrivo_id = :sa,
                note = :n,
                in_pausa = 0
            WHERE viaggio_id = :id
        """), {
            "id": id,
            "op": ora_partenza,
            "oa": ora_arrivo,
            "ki": km_iniziali,
            "kf": km_finali,
            "sa": final_sede_arrivo,
            "n": note
        })

        conn.execute(text("""
            UPDATE automezzi
            SET km_attuali = CASE WHEN :kf > km_attuali THEN :kf ELSE km_attuali END,
                sede_attuale_id = :sa
            WHERE automezzo_id = :aid
        """), {"aid": v["automezzo_id"], "kf": km_finali, "sa": final_sede_arrivo})

    return _redirect_ok("completed")



# ── ELIMINA ───────────────────────────────────────────────────────────────

@app.post("/elimina/{id}")
def elimina(id: int, r: Request, nuovi_km: int = Form(None)):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")

    import urllib.parse
    with engine.begin() as conn:
        if role in ("admin", "global_fleet_manager"):
            v = conn.execute(
                text("SELECT automezzo_id, km_iniziali, km_finali, user_id, ora_partenza_effettiva, data_viaggio FROM viaggi_automezzi WHERE viaggio_id = :id"),
                {"id": id},
            ).mappings().first()
        elif role == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar() or 0
            v = conn.execute(text("""
                SELECT v.automezzo_id, v.km_iniziali, v.km_finali, v.user_id, v.ora_partenza_effettiva, v.data_viaggio
                FROM viaggi_automezzi v
                JOIN users u ON v.user_id = u.user_id
                WHERE v.viaggio_id = :id AND u.reparto_id = :rep
            """), {"id": id, "rep": user_reparto_id}).mappings().first()
        else:
            # Normal user / operator: can only delete their own booking if not started yet
            v = conn.execute(
                text("SELECT automezzo_id, km_iniziali, km_finali, user_id, ora_partenza_effettiva, data_viaggio FROM viaggi_automezzi WHERE viaggio_id = :id AND user_id = :uid"),
                {"id": id, "uid": uid},
            ).mappings().first()

        if not v:
            return RedirectResponse(url=f"/?error={urllib.parse.quote('Prenotazione non trovata o non sei autorizzato a eliminarla.')}", status_code=303)

        today_str = datetime.date.today().isoformat()
        if v["data_viaggio"] < today_str:
            return RedirectResponse(url=f"/?error={urllib.parse.quote('Non è più possibile eliminare prenotazioni per date antecedenti ad oggi.')}", status_code=303)

        if role not in ("admin", "fleet_manager", "global_fleet_manager") and v["ora_partenza_effettiva"]:
            return RedirectResponse(url=f"/?error={urllib.parse.quote('Non puoi eliminare un viaggio che è già iniziato o completato.')}", status_code=303)

        if v:
            k_init = v["km_iniziali"] or 0
            k_fin = v["km_finali"]
            aid = v["automezzo_id"]
            if k_fin is not None:
                diff = k_fin - k_init
                msg_text = f"Viaggio eliminato con successo! Il tragitto comprendeva {diff} km (KM Partenza: {k_init}, KM Arrivo: {k_fin})."
            else:
                msg_text = f"Prenotazione eliminata con successo! (KM iniziali veicolo: {k_init})."
                
            if nuovi_km is not None and role in ("admin", "fleet_manager", "global_fleet_manager"):
                conn.execute(text("UPDATE automezzi SET km_attuali = :km WHERE automezzo_id = :aid"), {"km": nuovi_km, "aid": aid})
                msg_text += f" I chilometri dell'auto sono stati impostati a {nuovi_km} km."

            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})
            return RedirectResponse(url=f"/?msg={urllib.parse.quote(msg_text)}", status_code=303)

    return RedirectResponse(url="/?msg=deleted", status_code=303)

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
        query = """
            SELECT u.user_id, u.username, u.password_hash, u.nome, u.cognome,
                   u.email, u.ruolo, u.magazzino_id, u.reparto_id,
                   r.nome AS reparto_nome, s.nome AS sede_nome
            FROM users u
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            LEFT JOIN sedi s ON u.sede_id = s.sede_id
            WHERE {field} = :u AND u.attivo = 1
        """
        if "@" in username:
            row = c.execute(text(query.format(field="u.email")), {"u": username}).mappings().first()
        else:
            row = c.execute(text(query.format(field="u.username")), {"u": username}).mappings().first()

        if row and ok(password, row["password_hash"]):
            # Check user roles
            roles_rows = c.execute(text("SELECT ruolo FROM user_roles WHERE user_id = :uid"), {"uid": row["user_id"]}).mappings().all()
            roles = [rr["ruolo"] for rr in roles_rows] if roles_rows else [row["ruolo"]]

            if row["ruolo"] == "admin" or "admin" in roles:
                return templates.TemplateResponse(r, "appautopark_login.html", {
                    "request": r, "cfg": CFG,
                    "error": "Per motivi di sicurezza, gli utenti con ruolo Admin non possono accedere alla webapp.",
                })

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
                "roles": roles,
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
