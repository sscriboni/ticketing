from datetime import datetime, timedelta, date
import calendar
import urllib.parse
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from core import CFG, templates, engine

router = APIRouter()

@router.get("/calendario", response_class=HTMLResponse)
def calendario(r: Request, copertura_alert: str = None, servizi_scoperti: str = None):
    if not CFG.get('modulo_presenze', True):
        return RedirectResponse(url="/")
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        uid = user.get("id")
        assenze_raw = c.execute(text("""
            SELECT a.*, u.nome, u.cognome, u.username, r.nome as reparto_nome
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE a.user_id = :uid
            ORDER BY a.data_inizio DESC
        """), {"uid": uid}).mappings().all()
            
        festivita = c.execute(text("""
            SELECT f.*, c.nome as comune_nome 
            FROM festivita f 
            LEFT JOIN comuni c ON f.comune_id = c.comune_id 
            ORDER BY f.data DESC
        """)).mappings().all()

    assenze = [dict(a) for a in assenze_raw]
    months_it = {
        1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
        5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
        9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
    }
    grouped_assenze = {}
    current_year = date.today().year

    for a in assenze:
        d_init = str(a.get("data_inizio") or "")
        try:
            yr = int(d_init[:4])
            m = int(d_init[5:7])
        except (ValueError, IndexError):
            yr = 0
            m = 0

        if yr not in grouped_assenze:
            grouped_assenze[yr] = {}
        if m not in grouped_assenze[yr]:
            grouped_assenze[yr][m] = {
                "mese_num": m,
                "mese_nome": months_it.get(m, f"Mese {m}"),
                "elenco": []
            }
        grouped_assenze[yr][m]["elenco"].append(a)

    storico_anni = []
    for yr, mesi_dict in grouped_assenze.items():
        tot_anno = sum(len(m_data["elenco"]) for m_data in mesi_dict.values())
        storico_anni.append({
            "anno": yr,
            "is_current": (yr == current_year),
            "totale": tot_anno,
            "mesi": list(mesi_dict.values())
        })
            
    return templates.TemplateResponse(r, "calendario.html", {
        "request": r, "cfg": CFG, "user": user, "assenze": assenze, "storico_anni": storico_anni, "festivita": festivita,
        "copertura_alert": copertura_alert, "servizi_scoperti": servizi_scoperti
    })

@router.get("/calendario-presenze", response_class=HTMLResponse)
def calendario_presenze(r: Request):
    if not CFG.get('modulo_presenze', True):
        return RedirectResponse(url="/")
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    uid = user.get("id")
    
    with engine.connect() as c:
        presenze_raw = c.execute(text("""
            SELECT p.*, u.nome, u.cognome, r.nome as reparto_nome
            FROM presenze p
            JOIN users u ON p.user_id = u.user_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE p.user_id = :uid
            ORDER BY p.data_inizio DESC
        """), {"uid": uid}).mappings().all()
        
        festivita = c.execute(text("""
            SELECT f.*, c.nome as comune_nome 
            FROM festivita f 
            LEFT JOIN comuni c ON f.comune_id = c.comune_id 
            ORDER BY f.data DESC
        """)).mappings().all()

    today = date.today()
    cutoff_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    presenze = []
    num_vecchie = 0
    for p_raw in presenze_raw:
        p = dict(p_raw)
        end_d = str(p.get("data_fine") or p.get("data_inizio") or "")
        is_vecchia = bool(end_d and end_d < cutoff_date)
        p["is_vecchia"] = is_vecchia
        if is_vecchia:
            num_vecchie += 1
        presenze.append(p)
        
    return templates.TemplateResponse(r, "calendario_presenze.html", {
        "request": r, "cfg": CFG, "user": user, "presenze": presenze, "num_vecchie": num_vecchie, "cutoff_date": cutoff_date, "festivita": festivita
    })

