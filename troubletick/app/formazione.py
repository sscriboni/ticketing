import os
import urllib.parse
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import CFG, engine, templates
from utils import current_user, user_is_train_manager
from admin_logger import log_admin_action

router = APIRouter()

@router.get("/formazione", response_class=HTMLResponse)
def get_formazione_catalogo(
    r: Request,
    q: Optional[str] = Query(None),
    modalita: Optional[str] = Query(None),
    stato: Optional[str] = Query("tutti")
):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    if not CFG.get("modulo_formazione", False):
        msg = urllib.parse.quote("Il modulo Formazione non è attualmente abilitato.")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)
    
    can_manage = user_is_train_manager(user)
    
    with engine.connect() as conn:
        query_sql = """
            SELECT c.*,
                   u.nome as creatore_nome, u.cognome as creatore_cognome,
                   (SELECT COUNT(*) FROM edizioni_formazione e WHERE e.corso_id = c.corso_id) as edizioni_count,
                   (SELECT COUNT(*) FROM edizioni_formazione e WHERE e.corso_id = c.corso_id AND e.stato IN ('programmata', 'in_corso')) as edizioni_attive_count,
                   (SELECT MIN(e.data_inizio) FROM edizioni_formazione e WHERE e.corso_id = c.corso_id AND e.stato IN ('programmata', 'in_corso')) as prossima_data
            FROM corsi_formazione c
            LEFT JOIN users u ON c.creato_da_id = u.user_id
            WHERE 1=1
        """
        params = {}
        
        if q and q.strip():
            query_sql += """
                AND (
                    LOWER(c.titolo) LIKE :q 
                    OR LOWER(COALESCE(c.descrizione_breve, '')) LIKE :q 
                    OR LOWER(COALESCE(c.descrizione, '')) LIKE :q 
                    OR LOWER(COALESCE(c.destinatari, '')) LIKE :q 
                    OR LOWER(COALESCE(c.ente_erogatore, '')) LIKE :q
                )
            """
            params["q"] = f"%{q.strip().lower()}%"
            
        if modalita and modalita.strip():
            query_sql += " AND LOWER(COALESCE(c.modalita, '')) LIKE :modalita"
            params["modalita"] = f"%{modalita.strip().lower()}%"
            
        if stato == "attivi":
            query_sql += " AND c.attivo = 1"
        elif stato == "disattivati":
            query_sql += " AND c.attivo = 0"
            
        query_sql += " ORDER BY c.attivo DESC, c.creato_il DESC"
        
        corsi = conn.execute(text(query_sql), params).mappings().all()
        sedi = conn.execute(text("SELECT sede_id, nome, citta FROM sedi ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "formazione_corsi.html", {
        "request": r,
        "user": user,
        "cfg": CFG,
        "corsi": corsi,
        "sedi": sedi,
        "q": q or "",
        "modalita": modalita or "",
        "stato": stato or "tutti",
        "can_manage": can_manage
    })


