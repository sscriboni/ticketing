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
            has_started = bool(p.get("ora_partenza_effettiva"))
            has_ended = bool(p.get("ora_arrivo"))
            
            d["is_in_corso"] = has_started and not has_ended
            d["in_pausa"] = bool(p.get("in_pausa", 0))
            d["can_start"] = not has_started and not has_ended
            d["can_complete"] = has_started and not has_ended

            try:
                reconsegna_dt = datetime.datetime.strptime(f"{p['data_viaggio']} {p['ora_riconsegna_prevista']}", "%Y-%m-%d %H:%M")
                is_past = now > reconsegna_dt
            except Exception:
                is_past = False

            if has_ended:
                passate_list.append(d)
            elif is_past and not has_started:
                passate_list.append(d)
            else:
                attive_list.append(d)

        # All locations with count of available vehicles
        sedi_list = conn.execute(text("""
            SELECT s.sede_id, s.nome,
                   (SELECT COUNT(*) FROM automezzi a 
                    WHERE a.sede_attuale_id = s.sede_id 
                      AND a.stato = 'Disponibile' 
                      AND a.escluso_prenotazione = 0) AS auto_disponibili
            FROM sedi s
            ORDER BY s.nome
        """)).mappings().all()

        instant_mode = r.query_params.get("instant") == "1"
        instant_date = now.strftime("%Y-%m-%d")
        instant_hour = now.strftime("%H:00")
        instant_actual_time = now.strftime("%H:%M")
        info = r.query_params.get("info")

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
        "info": info,
        "instant": instant_mode,
        "instant_date": instant_date,
        "instant_hour": instant_hour,
        "instant_actual_time": instant_actual_time
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


