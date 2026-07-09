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
        CREATE TABLE IF NOT EXISTS marche_automezzi (
            marca_id {DB_PK},
            nome TEXT UNIQUE NOT NULL
        )
    """))

    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS automezzi (
            automezzo_id {DB_PK},
            targa TEXT UNIQUE NOT NULL,
            marca_id INTEGER NOT NULL,
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
            reparto_assegnato_id INTEGER,
            fornitore TEXT,
            classe_euro TEXT,
            FOREIGN KEY(marca_id) REFERENCES marche_automezzi(marca_id)
        )
    """))
    
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS manutenzioni_automezzi (
            manutenzione_id {DB_PK},
            automezzo_id INTEGER NOT NULL,
            tipo_servizio TEXT NOT NULL,
            data_inizio TEXT NOT NULL,
            ora_inizio TEXT NOT NULL,
            data_fine TEXT,
            ora_fine TEXT,
            km_registrati INTEGER NOT NULL,
            km_fine INTEGER,
            luogo TEXT NOT NULL,
            bloccante INTEGER DEFAULT 0,
            note TEXT,
            FOREIGN KEY(automezzo_id) REFERENCES automezzi(automezzo_id) ON DELETE CASCADE
        )
    """))
    
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS viaggi_automezzi (
            viaggio_id {DB_PK},
            automezzo_id INTEGER NOT NULL,
            data_viaggio TEXT NOT NULL,
            ora_partenza TEXT NOT NULL,
            ora_arrivo TEXT,
            km_iniziali INTEGER NOT NULL,
            km_finali INTEGER,
            sede_partenza_id INTEGER NOT NULL,
            sede_arrivo_id INTEGER,
            user_id INTEGER NOT NULL,
            note TEXT,
            FOREIGN KEY(automezzo_id) REFERENCES automezzi(automezzo_id) ON DELETE CASCADE,
            FOREIGN KEY(sede_partenza_id) REFERENCES sedi(sede_id),
            FOREIGN KEY(sede_arrivo_id) REFERENCES sedi(sede_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """))
    
    # Check if empty to seed initial data for marche
    count_marche = conn.execute(text("SELECT COUNT(*) FROM marche_automezzi")).scalar() or 0
    if count_marche == 0:
        marche_default = ["Fiat", "Tesla", "Audi", "Jeep", "Ford", "Toyota", "Renault", "Volkswagen", "BMW", "Mercedes-Benz", "Peugeot", "Opel"]
        for m in marche_default:
            conn.execute(text("INSERT OR IGNORE INTO marche_automezzi(nome) VALUES (:nome)"), {"nome": m})
            
    # Check if empty to seed initial data for automezzi
    count = conn.execute(text("SELECT COUNT(*) FROM automezzi")).scalar() or 0
    if count == 0:
        # Get some valid IDs for sedi, reparti and marche
        sede_ids = [r[0] for r in conn.execute(text("SELECT sede_id FROM sedi LIMIT 3")).all()]
        reparto_ids = [r[0] for r in conn.execute(text("SELECT reparto_id FROM reparti LIMIT 3")).all()]
        
        # Get matching brand ids for seed data
        fiat_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE nome = 'Fiat'")).scalar()
        tesla_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE nome = 'Tesla'")).scalar()
        audi_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE nome = 'Audi'")).scalar()
        jeep_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE nome = 'Jeep'")).scalar()
        
        fiat_id = fiat_id or 1
        tesla_id = tesla_id or 2
        audi_id = audi_id or 3
        jeep_id = jeep_id or 4
        
        s1 = sede_ids[0] if len(sede_ids) > 0 else None
        s2 = sede_ids[1] if len(sede_ids) > 1 else s1
        s3 = sede_ids[2] if len(sede_ids) > 2 else s1
        
        rep1 = reparto_ids[0] if len(reparto_ids) > 0 else None
        rep2 = reparto_ids[1] if len(reparto_ids) > 1 else rep1
        rep3 = reparto_ids[2] if len(reparto_ids) > 2 else rep1
        
        conn.execute(text("""
            INSERT INTO automezzi (targa, marca_id, modello, tipo, colore, alimentazione, data_immatricolazione, proprieta, canone_noleggio, km_attuali, stato, sede_assegnata_id, sede_attuale_id, reparto_assegnato_id, fornitore, classe_euro)
            VALUES 
            ('GF345KK', :tesla, 'Model 3', 'auto', 'Nero', 'E', '2023-05-15', 'Noleggio', 450.00, 12500, 'Disponibile', :s1, :s1, :rep1, 'LeasePlan', 'Elettrico'),
            ('FN123XX', :audi, 'A4 Avant', 'auto', 'Grigio', 'G', '2022-10-10', 'Noleggio', 580.00, 48000, 'In Uso', :s2, :s2, :rep2, 'Arval', 'Euro 6'),
            ('GE987YY', :fiat, '500 Hybrid', 'auto', 'Bianco', 'B', '2021-03-20', 'Proprietà', 0.00, 32000, 'Disponibile', :s3, :s3, :rep3, 'Concessionaria Fiat Torino', 'Euro 6'),
            ('GJ567ZZ', :jeep, 'Compass 4xe', 'auto', 'Rosso', 'G', '2022-06-01', 'Proprietà', 0.00, 19500, 'In Manutenzione', :s1, :s1, :rep1, 'Leasys', 'Euro 6')
        """), {
            "tesla": tesla_id, "audi": audi_id, "fiat": fiat_id, "jeep": jeep_id,
            "s1": s1, "s2": s2, "s3": s3, "rep1": rep1, "rep2": rep2, "rep3": rep3
        })

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
                   m.nome as marca_nome,
                   s_ass.nome as sede_assegnata_nome, 
                   s_att.nome as sede_attuale_nome, 
                   r.nome as reparto_assegnato_nome
            FROM automezzi a
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s_ass ON a.sede_assegnata_id = s_ass.sede_id
            LEFT JOIN sedi s_att ON a.sede_attuale_id = s_att.sede_id
            LEFT JOIN reparti r ON a.reparto_assegnato_id = r.reparto_id
            ORDER BY a.automezzo_id DESC
        """)).mappings().all()
        
        # Fetch sedi
        sedi = conn.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        
        # Fetch reparti
        reparti = conn.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        
        # Fetch marche
        marche = conn.execute(text("SELECT marca_id, nome FROM marche_automezzi ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "appautopark.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": automezzi,
        "sedi": sedi,
        "reparti": reparti,
        "marche": marche
    })

@router.post("/veicolo/nuovo")
def add_vehicle(
    r: Request,
    targa: str = Form(...),
    marca_id: int = Form(...),
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
    reparto_assegnato_id: int = Form(None),
    fornitore: str = Form(None),
    classe_euro: str = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO automezzi (
                targa, marca_id, modello, tipo, colore, alimentazione, data_immatricolazione, 
                proprieta, canone_noleggio, km_attuali, stato, 
                sede_assegnata_id, sede_attuale_id, reparto_assegnato_id,
                fornitore, classe_euro
            ) VALUES (
                :targa, :marca_id, :modello, :tipo, :colore, :alimentazione, :data_immatricolazione, 
                :proprieta, :canone_noleggio, :km_attuali, :stato, 
                :sede_assegnata_id, :sede_attuale_id, :reparto_assegnato_id,
                :fornitore, :classe_euro
            )
        """), {
            "targa": targa.strip().upper(),
            "marca_id": marca_id,
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
            "reparto_assegnato_id": reparto_assegnato_id,
            "fornitore": fornitore.strip() if fornitore else None,
            "classe_euro": classe_euro.strip() if classe_euro else None
        })
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/veicolo/modifica/{id}")
def edit_vehicle(
    id: int,
    r: Request,
    targa: str = Form(...),
    marca_id: int = Form(...),
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
    reparto_assegnato_id: int = Form(None),
    fornitore: str = Form(None),
    classe_euro: str = Form(None)
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
                marca_id = :marca_id,
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
                reparto_assegnato_id = :reparto_assegnato_id,
                fornitore = :fornitore,
                classe_euro = :classe_euro
            WHERE automezzo_id = :id
        """), {
            "id": id,
            "targa": targa.strip().upper(),
            "marca_id": marca_id,
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
            "reparto_assegnato_id": reparto_assegnato_id,
            "fornitore": fornitore.strip() if fornitore else None,
            "classe_euro": classe_euro.strip() if classe_euro else None
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

@router.get("/admin/automezzi/gestione", response_class=HTMLResponse)
def admin_automezzi_gestione_page(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/")
    return templates.TemplateResponse(r, "admin_autopark_gestione.html", {"request": r, "cfg": CFG, "user": user})

@router.get("/admin/automezzi/esporta")
def export_automezzi_csv(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.targa, m.nome as marca, a.modello, a.tipo, a.colore, a.alimentazione, a.data_immatricolazione, 
                   a.proprieta, a.canone_noleggio, a.km_attuali, a.stato, 
                   a.sede_assegnata_id, a.sede_attuale_id, a.reparto_assegnato_id,
                   a.fornitore, a.classe_euro
            FROM automezzi a
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            ORDER BY a.automezzo_id ASC
        """)).all()
        
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "targa", "marca", "modello", "tipo", "colore", "alimentazione", "data_immatricolazione",
        "proprieta", "canone_noleggio", "km_attuali", "stato", "sede_assegnata_id", "sede_attuale_id", "reparto_assegnato_id",
        "fornitore", "classe_euro"
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
    if user.get("ruolo") != "admin":
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
        return RedirectResponse(url="/admin/automezzi/gestione?msg=import_err", status_code=303)
        
    headers = next(reader, None)
    if not headers:
        return RedirectResponse(url="/admin/automezzi/gestione?msg=import_err", status_code=303)
        
    headers = [h.strip().lower() for h in headers]
    
    with engine.begin() as conn:
        for row in reader:
            if not row or len(row) < 3:
                continue
            data = dict(zip(headers, [val.strip() for val in row]))
            
            if "targa" not in data or "marca" not in data or "modello" not in data:
                continue
                
            targa = data["targa"].upper()
            marca_nome = data["marca"].strip()
            modello = data["modello"]
            tipo = data.get("tipo", "auto")
            colore = data.get("colore")
            alimentazione = data.get("alimentazione")
            data_immatricolazione = data.get("data_immatricolazione")
            proprieta = data.get("proprieta", "Proprietà")
            fornitore = data.get("fornitore")
            classe_euro = data.get("classe_euro")
            
            # resolve or insert brand name to get marca_id
            marca_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE LOWER(nome) = LOWER(:nome)"), {"nome": marca_nome}).scalar()
            if not marca_id:
                conn.execute(text("INSERT INTO marche_automezzi (nome) VALUES (:nome)"), {"nome": marca_nome})
                marca_id = conn.execute(text("SELECT marca_id FROM marche_automezzi WHERE nome = :nome"), {"nome": marca_nome}).scalar()
            
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
                        marca_id = :marca_id, modello = :modello, tipo = :tipo, colore = :colore,
                        alimentazione = :alimentazione, data_immatricolazione = :data_immatricolazione,
                        proprieta = :proprieta, canone_noleggio = :canone_noleggio, km_attuali = :km_attuali,
                        stato = :stato, sede_assegnata_id = :sede_assegnata_id, sede_attuale_id = :sede_attuale_id,
                        reparto_assegnato_id = :reparto_assegnato_id, fornitore = :fornitore, classe_euro = :classe_euro
                    WHERE automezzo_id = :id
                """), {
                    "id": existing, "targa": targa, "marca_id": marca_id, "modello": modello, "tipo": tipo, "colore": colore,
                    "alimentazione": alimentazione, "data_immatricolazione": data_immatricolazione, "proprieta": proprieta,
                    "canone_noleggio": canone_noleggio, "km_attuali": km_attuali, "stato": stato,
                    "sede_assegnata_id": sede_assegnata_id, "sede_attuale_id": sede_attuale_id,
                    "reparto_assegnato_id": reparto_assegnato_id,
                    "fornitore": fornitore.strip() if fornitore else None,
                    "classe_euro": classe_euro.strip() if classe_euro else None
                })
            else:
                conn.execute(text("""
                    INSERT INTO automezzi (
                        targa, marca_id, modello, tipo, colore, alimentazione, data_immatricolazione,
                        proprieta, canone_noleggio, km_attuali, stato, sede_assegnata_id, sede_attuale_id,
                        reparto_assegnato_id, fornitore, classe_euro
                    ) VALUES (
                        :targa, :marca_id, :modello, :tipo, :colore, :alimentazione, :data_immatricolazione,
                        :proprieta, :canone_noleggio, :km_attuali, :stato, :sede_assegnata_id, :sede_attuale_id,
                        :reparto_assegnato_id, :fornitore, :classe_euro
                    )
                """), {
                    "targa": targa, "marca_id": marca_id, "modello": modello, "tipo": tipo, "colore": colore,
                    "alimentazione": alimentazione, "data_immatricolazione": data_immatricolazione, "proprieta": proprieta,
                    "canone_noleggio": canone_noleggio, "km_attuali": km_attuali, "stato": stato,
                    "sede_assegnata_id": sede_assegnata_id, "sede_attuale_id": sede_attuale_id,
                    "reparto_assegnato_id": reparto_assegnato_id,
                    "fornitore": fornitore.strip() if fornitore else None,
                    "classe_euro": classe_euro.strip() if classe_euro else None
                })
                
    return RedirectResponse(url="/admin/automezzi/gestione?msg=import_ok", status_code=303)

@router.post("/admin/automezzi/svuota")
def empty_automezzi(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi"))
        
    return RedirectResponse(url="/admin/automezzi/gestione?msg=clear_ok", status_code=303)

@router.get("/admin/automezzi/manutenzioni", response_class=HTMLResponse)
def list_manutenzioni(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        manutenzioni = conn.execute(text("""
            SELECT m.*, a.targa, b.nome as marca, a.modello
            FROM manutenzioni_automezzi m
            JOIN automezzi a ON m.automezzo_id = a.automezzo_id
            JOIN marche_automezzi b ON a.marca_id = b.marca_id
            ORDER BY m.manutenzione_id DESC
        """)).all()
        
        veicoli = conn.execute(text("""
            SELECT a.automezzo_id, a.targa, b.nome as marca, a.modello, a.km_attuali 
            FROM automezzi a 
            JOIN marche_automezzi b ON a.marca_id = b.marca_id 
            ORDER BY b.nome, a.modello
        """)).all()
        
    return templates.TemplateResponse(r, "admin_automezzi_manutenzioni.html", {
        "request": r, "cfg": CFG, "user": user, "manutenzioni": manutenzioni, "veicoli": veicoli
    })

@router.post("/admin/automezzi/manutenzioni/nuova")
def add_manutenzione(
    r: Request,
    automezzo_id: int = Form(...),
    tipo_servizio: str = Form(...),
    data_inizio: str = Form(...),
    ora_inizio: str = Form(...),
    km_registrati: int = Form(...),
    luogo: str = Form(...),
    bloccante: int = Form(0),
    note: str = Form(None)
):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO manutenzioni_automezzi (
                automezzo_id, tipo_servizio, data_inizio, ora_inizio, km_registrati, luogo, bloccante, note
            ) VALUES (
                :automezzo_id, :tipo_servizio, :data_inizio, :ora_inizio, :km_registrati, :luogo, :bloccante, :note
            )
        """), {
            "automezzo_id": automezzo_id, "tipo_servizio": tipo_servizio, "data_inizio": data_inizio,
            "ora_inizio": ora_inizio, "km_registrati": km_registrati, "luogo": luogo, "bloccante": bloccante,
            "note": note
        })
        
        if bloccante == 1:
            conn.execute(text("""
                UPDATE automezzi 
                SET stato = 'In Manutenzione', km_attuali = MAX(km_attuali, :km_registrati)
                WHERE automezzo_id = :automezzo_id
            """), {"automezzo_id": automezzo_id, "km_registrati": km_registrati})
        else:
            conn.execute(text("""
                UPDATE automezzi 
                SET km_attuali = MAX(km_attuali, :km_registrati)
                WHERE automezzo_id = :automezzo_id
            """), {"automezzo_id": automezzo_id, "km_registrati": km_registrati})
            
    return RedirectResponse(url="/admin/automezzi/manutenzioni", status_code=303)

