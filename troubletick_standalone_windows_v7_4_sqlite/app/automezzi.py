import csv
import io
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import text
from core import CFG, templates, engine, DB_PK

router = APIRouter()

# Database Initialization for Automezzi
with engine.begin() as conn:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS automezzi (
            automezzo_id {DB_PK},
            targa TEXT UNIQUE NOT NULL,
            marca TEXT NOT NULL,
            modello TEXT NOT NULL,
            tipo TEXT NOT NULL,                -- 'auto' o 'furgone'
            colore TEXT,
            alimentazione TEXT,
            data_immatricolazione TEXT,
            proprieta TEXT,                   -- 'Noleggio' o 'Proprietà'
            canone_noleggio REAL DEFAULT 0,
            km_attuali INTEGER DEFAULT 0,
            stato TEXT DEFAULT 'Disponibile',   -- 'Disponibile', 'In Uso', 'In Manutenzione'
            sede_assegnata_id INTEGER,
            sede_attuale_id INTEGER,
            reparto_assegnato_id INTEGER
        )
    """))
    
    # Check if empty to seed initial data
    count = conn.execute(text("SELECT COUNT(*) FROM automezzi")).scalar() or 0
    if count == 0:
        # Get some valid IDs for sedi and reparti
        sede_ids = [r[0] for r in conn.execute(text("SELECT sede_id FROM sedi LIMIT 3")).all()]
        reparto_ids = [r[0] for r in conn.execute(text("SELECT reparto_id FROM reparti LIMIT 3")).all()]
        
        s1 = sede_ids[0] if len(sede_ids) > 0 else None
        s2 = sede_ids[1] if len(sede_ids) > 1 else s1
        s3 = sede_ids[2] if len(sede_ids) > 2 else s1
        
        rep1 = reparto_ids[0] if len(reparto_ids) > 0 else None
        rep2 = reparto_ids[1] if len(reparto_ids) > 1 else rep1
        rep3 = reparto_ids[2] if len(reparto_ids) > 2 else rep1
        
        conn.execute(text("""
            INSERT INTO automezzi (targa, marca, modello, tipo, colore, alimentazione, data_immatricolazione, proprieta, canone_noleggio, km_attuali, stato, sede_assegnata_id, sede_attuale_id, reparto_assegnato_id)
            VALUES 
            ('GF345KK', 'Tesla', 'Model 3', 'auto', 'Nero', 'Elettrica', '2023-05-15', 'Noleggio', 450.00, 12500, 'Disponibile', :s1, :s1, :rep1),
            ('FN123XX', 'Audi', 'A4 Avant', 'auto', 'Grigio', 'Diesel', '2022-10-10', 'Noleggio', 580.00, 48000, 'In Uso', :s2, :s2, :rep2),
            ('GE987YY', 'Fiat', '500 Hybrid', 'auto', 'Bianco', 'Ibrida', '2021-03-20', 'Proprietà', 0.00, 32000, 'Disponibile', :s3, :s3, :rep3),
            ('GJ567ZZ', 'Jeep', 'Compass 4xe', 'auto', 'Rosso', 'Ibrida Plug-in', '2022-06-01', 'Proprietà', 0.00, 19500, 'In Manutenzione', :s1, :s1, :rep1)
        """), {"s1": s1, "s2": s2, "s3": s3, "rep1": rep1, "rep2": rep2, "rep3": rep3})

@router.get("/admin/automezzi", response_class=HTMLResponse)
def list_automezzi(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/")
    
    with engine.connect() as conn:
        # Fetch automezzi
        automezzi = conn.execute(text("""
            SELECT a.*, 
                   s_ass.nome as sede_assegnata_nome, 
                   s_att.nome as sede_attuale_nome, 
                   r.nome as reparto_assegnato_nome
            FROM automezzi a
            LEFT JOIN sedi s_ass ON a.sede_assegnata_id = s_ass.sede_id
            LEFT JOIN sedi s_att ON a.sede_attuale_id = s_att.sede_id
            LEFT JOIN reparti r ON a.reparto_assegnato_id = r.reparto_id
            ORDER BY a.automezzo_id DESC
        """)).mappings().all()
        
        # Fetch sedi
        sedi = conn.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        
        # Fetch reparti
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "appautopark.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": automezzi,
        "sedi": sedi,
        "reparti": reparti
    })

@router.post("/veicolo/nuovo")
def add_vehicle(
    r: Request,
    targa: str = Form(...),
    marca: str = Form(...),
    modello: str = Form(...),
    tipo: str = Form(...),
    colore: str = Form(None),
    alimentazione: str = Form(None),
    data_immatricolazione: str = Form(None),
    proprieta: str = Form(None),
    canone_noleggio: float = Form(0.0),
    km_attuali: int = Form(0),
    stato: str = Form("Disponibile"),
    sede_assegnata_id: int = Form(None),
    sede_attuale_id: int = Form(None),
    reparto_assegnato_id: int = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO automezzi (
                targa, marca, modello, tipo, colore, alimentazione, data_immatricolazione, 
                proprieta, canone_noleggio, km_attuali, stato, 
                sede_assegnata_id, sede_attuale_id, reparto_assegnato_id
            ) VALUES (
                :targa, :marca, :modello, :tipo, :colore, :alimentazione, :data_immatricolazione, 
                :proprieta, :canone_noleggio, :km_attuali, :stato, 
                :sede_assegnata_id, :sede_attuale_id, :reparto_assegnato_id
            )
        """), {
            "targa": targa.strip().upper(),
            "marca": marca.strip(),
            "modello": modello.strip(),
            "tipo": tipo,
            "colore": colore.strip() if colore else None,
            "alimentazione": alimentazione.strip() if alimentazione else None,
            "data_immatricolazione": data_immatricolazione if data_immatricolazione else None,
            "proprieta": proprieta,
            "canone_noleggio": canone_noleggio,
            "km_attuali": km_attuali,
            "stato": stato,
            "sede_assegnata_id": sede_assegnata_id,
            "sede_attuale_id": sede_attuale_id if sede_attuale_id else sede_assegnata_id,
            "reparto_assegnato_id": reparto_assegnato_id
        })
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/veicolo/modifica/{id}")
def edit_vehicle(
    id: int,
    r: Request,
    targa: str = Form(...),
    marca: str = Form(...),
    modello: str = Form(...),
    tipo: str = Form(...),
    colore: str = Form(None),
    alimentazione: str = Form(None),
    data_immatricolazione: str = Form(None),
    proprieta: str = Form(None),
    canone_noleggio: float = Form(0.0),
    km_attuali: int = Form(0),
    stato: str = Form(...),
    sede_assegnata_id: int = Form(None),
    sede_attuale_id: int = Form(None),
    reparto_assegnato_id: int = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE automezzi SET
                targa = :targa,
                marca = :marca,
                modello = :modello,
                tipo = :tipo,
                colore = :colore,
                alimentazione = :alimentazione,
                data_immatricolazione = :data_immatricolazione,
                proprieta = :proprieta,
                canone_noleggio = :canone_noleggio,
                km_attuali = :km_attuali,
                stato = :stato,
                sede_assegnata_id = :sede_assegnata_id,
                sede_attuale_id = :sede_attuale_id,
                reparto_assegnato_id = :reparto_assegnato_id
            WHERE automezzo_id = :id
        """), {
            "id": id,
            "targa": targa.strip().upper(),
            "marca": marca.strip(),
            "modello": modello.strip(),
            "tipo": tipo,
            "colore": colore.strip() if colore else None,
            "alimentazione": alimentazione.strip() if alimentazione else None,
            "data_immatricolazione": data_immatricolazione if data_immatricolazione else None,
            "proprieta": proprieta,
            "canone_noleggio": canone_noleggio,
            "km_attuali": km_attuali,
            "stato": stato,
            "sede_assegnata_id": sede_assegnata_id,
            "sede_attuale_id": sede_attuale_id,
            "reparto_assegnato_id": reparto_assegnato_id
        })
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/veicolo/elimina/{id}")
def delete_vehicle(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi WHERE automezzo_id = :id"), {"id": id})
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.get("/admin/automezzi/esporta")
def export_automezzi_csv(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT targa, marca, modello, tipo, colore, alimentazione, data_immatricolazione, 
                   proprieta, canone_noleggio, km_attuali, stato, 
                   sede_assegnata_id, sede_attuale_id, reparto_assegnato_id
            FROM automezzi
            ORDER BY automezzo_id ASC
        """)).all()
        
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "targa", "marca", "modello", "tipo", "colore", "alimentazione", "data_immatricolazione",
        "proprieta", "canone_noleggio", "km_attuali", "stato", "sede_assegnata_id", "sede_attuale_id", "reparto_assegnato_id"
    ])
    for row in rows:
        writer.writerow(list(row))
        
    csv_data = output.getvalue()
    output.close()
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=automezzi.csv"}
    )

