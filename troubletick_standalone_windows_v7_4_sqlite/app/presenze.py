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
        assenze = c.execute(text("""
            SELECT a.*, u.nome, u.cognome, u.username, r.nome as reparto_nome
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE a.user_id = :uid
            ORDER BY a.data_inizio DESC
        """), {"uid": uid}).mappings().all()
            
        festivita = c.execute(text("""
            SELECT * FROM festivita ORDER BY data DESC
        """)).mappings().all()
            
    return templates.TemplateResponse(r, "calendario.html", {
        "request": r, "cfg": CFG, "user": user, "assenze": assenze, "festivita": festivita,
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
        presenze = c.execute(text("""
            SELECT p.*, u.nome, u.cognome, r.nome as reparto_nome
            FROM presenze p
            JOIN users u ON p.user_id = u.user_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE p.user_id = :uid
            ORDER BY p.data_inizio DESC
        """), {"uid": uid}).mappings().all()
        
        festivita = c.execute(text("""
            SELECT * FROM festivita ORDER BY data DESC
        """)).mappings().all()
        
    return templates.TemplateResponse(r, "calendario_presenze.html", {
        "request": r, "cfg": CFG, "user": user, "presenze": presenze, "festivita": festivita
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
            curr_dt = di_dt
            while curr_dt <= df_dt:
                dates_to_check.append(curr_dt.strftime("%Y-%m-%d"))
                curr_dt += timedelta(days=1)
                
            with engine.connect() as c_read:
                servizi = c_read.execute(text("""
                    SELECT servizio_id, descrizione 
                    FROM servizi 
                    WHERE reparto_id = :rid
                """), {"rid": reparto_id}).mappings().all()
                
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
                day_has_uncovered_service = False
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
                        
                    if len(servizi_ops[s["servizio_id"]]) > 0 and present_count == 0:
                        day_has_uncovered_service = True
                        
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
                    "servizi": day_servizi,
                    "uncovered": day_has_uncovered_service
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
def assenze_mese(r: Request, mese: int = None, anno: int = None, reparto_id: int = None):
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
            
        if reparto_id is None:
            return templates.TemplateResponse(r, "matrice_assenze.html", {
                "request": r, "cfg": CFG, "user": user, 
                "error": "Non sei assegnato a nessun reparto. Contatta l'amministratore.", 
                "mese": mese, "anno": anno, "reparto_id": None, "reparti": reparti_list
            })
            
        reparto_nome = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": reparto_id}).scalar()
        
        # Query active operators in this department
        operators = c.execute(text("""
            SELECT user_id, nome, cognome, username, ruolo
            FROM users
            WHERE reparto_id = :rid AND attivo = 1
            ORDER BY cognome, nome
        """), {"rid": reparto_id}).mappings().all()
        
        _, num_days = calendar.monthrange(anno, mese)
        first_day_of_month = date(anno, mese, 1)
        last_day_of_month = date(anno, mese, num_days)
        
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

        presenze_list = c.execute(text("""
            SELECT p.user_id, p.data_inizio, p.data_fine, p.tipo, p.nota
            FROM presenze p
            JOIN users u ON p.user_id = u.user_id
            WHERE u.reparto_id = :rid AND p.data_inizio <= :end AND p.data_fine >= :start
        """), {"rid": reparto_id, "start": first_day_of_month.isoformat(), "end": last_day_of_month.isoformat()}).mappings().all()
        
        giorni = []
        wd_names = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        for day_num in range(1, num_days + 1):
            d = date(anno, mese, day_num)
            d_str = d.isoformat()
            is_weekend = d.weekday() in (5, 6)
            holiday = festivita_map.get(d_str)
            giorni.append({
                "day_num": day_num,
                "is_weekend": is_weekend,
                "holiday": holiday,
                "weekday_name": wd_names[d.weekday()]
            })
            
        matrix = []
        for op in operators:
            giorni_stato = []
            op_id = op["user_id"]
            for day_num in range(1, num_days + 1):
                d = date(anno, mese, day_num)
                d_str = d.isoformat()
                
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
                holiday = festivita_map.get(d_str)
                
                giorni_stato.append({
                    "absent": is_absent,
                    "motivo": motivo,
                    "present": is_present,
                    "presenza_tipo": presenza_tipo,
                    "presenza_nota": presenza_nota,
                    "holiday": holiday,
                    "is_weekend": is_weekend
                })
                
            matrix.append({
                "operator_nome": f"{op['nome']} {op['cognome']}".strip() or op['username'],
                "operator_ruolo": op["ruolo"] or "operatore",
                "giorni_stato": giorni_stato
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