@router.post("/formazione/corsi/nuovo")
async def create_corso(
    r: Request,
    titolo: str = Form(...),
    descrizione_breve: Optional[str] = Form(""),
    descrizione: Optional[str] = Form(""),
    destinatari: Optional[str] = Form(""),
    ente_erogatore: Optional[str] = Form(""),
    periodo_svolgimento: Optional[str] = Form(""),
    link_piattaforma: Optional[str] = Form(""),
    durata_ore: Optional[str] = Form(None),
    categoria: Optional[str] = Form(""),
    attivo: int = Form(1)
):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Non hai i permessi per creare corsi"), status_code=303)

    form_data = await r.form()
    modalita_list = form_data.getlist("modalita")
    modalita_str = ", ".join([m.strip() for m in modalita_list if m.strip()]) if modalita_list else ""
    
    durata_val = None
    if durata_ore and durata_ore.strip():
        try:
            durata_val = float(durata_ore.strip().replace(",", "."))
        except ValueError:
            pass

    uid = user.get("id") or user.get("user_id")

    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO corsi_formazione (
                titolo, descrizione_breve, descrizione, destinatari, 
                ente_erogatore, periodo_svolgimento, modalita, link_piattaforma,
                durata_ore, categoria, attivo, creato_da_id, creato_il
            ) VALUES (
                :titolo, :descrizione_breve, :descrizione, :destinatari,
                :ente_erogatore, :periodo_svolgimento, :modalita, :link_piattaforma,
                :durata_ore, :categoria, :attivo, :creato_da_id, :creato_il
            )
        """), {
            "titolo": titolo.strip(),
            "descrizione_breve": (descrizione_breve or "").strip(),
            "descrizione": (descrizione or "").strip(),
            "destinatari": (destinatari or "").strip(),
            "ente_erogatore": (ente_erogatore or "").strip(),
            "periodo_svolgimento": (periodo_svolgimento or "").strip(),
            "modalita": modalita_str,
            "link_piattaforma": (link_piattaforma or "").strip(),
            "durata_ore": durata_val,
            "categoria": (categoria or "").strip(),
            "attivo": attivo,
            "creato_da_id": uid,
            "creato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        new_id = res.lastrowid
        log_admin_action(r, "FORMAZIONE_CREA_CORSO", f"Creato corso '{titolo.strip()}' (ID: {new_id})")

    return RedirectResponse(url=f"/formazione/corso/{new_id}?success=" + urllib.parse.quote("Corso creato con successo!"), status_code=303)


@router.get("/formazione/corso/{corso_id}", response_class=HTMLResponse)
def get_corso_dettaglio(r: Request, corso_id: int):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)

    can_manage = user_is_train_manager(user)

    with engine.connect() as conn:
        corso = conn.execute(text("""
            SELECT c.*, u.nome as creatore_nome, u.cognome as creatore_cognome
            FROM corsi_formazione c
            LEFT JOIN users u ON c.creato_da_id = u.user_id
            WHERE c.corso_id = :cid
        """), {"cid": corso_id}).mappings().first()

        if not corso:
            return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Corso non trovato"), status_code=303)

        edizioni = conn.execute(text("""
            SELECT e.*,
                   s.nome as sede_nome, s.citta as sede_citta, s.indirizzo as sede_indirizzo,
                   u.nome as creatore_nome, u.cognome as creatore_cognome
            FROM edizioni_formazione e
            LEFT JOIN sedi s ON e.sede_id = s.sede_id
            LEFT JOIN users u ON e.creato_da_id = u.user_id
            WHERE e.corso_id = :cid
            ORDER BY e.data_inizio DESC, e.ora DESC
        """), {"cid": corso_id}).mappings().all()

        sedi = conn.execute(text("SELECT sede_id, nome, citta, indirizzo FROM sedi ORDER BY nome")).mappings().all()

    # Parse modalita as list for convenient badge display
    modalita_tags = [m.strip() for m in (corso["modalita"] or "").split(",") if m.strip()]

    return templates.TemplateResponse(r, "formazione_corso_dettaglio.html", {
        "request": r,
        "user": user,
        "cfg": CFG,
        "corso": corso,
        "edizioni": edizioni,
        "sedi": sedi,
        "modalita_tags": modalita_tags,
        "can_manage": can_manage
    })


@router.post("/formazione/corso/{corso_id}/modifica")
async def update_corso(
    r: Request,
    corso_id: int,
    titolo: str = Form(...),
    descrizione_breve: Optional[str] = Form(""),
    descrizione: Optional[str] = Form(""),
    destinatari: Optional[str] = Form(""),
    ente_erogatore: Optional[str] = Form(""),
    periodo_svolgimento: Optional[str] = Form(""),
    link_piattaforma: Optional[str] = Form(""),
    durata_ore: Optional[str] = Form(None),
    categoria: Optional[str] = Form(""),
    attivo: int = Form(1)
):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url=f"/formazione/corso/{corso_id}?error=" + urllib.parse.quote("Non hai i permessi per modificare questo corso"), status_code=303)

    form_data = await r.form()
    modalita_list = form_data.getlist("modalita")
    modalita_str = ", ".join([m.strip() for m in modalita_list if m.strip()]) if modalita_list else ""

    durata_val = None
    if durata_ore and durata_ore.strip():
        try:
            durata_val = float(durata_ore.strip().replace(",", "."))
        except ValueError:
            pass

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE corsi_formazione SET
                titolo = :titolo,
                descrizione_breve = :descrizione_breve,
                descrizione = :descrizione,
                destinatari = :destinatari,
                ente_erogatore = :ente_erogatore,
                periodo_svolgimento = :periodo_svolgimento,
                modalita = :modalita,
                link_piattaforma = :link_piattaforma,
                durata_ore = :durata_ore,
                categoria = :categoria,
                attivo = :attivo
            WHERE corso_id = :cid
        """), {
            "cid": corso_id,
            "titolo": titolo.strip(),
            "descrizione_breve": (descrizione_breve or "").strip(),
            "descrizione": (descrizione or "").strip(),
            "destinatari": (destinatari or "").strip(),
            "ente_erogatore": (ente_erogatore or "").strip(),
            "periodo_svolgimento": (periodo_svolgimento or "").strip(),
            "modalita": modalita_str,
            "link_piattaforma": (link_piattaforma or "").strip(),
            "durata_ore": durata_val,
            "categoria": (categoria or "").strip(),
            "attivo": attivo
        })
        log_admin_action(r, "FORMAZIONE_MODIFICA_CORSO", f"Modificato corso ID: {corso_id} ('{titolo.strip()}')")

    return RedirectResponse(url=f"/formazione/corso/{corso_id}?success=" + urllib.parse.quote("Corso aggiornato con successo!"), status_code=303)