@router.post("/calendario-presenze/nuova")
def nuova_presenza(
    r: Request, 
    data_inizio: str = Form(...), 
    data_fine: str = Form(""), 
    tipo: str = Form(...), 
    nota: str = Form("")
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if not data_fine or not data_fine.strip():
        data_fine = data_inizio
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    if data_inizio < today_str or data_fine < today_str:
        error_msg = "Non è possibile inserire presenze nel passato."
        return RedirectResponse(url=f"/calendario-presenze?error={urllib.parse.quote(error_msg)}", status_code=303)
    
    # Cap nota at 20 characters
    nota = (nota or "").strip()[:20]
    
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO presenze (user_id, data_inizio, data_fine, tipo, nota)
            VALUES (:uid, :di, :df, :t, :n)
        """), {"uid": user.get("id"), "di": data_inizio, "df": data_fine, "t": tipo, "n": nota})
        
    return RedirectResponse(url="/calendario-presenze", status_code=303)

@router.post("/calendario-presenze/{presenza_id}/elimina")
def elimina_presenza(r: Request, presenza_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        if user.get("ruolo") == "admin":
            c.execute(text("DELETE FROM presenze WHERE presenza_id = :id"), {"id": presenza_id})
        else:
            c.execute(text("DELETE FROM presenze WHERE presenza_id = :id AND user_id = :uid"), {"id": presenza_id, "uid": user.get("id")})
            
    return RedirectResponse(url="/calendario-presenze", status_code=303)

@router.post("/calendario/nuova")
def nuova_assenza(r: Request, data_inizio: str = Form(...), data_fine: str = Form(""), motivo: str = Form("")):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if not data_fine or not data_fine.strip():
        data_fine = data_inizio
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    if data_inizio < today_str or data_fine < today_str:
        error_msg = "Non è possibile inserire assenze nel passato."
        return RedirectResponse(url=f"/calendario?error={urllib.parse.quote(error_msg)}", status_code=303)
        
    with engine.begin() as c:
        c.execute(text("""INSERT INTO assenze (user_id, data_inizio, data_fine, motivo)
                          VALUES (:uid, :di, :df, :m)"""), 
                  {"uid": user.get("id"), "di": data_inizio, "df": data_fine, "m": motivo})
        
        # Recupera il reparto dell'operatore
        reparto_id = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
        
    copertura_alert = None
    servizi_scoperti_str = None
    if reparto_id:
        try:
            di_dt = datetime.strptime(data_inizio, "%Y-%m-%d")
            df_dt = datetime.strptime(data_fine, "%Y-%m-%d")
            
            dates_to_check = []
            with engine.connect() as c_read:
                festivita_dates = {f["data"] for f in c_read.execute(text("SELECT data FROM festivita WHERE data >= :start AND data <= :end"), {"start": data_inizio, "end": data_fine}).mappings().all()}

            curr_dt = di_dt
            while curr_dt <= df_dt:
                d_str = curr_dt.strftime("%Y-%m-%d")
                # Escludi Sabato (5), Domenica (6) e festività dal controllo della copertura
                if curr_dt.weekday() not in (5, 6) and d_str not in festivita_dates:
                    dates_to_check.append(d_str)
                curr_dt += timedelta(days=1)
                
            with engine.connect() as c_read:
                servizi = c_read.execute(text("""
                    SELECT s.servizio_id, s.descrizione 
                    FROM servizi s
                    JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
                    WHERE s.reparto_id = :rid AND os.user_id = :uid
                """), {"rid": reparto_id, "uid": user.get("id")}).mappings().all()
                
                servizi_ops = {}
                for s in servizi:
                    ops = c_read.execute(text("""
                        SELECT u.user_id
                        FROM users u
                        JOIN operatori_servizi os ON u.user_id = os.user_id
                        WHERE os.servizio_id = :sid AND u.attivo = 1
                    """), {"sid": s["servizio_id"]}).mappings().all()
                    servizi_ops[s["servizio_id"]] = ops
                    
                assenze_overlaps = c_read.execute(text("""
                    SELECT a.user_id, a.data_inizio, a.data_fine
                    FROM assenze a
                    JOIN users u ON a.user_id = u.user_id
                    WHERE u.reparto_id = :rid AND a.data_inizio <= :end AND a.data_fine >= :start
                """), {"rid": reparto_id, "start": data_inizio, "end": data_fine}).mappings().all()
                
            uncovered_services = []
            for d_str in dates_to_check:
                for s in servizi:
                    sid = s["servizio_id"]
                    ops = servizi_ops[sid]
                    if len(ops) > 0:
                        present_count = 0
                        for op in ops:
                            is_absent = False
                            for a in assenze_overlaps:
                                if a["user_id"] == op["user_id"]:
                                    if a["data_inizio"] <= d_str <= a["data_fine"]:
                                        is_absent = True
                                        break
                            if not is_absent:
                                present_count += 1
                        if present_count == 0:
                            uncovered_services.append((s["descrizione"], d_str))
                            
            if uncovered_services:
                copertura_alert = "1"
                details = []
                for name, d_str in uncovered_services:
                    d_formatted = datetime.strptime(d_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                    details.append(f"{name} ({d_formatted})")
                servizi_scoperti_str = ", ".join(details)
        except Exception as e:
            print("Error checking coverage:", e)
            
    if copertura_alert:
        params = urllib.parse.urlencode({"copertura_alert": "1", "servizi_scoperti": servizi_scoperti_str})
        return RedirectResponse(url=f"/calendario?{params}", status_code=303)
        
    return RedirectResponse(url="/calendario", status_code=303)

@router.post("/calendario/{assenza_id}/elimina")
def elimina_assenza(r: Request, assenza_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.begin() as c:
        if user.get("ruolo") == "admin":
            c.execute(text("DELETE FROM assenze WHERE assenza_id = :id"), {"id": assenza_id})
        else:
            c.execute(text("DELETE FROM assenze WHERE assenza_id = :id AND user_id = :uid"), {"id": assenza_id, "uid": user.get("id")})
    return RedirectResponse(url="/calendario", status_code=303)

@router.get("/copertura-servizi", response_class=HTMLResponse)
def copertura_servizi(r: Request, mese: int = None, anno: int = None, reparto_id: int = None):
    if not CFG.get('modulo_presenze', True):
        return RedirectResponse(url="/")
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "responsabile"):
        return RedirectResponse(url="/tickets")
    
    today = date.today()
    if mese is None:
        mese = today.month
    if anno is None:
        anno = today.year
        
    with engine.connect() as c:
        reparti_list = []
        if user.get("ruolo") == "admin":
            reparti_list = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            
        if user.get("ruolo") == "admin":
            if reparto_id is None:
                if reparti_list:
                    reparto_id = reparti_list[0]["reparto_id"]
        else:
            reparto_id = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            
        if reparto_id is None:
            return templates.TemplateResponse(r, "copertura_servizi.html", {
                "request": r, "cfg": CFG, "user": user, 
                "error": "Non sei assegnato a nessun reparto. Contatta l'amministratore.", 
                "mese": mese, "anno": anno, "reparto_id": None, "reparti": reparti_list
            })
            
        reparto_nome = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": reparto_id}).scalar()
        
        servizi = c.execute(text("""
            SELECT servizio_id, descrizione 
            FROM servizi 
            WHERE reparto_id = :rid
            ORDER BY descrizione
        """), {"rid": reparto_id}).mappings().all()
        
        servizi_ops = {}
        for s in servizi:
            ops = c.execute(text("""
                SELECT u.user_id, u.nome, u.cognome, u.username
                FROM users u
                JOIN operatori_servizi os ON u.user_id = os.user_id
                WHERE os.servizio_id = :sid AND u.attivo = 1
                ORDER BY u.cognome, u.nome
            """), {"sid": s["servizio_id"]}).mappings().all()
            servizi_ops[s["servizio_id"]] = ops
            
        first_day_of_month = date(anno, mese, 1)
        last_day_of_month = date(anno, mese, calendar.monthrange(anno, mese)[1])
        
        festivita_list = c.execute(text("""
            SELECT data, descrizione FROM festivita 
            WHERE data >= :start AND data <= :end
        """), {"start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()
        festivita_map = {f["data"]: f["descrizione"] for f in festivita_list}
        
        assenze_list = c.execute(text("""
            SELECT a.user_id, a.data_inizio, a.data_fine, a.motivo
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            WHERE u.reparto_id = :rid AND a.data_inizio <= :end AND a.data_fine >= :start
        """), {"rid": reparto_id, "start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()
        
        cal = calendar.Calendar(firstweekday=0)
        weeks_raw = cal.monthdatescalendar(anno, mese)
        
        weeks = []
        for week_dates in weeks_raw:
            week_days = []
            for d in week_dates:
                d_str = d.isoformat()
                holiday = festivita_map.get(d_str)
                
                day_servizi = []
                uncovered_count = 0
                for s in servizi:
                    ops_status = []
                    present_count = 0
                    for op in servizi_ops[s["servizio_id"]]:
                        absent_record = None
                        for a in assenze_list:
                            if a["user_id"] == op["user_id"]:
                               if a["data_inizio"] <= d_str <= a["data_fine"]:
                                    absent_record = a
                                    break
                                    
                        is_absent = absent_record is not None
                        if not is_absent:
                            present_count += 1
                            
                        ops_status.append({
                            "user_id": op["user_id"],
                            "nome_completo": f"{op['nome']} {op['cognome']}".strip() or op['username'],
                            "assente": is_absent,
                            "motivo": absent_record["motivo"] if absent_record else None
                        })
                        
                    is_weekend_day = d.weekday() in (5, 6)
                    if not is_weekend_day and not holiday:
                        if len(servizi_ops[s["servizio_id"]]) > 0 and present_count == 0:
                            uncovered_count += 1
                        
                    day_servizi.append({
                        "servizio_id": s["servizio_id"],
                        "descrizione": s["descrizione"],
                        "operatori": ops_status
                    })
                    
                week_days.append({
                    "date": d,
                    "day_num": d.day,
                    "is_current_month": d.month == mese,
                    "is_today": d == today,
                    "holiday": holiday,
                    "is_weekend": is_weekend_day,
                    "servizi": day_servizi,
                    "uncovered": uncovered_count > 0 and not is_weekend_day and not holiday,
                    "uncovered_count": uncovered_count if (not is_weekend_day and not holiday) else 0
                })
            weeks.append(week_days)
            
        months_it = {
            1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
            5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
            9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
        }
        nome_mese = months_it.get(mese, "")
        
        if mese == 1:
            prev_mese, prev_anno = 12, anno - 1
        else:
            prev_mese, prev_anno = mese - 1, anno
            
        if mese == 12:
            next_mese, next_anno = 1, anno + 1
        else:
            next_mese, next_anno = mese + 1, anno

    return templates.TemplateResponse(r, "copertura_servizi.html", {
        "request": r, "cfg": CFG, "user": user,
        "weeks": weeks,
        "mese": mese,
        "anno": anno,
        "nome_mese": nome_mese,
        "prev_mese": prev_mese,
        "prev_anno": prev_anno,
        "next_mese": next_mese,
        "next_anno": next_anno,
        "reparto_id": reparto_id,
        "reparto_nome": reparto_nome,
        "reparti": reparti_list
    })

@router.get("/assenze-mese", response_class=HTMLResponse)
def assenze_mese(r: Request, mese: int = None, anno: int = None, reparto_id: int = None, sede_id: int = None, tag_id: int = None):
    if not CFG.get('modulo_presenze', True):
        return RedirectResponse(url="/")
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    today = date.today()
    if mese is None:
        mese = today.month
    if anno is None:
        anno = today.year
        
    with engine.connect() as c:
        reparti_list = []
        if user.get("ruolo") == "admin":
            reparti_list = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
            
        if user.get("ruolo") == "admin":
            if reparto_id is None:
                if reparti_list:
                    reparto_id = reparti_list[0]["reparto_id"]
        else:
            reparto_id = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            
        all_tags = []
        try:
            all_tags = c.execute(text("SELECT tag_id, nome, colore, descrizione FROM tag_operatori ORDER BY nome")).mappings().all()
        except Exception:
            pass

        if reparto_id is None:
            return templates.TemplateResponse(r, "matrice_assenze.html", {
                "request": r, "cfg": CFG, "user": user, 
                "error": "Non sei assegnato a nessun reparto. Contatta l'amministratore.", 
                "mese": mese, "anno": anno, "reparto_id": None, "reparti": reparti_list,
                "sedi_reparto": [], "sede_id": None, "all_tags": all_tags, "tag_id": tag_id, "conteggio_presenti": []
            })
            
        reparto_nome = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": reparto_id}).scalar()

        # Query distinct sedi of operators assigned to this department
        sedi_reparto = c.execute(text("""
            SELECT DISTINCT s.sede_id, s.nome
            FROM users u
            JOIN sedi s ON u.sede_id = s.sede_id
            WHERE u.reparto_id = :rid AND u.attivo = 1
            ORDER BY s.nome
        """), {"rid": reparto_id}).mappings().all()
        
        # Query active operators in this department (filtered by sede_id and tag_id if provided)
        op_where = "u.reparto_id = :rid AND u.attivo = 1"
        op_params = {"rid": reparto_id}
        if sede_id:
            op_where += " AND u.sede_id = :sid"
            op_params["sid"] = sede_id
        if tag_id:
            op_where += " AND u.user_id IN (SELECT user_id FROM operatori_tag WHERE tag_id = :tid)"
            op_params["tid"] = tag_id

        operators = c.execute(text(f"""
            SELECT u.user_id, u.nome, u.cognome, u.username, u.ruolo, u.sede_id, s.nome AS sede_nome, s.comune_id AS op_comune_id
            FROM users u
            LEFT JOIN sedi s ON u.sede_id = s.sede_id
            WHERE {op_where}
            ORDER BY u.cognome, u.nome
        """), op_params).mappings().all()
        
        # Mapping tag per ciascun operatore
        op_tags_map = {}
        try:
            op_tags_rows = c.execute(text("""
                SELECT ot.user_id, t.tag_id, t.nome, t.colore
                FROM operatori_tag ot
                JOIN tag_operatori t ON ot.tag_id = t.tag_id
                ORDER BY t.nome
            """)).mappings().all()
            for otr in op_tags_rows:
                uid = otr["user_id"]
                if uid not in op_tags_map:
                    op_tags_map[uid] = []
                op_tags_map[uid].append({
                    "tag_id": otr["tag_id"],
                    "nome": otr["nome"],
                    "colore": otr["colore"]
                })
        except Exception:
            pass

        _, num_days = calendar.monthrange(anno, mese)
        first_day_of_month = date(anno, mese, 1)
        last_day_of_month = date(anno, mese, num_days)
        
        festivita_list = c.execute(text("""
            SELECT f.data, f.descrizione, f.comune_id, c.nome as comune_nome 
            FROM festivita f
            LEFT JOIN comuni c ON f.comune_id = c.comune_id
            WHERE f.data >= :start AND f.data <= :end
        """), {"start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()
        
        assenze_list = c.execute(text("""
            SELECT a.user_id, a.data_inizio, a.data_fine, a.motivo
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            WHERE u.reparto_id = :rid AND a.data_inizio <= :end AND a.data_fine >= :start
        """), {"rid": reparto_id, "start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()

        presenze_list = c.execute(text("""
            SELECT p.user_id, p.data_inizio, p.data_fine, p.tipo, p.nota
            FROM presenze p
            JOIN users u ON p.user_id = u.user_id
            WHERE u.reparto_id = :rid AND p.data_inizio <= :end AND p.data_fine >= :start
        """), {"rid": reparto_id, "start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()

        # Check today's absences specifically
        today_str = today.isoformat()
        is_today_weekend = today.weekday() in (5, 6)

        today_festivita = c.execute(text("""
            SELECT f.data, f.descrizione, f.comune_id, c.nome as comune_nome 
            FROM festivita f
            LEFT JOIN comuni c ON f.comune_id = c.comune_id
            WHERE f.data = :today
        """), {"today": today_str}).mappings().all()

        today_assenze = c.execute(text("""
            SELECT a.user_id, a.motivo
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            WHERE u.reparto_id = :rid AND a.data_inizio <= :today AND a.data_fine >= :today
        """), {"rid": reparto_id, "today": today_str}).mappings().all()
        today_absent_map = {a["user_id"]: a["motivo"] for a in today_assenze}
        
        giorni = []
        wd_names = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        for day_num in range(1, num_days + 1):
            d = date(anno, mese, day_num)
            d_str = d.isoformat()
            is_weekend = d.weekday() in (5, 6)
            is_today = (d == today)
            
            header_holiday = None
            for f in festivita_list:
                if f["data"] == d_str:
                    if f["comune_id"] is None:
                        header_holiday = f["descrizione"]
                        break
                    elif not header_holiday:
                        header_holiday = f"{f['descrizione']} ({f['comune_nome']})"
                        
            giorni.append({
                "day_num": day_num,
                "is_weekend": is_weekend,
                "is_today": is_today,
                "holiday": header_holiday,
                "weekday_name": wd_names[d.weekday()]
            })
            
        matrix = []
        for op in operators:
            giorni_stato = []
            op_id = op["user_id"]
            op_comune_id = op["op_comune_id"]

            is_today_holiday = False
            for f in today_festivita:
                if f["comune_id"] is None or (op_comune_id is not None and f["comune_id"] == op_comune_id):
                    is_today_holiday = True
                    break

            is_absent_today = False
            today_absent_motivo = None
            if not is_today_weekend and not is_today_holiday:
                if op_id in today_absent_map:
                    is_absent_today = True
                    today_absent_motivo = today_absent_map[op_id]
            
            for day_num in range(1, num_days + 1):
                d = date(anno, mese, day_num)
                d_str = d.isoformat()
                is_today = (d == today)
                
                absent_record = None
                for a in assenze_list:
                    if a["user_id"] == op_id:
                        if a["data_inizio"] <= d_str <= a["data_fine"]:
                            absent_record = a
                            break
                            
                presence_record = None
                for p in presenze_list:
                    if p["user_id"] == op_id:
                        if p["data_inizio"] <= d_str <= p["data_fine"]:
                            presence_record = p
                            break

                is_absent = absent_record is not None
                motivo = absent_record["motivo"] if is_absent else None
                
                is_present = presence_record is not None
                presenza_tipo = presence_record["tipo"] if is_present else None
                presenza_nota = presence_record["nota"] if is_present else None

                is_weekend = d.weekday() in (5, 6)
                
                holiday = None
                for f in festivita_list:
                    if f["data"] == d_str:
                        if f["comune_id"] is None or (op_comune_id is not None and f["comune_id"] == op_comune_id):
                            holiday = f"{f['descrizione']} ({f['comune_nome']})" if f["comune_nome"] else f["descrizione"]
                            break

                # Se il giorno è una festività o un fine settimana (Sabato/Domenica), non evidenziare come ferie/assenza
                if holiday or is_weekend:
                    is_absent = False
                    is_present = False
                
                giorni_stato.append({
                    "absent": is_absent,
                    "motivo": motivo,
                    "present": is_present,
                    "presenza_tipo": presenza_tipo,
                    "presenza_nota": presenza_nota,
                    "holiday": holiday,
                    "is_weekend": is_weekend,
                    "is_today": is_today,
                    "weekday_name": wd_names[d.weekday()]
                })
                
            matrix.append({
                "operator_id": op["user_id"],
                "operator_nome": f"{(op['cognome'] or '').strip()} {(op['nome'] or '').strip()}".strip() or op['username'],
                "operator_ruolo": op["ruolo"] or "operatore",
                "sede_nome": op["sede_nome"] or "",
                "tags": op_tags_map.get(op["user_id"], []),
                "giorni_stato": giorni_stato,
                "is_absent_today": is_absent_today,
                "today_absent_motivo": today_absent_motivo
            })

        # Calcolo del conteggio operatori presenti per ciascun giorno
        tot_operators = len(matrix)
        conteggio_presenti = []
        for day_idx, day_info in enumerate(giorni):
            if day_info["is_weekend"] or day_info["holiday"]:
                presenti_count = 0
            else:
                presenti_count = sum(1 for row in matrix if not row["giorni_stato"][day_idx]["absent"])
            conteggio_presenti.append({
                "day_num": day_info["day_num"],
                "is_today": day_info["is_today"],
                "is_weekend": day_info["is_weekend"],
                "is_holiday": bool(day_info["holiday"]),
                "presenti": presenti_count,
                "totale": tot_operators
            })
            
        months_it = {
            1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
            5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
            9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
        }
        nome_mese = months_it.get(mese, "")
        
        if mese == 1:
            prev_mese, prev_anno = 12, anno - 1
        else:
            prev_mese, prev_anno = mese - 1, anno
            
        if mese == 12:
            next_mese, next_anno = 1, anno + 1
        else:
            next_mese, next_anno = mese + 1, anno
            
    return templates.TemplateResponse(r, "matrice_assenze.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "giorni": giorni,
        "matrix": matrix,
        "conteggio_presenti": conteggio_presenti,
        "mese": mese,
        "anno": anno,
        "nome_mese": nome_mese,
        "prev_mese": prev_mese,
        "prev_anno": prev_anno,
        "next_mese": next_mese,
        "next_anno": next_anno,
        "reparto_id": reparto_id,
        "reparto_nome": reparto_nome,
        "reparti": reparti_list,
        "sedi_reparto": sedi_reparto,
        "sede_id": sede_id,
        "all_tags": all_tags,
        "tag_id": tag_id
    })

@router.get("/servizi-assegnati", response_class=HTMLResponse)
def servizi_assegnati(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        user_reparto_id = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
        
        reparto_nome = None
        if user_reparto_id:
            reparto_nome = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": user_reparto_id}).scalar()
            
        operators_raw = c.execute(text("""
            SELECT u.user_id, u.nome, u.cognome, u.ruolo, r.nome AS reparto_nome,
                   s.servizio_id, s.descrizione AS servizio_nome
            FROM users u
            LEFT JOIN operatori_servizi os ON u.user_id = os.user_id
            LEFT JOIN servizi s ON os.servizio_id = s.servizio_id AND (:reparto_id IS NULL OR s.reparto_id = :reparto_id)
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE u.ruolo != 'normale' AND u.user_id != 1 AND u.attivo = 1
              AND (:reparto_id IS NULL OR u.reparto_id = :reparto_id)
            ORDER BY u.nome, u.cognome, s.descrizione
        """), {"reparto_id": user_reparto_id}).mappings().all()
        
        operators = {}
        for row in operators_raw:
            uid = row["user_id"]
            if uid not in operators:
                operators[uid] = {
                    "user_id": uid,
                    "nome": row["nome"],
                    "cognome": row["cognome"],
                    "ruolo": row["ruolo"],
                    "reparto_nome": row["reparto_nome"],
                    "servizi": []
                }
            if row["servizio_id"]:
                operators[uid]["servizi"].append({
                    "servizio_id": row["servizio_id"],
                    "nome": row["servizio_nome"]
                })
        operators_list = list(operators.values())
        
        services_raw = c.execute(text("""
            SELECT s.servizio_id, s.descrizione AS servizio_nome, r.nome AS reparto_nome,
                   u.user_id, u.nome AS operatore_nome, u.cognome AS operatore_cognome, u.ruolo AS operatore_ruolo
            FROM servizi s
            LEFT JOIN reparti r ON s.reparto_id = r.reparto_id
            LEFT JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
            LEFT JOIN users u ON os.user_id = u.user_id AND u.attivo = 1 AND (:reparto_id IS NULL OR u.reparto_id = :reparto_id)
            WHERE (:reparto_id IS NULL OR s.reparto_id = :reparto_id)
            ORDER BY r.nome, s.descrizione, u.nome, u.cognome
        """), {"reparto_id": user_reparto_id}).mappings().all()
        
        services = {}
        for row in services_raw:
            sid = row["servizio_id"]
            if sid not in services:
                services[sid] = {
                    "servizio_id": sid,
                    "nome": row["servizio_nome"],
                    "reparto_nome": row["reparto_nome"],
                    "operatori": []
                }
            if row["user_id"]:
                services[sid]["operatori"].append({
                    "user_id": row["user_id"],
                    "nome": row["operatore_nome"],
                    "cognome": row["operatore_cognome"],
                    "ruolo": row["operatore_ruolo"]
                })
        services_list = list(services.values())
        
    return templates.TemplateResponse(r, "servizi_assegnati.html", {
        "request": r, "cfg": CFG, "user": user,
        "operatori": operators_list,
        "servizi": services_list,
        "reparto_nome": reparto_nome
    })

# =========================================================================
# GESTIONE REPERIBILITÀ H24 (CALENDARIO & ASSEGNAZIONE TURNI)
# =========================================================================

def format_time_add(start_str: str, duration_hours: float):
    try:
        parts = (start_str or "18:00").split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        h, m = 18, 0
    total_start_min = h * 60 + m
    dur_min = int(round(float(duration_hours or 0) * 60))
    total_end_min = total_start_min + dur_min

    end_days = total_end_min // 1440
    rem_min = total_end_min % 1440
    end_h = rem_min // 60
    end_m = rem_min % 60

    start_disp = f"{h:02d}:{m:02d}"
    end_disp = f"{end_h:02d}:{end_m:02d}"
    if end_days > 0:
        end_disp += f" (+{end_days}g)"
    return start_disp, end_disp

def calc_turni_slots(start_time_str, turni_raw, default_durata=6.0):
    slots = []
    if not turni_raw:
        s_disp, e_disp = format_time_add(start_time_str or "18:00", default_durata)
        slots.append({
            "ordine_turno": 1,
            "durata_ore": default_durata,
            "badge_orario": f"{s_disp} - {e_disp}",
            "label": f"Turno 1 ({s_disp} - {e_disp})"
        })
        return slots

    curr_start = start_time_str or "18:00"
    for t in turni_raw:
        dur = float(t["durata_ore"] if t["durata_ore"] is not None else default_durata)
        s_disp, e_disp = format_time_add(curr_start, dur)
        slots.append({
            "ordine_turno": t["ordine_turno"],
            "durata_ore": dur,
            "badge_orario": f"{s_disp} - {e_disp}",
            "label": f"Turno {t['ordine_turno']} ({s_disp} - {e_disp})"
        })
        curr_start = e_disp.split(" ")[0]
    return slots

@router.get("/reperibilita", response_class=HTMLResponse)
def reperibilita_calendario(
    r: Request, 
    mese: int = None, 
    anno: int = None, 
    reparto_id: int = None,
    msg: str = None,
    error: str = None
):
    if not CFG.get('modulo_presenze', True):
        return RedirectResponse(url="/")
    if "user" not in r.session:
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    uid = user.get("id")

    today = date.today()
    if mese is None:
        mese = today.month
    if anno is None:
        anno = today.year
    if mese < 1: mese = 1
    elif mese > 12: mese = 12
    if anno < 2000 or anno > 2100: anno = today.year

    _, num_days = calendar.monthrange(anno, mese)
    first_day_of_month = date(anno, mese, 1)
    last_day_of_month = date(anno, mese, num_days)

    if mese == 1:
        prev_mese, prev_anno = 12, anno - 1
    else:
        prev_mese, prev_anno = mese - 1, anno

    if mese == 12:
        next_mese, next_anno = 1, anno + 1
    else:
        next_mese, next_anno = mese + 1, anno

    months_it = {
        1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
        5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
        9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
    }
    nome_mese = months_it.get(mese, "")

    with engine.connect() as c:
        # Reparti con reperibilita_h24 = 1
        reparti_rep = c.execute(text("""
            SELECT reparto_id, nome, reperibilita_orario_inizio, reperibilita_festivo_inizio
            FROM reparti
            WHERE reperibilita_h24 = 1
            ORDER BY nome
        """)).mappings().all()

        if not reparti_rep:
            return templates.TemplateResponse(r, "reperibilita.html", {
                "request": r, "cfg": CFG, "user": user,
                "reparti_rep": [], "sel_reparto": None,
                "weeks": [], "summary_list": [], "elenco_stampa": [],
                "data_stampa": "",
                "mese": mese, "anno": anno, "nome_mese": nome_mese,
                "prev_mese": prev_mese, "prev_anno": prev_anno,
                "next_mese": next_mese, "next_anno": next_anno,
                "user_is_reperibile": False, "can_manage": False,
                "tot_feriali": 0, "tot_festivi": 0, "tot_turni": 0, "tot_ore": 0,
                "msg": msg, "error": "Nessun reparto ha attualmente la Reperibilità h24 abilitata. È possibile abilitarla nell'Anagrafica Reparti."
            })

        rep_ids = [rp["reparto_id"] for rp in reparti_rep]
        if reparto_id and reparto_id in rep_ids:
            sel_reparto_id = reparto_id
        elif user.get("reparto_id") in rep_ids:
            sel_reparto_id = user.get("reparto_id")
        else:
            sel_reparto_id = rep_ids[0]

        sel_reparto = next(rp for rp in reparti_rep if rp["reparto_id"] == sel_reparto_id)

        # Turni definiti per il reparto selezionato
        turni_feriali_raw = c.execute(text("""
            SELECT * FROM reparti_reperibilita_turni
            WHERE reparto_id = :rid AND tipo_giorno = 'feriale'
            ORDER BY ordine_turno
        """), {"rid": sel_reparto_id}).mappings().all()

        turni_festivi_raw = c.execute(text("""
            SELECT * FROM reparti_reperibilita_turni
            WHERE reparto_id = :rid AND tipo_giorno = 'festivo'
            ORDER BY ordine_turno
        """), {"rid": sel_reparto_id}).mappings().all()

        slots_feriali = calc_turni_slots(sel_reparto["reperibilita_orario_inizio"] or "18:00", turni_feriali_raw, default_durata=6.0)
        slots_festivi = calc_turni_slots(sel_reparto["reperibilita_festivo_inizio"] or "08:00", turni_festivi_raw, default_durata=12.0)

        # Festività del mese
        festivita_rows = c.execute(text("""
            SELECT data, descrizione, comune_id FROM festivita
            WHERE data >= :start AND data <= :end
        """), {"start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()
        festivita_map = {f["data"]: f["descrizione"] for f in festivita_rows}

        is_rep_admin = bool(c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND UPPER(TRIM(t.nome)) = 'REP_ADMIN'
        """), {"uid": uid}).scalar()) or (user.get("ruolo") == "admin")

        is_admin_flag = 1 if (user.get("ruolo") == "admin" or is_rep_admin) else 0

        # Operatori attivi con tag 'Reperibile' o 'Rep_Admin'
        reperibili_raw = c.execute(text("""
            SELECT DISTINCT u.user_id, u.nome, u.cognome, u.username, u.email, u.telefono, u.reparto_id, r.nome as reparto_nome
            FROM users u
            JOIN operatori_tag ot ON u.user_id = ot.user_id
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE LOWER(TRIM(t.nome)) IN ('reperibile', 'rep_admin', 'reperibili', 'reperibilità', 'reperibilita') 
              AND u.attivo = 1
              AND (
                  u.reparto_id = :rid 
                  OR u.reparto_id IS NULL
                  OR u.user_id IN (
                      SELECT os.user_id 
                      FROM operatori_servizi os 
                      JOIN servizi s ON os.servizio_id = s.servizio_id 
                      WHERE s.reparto_id = :rid
                  )
                  OR u.user_id IN (
                      SELECT ra.user_id 
                      FROM reperibilita_assegnazioni ra 
                      WHERE ra.reparto_id = :rid
                  )
                  OR :is_admin = 1
                  OR (SELECT COUNT(*) FROM reparti WHERE reperibilita_h24 = 1) <= 1
              )
            ORDER BY u.cognome, u.nome
        """), {"rid": sel_reparto_id, "is_admin": is_admin_flag}).mappings().all()

        reperibili_list = [dict(r_op) for r_op in reperibili_raw]
        rep_uids = {r_op["user_id"] for r_op in reperibili_list}

        user_is_reperibile = (uid in rep_uids) or bool(c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND LOWER(TRIM(t.nome)) IN ('reperibile', 'rep_admin', 'reperibili', 'reperibilità', 'reperibilita')
        """), {"uid": uid}).scalar())

        # Verifica stato lock del mese per il reparto
        # Di default, i mesi sono in sola lettura (locked) finché un Rep_Admin o Admin li sblocca
        lock_row = c.execute(text("""
            SELECT sbloccato, modificato_da, aggiornato_il FROM reperibilita_mesi_lock
            WHERE reparto_id = :rid AND anno = :anno AND mese = :mese
        """), {"rid": sel_reparto_id, "anno": anno, "mese": mese}).mappings().first()
        is_month_locked = not bool(lock_row and lock_row["sbloccato"] == 1)

        # Assenze registrate nel mese (per verificare chi è presente nei giorni)
        assenze_rows = c.execute(text("""
            SELECT user_id, data_inizio, data_fine, motivo
            FROM assenze
            WHERE data_inizio <= :end AND data_fine >= :start
        """), {"start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()

        absent_map = {}
        for a in assenze_rows:
            auid = a["user_id"]
            try:
                a_start = datetime.strptime(a["data_inizio"], "%Y-%m-%d").date()
                a_end = datetime.strptime(a["data_fine"], "%Y-%m-%d").date()
            except Exception:
                continue
            cur = max(first_day_of_month, a_start)
            end_limit = min(last_day_of_month, a_end)
            while cur <= end_limit:
                absent_map[(auid, cur.isoformat())] = a["motivo"] or "Assenza"
                cur += timedelta(days=1)

        # Assegnazioni esistenti per il reparto nel mese (con telefono dell'operatore)
        assegnazioni_raw = c.execute(text("""
            SELECT ra.*, u.nome, u.cognome, u.username, u.telefono
            FROM reperibilita_assegnazioni ra
            JOIN users u ON ra.user_id = u.user_id
            WHERE ra.reparto_id = :rid AND ra.data >= :start AND ra.data <= :end
            ORDER BY ra.data, ra.ordine_turno, u.cognome, u.nome
        """), {"rid": sel_reparto_id, "start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()

        assignments_by_day_turno = {}
        for ass in assegnazioni_raw:
            key = (ass["data"], ass["ordine_turno"])
            if key not in assignments_by_day_turno:
                assignments_by_day_turno[key] = []
            assignments_by_day_turno[key].append(dict(ass))

        # Strutturazione settimane e giorni
        cal = calendar.Calendar(firstweekday=0)
        weeks_dates = cal.monthdatescalendar(anno, mese)
        weeks = []

        for w in weeks_dates:
            week_days = []
            for d in w:
                d_str = d.isoformat()
                is_curr_m = (d.month == mese)
                is_today = (d == today)
                is_weekend = d.weekday() in (5, 6)
                holiday_desc = festivita_map.get(d_str)
                is_festivo = is_weekend or bool(holiday_desc)
                tipo_giorno = "festivo" if is_festivo else "feriale"

                day_slots = slots_festivi if is_festivo else slots_feriali
                turni_day = []

                for sl in day_slots:
                    ord_t = sl["ordine_turno"]
                    assigned_users = assignments_by_day_turno.get((d_str, ord_t), [])

                    curr_user_assigned = any(au["user_id"] == uid for au in assigned_users)
                    curr_user_assigned_id = next((au["id"] for au in assigned_users if au["user_id"] == uid), None)
                    curr_user_absent_reason = absent_map.get((uid, d_str))

                    # Operatori disponibili (con tag 'Reperibile' e non assenti in questa data)
                    available_ops = []
                    for op in reperibili_list:
                        op_uid = op["user_id"]
                        is_already = any(au["user_id"] == op_uid for au in assigned_users)
                        if not is_already:
                            abs_reason = absent_map.get((op_uid, d_str))
                            if not abs_reason:
                                available_ops.append(op)

                    turni_day.append({
                        "ordine_turno": ord_t,
                        "durata_ore": sl["durata_ore"],
                        "badge_orario": sl["badge_orario"],
                        "label": sl["label"],
                        "assegnati": assigned_users,
                        "curr_user_assigned": curr_user_assigned,
                        "curr_user_assigned_id": curr_user_assigned_id,
                        "curr_user_absent": bool(curr_user_absent_reason),
                        "curr_user_absent_reason": curr_user_absent_reason,
                        "available_ops": available_ops
                    })

                week_days.append({
                    "date": d,
                    "date_str": d_str,
                    "day_num": d.day,
                    "is_current_month": is_curr_m,
                    "is_today": is_today,
                    "is_weekend": is_weekend,
                    "is_festivo": is_festivo,
                    "holiday_desc": holiday_desc,
                    "tipo_giorno": tipo_giorno,
                    "turni": turni_day
                })
            weeks.append(week_days)

        # Tabella Elenco Reperibili per la Stampa (giorno settimana, data, operatore, telefono, fasce orarie coperte)
        giorni_nomi = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        elenco_stampa = []
        for day_num in range(1, num_days + 1):
            d = date(anno, mese, day_num)
            d_str = d.isoformat()
            giorno_settimana = giorni_nomi[d.weekday()]
            data_formatted = d.strftime("%d/%m/%Y")
            giorno_e_data = f"{giorno_settimana} {data_formatted}"
            is_weekend = d.weekday() in (5, 6)
            holiday_desc = festivita_map.get(d_str)
            is_festivo = is_weekend or bool(holiday_desc)
            tipo_giorno = "festivo" if is_festivo else "feriale"
            day_slots = slots_festivi if is_festivo else slots_feriali

            turni_giorno = []
            for sl in day_slots:
                ord_t = sl["ordine_turno"]
                assigned_users = assignments_by_day_turno.get((d_str, ord_t), [])
                badge_orario = sl.get("badge_orario") or ""
                label_turno = sl.get("label") or f"Turno {ord_t}"
                
                fascia_label = badge_orario
                if len(day_slots) > 1 and label_turno:
                    fascia_label = f"{badge_orario} ({label_turno})"

                if assigned_users:
                    for au in assigned_users:
                        nome_operatore = f"{au.get('cognome') or ''} {au.get('nome') or ''}".strip() or au.get('username') or "—"
                        tel = (au.get("telefono") or "").strip()
                        turni_giorno.append({
                            "ordine_turno": ord_t,
                            "operatore": nome_operatore,
                            "telefono": tel if tel else "—",
                            "fascia_oraria": fascia_label,
                            "coperto": True
                        })
                else:
                    turni_giorno.append({
                        "ordine_turno": ord_t,
                        "operatore": "— Non assegnato —",
                        "telefono": "—",
                        "fascia_oraria": fascia_label,
                        "coperto": False
                    })

            elenco_stampa.append({
                "date": d,
                "date_str": d_str,
                "day_num": day_num,
                "giorno_settimana": giorno_settimana,
                "data_formattata": data_formatted,
                "giorno_e_data": giorno_e_data,
                "is_festivo": is_festivo,
                "holiday_desc": holiday_desc,
                "tipo_giorno": tipo_giorno,
                "turni": turni_giorno,
                "num_righe": len(turni_giorno)
            })

        # Riepilogo mensile dei reperibili a fondo pagina
        user_counts = {}
        for ass in assegnazioni_raw:
            auid = ass["user_id"]
            if auid not in user_counts:
                user_counts[auid] = {
                    "user_id": auid,
                    "nome_completo": f"{ass['cognome'] or ''} {ass['nome'] or ''}".strip() or ass['username'],
                    "username": ass["username"],
                    "telefono": (ass.get("telefono") or "").strip() or "—",
                    "feriali": 0,
                    "festivi": 0,
                    "ore": 0.0
                }
            if ass["tipo_giorno"] == "festivo":
                user_counts[auid]["festivi"] += 1
            else:
                user_counts[auid]["feriali"] += 1
            user_counts[auid]["ore"] += float(ass.get("durata_ore") or 0.0)

        summary_list = []
        for op in reperibili_list:
            op_uid = op["user_id"]
            if op_uid in user_counts:
                summary_list.append(user_counts[op_uid])
            else:
                summary_list.append({
                    "user_id": op_uid,
                    "nome_completo": f"{op['cognome'] or ''} {op['nome'] or ''}".strip() or op['username'],
                    "username": op["username"],
                    "telefono": (op.get("telefono") or "").strip() or "—",
                    "feriali": 0,
                    "festivi": 0,
                    "ore": 0.0
                })

        for auid, data_u in user_counts.items():
            if not any(s["user_id"] == auid for s in summary_list):
                summary_list.append(data_u)

        summary_list.sort(key=lambda x: x["nome_completo"].lower())

        tot_feriali = sum(s["feriali"] for s in summary_list)
        tot_festivi = sum(s["festivi"] for s in summary_list)
        tot_turni = tot_feriali + tot_festivi
        tot_ore = sum(s["ore"] for s in summary_list)

        return templates.TemplateResponse(r, "reperibilita.html", {
            "request": r, "cfg": CFG, "user": user,
            "reparti_rep": reparti_rep,
            "sel_reparto": sel_reparto,
            "weeks": weeks,
            "summary_list": summary_list,
            "elenco_stampa": elenco_stampa,
            "data_stampa": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "mese": mese, "anno": anno, "nome_mese": nome_mese,
            "prev_mese": prev_mese, "prev_anno": prev_anno,
            "next_mese": next_mese, "next_anno": next_anno,
            "user_is_reperibile": user_is_reperibile,
            "is_rep_admin": is_rep_admin,
            "is_month_locked": is_month_locked,
            "tot_feriali": tot_feriali,
            "tot_festivi": tot_festivi,
            "tot_turni": tot_turni,
            "tot_ore": tot_ore,
            "msg": msg, "error": error
        })

@router.post("/reperibilita/toggle-lock")
def reperibilita_toggle_lock(
    r: Request,
    reparto_id: int = Form(...),
    anno: int = Form(...),
    mese: int = Form(...)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    current_u = r.session.get("user")
    cid = current_u.get("id")

    with engine.begin() as c:
        is_rep_admin = bool(c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND UPPER(t.nome) = 'REP_ADMIN'
        """), {"uid": cid}).scalar()) or (current_u.get("ruolo") == "admin")

        if not is_rep_admin:
            err = "Solo un utente Rep_Admin o un amministratore può sbloccare o bloccare le modifiche del mese."
            params = urllib.parse.urlencode({"anno": anno, "mese": mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        lock_row = c.execute(text("""
            SELECT id, sbloccato FROM reperibilita_mesi_lock
            WHERE reparto_id = :rid AND anno = :anno AND mese = :mese
        """), {"rid": reparto_id, "anno": anno, "mese": mese}).mappings().first()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if lock_row:
            current_sbloccato = lock_row["sbloccato"] or 0
            new_sbloccato = 0 if current_sbloccato == 1 else 1
            c.execute(text("""
                UPDATE reperibilita_mesi_lock
                SET sbloccato = :s, modificato_da = :uid, aggiornato_il = :now
                WHERE id = :id
            """), {"s": new_sbloccato, "uid": cid, "now": now_str, "id": lock_row["id"]})
        else:
            # Default era locked (0), quindi al toggle viene sbloccato (1)
            new_sbloccato = 1
            c.execute(text("""
                INSERT INTO reperibilita_mesi_lock (reparto_id, anno, mese, sbloccato, modificato_da, aggiornato_il)
                VALUES (:rid, :anno, :mese, :s, :uid, :now)
            """), {"rid": reparto_id, "anno": anno, "mese": mese, "s": new_sbloccato, "uid": cid, "now": now_str})

    if new_sbloccato == 1:
        msg = "Mese sbloccato: gli operatori reperibili possono ora gestire i propri turni."
    else:
        msg = "Mese bloccato in sola lettura: solo gli utenti Rep_Admin possono modificare i turni."

    params = urllib.parse.urlencode({"anno": anno, "mese": mese, "reparto_id": reparto_id, "msg": msg})
    return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

@router.post("/reperibilita/assegna")
def reperibilita_assegna(
    r: Request,
    reparto_id: int = Form(...),
    data: str = Form(...),
    tipo_giorno: str = Form(...),
    ordine_turno: int = Form(...),
    durata_ore: float = Form(0.0),
    user_id: int = Form(...),
    redirect_mese: int = Form(...),
    redirect_anno: int = Form(...)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    current_u = r.session.get("user")
    cid = current_u.get("id")

    with engine.begin() as c:
        is_rep_admin = bool(c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND UPPER(t.nome) = 'REP_ADMIN'
        """), {"uid": cid}).scalar()) or (current_u.get("ruolo") == "admin")

        # Verifica stato lock del mese: se locked, solo Rep_Admin o Admin possono assegnare turni
        try:
            d_obj = datetime.strptime(data, "%Y-%m-%d").date()
            d_year = d_obj.year
            d_month = d_obj.month
        except Exception:
            d_year = redirect_anno
            d_month = redirect_mese

        lock_row = c.execute(text("""
            SELECT sbloccato FROM reperibilita_mesi_lock
            WHERE reparto_id = :rid AND anno = :a AND mese = :m
        """), {"rid": reparto_id, "a": d_year, "m": d_month}).mappings().first()
        is_month_locked = not bool(lock_row and lock_row["sbloccato"] == 1)

        if is_month_locked and not is_rep_admin:
            err = "Il mese selezionato è in sola lettura. Solo un utente Rep_Admin o un amministratore può assegnare o modificare i turni."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        # Solo chi ha il tag Rep_Admin o admin può assegnare altri operatori
        if user_id != cid and not is_rep_admin:
            err = "Solo l'utente con il tag Rep_Admin può assegnare turni ad altri reperibili."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        # Verifica che l'utente assegnato abbia il tag 'Reperibile' o 'Rep_Admin'
        is_rep_tag = c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND LOWER(TRIM(t.nome)) IN ('reperibile', 'rep_admin', 'reperibili', 'reperibilità', 'reperibilita')
        """), {"uid": user_id}).scalar()
        if not is_rep_tag:
            err = "L'operatore selezionato non possiede il tag 'Reperibile'."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        # Verifica presenza: l'operatore non deve avere assenze registrate in tale data
        absent_motivo = c.execute(text("""
            SELECT motivo FROM assenze
            WHERE user_id = :uid AND data_inizio <= :d AND data_fine >= :d
            LIMIT 1
        """), {"uid": user_id, "d": data}).scalar()
        if absent_motivo:
            err = f"L'operatore risulta assente in data {data} ({absent_motivo}). I turni possono essere selezionati solo nei giorni di presenza."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        # Verifica se già assegnato allo stesso turno
        already = c.execute(text("""
            SELECT id FROM reperibilita_assegnazioni
            WHERE reparto_id = :rid AND data = :d AND ordine_turno = :ord AND user_id = :uid
        """), {"rid": reparto_id, "d": data, "ord": ordine_turno, "uid": user_id}).scalar()
        if already:
            err = "L'operatore è già assegnato a questo turno."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        c.execute(text("""
            INSERT INTO reperibilita_assegnazioni (reparto_id, data, tipo_giorno, ordine_turno, durata_ore, user_id)
            VALUES (:rid, :d, :tipo, :ord, :dur, :uid)
        """), {
            "rid": reparto_id,
            "d": data,
            "tipo": tipo_giorno,
            "ord": ordine_turno,
            "dur": durata_ore,
            "uid": user_id
        })

    msg = "Turno di reperibilità assegnato con successo."
    params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "msg": msg})
    return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

