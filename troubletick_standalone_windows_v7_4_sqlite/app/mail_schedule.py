#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from datetime import datetime, timedelta

# Ensure script directory is in sys.path so imports work regardless of execution location
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from sqlalchemy import text
    from core import engine, CFG, BASE_DIR
    from email_utils import send_email_async
except ImportError as e:
    print(f"[ERRORE] Impossibile importare moduli core. Assicurati che l'ambiente virtuale sia attivo. Dettagli: {e}")
    sys.exit(1)

def get_next_working_day(conn):
    """
    Calcola la data della giornata lavorativa successiva escludendo sabati, domeniche 
    e date inserite nella tabella 'festivita'.
    """
    festivita_dates = set()
    try:
        fest_rows = conn.execute(text("SELECT data FROM festivita")).mappings().all()
        festivita_dates = {r["data"] for r in fest_rows}
    except Exception as e:
        print(f"[WARN] Impossibile recuperare festivita: {e}")

    target = datetime.today().date()
    while True:
        target += timedelta(days=1)
        # weekday(): 5 = Sabato, 6 = Domenica
        if target.weekday() >= 5:
            continue
        target_str = target.strftime("%Y-%m-%d")
        if target_str in festivita_dates:
            continue
        return target, target_str

def format_date_italian(d):
    """Formatta una data in italiano (es. Venerdì 17 Luglio 2026)"""
    days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    months = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    return f"{days[d.weekday()]} {d.day} {months[d.month - 1]} {d.year}"

def get_next_week_working_days(conn):
    """
    Ritorna la lista delle date (date_obj, date_str, formatted_str) dei giorni lavorativi (lunedì-venerdì)
    della settimana successiva.
    """
    from datetime import date, timedelta
    
    # Leggi festivita
    festivita_dates = set()
    try:
        fest_rows = conn.execute(text("SELECT data FROM festivita")).mappings().all()
        festivita_dates = {r["data"] for r in fest_rows}
    except Exception:
        pass
        
    today = date.today()
    # Trova il lunedì della settimana successiva
    # weekday(): 0=Lunedì, ..., 6=Domenica
    days_to_next_monday = 7 - today.weekday()
    next_monday = today + timedelta(days=days_to_next_monday)
    
    next_week_days = []
    for i in range(5): # Da lunedì a venerdì
        d = next_monday + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        is_holiday = d_str in festivita_dates
        next_week_days.append({
            "date": d,
            "date_str": d_str,
            "formatted": format_date_italian(d),
            "is_holiday": is_holiday
        })
    return next_week_days

def get_next_5_working_days(conn):
    """
    Ritorna la lista delle date (date_obj, date_str, formatted_str) dei prossimi 5 giorni lavorativi
    (escludendo sabato, domenica e festivita) a partire da domani.
    """
    from datetime import date, timedelta
    festivita_dates = set()
    try:
        fest_rows = conn.execute(text("SELECT data FROM festivita")).mappings().all()
        festivita_dates = {r["data"] for r in fest_rows}
    except Exception:
        pass
        
    working_days = []
    target = date.today()
    while len(working_days) < 5:
        target += timedelta(days=1)
        # 5=Sabato, 6=Domenica
        if target.weekday() >= 5:
            continue
        target_str = target.strftime("%Y-%m-%d")
        if target_str in festivita_dates:
            continue
        working_days.append({
            "date": target,
            "date_str": target_str,
            "formatted": format_date_italian(target)
        })
    return working_days

def get_date_5_working_days_ago(conn):
    """
    Ritorna la data (sotto forma di stringa YYYY-MM-DD 00:00:00) di 5 giorni lavorativi fa,
    escludendo sabati, domeniche e festivita.
    """
    from datetime import date, timedelta
    festivita_dates = set()
    try:
        fest_rows = conn.execute(text("SELECT data FROM festivita")).mappings().all()
        festivita_dates = {r["data"] for r in fest_rows}
    except Exception:
        pass
        
    target = date.today()
    working_days_count = 0
    while working_days_count < 5:
        target -= timedelta(days=1)
        # 5=Sabato, 6=Domenica
        if target.weekday() >= 5:
            continue
        target_str = target.strftime("%Y-%m-%d")
        if target_str in festivita_dates:
            continue
        working_days_count += 1
    return f"{target.strftime('%Y-%m-%d')} 00:00:00"

