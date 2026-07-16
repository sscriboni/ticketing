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

def query_resp_status(conn):
    """Raccoglie i dati per il report RESP_STATUS"""
    data = {}
    
    # Rileva il dialect del database per compatibilità SQLite / MySQL / MariaDB
    is_sqlite = engine.dialect.name == 'sqlite'
    if is_sqlite:
        date_filter = "date(creato_il, 'localtime') = date('now', 'localtime')"
        note_date_filter = "date(tn.creato_il, 'localtime') = date('now', 'localtime')"
    else:
        date_filter = "DATE(creato_il) = CURDATE()"
        note_date_filter = "DATE(tn.creato_il) = CURDATE()"

    # 1. Ticket aperti oggi, chiusi oggi e totali in attesa raggruppati per Servizio
    try:
        # Recupera la lista di tutti i servizi
        servizi_rows = conn.execute(text("SELECT servizio_id, descrizione FROM servizi ORDER BY descrizione")).mappings().all()
        services = {r["servizio_id"]: {"nome": r["descrizione"], "aperti_oggi": 0, "chiusi_oggi": 0, "in_attesa": 0} for r in servizi_rows}
        services[None] = {"nome": "[Nessun Servizio / Altro]", "aperti_oggi": 0, "chiusi_oggi": 0, "in_attesa": 0}
        
        # Biglietti aperti oggi (creati oggi)
        aperti_oggi_rows = conn.execute(text(f"""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE {date_filter}
            GROUP BY servizio_id
        """)).mappings().all()
        for r in aperti_oggi_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["aperti_oggi"] = r["count"]
            else:
                services[None]["aperti_oggi"] += r["count"]
                
        # Biglietti chiusi oggi (hanno nota di chiusura oggi)
        chiusi_oggi_rows = conn.execute(text(f"""
            SELECT t.servizio_id, COUNT(DISTINCT t.ticket_id) as count
            FROM tickets t
            JOIN ticket_notes tn ON t.ticket_id = tn.ticket_id
            WHERE t.stato = 'chiusa'
              AND tn.testo LIKE 'Stato modificato in: %Chiusa%.'
              AND {note_date_filter}
            GROUP BY t.servizio_id
        """)).mappings().all()
        for r in chiusi_oggi_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["chiusi_oggi"] = r["count"]
            else:
                services[None]["chiusi_oggi"] += r["count"]

        # Biglietti totali in attesa (stato != 'chiusa')
        in_attesa_rows = conn.execute(text("""
            SELECT servizio_id, COUNT(*) as count 
            FROM tickets 
            WHERE stato != 'chiusa'
            GROUP BY servizio_id
        """)).mappings().all()
        for r in in_attesa_rows:
            sid = r["servizio_id"]
            if sid in services:
                services[sid]["in_attesa"] = r["count"]
            else:
                services[None]["in_attesa"] += r["count"]

        # Trasforma in lista, escludi servizi con tutti i conteggi a zero (per brevità) ma mantieni quelli con in attesa > 0
        servizi_stats = []
        for sid, sinfo in services.items():
            if sinfo["aperti_oggi"] > 0 or sinfo["chiusi_oggi"] > 0 or sinfo["in_attesa"] > 0:
                servizi_stats.append({
                    "id": sid,
                    "nome": sinfo["nome"],
                    "aperti_oggi": sinfo["aperti_oggi"],
                    "chiusi_oggi": sinfo["chiusi_oggi"],
                    "in_attesa": sinfo["in_attesa"]
                })
        
        # Ordina per in_attesa discendente (evidenziando i servizi che hanno più ticket in attesa)
        servizi_stats.sort(key=lambda x: x["in_attesa"], reverse=True)
        data["servizi_stats"] = servizi_stats
        
    except Exception as e:
        print(f"[ERRORE] Recupero statistiche ticket per servizio fallito: {e}")
        data["servizi_stats"] = []

    # 2. Giornata lavorativa successiva: calcolo operatori presenti, assenti e scoperture
    next_day, next_day_str = get_next_working_day(conn)
    data["next_working_day_obj"] = next_day
    data["next_working_day_str"] = next_day_str
    data["next_working_day_formatted"] = format_date_italian(next_day)

    try:
        # Recupera tutti gli operatori attivi (ruolo != 'normale' ed attivo = 1)
        ops_rows = conn.execute(text("""
            SELECT user_id, username, nome, cognome, ruolo, email 
            FROM users 
            WHERE ruolo != 'normale' AND attivo = 1
        """)).mappings().all()
        operators = {r["user_id"]: dict(r) for r in ops_rows}

        # Recupera assenze per il giorno successivo
        assenze_rows = conn.execute(text("""
            SELECT user_id, motivo FROM assenze 
            WHERE data_inizio <= :target AND data_fine >= :target
        """), {"target": next_day_str}).mappings().all()
        absent_dict = {a["user_id"]: (a["motivo"] or "Assenza non specificata") for a in assenze_rows}

        # Suddividi in presenti ed assenti
        presenti = []
        assenti = []
        for uid, op in operators.items():
            if uid == 1: # Ignora superuser generico se necessario, oppure inseriscilo. Manteniamolo per completezza
                continue
            if uid in absent_dict:
                op["motivo"] = absent_dict[uid]
                assenti.append(op)
            else:
                presenti.append(op)
                
        data["presenti"] = presenti
        data["assenti"] = assenti

        # 3. Mappatura servizi ed eventuali scoperture
        # Recupera l'elenco dei servizi ed i loro operatori assegnati (escluso ruolo 'admin')
        service_ops_rows = conn.execute(text("""
            SELECT s.servizio_id, s.descrizione as servizio_desc, 
                   r.reparto_id, r.nome as reparto_nome,
                   u.user_id, u.nome, u.cognome
            FROM servizi s
            JOIN reparti r ON s.reparto_id = r.reparto_id
            LEFT JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
            LEFT JOIN users u ON os.user_id = u.user_id AND u.attivo = 1 AND u.ruolo != 'admin'
            ORDER BY r.nome, s.descrizione
        """)).mappings().all()

        service_coverage = {}
        for row in service_ops_rows:
            sid = row["servizio_id"]
            if sid not in service_coverage:
                service_coverage[sid] = {
                    "id": sid,
                    "descrizione": row["servizio_desc"],
                    "reparto": row["reparto_nome"],
                    "totale_assegnati": 0,
                    "presenti_nomi": [],
                    "assenti_nomi": []
                }
            uid = row["user_id"]
            if uid:
                service_coverage[sid]["totale_assegnati"] += 1
                name_str = f"{row['nome']} {row['cognome']}".strip() or row['username']
                if uid in absent_dict:
                    service_coverage[sid]["assenti_nomi"].append(name_str)
                else:
                    service_coverage[sid]["presenti_nomi"].append(name_str)

        # Classifica i servizi per stato di copertura
        scoperti = [] # Assegnati > 0 ma presenti = 0
        non_assegnati = [] # Assegnati = 0
        coperti = [] # Presenti > 0
        
        for sid, cov in service_coverage.items():
            presenti_cnt = len(cov["presenti_nomi"])
            if cov["totale_assegnati"] == 0:
                non_assegnati.append(cov)
            elif presenti_cnt == 0:
                cov["presenti_cnt"] = 0
                scoperti.append(cov)
            else:
                cov["presenti_cnt"] = presenti_cnt
                coperti.append(cov)

        data["scoperti"] = scoperti
        data["non_assegnati"] = non_assegnati
        data["coperti"] = coperti

    except Exception as e:
        print(f"[ERRORE] Analisi copertura operatori fallita: {e}")
        data["presenti"] = []
        data["assenti"] = []
        data["scoperti"] = []
        data["non_assegnati"] = []
        data["coperti"] = []

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
    
    # 1. Tabella Servizi (Aperti oggi, Chiusi oggi, In attesa)
    servizi_rows_html = ""
    if data["servizi_stats"]:
        for s in data["servizi_stats"]:
            # Evidenzia se ci sono ticket in attesa
            bg_style = ""
            badge_in_attesa = f"<span class='badge badge-neutral'>{s['in_attesa']}</span>"
            if s['in_attesa'] > 5:
                bg_style = "background-color: #fffbeb;" # Amber background per carico di lavoro elevato
                badge_in_attesa = f"<span class='badge badge-danger'>{s['in_attesa']} in attesa</span>"
            elif s['in_attesa'] > 0:
                badge_in_attesa = f"<span class='badge badge-warning'>{s['in_attesa']} in attesa</span>"
            else:
                badge_in_attesa = "<span class='badge badge-success'>0 - Libero</span>"

            servizi_rows_html += f"""
            <tr style="{bg_style}">
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #334155;">{s['nome']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #1e40af;">+ {s['aperti_oggi']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #065f46;">✓ {s['chiusi_oggi']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{badge_in_attesa}</td>
            </tr>
            """
    else:
        servizi_rows_html = "<tr><td colspan='4' style='padding: 15px; text-align: center; color: #64748b;'>Nessun movimento ticket registrato oggi.</td></tr>"

    # 2. Operatori Presenti domani
    presenti_html = ""
    if data["presenti"]:
        for op in data["presenti"]:
            presenti_html += f"""
            <div style="display: inline-block; width: 45%; margin: 5px; padding: 10px; background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; vertical-align: top;">
                <strong style="color: #065f46;">{op['nome']} {op['cognome']}</strong><br>
                <span style="font-size: 11px; color: #34d399; background: #065f46; padding: 2px 6px; border-radius: 4px; font-weight: bold; display: inline-block; margin-top: 4px;">
                    {op['ruolo'].upper()}
                </span>
            </div>
            """
    else:
        presenti_html = "<p style='color: #ef4444; font-weight: bold;'>⚠️ Attenzione! Nessun operatore disponibile in servizio.</p>"

    # 3. Operatori Assenti domani
    assenti_html = ""
    if data["assenti"]:
        for op in data["assenti"]:
            assenti_html += f"""
            <div style="padding: 10px; background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; margin-bottom: 8px;">
                <strong style="color: #991b1b;">{op['nome']} {op['cognome']}</strong> 
                <span style="font-size: 11px; color: #b91c1c; background: #fee2e2; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-left: 6px;">
                    {op['ruolo'].upper()}
                </span><br>
                <span style="font-size: 12px; color: #7f1d1d; display: inline-block; margin-top: 4px;">ℹ️ Motivo: <em>{op['motivo']}</em></span>
            </div>
            """
    else:
        assenti_html = "<p style='color: #065f46;'>Nessun operatore assente programmato per domani.</p>"

    # 4. Scoperture Servizi
    scoperti_html = ""
    if data["scoperti"]:
        for cov in data["scoperti"]:
            assenti_list = ", ".join(cov["assenti_nomi"]) if cov["assenti_nomi"] else "Nessuno"
            scoperti_html += f"""
            <div style="padding: 12px; background-color: #fff5f5; border-left: 4px solid #ef4444; border-radius: 6px; margin-bottom: 10px; border: 1px solid #fee2e2; border-left-width: 4px;">
                <strong style="color: #c53030; font-size: 14px;">{cov['descrizione']}</strong> <span style="font-size: 11px; color: #4a5568;">({cov['reparto']})</span><br>
                <span style="font-size: 12px; color: #9b2c2c; font-weight: bold;">STATO: SCOPERTO (0 Operatori Presenti)</span><br>
                <span style="font-size: 12px; color: #4a5568;">Operatori Assegnati Assenti: {assenti_list}</span>
            </div>
            """
    else:
        scoperti_html = "<div style='padding: 12px; background-color: #f0fdf4; border-left: 4px solid #10b981; border-radius: 6px; color: #166534; font-weight: bold;'>✓ Ottimo! Nessun servizio con operatori assegnati risulta scoperto.</div>"

    # 5. Servizi Senza Operatori Assegnati
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
                    📋 Report Attività & Presenze Servizi
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 14px; color: #c7d2fe;">Statistiche giornaliere ed organizzazione turni per i Responsabili</p>
            </div>
            
            <div style="padding: 25px;">
                <!-- SEZIONE 1: Ticket giornata in corso -->
                <h2 style="font-size: 16px; font-weight: 700; color: #4f46e5; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    📅 Attività Ticket Odierna (Giornata in Corso)
                </h2>
                <p style="font-size: 13px; color: #64748b; margin-top: 0; margin-bottom: 12px;">
                    Riepilogo dei ticket aperti e chiusi oggi, ordinati per backlog residuo (Servizi con più ticket in attesa in alto):
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px;">
                    <thead>
                        <tr style="background-color: #f1f5f9;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Servizio</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Aperti Oggi</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Chiusi Oggi</th>
                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #cbd5e1; font-weight: bold; color: #475569;">Totale in Attesa</th>
                        </tr>
                    </thead>
                    <tbody>
                        {servizi_rows_html}
                    </tbody>
                </table>

                <!-- SEZIONE 2: Giornata Lavorativa Successiva -->
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 30px;">
                    <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 15px; font-weight: bold; color: #1e1b4b; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">
                        🔮 Turno per la giornata successiva: <span style="color: #4f46e5;">{data['next_working_day_formatted']}</span>
                    </h3>
                    
                    <div style="display: table; width: 100%;">
                        <div style="display: table-row;">
                            <!-- Operatori Presenti -->
                            <div style="display: table-cell; width: 50%; padding-right: 10px; vertical-align: top;">
                                <h4 style="margin: 0 0 10px 0; font-size: 13px; font-weight: bold; color: #065f46; text-transform: uppercase;">
                                    🟢 Operatori Presenti ({len(data['presenti'])})
                                </h4>
                                {presenti_html}
                            </div>
                            
                            <!-- Operatori Assenti -->
                            <div style="display: table-cell; width: 50%; padding-left: 10px; vertical-align: top;">
                                <h4 style="margin: 0 0 10px 0; font-size: 13px; font-weight: bold; color: #991b1b; text-transform: uppercase;">
                                    🔴 Operatori Assenti ({len(data['assenti'])})
                                </h4>
                                {assenti_html}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- SEZIONE 3: Scoperture -->
                <h2 style="font-size: 16px; font-weight: 700; color: #b91c1c; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">
                    🚨 Scoperture Servizi Rilevate (Domani)
                </h2>
                <div style="margin-bottom: 25px;">
                    {scoperti_html}
                </div>

                <!-- SEZIONE 4: Servizi non assegnati -->
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