@router.post("/reperibilita/rimuovi")
def reperibilita_rimuovi(
    r: Request,
    assegnazione_id: int = Form(...),
    reparto_id: int = Form(...),
    redirect_mese: int = Form(...),
    redirect_anno: int = Form(...)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    current_u = r.session.get("user")
    cid = current_u.get("id")

    with engine.begin() as c:
        ass_row = c.execute(text("SELECT * FROM reperibilita_assegnazioni WHERE id = :id"), {"id": assegnazione_id}).mappings().first()
        if not ass_row:
            err = "Assegnazione non trovata."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        is_rep_admin = bool(c.execute(text("""
            SELECT 1 FROM operatori_tag ot
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            WHERE ot.user_id = :uid AND UPPER(t.nome) = 'REP_ADMIN'
        """), {"uid": cid}).scalar()) or (current_u.get("ruolo") == "admin")

        # Verifica stato lock del mese: se locked, solo Rep_Admin o Admin possono rimuovere turni
        try:
            d_obj = datetime.strptime(ass_row["data"], "%Y-%m-%d").date()
            d_year = d_obj.year
            d_month = d_obj.month
        except Exception:
            d_year = redirect_anno
            d_month = redirect_mese

        lock_row = c.execute(text("""
            SELECT sbloccato FROM reperibilita_mesi_lock
            WHERE reparto_id = :rid AND anno = :a AND mese = :m
        """), {"rid": reparto_id, "a": d_year, "m": d_month}).mappings().first()
        is_month_locked = not bool(lock_row and lock_row["sbloccato"] == 1)

        if is_month_locked and not is_rep_admin:
            err = "Il mese selezionato è in sola lettura. Solo un utente Rep_Admin o un amministratore può modificare o rimuovere i turni."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        # Solo l'utente stesso (togliersi dal turno) o chi ha Rep_Admin / admin può rimuovere l'assegnazione
        if ass_row["user_id"] != cid and not is_rep_admin:
            err = "Solo l'utente con il tag Rep_Admin può rimuovere le assegnazioni di altri operatori."
            params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "error": err})
            return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)

        c.execute(text("DELETE FROM reperibilita_assegnazioni WHERE id = :id"), {"id": assegnazione_id})

    msg = "Turno di reperibilità rimosso con successo."
    params = urllib.parse.urlencode({"anno": redirect_anno, "mese": redirect_mese, "reparto_id": reparto_id, "msg": msg})
    return RedirectResponse(url=f"/reperibilita?{params}", status_code=303)


