import os
from datetime import datetime
from typing import List
from fastapi import APIRouter, Request, Form, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, BASE_DIR, DB_DRIVER
from utils import require_superuser, save_upload

router = APIRouter()

@router.get("/admin/magazzini", response_class=HTMLResponse)
def admin_magazzini(r: Request, error: str = None, success: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        magazzini = c.execute(text("""
            SELECT m.magazzino_id, m.nome, s.nome AS sede_nome, c.nome AS categoria_nome, r.nome AS reparto_nome,
                   COALESCE(SUM(g.quantita), 0) AS totale_pezzi,
                   COUNT(g.materiale_id) AS totale_articoli
            FROM magazzini m
            LEFT JOIN sedi s ON m.sede_id = s.sede_id
            LEFT JOIN categorie c ON m.categoria_id = c.categoria_id
            LEFT JOIN reparti r ON m.reparto_id = r.reparto_id
            LEFT JOIN giacenze g ON m.magazzino_id = g.magazzino_id AND g.quantita > 0
            GROUP BY m.magazzino_id
            ORDER BY m.nome
        """)).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        categorie = c.execute(text("SELECT categoria_id, nome FROM categorie ORDER BY nome")).mappings().all()
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_magazzini.html", {"request": r, "cfg": CFG, "user": user, "magazzini": magazzini, "sedi": sedi, "categorie": categorie, "reparti": reparti, "error": error, "success": success})

@router.post("/admin/magazzino")
def add_magazzino(r: Request, nome: str = Form(...), sede_id: str = Form(None), categoria_id: str = Form(None), reparto_id: str = Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    sede_id_val = int(sede_id) if sede_id and str(sede_id).isdigit() else None
    categoria_id_val = int(categoria_id) if categoria_id and str(categoria_id).isdigit() else None
    reparto_id_val = int(reparto_id) if reparto_id and str(reparto_id).isdigit() else None
    with engine.begin() as c:
        c.execute(text("INSERT INTO magazzini (nome, sede_id, categoria_id, reparto_id) VALUES (:nome, :sede, :cat, :rep)"), 
                  {"nome": nome, "sede": sede_id_val, "cat": categoria_id_val, "rep": reparto_id_val})
    return RedirectResponse(url="/admin/magazzini", status_code=303)

@router.get("/admin/magazzino/{magazzino_id}/modifica", response_class=HTMLResponse)
def edit_magazzino_form(r: Request, magazzino_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).mappings().first()
        if not magazzino: return RedirectResponse(url="/admin/magazzini")
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        categorie = c.execute(text("SELECT categoria_id, nome FROM categorie ORDER BY nome")).mappings().all()
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "edit_magazzino.html", {"request": r, "cfg": CFG, "user": user, "magazzino": magazzino, "sedi": sedi, "categorie": categorie, "reparti": reparti})

@router.post("/admin/magazzino/{magazzino_id}/modifica")
def edit_magazzino_action(r: Request, magazzino_id: int, nome: str = Form(...), sede_id: str = Form(None), categoria_id: str = Form(None), reparto_id: str = Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    sede_id_val = int(sede_id) if sede_id and str(sede_id).isdigit() else None
    categoria_id_val = int(categoria_id) if categoria_id and str(categoria_id).isdigit() else None
    reparto_id_val = int(reparto_id) if reparto_id and str(reparto_id).isdigit() else None
    with engine.begin() as c:
        c.execute(text("UPDATE magazzini SET nome = :nome, sede_id = :sede, categoria_id = :cat, reparto_id = :rep WHERE magazzino_id = :id"),
                  {"nome": nome, "sede": sede_id_val, "cat": categoria_id_val, "rep": reparto_id_val, "id": magazzino_id})
    return RedirectResponse(url="/admin/magazzini", status_code=303)

@router.post("/admin/magazzino/delete")
def delete_magazzino(r: Request, magazzino_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        qta = c.execute(text("SELECT COALESCE(SUM(quantita), 0) FROM giacenze WHERE magazzino_id = :id"), {"id": magazzino_id}).scalar()
        if qta > 0:
            return RedirectResponse(url="/admin/magazzini?error=non_vuoto", status_code=303)
            
        c.execute(text("DELETE FROM giacenze WHERE magazzino_id = :id"), {"id": magazzino_id})
        c.execute(text("DELETE FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id})
    return RedirectResponse(url="/admin/magazzini?success=eliminato", status_code=303)

@router.post("/admin/magazzino/svuota")
def svuota_magazzino(r: Request, magazzino_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        c.execute(text("DELETE FROM giacenze WHERE magazzino_id = :id"), {"id": magazzino_id})
    return RedirectResponse(url="/admin/magazzini?success=svuotato", status_code=303)

# ===== GESTIONE MAGAZZINI LATO UTENTE =====

@router.get("/magazzini", response_class=HTMLResponse)
def user_magazzini_list(r: Request, magazzino_id: List[str] = Query(None), sede_id: str = None, q: str = None, solo_positive: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()

        is_initial_load = not any(k in r.query_params for k in ["magazzino_id", "sede_id", "q", "solo_positive"])
        if is_initial_load:
            if not user_mag_ids:
                solo_positive = "1"
                magazzino_id = []
            else:
                solo_positive = "0"
                magazzino_id = [str(uid) for uid in user_mag_ids]

        where_clauses = []
        params = {}
        
        if magazzino_id:
            mag_ids = [int(m) for m in magazzino_id if str(m).isdigit()]
            if mag_ids:
                where_clauses.append("m.magazzino_id IN :mag_ids")
                params["mag_ids"] = mag_ids
        if sede_id and sede_id.isdigit():
            where_clauses.append("m.sede_id = :sede_id")
            params["sede_id"] = int(sede_id)
        if q:
            where_clauses.append("mat.nome LIKE :q")
            params["q"] = f"%{q}%"
        if solo_positive == "1":
            where_clauses.append("COALESCE(g.quantita, 0) > 0")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        stmt = text(f"""
            SELECT m.magazzino_id, m.nome AS magazzino_nome, s.nome AS sede_nome,
                   mat.materiale_id, mat.nome AS materiale_nome, c.nome AS categoria_nome,
                   COALESCE(g.quantita, 0) AS quantita, COALESCE(mat.soglia_attenzione, 0) AS soglia_attenzione,
                   (SELECT COUNT(*) FROM trasferimenti WHERE stato = 'in_consegna' AND magazzino_dest_id = m.magazzino_id AND materiale_id = mat.materiale_id) AS trsf_in,
                   (SELECT COUNT(*) FROM trasferimenti WHERE stato = 'in_consegna' AND magazzino_partenza_id = m.magazzino_id AND materiale_id = mat.materiale_id) AS trsf_out
            FROM magazzini m
            JOIN materiali mat ON (m.categoria_id IS NULL OR m.categoria_id = mat.categoria_id)
            LEFT JOIN giacenze g ON m.magazzino_id = g.magazzino_id AND mat.materiale_id = g.materiale_id
            LEFT JOIN categorie c ON mat.categoria_id = c.categoria_id
            LEFT JOIN sedi s ON m.sede_id = s.sede_id
            {where_sql}
            ORDER BY m.nome, c.nome, mat.nome
        """)
        
        if "mag_ids" in params:
            from sqlalchemy import bindparam
            stmt = stmt.bindparams(bindparam("mag_ids", expanding=True))

        rows = c.execute(stmt, params).mappings().all()

        magazzini_list = c.execute(text("SELECT magazzino_id, nome FROM magazzini ORDER BY nome")).mappings().all()
        sedi_list = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()

        count_in_arrivo = 0
        if user.get("ruolo") in ("assistenza", "responsabile"):
            if user_mag_ids:
                from sqlalchemy import bindparam
                stmt_arrivo = text("SELECT COUNT(*) FROM trasferimenti WHERE magazzino_dest_id IN :mids AND stato = 'in_consegna'").bindparams(bindparam("mids", expanding=True))
                count_in_arrivo = c.execute(stmt_arrivo, {"mids": list(user_mag_ids)}).scalar() or 0
        elif user.get("ruolo") == "admin":
            count_in_arrivo = c.execute(text("SELECT COUNT(*) FROM trasferimenti WHERE stato = 'in_consegna'")).scalar() or 0

    msg = r.query_params.get("msg")
    trsf_id = r.query_params.get("trsf_id")
    print_pdf = r.query_params.get("print")

    return templates.TemplateResponse(r, "magazzini.html", {
        "request": r, "cfg": CFG, "user": user, 
        "righe": rows, "magazzini": magazzini_list, "sedi": sedi_list,
        "filtri": {"magazzino_id": magazzino_id or [], "sede_id": sede_id, "q": q, "solo_positive": solo_positive},
        "user_mag_ids": user_mag_ids, "count_in_arrivo": count_in_arrivo,
        "msg": msg, "trsf_id": trsf_id, "print_pdf": print_pdf
    })

@router.get("/magazzino/{magazzino_id}/giacenza/{materiale_id}", response_class=HTMLResponse)
def dettaglio_giacenza(r: Request, magazzino_id: int, materiale_id: int, error: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).mappings().first()
        materiale = c.execute(text("SELECT * FROM materiali WHERE materiale_id = :id"), {"id": materiale_id}).mappings().first()
        
        if not magazzino or not materiale:
            return RedirectResponse(url="/magazzini")
            
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True

        posizioni = c.execute(text("""
            SELECT p.posizione_fisica, p.quantita,
                   (SELECT marca FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = p.posizione_fisica
                    AND marca IS NOT NULL AND marca != ''
                    ORDER BY creato_il DESC LIMIT 1) as marca,
                   (SELECT modello FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = p.posizione_fisica
                    AND modello IS NOT NULL AND modello != ''
                    ORDER BY creato_il DESC LIMIT 1) as modello,
                   (SELECT allegato FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = p.posizione_fisica
                    AND allegato IS NOT NULL AND allegato != ''
                    AND (LOWER(allegato) LIKE '%.jpg' OR LOWER(allegato) LIKE '%.jpeg' OR LOWER(allegato) LIKE '%.png' OR LOWER(allegato) LIKE '%.gif' OR LOWER(allegato) LIKE '%.webp')
                    ORDER BY creato_il DESC LIMIT 1) as ultima_foto
            FROM (
                SELECT posizione_fisica, 
                       SUM(CASE WHEN operazione = 'carico' THEN quantita ELSE -quantita END) as quantita
                FROM movimenti_magazzino
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id
                GROUP BY posizione_fisica
                HAVING SUM(CASE WHEN operazione = 'carico' THEN quantita ELSE -quantita END) > 0
            ) p
            ORDER BY p.posizione_fisica
        """), {"mag_id": magazzino_id, "mat_id": materiale_id}).mappings().all()
        
        totale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag_id AND materiale_id = :mat_id"), 
                           {"mag_id": magazzino_id, "mat_id": materiale_id}).scalar() or 0

    return templates.TemplateResponse(r, "dettaglio_giacenza.html", {
        "request": r, "cfg": CFG, "user": user, 
        "magazzino": magazzino, "materiale": materiale, "posizioni": posizioni, "totale": totale, "can_edit": can_edit, "error": error
    })

@router.post("/magazzino/{magazzino_id}/materiale/{materiale_id}/foto")
async def magazzino_foto_posizione_action(r: Request, magazzino_id: int, materiale_id: int, posizione_fisica: str = Form(...), allegato: UploadFile = File(...)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    # Workaround per il bug di troncamento immagini > 1MB (SpooledTemporaryFile) su Windows
    if allegato and allegato.filename:
        content = await allegato.read()
        import io
        allegato.file = io.BytesIO(content)
        
    allegato_filename = save_upload(allegato)
    if not allegato_filename:
        return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}?error=upload_failed", status_code=303)

    from datetime import date
    oggi = date.today().isoformat()

    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, allegato, posizione_fisica)
            VALUES (:mag, :mat, :uid, 'foto', 0, :dt, 'Aggiornamento foto posizione', :all, :pos)
        """), {"mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "dt": oggi, "all": allegato_filename, "pos": posizione_fisica})

    return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

@router.post("/magazzino/{magazzino_id}/materiale/{materiale_id}/rinomina-posizione")
def magazzino_rinomina_posizione(
    r: Request, 
    magazzino_id: int, 
    materiale_id: int, 
    old_posizione: str = Form(...), 
    new_posizione: str = Form(...),
    marca: str = Form(""),
    modello: str = Form("")
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True
            
        if not can_edit:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

        if new_posizione and old_posizione:
            new_pos_clean = new_posizione.strip()
            if len(new_pos_clean) < 3:
                return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}?error=posizione_invalida", status_code=303)
            
            marca_clean = (marca or "").strip()
            modello_clean = (modello or "").strip()
            
            c.execute(text("""
                UPDATE movimenti_magazzino 
                SET posizione_fisica = :new_pos, marca = :marca, modello = :modello
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = :old_pos
            """), {
                "new_pos": new_pos_clean, 
                "marca": marca_clean, 
                "modello": modello_clean, 
                "mag_id": magazzino_id, 
                "mat_id": materiale_id, 
                "old_pos": old_posizione
            })
            
    return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

@router.post("/magazzino/{magazzino_id}/materiale/{materiale_id}/trasferisci-posizione")
def magazzino_trasferisci_posizione(
    r: Request, 
    magazzino_id: int, 
    materiale_id: int, 
    from_posizione: str = Form(...), 
    to_posizione: str = Form(...), 
    quantita: int = Form(...)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True
            
        if not can_edit:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)
            
        from_pos_clean = (from_posizione or "").strip()
        to_pos_clean = (to_posizione or "").strip()
        
        if len(to_pos_clean) < 3 or any(c.isspace() for c in to_pos_clean):
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}?error=posizione_invalida", status_code=303)
            
        if quantita <= 0:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}?error=quantita_invalida", status_code=303)
            
        # Verify quantity available in from_posizione
        pos_info = c.execute(text("""
            SELECT SUM(CASE WHEN operazione = 'carico' THEN quantita ELSE -quantita END) as quantita,
                   (SELECT marca FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
                    AND marca IS NOT NULL AND marca != ''
                    ORDER BY creato_il DESC LIMIT 1) as marca,
                   (SELECT modello FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
                    AND modello IS NOT NULL AND modello != ''
                    ORDER BY creato_il DESC LIMIT 1) as modello
            FROM movimenti_magazzino
            WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
            GROUP BY posizione_fisica
        """), {"mag": magazzino_id, "mat": materiale_id, "pos": from_pos_clean}).mappings().first()
        
        disponibile = pos_info["quantita"] if pos_info else 0
        from_marca = pos_info["marca"] if pos_info and pos_info["marca"] else ""
        from_modello = pos_info["modello"] if pos_info and pos_info["modello"] else ""
        
        if quantita > disponibile:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}?error=insufficient_stock", status_code=303)
            
        from datetime import date
        oggi = date.today().isoformat()
        
        # 1. Scarico from the source position
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, posizione_fisica, marca, modello)
            VALUES (:mag, :mat, :uid, 'scarico', :q, :dt, :desc, :pos, :marca, :modello)
        """), {
            "mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "q": quantita, "dt": oggi,
            "desc": f"Trasferimento interno verso posizione {to_pos_clean}", "pos": from_pos_clean,
            "marca": from_marca, "modello": from_modello
        })
        
        # 2. Carico to the destination position
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, posizione_fisica, marca, modello)
            VALUES (:mag, :mat, :uid, 'carico', :q, :dt, :desc, :pos, :marca, :modello)
        """), {
            "mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "q": quantita, "dt": oggi,
            "desc": f"Trasferimento interno da posizione {from_pos_clean}", "pos": to_pos_clean,
            "marca": from_marca, "modello": from_modello
        })
        
    return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

@router.get("/magazzino/{magazzino_id}/movimento/{materiale_id}", response_class=HTMLResponse)
def magazzino_movimento_form(
    r: Request, magazzino_id: int, materiale_id: int, operazione: str,
    richiesta_id: int = None, error: str = None,
    quantita: int = None, marca: str = None, modello: str = None,
    descrizione: str = None, trasferimento_id: int = None
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True
            
        if not can_edit:
            return RedirectResponse(url="/magazzini")
            
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).mappings().first()
        materiale = c.execute(text("SELECT * FROM materiali WHERE materiale_id = :id"), {"id": materiale_id}).mappings().first()
        
        if magazzino.get("categoria_id") and magazzino["categoria_id"] != materiale.get("categoria_id"):
            return RedirectResponse(url="/magazzini")
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        magazzini_dest = c.execute(text("""
            SELECT magazzino_id, nome FROM magazzini 
            WHERE magazzino_id != :id AND (categoria_id IS NULL OR categoria_id = :mat_cat)
            ORDER BY nome
        """), {"id": magazzino_id, "mat_cat": materiale.get("categoria_id")}).mappings().all()
        
        posizioni = []
        if operazione == "scarico":
            posizioni = c.execute(text("""
                SELECT p.posizione_fisica, p.quantita,
                       (SELECT marca FROM movimenti_magazzino 
                        WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = p.posizione_fisica
                        AND marca IS NOT NULL AND marca != ''
                        ORDER BY creato_il DESC LIMIT 1) as marca,
                       (SELECT modello FROM movimenti_magazzino 
                        WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = p.posizione_fisica
                        AND modello IS NOT NULL AND modello != ''
                        ORDER BY creato_il DESC LIMIT 1) as modello
                FROM (
                    SELECT posizione_fisica, 
                           SUM(CASE WHEN operazione = 'carico' THEN quantita ELSE -quantita END) as quantita
                    FROM movimenti_magazzino 
                    WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica IS NOT NULL AND posizione_fisica != ''
                    GROUP BY posizione_fisica
                ) p
            """), {"mag_id": magazzino_id, "mat_id": materiale_id}).mappings().all()
        else:
            # Per il carico, selezioniamo tutte le posizioni attualmente attive in questo magazzino
            posizioni = c.execute(text("""
                SELECT DISTINCT posizione_fisica
                FROM movimenti_magazzino
                WHERE magazzino_id = :mag_id AND posizione_fisica IS NOT NULL AND posizione_fisica != ''
                ORDER BY posizione_fisica
            """), {"mag_id": magazzino_id}).scalars().all()
            
        richiesta = None
        if operazione == "scarico" and richiesta_id:
            richiesta = c.execute(text("SELECT * FROM richieste_materiale WHERE richiesta_id = :id"), {"id": richiesta_id}).mappings().first()
            
        from datetime import date
        oggi = date.today().isoformat()

        # Trova tutti i magazzini abilitati per questo operatore compatibili con la categoria del materiale
        mat_cat = materiale.get("categoria_id")
        if user.get("ruolo") == "admin":
            magazzini_abilitati = c.execute(text("""
                SELECT magazzino_id, nome FROM magazzini
                WHERE (categoria_id IS NULL OR categoria_id = :mat_cat)
                ORDER BY nome
            """), {"mat_cat": mat_cat}).mappings().all()
        else:
            magazzini_abilitati = c.execute(text("""
                SELECT m.magazzino_id, m.nome 
                FROM magazzini m
                JOIN operatori_magazzini om ON m.magazzino_id = om.magazzino_id
                WHERE om.user_id = :uid AND (m.categoria_id IS NULL OR m.categoria_id = :mat_cat)
                ORDER BY m.nome
            """), {"uid": user.get("id"), "mat_cat": mat_cat}).mappings().all()
        
    template_file = "magazzino_carico.html" if operazione == "carico" else "magazzino_scarico.html"
    return templates.TemplateResponse(r, template_file, {
        "request": r, "cfg": CFG, "user": user, 
        "magazzino": magazzino, "materiale": materiale,
        "operazione": operazione, "sedi": sedi, "magazzini_dest": magazzini_dest, "oggi": oggi, "posizioni": posizioni, "richiesta": richiesta, "error": error,
        "magazzini_abilitati": magazzini_abilitati,
        "quantita": quantita, "marca": marca, "modello": modello,
        "descrizione": descrizione, "trasferimento_id": trasferimento_id
    })

@router.post("/magazzino/{magazzino_id}/movimento/{materiale_id}")
async def magazzino_movimento_action(
    r: Request, magazzino_id: int, materiale_id: int, operazione: str = Form(...), quantita: int = Form(...),
    data_movimento: str = Form(...), descrizione: str = Form(""), 
    sede_assegnazione_id: str = Form(None), posizione_fisica: str = Form(""),
    marca: str = Form(""), modello: str = Form(""),
    magazzino_destinazione_id: str = Form(None),
    allegato: UploadFile = File(None),
    genera_pdf: str = Form(None),
    richiesta_id: str = Form(None),
    trasferimento_id: str = Form(None)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    pos_clean = (posizione_fisica or "").strip()
    if len(pos_clean) < 3:
        richiesta_clause = f"&richiesta_id={richiesta_id}" if (richiesta_id and str(richiesta_id).isdigit()) else ""
        return RedirectResponse(
            url=f"/magazzino/{magazzino_id}/movimento/{materiale_id}?operazione={operazione}&error=posizione_invalida{richiesta_clause}",
            status_code=303
        )
    
    # Workaround per il bug di troncamento immagini > 1MB (SpooledTemporaryFile) su Windows
    if allegato and allegato.filename:
        content = await allegato.read()
        import io
        allegato.file = io.BytesIO(content)

    allegato_filename = save_upload(allegato)

    with engine.begin() as c:
        if operazione == "scarico" and richiesta_id and str(richiesta_id).isdigit():
            rid = int(richiesta_id)
            richiesta = c.execute(text("SELECT * FROM richieste_materiale WHERE richiesta_id = :id"), {"id": rid}).mappings().first()
            if richiesta:
                if richiesta["ticket_id"]:
                    ticket_stato = c.execute(text("SELECT stato FROM tickets WHERE ticket_id = :id"), {"id": richiesta["ticket_id"]}).scalar()
                    if ticket_stato != 'presa_in_carico':
                        return RedirectResponse(url=f"/ticket/{richiesta['ticket_id']}?error=not_taken_in_charge", status_code=303)
                quantita = richiesta["quantita"]
                sede_assegnazione_id = str(richiesta["sede_dest_id"])
                magazzino_destinazione_id = None

        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True
            
        if not can_edit or quantita <= 0:
            return RedirectResponse(url="/magazzini", status_code=303)

        if operazione == "scarico":
            pos_info = c.execute(text("""
                SELECT marca, modello FROM movimenti_magazzino
                WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
                AND (marca IS NOT NULL AND marca != '' OR modello IS NOT NULL AND modello != '')
                ORDER BY creato_il DESC LIMIT 1
            """), {"mag": magazzino_id, "mat": materiale_id, "pos": pos_clean}).mappings().first()
            if pos_info:
                marca = pos_info["marca"] or ""
                modello = pos_info["modello"] or ""

        mag_cat = c.execute(text("SELECT categoria_id FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).scalar()
        mat_cat = c.execute(text("SELECT categoria_id FROM materiali WHERE materiale_id = :id"), {"id": materiale_id}).scalar()
        if mag_cat and mag_cat != mat_cat:
            return RedirectResponse(url="/magazzini", status_code=303)

        row = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                        {"mag": magazzino_id, "mat": materiale_id}).first()
        qta_attuale = row[0] if row is not None else 0

        nuova_qta = max(0, qta_attuale - quantita) if operazione == "scarico" else qta_attuale + quantita

        if row is None:
            c.execute(text("INSERT INTO giacenze (magazzino_id, materiale_id, quantita) VALUES (:mag, :mat, :q)"),
                      {"mag": magazzino_id, "mat": materiale_id, "q": nuova_qta})
        else:
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": magazzino_id, "mat": materiale_id})

        if operazione == "carico" and trasferimento_id and str(trasferimento_id).isdigit():
            trsf_id = int(trasferimento_id)
            if not allegato_filename:
                trsf_all = c.execute(text("SELECT allegato FROM trasferimenti WHERE trasferimento_id = :id"), {"id": trsf_id}).scalar()
                if trsf_all:
                    allegato_filename = trsf_all
            c.execute(text("UPDATE trasferimenti SET stato = 'completato', data_arrivo = :now, user_arrivo_id = :uid WHERE trasferimento_id = :id"),
                      {"now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "uid": user["id"], "id": trsf_id})

        mag_dest_id_val = int(magazzino_destinazione_id) if magazzino_destinazione_id and str(magazzino_destinazione_id).isdigit() else None
        desc_source = descrizione
        
        if operazione == "scarico" and mag_dest_id_val:
            dest_mag_name = c.execute(text("SELECT nome FROM magazzini WHERE magazzino_id = :id"), {"id": mag_dest_id_val}).scalar()
            
            if dest_mag_name:
                desc_source = f"[Spedizione verso {dest_mag_name}] {descrizione}"

        sede_id_val = int(sede_assegnazione_id) if sede_assegnazione_id and str(sede_assegnazione_id).isdigit() else None
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, sede_assegnazione_id, posizione_fisica, marca, modello, allegato)
            VALUES (:mag, :mat, :uid, :op, :q, :dt, :desc, :sede, :pos, :marca, :modello, :all)
        """), {
            "mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "op": operazione, 
            "q": quantita, "dt": data_movimento, "desc": desc_source, 
            "sede": sede_id_val, "pos": pos_clean, "marca": marca, "modello": modello, "all": allegato_filename
        })
        
        trsf_id_val = None
        if operazione == "scarico" and mag_dest_id_val:
            c.execute(text("""
                INSERT INTO trasferimenti (magazzino_partenza_id, magazzino_dest_id, materiale_id, quantita, user_partenza_id, note, allegato, marca, modello, posizione_partenza)
                VALUES (:partenza, :dest, :mat, :q, :uid, :note, :all, :marca, :modello, :pos)
            """), {
                "partenza": magazzino_id, "dest": mag_dest_id_val, "mat": materiale_id,
                "q": quantita, "uid": user["id"], "note": descrizione, "all": allegato_filename,
                "marca": marca, "modello": modello, "pos": pos_clean
            })
            if DB_DRIVER.startswith("sqlite"):
                trsf_id_val = c.execute(text("SELECT last_insert_rowid()")).scalar()
            elif DB_DRIVER.startswith("mysql"):
                trsf_id_val = c.execute(text("SELECT LAST_INSERT_ID()")).scalar()
            else:
                trsf_id_val = c.execute(text("SELECT LASTVAL()")).scalar()
            
        if operazione == "scarico" and richiesta_id and str(richiesta_id).isdigit():
            rid = int(richiesta_id)
            c.execute(text("UPDATE richieste_materiale SET stato = 'evasa', magazzino_id = :mag_id WHERE richiesta_id = :id"), {"id": rid, "mag_id": magazzino_id})
            richiesta_ticket = c.execute(text("SELECT ticket_id FROM richieste_materiale WHERE richiesta_id = :id"), {"id": rid}).mappings().first()
            if richiesta_ticket and richiesta_ticket["ticket_id"]:
                autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
                mat_nome = c.execute(text("SELECT nome FROM materiali WHERE materiale_id = :mid"), {"mid": materiale_id}).scalar()
                testo = f"Richiesta materiale evasa dal magazzino: {quantita}x {mat_nome}."
                c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo, is_internal) VALUES (:tid, :a, :t, 0)"""),
                         {"tid": richiesta_ticket["ticket_id"], "a": f"Sistema ({autore})", "t": testo})
            
        if operazione == "scarico":
            if mag_dest_id_val and trsf_id_val:
                print_param = "&print=1" if genera_pdf == "1" else ""
                return RedirectResponse(url=f"/magazzini?msg=trasferimento_avviato&trsf_id={trsf_id_val}{print_param}", status_code=303)
            elif genera_pdf == "1":
                mov_id = c.execute(text("""
                    SELECT movimento_id FROM movimenti_magazzino
                    WHERE user_id = :uid AND magazzino_id = :mag AND materiale_id = :mat AND operazione = 'scarico'
                    ORDER BY movimento_id DESC LIMIT 1
                """), {"uid": user["id"], "mag": magazzino_id, "mat": materiale_id}).scalar()
                if mov_id:
                    return RedirectResponse(url=f"/stampa-consegna/scarico/{mov_id}", status_code=303)
            
    if operazione == "scarico" and richiesta_id:
        return RedirectResponse(url="/richieste-materiale", status_code=303)
    if operazione == "carico" and trasferimento_id:
        return RedirectResponse(url="/trasferimenti", status_code=303)
    return RedirectResponse(url="/magazzini", status_code=303)

@router.get("/stampa-consegna/multiplo/{gruppo_scarico}", response_class=HTMLResponse)
def stampa_consegna_multiplo(r: Request, gruppo_scarico: str):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        movements = c.execute(text("""
            SELECT m.*, mag.nome AS magazzino_nome, s.nome AS sede_nome,
                   mat.nome AS materiale_nome, u.nome AS user_nome, u.cognome AS user_cognome,
                   u.telefono AS user_telefono, s_orig.nome AS magazzino_sede_nome
            FROM movimenti_magazzino m
            JOIN magazzini mag ON m.magazzino_id = mag.magazzino_id
            LEFT JOIN sedi s_orig ON mag.sede_id = s_orig.sede_id
            LEFT JOIN sedi s ON m.sede_assegnazione_id = s.sede_id
            JOIN materiali mat ON m.materiale_id = mat.materiale_id
            JOIN users u ON m.user_id = u.user_id
            WHERE m.gruppo_scarico = :grp AND m.operazione = 'scarico'
            ORDER BY m.movimento_id ASC
        """), {"grp": gruppo_scarico}).mappings().all()
        
        if not movements:
            return RedirectResponse(url="/magazzini")
            
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user["id"]}).scalars().all()
            has_permission = False
            for mov in movements:
                if mov["magazzino_id"] in user_mag_ids:
                    has_permission = True
                    break
            if not has_permission:
                return RedirectResponse(url="/magazzini")
                
    representative_mov = movements[0]
    
    return templates.TemplateResponse(r, "stampa_consegna.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "mov": representative_mov,
        "movements": movements,
        "is_multiplo": True,
        "tipo": "scarico"
    })

@router.get("/stampa-consegna/trasferimento/{trasferimento_id}", response_class=HTMLResponse)
def stampa_ddt(r: Request, trasferimento_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.connect() as c:
        t = c.execute(text("""
            SELECT t.*, 
                   mp.nome AS magazzino_partenza_nome,
                   sp.nome AS magazzino_partenza_sede,
                   md.nome AS magazzino_dest_nome,
                   sd.nome AS magazzino_dest_sede,
                   mat.nome AS materiale_nome,
                   u_part.nome AS user_partenza_nome, u_part.cognome AS user_partenza_cognome,
                   u_arr.nome AS user_arrivo_nome, u_arr.cognome AS user_arrivo_cognome
            FROM trasferimenti t
            JOIN magazzini mp ON t.magazzino_partenza_id = mp.magazzino_id
            LEFT JOIN sedi sp ON mp.sede_id = sp.sede_id
            JOIN magazzini md ON t.magazzino_dest_id = md.magazzino_id
            LEFT JOIN sedi sd ON md.sede_id = sd.sede_id
            JOIN materiali mat ON t.materiale_id = mat.materiale_id
            JOIN users u_part ON t.user_partenza_id = u_part.user_id
            LEFT JOIN users u_arr ON t.user_arrivo_id = u_arr.user_id
            WHERE t.trasferimento_id = :id
        """), {"id": trasferimento_id}).mappings().first()
        
        if not t:
            return RedirectResponse(url="/trasferimenti")
            
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user["id"]}).scalars().all()
            if t["magazzino_partenza_id"] not in user_mag_ids and t["magazzino_dest_id"] not in user_mag_ids:
                return RedirectResponse(url="/trasferimenti")
                
    return templates.TemplateResponse(r, "stampa_ddt.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "t": t
    })

@router.get("/stampa-consegna/{tipo}/{doc_id}", response_class=HTMLResponse)
def stampa_consegna(r: Request, tipo: str, doc_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        if tipo == 'scarico':
            mov = c.execute(text("""
                SELECT m.*, mag.nome AS magazzino_nome, s.nome AS sede_nome,
                       mat.nome AS materiale_nome, u.nome AS user_nome, u.cognome AS user_cognome,
                       u.telefono AS user_telefono, s_orig.nome AS magazzino_sede_nome
                FROM movimenti_magazzino m
                JOIN magazzini mag ON m.magazzino_id = mag.magazzino_id
                LEFT JOIN sedi s_orig ON mag.sede_id = s_orig.sede_id
                LEFT JOIN sedi s ON m.sede_assegnazione_id = s.sede_id
                JOIN materiali mat ON m.materiale_id = mat.materiale_id
                JOIN users u ON m.user_id = u.user_id
                WHERE m.movimento_id = :id AND m.operazione = 'scarico'
            """), {"id": doc_id}).mappings().first()
        else:
            return RedirectResponse(url="/magazzini")

        if not mov:
            return RedirectResponse(url="/magazzini")
            
    return templates.TemplateResponse(r, "stampa_consegna.html", {
        "request": r, "cfg": CFG, "user": user, "mov": mov, "tipo": tipo
    })

@router.get("/trasferimenti", response_class=HTMLResponse)
def trasferimenti_list(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.connect() as c:
        where_clause = "1=1"
        params = {}
        user_mag_ids = []
        
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if user_mag_ids:
                where_clause += " AND (t.magazzino_dest_id IN :mids OR t.magazzino_partenza_id IN :mids)"
                params["mids"] = list(user_mag_ids)
            else:
                where_clause += " AND 1=0"
            
        stmt = text(f"""
            SELECT t.*, 
                   mp.nome AS magazzino_partenza,
                   md.nome AS magazzino_destinazione,
                   mat.nome AS materiale_nome,
                   u.nome AS user_nome, u.cognome AS user_cognome
            FROM trasferimenti t
            JOIN magazzini mp ON t.magazzino_partenza_id = mp.magazzino_id
            JOIN magazzini md ON t.magazzino_dest_id = md.magazzino_id
            JOIN materiali mat ON t.materiale_id = mat.materiale_id
            JOIN users u ON t.user_partenza_id = u.user_id
            WHERE {where_clause}
            ORDER BY t.stato DESC, t.creato_il DESC
        """)
        if user.get("ruolo") != "admin" and user_mag_ids:
            from sqlalchemy import bindparam
            stmt = stmt.bindparams(bindparam("mids", expanding=True))
            
        trasferimenti = c.execute(stmt, params).mappings().all()
        
    return templates.TemplateResponse(r, "trasferimenti.html", {"request": r, "cfg": CFG, "user": user, "trasferimenti": trasferimenti, "user_mag_ids": user_mag_ids})

@router.post("/trasferimenti/{trasferimento_id}/annulla")
def annulla_trasferimento(r: Request, trasferimento_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.begin() as c:
        t = c.execute(text("SELECT * FROM trasferimenti WHERE trasferimento_id = :id AND stato = 'in_consegna'"), {"id": trasferimento_id}).mappings().first()
        if not t:
            return RedirectResponse(url="/trasferimenti", status_code=303)
            
        can_cancel = False
        if user.get("ruolo") == "admin":
            can_cancel = True
        else:
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if t["magazzino_partenza_id"] in user_mag_ids or t["magazzino_dest_id"] in user_mag_ids:
                can_cancel = True
                
        if not can_cancel:
            return RedirectResponse(url="/trasferimenti", status_code=303)
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        oggi = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Update transfer status to 'annullato'
        c.execute(text("UPDATE trasferimenti SET stato = 'annullato', data_arrivo = :now, user_arrivo_id = :uid WHERE trasferimento_id = :id"),
                  {"now": now_str, "uid": user["id"], "id": trasferimento_id})
                  
        # 2. Restore inventory at departure warehouse
        row = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                        {"mag": t["magazzino_partenza_id"], "mat": t["materiale_id"]}).first()
        
        if row is None:
            c.execute(text("INSERT INTO giacenze (magazzino_id, materiale_id, quantita) VALUES (:mag, :mat, :q)"),
                      {"mag": t["magazzino_partenza_id"], "mat": t["materiale_id"], "q": t["quantita"]})
        else:
            nuova_qta = row[0] + t["quantita"]
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": t["magazzino_partenza_id"], "mat": t["materiale_id"]})
                      
        # 3. Create compensating carico movement in movimenti_magazzino
        desc_cancel = f"[Annullamento Trasferimento #{trasferimento_id}]"
        if t["note"]:
            desc_cancel += f" {t['note']}"
            
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, posizione_fisica, marca, modello, allegato)
            VALUES (:mag, :mat, :uid, 'carico', :q, :dt, :desc, :pos, :marca, :modello, :all)
        """), {
            "mag": t["magazzino_partenza_id"], "mat": t["materiale_id"], "uid": user["id"], 
            "q": t["quantita"], "dt": oggi, "desc": desc_cancel, 
            "pos": t["posizione_partenza"], "marca": t["marca"], "modello": t["modello"], "all": t["allegato"]
        })
        
    return RedirectResponse(url="/trasferimenti?msg=annullato", status_code=303)

