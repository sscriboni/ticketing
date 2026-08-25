import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, DB_PK, DB_DRIVER
from utils import require_superuser, current_user

router = APIRouter()

def init_fornitori_db():
    with engine.begin() as c:
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS fornitori (
            fornitore_id {DB_PK},
            ragione_sociale TEXT NOT NULL,
            partita_iva TEXT,
            codice_fiscale TEXT,
            descrizione TEXT,
            indirizzo TEXT,
            sito_web TEXT,
            email_generale TEXT,
            telefono_generale TEXT,
            pec TEXT,
            note TEXT,
            attivo INTEGER DEFAULT 1,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP
        )"""))

        c.execute(text(f"""CREATE TABLE IF NOT EXISTS fornitori_contatti (
            contatto_id {DB_PK},
            fornitore_id INTEGER NOT NULL,
            titolo TEXT NOT NULL,
            nome_referente TEXT,
            telefono TEXT,
            telefono_secondario TEXT,
            email TEXT,
            email_secondaria TEXT,
            url TEXT,
            orari_disponibilita TEXT,
            istruzioni_ingaggio TEXT,
            note TEXT,
            ordine INTEGER DEFAULT 0,
            creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(fornitore_id) REFERENCES fornitori(fornitore_id) ON DELETE CASCADE
        )"""))

        c.execute(text(f"""CREATE TABLE IF NOT EXISTS servizi_fornitori (
            servizio_id INTEGER NOT NULL,
            fornitore_id INTEGER NOT NULL,
            note TEXT,
            principale INTEGER DEFAULT 0,
            PRIMARY KEY (servizio_id, fornitore_id),
            FOREIGN KEY(servizio_id) REFERENCES servizi(servizio_id) ON DELETE CASCADE,
            FOREIGN KEY(fornitore_id) REFERENCES fornitori(fornitore_id) ON DELETE CASCADE
        )"""))

# Inizializzazione automatica delle tabelle al caricamento
try:
    init_fornitori_db()
except Exception as e:
    print(f"[FORNITORI DB INIT WARNING] {e}")


# ==========================================
# GESTIONE ADMIN FORNITORI
# ==========================================

@router.get("/admin/fornitori", response_class=HTMLResponse)
def admin_fornitori_list(r: Request, q: Optional[str] = None, stato: Optional[str] = None, servizio_id: Optional[int] = None, error: Optional[str] = None, success: Optional[str] = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    where_clauses = ["1=1"]
    params = {}

    if q and q.strip():
        where_clauses.append("(f.ragione_sociale LIKE :q OR f.partita_iva LIKE :q OR f.codice_fiscale LIKE :q OR f.descrizione LIKE :q OR f.email_generale LIKE :q)")
        params["q"] = f"%{q.strip()}%"

    if stato == "attivi":
        where_clauses.append("f.attivo = 1")
    elif stato == "inattivi":
        where_clauses.append("f.attivo = 0")

    if servizio_id:
        where_clauses.append("f.fornitore_id IN (SELECT fornitore_id FROM servizi_fornitori WHERE servizio_id = :sid)")
        params["sid"] = servizio_id

    where_sql = " AND ".join(where_clauses)

    with engine.connect() as c:
        fornitori_raw = c.execute(text(f"""
            SELECT f.*,
                   (SELECT COUNT(*) FROM fornitori_contatti fc WHERE fc.fornitore_id = f.fornitore_id) AS cnt_contatti,
                   (SELECT COUNT(*) FROM servizi_fornitori sf WHERE sf.fornitore_id = f.fornitore_id) AS cnt_servizi
            FROM fornitori f
            WHERE {where_sql}
            ORDER BY f.ragione_sociale ASC
        """), params).mappings().all()

        servizi = c.execute(text("SELECT servizio_id, descrizione FROM servizi ORDER BY descrizione")).mappings().all()

    return templates.TemplateResponse(r, "admin_fornitori.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "fornitori": fornitori_raw,
        "servizi": servizi,
        "q": q or "",
        "stato": stato or "",
        "servizio_id": servizio_id,
        "error": error,
        "success": success
    })


@router.post("/admin/fornitore")
def admin_crea_fornitore(
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
    attivo: int = Form(1)
):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    ragione_sociale = ragione_sociale.strip()
    if not ragione_sociale:
        return RedirectResponse(url="/admin/fornitori?error=nome_obbligatorio", status_code=303)

    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO fornitori (
                ragione_sociale, partita_iva, codice_fiscale, descrizione,
                indirizzo, sito_web, email_generale, telefono_generale,
                pec, note, attivo, creato_il
            ) VALUES (
                :rs, :piva, :cf, :desc,
                :ind, :sito, :email, :tel,
                :pec, :note, :attivo, :creato
            )
        """), {
            "rs": ragione_sociale,
            "piva": partita_iva.strip() or None,
            "cf": codice_fiscale.strip() or None,
            "desc": descrizione.strip() or None,
            "ind": indirizzo.strip() or None,
            "sito": sito_web.strip() or None,
            "email": email_generale.strip() or None,
            "tel": telefono_generale.strip() or None,
            "pec": pec.strip() or None,
            "note": note.strip() or None,
            "attivo": 1 if attivo else 0,
            "creato": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return RedirectResponse(url="/admin/fornitori?success=creato", status_code=303)


@router.get("/admin/fornitore/{fornitore_id}", response_class=HTMLResponse)
def admin_dettaglio_fornitore(r: Request, fornitore_id: int, error: Optional[str] = None, success: Optional[str] = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.connect() as c:
        fornitore = c.execute(text("SELECT * FROM fornitori WHERE fornitore_id = :id"), {"id": fornitore_id}).mappings().first()
        if not fornitore:
            return RedirectResponse(url="/admin/fornitori?error=non_trovato", status_code=303)

        contatti = c.execute(text("""
            SELECT * FROM fornitori_contatti
            WHERE fornitore_id = :id
            ORDER BY ordine ASC, contatto_id ASC
        """), {"id": fornitore_id}).mappings().all()

        servizi_associati = c.execute(text("""
            SELECT sf.servizio_id, sf.note as sf_note, sf.principale, s.descrizione as servizio_nome, r.nome as reparto_nome
            FROM servizi_fornitori sf
            JOIN servizi s ON sf.servizio_id = s.servizio_id
            LEFT JOIN reparti r ON s.reparto_id = r.reparto_id
            WHERE sf.fornitore_id = :id
            ORDER BY s.descrizione ASC
        """), {"id": fornitore_id}).mappings().all()

        tutti_servizi = c.execute(text("""
            SELECT s.servizio_id, s.descrizione, r.nome as reparto_nome
            FROM servizi s
            LEFT JOIN reparti r ON s.reparto_id = r.reparto_id
            ORDER BY s.descrizione ASC
        """)).mappings().all()

    return templates.TemplateResponse(r, "edit_fornitore.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "fornitore": fornitore,
        "contatti": contatti,
        "servizi_associati": servizi_associati,
        "tutti_servizi": tutti_servizi,
        "error": error,
        "success": success
    })


@router.post("/admin/fornitore/{fornitore_id}/modifica")
def admin_modifica_fornitore(
    r: Request,
    fornitore_id: int,
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
    attivo: int = Form(0)
):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    ragione_sociale = ragione_sociale.strip()
    if not ragione_sociale:
        return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?error=nome_obbligatorio", status_code=303)

    with engine.begin() as c:
        c.execute(text("""
            UPDATE fornitori SET
                ragione_sociale = :rs,
                partita_iva = :piva,
                codice_fiscale = :cf,
                descrizione = :desc,
                indirizzo = :ind,
                sito_web = :sito,
                email_generale = :email,
                telefono_generale = :tel,
                pec = :pec,
                note = :note,
                attivo = :attivo
            WHERE fornitore_id = :id
        """), {
            "rs": ragione_sociale,
            "piva": partita_iva.strip() or None,
            "cf": codice_fiscale.strip() or None,
            "desc": descrizione.strip() or None,
            "ind": indirizzo.strip() or None,
            "sito": sito_web.strip() or None,
            "email": email_generale.strip() or None,
            "tel": telefono_generale.strip() or None,
            "pec": pec.strip() or None,
            "note": note.strip() or None,
            "attivo": 1 if attivo else 0,
            "id": fornitore_id
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=salvato", status_code=303)


@router.post("/admin/fornitore/{fornitore_id}/toggle-attivo")
def admin_toggle_attivo_fornitore(r: Request, fornitore_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as c:
        curr = c.execute(text("SELECT attivo FROM fornitori WHERE fornitore_id = :id"), {"id": fornitore_id}).scalar()
        new_val = 0 if curr == 1 else 1
        c.execute(text("UPDATE fornitori SET attivo = :val WHERE fornitore_id = :id"), {"val": new_val, "id": fornitore_id})

    return {"status": "success", "new_val": new_val}


@router.post("/admin/fornitore/{fornitore_id}/elimina")
def admin_elimina_fornitore(r: Request, fornitore_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as c:
        c.execute(text("DELETE FROM fornitori_contatti WHERE fornitore_id = :id"), {"id": fornitore_id})
        c.execute(text("DELETE FROM servizi_fornitori WHERE fornitore_id = :id"), {"id": fornitore_id})
        c.execute(text("DELETE FROM fornitori WHERE fornitore_id = :id"), {"id": fornitore_id})

    return RedirectResponse(url="/admin/fornitori?success=eliminato", status_code=303)


# ==========================================
# GESTIONE SCHEDE CONTATTO FORNITORE
# ==========================================

@router.post("/admin/fornitore/{fornitore_id}/contatto")
def admin_aggiungi_contatto(
    r: Request,
    fornitore_id: int,
    titolo: str = Form(...),
    nome_referente: str = Form(""),
    telefono: str = Form(""),
    telefono_secondario: str = Form(""),
    email: str = Form(""),
    email_secondaria: str = Form(""),
    url: str = Form(""),
    orari_disponibilita: str = Form(""),
    istruzioni_ingaggio: str = Form(""),
    note: str = Form(""),
    ordine: int = Form(0)
):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?error=titolo_contatto_obbligatorio", status_code=303)

    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO fornitori_contatti (
                fornitore_id, titolo, nome_referente, telefono, telefono_secondario,
                email, email_secondaria, url, orari_disponibilita, istruzioni_ingaggio,
                note, ordine, creato_il
            ) VALUES (
                :fid, :titolo, :ref, :tel, :tel2,
                :email, :email2, :url, :orari, :istr,
                :note, :ord, :creato
            )
        """), {
            "fid": fornitore_id,
            "titolo": titolo,
            "ref": nome_referente.strip() or None,
            "tel": telefono.strip() or None,
            "tel2": telefono_secondario.strip() or None,
            "email": email.strip() or None,
            "email2": email_secondaria.strip() or None,
            "url": url.strip() or None,
            "orari": orari_disponibilita.strip() or None,
            "istr": istruzioni_ingaggio.strip() or None,
            "note": note.strip() or None,
            "ord": ordine or 0,
            "creato": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=contatto_aggiunto", status_code=303)


@router.post("/admin/fornitore/{fornitore_id}/contatto/{contatto_id}/modifica")
def admin_modifica_contatto(
    r: Request,
    fornitore_id: int,
    contatto_id: int,
    titolo: str = Form(...),
    nome_referente: str = Form(""),
    telefono: str = Form(""),
    telefono_secondario: str = Form(""),
    email: str = Form(""),
    email_secondaria: str = Form(""),
    url: str = Form(""),
    orari_disponibilita: str = Form(""),
    istruzioni_ingaggio: str = Form(""),
    note: str = Form(""),
    ordine: int = Form(0)
):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    titolo = titolo.strip()
    if not titolo:
        return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?error=titolo_contatto_obbligatorio", status_code=303)

    with engine.begin() as c:
        c.execute(text("""
            UPDATE fornitori_contatti SET
                titolo = :titolo,
                nome_referente = :ref,
                telefono = :tel,
                telefono_secondario = :tel2,
                email = :email,
                email_secondaria = :email2,
                url = :url,
                orari_disponibilita = :orari,
                istruzioni_ingaggio = :istr,
                note = :note,
                ordine = :ord
            WHERE contatto_id = :cid AND fornitore_id = :fid
        """), {
            "titolo": titolo,
            "ref": nome_referente.strip() or None,
            "tel": telefono.strip() or None,
            "tel2": telefono_secondario.strip() or None,
            "email": email.strip() or None,
            "email2": email_secondaria.strip() or None,
            "url": url.strip() or None,
            "orari": orari_disponibilita.strip() or None,
            "istr": istruzioni_ingaggio.strip() or None,
            "note": note.strip() or None,
            "ord": ordine or 0,
            "cid": contatto_id,
            "fid": fornitore_id
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=contatto_modificato", status_code=303)


@router.post("/admin/fornitore/{fornitore_id}/contatto/{contatto_id}/elimina")
def admin_elimina_contatto(r: Request, fornitore_id: int, contatto_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as c:
        c.execute(text("DELETE FROM fornitori_contatti WHERE contatto_id = :cid AND fornitore_id = :fid"), {
            "cid": contatto_id,
            "fid": fornitore_id
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=contatto_eliminato", status_code=303)


# ==========================================
# GESTIONE ASSOCIAZIONE SERVIZI <-> FORNITORI
# ==========================================

@router.post("/admin/fornitore/{fornitore_id}/associa-servizio")
def admin_associa_servizio_a_fornitore(
    r: Request,
    fornitore_id: int,
    servizio_id: int = Form(...),
    note: str = Form(""),
    principale: int = Form(0)
):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as c:
        # Se SQLite/MySQL, gestisci inserimento o aggiornamento
        c.execute(text("""
            DELETE FROM servizi_fornitori WHERE servizio_id = :sid AND fornitore_id = :fid
        """), {"sid": servizio_id, "fid": fornitore_id})

        c.execute(text("""
            INSERT INTO servizi_fornitori (servizio_id, fornitore_id, note, principale)
            VALUES (:sid, :fid, :note, :princ)
        """), {
            "sid": servizio_id,
            "fid": fornitore_id,
            "note": note.strip() or None,
            "princ": 1 if principale else 0
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=servizio_associato", status_code=303)


@router.post("/admin/fornitore/{fornitore_id}/disassocia-servizio")
def admin_disassocia_servizio_da_fornitore(r: Request, fornitore_id: int, servizio_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user

    with engine.begin() as c:
        c.execute(text("DELETE FROM servizi_fornitori WHERE servizio_id = :sid AND fornitore_id = :fid"), {
            "sid": servizio_id,
            "fid": fornitore_id
        })

    return RedirectResponse(url=f"/admin/fornitore/{fornitore_id}?success=servizio_disassociato", status_code=303)


# ==========================================
# RUBRICA FORNITORI (OPERATORI, ASSISTENZA, ADMIN)
# ==========================================

@router.get("/fornitori", response_class=HTMLResponse)
def rubrica_fornitori(r: Request, q: Optional[str] = None, servizio_id: Optional[int] = None):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login")

    where_clauses = ["f.attivo = 1"]
    params = {}

    if q and q.strip():
        where_clauses.append("(f.ragione_sociale LIKE :q OR f.partita_iva LIKE :q OR f.descrizione LIKE :q OR f.indirizzo LIKE :q)")
        params["q"] = f"%{q.strip()}%"

    if servizio_id:
        where_clauses.append("f.fornitore_id IN (SELECT fornitore_id FROM servizi_fornitori WHERE servizio_id = :sid)")
        params["sid"] = servizio_id

    where_sql = " AND ".join(where_clauses)

    with engine.connect() as c:
        fornitori_raw = c.execute(text(f"""
            SELECT f.*
            FROM fornitori f
            WHERE {where_sql}
            ORDER BY f.ragione_sociale ASC
        """), params).mappings().all()

        # Carica contatti e servizi associati per ciascun fornitore
        fornitori_list = []
        for f in fornitori_raw:
            fid = f["fornitore_id"]
            contatti = c.execute(text("""
                SELECT * FROM fornitori_contatti
                WHERE fornitore_id = :fid
                ORDER BY ordine ASC, contatto_id ASC
            """), {"fid": fid}).mappings().all()

            servizi = c.execute(text("""
                SELECT sf.note as sf_note, sf.principale, s.servizio_id, s.descrizione as servizio_nome, r.nome as reparto_nome
                FROM servizi_fornitori sf
                JOIN servizi s ON sf.servizio_id = s.servizio_id
                LEFT JOIN reparti r ON s.reparto_id = r.reparto_id
                WHERE sf.fornitore_id = :fid
                ORDER BY s.descrizione ASC
            """), {"fid": fid}).mappings().all()

            f_dict = dict(f)
            f_dict["contatti"] = [dict(cnt) for cnt in contatti]
            f_dict["servizi"] = [dict(srv) for srv in servizi]
            fornitori_list.append(f_dict)

        tutti_servizi = c.execute(text("SELECT servizio_id, descrizione FROM servizi WHERE accetta_ticket = 1 ORDER BY descrizione")).mappings().all()

    return templates.TemplateResponse(r, "fornitori_rubrica.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "fornitori": fornitori_list,
        "servizi": tutti_servizi,
        "q": q or "",
        "servizio_id": servizio_id
    })
