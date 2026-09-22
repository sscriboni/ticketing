import os
import sys
import logging
from datetime import datetime
from sqlalchemy import text

# Assicuriamo che il percorso corrente sia in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core import engine, CFG, templates, LOG_DIR
from email_utils import send_email_async, _log_email_event

logger = logging.getLogger("fleet_notifications")


def notifica_utente_prenotazione(
    azione: str,
    automezzo_id: int,
    data_viaggio: str,
    ora_partenza: str,
    ora_riconsegna_prevista: str = None,
    sede_partenza_id: int = None,
    sede_partenza_nome: str = None,
    conducente_id: int = None,
    conducente_email: str = None,
    conducente_nome: str = None,
    note: str = None,
    autore_nome: str = None,
    autore_email: str = None,
) -> bool:
    """
    Invia un'email riepilogativa all'utente che ha effettuato/ricevuto la prenotazione
    o la cancellazione di un autoveicolo.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    azione_clean = (azione or "nuova").strip().lower()
    if azione_clean not in ("nuova", "cancellata"):
        azione_clean = "nuova"

    try:
        with engine.connect() as conn:
            # 1. Dati del veicolo
            car = conn.execute(text("""
                SELECT a.automezzo_id, a.targa, a.modello, a.reparto_assegnato_id,
                       COALESCE(m.nome, 'Altro') as marca_nome,
                       r.nome as reparto_nome,
                       r.messaggio_carpooling as istruzioni_carpooling,
                       s_ass.nome as sede_assegnata_nome,
                       s_att.nome as sede_attuale_nome,
                       a.posizione_parcheggio
                FROM automezzi a
                LEFT JOIN marche_automezzi m ON a.marca_id = m.marca_id
                LEFT JOIN reparti r ON a.reparto_assegnato_id = r.reparto_id
                LEFT JOIN sedi s_ass ON a.sede_assegnata_id = s_ass.sede_id
                LEFT JOIN sedi s_att ON a.sede_attuale_id = s_att.sede_id
                WHERE a.automezzo_id = :aid
            """), {"aid": automezzo_id}).mappings().first()

            if not car:
                msg = f"[{now_str}] SKIPPED - User Booking Notify: Automezzo ID {automezzo_id} non trovato nel database."
                _log_email_event(msg)
                return False

            # 1b. Fleet Manager del reparto
            fleet_managers_list = []
            rep_id = car.get("reparto_assegnato_id")
            if rep_id:
                fm_rows = conn.execute(text("""
                    SELECT DISTINCT u.nome, u.cognome, u.email, u.telefono
                    FROM users u
                    LEFT JOIN user_roles ur ON u.user_id = ur.user_id
                    WHERE u.attivo = 1
                      AND u.reparto_id = :rep_id
                      AND (u.ruolo = 'fleet_manager' OR ur.ruolo = 'fleet_manager')
                    ORDER BY u.cognome, u.nome
                """), {"rep_id": rep_id}).mappings().all()
                fleet_managers_list = [dict(fm) for fm in fm_rows]

            # 2. Risoluzione sede di partenza
            resolved_sede_nome = (sede_partenza_nome or "").strip()
            if not resolved_sede_nome and sede_partenza_id:
                s_row = conn.execute(text("SELECT nome FROM sedi WHERE sede_id = :sid"), {"sid": sede_partenza_id}).mappings().first()
                if s_row:
                    resolved_sede_nome = s_row["nome"]
            if not resolved_sede_nome:
                resolved_sede_nome = car.get("sede_attuale_nome") or car.get("sede_assegnata_nome") or "Non specificata"

            # 3. Risoluzione anagrafica conducente
            resolved_conducente_nome = (conducente_nome or "").strip()
            resolved_conducente_email = (conducente_email or "").strip().lower()

            if conducente_id and (not resolved_conducente_nome or not resolved_conducente_email):
                u_row = conn.execute(text("SELECT nome, cognome, email FROM users WHERE user_id = :uid"), {"uid": conducente_id}).mappings().first()
                if u_row:
                    if not resolved_conducente_nome:
                        resolved_conducente_nome = f"{u_row.get('nome', '')} {u_row.get('cognome', '')}".strip()
                    if not resolved_conducente_email and u_row.get("email"):
                        resolved_conducente_email = u_row.get("email").strip().lower()

            if resolved_conducente_email and not resolved_conducente_nome:
                u_row_email = conn.execute(text("SELECT nome, cognome FROM users WHERE LOWER(email) = LOWER(:email)"), {"email": resolved_conducente_email}).mappings().first()
                if u_row_email:
                    resolved_conducente_nome = f"{u_row_email.get('nome', '')} {u_row_email.get('cognome', '')}".strip()

            if not resolved_conducente_nome:
                resolved_conducente_nome = resolved_conducente_email or "Gentile Utente"

            # 4. Determinazione destinatari (conducente e autore se diverso)
            dest_email = resolved_conducente_email
            cc_email = None

            autore_email_clean = (autore_email or "").strip().lower()
            if autore_email_clean:
                if not dest_email:
                    dest_email = autore_email_clean
                elif dest_email != autore_email_clean:
                    cc_email = autore_email_clean

            if not dest_email:
                msg = f"[{now_str}] SKIPPED - User Booking Notify: Nessun indirizzo email conducente o richiedente disponibile per il veicolo {car['targa']}."
                _log_email_event(msg)
                return False

            # 5. Formattazione data viaggio
            formatted_data = str(data_viaggio or "")
            try:
                dt_obj = datetime.strptime(data_viaggio, "%Y-%m-%d")
                formatted_data = dt_obj.strftime("%d/%m/%Y")
            except Exception:
                pass

            app_title = CFG.get("app_title", "Troubletick")
            targa = car["targa"].upper()

            if azione_clean == "nuova":
                subject = f"[{app_title}] 🚗 Conferma Prenotazione: {targa} ({car['marca_nome']} {car['modello']})"
                reason = f"Riepilogo nuova prenotazione veicolo {targa} inviato a {dest_email}"
            else:
                subject = f"[{app_title}] 🚫 Cancellazione Prenotazione: {targa} ({car['marca_nome']} {car['modello']})"
                reason = f"Riepilogo cancellazione prenotazione veicolo {targa} inviato a {dest_email}"

            prenotazione_dict = {
                "data_viaggio": formatted_data,
                "ora_partenza": ora_partenza or "--:--",
                "ora_riconsegna_prevista": ora_riconsegna_prevista or "--:--",
                "sede_partenza_nome": resolved_sede_nome,
                "conducente_nome": resolved_conducente_nome,
                "conducente_email": resolved_conducente_email,
                "note": (note or "").strip()
            }

            autore_display = (autore_nome or "").strip() or "Sistema / Utente"

            html_body = templates.get_template("email_riepilogo_prenotazione_utente.html").render({
                "cfg": CFG,
                "azione": azione_clean,
                "veicolo": dict(car),
                "prenotazione": prenotazione_dict,
                "autore_nome": autore_display,
                "destinatario_nome": resolved_conducente_nome,
                "app_url": CFG.get("app_url", ""),
                "istruzioni": (car.get("istruzioni_carpooling") or "").strip(),
                "fleet_managers": fleet_managers_list
            })

            return send_email_async(
                dest_email=dest_email,
                subject=subject,
                body=html_body,
                reason=reason,
                cc_email=cc_email
            )

    except Exception as e:
        err_msg = f"[{now_str}] FAILURE - User Booking Notify Exception: {type(e).__name__}: {str(e)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False


def notifica_fleet_managers_prenotazione(
    azione: str,
    automezzo_id: int,
    data_viaggio: str,
    ora_partenza: str,
    ora_riconsegna_prevista: str = None,
    sede_partenza_id: int = None,
    sede_partenza_nome: str = None,
    conducente_id: int = None,
    conducente_email: str = None,
    conducente_nome: str = None,
    note: str = None,
    autore_nome: str = None,
    autore_email: str = None,
) -> bool:
    """
    Invia un'email di notifica a tutti i Fleet Manager attivi assegnati al reparto
    di appartenenza del veicolo indicato, E all'utente/conducente che ha effettuato
    la prenotazione o la cancellazione.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    azione_clean = (azione or "nuova").strip().lower()
    if azione_clean not in ("nuova", "cancellata"):
        azione_clean = "nuova"

    # Invia sempre la notifica riepilogativa all'utente che ha prenotato / conducente
    try:
        notifica_utente_prenotazione(
            azione=azione_clean,
            automezzo_id=automezzo_id,
            data_viaggio=data_viaggio,
            ora_partenza=ora_partenza,
            ora_riconsegna_prevista=ora_riconsegna_prevista,
            sede_partenza_id=sede_partenza_id,
            sede_partenza_nome=sede_partenza_nome,
            conducente_id=conducente_id,
            conducente_email=conducente_email,
            conducente_nome=conducente_nome,
            note=note,
            autore_nome=autore_nome,
            autore_email=autore_email
        )
    except Exception as e_user:
        logger.warning(f"Errore invio notifica utente: {e_user}")

    # Notifica ai Fleet Manager del reparto
    try:
        with engine.connect() as conn:
            # 1. Recupero dati completi dell'automezzo e del suo reparto assegnato
            car = conn.execute(text("""
                SELECT a.automezzo_id, a.targa, a.modello, a.reparto_assegnato_id,
                       COALESCE(m.nome, 'Altro') as marca_nome,
                       r.nome as reparto_nome,
                       s_ass.nome as sede_assegnata_nome,
                       s_att.nome as sede_attuale_nome
                FROM automezzi a
                LEFT JOIN marche_automezzi m ON a.marca_id = m.marca_id
                LEFT JOIN reparti r ON a.reparto_assegnato_id = r.reparto_id
                LEFT JOIN sedi s_ass ON a.sede_assegnata_id = s_ass.sede_id
                LEFT JOIN sedi s_att ON a.sede_attuale_id = s_att.sede_id
                WHERE a.automezzo_id = :aid
            """), {"aid": automezzo_id}).mappings().first()

            if not car:
                msg = f"[{now_str}] SKIPPED - Fleet Notify: Automezzo ID {automezzo_id} non trovato nel database."
                _log_email_event(msg)
                return False

            reparto_id = car["reparto_assegnato_id"]
            if not reparto_id or reparto_id == 0:
                msg = f"[{now_str}] SKIPPED - Fleet Notify: Automezzo {car['targa']} (ID: {automezzo_id}) non ha un reparto assegnato."
                _log_email_event(msg)
                return False

            # 2. Ricerca Fleet Manager attivi del reparto del veicolo (sia da users che da user_roles)
            fm_rows = conn.execute(text("""
                SELECT DISTINCT u.user_id, u.email, u.nome, u.cognome
                FROM users u
                LEFT JOIN user_roles ur ON u.user_id = ur.user_id
                WHERE u.attivo = 1
                  AND u.reparto_id = :rep_id
                  AND (u.ruolo = 'fleet_manager' OR ur.ruolo = 'fleet_manager')
                  AND u.email IS NOT NULL AND TRIM(u.email) != ''
            """), {"rep_id": reparto_id}).mappings().all()

            if not fm_rows:
                rep_label = car["reparto_nome"] or f"ID {reparto_id}"
                msg = f"[{now_str}] SKIPPED - Fleet Notify: Nessun Fleet Manager attivo configurato con email per il reparto '{rep_label}' (Veicolo: {car['targa']})."
                _log_email_event(msg)
                return False

            # 3. Risoluzione sede di partenza se non specificata
            resolved_sede_nome = (sede_partenza_nome or "").strip()
            if not resolved_sede_nome and sede_partenza_id:
                s_row = conn.execute(text("SELECT nome FROM sedi WHERE sede_id = :sid"), {"sid": sede_partenza_id}).mappings().first()
                if s_row:
                    resolved_sede_nome = s_row["nome"]
            if not resolved_sede_nome:
                resolved_sede_nome = car.get("sede_attuale_nome") or car.get("sede_assegnata_nome") or "Non specificata"

            # 4. Risoluzione anagrafica conducente
            resolved_conducente_nome = (conducente_nome or "").strip()
            resolved_conducente_email = (conducente_email or "").strip()

            if conducente_id and (not resolved_conducente_nome or not resolved_conducente_email):
                u_row = conn.execute(text("SELECT nome, cognome, email FROM users WHERE user_id = :uid"), {"uid": conducente_id}).mappings().first()
                if u_row:
                    if not resolved_conducente_nome:
                        resolved_conducente_nome = f"{u_row.get('nome', '')} {u_row.get('cognome', '')}".strip()
                    if not resolved_conducente_email:
                        resolved_conducente_email = u_row.get("email", "")

            if resolved_conducente_email and not resolved_conducente_nome:
                u_row_email = conn.execute(text("SELECT nome, cognome FROM users WHERE LOWER(email) = LOWER(:email)"), {"email": resolved_conducente_email}).mappings().first()
                if u_row_email:
                    resolved_conducente_nome = f"{u_row_email.get('nome', '')} {u_row_email.get('cognome', '')}".strip()

            if not resolved_conducente_nome:
                resolved_conducente_nome = resolved_conducente_email or "Non specificato"

            # 5. Formattazione data viaggio (es. da YYYY-MM-DD a DD/MM/YYYY)
            formatted_data = str(data_viaggio or "")
            try:
                dt_obj = datetime.strptime(data_viaggio, "%Y-%m-%d")
                formatted_data = dt_obj.strftime("%d/%m/%Y")
            except Exception:
                pass

            app_title = CFG.get("app_title", "Troubletick")
            targa = car["targa"].upper()
            reparto_nome = car["reparto_nome"] or "Aziendale"

            if azione_clean == "nuova":
                subject = f"[{app_title}] 🚗 Nuova Prenotazione: {targa} ({car['marca_nome']} {car['modello']}) - Reparto {reparto_nome}"
                reason = f"Notifica nuova prenotazione veicolo {targa} ai fleet manager del reparto {reparto_nome}"
            else:
                subject = f"[{app_title}] 🚫 Prenotazione Cancellata: {targa} ({car['marca_nome']} {car['modello']}) - Reparto {reparto_nome}"
                reason = f"Notifica cancellazione prenotazione veicolo {targa} ai fleet manager del reparto {reparto_nome}"

            prenotazione_dict = {
                "data_viaggio": formatted_data,
                "ora_partenza": ora_partenza or "--:--",
                "ora_riconsegna_prevista": ora_riconsegna_prevista or "--:--",
                "sede_partenza_nome": resolved_sede_nome,
                "conducente_nome": resolved_conducente_nome,
                "conducente_email": resolved_conducente_email,
                "note": (note or "").strip()
            }

            autore_display = (autore_nome or "").strip() or "Sistema / Utente"

            # 6. Invio email a ciascun Fleet Manager destinatario
            sent_count = 0
            for fm in fm_rows:
                fm_email = (fm.get("email") or "").strip()
                if not fm_email:
                    continue
                fm_nome = f"{fm.get('nome', '')} {fm.get('cognome', '')}".strip() or "Fleet Manager"

                html_body = templates.get_template("email_notifica_prenotazione_fleet.html").render({
                    "cfg": CFG,
                    "azione": azione_clean,
                    "veicolo": dict(car),
                    "prenotazione": prenotazione_dict,
                    "autore_nome": autore_display,
                    "destinatario_nome": fm_nome,
                    "app_url": CFG.get("app_url", "")
                })

                res = send_email_async(
                    dest_email=fm_email,
                    subject=subject,
                    body=html_body,
                    reason=reason
                )
                if res:
                    sent_count += 1

            return sent_count > 0

    except Exception as e:
        err_msg = f"[{now_str}] FAILURE - Fleet Notify Exception: {type(e).__name__}: {str(e)}"
        print(err_msg)
        _log_email_event(err_msg)
        return False