@router.post("/formazione/corso/{corso_id}/elimina")
def delete_corso(r: Request, corso_id: int):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Non hai i permessi per eliminare questo corso"), status_code=303)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM edizioni_formazione WHERE corso_id = :cid"), {"cid": corso_id})
        conn.execute(text("DELETE FROM corsi_formazione WHERE corso_id = :cid"), {"cid": corso_id})
        log_admin_action(r, "FORMAZIONE_ELIMINA_CORSO", f"Eliminato corso ID: {corso_id} e relative edizioni")

    return RedirectResponse(url="/formazione?success=" + urllib.parse.quote("Corso ed edizioni associate eliminati con successo!"), status_code=303)


@router.post("/formazione/corso/{corso_id}/edizioni/nuova")
def create_edizione(
    r: Request,
    corso_id: int,
    codice_edizione: Optional[str] = Form(""),
    data_inizio: str = Form(...),
    data_fine: Optional[str] = Form(None),
    ora: Optional[str] = Form(""),
    durata: Optional[str] = Form(""),
    tipo_localita: str = Form("online"),
    sede_id: Optional[int] = Form(None),
    luogo_custom: Optional[str] = Form(None),
    tutor: Optional[str] = Form(""),
    link_piattaforma: Optional[str] = Form(""),
    stato: str = Form("programmata"),
    note: Optional[str] = Form("")
):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url=f"/formazione/corso/{corso_id}?error=" + urllib.parse.quote("Non hai i permessi per aggiungere edizioni"), status_code=303)

    uid = user.get("id") or user.get("user_id")

    with engine.begin() as conn:
        if not codice_edizione or not codice_edizione.strip():
            count_exist = conn.execute(text("SELECT COUNT(*) FROM edizioni_formazione WHERE corso_id = :cid"), {"cid": corso_id}).scalar() or 0
            codice_edizione = f"Edizione {count_exist + 1}"
        else:
            codice_edizione = codice_edizione.strip()

        # Sanitize localita
        if tipo_localita == "online":
            sede_id = None
            luogo_custom = None
        elif tipo_localita == "sede":
            luogo_custom = None
        elif tipo_localita == "altro":
            sede_id = None

        conn.execute(text("""
            INSERT INTO edizioni_formazione (
                corso_id, codice_edizione, data_inizio, data_fine,
                ora, durata, tipo_localita, sede_id, luogo_custom,
                tutor, link_piattaforma, stato, note, creato_da_id, creato_il
            ) VALUES (
                :corso_id, :codice_edizione, :data_inizio, :data_fine,
                :ora, :durata, :tipo_localita, :sede_id, :luogo_custom,
                :tutor, :link_piattaforma, :stato, :note, :creato_da_id, :creato_il
            )
        """), {
            "corso_id": corso_id,
            "codice_edizione": codice_edizione,
            "data_inizio": data_inizio.strip(),
            "data_fine": data_fine.strip() if data_fine and data_fine.strip() else None,
            "ora": (ora or "").strip(),
            "durata": (durata or "").strip(),
            "tipo_localita": tipo_localita,
            "sede_id": sede_id if tipo_localita == "sede" else None,
            "luogo_custom": (luogo_custom or "").strip() if tipo_localita == "altro" else None,
            "tutor": (tutor or "").strip(),
            "link_piattaforma": (link_piattaforma or "").strip(),
            "stato": stato,
            "note": (note or "").strip(),
            "creato_da_id": uid,
            "creato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        new_ed_id = res.lastrowid
        log_admin_action(r, "FORMAZIONE_CREA_EDIZIONE", f"Creata edizione '{codice_edizione.strip()}' per corso ID: {corso_id} (ID ed: {new_ed_id})")

    return RedirectResponse(url=f"/formazione/corso/{corso_id}?success=" + urllib.parse.quote("Nuova edizione creata con successo!"), status_code=303)


@router.post("/formazione/edizione/{edizione_id}/modifica")
def update_edizione(
    r: Request,
    edizione_id: int,
    codice_edizione: str = Form(...),
    data_inizio: str = Form(...),
    data_fine: Optional[str] = Form(None),
    ora: Optional[str] = Form(""),
    durata: Optional[str] = Form(""),
    tipo_localita: str = Form("online"),
    sede_id: Optional[int] = Form(None),
    luogo_custom: Optional[str] = Form(None),
    tutor: Optional[str] = Form(""),
    link_piattaforma: Optional[str] = Form(""),
    stato: str = Form("programmata"),
    note: Optional[str] = Form("")
):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Non hai i permessi per modificare edizioni"), status_code=303)

    with engine.begin() as conn:
        corso_id = conn.execute(text("SELECT corso_id FROM edizioni_formazione WHERE edizione_id = :eid"), {"eid": edizione_id}).scalar()
        if not corso_id:
            return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Edizione non trovata"), status_code=303)

        if tipo_localita == "online":
            sede_id = None
            luogo_custom = None
        elif tipo_localita == "sede":
            luogo_custom = None
        elif tipo_localita == "altro":
            sede_id = None

        conn.execute(text("""
            UPDATE edizioni_formazione SET
                codice_edizione = :codice_edizione,
                data_inizio = :data_inizio,
                data_fine = :data_fine,
                ora = :ora,
                durata = :durata,
                tipo_localita = :tipo_localita,
                sede_id = :sede_id,
                luogo_custom = :luogo_custom,
                tutor = :tutor,
                link_piattaforma = :link_piattaforma,
                stato = :stato,
                note = :note
            WHERE edizione_id = :eid
        """), {
            "eid": edizione_id,
            "codice_edizione": codice_edizione.strip(),
            "data_inizio": data_inizio.strip(),
            "data_fine": data_fine.strip() if data_fine and data_fine.strip() else None,
            "ora": (ora or "").strip(),
            "durata": (durata or "").strip(),
            "tipo_localita": tipo_localita,
            "sede_id": sede_id if tipo_localita == "sede" else None,
            "luogo_custom": (luogo_custom or "").strip() if tipo_localita == "altro" else None,
            "tutor": (tutor or "").strip(),
            "link_piattaforma": (link_piattaforma or "").strip(),
            "stato": stato,
            "note": (note or "").strip()
        })
        log_admin_action(r, "FORMAZIONE_MODIFICA_EDIZIONE", f"Modificata edizione ID: {edizione_id} (corso ID: {corso_id}, codice: {codice_edizione.strip()})")

    return RedirectResponse(url=f"/formazione/corso/{corso_id}?success=" + urllib.parse.quote("Edizione modificata con successo!"), status_code=303)


@router.post("/formazione/edizione/{edizione_id}/elimina")
def delete_edizione(r: Request, edizione_id: int):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not CFG.get("modulo_formazione", False):
        return RedirectResponse(url="/?error=" + urllib.parse.quote("Modulo Formazione disabilitato"), status_code=303)
    if not user_is_train_manager(user):
        return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Non hai i permessi per eliminare edizioni"), status_code=303)

    with engine.begin() as conn:
        corso_id = conn.execute(text("SELECT corso_id FROM edizioni_formazione WHERE edizione_id = :eid"), {"eid": edizione_id}).scalar()
        if not corso_id:
            return RedirectResponse(url="/formazione?error=" + urllib.parse.quote("Edizione non trovata"), status_code=303)

        conn.execute(text("DELETE FROM edizioni_formazione WHERE edizione_id = :eid"), {"eid": edizione_id})
        log_admin_action(r, "FORMAZIONE_ELIMINA_EDIZIONE", f"Eliminata edizione ID: {edizione_id} (corso ID: {corso_id})")

    return RedirectResponse(url=f"/formazione/corso/{corso_id}?success=" + urllib.parse.quote("Edizione eliminata con successo!"), status_code=303)