def query_admin_status(conn):
    """Raccoglie i dati per il report ADMIN_STATUS"""
    data = {}
    
    # 1. Conteggio record tabelle anagrafiche e principali
    tables = {
        "reparti": "Reparti (Dipartimenti)",
        "servizi": "Servizi",
        "sedi": "Sedi Fisiche",
        "comuni": "Comuni di residenza",
        "ruoli": "Ruoli utente",
        "categorie": "Categorie materiali",
        "materiali": "Materiali/Asset",
        "magazzini": "Magazzini",
        "automezzi": "Automezzi aziendali",
        "users": "Utenti Registrati",
        "tickets": "Ticket Totali"
    }
    
    table_counts = []
    for table_name, label in tables.items():
        try:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
            table_counts.append({"table": label, "count": cnt})
        except Exception as e:
            table_counts.append({"table": label, "count": f"N/D (Errore: {e})"})
    data["table_counts"] = table_counts

    # 2. Conteggio Utenti ed Operatori per ruolo e stato
    try:
        # Utenti (ruolo = 'normale')
        data["users_total"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo = 'normale'")).scalar() or 0
        data["users_active"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo = 'normale' AND attivo = 1")).scalar() or 0
        data["users_inactive"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo = 'normale' AND attivo = 0")).scalar() or 0
        
        # Operatori (ruolo != 'normale')
        data["ops_total"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo != 'normale'")).scalar() or 0
        data["ops_active"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo != 'normale' AND attivo = 1")).scalar() or 0
        data["ops_inactive"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ruolo != 'normale' AND attivo = 0")).scalar() or 0
    except Exception as e:
        print(f"[ERRORE] Conteggi utenti/operatori falliti: {e}")
        data["users_total"] = data["users_active"] = data["users_inactive"] = "N/D"
        data["ops_total"] = data["ops_active"] = data["ops_inactive"] = "N/D"

    # 3. Statistiche Accessi
    now = datetime.now()
    time_24h = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    time_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    time_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        data["logins_never"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ultimo_accesso IS NULL")).scalar() or 0
        data["logins_24h"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ultimo_accesso >= :t"), {"t": time_24h}).scalar() or 0
        data["logins_7d"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ultimo_accesso >= :t"), {"t": time_7d}).scalar() or 0
        data["logins_30d"] = conn.execute(text("SELECT COUNT(*) FROM users WHERE ultimo_accesso >= :t"), {"t": time_30d}).scalar() or 0
    except Exception as e:
        print(f"[ERRORE] Statistiche accessi fallite: {e}")
        data["logins_never"] = data["logins_24h"] = data["logins_7d"] = data["logins_30d"] = "N/D"

    # 4. Ultimi 10 accessi andati a buon fine
    try:
        logins_rows = conn.execute(text("""
            SELECT username, nome, cognome, ruolo, ultimo_accesso, ultimo_ip 
            FROM users 
            WHERE ultimo_accesso IS NOT NULL 
            ORDER BY ultimo_accesso DESC 
            LIMIT 10
        """)).mappings().all()
        data["recent_logins"] = [dict(r) for r in logins_rows]
    except Exception as e:
        print(f"[ERRORE] Recupero recenti login fallito: {e}")
        data["recent_logins"] = []

    # 5. Ultimi 10 accessi falliti (da log file)
    failed_logins = []
    log_file = os.path.join(BASE_DIR, "failed_logins.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[-10:]:
                if line.strip():
                    failed_logins.append(line.strip())
            # Inverti l'ordine per mostrare i più recenti in alto
            failed_logins.reverse()
        except Exception as e:
            failed_logins.append(f"Errore lettura log accessi falliti: {e}")
    else:
        failed_logins.append("Nessun tentativo di accesso fallito registrato.")
    data["failed_logins"] = failed_logins

    return data

def query_resp_status_for_reparto(conn, reparto_id, reparto_nome):
    """Raccoglie i dati per il report RESP_STATUS limitatamente ad un singolo reparto"""
    data = {
        "reparto_id": reparto_id,
        "reparto_nome": reparto_nome
    }
    
    # Rileva il dialect del database per compatibilità SQLite / MySQL / MariaDB
    is_sqlite = engine.dialect.name == 'sqlite'
    if is_sqlite:
        date_filter = "date(creato_il, 'localtime') = date('now', 'localtime')"
        note_date_filter = "date(tn.creato_il, 'localtime') = date('now', 'localtime')"
    else:
        date_filter = "DATE(creato_il) = CURDATE()"
        note_date_filter = "DATE(tn.creato_il) = CURDATE()"

    # 1. Ticket aperti oggi, chiusi oggi, aperti negli ultimi 5 gg lavorativi, da prendere, in lavorazione (solo per questo reparto)
    try:
        # Recupera la lista dei servizi di questo reparto
        servizi_rows = conn.execute(text("""
            SELECT servizio_id, descrizione 
            FROM servizi 
            WHERE reparto_id = :rep_id 
            ORDER BY descrizione
        """), {"rep_id": reparto_id}).mappings().all()
        
        services = {r["servizio_id"]: {
            "nome": r["descrizione"], 
            "aperti_oggi": 0, 
            "aperti_5gg": 0,
            "da_prendere": 0,
            "in_lavorazione": 0,
            "chiusi_oggi": 0
        } for r in servizi_rows}
        
        # Biglietti aperti oggi (creati oggi)
        aperti_oggi_rows = conn.execute(text(f"""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE {date_filter} AND reparto_id = :rep_id
            GROUP BY servizio_id
        """), {"rep_id": reparto_id}).mappings().all()
        for r in aperti_oggi_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["aperti_oggi"] = r["count"]
                
        # Biglietti aperti negli ultimi 5 giorni lavorativi
        five_days_ago_str = get_date_5_working_days_ago(conn)
        aperti_5gg_rows = conn.execute(text("""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE creato_il >= :five_days_ago AND reparto_id = :rep_id
            GROUP BY servizio_id
        """), {"rep_id": reparto_id, "five_days_ago": five_days_ago_str}).mappings().all()
        for r in aperti_5gg_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["aperti_5gg"] = r["count"]

        # Biglietti in attesa di essere presi in carico (stato = 'nuova')
        da_prendere_rows = conn.execute(text("""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE stato = 'nuova' AND reparto_id = :rep_id
            GROUP BY servizio_id
        """), {"rep_id": reparto_id}).mappings().all()
        for r in da_prendere_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["da_prendere"] = r["count"]

        # Biglietti in lavorazione (stato = 'presa_in_carico')
        in_lavorazione_rows = conn.execute(text("""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE stato = 'presa_in_carico' AND reparto_id = :rep_id
            GROUP BY servizio_id
        """), {"rep_id": reparto_id}).mappings().all()
        for r in in_lavorazione_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["in_lavorazione"] = r["count"]

        # Biglietti chiusi oggi (hanno nota di chiusura oggi)
        chiusi_oggi_rows = conn.execute(text(f"""
            SELECT t.servizio_id, COUNT(DISTINCT t.ticket_id) as count
            FROM tickets t
            JOIN ticket_notes tn ON t.ticket_id = tn.ticket_id
            WHERE t.stato = 'chiusa'
              AND tn.testo LIKE 'Stato modificato in: %Chiusa%.'
              AND {note_date_filter}
              AND t.reparto_id = :rep_id
            GROUP BY t.servizio_id
        """), {"rep_id": reparto_id}).mappings().all()
        for r in chiusi_oggi_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["chiusi_oggi"] = r["count"]

        # Trasforma in lista
        servizi_stats = []
        for sid, sinfo in services.items():
            if (sinfo["aperti_oggi"] > 0 or sinfo["chiusi_oggi"] > 0 or 
                sinfo["aperti_5gg"] > 0 or sinfo["da_prendere"] > 0 or sinfo["in_lavorazione"] > 0):
                servizi_stats.append({
                    "id": sid,
                    "nome": sinfo["nome"],
                    "aperti_oggi": sinfo["aperti_oggi"],
                    "aperti_5gg": sinfo["aperti_5gg"],
                    "da_prendere": sinfo["da_prendere"],
                    "in_lavorazione": sinfo["in_lavorazione"],
                    "chiusi_oggi": sinfo["chiusi_oggi"]
                })
        
        # Ordina per "da prendere in carico" desc, poi "in lavorazione" desc
        servizi_stats.sort(key=lambda x: (x["da_prendere"], x["in_lavorazione"]), reverse=True)
        data["servizi_stats"] = servizi_stats
        
    except Exception as e:
        print(f"[ERRORE] Recupero statistiche ticket per reparto {reparto_nome} fallito: {e}")
        data["servizi_stats"] = []

    # Carica tutti gli operatori attivi di questo reparto ed i servizi associati
    try:
        ops_rows = conn.execute(text("""
            SELECT user_id, username, nome, cognome, ruolo, email, reparto_id
            FROM users 
            WHERE ruolo != 'normale' AND attivo = 1 AND user_id != 1 AND reparto_id = :rep_id
        """), {"rep_id": reparto_id}).mappings().all()
        operators = {r["user_id"]: dict(r) for r in ops_rows}

        service_ops_rows = conn.execute(text("""
            SELECT s.servizio_id, s.descrizione as servizio_desc, 
                   r.nome as reparto_nome,
                   os.user_id
            FROM servizi s
            JOIN reparti r ON s.reparto_id = r.reparto_id
            LEFT JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
            WHERE s.reparto_id = :rep_id
        """), {"rep_id": reparto_id}).mappings().all()
        
        # Mappa dei servizi con i loro operatori attivi assegnati
        services_ops_map = {}
        for row in service_ops_rows:
            sid = row["servizio_id"]
            uid = row["user_id"]
            if sid not in services_ops_map:
                services_ops_map[sid] = {
                    "id": sid,
                    "descrizione": row["servizio_desc"],
                    "reparto": row["reparto_nome"],
                    "ops_uids": set()
                }
            if uid in operators:
                services_ops_map[sid]["ops_uids"].add(uid)
                
        # Estrai i servizi non assegnati ad alcun operatore attivo
        non_assegnati = []
        active_services_ops_map = {}
        for sid, sinfo in services_ops_map.items():
            if len(sinfo["ops_uids"]) == 0:
                non_assegnati.append(sinfo)
            else:
                active_services_ops_map[sid] = sinfo
                
        data["non_assegnati"] = non_assegnati
    except Exception as e:
        print(f"[ERRORE] Caricamento operatori/servizi fallito: {e}")
        operators = {}
        active_services_ops_map = {}
        data["non_assegnati"] = []

    # Funzione interna helper per calcolare assenti e scoperture in una data
    def get_absents_and_gaps(target_date_str):
        try:
            if not operators:
                return [], []
                
            assenze_rows = conn.execute(text("""
                SELECT user_id, motivo FROM assenze 
                WHERE data_inizio <= :target AND data_fine >= :target
            """), {"target": target_date_str}).mappings().all()
            
            absent_uids = {a["user_id"]: (a["motivo"] or "Assenza non specificata") 
                           for a in assenze_rows if a["user_id"] in operators}
            
            # 1. Operatori assenti
            absent_ops = []
            for uid, op in operators.items():
                if uid in absent_uids:
                    op_copy = op.copy()
                    op_copy["motivo"] = absent_uids[uid]
                    absent_ops.append(op_copy)
            
            # 2. Scoperture servizi
            gaps = []
            for sid, sinfo in active_services_ops_map.items():
                present_cnt = len(sinfo["ops_uids"] - set(absent_uids.keys()))
                if present_cnt == 0 and len(sinfo["ops_uids"]) > 0:
                    assenti_nomi = []
                    for uid in sinfo["ops_uids"]:
                        op_info = operators[uid]
                        assenti_nomi.append(f"{op_info['nome']} {op_info['cognome']}".strip())
                    gaps.append({
                        "id": sid,
                        "descrizione": sinfo["descrizione"],
                        "reparto": sinfo["reparto"],
                        "assenti_nomi": assenti_nomi
                    })
            return absent_ops, gaps
        except Exception as ex:
            print(f"[WARN] Impossibile calcolare copertura per {target_date_str}: {ex}")
            return [], []

    def get_attendance_modalities(target_date_str):
        try:
            if not operators:
                return []
            pres_rows = conn.execute(text("""
                SELECT user_id, tipo, nota FROM presenze
                WHERE data_inizio <= :target AND data_fine >= :target
            """), {"target": target_date_str}).mappings().all()
            
            modalita_list = []
            for r in pres_rows:
                uid = r["user_id"]
                if uid in operators:
                    op = operators[uid]
                    modalita_list.append({
                        "nome": op["nome"],
                        "cognome": op["cognome"],
                        "ruolo": op["ruolo"],
                        "tipo": r["tipo"],
                        "nota": r["nota"] or ""
                    })
            return modalita_list
        except Exception as ex:
            print(f"[WARN] Impossibile recuperare modalità di presenza per {target_date_str}: {ex}")
            return []

    # 2. Giornata in corso (Oggi)
    today_str = datetime.today().strftime("%Y-%m-%d")
    data["today_formatted"] = format_date_italian(datetime.today())
    today_absents, _ = get_absents_and_gaps(today_str)
    data["today_assenti"] = today_absents
    data["today_presenze_mod"] = get_attendance_modalities(today_str)

    # 3. Giornata lavorativa successiva (Domani)
    next_day, next_day_str = get_next_working_day(conn)
    data["next_working_day_formatted"] = format_date_italian(next_day)
    tomorrow_absents, tomorrow_gaps = get_absents_and_gaps(next_day_str)
    data["tomorrow_assenti"] = tomorrow_absents
    data["tomorrow_scoperti"] = tomorrow_gaps
    data["tomorrow_presenze_mod"] = get_attendance_modalities(next_day_str)

    # 4. Situazione settimana successiva
    try:
        next_week_days = get_next_week_working_days(conn)
        next_week_summary = []
        for day in next_week_days:
            if day["is_holiday"]:
                next_week_summary.append({
                    "formatted_date": day["formatted"],
                    "is_holiday": True,
                    "scoperti": []
                })
            else:
                _, day_gaps = get_absents_and_gaps(day["date_str"])
                next_week_summary.append({
                    "formatted_date": day["formatted"],
                    "is_holiday": False,
                    "scoperti": day_gaps
                })
        data["next_week_summary"] = next_week_summary
    except Exception as e:
        print(f"[ERRORE] Analisi settimana successiva fallita: {e}")
        data["next_week_summary"] = []

    return data

def build_html_admin_status(data):
    """Costruisce il corpo HTML premium per ADMIN_STATUS"""
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # Costruisci righe conteggio tabelle
    table_rows_html = ""
    for item in data["table_counts"]:
        table_rows_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155;">{item['table']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #1e293b; text-align: right;">{item['count']}</td>
        </tr>
        """
        
    # Costruisci righe ultimi 10 accessi riusciti
    login_rows_html = ""
    if data["recent_logins"]:
        for r in data["recent_logins"]:
            ruolo_badge = f"<span class='badge badge-neutral'>{r['ruolo']}</span>"
            if r['ruolo'] == 'admin':
                ruolo_badge = "<span class='badge badge-danger'>admin</span>"
            elif r['ruolo'] == 'responsabile':
                ruolo_badge = "<span class='badge badge-warning'>responsabile</span>"
            elif r['ruolo'] == 'assistenza':
                ruolo_badge = "<span class='badge badge-primary'>assistenza</span>"
                
            login_rows_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155;">
                    <strong>{r.get('nome', '')} {r.get('cognome', '')}</strong><br>
                    <span style="font-size: 11px; color: #64748b;">@{r['username']}</span>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">{ruolo_badge}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155; font-family: monospace;">{r['ultimo_ip']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155; text-align: right;">{r['ultimo_accesso']}</td>
            </tr>
            """
    else:
        login_rows_html = "<tr><td colspan='4' style='padding: 15px; text-align: center; color: #64748b;'>Nessun accesso registrato.</td></tr>"

    # Costruisci righe accessi falliti
    failed_rows_html = ""
    for entry in data["failed_logins"]:
        is_warning = "Tentativo fallito" in entry or "IP:" in entry
        style_color = "color: #991b1b; background-color: #fee2e2;" if is_warning else "color: #475569;"
        failed_rows_html += f"""
        <div style="padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border-left: 3px solid #ef4444; font-family: monospace; font-size: 12px; {style_color}">
            {entry}
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .badge {{
                display: inline-block;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 12px;
                text-transform: uppercase;
            }}
            .badge-neutral {{ background-color: #e2e8f0; color: #334155; }}
            .badge-success {{ background-color: #d1fae5; color: #065f46; }}
            .badge-warning {{ background-color: #fef3c7; color: #92400e; }}
            .badge-danger {{ background-color: #fee2e2; color: #991b1b; }}
            .badge-primary {{ background-color: #dbeafe; color: #1e40af; }}
        </style>
    </head>
    <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; -webkit-font-smoothing: antialiased;">
        <div style="max-width: 700px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 30px; text-align: center; color: #ffffff;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    ⚙️ Troubletick Admin Status
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 14px; color: #94a3b8;">Riepilogo dello stato del sistema ed accessi al {now_str}</p>
            </div>
            
            <div style="padding: 25px;">
                <!-- Grid Statistiche Rapide -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    👥 Statistiche Utenti & Operatori
                </h2>
                <div style="display: table; width: 100%; margin-bottom: 25px; border-spacing: 10px; margin-left: -10px; margin-right: -10px;">
                    <!-- Utenti Normali -->
                    <div style="display: table-cell; width: 50%; background: #f1f5f9; padding: 15px; border-radius: 10px; vertical-align: top; border: 1px solid #e2e8f0;">
                        <h3 style="margin: 0 0 10px 0; font-size: 14px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.05em;">
                            Utenti (Richiedenti)
                        </h3>
                        <p style="margin: 0 0 5px 0; font-size: 20px; font-weight: bold; color: #1e293b;">{data['users_total']} <span style="font-size: 12px; font-weight: normal; color: #64748b;">totali</span></p>
                        <div style="font-size: 12px; color: #475569;">
                            <span style="display: inline-block; margin-right: 10px;"><span style="color: #10b981;">●</span> {data['users_active']} Attivi</span>
                            <span><span style="color: #ef4444;">●</span> {data['users_inactive']} In attesa</span>
                        </div>
                    </div>
                    <!-- Operatori -->
                    <div style="display: table-cell; width: 50%; background: #f1f5f9; padding: 15px; border-radius: 10px; vertical-align: top; border: 1px solid #e2e8f0;">
                        <h3 style="margin: 0 0 10px 0; font-size: 14px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.05em;">
                            Operatori & Staff
                        </h3>
                        <p style="margin: 0 0 5px 0; font-size: 20px; font-weight: bold; color: #1e293b;">{data['ops_total']} <span style="font-size: 12px; font-weight: normal; color: #64748b;">totali</span></p>
                        <div style="font-size: 12px; color: #475569;">
                            <span style="display: inline-block; margin-right: 10px;"><span style="color: #10b981;">●</span> {data['ops_active']} Attivi</span>
                            <span><span style="color: #ef4444;">●</span> {data['ops_inactive']} In attesa</span>
                        </div>
                    </div>
                </div>

                <!-- Grid Frequenza Accesso -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🔑 Frequenza Login (Utenti Unici)
                </h2>
                <div style="display: table; width: 100%; margin-bottom: 25px; border-spacing: 8px; margin-left: -8px; margin-right: -8px; text-align: center;">
                    <div style="display: table-cell; width: 25%; background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 18px; font-weight: bold; color: #2563eb;">{data['logins_24h']}</div>
                        <div style="font-size: 11px; color: #64748b;">Ultime 24 Ore</div>
                    </div>
                    <div style="display: table-cell; width: 25%; background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 18px; font-weight: bold; color: #4f46e5;">{data['logins_7d']}</div>
                        <div style="font-size: 11px; color: #64748b;">Ultimi 7 Giorni</div>
                    </div>
                    <div style="display: table-cell; width: 25%; background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{data['logins_30d']}</div>
                        <div style="font-size: 11px; color: #64748b;">Ultimi 30 Giorni</div>
                    </div>
                    <div style="display: table-cell; width: 25%; background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 18px; font-weight: bold; color: #64748b;">{data['logins_never']}</div>
                        <div style="font-size: 11px; color: #64748b;">Mai Effettuato</div>
                    </div>
                </div>

                <!-- Stato Database Anagrafiche -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 25px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    📊 Dimensione Tabelle Anagrafiche e Record
                </h2>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Tabella / Anagrafica</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Numero di Record</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>

                <!-- Ultimi 10 Login Riusciti -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 25px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    ✅ Ultimi 10 Accessi Riusciti nel Sistema
                </h2>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Operatore/Utente</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Ruolo</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">IP Address</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Data e Ora</th>
                        </tr>
                    </thead>
                    <tbody>
                        {login_rows_html}
                    </tbody>
                </table>

                <!-- Ultimi 10 Login Falliti -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 25px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🚨 Ultimi Tentativi di Accesso Falliti (Log)
                </h2>
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 10px; max-height: 250px; overflow-y: auto;">
                    {failed_rows_html}
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                {CFG.get('company_name', 'Troubletick Helpdesk')} — Generato automaticamente tramite cron.
            </div>
        </div>
    </body>
    </html>
    """
    return html

def build_html_resp_status(data):
    """Costruisce il corpo HTML premium per RESP_STATUS"""
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # 1. Tabella Servizi (Aperti 5gg, Da Prendere, In Lavorazione, Chiusi Oggi)
    servizi_rows_html = ""
    if data["servizi_stats"]:
        for s in data["servizi_stats"]:
            bg_style = ""
            badge_da_prendere = f"<span class='badge badge-neutral'>{s['da_prendere']}</span>"
            if s['da_prendere'] > 5:
                bg_style = "background-color: #fffbeb;"
                badge_da_prendere = f"<span class='badge badge-danger'>{s['da_prendere']} da prendere</span>"
            elif s['da_prendere'] > 0:
                badge_da_prendere = f"<span class='badge badge-warning'>{s['da_prendere']} da prendere</span>"
            else:
                badge_da_prendere = "<span class='badge badge-success'>0</span>"

            badge_in_lavorazione = f"<span class='badge badge-primary'>{s['in_lavorazione']}</span>" if s['in_lavorazione'] > 0 else "<span class='badge badge-neutral'>0</span>"

            servizi_rows_html += f"""
            <tr style="{bg_style}">
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #334155;">{s['nome']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #1e40af; font-weight: bold;">{s['aperti_5gg']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">{badge_da_prendere}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">{badge_in_lavorazione}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #065f46; font-weight: bold;">✓ {s['chiusi_oggi']}</td>
            </tr>
            """
    else:
        servizi_rows_html = "<tr><td colspan='5' style='padding: 15px; text-align: center; color: #64748b;'>Nessun movimento ticket registrato di recente.</td></tr>"

    # 2. Operatori Assenti Oggi
    today_assenti_html = ""
    if data["today_assenti"]:
        for op in data["today_assenti"]:
            ruolo_lbl = op['ruolo'].upper()
            today_assenti_html += f"""
            <div style="padding: 10px; background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; margin-bottom: 8px; display: inline-block; width: 45%; margin-right: 10px; vertical-align: top; box-sizing: border-box;">
                <strong style="color: #991b1b; font-size: 13px;">{op['nome']} {op['cognome']}</strong> 
                <span style="font-size: 10px; color: #b91c1c; background: #fee2e2; padding: 1px 5px; border-radius: 4px; font-weight: bold;">{ruolo_lbl}</span><br>
                <span style="font-size: 11px; color: #7f1d1d; display: inline-block; margin-top: 4px;">ℹ️ Assenza: <em>{op['motivo']}</em></span>
            </div>
            """
    else:
        today_assenti_html = "<div style='padding: 10px; background-color: #f0fdf4; border: 1px solid #bcf0da; border-radius: 8px; color: #166534; font-size: 13px;'>✓ Tutti gli operatori sono presenti oggi.</div>"

    # 2b. Modalità Presenza Oggi
    today_presenze_mod_html = ""
    if data["today_presenze_mod"]:
        for op in data["today_presenze_mod"]:
            ruolo_lbl = op['ruolo'].upper()
            nota_lbl = f" ({op['nota']})" if op['nota'] else ""
            today_presenze_mod_html += f"""
            <div style="padding: 10px; background-color: #f0fdf4; border: 1px solid #bcf0da; border-radius: 8px; margin-bottom: 8px; display: inline-block; width: 45%; margin-right: 10px; vertical-align: top; box-sizing: border-box;">
                <strong style="color: #166534; font-size: 13px;">{op['nome']} {op['cognome']}</strong> 
                <span style="font-size: 10px; color: #166534; background: #d1fae5; padding: 1px 5px; border-radius: 4px; font-weight: bold;">{ruolo_lbl}</span><br>
                <span style="font-size: 11px; color: #14532d; display: inline-block; margin-top: 4px;">📍 Presenza: <strong>{op['tipo']}</strong>{nota_lbl}</span>
            </div>
            """
    else:
        today_presenze_mod_html = "<p style='color: #64748b; font-size: 13px; margin: 0;'>Nessuna modalità di presenza specifica registrata oggi.</p>"

    # 3. Operatori Assenti Domani (Giorno dopo)
    tomorrow_assenti_html = ""
    if data["tomorrow_assenti"]:
        for op in data["tomorrow_assenti"]:
            ruolo_lbl = op['ruolo'].upper()
            tomorrow_assenti_html += f"""
            <div style="padding: 10px; background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; margin-bottom: 8px; display: inline-block; width: 45%; margin-right: 10px; vertical-align: top; box-sizing: border-box;">
                <strong style="color: #991b1b; font-size: 13px;">{op['nome']} {op['cognome']}</strong> 
                <span style="font-size: 10px; color: #b91c1c; background: #fee2e2; padding: 1px 5px; border-radius: 4px; font-weight: bold;">{ruolo_lbl}</span><br>
                <span style="font-size: 11px; color: #7f1d1d; display: inline-block; margin-top: 4px;">ℹ️ Assenza: <em>{op['motivo']}</em></span>
            </div>
            """
    else:
        tomorrow_assenti_html = "<div style='padding: 10px; background-color: #f0fdf4; border: 1px solid #bcf0da; border-radius: 8px; color: #166534; font-size: 13px;'>✓ Nessun operatore assente domani.</div>"

    # 3b. Modalità Presenza Domani
    tomorrow_presenze_mod_html = ""
    if data["tomorrow_presenze_mod"]:
        for op in data["tomorrow_presenze_mod"]:
            ruolo_lbl = op['ruolo'].upper()
            nota_lbl = f" ({op['nota']})" if op['nota'] else ""
            tomorrow_presenze_mod_html += f"""
            <div style="padding: 10px; background-color: #f0fdf4; border: 1px solid #bcf0da; border-radius: 8px; margin-bottom: 8px; display: inline-block; width: 45%; margin-right: 10px; vertical-align: top; box-sizing: border-box;">
                <strong style="color: #166534; font-size: 13px;">{op['nome']} {op['cognome']}</strong> 
                <span style="font-size: 10px; color: #166534; background: #d1fae5; padding: 1px 5px; border-radius: 4px; font-weight: bold;">{ruolo_lbl}</span><br>
                <span style="font-size: 11px; color: #14532d; display: inline-block; margin-top: 4px;">📍 Presenza: <strong>{op['tipo']}</strong>{nota_lbl}</span>
            </div>
            """
    else:
        tomorrow_presenze_mod_html = "<p style='color: #64748b; font-size: 13px; margin: 0;'>Nessuna modalità di presenza specifica registrata per domani.</p>"

    # 4. Scoperture Domani
    tomorrow_scoperti_html = ""
    if data["tomorrow_scoperti"]:
        for cov in data["tomorrow_scoperti"]:
            assenti_list = ", ".join(cov["assenti_nomi"]) if cov["assenti_nomi"] else "Nessuno"
            tomorrow_scoperti_html += f"""
            <div style="padding: 12px; background-color: #fff5f5; border-left: 4px solid #ef4444; border-radius: 6px; margin-bottom: 10px; border: 1px solid #fee2e2; border-left-width: 4px;">
                <strong style="color: #c53030; font-size: 14px;">{cov['descrizione']}</strong> <span style="font-size: 11px; color: #4a5568;">({cov['reparto']})</span><br>
                <span style="font-size: 12px; color: #9b2c2c; font-weight: bold;">STATO: SCOPERTO (0 Operatori Presenti)</span><br>
                <span style="font-size: 12px; color: #4a5568;">Operatori Assegnati Assenti: {assenti_list}</span>
            </div>
            """
    else:
        tomorrow_scoperti_html = "<div style='padding: 12px; background-color: #f0fdf4; border-left: 4px solid #10b981; border-radius: 6px; color: #166534; font-weight: bold;'>✓ Ottimo! Nessun servizio con operatori assegnati risulta scoperto domani.</div>"

    # 5. Riassunto Settimana Successiva
    week_rows_html = ""
    if data["next_week_summary"]:
        for day in data["next_week_summary"]:
            if day["is_holiday"]:
                status_html = "<span class='badge badge-neutral' style='background: #fee2e2; color: #991b1b;'>FESTIVITÀ (LAVORO SOSPESO)</span>"
            elif day["scoperti"]:
                service_names = [f"<strong>{s['descrizione']}</strong> ({s['reparto']})" for s in day["scoperti"]]
                status_html = f"""
                <span class='badge badge-danger' style='margin-bottom: 4px;'>⚠️ {len(day['scoperti'])} SCOPERTURE</span><br>
                <span style='font-size: 12px; color: #7f1d1d;'>Servizi scoperti: {', '.join(service_names)}</span>
                """
            else:
                status_html = "<span class='badge badge-success'>🟢 COPERTO</span>"
                
            week_rows_html += f"""
            <tr>
                <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; color: #1e293b; font-weight: bold; width: 35%;">{day['formatted_date']}</td>
                <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: middle;">{status_html}</td>
            </tr>
            """
    else:
        week_rows_html = "<tr><td colspan='2' style='padding: 15px; text-align: center; color: #64748b;'>Dati non disponibili per la settimana successiva.</td></tr>"

    # 6. Servizi Senza Operatori Assegnati
    non_assegnati_html = ""
    if data["non_assegnati"]:
        non_assegnati_html += "<ul style='margin: 0; padding-left: 20px; font-size: 13px; color: #7f5f07;'>"
        for cov in data["non_assegnati"]:
            non_assegnati_html += f"<li style='margin-bottom: 4px;'><strong>{cov['descrizione']}</strong> <span style='font-size: 11px; color: #6b7280;'>({cov['reparto']})</span></li>"
        non_assegnati_html += "</ul>"
    else:
        non_assegnati_html = "<p style='color: #64748b; font-size: 13px; margin: 0;'>Tutti i servizi hanno almeno un operatore associato.</p>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .badge {{
                display: inline-block;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 12px;
                text-transform: uppercase;
            }}
            .badge-neutral {{ background-color: #e2e8f0; color: #334155; }}
            .badge-success {{ background-color: #d1fae5; color: #065f46; }}
            .badge-warning {{ background-color: #fef3c7; color: #92400e; }}
            .badge-danger {{ background-color: #fee2e2; color: #991b1b; }}
            .badge-primary {{ background-color: #dbeafe; color: #1e40af; }}
        </style>
    </head>
    <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; -webkit-font-smoothing: antialiased;">
        <div style="max-width: 700px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%); padding: 30px; text-align: center; color: #ffffff;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    📋 Report Attività & Pianificazione Servizi
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 14px; color: #c7d2fe;">Reparto: <strong>{data.get('reparto_nome', 'N/D')}</strong> — Statistiche ticket, presenze ed anomalie di copertura</p>
            </div>
            
            <div style="padding: 25px;">
                <!-- SEZIONE 1: Ticket giornata in corso -->
                <h2 style="font-size: 16px; font-weight: 700; color: #4f46e5; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    📅 Attività Ticket Odierna (Giornata in Corso)
                </h2>
                <p style="font-size: 13px; color: #64748b; margin-top: 0; margin-bottom: 12px;">
                    Riepilogo dei ticket per servizio, ordinati per priorità di gestione (servizi con più ticket da prendere in carico in alto):
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Servizio</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Aperti (5gg lav.)</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Da Prendere</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">In Lavorazione</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Chiusi Oggi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {servizi_rows_html}
                    </tbody>
                </table>

                <!-- SEZIONE 2: Assenze Giornata in Corso (Oggi) -->
                <h2 style="font-size: 16px; font-weight: 700; color: #4f46e5; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🔴 Operatori Assenti Oggi: <span style="font-weight: normal; font-size: 14px; color: #4b5563;">{data['today_formatted']}</span>
                </h2>
                <div style="margin-bottom: 30px;">
                    {today_assenti_html}
                </div>

                <!-- SEZIONE 2b: Modalità Presenza Oggi -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f766e; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🗓️ Modalità di Presenza Oggi: <span style="font-weight: normal; font-size: 14px; color: #4b5563;">{data['today_formatted']}</span>
                </h2>
                <div style="margin-bottom: 30px;">
                    {today_presenze_mod_html}
                </div>

                <!-- SEZIONE 3: Assenze Giornata Lavorativa Successiva (Domani) -->
                <h2 style="font-size: 16px; font-weight: 700; color: #4f46e5; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🔴 Operatori Assenti Domani: <span style="font-weight: normal; font-size: 14px; color: #4b5563;">{data['next_working_day_formatted']}</span>
                </h2>
                <div style="margin-bottom: 30px;">
                    {tomorrow_assenti_html}
                </div>

                <!-- SEZIONE 3b: Modalità Presenza Domani -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0f766e; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🗓️ Modalità di Presenza Domani: <span style="font-weight: normal; font-size: 14px; color: #4b5563;">{data['next_working_day_formatted']}</span>
                </h2>
                <div style="margin-bottom: 30px;">
                    {tomorrow_presenze_mod_html}
                </div>

                <!-- SEZIONE 4: Scoperture di Domani -->
                <h2 style="font-size: 16px; font-weight: 700; color: #b91c1c; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🚨 Scoperture Servizi Domani ({data['next_working_day_formatted']})
                </h2>
                <div style="margin-bottom: 30px;">
                    {tomorrow_scoperti_html}
                </div>

                <!-- SEZIONE 5: Riassunto Settimana Successiva -->
                <h2 style="font-size: 16px; font-weight: 700; color: #4f46e5; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🗓️ Riassunto Copertura Settimana Successiva (Previsione)
                </h2>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Giorno</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Stato Copertura</th>
                        </tr>
                    </thead>
                    <tbody>
                        {week_rows_html}
                    </tbody>
                </table>

                <!-- SEZIONE 6: Servizi non assegnati (Anomalia Configurazione) -->
                <div style="background-color: #fffbeb; border: 1px solid #fef3c7; padding: 15px; border-radius: 8px; margin-bottom: 10px;">
                    <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 13px; font-weight: bold; color: #7f5f07; text-transform: uppercase;">
                        ⚠️ Servizi senza operatori associati (Anomalia Configurazione)
                    </h3>
                    {non_assegnati_html}
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                {CFG.get('company_name', 'Troubletick Helpdesk')} — Generato automaticamente tramite cron.
            </div>
        </div>
    </body>
    </html>
    """
    return html

def query_ope_status(conn, op_id, op_nome, op_cognome, reparto_id, reparto_nome):
    """Raccoglie i dati per il report OPE_STATUS di un singolo operatore"""
    data = {
        "op_id": op_id,
        "op_nome": op_nome,
        "op_cognome": op_cognome,
        "reparto_id": reparto_id,
        "reparto_nome": reparto_nome
    }
    
    # 1. Riepilogo ticket del proprio reparto (riutilizziamo la logica di query_resp_status_for_reparto)
    rep_data = query_resp_status_for_reparto(conn, reparto_id, reparto_nome)
    data["servizi_stats"] = rep_data["servizi_stats"]
    data["non_assegnati"] = rep_data["non_assegnati"]
    
    # 2. Servizi assegnati a questo operatore
    assigned_services = conn.execute(text("""
        SELECT s.servizio_id, s.descrizione 
        FROM operatori_servizi os 
        JOIN servizi s ON os.servizio_id = s.servizio_id 
        WHERE os.user_id = :uid
    """), {"uid": op_id}).mappings().all()
    
    # Mappa degli operatori assegnati a ciascuno di questi servizi
    services_ops = {}
    for s in assigned_services:
        sid = s["servizio_id"]
        ops_rows = conn.execute(text("""
            SELECT os.user_id 
            FROM operatori_servizi os 
            JOIN users u ON os.user_id = u.user_id 
            WHERE os.servizio_id = :sid AND u.attivo = 1
        """), {"sid": sid}).mappings().all()
        services_ops[sid] = {
            "descrizione": s["descrizione"],
            "uids": {r["user_id"] for r in ops_rows}
        }
        
    # 3. Calcolo situazione per i prossimi 5 giorni lavorativi
    next_5_days = get_next_5_working_days(conn)
    schedule = []
    
    # Carica tutti gli operatori attivi del reparto per poter verificare i dettagli nomi se serve
    ops_rows = conn.execute(text("""
        SELECT user_id, username, nome, cognome 
        FROM users 
        WHERE ruolo != 'normale' AND attivo = 1 AND user_id != 1 AND reparto_id = :rep_id
    """), {"rep_id": reparto_id}).mappings().all()
    operators = {r["user_id"]: dict(r) for r in ops_rows}
    
    for day in next_5_days:
        date_str = day["date_str"]
        
        # a. Stato di questo operatore (Assenza)
        absent_row = conn.execute(text("""
            SELECT motivo FROM assenze 
            WHERE user_id = :uid AND data_inizio <= :target AND data_fine >= :target
        """), {"uid": op_id, "target": date_str}).mappings().all()
        
        # b. Stato di questo operatore (Presenza)
        pres_row = conn.execute(text("""
            SELECT tipo, nota FROM presenze 
            WHERE user_id = :uid AND data_inizio <= :target AND data_fine >= :target
        """), {"uid": op_id, "target": date_str}).mappings().all()
        
        if absent_row:
            op_status = f"Assente ({absent_row[0]['motivo'] or 'Ferie/Altro'})"
            is_op_absent = True
        elif pres_row:
            op_status = f"Presente ({pres_row[0]['tipo']}{' - ' + pres_row[0]['nota'] if pres_row[0]['nota'] else ''})"
            is_op_absent = False
        else:
            op_status = "Presente (Standard)"
            is_op_absent = False
            
        # c. Scoperture nei servizi a cui è assegnato
        # Troviamo tutti gli operatori assenti in questa data per controllare la copertura
        assenze_rows = conn.execute(text("""
            SELECT user_id FROM assenze 
            WHERE data_inizio <= :target AND data_fine >= :target
        """), {"target": date_str}).mappings().all()
        day_absents = {a["user_id"] for a in assenze_rows}
        
        scoperti = []
        for sid, sinfo in services_ops.items():
            presenti_cnt = len(sinfo["uids"] - day_absents)
            if presenti_cnt == 0 and len(sinfo["uids"]) > 0:
                scoperti.append(sinfo["descrizione"])
                
        schedule.append({
            "formatted_date": day["formatted"],
            "op_status": op_status,
            "is_absent": is_op_absent,
            "scoperti": scoperti
        })
        
    data["schedule"] = schedule
    return data

def build_html_ope_status(data):
    """Costruisce il corpo HTML premium per OPE_STATUS"""
    # 1. Tabella Servizi (Aperti 5gg, Da Prendere, In Lavorazione, Chiusi Oggi)
    servizi_rows_html = ""
    if data["servizi_stats"]:
        for s in data["servizi_stats"]:
            bg_style = ""
            badge_da_prendere = f"<span class='badge badge-neutral'>{s['da_prendere']}</span>"
            if s['da_prendere'] > 5:
                bg_style = "background-color: #fffbeb;"
                badge_da_prendere = f"<span class='badge badge-danger'>{s['da_prendere']} da prendere</span>"
            elif s['da_prendere'] > 0:
                badge_da_prendere = f"<span class='badge badge-warning'>{s['da_prendere']} da prendere</span>"
            else:
                badge_da_prendere = "<span class='badge badge-success'>0</span>"

            badge_in_lavorazione = f"<span class='badge badge-primary'>{s['in_lavorazione']}</span>" if s['in_lavorazione'] > 0 else "<span class='badge badge-neutral'>0</span>"

            servizi_rows_html += f"""
            <tr style="{bg_style}">
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #334155;">{s['nome']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #1e40af; font-weight: bold;">{s['aperti_5gg']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">{badge_da_prendere}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">{badge_in_lavorazione}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #065f46; font-weight: bold;">✓ {s['chiusi_oggi']}</td>
            </tr>
            """
    else:
        servizi_rows_html = "<tr><td colspan='5' style='padding: 15px; text-align: center; color: #64748b;'>Nessun movimento ticket registrato di recente.</td></tr>"

    # 2. Tabella Assenze / Presenze prossimi 5 giorni e scoperture
    schedule_rows_html = ""
    for s in data["schedule"]:
        status_color = "#0f766e" if not s["is_absent"] else "#991b1b"
        status_bg = "#f0fdf4" if not s["is_absent"] else "#fef2f2"
        status_border = "#bcf0da" if not s["is_absent"] else "#fca5a5"
        
        status_badge = f"<span style='display: inline-block; padding: 4px 8px; font-size: 11px; font-weight: bold; border-radius: 6px; background-color: {status_bg}; border: 1px solid {status_border}; color: {status_color};'>{s['op_status']}</span>"
        
        if s["scoperti"]:
            gaps_list = ", ".join([f"<strong>{srv}</strong>" for srv in s["scoperti"]])
            scoperti_badge = f"<span class='badge badge-danger' style='margin-bottom: 4px;'>🚨 SCOPERTO!</span><br><span style='font-size: 12px; color: #991b1b;'>I tuoi servizi scoperti: {gaps_list}</span>"
        else:
            scoperti_badge = "<span class='badge badge-success'>🟢 COPERTO</span>"
            
        schedule_rows_html += f"""
        <tr>
            <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; color: #1e293b; font-weight: bold; width: 30%;">{s['formatted_date']}</td>
            <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; width: 35%;">{status_badge}</td>
            <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: middle;">{scoperti_badge}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .badge {{
                display: inline-block;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 12px;
                text-transform: uppercase;
            }}
            .badge-neutral {{ background-color: #e2e8f0; color: #334155; }}
            .badge-success {{ background-color: #d1fae5; color: #065f46; }}
            .badge-warning {{ background-color: #fef3c7; color: #92400e; }}
            .badge-danger {{ background-color: #fee2e2; color: #991b1b; }}
            .badge-primary {{ background-color: #dbeafe; color: #1e40af; }}
        </style>
    </head>
    <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; -webkit-font-smoothing: antialiased;">
        <div style="max-width: 700px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); padding: 30px; text-align: center; color: #ffffff;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em;">
                    👋 Ciao {data['op_nome']}!
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 14px; color: #e0f2fe;">Riepilogo ticket del reparto <strong>{data['reparto_nome']}</strong> e tuo piano turni</p>
            </div>
            
            <div style="padding: 25px;">
                <!-- SEZIONE 1: Riepilogo ticket di reparto -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0369a1; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    📋 Stato Ticket di Reparto (Oggi)
                </h2>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Servizio</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Aperti (5gg lav.)</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Da Prendere</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">In Lavorazione</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Chiusi Oggi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {servizi_rows_html}
                    </tbody>
                </table>

                <!-- SEZIONE 2: Le mie presenze e coperture prossimi 5 giorni -->
                <h2 style="font-size: 16px; font-weight: 700; color: #0369a1; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🗓️ Tuo Turno e Stato Copertura Servizi (Prossimi 5 Giorni Lavorativi)
                </h2>
                <p style="font-size: 13px; color: #64748b; margin-top: 0; margin-bottom: 12px;">
                    Verifica il tuo stato di presenza o assenza programmata. Se i servizi a cui sei assegnato risultano scoperti (0 operatori in turno) a causa di assenze concomitanti, verranno evidenziati in rosso:
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Giorno</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Tuo Stato</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Copertura Servizi Assegnati</th>
                        </tr>
                    </thead>
                    <tbody>
                        {schedule_rows_html}
                    </tbody>
                </table>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                {CFG.get('company_name', 'Troubletick Helpdesk')} — Generato automaticamente tramite cron.
            </div>
        </div>
    </body>
    </html>
    """
    return html

def main():
    parser = argparse.ArgumentParser(description="Script di notifica programmata per l'Helpdesk Troubletick")
    parser.add_argument("type", nargs="?", choices=["ADMIN_STATUS", "RESP_STATUS", "OPE_STATUS"], help="Tipologia di email da inviare")
    parser.add_argument("--type", dest="type_flag", choices=["ADMIN_STATUS", "RESP_STATUS", "OPE_STATUS"], help="Tipologia di email da inviare (opzione)")
    parser.add_argument("--to", help="Indirizzo email di destinazione personalizzato (sovrascrive la configurazione)")
    parser.add_argument("--cc", help="Indirizzo email in CC personalizzato")
    parser.add_argument("--mail", help="Indirizzo email a cui inviare SOLO ed ESCLUSIVAMENTE la mail, disattivando altri destinatari e CC")
    
    args = parser.parse_args()
    
    # Risolvi il tipo di email (sia posizionale che flag)
    email_type = args.type or args.type_flag
    
    if not email_type:
        print("[ERRORE] Devi specificare una tipologia di mail da inviare: ADMIN_STATUS, RESP_STATUS o OPE_STATUS.")
        parser.print_help()
        sys.exit(1)
        
    print(f"[*] Avvio generazione notifica: {email_type}")

    try:
        with engine.connect() as conn:
            if email_type == "ADMIN_STATUS":
                print("[*] Esecuzione query per ADMIN_STATUS...")
                default_recipient = CFG.get("helpdesk_email", "admin@example.com")
                dest_email = args.mail or args.to or default_recipient
                cc_email = None if args.mail else args.cc
                print(f"[*] Destinatario impostato: {dest_email} (CC: {cc_email or 'Nessuno'})")
                
                data = query_admin_status(conn)
                subject = f"[{CFG.get('app_title', 'Troubletick')}] ⚙️ Stato del Sistema ed Accessi"
                body = build_html_admin_status(data)
                reason = "Report Amministrativo programmato (ADMIN_STATUS)"
                
                print("[*] Generazione email completata. Invio in corso...")
                send_email_async(
                    dest_email=dest_email,
                    subject=subject,
                    body=body,
                    reason=reason,
                    cc_email=cc_email
                )
                print("[+] Inviata con successo!")
                
            elif email_type == "RESP_STATUS":
                print("[*] Esecuzione query per RESP_STATUS per ciascun reparto...")
                
                # Recupera solo i reparti che offrono assistenza (hanno almeno un servizio che accetta ticket)
                reparti_rows = conn.execute(text("""
                    SELECT DISTINCT r.reparto_id, r.nome 
                    FROM reparti r 
                    JOIN servizi s ON r.reparto_id = s.reparto_id 
                    WHERE s.accetta_ticket = 1 
                    ORDER BY r.nome
                """)).mappings().all()
                
                if not reparti_rows:
                    print("[*] Nessun reparto configurato nel sistema.")
                    sys.exit(0)
                    
                cc_email = None if args.mail else args.cc
                
                for rep in reparti_rows:
                    rep_id = rep["reparto_id"]
                    rep_nome = rep["nome"]
                    
                    # Determina destinatari
                    if args.mail or args.to:
                        dest_emails = [args.mail or args.to]
                    else:
                        resp_rows = conn.execute(text("""
                            SELECT email FROM users 
                            WHERE ruolo = 'responsabile' AND reparto_id = :rep_id AND attivo = 1
                        """), {"rep_id": rep_id}).mappings().all()
                        dest_emails = [r["email"] for r in resp_rows if r["email"]]
                        
                    if not dest_emails:
                        print(f"[*] Nessun responsabile attivo configurato per il reparto '{rep_nome}' (ID: {rep_id}). Invio report saltato.")
                        continue
                        
                    print(f"[*] Generazione report RESP_STATUS per reparto '{rep_nome}' (Destinatari: {', '.join(dest_emails)})")
                    data = query_resp_status_for_reparto(conn, rep_id, rep_nome)
                    
                    subject = f"[{CFG.get('app_title', 'Troubletick')}] 📋 Report Attività & Presenze - Reparto: {rep_nome}"
                    body = build_html_resp_status(data)
                    reason = f"Report Attività e Copertura Servizi programmato per reparto {rep_nome} (RESP_STATUS)"
                    
                    for dest in dest_emails:
                        send_email_async(
                            dest_email=dest,
                            subject=subject,
                            body=body,
                            reason=reason,
                            cc_email=cc_email
                        )
                    print(f"[+] Inviato con successo per reparto '{rep_nome}'!")
                    
            elif email_type == "OPE_STATUS":
                print("[*] Esecuzione query per OPE_STATUS per ciascun operatore...")
                
                # Trova tutti gli operatori attivi di reparti che offrono assistenza
                operators_rows = conn.execute(text("""
                    SELECT DISTINCT u.user_id, u.nome, u.cognome, u.email, u.reparto_id, r.nome as reparto_nome
                    FROM users u
                    JOIN reparti r ON u.reparto_id = r.reparto_id
                    JOIN servizi s ON r.reparto_id = s.reparto_id
                    WHERE u.ruolo = 'assistenza' AND u.attivo = 1 AND s.accetta_ticket = 1
                """)).mappings().all()
                
                if not operators_rows:
                    print("[*] Nessun operatore attivo in reparti di assistenza trovato.")
                    sys.exit(0)
                    
                cc_email = None if args.mail else args.cc
                
                for op in operators_rows:
                    op_id = op["user_id"]
                    op_nome = op["nome"]
                    op_cognome = op["cognome"]
                    op_email = op["email"]
                    rep_id = op["reparto_id"]
                    rep_nome = op["reparto_nome"]
                    
                    # Se l'utente ha specificato --mail o --to sulla riga di comando, inviamo solo lì
                    dest_email = args.mail or args.to or op_email
                    if not dest_email:
                        print(f"[*] Operatore {op_nome} {op_cognome} non ha un indirizzo email configurato. Invio saltato.")
                        continue
                        
                    print(f"[*] Generazione report OPE_STATUS per operatore '{op_nome} {op_cognome}' (Destinatario: {dest_email})")
                    data = query_ope_status(conn, op_id, op_nome, op_cognome, rep_id, rep_nome)
                    
                    subject = f"[{CFG.get('app_title', 'Troubletick')}] 🗓️ Riepilogo Ticket e Turni per {op_nome}"
                    body = build_html_ope_status(data)
                    reason = f"Report Attività e Copertura programmato per operatore {op_nome} {op_cognome} (OPE_STATUS)"
                    
                    send_email_async(
                        dest_email=dest_email,
                        subject=subject,
                        body=body,
                        reason=reason,
                        cc_email=cc_email
                    )
                    print(f"[+] Inviato con successo a {op_nome} {op_cognome}!")
            
    except Exception as e:
        print(f"[ERRORE CRITICO] Esecuzione fallita: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
