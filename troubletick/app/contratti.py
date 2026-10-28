import os
import io
import csv
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import text
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core import engine, CFG, templates, DB_PK, DB_DRIVER
from utils import current_user, user_has_tag_dec, user_can_manage_fornitori, safe_int, safe_float



router = APIRouter()

def init_contratti_db():
    with engine.begin() as c:
        # Tabella contratti
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS contratti (
            contratto_id {DB_PK},
            titolo TEXT NOT NULL,
            codice_contratto TEXT,
            cig TEXT,
            cup TEXT,
            fornitore_id INTEGER NOT NULL,
            anno INTEGER NOT NULL,
            data_inizio TEXT,
            data_fine TEXT,
            stato TEXT DEFAULT 'attivo',
            aliquota_iva REAL DEFAULT 22.0,
            dec_user_id INTEGER,
            reparto_id INTEGER,
            descrizione TEXT,
            creato_da_id INTEGER,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
            aggiornato_il TEXT,
            FOREIGN KEY(fornitore_id) REFERENCES fornitori(fornitore_id) ON DELETE RESTRICT,
            FOREIGN KEY(dec_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
            FOREIGN KEY(reparto_id) REFERENCES reparti(reparto_id) ON DELETE SET NULL,
            FOREIGN KEY(creato_da_id) REFERENCES users(user_id) ON DELETE SET NULL
        )"""))

        # Tabella moduli di fornitura legati al contratto
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS contratti_moduli (
            modulo_id {DB_PK},
            contratto_id INTEGER NOT NULL,
            servizio_id INTEGER,
            descrizione TEXT NOT NULL,
            costo REAL NOT NULL DEFAULT 0.0,
            giornate REAL,
            costo_giornaliero REAL,
            note TEXT,
            ordine INTEGER DEFAULT 0,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(contratto_id) REFERENCES contratti(contratto_id) ON DELETE CASCADE,
            FOREIGN KEY(servizio_id) REFERENCES servizi(servizio_id) ON DELETE SET NULL
        )"""))

        # Colonna opzionale importo su contratti se non ancora presente
        try:
            c.execute(text("ALTER TABLE contratti ADD COLUMN importo REAL DEFAULT 0.0"))
        except Exception:
            pass

        # Colonna aliquota_iva su contratti se non ancora presente
        try:
            c.execute(text("ALTER TABLE contratti ADD COLUMN aliquota_iva REAL DEFAULT 22.0"))
        except Exception:
            pass
        try:
            c.execute(text("UPDATE contratti SET aliquota_iva = 22.0 WHERE aliquota_iva IS NULL"))
        except Exception:
            pass

        # Tabella ordini al fornitore associati al contratto
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS contratti_ordini (
            ordine_id {DB_PK},
            contratto_id INTEGER NOT NULL,
            codice TEXT NOT NULL,
            descrizione TEXT NOT NULL,
            durata TEXT,
            importo REAL NOT NULL DEFAULT 0.0,
            cig TEXT,
            giornate REAL,
            costo_giornaliero REAL,
            stato TEXT DEFAULT 'emesso',
            note TEXT,
            creato_da_id INTEGER,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
            aggiornato_il TEXT,
            FOREIGN KEY(contratto_id) REFERENCES contratti(contratto_id) ON DELETE CASCADE,
            FOREIGN KEY(creato_da_id) REFERENCES users(user_id) ON DELETE SET NULL
        )"""))

        # Tabella attività operative legate all'ordine
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS ordini_attivita (
            attivita_id {DB_PK},
            ordine_id INTEGER NOT NULL,
            descrizione TEXT NOT NULL,
            data_inizio TEXT NOT NULL,
            data_fine TEXT,
            costo REAL NOT NULL DEFAULT 0.0,
            giornate REAL,
            stato TEXT DEFAULT 'pianificata',
            richiedente TEXT,
            data_richiesta TEXT,
            note TEXT,
            creato_da_id INTEGER,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
            aggiornato_il TEXT,
            FOREIGN KEY(ordine_id) REFERENCES contratti_ordini(ordine_id) ON DELETE CASCADE,
            FOREIGN KEY(creato_da_id) REFERENCES users(user_id) ON DELETE SET NULL
        )"""))

        # Indici per velocizzare ricerche e foreign key
        try:
            if DB_DRIVER.startswith("sqlite") or "sqlite" in DB_DRIVER:
                c.execute(text("CREATE INDEX IF NOT EXISTS idx_contratti_ordini_cid ON contratti_ordini (contratto_id)"))
                c.execute(text("CREATE INDEX IF NOT EXISTS idx_ordini_attivita_oid ON ordini_attivita (ordine_id)"))
            else:
                c.execute(text("CREATE INDEX idx_contratti_ordini_cid ON contratti_ordini (contratto_id)"))
                c.execute(text("CREATE INDEX idx_ordini_attivita_oid ON ordini_attivita (ordine_id)"))
        except Exception:
            pass

        # Assicuriamo la presenza del Tag DEC in tag_operatori
        try:
            dec_exists = c.execute(text("SELECT COUNT(*) FROM tag_operatori WHERE UPPER(nome) = 'DEC'")).scalar() or 0
            if dec_exists == 0:
                c.execute(text("""
                    INSERT INTO tag_operatori (nome, colore, descrizione)
                    VALUES ('DEC', '#dc3545', 'Direttore dell''Esecuzione del Contratto')
                """))
        except Exception as ex_tag:
            print(f"[CONTRATTI TAG INIT NOTE] {ex_tag}")

# Inizializzazione automatica delle tabelle
try:
    init_contratti_db()
except Exception as e:
    print(f"[CONTRATTI DB INIT WARNING] {e}")


# ==========================================
# HELPER PERMESSI E VISIBILITA'
# ==========================================


def user_can_access_contratti(user: dict) -> bool:
    """Verifica booleana se l'utente ha diritto ad accedere al modulo contratti"""
    if not user:
        return False
    ruolo = user.get("ruolo", "normale")
    if ruolo in ("admin", "responsabile", "amministrativo"):
        return True
    return user_has_tag_dec(user)

def check_contratti_access(r: Request):
    """
    Verifica se l'utente autenticato può accedere al modulo contratti:
    - Ruolo admin
    - Ruolo responsabile
    - Ruolo amministrativo
    - Operatore/Utente con tag DEC
    """
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    ruolo = user.get("ruolo", "normale")
    if ruolo in ("admin", "responsabile", "amministrativo"):
        return user

    if user_has_tag_dec(user):
        return user

    # Nessun permesso
    return RedirectResponse(url="/tickets?error=accesso_non_autorizzato", status_code=303)


def get_contratto_scope_filter(user: dict):
    """
    Tutti gli utenti abilitati al modulo contratti possono visualizzare tutti i contratti censiti.
    """
    return "1=1", {}


def can_manage_single_contratto(user: dict, contratto_row: dict, conn=None) -> bool:
    """
    Verifica se l'utente può modificare o eliminare un determinato contratto:
    - Admin / Amministrativo: sempre True
    - Inserito dall'operatore collegato (creato_da_id): True
    - Operatore è il DEC designato (dec_user_id): True
    - Legato ai propri servizi:
      * Responsabile: se il contratto appartiene al proprio reparto, è stato creato da un membro del proprio reparto,
        o ha moduli associati a servizi del proprio reparto
      * Operatore: se uno dei moduli del contratto è associato a un servizio assegnato all'operatore (operatori_servizi)
    """
    if not user or not user.get("id"):
        return False
    
    uid = user["id"]
    ruolo = user.get("ruolo", "normale")

    if ruolo in ("admin", "amministrativo"):
        return True

    # Inserito dall'operatore collegato
    if contratto_row.get("creato_da_id") == uid:
        return True

    # DEC del contratto
    if contratto_row.get("dec_user_id") == uid:
        return True

    cid = contratto_row.get("contratto_id")
    if not cid:
        return False

    def _check_in_db(c):
        # Se responsabile di reparto
        if ruolo == "responsabile":
            rep_id = user.get("reparto_id")
            if rep_id:
                if contratto_row.get("reparto_id") == rep_id:
                    return True
                # Creatore appartiene al reparto del responsabile
                if contratto_row.get("creato_da_id"):
                    creator_rep = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": contratto_row["creato_da_id"]}).scalar()
                    if creator_rep and creator_rep == rep_id:
                        return True
                # Moduli associati a servizi del reparto
                has_rep_services = c.execute(text("""
                    SELECT COUNT(*) 
                    FROM contratti_moduli cm 
                    JOIN servizi s ON cm.servizio_id = s.servizio_id 
                    WHERE cm.contratto_id = :cid AND s.reparto_id = :rep_id
                """), {"cid": cid, "rep_id": rep_id}).scalar() or 0
                if has_rep_services > 0:
                    return True

        # Per qualunque operatore: legato ai propri servizi assegnati (operatori_servizi)
        has_my_services = c.execute(text("""
            SELECT COUNT(*) 
            FROM contratti_moduli cm 
            WHERE cm.contratto_id = :cid 
              AND cm.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid)
        """), {"cid": cid, "uid": uid}).scalar() or 0
        if has_my_services > 0:
            return True

        return False

    if conn is not None:
        return _check_in_db(conn)
    else:
        with engine.connect() as c:
            return _check_in_db(c)


# ==========================================
# HELPER ECONOMICI / QUADRATURA ORDINI
# ==========================================