@router.get("/log-magazzini", response_class=HTMLResponse)
def log_magazzini(r: Request, magazzino_id: str = None, categoria_id: str = None, materiale_id: str = None, operazione: str = None, data_dal: str = None, data_al: str = None, q: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        where_clauses = []
        params = {}
        
        use_expanding = False
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if user_mag_ids:
                where_clauses.append("mm.magazzino_id IN :user_mag_ids")
                params["user_mag_ids"] = list(user_mag_ids)
                use_expanding = True
            else:
                where_clauses.append("1 = 0")
                
        if magazzino_id and magazzino_id.isdigit():
            where_clauses.append("mm.magazzino_id = :mag_id")
            params["mag_id"] = int(magazzino_id)
        if categoria_id and categoria_id.isdigit():
            where_clauses.append("mat.categoria_id = :cat_id")
            params["cat_id"] = int(categoria_id)
        if materiale_id and materiale_id.isdigit():
            where_clauses.append("mm.materiale_id = :mat_id")
            params["mat_id"] = int(materiale_id)
        if operazione:
            where_clauses.append("mm.operazione = :op")
            params["op"] = operazione
        if data_dal:
            where_clauses.append("mm.data_movimento >= :data_dal")
            params["data_dal"] = data_dal
        if data_al:
            where_clauses.append("mm.data_movimento <= :data_al")
            params["data_al"] = data_al
        if q:
            where_clauses.append("(mm.descrizione LIKE :q OR mat.nome LIKE :q OR mm.marca LIKE :q OR mm.modello LIKE :q OR mm.posizione_fisica LIKE :q)")
            params["q"] = f"%{q}%"

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        
        stmt = text(f"""
            SELECT mm.*, mat.nome as materiale_nome, c.nome as categoria_nome, u.nome as user_nome, u.cognome as user_cognome, s.nome as sede_nome, mag.nome as magazzino_nome
            FROM movimenti_magazzino mm
            JOIN materiali mat ON mm.materiale_id = mat.materiale_id
            LEFT JOIN categorie c ON mat.categoria_id = c.categoria_id
            JOIN users u ON mm.user_id = u.user_id
            LEFT JOIN sedi s ON mm.sede_assegnazione_id = s.sede_id
            JOIN magazzini mag ON mm.magazzino_id = mag.magazzino_id
            {where_sql}
            ORDER BY mm.creato_il DESC
        """)
        if use_expanding:
            from sqlalchemy import bindparam
            stmt = stmt.bindparams(bindparam("user_mag_ids", expanding=True))
            
        movimenti = c.execute(stmt, params).mappings().all()
        
        magazzini = c.execute(text("SELECT magazzino_id, nome FROM magazzini ORDER BY nome")).mappings().all()
        categorie = c.execute(text("SELECT categoria_id, nome FROM categorie ORDER BY nome")).mappings().all()
        materiali = c.execute(text("SELECT materiale_id, nome FROM materiali ORDER BY nome")).mappings().all()
        
        filtri = {
            "magazzino_id": magazzino_id,
            "categoria_id": categoria_id,
            "materiale_id": materiale_id,
            "operazione": operazione,
            "data_dal": data_dal,
            "data_al": data_al,
            "q": q
        }

    return templates.TemplateResponse(r, "log_magazzini.html", {
        "request": r, "cfg": CFG, "user": user, 
        "movimenti": movimenti, "magazzini": magazzini, 
        "categorie": categorie, "materiali": materiali, "filtri": filtri
    })

@router.get("/richieste-materiale", response_class=HTMLResponse)
def richieste_materiale_list(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        where_clause = "1=1"
        params = {}
        user_mag_ids = []
        use_expanding = False
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if user_mag_ids:
                where_clause = "rm.magazzino_id IN :mids"
                params = {"mids": list(user_mag_ids)}
                use_expanding = True
            else:
                where_clause = "1=0"
                params = {}
                
        stmt = text(f"""
            SELECT rm.*, m.nome as materiale_nome, c.nome as categoria_nome, s.nome as sede_nome, mag.nome as magazzino_nome,
                   u.nome as req_nome, u.cognome as req_cognome
            FROM richieste_materiale rm
            JOIN materiali m ON rm.materiale_id = m.materiale_id
            JOIN categorie c ON rm.categoria_id = c.categoria_id
            JOIN sedi s ON rm.sede_dest_id = s.sede_id
            JOIN users u ON rm.user_id = u.user_id
            LEFT JOIN magazzini mag ON rm.magazzino_id = mag.magazzino_id
            WHERE {where_clause}
            ORDER BY rm.creato_il DESC
        """)
        if use_expanding:
            from sqlalchemy import bindparam
            stmt = stmt.bindparams(bindparam("mids", expanding=True))
            
        richieste = c.execute(stmt, params).mappings().all()
        
    return templates.TemplateResponse(r, "richieste_materiale.html", {"request": r, "cfg": CFG, "user": user, "richieste": richieste, "user_mag_ids": user_mag_ids})

@router.get("/richiesta-materiale/nuova", response_class=HTMLResponse)
def nuova_richiesta_materiale_form(r: Request, ticket_id: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if not ticket_id or not str(ticket_id).isdigit():
        return RedirectResponse(url="/richieste-materiale")
        
    with engine.connect() as c:
        ticket = c.execute(text("SELECT ticket_id, stato FROM tickets WHERE ticket_id = :id"), {"id": int(ticket_id)}).mappings().first()
        if not ticket:
            return RedirectResponse(url="/richieste-materiale")
        if ticket["stato"] != 'presa_in_carico':
            return RedirectResponse(url=f"/ticket/{ticket_id}?error=not_taken_in_charge", status_code=303)
            
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        categorie = c.execute(text("SELECT categoria_id, nome FROM categorie ORDER BY nome")).mappings().all()
        materiali = c.execute(text("SELECT materiale_id, nome, categoria_id FROM materiali ORDER BY nome")).mappings().all()
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if user_mag_ids:
                from sqlalchemy import bindparam
                stmt = text("""
                    SELECT magazzino_id, nome, categoria_id 
                    FROM magazzini 
                    WHERE magazzino_id IN :mids 
                    ORDER BY nome
                """).bindparams(bindparam("mids", expanding=True))
                magazzini = c.execute(stmt, {"mids": list(user_mag_ids)}).mappings().all()
            else:
                magazzini = []
        else:
            magazzini = c.execute(text("SELECT magazzino_id, nome, categoria_id FROM magazzini ORDER BY nome")).mappings().all()
        
        giacenze_raw = c.execute(text("SELECT magazzino_id, materiale_id, quantita FROM giacenze")).mappings().all()
        giacenze_json = []
        for g in giacenze_raw:
            giacenze_json.append({"magazzino_id": g["magazzino_id"], "materiale_id": g["materiale_id"], "quantita": int(g["quantita"]) if g["quantita"] is not None else 0})
            
        import json
        giacenze_json_str = json.dumps(giacenze_json)
        
    return templates.TemplateResponse(r, "nuova_richiesta_materiale.html", {
        "request": r, "cfg": CFG, "user": user, "sedi": sedi, "categorie": categorie, "materiali": materiali,
        "magazzini": magazzini, "giacenze_json": giacenze_json_str, "ticket_id": ticket_id
    })

@router.post("/richiesta-materiale/nuova")
def nuova_richiesta_materiale_action(r: Request, sede_dest_id: int = Form(...), categoria_id: int = Form(...), 
                                     materiale_id: int = Form(...), magazzino_id: str = Form(None), quantita: int = Form(...), ticket_id: str = Form(None)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    ticket_id_val = int(ticket_id) if ticket_id and str(ticket_id).isdigit() else None
    if not ticket_id_val:
        return RedirectResponse(url="/richieste-materiale", status_code=303)
        
    magazzino_id_val = int(magazzino_id) if magazzino_id and str(magazzino_id).isdigit() else None
    
    if user.get("ruolo") != "admin" and magazzino_id_val:
        with engine.connect() as c_sec:
            is_valid = c_sec.execute(text("""
                SELECT 1 FROM operatori_magazzini 
                WHERE user_id = :uid AND magazzino_id = :mid
            """), {"uid": user.get("id"), "mid": magazzino_id_val}).scalar()
            if not is_valid:
                magazzino_id_val = None
                
    with engine.begin() as c:
        ticket = c.execute(text("SELECT ticket_id, stato FROM tickets WHERE ticket_id = :id"), {"id": ticket_id_val}).mappings().first()
        if not ticket:
            return RedirectResponse(url="/richieste-materiale", status_code=303)
        if ticket["stato"] != 'presa_in_carico':
            return RedirectResponse(url=f"/ticket/{ticket_id_val}?error=not_taken_in_charge", status_code=303)
            
        stato = 'nuova'
        if magazzino_id_val:
            giacenza = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"),
                                 {"mag": magazzino_id_val, "mat": materiale_id}).scalar() or 0
            if giacenza >= quantita:
                stato = 'pronta_per_scarico'
                
        c.execute(text("""
            INSERT INTO richieste_materiale (user_id, sede_dest_id, categoria_id, materiale_id, quantita, magazzino_id, ticket_id, stato)
            VALUES (:uid, :sede, :cat, :mat, :q, :mag, :tid, :stato)
        """), {
            "uid": user["id"], "sede": sede_dest_id, "cat": categoria_id, "mat": materiale_id,
            "q": quantita, "mag": magazzino_id_val, "tid": ticket_id_val, "stato": stato
        })
        
        if ticket_id_val:
            autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
            mat_nome = c.execute(text("SELECT nome FROM materiali WHERE materiale_id = :mid"), {"mid": materiale_id}).scalar()
            testo = f"Creata nuova richiesta di materiale: {quantita}x {mat_nome}."
            c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo, is_internal) VALUES (:tid, :a, :t, 0)"""),
                     {"tid": ticket_id_val, "a": f"Sistema ({autore})", "t": testo})

    if ticket_id_val:
        return RedirectResponse(url=f"/ticket/{ticket_id_val}", status_code=303)
    return RedirectResponse(url="/richieste-materiale", status_code=303)

@router.post("/richiesta-materiale/{richiesta_id}/annulla")
def annulla_richiesta_action(r: Request, richiesta_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")

    with engine.begin() as c:
        richiesta = c.execute(text("SELECT * FROM richieste_materiale WHERE richiesta_id = :id"), {"id": richiesta_id}).mappings().first()
        if not richiesta:
            return RedirectResponse(url="/richieste-materiale", status_code=303)
            
        if richiesta["ticket_id"]:
            ticket_stato = c.execute(text("SELECT stato FROM tickets WHERE ticket_id = :id"), {"id": richiesta["ticket_id"]}).scalar()
            if ticket_stato != 'presa_in_carico':
                return RedirectResponse(url=f"/ticket/{richiesta['ticket_id']}?error=not_taken_in_charge", status_code=303)

        # Check permissions
        can_cancel = False
        if user.get("ruolo") == "admin" or user.get("id") == richiesta["user_id"]:
            can_cancel = True
        
        if not can_cancel or richiesta["stato"] not in ['nuova', 'pronta_per_scarico']:
            return RedirectResponse(url="/richieste-materiale", status_code=303)

        c.execute(text("UPDATE richieste_materiale SET stato = 'annullata' WHERE richiesta_id = :id"), {"id": richiesta_id})

        if richiesta["ticket_id"]:
            autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
            mat_nome = c.execute(text("SELECT nome FROM materiali WHERE materiale_id = :mid"), {"mid": richiesta["materiale_id"]}).scalar()
            testo = f"Richiesta materiale annullata: {richiesta['quantita']}x {mat_nome}."
            c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo, is_internal) VALUES (:tid, :a, :t, 0)"""),
                     {"tid": richiesta["ticket_id"], "a": f"Sistema ({autore})", "t": testo})
            return RedirectResponse(url=f"/ticket/{richiesta['ticket_id']}", status_code=303)

    return RedirectResponse(url="/richieste-materiale", status_code=303)