@router.post("/admin/automezzi/manutenzioni/completa/{id}")
def complete_manutenzione(
    id: int,
    r: Request,
    data_fine: str = Form(...),
    ora_fine: str = Form(...),
    km_fine: int = Form(...),
    note_finali: str = Form(None)
):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        m = conn.execute(text("SELECT automezzo_id, bloccante, note FROM manutenzioni_automezzi WHERE manutenzione_id = :id"), {"id": id}).first()
        if m:
            note_complete = (m.note or "") + (f" | Resoconto finale: {note_finali}" if note_finali else "")
            conn.execute(text("""
                UPDATE manutenzioni_automezzi
                SET data_fine = :data_fine, ora_fine = :ora_fine, km_fine = :km_fine, note = :note
                WHERE manutenzione_id = :id
            """), {"id": id, "data_fine": data_fine, "ora_fine": ora_fine, "km_fine": km_fine, "note": note_complete})
            
            conn.execute(text("""
                UPDATE automezzi
                SET stato = 'Disponibile', km_attuali = MAX(km_attuali, :km_fine)
                WHERE automezzo_id = :automezzo_id
            """), {"automezzo_id": m.automezzo_id, "km_fine": km_fine})
            
    return RedirectResponse(url="/admin/automezzi/manutenzioni", status_code=303)

