import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, DB_PK, DB_DRIVER
from utils import current_user

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

def user_has_tag_dec(user: dict) -> bool:
    """Verifica se l'utente possiede il tag DEC assegnato"""
    if not user or not user.get("id"):
        return False
    try:
        with engine.connect() as c:
            count = c.execute(text("""
                SELECT COUNT(*) 
                FROM operatori_tag ot
                JOIN tag_operatori t ON ot.tag_id = t.tag_id
                WHERE ot.user_id = :uid AND UPPER(t.nome) = 'DEC'
            """), {"uid": user["id"]}).scalar() or 0
            return count > 0
    except Exception:
        return False

def user_can_access_contratti(user: dict) -> bool:
    """Verifica booleana se l'utente ha diritto ad accedere al modulo contratti"""
    if not user:
        return False
    ruolo = user.get("ruolo", "normale")
    if ruolo in ("admin", "responsabile"):
        return True
    return user_has_tag_dec(user)

def check_contratti_access(r: Request):
    """
    Verifica se l'utente autenticato può accedere al modulo contratti:
    - Ruolo admin
    - Ruolo responsabile
    - Operatore/Utente con tag DEC
    """
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    ruolo = user.get("ruolo", "normale")
    if ruolo == "admin" or ruolo == "responsabile":
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
    - Admin: sempre True
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

    if ruolo == "admin":
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
# ROTTE GESTIONE CONTRATTI
# ==========================================