@router.get("/magazzino/{magazzino_id}/log", response_class=HTMLResponse)
def magazzino_log(r: Request, magazzino_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id not in user_mag_ids:
                return RedirectResponse(url="/magazzini")
                
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).mappings().first()
        if not magazzino:
            return RedirectResponse(url="/magazzini")
            
        movimenti = c.execute(text("""
            SELECT mm.*, mat.nome as materiale_nome, c.nome as categoria_nome, 
                   u.nome as user_nome, u.cognome as user_cognome, s.nome as sede_nome
            FROM movimenti_magazzino mm
            JOIN materiali mat ON mm.materiale_id = mat.materiale_id
            LEFT JOIN categorie c ON mat.categoria_id = c.categoria_id
            JOIN users u ON mm.user_id = u.user_id
            LEFT JOIN sedi s ON mm.sede_assegnazione_id = s.sede_id
            WHERE mm.magazzino_id = :mag_id
            ORDER BY mm.creato_il DESC, mm.movimento_id DESC
        """), {"mag_id": magazzino_id}).mappings().all()

        latest_mov_id = c.execute(text("""
            SELECT movimento_id FROM movimenti_magazzino
            WHERE magazzino_id = :mag_id AND operazione IN ('carico', 'scarico')
            ORDER BY creato_il DESC, movimento_id DESC LIMIT 1
        """), {"mag_id": magazzino_id}).scalar()
        
    return templates.TemplateResponse(r, "magazzino_log.html", {
        "request": r, "cfg": CFG, "user": user, 
        "magazzino": magazzino, "movimenti": movimenti, "latest_mov_id": latest_mov_id
    })