@router.post("/admin/automezzi/manutenzioni/elimina/{id}")
def delete_manutenzione(id: int, r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        m = conn.execute(text("SELECT automezzo_id, data_fine, bloccante FROM manutenzioni_automezzi WHERE manutenzione_id = :id"), {"id": id}).first()
        if m and not m.data_fine and m.bloccante == 1:
            conn.execute(text("UPDATE automezzi SET stato = 'Disponibile' WHERE automezzo_id = :automezzo_id"), {"automezzo_id": m.automezzo_id})
        conn.execute(text("DELETE FROM manutenzioni_automezzi WHERE manutenzione_id = :id"), {"id": id})
        
    return RedirectResponse(url="/admin/automezzi/manutenzioni", status_code=303)

@router.get("/admin/automezzi/marche", response_class=HTMLResponse)
def list_marche(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        marche = conn.execute(text("SELECT * FROM marche_automezzi ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "admin_automezzi_marche.html", {
        "request": r, "cfg": CFG, "user": user, "marche": marche
    })

@router.post("/admin/automezzi/marche/nuova")
def add_marca(r: Request, nome: str = Form(...)):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("INSERT OR IGNORE INTO marche_automezzi (nome) VALUES (:nome)"), {"nome": nome.strip()})
        
    return RedirectResponse(url="/admin/automezzi/marche", status_code=303)

@router.post("/admin/automezzi/marche/modifica/{id}")
def edit_marca(id: int, r: Request, nome: str = Form(...)):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("UPDATE marche_automezzi SET nome = :nome WHERE marca_id = :id"), {"id": id, "nome": nome.strip()})
        
    return RedirectResponse(url="/admin/automezzi/marche", status_code=303)