def get_contratto_financials(conn, contratto_id: int):
    """
    Calcola il quadro economico complessivo del contratto:
    - importo_contratto: somma dei moduli contratti_moduli, oppure se contratti.importo > 0, il massimo tra i due
    - tot_ordini: somma degli importi degli ordini associati (esclusi gli ordini in stato 'annullato')
    - residuo_ordinabile: importo_contratto - tot_ordini
    - is_allineato: True se l'importo degli ordini coincide esattamente (entro 1 centesimo) con l'importo contrattuale
    - perc_ordinata: percentuale di capienza contrattuale impegnata da ordini
    """
    row_c = conn.execute(text("SELECT importo, aliquota_iva FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
    importo_esplicito = (row_c["importo"] or 0.0) if row_c else 0.0
    aliquota_iva = (row_c["aliquota_iva"] if (row_c and row_c["aliquota_iva"] is not None) else 22.0)

    tot_moduli = conn.execute(text("SELECT COALESCE(SUM(costo), 0.0) FROM contratti_moduli WHERE contratto_id = :cid"), {"cid": contratto_id}).scalar() or 0.0

    if tot_moduli > 0:
        importo_contratto = max(tot_moduli, importo_esplicito)
    else:
        importo_contratto = importo_esplicito

    tot_ordini = conn.execute(text("""
        SELECT COALESCE(SUM(importo), 0.0) 
        FROM contratti_ordini 
        WHERE contratto_id = :cid AND (stato IS NULL OR stato != 'annullato')
    """), {"cid": contratto_id}).scalar() or 0.0

    tot_giornate_ordini = conn.execute(text("""
        SELECT COALESCE(SUM(giornate), 0.0) 
        FROM contratti_ordini 
        WHERE contratto_id = :cid AND (stato IS NULL OR stato != 'annullato')
    """), {"cid": contratto_id}).scalar() or 0.0

    residuo_ordinabile = importo_contratto - tot_ordini
    is_allineato = (importo_contratto > 0 and abs(residuo_ordinabile) < 0.01)
    perc_ordinata = round((tot_ordini / importo_contratto * 100.0), 1) if importo_contratto > 0 else 0.0

    iva_molt = 1.0 + (aliquota_iva / 100.0)
    importo_contratto_iva = round(importo_contratto * iva_molt, 2)
    tot_ordini_iva = round(tot_ordini * iva_molt, 2)
    residuo_ordinabile_iva = round(residuo_ordinabile * iva_molt, 2)

    return {
        "importo_contratto": importo_contratto,
        "importo_contratto_iva": importo_contratto_iva,
        "aliquota_iva": aliquota_iva,
        "tot_moduli": tot_moduli,
        "tot_ordini": tot_ordini,
        "tot_ordini_iva": tot_ordini_iva,
        "tot_giornate_ordini": tot_giornate_ordini,
        "residuo_ordinabile": residuo_ordinabile,
        "residuo_ordinabile_iva": residuo_ordinabile_iva,
        "is_allineato": is_allineato,
        "perc_ordinata": perc_ordinata
    }

def get_ordine_financials(conn, ordine_id: int):
    """
    Calcola il quadro economico del singolo ordine:
    - importo_ordine: importo economico dell'ordine
    - tot_costo_attivita: somma dei costi delle attività (escluse quelle annullate)
    - tot_giornate_attivita: somma delle giornate delle attività (escluse quelle annullate)
    - residuo_costo: capienza residua per creare nuove attività
    - residuo_giornate: giornate residue disponibili (se l'ordine prevede giornate)
    - perc_consumata: percentuale dell'ordine consumata da attività
    - is_esaurito: True se l'ordine ha esaurito l'importo
    """
    ordine = conn.execute(text("SELECT * FROM contratti_ordini WHERE ordine_id = :oid"), {"oid": ordine_id}).mappings().first()
    if not ordine:
        return None

    importo_ordine = ordine["importo"] or 0.0
    giornate_ordine = ordine["giornate"] or 0.0

    tot_costo_att = conn.execute(text("""
        SELECT COALESCE(SUM(costo), 0.0) 
        FROM ordini_attivita 
        WHERE ordine_id = :oid AND (stato IS NULL OR stato != 'annullata')
    """), {"oid": ordine_id}).scalar() or 0.0

    tot_giornate_att = conn.execute(text("""
        SELECT COALESCE(SUM(giornate), 0.0) 
        FROM ordini_attivita 
        WHERE ordine_id = :oid AND (stato IS NULL OR stato != 'annullata')
    """), {"oid": ordine_id}).scalar() or 0.0

    residuo_costo = importo_ordine - tot_costo_att
    residuo_giornate = (giornate_ordine - tot_giornate_att) if giornate_ordine > 0 else 0.0
    perc_consumata = round((tot_costo_att / importo_ordine * 100.0), 1) if importo_ordine > 0 else 0.0
    is_esaurito = (residuo_costo <= 0.009 and importo_ordine > 0)

    return {
        "ordine": dict(ordine),
        "importo_ordine": importo_ordine,
        "giornate_ordine": giornate_ordine,
        "tot_costo_attivita": tot_costo_att,
        "tot_giornate_attivita": tot_giornate_att,
        "residuo_costo": residuo_costo,
        "residuo_giornate": residuo_giornate,
        "perc_consumata": perc_consumata,
        "is_esaurito": is_esaurito
    }


# ==========================================
# ROTTE GESTIONE CONTRATTI
# ==========================================

def get_contratti_order_by(sort_by: Optional[str], sort_dir: Optional[str]) -> tuple[str, str, str]:
    """Risolve la clausola ORDER BY e direzione per la lista e l'export dei contratti."""
    sort_by_clean = (sort_by or "").strip().lower()
    sort_dir_clean = (sort_dir or "").strip().lower()

    sort_map = {
        "anno": "c.anno",
        "titolo": "c.titolo",
        "fornitore": "f.ragione_sociale",
        "dec": "u_dec.cognome, u_dec.nome",
        "reparto": "rep.nome",
        "moduli": "cnt_moduli",
        "importo": "totale_costo",
        "stato": "c.stato",
    }

    if sort_by_clean in sort_map:
        direction = "desc" if sort_dir_clean == "desc" else ("asc" if sort_dir_clean == "asc" else ("desc" if sort_by_clean in ("anno", "importo", "moduli") else "asc"))
        dir_sql = direction.upper()
        if sort_by_clean == "dec":
            order_clause = f"u_dec.cognome {dir_sql}, u_dec.nome {dir_sql}"
        else:
            order_clause = f"{sort_map[sort_by_clean]} {dir_sql}"
        return f"{order_clause}, c.contratto_id DESC", sort_by_clean, direction
    else:
        return "c.anno DESC, c.contratto_id DESC", "anno", "desc"

@router.get("/contratti", response_class=HTMLResponse)
@router.get("/contratto", response_class=HTMLResponse)
@router.get("/contratti/contratti", response_class=HTMLResponse)
@router.get("/contratto/contratti", response_class=HTMLResponse)
@router.get("/contratti/contratto", response_class=HTMLResponse)
@router.get("/contratti/elenco", response_class=HTMLResponse)
@router.get("/contratto/elenco", response_class=HTMLResponse)
def contratti_list(
    r: Request,
    anno: Optional[str] = None,
    fornitore_id: Optional[str] = None,
    stato: Optional[str] = None,
    reparto_id: Optional[str] = None,
    operatore_id: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
    error: Optional[str] = None,
    success: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    anno_val = safe_int(anno)
    fornitore_id_val = safe_int(fornitore_id)
    reparto_id_val = safe_int(reparto_id)
    operatore_id_val = safe_int(operatore_id)

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    current_year = datetime.now().year
    if anno_val:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno_val

    if fornitore_id_val:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id_val

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id_val:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id_val

    if operatore_id_val:
        where_clauses.append("(c.dec_user_id = :operatore_id OR c.creato_da_id = :operatore_id)")
        params["operatore_id"] = operatore_id_val

    if q and q.strip():
        where_clauses.append("""(
            c.titolo LIKE :q 
            OR c.codice_contratto LIKE :q 
            OR c.cig LIKE :q 
            OR c.cup LIKE :q 
            OR f.ragione_sociale LIKE :q
            OR u_dec.nome LIKE :q
            OR u_dec.cognome LIKE :q
            OR u_creatore.nome LIKE :q
            OR u_creatore.cognome LIKE :q
        )""")
        params["q"] = f"%{q.strip()}%"

    where_sql = " AND ".join(where_clauses)

    order_by_sql, effective_sort_by, effective_sort_dir = get_contratti_order_by(sort_by, sort_dir)

    with engine.connect() as conn:
        # Elenco contratti con totali moduli calcolati
        contratti = conn.execute(text(f"""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.email_generale AS fornitore_email,
                   f.telefono_generale AS fornitore_telefono,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome,
                   u_dec.email AS dec_email,
                   u_creatore.nome AS creatore_nome,
                   u_creatore.cognome AS creatore_cognome,
                   (SELECT COUNT(*) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id) AS cnt_moduli,
                   COALESCE((SELECT SUM(cm.costo) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_costo,
                   COALESCE((SELECT SUM(cm.giornate) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_giornate
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            LEFT JOIN users u_creatore ON c.creato_da_id = u_creatore.user_id
            WHERE {where_sql}
            ORDER BY {order_by_sql}
        """), params).mappings().all()

        # Liste di supporto per i filtri
        fornitori = conn.execute(text("SELECT fornitore_id, ragione_sociale FROM fornitori WHERE attivo = 1 ORDER BY ragione_sociale")).mappings().all()
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        operatori = conn.execute(text("""
            SELECT DISTINCT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
            FROM users u
            JOIN operatori_tag ot ON u.user_id = ot.user_id
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE UPPER(t.nome) = 'DEC' AND u.attivo = 1
            ORDER BY u.cognome, u.nome
        """)).mappings().all()
        anni_disponibili = conn.execute(text("SELECT DISTINCT anno FROM contratti ORDER BY anno DESC")).scalars().all()
        if not anni_disponibili:
            anni_disponibili = [current_year]
        elif current_year not in anni_disponibili:
            anni_disponibili = sorted(list(set(list(anni_disponibili) + [current_year])), reverse=True)

        # Calcolo permessi di modifica per ciascun contratto in lista
        if user.get("ruolo") in ("admin", "amministrativo"):
            editable_ids_set = None
        else:
            uid = user["id"]
            rep_id = user.get("reparto_id")
            query_editable = """
                SELECT DISTINCT c.contratto_id
                FROM contratti c
                LEFT JOIN contratti_moduli cm ON c.contratto_id = cm.contratto_id
                LEFT JOIN servizi s ON cm.servizio_id = s.servizio_id
                WHERE c.creato_da_id = :uid
                   OR c.dec_user_id = :uid
                   OR cm.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid)
            """
            params_editable = {"uid": uid}
            if user.get("ruolo") == "responsabile" and rep_id:
                query_editable += """
                   OR c.reparto_id = :rep_id
                   OR c.creato_da_id IN (SELECT user_id FROM users WHERE reparto_id = :rep_id)
                   OR s.reparto_id = :rep_id
                """
                params_editable["rep_id"] = rep_id

            editable_ids_set = set(conn.execute(text(query_editable), params_editable).scalars().all())

        contratti_augmented = []
        for c_item in contratti:
            c_dict = dict(c_item)
            c_dict["can_edit"] = True if (user.get("ruolo") in ("admin", "amministrativo") or (editable_ids_set is not None and c_dict["contratto_id"] in editable_ids_set)) else False
            aliquota = float(c_dict.get("aliquota_iva") if c_dict.get("aliquota_iva") is not None else 22.0)
            c_costo = float(c_dict.get("totale_costo") or 0.0)
            c_dict["aliquota_iva"] = aliquota
            c_dict["totale_costo_iva"] = round(c_costo * (1.0 + aliquota / 100.0), 2)
            contratti_augmented.append(c_dict)

        # Calcolo KPI per la selezione
        totale_spesa = sum(c["totale_costo"] for c in contratti)
        totale_spesa_iva = sum(c["totale_costo_iva"] for c in contratti_augmented)
        totale_attivi = sum(1 for c in contratti if c["stato"] in ("attivo", "perfezionato"))
        totale_giornate = sum(c["totale_giornate"] for c in contratti)

    is_dec = user_has_tag_dec(user)

    return templates.TemplateResponse(r, "contratti_list.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "is_dec": is_dec,
        "contratti": contratti_augmented,
        "fornitori": fornitori,
        "reparti": reparti,
        "operatori": operatori,
        "anni_disponibili": anni_disponibili,
        "anno_selezionato": anno_val,
        "fornitore_selezionato": fornitore_id_val,
        "stato_selezionato": stato or "",
        "reparto_selezionato": reparto_id_val,
        "operatore_selezionato": operatore_id_val,
        "q": q or "",
        "totale_spesa": totale_spesa,
        "totale_spesa_iva": totale_spesa_iva,
        "totale_attivi": totale_attivi,
        "totale_giornate": totale_giornate,
        "sort_by": effective_sort_by,
        "sort_dir": effective_sort_dir,
        "error": error,
        "success": success
    })


@router.get("/contratti/export/csv")
@router.get("/contratto/export/csv")
@router.get("/contratti/csv")
def contratti_export_csv(
    r: Request,
    anno: Optional[str] = None,
    fornitore_id: Optional[str] = None,
    stato: Optional[str] = None,
    reparto_id: Optional[str] = None,
    operatore_id: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    anno_val = safe_int(anno)
    fornitore_id_val = safe_int(fornitore_id)
    reparto_id_val = safe_int(reparto_id)
    operatore_id_val = safe_int(operatore_id)

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    if anno_val:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno_val

    if fornitore_id_val:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id_val

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id_val:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id_val

    if operatore_id_val:
        where_clauses.append("(c.dec_user_id = :operatore_id OR c.creato_da_id = :operatore_id)")
        params["operatore_id"] = operatore_id_val

    if q and q.strip():
        where_clauses.append("""(
            c.titolo LIKE :q 
            OR c.codice_contratto LIKE :q 
            OR c.cig LIKE :q 
            OR c.cup LIKE :q 
            OR f.ragione_sociale LIKE :q
            OR u_dec.nome LIKE :q
            OR u_dec.cognome LIKE :q
            OR u_creatore.nome LIKE :q
            OR u_creatore.cognome LIKE :q
        )""")
        params["q"] = f"%{q.strip()}%"

    where_sql = " AND ".join(where_clauses)

    order_by_sql, _, _ = get_contratti_order_by(sort_by, sort_dir)

    with engine.connect() as conn:
        contratti = conn.execute(text(f"""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.partita_iva AS fornitore_piva,
                   f.email_generale AS fornitore_email,
                   f.telefono_generale AS fornitore_telefono,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome,
                   u_dec.email AS dec_email,
                   u_creatore.nome AS creatore_nome,
                   u_creatore.cognome AS creatore_cognome,
                   (SELECT COUNT(*) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id) AS cnt_moduli,
                   COALESCE((SELECT SUM(cm.costo) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_costo,
                   COALESCE((SELECT SUM(cm.giornate) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_giornate
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            LEFT JOIN users u_creatore ON c.creato_da_id = u_creatore.user_id
            WHERE {where_sql}
            ORDER BY {order_by_sql}
        """), params).mappings().all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        "ID",
        "Anno",
        "Titolo Contratto",
        "Codice Contratto",
        "CIG",
        "CUP",
        "Fornitore",
        "P.IVA Fornitore",
        "Email Fornitore",
        "Telefono Fornitore",
        "Reparto",
        "DEC (Direttore Esecuzione)",
        "Email DEC",
        "Inserito Da",
        "Data Inizio",
        "Data Fine",
        "Stato",
        "N. Moduli / Voci",
        "Totale Giornate",
        "Totale Importo [IVA escl.] (€)",
        "Aliquota IVA (%)",
        "Totale IVA (€)",
        "Totale Importo [IVA incl.] (€)",
        "Descrizione",
        "Data Creazione"
    ])

    for c in contratti:
        dec_full = f"{c['dec_cognome'] or ''} {c['dec_nome'] or ''}".strip()
        creatore_full = f"{c['creatore_cognome'] or ''} {c['creatore_nome'] or ''}".strip()
        costo_float = float(c['totale_costo'] or 0.0)
        aliquota = float(c['aliquota_iva'] if (c.get('aliquota_iva') is not None) else 22.0)
        tot_iva = round(costo_float * (aliquota / 100.0), 2)
        tot_costo_iva = round(costo_float + tot_iva, 2)

        costo_val = f"{costo_float:.2f}".replace('.', ',')
        aliquota_str = f"{aliquota:.1f}".replace('.', ',') if (aliquota % 1 != 0) else f"{int(aliquota)}"
        iva_val = f"{tot_iva:.2f}".replace('.', ',')
        costo_iva_val = f"{tot_costo_iva:.2f}".replace('.', ',')
        giornate_val = f"{c['totale_giornate']:.1f}".replace('.', ',') if c['totale_giornate'] else "0"

        writer.writerow([
            c["contratto_id"],
            c["anno"],
            c["titolo"] or "",
            c["codice_contratto"] or "",
            c["cig"] or "",
            c["cup"] or "",
            c["fornitore_nome"] or "",
            c["fornitore_piva"] or "",
            c["fornitore_email"] or "",
            c["fornitore_telefono"] or "",
            c["reparto_nome"] or "",
            dec_full,
            c["dec_email"] or "",
            creatore_full,
            c["data_inizio"] or "",
            c["data_fine"] or "",
            c["stato"] or "",
            c["cnt_moduli"] or 0,
            giornate_val,
            costo_val,
            aliquota_str,
            iva_val,
            costo_iva_val,
            (c["descrizione"] or "").replace("\r\n", " ").replace("\n", " "),
            c["creato_il"] or ""
        ])

    today_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"contratti_fornitura_{today_str}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/contratti/export/excel")