@router.post("/magazzino/{magazzino_id}/movimento/{movimento_id}/annulla")
def annulla_movimento_action(r: Request, magazzino_id: int, movimento_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.begin() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            if magazzino_id in user_mag_ids: can_edit = True
            
        if not can_edit:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?error=non_autorizzato", status_code=303)
            
        mov = c.execute(text("SELECT * FROM movimenti_magazzino WHERE movimento_id = :mid AND magazzino_id = :mag_id"), 
                        {"mid": movimento_id, "mag_id": magazzino_id}).mappings().first()
        if not mov:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?error=movimento_non_trovato", status_code=303)
            
        latest_mov_id = c.execute(text("""
            SELECT movimento_id FROM movimenti_magazzino
            WHERE magazzino_id = :mag_id AND operazione IN ('carico', 'scarico')
            ORDER BY creato_il DESC, movimento_id DESC LIMIT 1
        """), {"mag_id": magazzino_id}).scalar()
        
        if latest_mov_id != movimento_id:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?error=non_ultimo_movimento", status_code=303)
            
        op = mov["operazione"]
        mat_id = mov["materiale_id"]
        qta = mov["quantita"]
        
        if op not in ("carico", "scarico"):
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?error=operazione_non_annullabile", status_code=303)
            
        row = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                        {"mag": magazzino_id, "mat": mat_id}).first()
        qta_attuale = row[0] if row is not None else 0
        
        if op == "carico":
            if qta_attuale < qta:
                return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?error=giacenza_insufficiente", status_code=303)
            nuova_qta = qta_attuale - qta
        else:  # scarico
            nuova_qta = qta_attuale + qta
            
        if row is None:
            c.execute(text("INSERT INTO giacenze (magazzino_id, materiale_id, quantita) VALUES (:mag, :mat, :q)"),
                      {"mag": magazzino_id, "mat": mat_id, "q": nuova_qta})
        else:
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": magazzino_id, "mat": mat_id})
                      
        # Gestione euristica per ripristinare le richieste materiale evase collegate
        if op == "scarico":
            req = c.execute(text("""
                SELECT richiesta_id FROM richieste_materiale
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND quantita = :qta AND stato = 'evasa'
                ORDER BY creato_il DESC LIMIT 1
            """), {"mag_id": magazzino_id, "mat_id": mat_id, "qta": qta}).mappings().first()
            if req:
                c.execute(text("UPDATE richieste_materiale SET stato = 'pronta_per_scarico' WHERE richiesta_id = :rid"), {"rid": req["richiesta_id"]})
                
            # Cerca e cancella trasferimenti in consegna generati da questo scarico
            trsf_out = c.execute(text("""
                SELECT trasferimento_id FROM trasferimenti
                WHERE magazzino_partenza_id = :mag_id AND materiale_id = :mat_id AND quantita = :qta AND stato = 'in_consegna'
                ORDER BY creato_il DESC LIMIT 1
            """), {"mag_id": magazzino_id, "mat_id": mat_id, "qta": qta}).mappings().first()
            if trsf_out:
                c.execute(text("DELETE FROM trasferimenti WHERE trasferimento_id = :tid"), {"tid": trsf_out["trasferimento_id"]})
        
        elif op == "carico":
            # Cerca trasferimenti completati col carico e ripristinali a in consegna
            trsf_in = c.execute(text("""
                SELECT trasferimento_id FROM trasferimenti
                WHERE magazzino_dest_id = :mag_id AND materiale_id = :mat_id AND quantita = :qta AND stato = 'completato'
                ORDER BY creato_il DESC LIMIT 1
            """), {"mag_id": magazzino_id, "mat_id": mat_id, "qta": qta}).mappings().first()
            if trsf_in:
                c.execute(text("UPDATE trasferimenti SET stato = 'in_consegna', data_arrivo = NULL, user_arrivo_id = NULL WHERE trasferimento_id = :tid"), {"tid": trsf_in["trasferimento_id"]})
                
        c.execute(text("DELETE FROM movimenti_magazzino WHERE movimento_id = :mid"), {"mid": movimento_id})
        
    return RedirectResponse(url=f"/magazzino/{magazzino_id}/log?success=annullato", status_code=303)

