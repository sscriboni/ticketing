import os
from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from core import engine, CFG, templates, BASE_DIR
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
def user_magazzini_list(r: Request, magazzino_id: str = None, sede_id: str = None, q: str = None, solo_positive: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    if user.get("ruolo") == "normale":
        return RedirectResponse(url="/tickets")
        
    with engine.connect() as c:
        if not any(k in r.query_params for k in ["magazzino_id", "sede_id", "q", "solo_positive"]):
            solo_positive = "1"
            
        where_clauses = []
        params = {}
        
        if magazzino_id and magazzino_id.isdigit():
            where_clauses.append("m.magazzino_id = :mag_id")
            params["mag_id"] = int(magazzino_id)
        if sede_id and sede_id.isdigit():
            where_clauses.append("m.sede_id = :sede_id")
            params["sede_id"] = int(sede_id)
        if q:
            where_clauses.append("mat.nome LIKE :q")
            params["q"] = f"%{q}%"
        if solo_positive == "1":
            where_clauses.append("COALESCE(g.quantita, 0) > 0")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        rows = c.execute(text(f"""
            SELECT m.magazzino_id, m.nome AS magazzino_nome, s.nome AS sede_nome,
                   mat.materiale_id, mat.nome AS materiale_nome, c.nome AS categoria_nome,
                   COALESCE(g.quantita, 0) AS quantita
            FROM magazzini m
            JOIN materiali mat ON (m.categoria_id IS NULL OR m.categoria_id = mat.categoria_id)
            LEFT JOIN giacenze g ON m.magazzino_id = g.magazzino_id AND mat.materiale_id = g.materiale_id
            LEFT JOIN categorie c ON mat.categoria_id = c.categoria_id
            LEFT JOIN sedi s ON m.sede_id = s.sede_id
            {where_sql}
            ORDER BY m.nome, c.nome, mat.nome
        """), params).mappings().all()

        magazzini_list = c.execute(text("SELECT magazzino_id, nome FROM magazzini ORDER BY nome")).mappings().all()
        sedi_list = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()

        user_mag_id = None
        count_in_arrivo = 0
        if user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id:
                count_in_arrivo = c.execute(text("SELECT COUNT(*) FROM trasferimenti WHERE magazzino_dest_id = :mid AND stato = 'in_consegna'"), {"mid": user_mag_id}).scalar() or 0
        elif user.get("ruolo") == "admin":
            count_in_arrivo = c.execute(text("SELECT COUNT(*) FROM trasferimenti WHERE stato = 'in_consegna'")).scalar() or 0

    return templates.TemplateResponse(r, "magazzini.html", {
        "request": r, "cfg": CFG, "user": user, 
        "righe": rows, "magazzini": magazzini_list, "sedi": sedi_list,
        "filtri": {"magazzino_id": magazzino_id, "sede_id": sede_id, "q": q, "solo_positive": solo_positive},
        "user_mag_id": user_mag_id, "count_in_arrivo": count_in_arrivo
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
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == magazzino_id: can_edit = True

        posizioni = c.execute(text("""
            SELECT p.posizione_fisica, p.quantita,
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
def magazzino_rinomina_posizione(r: Request, magazzino_id: int, materiale_id: int, old_posizione: str = Form(...), new_posizione: str = Form(...)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == magazzino_id: can_edit = True
            
        if not can_edit:
            return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

        if new_posizione and new_posizione.strip() and old_posizione:
            c.execute(text("""
                UPDATE movimenti_magazzino 
                SET posizione_fisica = :new_pos 
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = :old_pos
            """), {"new_pos": new_posizione.strip(), "mag_id": magazzino_id, "mat_id": materiale_id, "old_pos": old_posizione})
            
            c.execute(text("""
                UPDATE consegne_programmate 
                SET posizione_fisica = :new_pos 
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND posizione_fisica = :old_pos
            """), {"new_pos": new_posizione.strip(), "mag_id": magazzino_id, "mat_id": materiale_id, "old_pos": old_posizione})
            
    return RedirectResponse(url=f"/magazzino/{magazzino_id}/giacenza/{materiale_id}", status_code=303)

@router.get("/magazzino/{magazzino_id}/movimento/{materiale_id}", response_class=HTMLResponse)
def magazzino_movimento_form(r: Request, magazzino_id: int, materiale_id: int, operazione: str):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if mag_id == magazzino_id: can_edit = True
            
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
                SELECT DISTINCT posizione_fisica 
                FROM movimenti_magazzino 
                WHERE magazzino_id = :mag_id AND materiale_id = :mat_id AND operazione = 'carico' AND posizione_fisica IS NOT NULL AND posizione_fisica != ''
            """), {"mag_id": magazzino_id, "mat_id": materiale_id}).scalars().all()
            
        from datetime import date
        oggi = date.today().isoformat()
        
    template_file = "magazzino_carico.html" if operazione == "carico" else "magazzino_scarico.html"
    return templates.TemplateResponse(r, template_file, {
        "request": r, "cfg": CFG, "user": user, 
        "magazzino": magazzino, "materiale": materiale,
        "operazione": operazione, "sedi": sedi, "magazzini_dest": magazzini_dest, "oggi": oggi, "posizioni": posizioni
    })

@router.post("/magazzino/{magazzino_id}/movimento/{materiale_id}")
async def magazzino_movimento_action(
    r: Request, magazzino_id: int, materiale_id: int, operazione: str = Form(...), quantita: int = Form(...),
    data_movimento: str = Form(...), descrizione: str = Form(""), 
    sede_assegnazione_id: str = Form(None), posizione_fisica: str = Form(...),
    marca: str = Form(""), modello: str = Form(""),
    magazzino_destinazione_id: str = Form(None),
    allegato: UploadFile = File(None),
    programma_consegna: str = Form(None),
    genera_pdf: str = Form(None)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    # Workaround per il bug di troncamento immagini > 1MB (SpooledTemporaryFile) su Windows
    if allegato and allegato.filename:
        content = await allegato.read()
        import io
        allegato.file = io.BytesIO(content)

    allegato_filename = save_upload(allegato)

    with engine.begin() as c:
        # Gestione scarico programmato
        if operazione == "scarico" and programma_consegna == "1":
            sede_id_val = int(sede_assegnazione_id) if sede_assegnazione_id and str(sede_assegnazione_id).isdigit() else None
            c.execute(text("""
                INSERT INTO consegne_programmate (magazzino_id, materiale_id, user_id, quantita, data_programmata, descrizione, sede_assegnazione_id, posizione_fisica, marca, modello, allegato)
                VALUES (:mag, :mat, :uid, :q, :dt_prog, :desc, :sede, :pos, :marca, :modello, :all)
            """), {
                "mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "q": quantita,
                "dt_prog": data_movimento, "desc": descrizione, "sede": sede_id_val,
                "pos": posizione_fisica, "marca": marca, "modello": modello, "all": allegato_filename
            })
            if genera_pdf == "1":
                cons_id = c.execute(text("""
                    SELECT consegna_id FROM consegne_programmate
                    WHERE user_id = :uid AND magazzino_id = :mag AND materiale_id = :mat
                    ORDER BY consegna_id DESC LIMIT 1
                """), {"uid": user["id"], "mag": magazzino_id, "mat": materiale_id}).scalar()
                if cons_id:
                    return RedirectResponse(url=f"/stampa-consegna/programmata/{cons_id}", status_code=303)
            return RedirectResponse(url="/consegne-programmate?success=programmato", status_code=303)

        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if mag_id == magazzino_id: can_edit = True
            
        if not can_edit or quantita <= 0:
            return RedirectResponse(url="/magazzini", status_code=303)

        mag_cat = c.execute(text("SELECT categoria_id FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).scalar()
        mat_cat = c.execute(text("SELECT categoria_id FROM materiali WHERE materiale_id = :id"), {"id": materiale_id}).scalar()
        if mag_cat and mag_cat != mat_cat:
            return RedirectResponse(url="/magazzini", status_code=303)

        qta_attuale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                                {"mag": magazzino_id, "mat": materiale_id}).scalar() or 0

        nuova_qta = max(0, qta_attuale - quantita) if operazione == "scarico" else qta_attuale + quantita

        if qta_attuale == 0 and nuova_qta > 0:
            c.execute(text("INSERT INTO giacenze (magazzino_id, materiale_id, quantita) VALUES (:mag, :mat, :q)"),
                      {"mag": magazzino_id, "mat": materiale_id, "q": nuova_qta})
        else:
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": magazzino_id, "mat": materiale_id})

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
            "sede": sede_id_val, "pos": posizione_fisica, "marca": marca, "modello": modello, "all": allegato_filename
        })
        
        if operazione == "scarico" and mag_dest_id_val:
            c.execute(text("""
                INSERT INTO trasferimenti (magazzino_partenza_id, magazzino_dest_id, materiale_id, quantita, user_partenza_id, note, allegato)
                VALUES (:partenza, :dest, :mat, :q, :uid, :note, :all)
            """), {
                "partenza": magazzino_id, "dest": mag_dest_id_val, "mat": materiale_id,
                "q": quantita, "uid": user["id"], "note": descrizione, "all": allegato_filename
            })
            
        if operazione == "scarico" and genera_pdf == "1":
            mov_id = c.execute(text("""
                SELECT movimento_id FROM movimenti_magazzino
                WHERE user_id = :uid AND magazzino_id = :mag AND materiale_id = :mat AND operazione = 'scarico'
                ORDER BY movimento_id DESC LIMIT 1
            """), {"uid": user["id"], "mag": magazzino_id, "mat": materiale_id}).scalar()
            if mov_id:
                return RedirectResponse(url=f"/stampa-consegna/scarico/{mov_id}", status_code=303)
            
    return RedirectResponse(url="/magazzini", status_code=303)

@router.get("/stampa-consegna/{tipo}/{doc_id}", response_class=HTMLResponse)
def stampa_consegna(r: Request, tipo: str, doc_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        if tipo == 'scarico':
            mov = c.execute(text("""
                SELECT m.*, mag.nome AS magazzino_nome, s.nome AS sede_nome,
                       mat.nome AS materiale_nome, u.nome AS user_nome, u.cognome AS user_cognome
                FROM movimenti_magazzino m
                JOIN magazzini mag ON m.magazzino_id = mag.magazzino_id
                LEFT JOIN sedi s ON m.sede_assegnazione_id = s.sede_id
                JOIN materiali mat ON m.materiale_id = mat.materiale_id
                JOIN users u ON m.user_id = u.user_id
                WHERE m.movimento_id = :id AND m.operazione = 'scarico'
            """), {"id": doc_id}).mappings().first()
        elif tipo == 'programmata':
            mov = c.execute(text("""
                SELECT cp.*, mag.nome AS magazzino_nome, s.nome AS sede_nome,
                       mat.nome AS materiale_nome, u.nome AS user_nome, u.cognome AS user_cognome
                FROM consegne_programmate cp
                JOIN magazzini mag ON cp.magazzino_id = mag.magazzino_id
                LEFT JOIN sedi s ON cp.sede_assegnazione_id = s.sede_id
                JOIN materiali mat ON cp.materiale_id = mat.materiale_id
                JOIN users u ON cp.user_id = u.user_id
                WHERE cp.consegna_id = :id
            """), {"id": doc_id}).mappings().first()
        else:
            return RedirectResponse(url="/magazzini")

        if not mov:
            return RedirectResponse(url="/magazzini")
            
    return templates.TemplateResponse(r, "stampa_consegna.html", {
        "request": r, "cfg": CFG, "user": user, "mov": mov, "tipo": tipo
    })

@router.get("/consegne-programmate", response_class=HTMLResponse)
def consegne_programmate_list(r: Request, success: str = None, error: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.connect() as c:
        where_clause = "c.stato = 'programmata'"
        params = {}
        user_mag_id = None
        if user.get("ruolo") != "admin":
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id:
                where_clause += " AND c.magazzino_id = :mag_id"
                params["mag_id"] = user_mag_id
            else:
                where_clause += " AND 1=0"

        consegne = c.execute(text(f"""
            SELECT c.*, m.nome as materiale_nome, mag.nome as magazzino_nome, s.nome as sede_nome,
                   u.nome as user_nome, u.cognome as user_cognome
            FROM consegne_programmate c
            JOIN materiali m ON c.materiale_id = m.materiale_id
            JOIN magazzini mag ON c.magazzino_id = mag.magazzino_id
            LEFT JOIN sedi s ON c.sede_assegnazione_id = s.sede_id
            JOIN users u ON c.user_id = u.user_id
            WHERE {where_clause}
            ORDER BY c.data_programmata ASC
        """), params).mappings().all()

    return templates.TemplateResponse(r, "consegne_programmate.html", {
        "request": r, "cfg": CFG, "user": user, "consegne": consegne, "success": success, "error": error, "user_mag_id": user_mag_id
    })

@router.get("/consegna-programmata/{consegna_id}/modifica", response_class=HTMLResponse)
def modifica_consegna_form(r: Request, consegna_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.connect() as c:
        consegna = c.execute(text("SELECT * FROM consegne_programmate WHERE consegna_id = :id AND stato = 'programmata'"), {"id": consegna_id}).mappings().first()
        if not consegna: return RedirectResponse(url="/consegne-programmate")

        can_edit = False
        if user.get("ruolo") == "admin" or consegna['user_id'] == user['id']:
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == consegna["magazzino_id"]: can_edit = True
        if not can_edit: return RedirectResponse(url="/consegne-programmate")

        materiale = c.execute(text("SELECT * FROM materiali WHERE materiale_id = :id"), {"id": consegna['materiale_id']}).mappings().first()
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": consegna['magazzino_id']}).mappings().first()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()

    return templates.TemplateResponse(r, "modifica_consegna.html", {"request": r, "cfg": CFG, "user": user, "consegna": consegna, "materiale": materiale, "magazzino": magazzino, "sedi": sedi})

@router.post("/consegna-programmata/{consegna_id}/modifica")
def modifica_consegna_action(r: Request, consegna_id: int, quantita: int = Form(...), data_programmata: str = Form(...), descrizione: str = Form(""), sede_assegnazione_id: str = Form(None), posizione_fisica: str = Form(...), marca: str = Form(""), modello: str = Form("")):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.begin() as c:
        consegna = c.execute(text("SELECT * FROM consegne_programmate WHERE consegna_id = :id AND stato = 'programmata'"), {"id": consegna_id}).mappings().first()
        if not consegna: return RedirectResponse(url="/consegne-programmate")

        can_edit = False
        if user.get("ruolo") == "admin" or consegna['user_id'] == user['id']:
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == consegna["magazzino_id"]: can_edit = True
        if not can_edit: return RedirectResponse(url="/consegne-programmate")

        sede_id_val = int(sede_assegnazione_id) if sede_assegnazione_id and str(sede_assegnazione_id).isdigit() else None
        c.execute(text("""
            UPDATE consegne_programmate SET quantita = :q, data_programmata = :dt, descrizione = :desc, sede_assegnazione_id = :sede, posizione_fisica = :pos, marca = :marca, modello = :modello
            WHERE consegna_id = :id
        """), {"q": quantita, "dt": data_programmata, "desc": descrizione, "sede": sede_id_val, "pos": posizione_fisica, "marca": marca, "modello": modello, "id": consegna_id})
    return RedirectResponse(url="/consegne-programmate?success=modificato", status_code=303)

@router.post("/consegna-programmata/{consegna_id}/esegui")
def esegui_consegna_programmata(r: Request, consegna_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        consegna = c.execute(text("SELECT * FROM consegne_programmate WHERE consegna_id = :id AND stato = 'programmata'"), {"id": consegna_id}).mappings().first()
        if not consegna:
            return RedirectResponse(url="/consegne-programmate?error=not_found", status_code=303)
        
        can_edit = False
        if user.get("ruolo") == "admin":
            can_edit = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == consegna["magazzino_id"]: can_edit = True
        if not can_edit: return RedirectResponse(url="/consegne-programmate", status_code=303)

        qta_attuale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                                {"mag": consegna["magazzino_id"], "mat": consegna["materiale_id"]}).scalar() or 0
        
        if qta_attuale < consegna["quantita"]:
            return RedirectResponse(url=f"/consegne-programmate?error=giacenza_insufficiente", status_code=303)

        nuova_qta = max(0, qta_attuale - consegna["quantita"])
        c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                  {"q": nuova_qta, "mag": consegna["magazzino_id"], "mat": consegna["materiale_id"]})

        from datetime import date
        oggi = date.today().isoformat()
        desc_log = f"[Eseguita Consegna Programmata #{consegna_id}] {consegna['descrizione']}"
        
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, sede_assegnazione_id, posizione_fisica, marca, modello, allegato)
            VALUES (:mag, :mat, :uid, 'scarico', :q, :dt, :desc, :sede, :pos, :marca, :modello, :all)
        """), {
            "mag": consegna["magazzino_id"], "mat": consegna["materiale_id"], "uid": user["id"], "q": consegna["quantita"], 
            "dt": oggi, "desc": desc_log, "sede": consegna["sede_assegnazione_id"],
            "pos": consegna["posizione_fisica"], "marca": consegna["marca"], "modello": consegna["modello"], "all": consegna["allegato"]
        })

        c.execute(text("""
            UPDATE consegne_programmate 
            SET stato = 'consegnata', data_consegna_effettiva = :now, user_consegna_id = :uid
            WHERE consegna_id = :id
        """), {"now": oggi, "uid": user["id"], "id": consegna_id})

    return RedirectResponse(url="/consegne-programmate?success=eseguita", status_code=303)

@router.get("/trasferimenti", response_class=HTMLResponse)
def trasferimenti_list(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.connect() as c:
        where_clause = "1=1"
        params = {}
        user_mag_id = None
        
        if user.get("ruolo") != "admin":
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            where_clause += " AND (t.magazzino_dest_id = :mag_id OR t.magazzino_partenza_id = :mag_id)"
            params["mag_id"] = user_mag_id
            
        trasferimenti = c.execute(text(f"""
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
        """), params).mappings().all()
        
    return templates.TemplateResponse(r, "trasferimenti.html", {"request": r, "cfg": CFG, "user": user, "trasferimenti": trasferimenti, "user_mag_id": user_mag_id})

@router.post("/trasferimenti/{trasferimento_id}/ricevi")
def ricevi_trasferimento(r: Request, trasferimento_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") == "normale": return RedirectResponse(url="/tickets")
    
    with engine.begin() as c:
        t = c.execute(text("SELECT * FROM trasferimenti WHERE trasferimento_id = :id AND stato = 'in_consegna'"), {"id": trasferimento_id}).mappings().first()
        if not t:
            return RedirectResponse(url="/trasferimenti", status_code=303)
            
        if user.get("ruolo") != "admin":
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if t["magazzino_dest_id"] != user_mag_id:
                return RedirectResponse(url="/trasferimenti", status_code=303)
                
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Aggiorna giacenza magazzino di arrivo
        qta_attuale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                                {"mag": t["magazzino_dest_id"], "mat": t["materiale_id"]}).scalar() or 0
        nuova_qta = qta_attuale + t["quantita"]
        
        if qta_attuale == 0:
            c.execute(text("INSERT INTO giacenze (magazzino_id, materiale_id, quantita) VALUES (:mag, :mat, :q)"),
                      {"mag": t["magazzino_dest_id"], "mat": t["materiale_id"], "q": nuova_qta})
        else:
            c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                      {"q": nuova_qta, "mag": t["magazzino_dest_id"], "mat": t["materiale_id"]})
                      
        # Crea movimento di log
        mp_nome = c.execute(text("SELECT nome FROM magazzini WHERE magazzino_id = :id"), {"id": t["magazzino_partenza_id"]}).scalar()
        desc_dest = f"[Ricezione da {mp_nome}] {t['note']}"
        
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, allegato)
            VALUES (:mag, :mat, :uid, 'carico', :q, :dt, :desc, :all)
        """), {
            "mag": t["magazzino_dest_id"], "mat": t["materiale_id"], "uid": user["id"], 
            "q": t["quantita"], "dt": now.split(" ")[0], "desc": desc_dest, "all": t["allegato"]
        })
        
        # Aggiorna trasferimento come completato
        c.execute(text("UPDATE trasferimenti SET stato = 'completato', data_arrivo = :now, user_arrivo_id = :uid WHERE trasferimento_id = :id"),
                  {"now": now, "uid": user["id"], "id": trasferimento_id})
                  
    return RedirectResponse(url="/trasferimenti", status_code=303)

@router.get("/magazzino/{magazzino_id}/log", response_class=HTMLResponse)
def magazzino_log(r: Request, magazzino_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.connect() as c:
        magazzino = c.execute(text("SELECT * FROM magazzini WHERE magazzino_id = :id"), {"id": magazzino_id}).mappings().first()
        if not magazzino: return RedirectResponse(url="/magazzini")
        
        can_view = False
        if user.get("ruolo") == "admin": can_view = True
        elif user.get("ruolo") in ("assistenza", "responsabile"):
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_mag_id == magazzino_id: can_view = True
        
        if not can_view: return RedirectResponse(url="/magazzini")

        movimenti = c.execute(text("""
            SELECT mm.*, mat.nome as materiale_nome, u.nome as user_nome, u.cognome as user_cognome, s.nome as sede_nome
            FROM movimenti_magazzino mm
            JOIN materiali mat ON mm.materiale_id = mat.materiale_id
            JOIN users u ON mm.user_id = u.user_id
            LEFT JOIN sedi s ON mm.sede_assegnazione_id = s.sede_id
            WHERE mm.magazzino_id = :id
            ORDER BY mm.creato_il DESC
        """), {"id": magazzino_id}).mappings().all()

    return templates.TemplateResponse(r, "magazzino_log.html", {"request": r, "cfg": CFG, "user": user, "magazzino": magazzino, "movimenti": movimenti})

@router.get("/richieste-materiale", response_class=HTMLResponse)
def richieste_materiale_list(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        where_clause = "1=1"
        params = {}
        if user.get("ruolo") != "admin":
            mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if mag_id:
                where_clause = "(rm.magazzino_id = :mag_id OR rm.user_id = :uid)"
                params = {"mag_id": mag_id, "uid": user["id"]}
            else:
                where_clause = "rm.user_id = :uid"
                params = {"uid": user["id"]}
                
        richieste = c.execute(text(f"""
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
        """), params).mappings().all()
        
    return templates.TemplateResponse(r, "richieste_materiale.html", {"request": r, "cfg": CFG, "user": user, "richieste": richieste})

@router.get("/richiesta-materiale/nuova", response_class=HTMLResponse)
def nuova_richiesta_materiale_form(r: Request, ticket_id: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        categorie = c.execute(text("SELECT categoria_id, nome FROM categorie ORDER BY nome")).mappings().all()
        materiali = c.execute(text("SELECT materiale_id, nome, categoria_id FROM materiali ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "nuova_richiesta_materiale.html", {
        "request": r, "cfg": CFG, "user": user, "sedi": sedi, "categorie": categorie, "materiali": materiali, "ticket_id": ticket_id
    })

@router.post("/richiesta-materiale/nuova")
def nuova_richiesta_materiale_action(r: Request, sede_dest_id: int = Form(...), categoria_id: int = Form(...), 
                                     materiale_id: int = Form(...), quantita: int = Form(...), ticket_id: str = Form(None)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    ticket_id_val = int(ticket_id) if ticket_id and str(ticket_id).isdigit() else None
    
    with engine.begin() as c:
        magazzino_id = c.execute(text("SELECT magazzino_id FROM magazzini WHERE (sede_id = :sede OR sede_id IS NULL) AND (categoria_id = :cat OR categoria_id IS NULL) ORDER BY sede_id DESC, categoria_id DESC LIMIT 1"),
                                 {"sede": sede_dest_id, "cat": categoria_id}).scalar()
        
        stato = 'nuova'
        if magazzino_id:
            giacenza = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"),
                                 {"mag": magazzino_id, "mat": materiale_id}).scalar() or 0
            if giacenza >= quantita:
                stato = 'pronta_per_scarico'
                
        c.execute(text("""
            INSERT INTO richieste_materiale (user_id, sede_dest_id, categoria_id, materiale_id, quantita, magazzino_id, ticket_id, stato)
            VALUES (:uid, :sede, :cat, :mat, :q, :mag, :tid, :stato)
        """), {
            "uid": user["id"], "sede": sede_dest_id, "cat": categoria_id, "mat": materiale_id,
            "q": quantita, "mag": magazzino_id, "tid": ticket_id_val, "stato": stato
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

@router.get("/richiesta-materiale/{richiesta_id}/evadi", response_class=HTMLResponse)
def evadi_richiesta_form(r: Request, richiesta_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        richiesta = c.execute(text("""
            SELECT rm.*, m.nome as materiale_nome, c.nome as categoria_nome, s.nome as sede_nome, mag.nome as magazzino_nome
            FROM richieste_materiale rm
            JOIN materiali m ON rm.materiale_id = m.materiale_id
            JOIN categorie c ON rm.categoria_id = c.categoria_id
            JOIN sedi s ON rm.sede_dest_id = s.sede_id
            LEFT JOIN magazzini mag ON rm.magazzino_id = mag.magazzino_id
            WHERE rm.richiesta_id = :id
        """), {"id": richiesta_id}).mappings().first()
        
        if not richiesta or richiesta["stato"] != 'pronta_per_scarico':
            return RedirectResponse(url="/richieste-materiale")
            
        if user.get("ruolo") != "admin":
            user_mag_id = c.execute(text("SELECT magazzino_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if not user_mag_id or user_mag_id != richiesta["magazzino_id"]:
                return RedirectResponse(url="/richieste-materiale")
                
        from datetime import date
        oggi = date.today().isoformat()
        
    return templates.TemplateResponse(r, "evadi_richiesta.html", {"request": r, "cfg": CFG, "user": user, "richiesta": richiesta, "oggi": oggi})

@router.post("/richiesta-materiale/{richiesta_id}/evadi")
async def evadi_richiesta_action(r: Request, richiesta_id: int, data_movimento: str = Form(...), descrizione: str = Form(""), 
                           posizione_fisica: str = Form(...), marca: str = Form(""), modello: str = Form(""),
                           allegato: UploadFile = File(None), genera_pdf: str = Form(None)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    # Workaround per il bug di troncamento immagini > 1MB (SpooledTemporaryFile) su Windows
    if allegato and allegato.filename:
        content = await allegato.read()
        import io
        allegato.file = io.BytesIO(content)

    allegato_filename = save_upload(allegato)
    
    with engine.begin() as c:
        richiesta = c.execute(text("SELECT * FROM richieste_materiale WHERE richiesta_id = :id"), {"id": richiesta_id}).mappings().first()
        if not richiesta or richiesta["stato"] != 'pronta_per_scarico':
            return RedirectResponse(url="/richieste-materiale", status_code=303)
            
        magazzino_id = richiesta["magazzino_id"]
        materiale_id = richiesta["materiale_id"]
        quantita = richiesta["quantita"]
        
        qta_attuale = c.execute(text("SELECT quantita FROM giacenze WHERE magazzino_id = :mag AND materiale_id = :mat"), 
                                {"mag": magazzino_id, "mat": materiale_id}).scalar() or 0
                                
        nuova_qta = max(0, qta_attuale - quantita)
        c.execute(text("UPDATE giacenze SET quantita = :q WHERE magazzino_id = :mag AND materiale_id = :mat"),
                  {"q": nuova_qta, "mag": magazzino_id, "mat": materiale_id})
                  
        desc_completa = f"[Evasione Richiesta #{richiesta_id}] {descrizione}"
        
        c.execute(text("""
            INSERT INTO movimenti_magazzino (magazzino_id, materiale_id, user_id, operazione, quantita, data_movimento, descrizione, sede_assegnazione_id, posizione_fisica, marca, modello, allegato)
            VALUES (:mag, :mat, :uid, 'scarico', :q, :dt, :desc, :sede, :pos, :marca, :modello, :all)
        """), {
            "mag": magazzino_id, "mat": materiale_id, "uid": user["id"], "q": quantita, 
            "dt": data_movimento, "desc": desc_completa, "sede": richiesta["sede_dest_id"],
            "pos": posizione_fisica, "marca": marca, "modello": modello, "all": allegato_filename
        })
        
        c.execute(text("UPDATE richieste_materiale SET stato = 'evasa' WHERE richiesta_id = :id"), {"id": richiesta_id})
        
        if richiesta["ticket_id"]:
            autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
            mat_nome = c.execute(text("SELECT nome FROM materiali WHERE materiale_id = :mid"), {"mid": materiale_id}).scalar()
            testo = f"Richiesta materiale evasa dal magazzino: {quantita}x {mat_nome}."
            c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo, is_internal) VALUES (:tid, :a, :t, 0)"""),
                     {"tid": richiesta["ticket_id"], "a": f"Sistema ({autore})", "t": testo})
                     
        if genera_pdf == "1":
            mov_id = c.execute(text("""
                SELECT movimento_id FROM movimenti_magazzino
                WHERE user_id = :uid AND magazzino_id = :mag AND materiale_id = :mat AND operazione = 'scarico'
                ORDER BY movimento_id DESC LIMIT 1
            """), {"uid": user["id"], "mag": magazzino_id, "mat": materiale_id}).scalar()
            if mov_id:
                return RedirectResponse(url=f"/stampa-consegna/scarico/{mov_id}", status_code=303)

    return RedirectResponse(url="/richieste-materiale", status_code=303)

@router.post("/richiesta-materiale/{richiesta_id}/annulla")
def annulla_richiesta_action(r: Request, richiesta_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")

    with engine.begin() as c:
        richiesta = c.execute(text("SELECT * FROM richieste_materiale WHERE richiesta_id = :id"), {"id": richiesta_id}).mappings().first()
        if not richiesta:
            return RedirectResponse(url="/richieste-materiale", status_code=303)

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

    return RedirectResponse(url="/richieste-materiale", status_code=303)