@router.get("/contratto/export/excel")
@router.get("/contratti/excel")
def contratti_export_excel(
    r: Request,
    anno: Optional[str] = None,
    fornitore_id: Optional[str] = None,
    stato: Optional[str] = None,
    reparto_id: Optional[str] = None,
    operatore_id: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    anno_val = safe_int(anno)
    fornitore_id_val = safe_int(fornitore_id)
    reparto_id_val = safe_int(reparto_id)
    operatore_id_val = safe_int(operatore_id)

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    if anno_val:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno_val

    if fornitore_id_val:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id_val

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id_val:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id_val

    if operatore_id_val:
        where_clauses.append("(c.dec_user_id = :operatore_id OR c.creato_da_id = :operatore_id)")
        params["operatore_id"] = operatore_id_val

    if q and q.strip():
        where_clauses.append("""(
            c.titolo LIKE :q 
            OR c.codice_contratto LIKE :q 
            OR c.cig LIKE :q 
            OR c.cup LIKE :q 
            OR f.ragione_sociale LIKE :q
            OR u_dec.nome LIKE :q
            OR u_dec.cognome LIKE :q
            OR u_creatore.nome LIKE :q
            OR u_creatore.cognome LIKE :q
        )""")
        params["q"] = f"%{q.strip()}%"

    where_sql = " AND ".join(where_clauses)
    order_by_sql, _, _ = get_contratti_order_by(sort_by, sort_dir)

    with engine.connect() as conn:
        contratti = conn.execute(text(f"""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.partita_iva AS fornitore_piva,
                   f.email_generale AS fornitore_email,
                   f.telefono_generale AS fornitore_telefono,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome,
                   u_dec.email AS dec_email,
                   u_creatore.nome AS creatore_nome,
                   u_creatore.cognome AS creatore_cognome,
                   (SELECT COUNT(*) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id) AS cnt_moduli,
                   COALESCE((SELECT SUM(cm.costo) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_costo,
                   COALESCE((SELECT SUM(cm.giornate) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_giornate
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            LEFT JOIN users u_creatore ON c.creato_da_id = u_creatore.user_id
            WHERE {where_sql}
            ORDER BY {order_by_sql}
        """), params).mappings().all()

    # Creazione file Excel professionale (.xlsx) con openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contratti Fornitura"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_side = Side(border_style="thin", color="D9D9D9")
    border_thin = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")

    font_regular = Font(name="Calibri", size=10)
    font_bold = Font(name="Calibri", size=10, bold=True)

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    headers_def = [
        ("ID", 8, align_center),
        ("Anno", 8, align_center),
        ("Titolo Contratto", 35, align_left),
        ("Codice Contratto", 18, align_center),
        ("CIG", 14, align_center),
        ("CUP", 14, align_center),
        ("Fornitore", 30, align_left),
        ("P.IVA Fornitore", 16, align_center),
        ("Email Fornitore", 25, align_left),
        ("Telefono Fornitore", 18, align_left),
        ("Reparto", 20, align_left),
        ("DEC (Direttore Esecuzione)", 25, align_left),
        ("Email DEC", 25, align_left),
        ("Inserito Da", 22, align_left),
        ("Data Inizio", 12, align_center),
        ("Data Fine", 12, align_center),
        ("Stato", 14, align_center),
        ("N. Moduli / Voci", 14, align_center),
        ("Totale Giornate", 15, align_right),
        ("Totale Importo [IVA escl.] (€)", 24, align_right),
        ("Aliquota IVA (%)", 15, align_center),
        ("Totale IVA (€)", 16, align_right),
        ("Totale Importo [IVA incl.] (€)", 24, align_right),
        ("Descrizione", 40, align_left),
        ("Data Creazione", 18, align_center),
    ]

    ws.row_dimensions[1].height = 28
    for col_idx, (h_title, min_w, _) in enumerate(headers_def, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h_title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border_thin

    row_idx = 2
    tot_moduli_sum = 0
    tot_giornate_sum = 0.0
    tot_costo_sum = 0.0
    tot_iva_sum = 0.0
    tot_costo_iva_sum = 0.0

    for c in contratti:
        dec_full = f"{c['dec_cognome'] or ''} {c['dec_nome'] or ''}".strip()
        creatore_full = f"{c['creatore_cognome'] or ''} {c['creatore_nome'] or ''}".strip()
        costo = float(c['totale_costo'] or 0.0)
        giornate = float(c['totale_giornate'] or 0.0)
        moduli_cnt = int(c['cnt_moduli'] or 0)
        aliquota = float(c['aliquota_iva'] if (c.get('aliquota_iva') is not None) else 22.0)
        iva_val = round(costo * (aliquota / 100.0), 2)
        costo_iva = round(costo + iva_val, 2)

        tot_moduli_sum += moduli_cnt
        tot_giornate_sum += giornate
        tot_costo_sum += costo
        tot_iva_sum += iva_val
        tot_costo_iva_sum += costo_iva

        row_vals = [
            c["contratto_id"],
            c["anno"],
            c["titolo"] or "",
            c["codice_contratto"] or "",
            c["cig"] or "",
            c["cup"] or "",
            c["fornitore_nome"] or "",
            c["fornitore_piva"] or "",
            c["fornitore_email"] or "",
            c["fornitore_telefono"] or "",
            c["reparto_nome"] or "",
            dec_full,
            c["dec_email"] or "",
            creatore_full,
            c["data_inizio"] or "",
            c["data_fine"] or "",
            (c["stato"] or "").upper(),
            moduli_cnt,
            giornate,
            costo,
            aliquota,
            iva_val,
            costo_iva,
            (c["descrizione"] or "").replace("\r\n", " ").replace("\n", " "),
            c["creato_il"] or ""
        ]

        ws.row_dimensions[row_idx].height = 20
        is_even = (row_idx % 2 == 0)

        for col_idx, val in enumerate(row_vals, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = font_regular
            cell.border = border_thin
            cell.alignment = headers_def[col_idx - 1][2]
            if is_even:
                cell.fill = zebra_fill

            if col_idx in (19,):
                cell.number_format = '#,##0.0'
            elif col_idx in (20, 22, 23):
                cell.number_format = '#,##0.00 €'
            elif col_idx in (21,):
                cell.number_format = '0"%"'
            elif col_idx in (1, 2, 18):
                cell.number_format = '#,##0'

        row_idx += 1

    # Riga totali riepilogativa
    ws.row_dimensions[row_idx].height = 24
    double_bottom = Border(
        left=thin_side, right=thin_side,
        top=Side(border_style="thin", color="000000"),
        bottom=Side(border_style="double", color="000000")
    )
    summary_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    for col_idx in range(1, len(headers_def) + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.font = font_bold
        cell.border = double_bottom
        cell.fill = summary_fill

    ws.cell(row=row_idx, column=3, value="TOTALE COMPLESSIVO").alignment = align_left
    cell_mod = ws.cell(row=row_idx, column=18, value=tot_moduli_sum)
    cell_mod.alignment = align_center
    cell_mod.number_format = '#,##0'

    cell_gg = ws.cell(row=row_idx, column=19, value=tot_giornate_sum)
    cell_gg.alignment = align_right
    cell_gg.number_format = '#,##0.0'

    cell_c = ws.cell(row=row_idx, column=20, value=tot_costo_sum)
    cell_c.alignment = align_right
    cell_c.number_format = '#,##0.00 €'

    cell_iva = ws.cell(row=row_idx, column=22, value=tot_iva_sum)
    cell_iva.alignment = align_right
    cell_iva.number_format = '#,##0.00 €'

    cell_c_iva = ws.cell(row=row_idx, column=23, value=tot_costo_iva_sum)
    cell_c_iva.alignment = align_right
    cell_c_iva.number_format = '#,##0.00 €'

    for col_idx, (_, min_w, _) in enumerate(headers_def, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min_w

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    today_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"contratti_fornitura_{today_str}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratto/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratto/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratti/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratti/report-economico", response_class=HTMLResponse)
@router.get("/contratto/report-economico", response_class=HTMLResponse)
def contratti_riepilogo_economico(
    r: Request,
    anno: Optional[str] = None,
    fornitore_id: Optional[str] = None,
    reparto_id: Optional[str] = None,
    stato: Optional[str] = None,
    operatore_id: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    current_year = datetime.now().year
    
    anno_val = safe_int(anno)
    fornitore_id_val = safe_int(fornitore_id)
    reparto_id_val = safe_int(reparto_id)
    operatore_id_val = safe_int(operatore_id)

    # Se l'anno non è specificato nei parametri (primo accesso, anno is None), impostiamo l'anno corrente di default.
    # Se il parametro anno è 0 o stringa vuota, significa visualizzare "Tutti gli anni".
    if anno is None:
        anno_filtro = current_year
    else:
        anno_filtro = anno_val

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    if anno_filtro and anno_filtro > 0:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno_filtro

    if fornitore_id_val:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id_val

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id_val:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id_val

    if operatore_id_val:
        where_clauses.append("(c.dec_user_id = :operatore_id OR c.creato_da_id = :operatore_id)")
        params["operatore_id"] = operatore_id_val

    where_sql = " AND ".join(where_clauses)


    with engine.connect() as conn:
        # Contratti filtrati
        contratti_raw = conn.execute(text(f"""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.partita_iva AS fornitore_piva,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            WHERE {where_sql}
            ORDER BY c.anno DESC, rep.nome ASC, f.ragione_sociale ASC, c.contratto_id DESC
        """), params).mappings().all()

        contratti_ids = [c["contratto_id"] for c in contratti_raw]

        # Moduli dettagliati
        moduli_per_contratto = {}
        if contratti_ids:
            from sqlalchemy import bindparam
            stmt_moduli = text("""
                SELECT cm.*, s.descrizione AS servizio_nome
                FROM contratti_moduli cm
                LEFT JOIN servizi s ON cm.servizio_id = s.servizio_id
                WHERE cm.contratto_id IN :cids
                ORDER BY cm.ordine ASC, cm.modulo_id ASC
            """).bindparams(bindparam("cids", expanding=True))
            moduli_rows = conn.execute(stmt_moduli, {"cids": contratti_ids}).mappings().all()
            for m in moduli_rows:
                cid = m["contratto_id"]
                if cid not in moduli_per_contratto:
                    moduli_per_contratto[cid] = []
                moduli_per_contratto[cid].append(dict(m))

        # Assembliamo la lista contratti con i moduli e calcoli subtotali
        contratti_list = []
        totale_costo_generale = 0.0
        totale_giornate_generale = 0.0
        totale_moduli_generale = 0

        # Mappe di raggruppamento per fornitori e reparti
        agg_fornitori = {}
        agg_reparti = {}
        agg_stati = {
            "attivo": {"count": 0, "totale": 0.0},
            "perfezionato": {"count": 0, "totale": 0.0},
            "in_trattativa": {"count": 0, "totale": 0.0},
            "in_definizione": {"count": 0, "totale": 0.0},
            "scaduto": {"count": 0, "totale": 0.0},
            "concluso": {"count": 0, "totale": 0.0}
        }

        for c_row in contratti_raw:
            cid = c_row["contratto_id"]
            c_dict = dict(c_row)
            mods = moduli_per_contratto.get(cid, [])
            c_costo = sum(float(m.get("costo") or 0.0) for m in mods)
            c_giornate = sum(float(m.get("giornate") or 0.0) for m in mods)
            aliquota = float(c_dict.get("aliquota_iva") if c_dict.get("aliquota_iva") is not None else 22.0)
            for m in mods:
                m["costo_iva"] = round(float(m.get("costo") or 0.0) * (1.0 + aliquota / 100.0), 2)
            
            c_dict["moduli"] = mods
            c_dict["aliquota_iva"] = aliquota
            c_dict["totale_costo"] = c_costo
            c_dict["totale_costo_iva"] = round(c_costo * (1.0 + aliquota / 100.0), 2)
            c_dict["totale_giornate"] = c_giornate
            c_dict["cnt_moduli"] = len(mods)
            contratti_list.append(c_dict)

            totale_costo_generale += c_costo
            totale_giornate_generale += c_giornate
            totale_moduli_generale += len(mods)

            # Raggruppamento fornitore
            fid = c_dict["fornitore_id"]
            fnome = c_dict["fornitore_nome"]
            if fid not in agg_fornitori:
                agg_fornitori[fid] = {
                    "fornitore_id": fid,
                    "fornitore_nome": fnome,
                    "totale_costo": 0.0,
                    "totale_giornate": 0.0,
                    "cnt_contratti": 0
                }
            agg_fornitori[fid]["totale_costo"] += c_costo
            agg_fornitori[fid]["totale_giornate"] += c_giornate
            agg_fornitori[fid]["cnt_contratti"] += 1

            # Raggruppamento reparto
            rid = c_dict.get("reparto_id") or 0
            rnome = c_dict.get("reparto_nome") or "Generale / Nessun Reparto"
            if rid not in agg_reparti:
                agg_reparti[rid] = {
                    "reparto_id": rid,
                    "reparto_nome": rnome,
                    "totale_costo": 0.0,
                    "totale_giornate": 0.0,
                    "cnt_contratti": 0
                }
            agg_reparti[rid]["totale_costo"] += c_costo
            agg_reparti[rid]["totale_giornate"] += c_giornate
            agg_reparti[rid]["cnt_contratti"] += 1

            # Raggruppamento stato
            st = c_dict.get("stato", "attivo")
            if st in agg_stati:
                agg_stati[st]["count"] += 1
                agg_stati[st]["totale"] += c_costo

        # Calcolo percentuali per fornitori e reparti
        fornitori_agg_list = list(agg_fornitori.values())
        for f in fornitori_agg_list:
            f["percentuale"] = (f["totale_costo"] / totale_costo_generale * 100) if totale_costo_generale > 0 else 0.0
        fornitori_agg_list.sort(key=lambda x: x["totale_costo"], reverse=True)

        reparti_agg_list = list(agg_reparti.values())
        for rep in reparti_agg_list:
            rep["percentuale"] = (rep["totale_costo"] / totale_costo_generale * 100) if totale_costo_generale > 0 else 0.0
        reparti_agg_list.sort(key=lambda x: x["totale_costo"], reverse=True)

        # Liste per i filtri
        fornitori = conn.execute(text("SELECT fornitore_id, ragione_sociale FROM fornitori WHERE attivo = 1 ORDER BY ragione_sociale")).mappings().all()
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        operatori = conn.execute(text("""
            SELECT DISTINCT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
            FROM users u
            JOIN operatori_tag ot ON u.user_id = ot.user_id
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE UPPER(t.nome) = 'DEC' AND u.attivo = 1
            ORDER BY u.cognome, u.nome
        """)).mappings().all()
        anni_disponibili = conn.execute(text("SELECT DISTINCT anno FROM contratti ORDER BY anno DESC")).scalars().all()
        if not anni_disponibili:
            anni_disponibili = [current_year]
        elif current_year not in anni_disponibili:
            anni_disponibili = sorted(list(set(list(anni_disponibili) + [current_year])), reverse=True)

    return templates.TemplateResponse(r, "contratti_riepilogo_economico.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "contratti": contratti_list,
        "totale_costo_generale": totale_costo_generale,
        "totale_giornate_generale": totale_giornate_generale,
        "totale_contratti": len(contratti_list),
        "totale_moduli_generale": totale_moduli_generale,
        "fornitori_agg": fornitori_agg_list,
        "reparti_agg": reparti_agg_list,
        "stati_agg": agg_stati,
        "fornitori": fornitori,
        "reparti": reparti,
        "operatori": operatori,
        "anni_disponibili": anni_disponibili,
        "anno_selezionato": anno_filtro,
        "fornitore_selezionato": fornitore_id_val,
        "reparto_selezionato": reparto_id_val,
        "operatore_selezionato": operatore_id_val,
        "stato_selezionato": stato or "",
        "current_year": current_year
    })


@router.get("/contratti/fornitori")
def redirect_contratti_fornitori():
    return RedirectResponse(url="/fornitori", status_code=307)

@router.get("/contratti/admin/fornitori")
def redirect_contratti_admin_fornitori():
    return RedirectResponse(url="/admin/fornitori", status_code=307)

@router.post("/contratti/fornitore/nuovo")
@router.post("/contratto/fornitore/nuovo")
@router.post("/contratti/fornitori/nuovo")
def contratti_crea_fornitore(
    r: Request,
    ragione_sociale: str = Form(...),
    partita_iva: str = Form(""),
    codice_fiscale: str = Form(""),
    descrizione: str = Form(""),
    indirizzo: str = Form(""),
    sito_web: str = Form(""),
    email_generale: str = Form(""),
    telefono_generale: str = Form(""),
    pec: str = Form(""),
    note: str = Form(""),
    redirect_to: Optional[str] = Form(None)
):
    from fornitori import operatore_crea_fornitore
    return operatore_crea_fornitore(
        r=r,
        ragione_sociale=ragione_sociale,
        partita_iva=partita_iva,
        codice_fiscale=codice_fiscale,
        descrizione=descrizione,
        indirizzo=indirizzo,
        sito_web=sito_web,
        email_generale=email_generale,
        telefono_generale=telefono_generale,
        pec=pec,
        note=note,
        redirect_to=redirect_to
    )


@router.get("/contratto/nuovo", response_class=HTMLResponse)
@router.get("/contratti/nuovo", response_class=HTMLResponse)
@router.get("/contratti/contratto/nuovo", response_class=HTMLResponse)
def contratto_nuovo_form(r: Request, error: Optional[str] = None):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as conn:
        fornitori = conn.execute(text("SELECT fornitore_id, ragione_sociale FROM fornitori WHERE attivo = 1 ORDER BY ragione_sociale")).mappings().all()
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        servizi = conn.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi ORDER BY descrizione")).mappings().all()

        # Operatori con tag DEC (o tutti gli operatori attivi se admin)
        dec_operators = conn.execute(text("""
            SELECT DISTINCT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
            FROM users u
            JOIN operatori_tag ot ON u.user_id = ot.user_id
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE UPPER(t.nome) = 'DEC' AND u.attivo = 1
            ORDER BY u.cognome, u.nome
        """)).mappings().all()

        # Se nessun DEC trovato con tag, fallback sugli utenti per non bloccare la creazione
        if not dec_operators:
            dec_operators = conn.execute(text("""
                SELECT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
                FROM users u
                LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
                WHERE u.attivo = 1
                ORDER BY u.cognome, u.nome
            """)).mappings().all()

    current_year = datetime.now().year

    return templates.TemplateResponse(r, "contratto_form.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "contratto": None,
        "fornitori": fornitori,
        "reparti": reparti,
        "servizi": servizi,
        "dec_operators": dec_operators,
        "current_year": current_year,
        "error": error
    })


@router.post("/contratto/nuovo")
@router.post("/contratti/nuovo")
@router.post("/contratti/contratto/nuovo")
def contratto_nuovo_save(
    r: Request,
    titolo: str = Form(...),
    fornitore_id: int = Form(...),
    anno: int = Form(...),
    codice_contratto: Optional[str] = Form(None),
    cig: Optional[str] = Form(None),
    cup: Optional[str] = Form(None),
    aliquota_iva: Optional[str] = Form("22.0"),
    data_inizio: Optional[str] = Form(None),
    data_fine: Optional[str] = Form(None),
    stato: str = Form("attivo"),
    dec_user_id: Optional[str] = Form(None),
    reparto_id: Optional[str] = Form(None),
    descrizione: Optional[str] = Form(None),
    # Modulo iniziale opzionale
    modulo_descrizione: Optional[str] = Form(None),
    modulo_servizio_id: Optional[str] = Form(None),
    modulo_costo: Optional[str] = Form(None),
    modulo_giornate: Optional[str] = Form(None),
    modulo_costo_giornaliero: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url="/contratto/nuovo?error=titolo_obbligatorio", status_code=303)

    dec_user_id_val = safe_int(dec_user_id)
    reparto_id_val = safe_int(reparto_id)
    modulo_servizio_id_val = safe_int(modulo_servizio_id)
    modulo_costo_val = safe_float(modulo_costo)
    modulo_giornate_val = safe_float(modulo_giornate)
    modulo_costo_giornaliero_val = safe_float(modulo_costo_giornaliero)
    aliquota_iva_val = safe_float(aliquota_iva)
    if aliquota_iva_val is None:
        aliquota_iva_val = 22.0

    # Se l'utente è operatore DEC e non ha specificato il DEC, assegniamo lui stesso
    if not dec_user_id_val and user_has_tag_dec(user):
        dec_user_id_val = user["id"]

    # Se non è specificato il reparto, usiamo quello dell'utente o del DEC
    if not reparto_id_val and user.get("reparto_id"):
        reparto_id_val = user.get("reparto_id")

    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO contratti (
                titolo, codice_contratto, cig, cup, fornitore_id, anno,
                aliquota_iva, data_inizio, data_fine, stato, dec_user_id, reparto_id,
                descrizione, creato_da_id, creato_il
            ) VALUES (
                :titolo, :codice, :cig, :cup, :fornitore_id, :anno,
                :aliquota_iva, :data_inizio, :data_fine, :stato, :dec_user_id, :reparto_id,
                :descrizione, :creato_da_id, :creato_il
            )
        """), {
            "titolo": titolo,
            "codice": codice_contratto.strip() if codice_contratto else None,
            "cig": cig.strip() if cig else None,
            "cup": cup.strip() if cup else None,
            "fornitore_id": fornitore_id,
            "anno": anno,
            "aliquota_iva": aliquota_iva_val,
            "data_inizio": data_inizio.strip() if data_inizio else None,
            "data_fine": data_fine.strip() if data_fine else None,
            "stato": stato,
            "dec_user_id": dec_user_id_val,
            "reparto_id": reparto_id_val,
            "descrizione": descrizione.strip() if descrizione else None,
            "creato_da_id": user["id"],
            "creato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        if DB_DRIVER.startswith("sqlite"):
            contratto_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
        elif DB_DRIVER.startswith("mysql"):
            contratto_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        else:
            contratto_id = conn.execute(text("SELECT LASTVAL()")).scalar()

        # Inserimento modulo iniziale se specificato
        if modulo_descrizione and modulo_descrizione.strip():
            calcolato_costo = modulo_costo_val or 0.0
            if (not modulo_costo_val or modulo_costo_val == 0) and modulo_giornate_val and modulo_costo_giornaliero_val:
                calcolato_costo = float(modulo_giornate_val) * float(modulo_costo_giornaliero_val)

            conn.execute(text("""
                INSERT INTO contratti_moduli (
                    contratto_id, servizio_id, descrizione, costo,
                    giornate, costo_giornaliero, creato_il
                ) VALUES (
                    :cid, :sid, :desc, :costo, :giornate, :costo_gg, :creato_il
                )
            """), {
                "cid": contratto_id,
                "sid": modulo_servizio_id_val if modulo_servizio_id_val else None,
                "desc": modulo_descrizione.strip(),
                "costo": calcolato_costo,
                "giornate": modulo_giornate_val if modulo_giornate_val else None,
                "costo_gg": modulo_costo_giornaliero_val if modulo_costo_giornaliero_val else None,
                "creato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=creato", status_code=303)


@router.get("/contratto/{contratto_id}", response_class=HTMLResponse)
@router.get("/contratti/{contratto_id}", response_class=HTMLResponse)
@router.get("/contratti/contratto/{contratto_id}", response_class=HTMLResponse)
def contratto_detail(
    r: Request,
    contratto_id: int,
    error: Optional[str] = None,
    success: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as conn:
        contratto = conn.execute(text("""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.partita_iva AS fornitore_piva,
                   f.codice_fiscale AS fornitore_cf,
                   f.email_generale AS fornitore_email,
                   f.telefono_generale AS fornitore_telefono,
                   f.pec AS fornitore_pec,
                   f.sito_web AS fornitore_sito,
                   f.indirizzo AS fornitore_indirizzo,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome,
                   u_dec.email AS dec_email,
                   u_cr.nome AS creatore_nome,
                   u_cr.cognome AS creatore_cognome
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            LEFT JOIN users u_cr ON c.creato_da_id = u_cr.user_id
            WHERE c.contratto_id = :cid
        """), {"cid": contratto_id}).mappings().first()

        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        can_edit = can_manage_single_contratto(user, dict(contratto), conn=conn)

        moduli = conn.execute(text("""
            SELECT cm.*, s.descrizione AS servizio_nome, s.reparto_id AS servizio_reparto_id
            FROM contratti_moduli cm
            LEFT JOIN servizi s ON cm.servizio_id = s.servizio_id
            WHERE cm.contratto_id = :cid
            ORDER BY cm.ordine ASC, cm.modulo_id ASC
        """), {"cid": contratto_id}).mappings().all()

        servizi = conn.execute(text("SELECT servizio_id, descrizione FROM servizi ORDER BY descrizione")).mappings().all()

        # Contatti di escalation del fornitore associato
        contatti_fornitore = conn.execute(text("""
            SELECT * FROM fornitori_contatti WHERE fornitore_id = :fid ORDER BY ordine ASC, contatto_id ASC
        """), {"fid": contratto["fornitore_id"]}).mappings().all()

        financials = get_contratto_financials(conn, contratto_id)

        ordini_rows = conn.execute(text("""
            SELECT co.*,
                   u.nome AS creatore_nome, u.cognome AS creatore_cognome,
                   (SELECT COUNT(*) FROM ordini_attivita oa WHERE oa.ordine_id = co.ordine_id AND (oa.stato IS NULL OR oa.stato != 'annullata')) AS cnt_attivita,
                   COALESCE((SELECT SUM(costo) FROM ordini_attivita oa WHERE oa.ordine_id = co.ordine_id AND (oa.stato IS NULL OR oa.stato != 'annullata')), 0.0) AS totale_costo_attivita,
                   COALESCE((SELECT SUM(giornate) FROM ordini_attivita oa WHERE oa.ordine_id = co.ordine_id AND (oa.stato IS NULL OR oa.stato != 'annullata')), 0.0) AS totale_giornate_attivita
            FROM contratti_ordini co
            LEFT JOIN users u ON co.creato_da_id = u.user_id
            WHERE co.contratto_id = :cid
            ORDER BY co.ordine_id ASC
        """), {"cid": contratto_id}).mappings().all()

        ordini = []
        for o in ordini_rows:
            od = dict(o)
            imp = od.get("importo") or 0.0
            tot_att = od.get("totale_costo_attivita") or 0.0
            od["residuo_costo"] = imp - tot_att
            od["perc_consumata"] = round((tot_att / imp * 100.0), 1) if imp > 0 else 0.0
            od["is_esaurito"] = (od["residuo_costo"] <= 0.009 and imp > 0)
            ordini.append(od)

    aliquota_iva = float(contratto["aliquota_iva"] if (contratto and contratto.get("aliquota_iva") is not None) else 22.0)
    iva_molt = 1.0 + (aliquota_iva / 100.0)

    moduli_enriched = []
    for m in moduli:
        md = dict(m)
        c_val = float(md.get("costo") or 0.0)
        md["costo_iva"] = round(c_val * iva_molt, 2)
        moduli_enriched.append(md)
    moduli = moduli_enriched

    totale_costo = sum(m["costo"] for m in moduli)
    totale_costo_iva = round(totale_costo * iva_molt, 2)
    totale_giornate = sum((m["giornate"] or 0.0) for m in moduli)
    is_dec = user_has_tag_dec(user)

    return templates.TemplateResponse(r, "contratto_detail.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "is_dec": is_dec,
        "can_edit": can_edit,
        "contratto": contratto,
        "moduli": moduli,
        "ordini": ordini,
        "financials": financials,
        "servizi": servizi,
        "contatti_fornitore": contatti_fornitore,
        "totale_costo": totale_costo,
        "totale_costo_iva": totale_costo_iva,
        "aliquota_iva": aliquota_iva,
        "totale_giornate": totale_giornate,
        "error": error,
        "success": success
    })


@router.get("/contratto/{contratto_id}/modifica", response_class=HTMLResponse)
@router.get("/contratti/{contratto_id}/modifica", response_class=HTMLResponse)
@router.get("/contratti/contratto/{contratto_id}/modifica", response_class=HTMLResponse)
def contratto_edit_form(r: Request, contratto_id: int, error: Optional[str] = None):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        fornitori = conn.execute(text("SELECT fornitore_id, ragione_sociale FROM fornitori WHERE attivo = 1 ORDER BY ragione_sociale")).mappings().all()
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        servizi = conn.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi ORDER BY descrizione")).mappings().all()

        dec_operators = conn.execute(text("""
            SELECT DISTINCT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
            FROM users u
            JOIN operatori_tag ot ON u.user_id = ot.user_id
            JOIN tag_operatori t ON ot.tag_id = t.tag_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            WHERE UPPER(t.nome) = 'DEC' AND u.attivo = 1
            ORDER BY u.cognome, u.nome
        """)).mappings().all()

        if not dec_operators:
            dec_operators = conn.execute(text("""
                SELECT u.user_id, u.nome, u.cognome, u.reparto_id, r.nome AS reparto_nome
                FROM users u
                LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
                WHERE u.attivo = 1
                ORDER BY u.cognome, u.nome
            """)).mappings().all()

    current_year = datetime.now().year

    return templates.TemplateResponse(r, "contratto_form.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "contratto": contratto,
        "fornitori": fornitori,
        "reparti": reparti,
        "servizi": servizi,
        "dec_operators": dec_operators,
        "current_year": current_year,
        "error": error
    })


@router.post("/contratto/{contratto_id}/modifica")
@router.post("/contratti/{contratto_id}/modifica")
@router.post("/contratti/contratto/{contratto_id}/modifica")
def contratto_edit_save(
    r: Request,
    contratto_id: int,
    titolo: str = Form(...),
    fornitore_id: int = Form(...),
    anno: int = Form(...),
    codice_contratto: Optional[str] = Form(None),
    cig: Optional[str] = Form(None),
    cup: Optional[str] = Form(None),
    aliquota_iva: Optional[str] = Form("22.0"),
    data_inizio: Optional[str] = Form(None),
    data_fine: Optional[str] = Form(None),
    stato: str = Form("attivo"),
    dec_user_id: Optional[str] = Form(None),
    reparto_id: Optional[str] = Form(None),
    descrizione: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url=f"/contratto/{contratto_id}/modifica?error=titolo_obbligatorio", status_code=303)

    dec_user_id_val = safe_int(dec_user_id)
    reparto_id_val = safe_int(reparto_id)
    aliquota_iva_val = safe_float(aliquota_iva)
    if aliquota_iva_val is None:
        aliquota_iva_val = 22.0

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("""
            UPDATE contratti SET
                titolo = :titolo,
                fornitore_id = :fornitore_id,
                anno = :anno,
                codice_contratto = :codice,
                cig = :cig,
                cup = :cup,
                aliquota_iva = :aliquota_iva,
                data_inizio = :data_inizio,
                data_fine = :data_fine,
                stato = :stato,
                dec_user_id = :dec_user_id,
                reparto_id = :reparto_id,
                descrizione = :descrizione,
                aggiornato_il = :aggiornato_il
            WHERE contratto_id = :cid
        """), {
            "titolo": titolo,
            "fornitore_id": fornitore_id,
            "anno": anno,
            "codice": codice_contratto.strip() if codice_contratto else None,
            "cig": cig.strip() if cig else None,
            "cup": cup.strip() if cup else None,
            "aliquota_iva": aliquota_iva_val,
            "data_inizio": data_inizio.strip() if data_inizio else None,
            "data_fine": data_fine.strip() if data_fine else None,
            "stato": stato,
            "dec_user_id": dec_user_id_val,
            "reparto_id": reparto_id_val,
            "descrizione": descrizione.strip() if descrizione else None,
            "aggiornato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cid": contratto_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=modificato", status_code=303)


@router.post("/contratto/{contratto_id}/elimina")
@router.post("/contratti/{contratto_id}/elimina")
@router.post("/contratti/contratto/{contratto_id}/elimina")
def contratto_delete(r: Request, contratto_id: int):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("""
            DELETE FROM ordini_attivita 
            WHERE ordine_id IN (SELECT ordine_id FROM contratti_ordini WHERE contratto_id = :cid)
        """), {"cid": contratto_id})
        conn.execute(text("DELETE FROM contratti_ordini WHERE contratto_id = :cid"), {"cid": contratto_id})
        conn.execute(text("DELETE FROM contratti_moduli WHERE contratto_id = :cid"), {"cid": contratto_id})
        conn.execute(text("DELETE FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id})

    return RedirectResponse(url="/contratti?success=eliminato", status_code=303)


@router.post("/contratto/{contratto_id}/duplica")
@router.post("/contratti/{contratto_id}/duplica")
@router.post("/contratti/contratto/{contratto_id}/duplica")
def contratto_duplica(
    r: Request,
    contratto_id: int,
    nuovo_anno: Optional[str] = Form(None),
    nuovo_titolo: Optional[str] = Form(None),
    stato: str = Form("in_definizione")
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        nuovo_anno_val = safe_int(nuovo_anno)
        target_anno = nuovo_anno_val if nuovo_anno_val else (contratto["anno"] + 1)
        
        if nuovo_titolo and nuovo_titolo.strip():
            target_titolo = nuovo_titolo.strip()
        else:
            old_titolo = contratto["titolo"]
            old_anno_str = str(contratto["anno"])
            new_anno_str = str(target_anno)
            if old_anno_str in old_titolo:
                target_titolo = old_titolo.replace(old_anno_str, new_anno_str)
            else:
                target_titolo = f"{old_titolo} ({target_anno})"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        aliquota_orig = float(contratto["aliquota_iva"] if (contratto.get("aliquota_iva") is not None) else 22.0)

        conn.execute(text("""
            INSERT INTO contratti (
                titolo, codice_contratto, cig, cup, fornitore_id, anno,
                aliquota_iva, data_inizio, data_fine, stato, dec_user_id, reparto_id,
                descrizione, creato_da_id, creato_il
            ) VALUES (
                :titolo, :codice, :cig, :cup, :fornitore_id, :anno,
                :aliquota_iva, NULL, NULL, :stato, :dec_user_id, :reparto_id,
                :descrizione, :creato_da_id, :creato_il
            )
        """), {
            "titolo": target_titolo,
            "codice": contratto["codice_contratto"],
            "cig": contratto["cig"],
            "cup": contratto["cup"],
            "fornitore_id": contratto["fornitore_id"],
            "anno": target_anno,
            "aliquota_iva": aliquota_orig,
            "stato": stato,
            "dec_user_id": contratto["dec_user_id"],
            "reparto_id": contratto["reparto_id"],
            "descrizione": contratto["descrizione"],
            "creato_da_id": user["id"],
            "creato_il": now
        })

        if DB_DRIVER.startswith("sqlite"):
            new_contratto_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
        elif DB_DRIVER.startswith("mysql"):
            new_contratto_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        else:
            new_contratto_id = conn.execute(text("SELECT LASTVAL()")).scalar()

        moduli_orig = conn.execute(text("""
            SELECT * FROM contratti_moduli WHERE contratto_id = :cid ORDER BY ordine ASC, modulo_id ASC
        """), {"cid": contratto_id}).mappings().all()

        for m in moduli_orig:
            conn.execute(text("""
                INSERT INTO contratti_moduli (
                    contratto_id, servizio_id, descrizione, costo,
                    giornate, costo_giornaliero, note, ordine, creato_il
                ) VALUES (
                    :cid, :sid, :desc, :costo, :giornate, :costo_gg, :note, :ordine, :creato_il
                )
            """), {
                "cid": new_contratto_id,
                "sid": m["servizio_id"],
                "desc": m["descrizione"],
                "costo": m["costo"],
                "giornate": m["giornate"],
                "costo_gg": m["costo_giornaliero"],
                "note": m["note"],
                "ordine": m["ordine"],
                "creato_il": now
            })

    return RedirectResponse(url=f"/contratto/{new_contratto_id}?success=duplicato", status_code=303)


# ==========================================
# GESTIONE MODULI / VOCI DI FORNITURA
# ==========================================

@router.post("/contratto/{contratto_id}/modulo/nuovo")
@router.post("/contratti/{contratto_id}/modulo/nuovo")
@router.post("/contratti/contratto/{contratto_id}/modulo/nuovo")
def modulo_nuovo_save(
    r: Request,
    contratto_id: int,
    descrizione: str = Form(...),
    servizio_id: Optional[str] = Form(None),
    costo: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    costo_giornaliero: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    ordine: int = Form(0)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    if not descrizione:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=descrizione_modulo_obbligatoria", status_code=303)

    servizio_id_val = safe_int(servizio_id)
    costo_val = safe_float(costo)
    giornate_val = safe_float(giornate)
    costo_giornaliero_val = safe_float(costo_giornaliero)

    calcolato_costo = costo_val or 0.0
    if (not costo_val or costo_val == 0) and giornate_val and costo_giornaliero_val:
        calcolato_costo = float(giornate_val) * float(costo_giornaliero_val)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("""
            INSERT INTO contratti_moduli (
                contratto_id, servizio_id, descrizione, costo,
                giornate, costo_giornaliero, note, ordine, creato_il
            ) VALUES (
                :cid, :sid, :desc, :costo, :giornate, :costo_gg, :note, :ordine, :creato_il
            )
        """), {
            "cid": contratto_id,
            "sid": servizio_id_val if servizio_id_val else None,
            "desc": descrizione,
            "costo": calcolato_costo,
            "giornate": giornate_val if giornate_val else None,
            "costo_gg": costo_giornaliero_val if costo_giornaliero_val else None,
            "note": note.strip() if note else None,
            "ordine": ordine,
            "creato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=modulo_aggiunto", status_code=303)


@router.post("/contratto/{contratto_id}/modulo/{modulo_id}/modifica")
@router.post("/contratti/{contratto_id}/modulo/{modulo_id}/modifica")
@router.post("/contratti/contratto/{contratto_id}/modulo/{modulo_id}/modifica")
def modulo_edit_save(
    r: Request,
    contratto_id: int,
    modulo_id: int,
    descrizione: str = Form(...),
    servizio_id: Optional[str] = Form(None),
    costo: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    costo_giornaliero: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    ordine: int = Form(0)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    if not descrizione:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=descrizione_modulo_obbligatoria", status_code=303)

    servizio_id_val = safe_int(servizio_id)
    costo_val = safe_float(costo)
    giornate_val = safe_float(giornate)
    costo_giornaliero_val = safe_float(costo_giornaliero)

    calcolato_costo = costo_val or 0.0
    if (not costo_val or costo_val == 0) and giornate_val and costo_giornaliero_val:
        calcolato_costo = float(giornate_val) * float(costo_giornaliero_val)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("""
            UPDATE contratti_moduli SET
                servizio_id = :sid,
                descrizione = :desc,
                costo = :costo,
                giornate = :giornate,
                costo_giornaliero = :costo_gg,
                note = :note,
                ordine = :ordine
            WHERE modulo_id = :mid AND contratto_id = :cid
        """), {
            "sid": servizio_id_val if servizio_id_val else None,
            "desc": descrizione,
            "costo": calcolato_costo,
            "giornate": giornate_val if giornate_val else None,
            "costo_gg": costo_giornaliero_val if costo_giornaliero_val else None,
            "note": note.strip() if note else None,
            "ordine": ordine,
            "mid": modulo_id,
            "cid": contratto_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=modulo_modificato", status_code=303)


@router.post("/contratto/{contratto_id}/modulo/{modulo_id}/elimina")
@router.post("/contratti/{contratto_id}/modulo/{modulo_id}/elimina")
@router.post("/contratti/contratto/{contratto_id}/modulo/{modulo_id}/elimina")
def modulo_delete(r: Request, contratto_id: int, modulo_id: int):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto)):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("DELETE FROM contratti_moduli WHERE modulo_id = :mid AND contratto_id = :cid"), {
            "mid": modulo_id,
            "cid": contratto_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=modulo_eliminato", status_code=303)



# ==========================================
# GESTIONE ORDINI AL FORNITORE
# ==========================================

@router.post("/contratto/{contratto_id}/ordine/nuovo")
@router.post("/contratti/{contratto_id}/ordine/nuovo")
@router.post("/contratti/contratto/{contratto_id}/ordine/nuovo")
def ordine_nuovo_save(
    r: Request,
    contratto_id: int,
    codice: str = Form(...),
    descrizione: str = Form(...),
    durata: Optional[str] = Form(None),
    importo: Optional[str] = Form(None),
    cig: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    costo_giornaliero: Optional[str] = Form(None),
    stato: str = Form("emesso"),
    note: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    codice = codice.strip()
    descrizione = descrizione.strip()
    if not codice or not descrizione:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=campi_obbligatori_ordine", status_code=303)

    giornate_val = safe_float(giornate)
    costo_giornaliero_val = safe_float(costo_giornaliero)
    importo_val = safe_float(importo) or 0.0

    if (not importo_val or importo_val == 0) and giornate_val and costo_giornaliero_val:
        importo_val = float(giornate_val) * float(costo_giornaliero_val)

    if importo_val < 0:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=importo_non_valido", status_code=303)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        financials = get_contratto_financials(conn, contratto_id)
        # Controllo capienza contratto: sommatoria importi ordini non può superare importo contratto
        if financials["importo_contratto"] > 0:
            if (financials["tot_ordini"] + importo_val) > (financials["importo_contratto"] + 0.009):
                disp_str = f"{financials['residuo_ordinabile']:.2f}"
                return RedirectResponse(
                    url=f"/contratto/{contratto_id}?error=superamento_importo_contratto&disponibile={disp_str}",
                    status_code=303
                )
        elif importo_val > 0:
            return RedirectResponse(
                url=f"/contratto/{contratto_id}?error=importo_contratto_nullo",
                status_code=303
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text("""
            INSERT INTO contratti_ordini (
                contratto_id, codice, descrizione, durata, importo, cig,
                giornate, costo_giornaliero, stato, note, creato_da_id, creato_il
            ) VALUES (
                :cid, :codice, :desc, :durata, :importo, :cig,
                :giornate, :costo_gg, :stato, :note, :creato_da_id, :creato_il
            )
        """), {
            "cid": contratto_id,
            "codice": codice,
            "desc": descrizione,
            "durata": durata.strip() if durata else None,
            "importo": importo_val,
            "cig": cig.strip() if cig else None,
            "giornate": giornate_val if giornate_val else None,
            "costo_gg": costo_giornaliero_val if costo_giornaliero_val else None,
            "stato": stato,
            "note": note.strip() if note else None,
            "creato_da_id": user.get("id"),
            "creato_il": now
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=ordine_creato", status_code=303)


@router.post("/contratto/{contratto_id}/ordine/{ordine_id}/modifica")
@router.post("/contratti/{contratto_id}/ordine/{ordine_id}/modifica")
@router.post("/contratti/contratto/{contratto_id}/ordine/{ordine_id}/modifica")
def ordine_edit_save(
    r: Request,
    contratto_id: int,
    ordine_id: int,
    codice: str = Form(...),
    descrizione: str = Form(...),
    durata: Optional[str] = Form(None),
    importo: Optional[str] = Form(None),
    cig: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    costo_giornaliero: Optional[str] = Form(None),
    stato: str = Form("emesso"),
    note: Optional[str] = Form(None),
    return_to: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    codice = codice.strip()
    descrizione = descrizione.strip()
    redirect_target = f"/contratto/{contratto_id}/ordine/{ordine_id}" if return_to == "ordine" else f"/contratto/{contratto_id}"

    if not codice or not descrizione:
        return RedirectResponse(url=f"{redirect_target}?error=campi_obbligatori_ordine", status_code=303)

    giornate_val = safe_float(giornate)
    costo_giornaliero_val = safe_float(costo_giornaliero)
    importo_val = safe_float(importo) or 0.0

    if (not importo_val or importo_val == 0) and giornate_val and costo_giornaliero_val:
        importo_val = float(giornate_val) * float(costo_giornaliero_val)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        old_ordine = conn.execute(text("SELECT * FROM contratti_ordini WHERE ordine_id = :oid AND contratto_id = :cid"), {
            "oid": ordine_id,
            "cid": contratto_id
        }).mappings().first()
        if not old_ordine:
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=ordine_non_trovato", status_code=303)

        financials = get_contratto_financials(conn, contratto_id)
        vecchio_importo = old_ordine["importo"] if old_ordine["stato"] != 'annullato' else 0.0
        nuovo_importo_effettivo = importo_val if stato != 'annullato' else 0.0
        differenza = nuovo_importo_effettivo - vecchio_importo

        if financials["importo_contratto"] > 0 and differenza > 0:
            if (financials["tot_ordini"] + differenza) > (financials["importo_contratto"] + 0.009):
                disp_str = f"{financials['residuo_ordinabile']:.2f}"
                return RedirectResponse(
                    url=f"{redirect_target}?error=superamento_importo_contratto&disponibile={disp_str}",
                    status_code=303
                )

        ord_fin = get_ordine_financials(conn, ordine_id)
        if ord_fin and stato != 'annullato' and importo_val < (ord_fin["tot_costo_attivita"] - 0.009):
            util_str = f"{ord_fin['tot_costo_attivita']:.2f}"
            return RedirectResponse(
                url=f"{redirect_target}?error=importo_minore_attivita_esistenti&utilizzato={util_str}",
                status_code=303
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text("""
            UPDATE contratti_ordini SET
                codice = :codice,
                descrizione = :desc,
                durata = :durata,
                importo = :importo,
                cig = :cig,
                giornate = :giornate,
                costo_giornaliero = :costo_gg,
                stato = :stato,
                note = :note,
                aggiornato_il = :aggiornato_il
            WHERE ordine_id = :oid AND contratto_id = :cid
        """), {
            "codice": codice,
            "desc": descrizione,
            "durata": durata.strip() if durata else None,
            "importo": importo_val,
            "cig": cig.strip() if cig else None,
            "giornate": giornate_val if giornate_val else None,
            "costo_gg": costo_giornaliero_val if costo_giornaliero_val else None,
            "stato": stato,
            "note": note.strip() if note else None,
            "aggiornato_il": now,
            "oid": ordine_id,
            "cid": contratto_id
        })

    return RedirectResponse(url=f"{redirect_target}?success=ordine_modificato", status_code=303)


@router.post("/contratto/{contratto_id}/ordine/{ordine_id}/elimina")
@router.post("/contratti/{contratto_id}/ordine/{ordine_id}/elimina")
@router.post("/contratti/contratto/{contratto_id}/ordine/{ordine_id}/elimina")
def ordine_delete(r: Request, contratto_id: int, ordine_id: int):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("DELETE FROM ordini_attivita WHERE ordine_id = :oid"), {"oid": ordine_id})
        conn.execute(text("DELETE FROM contratti_ordini WHERE ordine_id = :oid AND contratto_id = :cid"), {
            "oid": ordine_id,
            "cid": contratto_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}?success=ordine_eliminato", status_code=303)


# ==========================================
# GESTIONE ATTIVITÀ DELL'ORDINE
# ==========================================

@router.get("/contratto/{contratto_id}/ordine/{ordine_id}", response_class=HTMLResponse)
@router.get("/contratti/{contratto_id}/ordine/{ordine_id}", response_class=HTMLResponse)
@router.get("/contratti/contratto/{contratto_id}/ordine/{ordine_id}", response_class=HTMLResponse)
def ordine_detail(
    r: Request,
    contratto_id: int,
    ordine_id: int,
    error: Optional[str] = None,
    success: Optional[str] = None,
    disponibile: Optional[str] = None,
    utilizzato: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as conn:
        contratto = conn.execute(text("""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            WHERE c.contratto_id = :cid
        """), {"cid": contratto_id}).mappings().first()

        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        can_edit = can_manage_single_contratto(user, dict(contratto), conn=conn)

        ordine_fin = get_ordine_financials(conn, ordine_id)
        if not ordine_fin or ordine_fin["ordine"]["contratto_id"] != contratto_id:
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=ordine_non_trovato", status_code=303)

        attivita = conn.execute(text("""
            SELECT oa.*,
                   u.nome AS creatore_nome, u.cognome AS creatore_cognome
            FROM ordini_attivita oa
            LEFT JOIN users u ON oa.creato_da_id = u.user_id
            WHERE oa.ordine_id = :oid
            ORDER BY oa.data_inizio DESC, oa.attivita_id DESC
        """), {"oid": ordine_id}).mappings().all()

        contratto_fin = get_contratto_financials(conn, contratto_id)

    is_dec = user_has_tag_dec(user)

    return templates.TemplateResponse(r, "ordine_detail.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "is_dec": is_dec,
        "can_edit": can_edit,
        "contratto": contratto,
        "ordine": ordine_fin["ordine"],
        "ordine_fin": ordine_fin,
        "contratto_fin": contratto_fin,
        "attivita": attivita,
        "error": error,
        "success": success,
        "disponibile": disponibile,
        "utilizzato": utilizzato
    })


@router.post("/contratto/{contratto_id}/ordine/{ordine_id}/attivita/nuova")
@router.post("/contratti/{contratto_id}/ordine/{ordine_id}/attivita/nuova")
@router.post("/contratti/contratto/{contratto_id}/ordine/{ordine_id}/attivita/nuova")
def attivita_nuova_save(
    r: Request,
    contratto_id: int,
    ordine_id: int,
    descrizione: str = Form(...),
    data_inizio: str = Form(...),
    data_fine: Optional[str] = Form(None),
    costo: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    stato: str = Form("pianificata"),
    richiedente: Optional[str] = Form(None),
    data_richiesta: Optional[str] = Form(None),
    note: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    data_inizio = data_inizio.strip()
    if not descrizione or not data_inizio:
        return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=campi_obbligatori_attivita", status_code=303)

    giornate_val = safe_float(giornate)
    costo_val = safe_float(costo)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        ordine_fin = get_ordine_financials(conn, ordine_id)
        if not ordine_fin or ordine_fin["ordine"]["contratto_id"] != contratto_id:
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=ordine_non_trovato", status_code=303)

        ordine = ordine_fin["ordine"]

        if (costo_val is None or costo_val == 0) and giornate_val and ordine.get("costo_giornaliero"):
            costo_val = float(giornate_val) * float(ordine["costo_giornaliero"])
        elif costo_val is None:
            costo_val = 0.0

        if stato != 'annullata':
            if costo_val > (ordine_fin["residuo_costo"] + 0.009):
                disp_str = f"{ordine_fin['residuo_costo']:.2f}"
                return RedirectResponse(
                    url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=esaurimento_importo_ordine&disponibile={disp_str}",
                    status_code=303
                )
            if ordine.get("giornate") and giornate_val and ordine_fin["residuo_giornate"] is not None:
                if giornate_val > (ordine_fin["residuo_giornate"] + 0.009):
                    disp_gg = f"{ordine_fin['residuo_giornate']:.1f}"
                    return RedirectResponse(
                        url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=esaurimento_giornate_ordine&disponibile={disp_gg}",
                        status_code=303
                    )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text("""
            INSERT INTO ordini_attivita (
                ordine_id, descrizione, data_inizio, data_fine, costo, giornate,
                stato, richiedente, data_richiesta, note, creato_da_id, creato_il
            ) VALUES (
                :oid, :desc, :d_ini, :d_fin, :costo, :giornate,
                :stato, :richiedente, :data_richiesta, :note, :creato_da_id, :creato_il
            )
        """), {
            "oid": ordine_id,
            "desc": descrizione,
            "d_ini": data_inizio,
            "d_fin": data_fine.strip() if data_fine else None,
            "costo": costo_val,
            "giornate": giornate_val if giornate_val else None,
            "stato": stato,
            "richiedente": richiedente.strip() if richiedente else None,
            "data_richiesta": data_richiesta.strip() if data_richiesta else None,
            "note": note.strip() if note else None,
            "creato_da_id": user.get("id"),
            "creato_il": now
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?success=attivita_creata", status_code=303)


@router.post("/contratto/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/modifica")
@router.post("/contratti/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/modifica")
@router.post("/contratti/contratto/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/modifica")
def attivita_edit_save(
    r: Request,
    contratto_id: int,
    ordine_id: int,
    attivita_id: int,
    descrizione: str = Form(...),
    data_inizio: str = Form(...),
    data_fine: Optional[str] = Form(None),
    costo: Optional[str] = Form(None),
    giornate: Optional[str] = Form(None),
    stato: str = Form("pianificata"),
    richiedente: Optional[str] = Form(None),
    data_richiesta: Optional[str] = Form(None),
    note: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    data_inizio = data_inizio.strip()
    if not descrizione or not data_inizio:
        return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=campi_obbligatori_attivita", status_code=303)

    giornate_val = safe_float(giornate)
    costo_val = safe_float(costo)

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        ordine_fin = get_ordine_financials(conn, ordine_id)
        if not ordine_fin or ordine_fin["ordine"]["contratto_id"] != contratto_id:
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=ordine_non_trovato", status_code=303)

        ordine = ordine_fin["ordine"]
        old_att = conn.execute(text("SELECT * FROM ordini_attivita WHERE attivita_id = :aid AND ordine_id = :oid"), {
            "aid": attivita_id,
            "oid": ordine_id
        }).mappings().first()
        if not old_att:
            return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=attivita_non_trovata", status_code=303)

        if (costo_val is None or costo_val == 0) and giornate_val and ordine.get("costo_giornaliero"):
            costo_val = float(giornate_val) * float(ordine["costo_giornaliero"])
        elif costo_val is None:
            costo_val = 0.0

        vecchio_costo = old_att["costo"] if old_att["stato"] != 'annullata' else 0.0
        nuovo_costo_effettivo = costo_val if stato != 'annullata' else 0.0
        diff_costo = nuovo_costo_effettivo - vecchio_costo

        if diff_costo > 0 and (ordine_fin["tot_costo_attivita"] + diff_costo) > (ordine_fin["importo_ordine"] + 0.009):
            residuo_reale = ordine_fin["residuo_costo"] + (vecchio_costo if old_att["stato"] != 'annullata' else 0.0)
            return RedirectResponse(
                url=f"/contratto/{contratto_id}/ordine/{ordine_id}?error=esaurimento_importo_ordine&disponibile={residuo_reale:.2f}",
                status_code=303
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text("""
            UPDATE ordini_attivita SET
                descrizione = :desc,
                data_inizio = :d_ini,
                data_fine = :d_fin,
                costo = :costo,
                giornate = :giornate,
                stato = :stato,
                richiedente = :richiedente,
                data_richiesta = :data_richiesta,
                note = :note,
                aggiornato_il = :aggiornato_il
            WHERE attivita_id = :aid AND ordine_id = :oid
        """), {
            "desc": descrizione,
            "d_ini": data_inizio,
            "d_fin": data_fine.strip() if data_fine else None,
            "costo": costo_val,
            "giornate": giornate_val if giornate_val else None,
            "stato": stato,
            "richiedente": richiedente.strip() if richiedente else None,
            "data_richiesta": data_richiesta.strip() if data_richiesta else None,
            "note": note.strip() if note else None,
            "aggiornato_il": now,
            "aid": attivita_id,
            "oid": ordine_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?success=attivita_modificata", status_code=303)


@router.post("/contratto/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/elimina")
@router.post("/contratti/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/elimina")
@router.post("/contratti/contratto/{contratto_id}/ordine/{ordine_id}/attivita/{attivita_id}/elimina")
def attivita_delete(r: Request, contratto_id: int, ordine_id: int, attivita_id: int):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as conn:
        contratto = conn.execute(text("SELECT * FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id}).mappings().first()
        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        if not can_manage_single_contratto(user, dict(contratto), conn=conn):
            return RedirectResponse(url=f"/contratto/{contratto_id}?error=permesso_negato", status_code=303)

        conn.execute(text("DELETE FROM ordini_attivita WHERE attivita_id = :aid AND ordine_id = :oid"), {
            "aid": attivita_id,
            "oid": ordine_id
        })

    return RedirectResponse(url=f"/contratto/{contratto_id}/ordine/{ordine_id}?success=attivita_eliminata", status_code=303)


# ==========================================
# STAMPA SCHEDA CONTRATTO
# ==========================================

@router.get("/contratto/{contratto_id}/stampa", response_class=HTMLResponse)
@router.get("/contratti/{contratto_id}/stampa", response_class=HTMLResponse)
@router.get("/contratti/contratto/{contratto_id}/stampa", response_class=HTMLResponse)
def contratto_stampa(r: Request, contratto_id: int):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as conn:
        contratto = conn.execute(text("""
            SELECT c.*,
                   f.ragione_sociale AS fornitore_nome,
                   f.partita_iva AS fornitore_piva,
                   f.codice_fiscale AS fornitore_cf,
                   f.email_generale AS fornitore_email,
                   f.telefono_generale AS fornitore_telefono,
                   f.pec AS fornitore_pec,
                   f.indirizzo AS fornitore_indirizzo,
                   rep.nome AS reparto_nome,
                   u_dec.nome AS dec_nome,
                   u_dec.cognome AS dec_cognome,
                   u_dec.email AS dec_email
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            WHERE c.contratto_id = :cid
        """), {"cid": contratto_id}).mappings().first()

        if not contratto:
            return RedirectResponse(url="/contratti?error=non_trovato", status_code=303)

        moduli = conn.execute(text("""
            SELECT cm.*, s.descrizione AS servizio_nome
            FROM contratti_moduli cm
            LEFT JOIN servizi s ON cm.servizio_id = s.servizio_id
            WHERE cm.contratto_id = :cid
            ORDER BY cm.ordine ASC, cm.modulo_id ASC
        """), {"cid": contratto_id}).mappings().all()

        ordini_rows = conn.execute(text("""
            SELECT co.*,
                   (SELECT COUNT(*) FROM ordini_attivita oa WHERE oa.ordine_id = co.ordine_id AND (oa.stato IS NULL OR oa.stato != 'annullata')) AS cnt_attivita,
                   COALESCE((SELECT SUM(costo) FROM ordini_attivita oa WHERE oa.ordine_id = co.ordine_id AND (oa.stato IS NULL OR oa.stato != 'annullata')), 0.0) AS totale_costo_attivita
            FROM contratti_ordini co
            WHERE co.contratto_id = :cid
            ORDER BY co.ordine_id ASC
        """), {"cid": contratto_id}).mappings().all()

        ordini = []
        for o in ordini_rows:
            od = dict(o)
            att_list = conn.execute(text("""
                SELECT * FROM ordini_attivita 
                WHERE ordine_id = :oid 
                ORDER BY data_inizio ASC, attivita_id ASC
            """), {"oid": od["ordine_id"]}).mappings().all()
            od["attivita"] = [dict(a) for a in att_list]
            ordini.append(od)

        financials = get_contratto_financials(conn, contratto_id)

    aliquota_iva = float(contratto["aliquota_iva"] if (contratto and contratto.get("aliquota_iva") is not None) else 22.0)
    iva_molt = 1.0 + (aliquota_iva / 100.0)

    moduli_enriched = []
    for m in moduli:
        md = dict(m)
        c_val = float(md.get("costo") or 0.0)
        md["costo_iva"] = round(c_val * iva_molt, 2)
        moduli_enriched.append(md)
    moduli = moduli_enriched

    totale_costo = sum(m["costo"] for m in moduli)
    totale_costo_iva = round(totale_costo * iva_molt, 2)
    totale_giornate = sum((m["giornate"] or 0.0) for m in moduli)

    return templates.TemplateResponse(r, "contratto_stampa.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "contratto": contratto,
        "moduli": moduli,
        "ordini": ordini,
        "financials": financials,
        "totale_costo": totale_costo,
        "totale_costo_iva": totale_costo_iva,
        "aliquota_iva": aliquota_iva,
        "totale_giornate": totale_giornate,
        "data_stampa": datetime.now().strftime("%d/%m/%Y %H:%M")
    })