@router.post("/admin/automezzi/marche/elimina/{id}")
def delete_marca(id: int, r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM marche_automezzi WHERE marca_id = :id"), {"id": id})
        
    return RedirectResponse(url="/admin/automezzi/marche", status_code=303)

@router.get("/admin/automezzi/viaggi", response_class=HTMLResponse)
def list_viaggi(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        viaggi_attivi = conn.execute(text("""
            SELECT v.*, a.targa, b.nome as marca, a.modello,
                   s_part.nome as sede_partenza_nome,
                   u.nome as user_nome, u.cognome as user_cognome
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi b ON a.marca_id = b.marca_id
            JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
            JOIN users u ON v.user_id = u.user_id
            WHERE v.ora_arrivo IS NULL OR v.km_finali IS NULL
            ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
        """)).mappings().all()
        
        viaggi_completati = conn.execute(text("""
            SELECT v.*, a.targa, b.nome as marca, a.modello,
                   s_part.nome as sede_partenza_nome,
                   s_arr.nome as sede_arrivo_nome,
                   u.nome as user_nome, u.cognome as user_cognome
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi b ON a.marca_id = b.marca_id
            JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
            JOIN sedi s_arr ON v.sede_arrivo_id = s_arr.sede_id
            JOIN users u ON v.user_id = u.user_id
            WHERE v.ora_arrivo IS NOT NULL AND v.km_finali IS NOT NULL
            ORDER BY v.data_viaggio DESC, v.ora_arrivo DESC
        """)).mappings().all()
        
        veicoli = conn.execute(text("""
            SELECT a.automezzo_id, a.targa, b.nome as marca, a.modello, a.km_attuali, a.sede_attuale_id, s.nome as sede_attuale_nome
            FROM automezzi a 
            JOIN marche_automezzi b ON a.marca_id = b.marca_id 
            LEFT JOIN sedi s ON a.sede_attuale_id = s.sede_id
            ORDER BY b.nome, a.modello
        """)).mappings().all()
        
        operatori = conn.execute(text("""
            SELECT user_id, nome, cognome, ruolo 
            FROM users 
            WHERE attivo = 1 
            ORDER BY cognome, nome
        """)).mappings().all()
        
        sedi = conn.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        
    return templates.TemplateResponse(r, "admin_automezzi_viaggi.html", {
        "request": r, "cfg": CFG, "user": user, 
        "viaggi_attivi": viaggi_attivi, "viaggi_completati": viaggi_completati,
        "veicoli": veicoli, "operatori": operatori, "sedi": sedi
    })

@router.post("/admin/automezzi/viaggi/nuovo")
def add_viaggio(
    r: Request,
    automezzo_id: int = Form(...),
    data_viaggio: str = Form(...),
    ora_partenza: str = Form(...),
    ora_arrivo: str = Form(None),
    km_iniziali: int = Form(...),
    km_finali: int = Form(None),
    sede_partenza_id: int = Form(...),
    sede_arrivo_id: int = Form(None),
    user_id: int = Form(...),
    note: str = Form(None)
):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    ora_arrivo = ora_arrivo.strip() if ora_arrivo and ora_arrivo.strip() else None
    km_finali_val = km_finali if km_finali is not None else None
    sede_arrivo_id_val = sede_arrivo_id if sede_arrivo_id else None
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_arrivo, 
                km_iniziali, km_finali, sede_partenza_id, sede_arrivo_id, user_id, note
            ) VALUES (
                :automezzo_id, :data_viaggio, :ora_partenza, :ora_arrivo,
                :km_iniziali, :km_finali, :sede_partenza_id, :sede_arrivo_id, :user_id, :note
            )
        """), {
            "automezzo_id": automezzo_id, "data_viaggio": data_viaggio, "ora_partenza": ora_partenza,
            "ora_arrivo": ora_arrivo, "km_iniziali": km_iniziali, "km_finali": km_finali_val,
            "sede_partenza_id": sede_partenza_id, "sede_arrivo_id": sede_arrivo_id_val,
            "user_id": user_id, "note": note
        })
        
        if ora_arrivo and km_finali_val is not None:
            conn.execute(text("""
                UPDATE automezzi
                SET stato = 'Disponibile', 
                    km_attuali = MAX(km_attuali, :km_finali),
                    sede_attuale_id = COALESCE(:sede_arrivo_id, sede_attuale_id)
                WHERE automezzo_id = :automezzo_id
            """), {
                "km_finali": km_finali_val,
                "sede_arrivo_id": sede_arrivo_id_val,
                "automezzo_id": automezzo_id
            })
        else:
            conn.execute(text("""
                UPDATE automezzi
                SET stato = 'In Uso',
                    km_attuali = MAX(km_attuali, :km_iniziali),
                    sede_attuale_id = :sede_partenza_id
                WHERE automezzo_id = :automezzo_id
            """), {
                "km_iniziali": km_iniziali,
                "sede_partenza_id": sede_partenza_id,
                "automezzo_id": automezzo_id
            })
            
    return RedirectResponse(url="/admin/automezzi/viaggi", status_code=303)

@router.post("/admin/automezzi/viaggi/completa/{id}")
def complete_viaggio(
    id: int,
    r: Request,
    ora_arrivo: str = Form(...),
    km_finali: int = Form(...),
    sede_arrivo_id: int = Form(...),
    note_finali: str = Form(None)
):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        v = conn.execute(text("SELECT automezzo_id, note FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if v:
            note_complete = (v.note or "") + (f" | Arrivo: {note_finali}" if note_finali else "")
            conn.execute(text("""
                UPDATE viaggi_automezzi
                SET ora_arrivo = :ora_arrivo, km_finali = :km_finali, sede_arrivo_id = :sede_arrivo_id, note = :note
                WHERE viaggio_id = :id
            """), {
                "id": id, "ora_arrivo": ora_arrivo.strip(), "km_finali": km_finali,
                "sede_arrivo_id": sede_arrivo_id, "note": note_complete
            })
            
            conn.execute(text("""
                UPDATE automezzi
                SET stato = 'Disponibile', 
                    km_attuali = MAX(km_attuali, :km_finali),
                    sede_attuale_id = :sede_arrivo_id
                WHERE automezzo_id = :automezzo_id
            """), {
                "automezzo_id": v.automezzo_id,
                "km_finali": km_finali,
                "sede_arrivo_id": sede_arrivo_id
            })
            
    return RedirectResponse(url="/admin/automezzi/viaggi", status_code=303)

@router.post("/admin/automezzi/viaggi/elimina/{id}")
def delete_viaggio(id: int, r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        v = conn.execute(text("SELECT automezzo_id, ora_arrivo FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if v:
            if not v.ora_arrivo:
                conn.execute(text("UPDATE automezzi SET stato = 'Disponibile' WHERE automezzo_id = :automezzo_id"), {"automezzo_id": v.automezzo_id})
            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})
            
    return RedirectResponse(url="/admin/automezzi/viaggi", status_code=303)