@app.post("/registra-viaggio")
def registra_viaggio(r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    today_str = datetime.date.today().isoformat()
    
    with engine.begin() as conn:
        b = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :uid AND data_viaggio = :today AND ora_partenza_effettiva IS NULL AND ora_arrivo IS NULL
            ORDER BY ora_partenza ASC
        """), {"uid": uid, "today": today_str}).first()
        
        if b:
            now_str = datetime.datetime.now().strftime("%H:%M")
            conn.execute(text("""
                UPDATE viaggi_automezzi
                SET ora_partenza_effettiva = :now_time, in_pausa = 0
                WHERE viaggio_id = :id
            """), {"now_time": now_str, "id": b.viaggio_id})
            return _redirect_ok("started")
        else:
            return RedirectResponse(url="/?instant=1&info=no_booking", status_code=303)


@app.post("/registra-viaggio-istantaneo")
def registra_viaggio_istantaneo(
    r: Request,
    automezzo_id: int = Form(...),
    sede_partenza_id: int = Form(...),
    ora_riconsegna_prevista: str = Form(...),
    note: str = Form(None)
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    
    now = datetime.datetime.now()
    data_viaggio = now.strftime("%Y-%m-%d")
    ora_partenza = now.strftime("%H:00")
    ora_partenza_eff = now.strftime("%H:%M")
    
    if ora_riconsegna_prevista <= ora_partenza:
        return RedirectResponse(url="/?instant=1&error=L'ora+di+riconsegna+deve+essere+successiva+all'ora+di+partenza.", status_code=303)
        
    with engine.connect() as conn:
        driver = conn.execute(text("""
            SELECT user_id, reparto_id, email, nome, cognome 
            FROM users 
            WHERE user_id = :uid AND attivo = 1
        """), {"uid": uid}).first()
        
    if not driver:
        return RedirectResponse(url="/?instant=1&error=Utente+non+trovato+o+non+attivo.", status_code=303)
        
    with engine.begin() as conn:
        car = conn.execute(
            text("SELECT km_attuali, escluso_prenotazione, sede_attuale_id FROM automezzi WHERE automezzo_id = :id"),
            {"id": automezzo_id},
        ).first()
        
        if not car or car.escluso_prenotazione == 1 or car.sede_attuale_id != sede_partenza_id:
            return RedirectResponse(url="/?instant=1&error=Il+veicolo+selezionato+non+è+disponibile+per+questa+sede.", status_code=303)
            
        overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE automezzo_id = :aid AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()
        
        if overlap:
            return RedirectResponse(url="/?instant=1&error=Il+veicolo+è+già+prenotato+in+questa+fascia.", status_code=303)
            
        driver_overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :driver_id AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "driver_id": uid, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()
        
        if driver_overlap:
            return RedirectResponse(url="/?instant=1&error=Hai+già+un'altra+prenotazione+attiva+in+questa+fascia.", status_code=303)
            
        km_iniziali = car.km_attuali or 0
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista,
                ora_arrivo, km_iniziali, km_finali,
                sede_partenza_id, sede_arrivo_id, user_id, email_conducente, ora_partenza_effettiva, note, in_pausa
            ) VALUES (
                :aid, :dv, :op, :orc, NULL, :km, NULL, :sp, NULL, :driver_uid, :email, :ora_partenza_eff, :note, 0
            )
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
            "km": km_iniziali, "sp": sede_partenza_id,
            "driver_uid": uid, "email": driver.email, "ora_partenza_eff": ora_partenza_eff, "note": note,
        })
        
    return _redirect_ok("started")


@app.post("/avvia/{id}")
def avvia(id: int, r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if not booking:
            return _redirect_err("Prenotazione non trovata.")
        if booking.user_id != uid and user.get("ruolo") not in ("admin", "global_fleet_manager"):
            return _redirect_err("Non sei autorizzato ad avviare questo viaggio.")
            
        now_str = datetime.datetime.now().strftime("%H:%M")
        conn.execute(text("UPDATE viaggi_automezzi SET ora_partenza_effettiva = :now, in_pausa = 0 WHERE viaggio_id = :id"), {"now": now_str, "id": id})
        
    return _redirect_ok("started")


@app.post("/pausa/{id}")
def toggle_pausa(id: int, r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, in_pausa FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if not booking:
            return _redirect_err("Prenotazione non trovata.")
        if booking.user_id != uid and user.get("ruolo") not in ("admin", "global_fleet_manager"):
            return _redirect_err("Non sei autorizzato ad effettuare questa operazione.")
            
        new_val = 1 if not booking.in_pausa else 0
        conn.execute(text("UPDATE viaggi_automezzi SET in_pausa = :new_val WHERE viaggio_id = :id"), {"new_val": new_val, "id": id})
        
    msg_type = "paused" if new_val == 1 else "resumed"
    return _redirect_ok(msg_type)


@app.post("/completa/{id}")
def completa(
    id: int, r: Request,
    km_finali: int = Form(...),
    sede_arrivo_id: int = Form(...),
    ora_arrivo: str = Form(...),
    note_finali: str = Form(None),
):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")

    with engine.begin() as conn:
        v = conn.execute(text("""
            SELECT automezzo_id, km_iniziali, note, data_viaggio, ora_partenza, ora_partenza_effettiva, in_pausa, inizio_pausa, minuti_fermo
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()

        if not v:
            return _redirect_err("Prenotazione non trovata o già completata.")

        if not v.ora_partenza_effettiva:
            return _redirect_err("Devi prima avviare il viaggio con il pulsante Registra Viaggio.")

        # Validate that ora_arrivo is greater than ora_partenza_effettiva
        if ora_arrivo <= v.ora_partenza_effettiva:
            return _redirect_err(f"L'orario di rientro ({ora_arrivo}) deve essere successivo all'orario di partenza effettiva ({v.ora_partenza_effettiva}).")

        # Check if date has changed (compare today's date with data_viaggio)
        today_str = datetime.date.today().isoformat()
        warning_msg = None
        if today_str != v.data_viaggio:
            warning_msg = "Attenzione: la data corrente è diversa da quella di partenza. Il viaggio è stato registrato con data di fine pari alla data di partenza."

        minutes_fermo = v.minuti_fermo or 0
        if v.in_pausa and v.inizio_pausa:
            try:
                # Calculate pause duration up to the return time on data_viaggio
                inizio = datetime.datetime.fromisoformat(v.inizio_pausa)
                rientro_dt = datetime.datetime.strptime(f"{v.data_viaggio} {ora_arrivo}", "%Y-%m-%d %H:%M")
                if rientro_dt > inizio:
                    delta = rientro_dt - inizio
                    minutes_fermo += int(delta.total_seconds() / 60)
            except Exception:
                pass

        if km_finali < v.km_iniziali:
            return _redirect_err(f"I km finali ({km_finali}) non possono essere inferiori a quelli iniziali ({v.km_iniziali}).")

        note_complete = (v.note or "") + (f" | Rientro: {note_finali}" if note_finali else "")

        conn.execute(text("""
            UPDATE viaggi_automezzi
            SET ora_arrivo = :oa, km_finali = :kf, sede_arrivo_id = :sa, note = :n,
                in_pausa = 0, inizio_pausa = NULL, minuti_fermo = :mf
            WHERE viaggio_id = :id
        """), {"id": id, "oa": ora_arrivo, "kf": km_finali, "sa": sede_arrivo_id, "n": note_complete, "mf": minutes_fermo})

        conn.execute(text("""
            UPDATE automezzi
            SET km_attuali = CASE WHEN :kf > km_attuali THEN :kf ELSE km_attuali END, sede_attuale_id = :sa
            WHERE automezzo_id = :aid
        """), {"aid": v.automezzo_id, "kf": km_finali, "sa": sede_arrivo_id})

    if warning_msg:
        return _redirect_ok(warning_msg)
    else:
        return _redirect_ok("completed")


@app.post("/annulla-viaggio/{id}")
def annulla_viaggio(id: int, r: Request):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")
    
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if not booking:
            return _redirect_err("Prenotazione non trovata.")
        if booking.user_id != uid and role not in ("admin", "global_fleet_manager"):
            return _redirect_err("Non sei autorizzato ad annullare questo viaggio.")
            
        conn.execute(text("UPDATE viaggi_automezzi SET ora_partenza_effettiva = NULL, in_pausa = 0 WHERE viaggio_id = :id"), {"id": id})
        
    return _redirect_ok("Avvio viaggio annullato. Stato prenotazione ripristinato.")


# ── ELIMINA ───────────────────────────────────────────────────────────────

@app.post("/elimina/{id}")
def elimina(id: int, r: Request, nuovi_km: int = Form(None)):
    user = r.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    uid = user.get("id")
    role = user.get("ruolo")

    import urllib.parse
    if role not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url=f"/?error={urllib.parse.quote('Non sei autorizzato a eliminare prenotazioni.')}", status_code=303)

    with engine.begin() as conn:
        if role in ("admin", "global_fleet_manager"):
            v = conn.execute(
                text("SELECT automezzo_id, km_iniziali, km_finali FROM viaggi_automezzi WHERE viaggio_id = :id"),
                {"id": id},
            ).mappings().first()
        elif role == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar() or 0
            v = conn.execute(text("""
                SELECT v.automezzo_id, v.km_iniziali, v.km_finali
                FROM viaggi_automezzi v
                JOIN users u ON v.user_id = u.user_id
                WHERE v.viaggio_id = :id AND u.reparto_id = :rep
            """), {"id": id, "rep": user_reparto_id}).mappings().first()
        else:
            v = None

        if v:
            k_init = v["km_iniziali"] or 0
            k_fin = v["km_finali"]
            aid = v["automezzo_id"]
            if k_fin is not None:
                diff = k_fin - k_init
                msg_text = f"Viaggio eliminato con successo! Il tragitto comprendeva {diff} km (KM Partenza: {k_init}, KM Arrivo: {k_fin})."
            else:
                msg_text = f"Prenotazione eliminata con successo! (KM iniziali veicolo: {k_init})."
                
            if nuovi_km is not None:
                conn.execute(text("UPDATE automezzi SET km_attuali = :km WHERE automezzo_id = :aid"), {"km": nuovi_km, "aid": aid})
                msg_text += f" I chilometri dell'auto sono stati impostati a {nuovi_km} km."

            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})
            return RedirectResponse(url=f"/?msg={urllib.parse.quote(msg_text)}", status_code=303)

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