@router.post("/admin/automezzi/importa")
def import_automezzi_csv(r: Request, file: UploadFile = File(...)):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    try:
        contents = file.file.read().decode("utf-8-sig")
        stream = io.StringIO(contents)
        try:
            dialect = csv.Sniffer().sniff(contents[:2048])
            reader = csv.reader(stream, dialect)
        except Exception:
            reader = csv.reader(stream, delimiter=';')
    except Exception:
        return RedirectResponse(url="/admin/automezzi", status_code=303)
        
    headers = next(reader, None)
    if not headers:
        return RedirectResponse(url="/admin/automezzi", status_code=303)
        
    headers = [h.strip().lower() for h in headers]
    
    with engine.begin() as conn:
        for row in reader:
            if not row or len(row) < 3:
                continue
            data = dict(zip(headers, [val.strip() for val in row]))
            
            if "targa" not in data or "marca" not in data or "modello" not in data:
                continue
                
            targa = data["targa"].upper()
            marca = data["marca"]
            modello = data["modello"]
            tipo = data.get("tipo", "auto")
            colore = data.get("colore")
            alimentazione = data.get("alimentazione")
            data_immatricolazione = data.get("data_immatricolazione")
            proprieta = data.get("proprieta", "Proprietà")
            
            try:
                canone_noleggio = float(data.get("canone_noleggio") or 0.0)
            except ValueError:
                canone_noleggio = 0.0
                
            try:
                km_attuali = int(data.get("km_attuali") or 0)
            except ValueError:
                km_attuali = 0
                
            stato = data.get("stato", "Disponibile")
            
            def get_int_or_none(k):
                val = data.get(k)
                if val:
                    try:
                        return int(val)
                    except ValueError:
                        pass
                return None
                
            sede_assegnata_id = get_int_or_none("sede_assegnata_id")
            sede_attuale_id = get_int_or_none("sede_attuale_id") or sede_assegnata_id
            reparto_assegnato_id = get_int_or_none("reparto_assegnato_id")
            
            existing = conn.execute(text("SELECT automezzo_id FROM automezzi WHERE targa = :targa"), {"targa": targa}).scalar()
            if existing:
                conn.execute(text("""
                    UPDATE automezzi SET
                        marca = :marca, modello = :modello, tipo = :tipo, colore = :colore,
                        alimentazione = :alimentazione, data_immatricolazione = :data_immatricolazione,
                        proprieta = :proprieta, canone_noleggio = :canone_noleggio, km_attuali = :km_attuali,
                        stato = :stato, sede_assegnata_id = :sede_assegnata_id, sede_attuale_id = :sede_attuale_id,
                        reparto_assegnato_id = :reparto_assegnato_id
                    WHERE automezzo_id = :id
                """), {
                    "id": existing, "targa": targa, "marca": marca, "modello": modello, "tipo": tipo, "colore": colore,
                    "alimentazione": alimentazione, "data_immatricolazione": data_immatricolazione, "proprieta": proprieta,
                    "canone_noleggio": canone_noleggio, "km_attuali": km_attuali, "stato": stato,
                    "sede_assegnata_id": sede_assegnata_id, "sede_attuale_id": sede_attuale_id,
                    "reparto_assegnato_id": reparto_assegnato_id
                })
            else:
                conn.execute(text("""
                    INSERT INTO automezzi (
                        targa, marca, modello, tipo, colore, alimentazione, data_immatricolazione,
                        proprieta, canone_noleggio, km_attuali, stato, sede_assegnata_id, sede_attuale_id,
                        reparto_assegnato_id
                    ) VALUES (
                        :targa, :marca, :modello, :tipo, :colore, :alimentazione, :data_immatricolazione,
                        :proprieta, :canone_noleggio, :km_attuali, :stato, :sede_assegnata_id, :sede_attuale_id,
                        :reparto_assegnato_id
                    )
                """), {
                    "targa": targa, "marca": marca, "modello": modello, "tipo": tipo, "colore": colore,
                    "alimentazione": alimentazione, "data_immatricolazione": data_immatricolazione, "proprieta": proprieta,
                    "canone_noleggio": canone_noleggio, "km_attuali": km_attuali, "stato": stato,
                    "sede_assegnata_id": sede_assegnata_id, "sede_attuale_id": sede_attuale_id,
                    "reparto_assegnato_id": reparto_assegnato_id
                })
                
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/admin/automezzi/svuota")
def empty_automezzi(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi"))
        
    return RedirectResponse(url="/admin/automezzi", status_code=303)