@router.get("/magazzini/scarico-multiplo", response_class=HTMLResponse)
def get_scarico_multiplo(r: Request, error: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        if user.get("ruolo") == "admin":
            magazzini_list = c.execute(text("SELECT magazzino_id, nome FROM magazzini ORDER BY nome")).mappings().all()
        else:
            magazzini_list = c.execute(text("""
                SELECT m.magazzino_id, m.nome FROM magazzini m
                JOIN operatori_magazzini om ON m.magazzino_id = om.magazzino_id
                WHERE om.user_id = :uid
                ORDER BY m.nome
            """), {"uid": user.get("id")}).mappings().all()
            
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        
        giacenze_raw = c.execute(text("""
            SELECT mm.magazzino_id, mm.materiale_id, mat.nome AS materiale_nome,
                   mm.posizione_fisica,
                   (SELECT marca FROM movimenti_magazzino 
                    WHERE magazzino_id = mm.magazzino_id AND materiale_id = mm.materiale_id AND posizione_fisica = mm.posizione_fisica
                    AND marca IS NOT NULL AND marca != ''
                    ORDER BY creato_il DESC LIMIT 1) as marca,
                   (SELECT modello FROM movimenti_magazzino 
                    WHERE magazzino_id = mm.magazzino_id AND materiale_id = mm.materiale_id AND posizione_fisica = mm.posizione_fisica
                    AND modello IS NOT NULL AND modello != ''
                    ORDER BY creato_il DESC LIMIT 1) as modello,
                   SUM(CASE WHEN mm.operazione = 'carico' THEN mm.quantita ELSE -mm.quantita END) AS quantita
            FROM movimenti_magazzino mm
            JOIN materiali mat ON mm.materiale_id = mat.materiale_id
            GROUP BY mm.magazzino_id, mm.materiale_id, mm.posizione_fisica
            HAVING SUM(CASE WHEN mm.operazione = 'carico' THEN mm.quantita ELSE -mm.quantita END) > 0
            ORDER BY mm.magazzino_id, mat.nome, mm.posizione_fisica
        """)).mappings().all()
        
    import json
    giacenze_json = []
    for g in giacenze_raw:
        giacenze_json.append({
            "magazzino_id": g["magazzino_id"],
            "materiale_id": g["materiale_id"],
            "materiale_nome": g["materiale_nome"],
            "posizione_fisica": g["posizione_fisica"],
            "marca": g["marca"] or "",
            "modello": g["modello"] or "",
            "quantita": int(g["quantita"]) if g["quantita"] is not None else 0
        })
        
    magazzini_json = [{"magazzino_id": m["magazzino_id"], "nome": m["nome"]} for m in magazzini_list]
    
    from datetime import date
    oggi = date.today().isoformat()
    
    return templates.TemplateResponse(r, "magazzino_scarico_multiplo.html", {
        "request": r, "cfg": CFG, "user": user,
        "sedi": sedi,
        "giacenze_json": json.dumps(giacenze_json),
        "magazzini_json": json.dumps(magazzini_json),
        "oggi": oggi,
        "error": error
    })

@router.post("/magazzini/scarico-multiplo")
async def post_scarico_multiplo(
    r: Request,
    data_movimento: str = Form(...),
    descrizione: str = Form(...),
    sede_assegnazione_id: str = Form(None),
    genera_pdf: str = Form(None),
    allegato: UploadFile = File(None),
    magazzino_id: List[int] = Form(...),
    materiale_id: List[int] = Form(...),
    posizione_fisica: List[str] = Form(...),
    quantita: List[int] = Form(...)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    if not magazzino_id or not (len(magazzino_id) == len(materiale_id) == len(posizione_fisica) == len(quantita)):
        return RedirectResponse(url="/magazzini?error=parametri_invalidi", status_code=303)
        
    with engine.connect() as c:
        user_mag_ids = []
        if user.get("ruolo") != "admin":
            user_mag_ids = c.execute(text("SELECT magazzino_id FROM operatori_magazzini WHERE user_id = :uid"), {"uid": user["id"]}).scalars().all()
            for m_id in magazzino_id:
                if m_id not in user_mag_ids:
                    return RedirectResponse(url="/magazzini?error=non_autorizzato", status_code=303)
                    
    import uuid
    gruppo_scarico_id = f"MULT-{uuid.uuid4().hex[:10].upper()}"
    
    if allegato and allegato.filename:
        content = await allegato.read()
        import io
        allegato.file = io.BytesIO(content)
        
    allegato_filename = save_upload(allegato)
    
    with engine.begin() as c:
        for i in range(len(magazzino_id)):
            m_id = magazzino_id[i]
            mat_id = materiale_id[i]
            pos = posizione_fisica[i].strip()
            qta = quantita[i]
            
            if qta <= 0:
                continue
                
            qta_pos = c.execute(text("""
                SELECT SUM(CASE WHEN operazione = 'carico' THEN quantita ELSE -quantita END)
                FROM movimenti_magazzino
                WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
            """), {"mag": m_id, "mat": mat_id, "pos": pos}).scalar() or 0
            
            if qta > qta_pos:
                return RedirectResponse(url="/magazzini/scarico-multiplo?error=giacenza_insufficiente", status_code=303)
                
            qta_attuale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                                    {"mag": m_id, "mat": mat_id}).scalar() or 0
            nuova_qta = max(0, qta_attuale - qta)
            
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": m_id, "mat": mat_id})
                      
            sede_id_val = int(sede_assegnazione_id) if sede_assegnazione_id and str(sede_assegnazione_id).isdigit() else None
            
            pos_info = c.execute(text("""
                SELECT marca, modello FROM movimenti_magazzino
                WHERE magazzino_id = :mag AND materiale_id = :mat AND posizione_fisica = :pos
                AND (marca IS NOT NULL AND marca != '' OR modello IS NOT NULL AND modello != '')
                ORDER BY creato_il DESC LIMIT 1
            """), {"mag": m_id, "mat": mat_id, "pos": pos}).mappings().first()
            m_marca = pos_info["marca"] if pos_info else ""
            m_modello = pos_info["modello"] if pos_info else ""
            
            c.execute(text("""
                INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, sede_assegnazione_id, posizione_fisica, marca, modello, allegato, gruppo_scarico)
                VALUES (:mag, :mat, :uid, 'scarico', :q, :dt, :desc, :sede, :pos, :marca, :modello, :all, :grp)
            """), {
                "mag": m_id, "mat": mat_id, "uid": user["id"], "q": qta, "dt": data_movimento,
                "desc": descrizione, "sede": sede_id_val, "pos": pos, 
                "marca": m_marca, "modello": m_modello,
                "all": allegato_filename, "grp": gruppo_scarico_id
            })
            
    if genera_pdf == "1":
        return RedirectResponse(url=f"/stampa-consegna/multiplo/{gruppo_scarico_id}", status_code=303)
    return RedirectResponse(url="/magazzini", status_code=303)

@router.get("/magazzini/report", response_class=HTMLResponse)
def magazzini_report(r: Request, mese: int = None, anno: int = None, magazzino_id: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "responsabile"):
        return RedirectResponse(url="/tickets")
        
    from datetime import datetime
    now = datetime.now()
    if anno is None:
        anno = now.year
    if mese is None:
        mese = now.month
        
    with engine.connect() as c:
        if user.get("ruolo") == "admin":
            magazzini_list = c.execute(text("SELECT magazzino_id, nome FROM magazzini ORDER BY nome")).mappings().all()
        else:
            magazzini_list = c.execute(text("""
                SELECT m.magazzino_id, m.nome FROM magazzini m
                JOIN operatori_magazzini om ON m.magazzino_id = om.magazzino_id
                WHERE om.user_id = :uid
                ORDER BY m.nome
            """), {"uid": user.get("id")}).mappings().all()
            
        prefix = f"{anno}-{mese:02d}-%"
        params = {"prefix": prefix}
        
        filter_sql = ""
        if user.get("ruolo") != "admin":
            user_mag_ids = [m["magazzino_id"] for m in magazzini_list]
            if not user_mag_ids:
                return templates.TemplateResponse(r, "magazzino_report.html", {
                    "request": r, "cfg": CFG, "user": user,
                    "righe": [], "magazzini": [], "anno": anno, "mese": mese,
                    "filtri": {"magazzino_id": magazzino_id}
                })
            filter_sql += " AND sub.magazzino_id IN :user_mag_ids"
            params["user_mag_ids"] = user_mag_ids
            
        if magazzino_id and magazzino_id.isdigit():
            filter_sql += " AND sub.magazzino_id = :mag_id"
            params["mag_id"] = int(magazzino_id)
            
        query = f"""
            SELECT * FROM (
                SELECT m.magazzino_id, m.nome AS magazzino_nome, 
                       mat.materiale_id, mat.nome AS materiale_nome, c.nome AS categoria_nome,
                       COALESCE(g.quantita, 0) AS disponibilita,
                       COALESCE(mat.soglia_attenzione, 0) AS soglia_attenzione,
                       COALESCE((
                           SELECT SUM(mm.quantita)
                           FROM movimenti_magazzino mm
                           WHERE mm.magazzino_id = m.magazzino_id
                             AND mm.materiale_id = mat.materiale_id
                             AND mm.operazione = 'carico'
                             AND mm.data_movimento LIKE :prefix
                       ), 0) AS carichi_mese,
                       COALESCE((
                           SELECT SUM(mm.quantita)
                           FROM movimenti_magazzino mm
                           WHERE mm.magazzino_id = m.magazzino_id
                             AND mm.materiale_id = mat.materiale_id
                             AND mm.operazione = 'scarico'
                             AND mm.data_movimento LIKE :prefix
                       ), 0) AS consegne_mese
                FROM magazzini m
                JOIN materiali mat ON (m.categoria_id IS NULL OR m.categoria_id = mat.categoria_id)
                LEFT JOIN giacenze g ON m.magazzino_id = g.magazzino_id AND mat.materiale_id = g.materiale_id
                LEFT JOIN categorie c ON mat.categoria_id = c.categoria_id
            ) sub
            WHERE (sub.disponibilita > 0 OR sub.carichi_mese > 0 OR sub.consegne_mese > 0) {filter_sql}
            ORDER BY sub.magazzino_nome, sub.categoria_nome, sub.materiale_nome
        """
        
        stmt = text(query)
        if "user_mag_ids" in params:
            from sqlalchemy import bindparam
            stmt = stmt.bindparams(bindparam("user_mag_ids", expanding=True))
            
        raw_rows = c.execute(stmt, params).mappings().all()
        rows = []
        for row in raw_rows:
            rows.append({
                "magazzino_id": row["magazzino_id"],
                "magazzino_nome": row["magazzino_nome"],
                "materiale_id": row["materiale_id"],
                "materiale_nome": row["materiale_nome"],
                "categoria_nome": row["categoria_nome"],
                "disponibilita": int(row["disponibilita"]),
                "carichi_mese": int(row["carichi_mese"]),
                "consegne_mese": int(row["consegne_mese"])
            })
            
    return templates.TemplateResponse(r, "magazzino_report.html", {
        "request": r, "cfg": CFG, "user": user,
        "righe": rows, "magazzini": magazzini_list, "anno": anno, "mese": mese,
        "filtri": {"magazzino_id": magazzino_id}
    })