def main():
    parser = argparse.ArgumentParser(description="Script di notifica programmata per l'Helpdesk Troubletick")
    parser.add_argument("type", nargs="?", choices=["ADMIN_STATUS", "RESP_STATUS"], help="Tipologia di email da inviare")
    parser.add_argument("--type", dest="type_flag", choices=["ADMIN_STATUS", "RESP_STATUS"], help="Tipologia di email da inviare (opzione)")
    parser.add_argument("--to", help="Indirizzo email di destinazione personalizzato (sovrascrive la configurazione)")
    parser.add_argument("--cc", help="Indirizzo email in CC personalizzato")
    parser.add_argument("--mail", help="Indirizzo email a cui inviare SOLO ed ESCLUSIVAMENTE la mail, disattivando altri destinatari e CC")
    
    args = parser.parse_args()
    
    # Risolvi il tipo di email (sia posizionale che flag)
    email_type = args.type or args.type_flag
    
    if not email_type:
        print("[ERRORE] Devi specificare una tipologia di mail da inviare: ADMIN_STATUS o RESP_STATUS.")
        parser.print_help()
        sys.exit(1)
        
    print(f"[*] Avvio generazione notifica: {email_type}")
    
    # Recupera indirizzo destinatario di default
    default_recipient = CFG.get("helpdesk_email", "admin@example.com")
    dest_email = args.mail or args.to or default_recipient
    cc_email = None if args.mail else args.cc
    
    print(f"[*] Destinatario impostato: {dest_email} (CC: {cc_email or 'Nessuno'})")

    try:
        with engine.connect() as conn:
            if email_type == "ADMIN_STATUS":
                print("[*] Esecuzione query per ADMIN_STATUS...")
                data = query_admin_status(conn)
                subject = f"[{CFG.get('app_title', 'Troubletick')}] ⚙️ Stato del Sistema ed Accessi"
                body = build_html_admin_status(data)
                reason = "Report Amministrativo programmato (ADMIN_STATUS)"
                
            elif email_type == "RESP_STATUS":
                print("[*] Esecuzione query per RESP_STATUS...")
                data = query_resp_status(conn)
                subject = f"[{CFG.get('app_title', 'Troubletick')}] 📋 Report Attività Ticket & Presenze"
                body = build_html_resp_status(data)
                reason = "Report Attività e Copertura Servizi programmato (RESP_STATUS)"
            
            print("[*] Generazione email completata. Invio in corso...")
            send_email_async(
                dest_email=dest_email,
                subject=subject,
                body=body,
                reason=reason,
                cc_email=cc_email
            )
            print("[+] Inviata con successo!")
            
    except Exception as e:
        print(f"[ERRORE CRITICO] Esecuzione fallita: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