@router.get("/contratti", response_class=HTMLResponse)
@router.get("/contratto", response_class=HTMLResponse)
@router.get("/contratti/contratti", response_class=HTMLResponse)
@router.get("/contratto/contratti", response_class=HTMLResponse)
@router.get("/contratti/contratto", response_class=HTMLResponse)
@router.get("/contratti/elenco", response_class=HTMLResponse)
@router.get("/contratto/elenco", response_class=HTMLResponse)
def contratti_list(
    r: Request,
    anno: Optional[int] = None,
    fornitore_id: Optional[int] = None,
    stato: Optional[str] = None,
    reparto_id: Optional[int] = None,
    q: Optional[str] = None,
    error: Optional[str] = None,
    success: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    current_year = datetime.now().year
    if anno:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno

    if fornitore_id:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id

    if q and q.strip():
        where_clauses.append("""(
            c.titolo LIKE :q 
            OR c.codice_contratto LIKE :q 
            OR c.cig LIKE :q 
            OR c.cup LIKE :q 
            OR f.ragione_sociale LIKE :q
            OR u_dec.nome LIKE :q
            OR u_dec.cognome LIKE :q
        )""")
        params["q"] = f"%{q.strip()}%"

    where_sql = " AND ".join(where_clauses)

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
                   (SELECT COUNT(*) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id) AS cnt_moduli,
                   COALESCE((SELECT SUM(cm.costo) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_costo,
                   COALESCE((SELECT SUM(cm.giornate) FROM contratti_moduli cm WHERE cm.contratto_id = c.contratto_id), 0.0) AS totale_giornate
            FROM contratti c
            JOIN fornitori f ON c.fornitore_id = f.fornitore_id
            LEFT JOIN reparti rep ON c.reparto_id = rep.reparto_id
            LEFT JOIN users u_dec ON c.dec_user_id = u_dec.user_id
            WHERE {where_sql}
            ORDER BY c.anno DESC, c.contratto_id DESC
        """), params).mappings().all()

        # Liste di supporto per i filtri
        fornitori = conn.execute(text("SELECT fornitore_id, ragione_sociale FROM fornitori WHERE attivo = 1 ORDER BY ragione_sociale")).mappings().all()
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        anni_disponibili = conn.execute(text("SELECT DISTINCT anno FROM contratti ORDER BY anno DESC")).scalars().all()
        if not anni_disponibili:
            anni_disponibili = [current_year]
        elif current_year not in anni_disponibili:
            anni_disponibili = sorted(list(set(list(anni_disponibili) + [current_year])), reverse=True)

        # Calcolo permessi di modifica per ciascun contratto in lista
        if user.get("ruolo") == "admin":
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
            c_dict["can_edit"] = True if (user.get("ruolo") == "admin" or c_dict["contratto_id"] in editable_ids_set) else False
            contratti_augmented.append(c_dict)

        # Calcolo KPI per la selezione
        totale_spesa = sum(c["totale_costo"] for c in contratti)
        totale_attivi = sum(1 for c in contratti if c["stato"] == "attivo")
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
        "anni_disponibili": anni_disponibili,
        "anno_selezionato": anno,
        "fornitore_selezionato": fornitore_id,
        "stato_selezionato": stato or "",
        "reparto_selezionato": reparto_id,
        "q": q or "",
        "totale_spesa": totale_spesa,
        "totale_attivi": totale_attivi,
        "totale_giornate": totale_giornate,
        "error": error,
        "success": success
    })


@router.get("/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratto/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratto/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratti/contratti/riepilogo-economico", response_class=HTMLResponse)
@router.get("/contratti/report-economico", response_class=HTMLResponse)
@router.get("/contratto/report-economico", response_class=HTMLResponse)
def contratti_riepilogo_economico(
    r: Request,
    anno: Optional[int] = None,
    fornitore_id: Optional[int] = None,
    reparto_id: Optional[int] = None,
    stato: Optional[str] = None
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    current_year = datetime.now().year
    
    # Se l'anno non è specificato nei parametri (primo accesso), impostiamo l'anno corrente di default.
    # Se il parametro anno è 0, significa visualizzare "Tutti gli anni".
    anno_filtro = anno
    if anno is None:
        anno_filtro = current_year

    scope_sql, scope_params = get_contratto_scope_filter(user)
    where_clauses = [scope_sql]
    params = dict(scope_params)

    if anno_filtro and anno_filtro > 0:
        where_clauses.append("c.anno = :anno")
        params["anno"] = anno_filtro

    if fornitore_id:
        where_clauses.append("c.fornitore_id = :fornitore_id")
        params["fornitore_id"] = fornitore_id

    if stato and stato.strip():
        where_clauses.append("c.stato = :stato")
        params["stato"] = stato.strip()

    if reparto_id:
        where_clauses.append("c.reparto_id = :reparto_id")
        params["reparto_id"] = reparto_id

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
            
            c_dict["moduli"] = mods
            c_dict["totale_costo"] = c_costo
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
        "anni_disponibili": anni_disponibili,
        "anno_selezionato": anno_filtro,
        "fornitore_selezionato": fornitore_id,
        "reparto_selezionato": reparto_id,
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
    data_inizio: Optional[str] = Form(None),
    data_fine: Optional[str] = Form(None),
    stato: str = Form("attivo"),
    dec_user_id: Optional[int] = Form(None),
    reparto_id: Optional[int] = Form(None),
    descrizione: Optional[str] = Form(None),
    # Modulo iniziale opzionale
    modulo_descrizione: Optional[str] = Form(None),
    modulo_servizio_id: Optional[int] = Form(None),
    modulo_costo: Optional[float] = Form(None),
    modulo_giornate: Optional[float] = Form(None),
    modulo_costo_giornaliero: Optional[float] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url="/contratto/nuovo?error=titolo_obbligatorio", status_code=303)

    # Se l'utente è operatore DEC e non ha specificato il DEC, assegniamo lui stesso
    if not dec_user_id and user_has_tag_dec(user):
        dec_user_id = user["id"]

    # Se non è specificato il reparto, usiamo quello dell'utente o del DEC
    if not reparto_id and user.get("reparto_id"):
        reparto_id = user.get("reparto_id")

    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO contratti (
                titolo, codice_contratto, cig, cup, fornitore_id, anno,
                data_inizio, data_fine, stato, dec_user_id, reparto_id,
                descrizione, creato_da_id, creato_il
            ) VALUES (
                :titolo, :codice, :cig, :cup, :fornitore_id, :anno,
                :data_inizio, :data_fine, :stato, :dec_user_id, :reparto_id,
                :descrizione, :creato_da_id, :creato_il
            )
        """), {
            "titolo": titolo,
            "codice": codice_contratto.strip() if codice_contratto else None,
            "cig": cig.strip() if cig else None,
            "cup": cup.strip() if cup else None,
            "fornitore_id": fornitore_id,
            "anno": anno,
            "data_inizio": data_inizio.strip() if data_inizio else None,
            "data_fine": data_fine.strip() if data_fine else None,
            "stato": stato,
            "dec_user_id": dec_user_id,
            "reparto_id": reparto_id,
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
            calcolato_costo = modulo_costo or 0.0
            if (not modulo_costo or modulo_costo == 0) and modulo_giornate and modulo_costo_giornaliero:
                calcolato_costo = float(modulo_giornate) * float(modulo_costo_giornaliero)

            conn.execute(text("""
                INSERT INTO contratti_moduli (
                    contratto_id, servizio_id, descrizione, costo,
                    giornate, costo_giornaliero, creato_il
                ) VALUES (
                    :cid, :sid, :desc, :costo, :giornate, :costo_gg, :creato_il
                )
            """), {
                "cid": contratto_id,
                "sid": modulo_servizio_id if modulo_servizio_id else None,
                "desc": modulo_descrizione.strip(),
                "costo": calcolato_costo,
                "giornate": modulo_giornate if modulo_giornate else None,
                "costo_gg": modulo_costo_giornaliero if modulo_costo_giornaliero else None,
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

    totale_costo = sum(m["costo"] for m in moduli)
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
        "servizi": servizi,
        "contatti_fornitore": contatti_fornitore,
        "totale_costo": totale_costo,
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
    data_inizio: Optional[str] = Form(None),
    data_fine: Optional[str] = Form(None),
    stato: str = Form("attivo"),
    dec_user_id: Optional[int] = Form(None),
    reparto_id: Optional[int] = Form(None),
    descrizione: Optional[str] = Form(None)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url=f"/contratto/{contratto_id}/modifica?error=titolo_obbligatorio", status_code=303)

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
            "data_inizio": data_inizio.strip() if data_inizio else None,
            "data_fine": data_fine.strip() if data_fine else None,
            "stato": stato,
            "dec_user_id": dec_user_id,
            "reparto_id": reparto_id,
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

        conn.execute(text("DELETE FROM contratti_moduli WHERE contratto_id = :cid"), {"cid": contratto_id})
        conn.execute(text("DELETE FROM contratti WHERE contratto_id = :cid"), {"cid": contratto_id})

    return RedirectResponse(url="/contratti?success=eliminato", status_code=303)


@router.post("/contratto/{contratto_id}/duplica")
@router.post("/contratti/{contratto_id}/duplica")
@router.post("/contratti/contratto/{contratto_id}/duplica")
def contratto_duplica(
    r: Request,
    contratto_id: int,
    nuovo_anno: Optional[int] = Form(None),
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

        target_anno = nuovo_anno if nuovo_anno else (contratto["anno"] + 1)
        
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

        conn.execute(text("""
            INSERT INTO contratti (
                titolo, codice_contratto, cig, cup, fornitore_id, anno,
                data_inizio, data_fine, stato, dec_user_id, reparto_id,
                descrizione, creato_da_id, creato_il
            ) VALUES (
                :titolo, :codice, :cig, :cup, :fornitore_id, :anno,
                NULL, NULL, :stato, :dec_user_id, :reparto_id,
                :descrizione, :creato_da_id, :creato_il
            )
        """), {
            "titolo": target_titolo,
            "codice": contratto["codice_contratto"],
            "cig": contratto["cig"],
            "cup": contratto["cup"],
            "fornitore_id": contratto["fornitore_id"],
            "anno": target_anno,
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
    servizio_id: Optional[int] = Form(None),
    costo: Optional[float] = Form(None),
    giornate: Optional[float] = Form(None),
    costo_giornaliero: Optional[float] = Form(None),
    note: Optional[str] = Form(None),
    ordine: int = Form(0)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    if not descrizione:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=descrizione_modulo_obbligatoria", status_code=303)

    calcolato_costo = costo or 0.0
    if (not costo or costo == 0) and giornate and costo_giornaliero:
        calcolato_costo = float(giornate) * float(costo_giornaliero)

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
            "sid": servizio_id if servizio_id else None,
            "desc": descrizione,
            "costo": calcolato_costo,
            "giornate": giornate if giornate else None,
            "costo_gg": costo_giornaliero if costo_giornaliero else None,
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
    servizio_id: Optional[int] = Form(None),
    costo: Optional[float] = Form(None),
    giornate: Optional[float] = Form(None),
    costo_giornaliero: Optional[float] = Form(None),
    note: Optional[str] = Form(None),
    ordine: int = Form(0)
):
    user = check_contratti_access(r)
    if isinstance(user, RedirectResponse):
        return user

    descrizione = descrizione.strip()
    if not descrizione:
        return RedirectResponse(url=f"/contratto/{contratto_id}?error=descrizione_modulo_obbligatoria", status_code=303)

    calcolato_costo = costo or 0.0
    if (not costo or costo == 0) and giornate and costo_giornaliero:
        calcolato_costo = float(giornate) * float(costo_giornaliero)

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
            "sid": servizio_id if servizio_id else None,
            "desc": descrizione,
            "costo": calcolato_costo,
            "giornate": giornate if giornate else None,
            "costo_gg": costo_giornaliero if costo_giornaliero else None,
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

    totale_costo = sum(m["costo"] for m in moduli)
    totale_giornate = sum((m["giornate"] or 0.0) for m in moduli)

    return templates.TemplateResponse(r, "contratto_stampa.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "contratto": contratto,
        "moduli": moduli,
        "totale_costo": totale_costo,
        "totale_giornate": totale_giornate,
        "data_stampa": datetime.now().strftime("%d/%m/%Y %H:%M")
    })
