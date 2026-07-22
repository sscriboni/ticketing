import csv
import io
import datetime
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
            escluso_prenotazione INTEGER DEFAULT 0,
            FOREIGN KEY(marca_id) REFERENCES marche_automezzi(marca_id)
        )
    """))
    
    try:
        conn.execute(text("ALTER TABLE automezzi ADD COLUMN escluso_prenotazione INTEGER DEFAULT 0"))
    except Exception:
        pass
        
    try:
        # Per retrocompatibilità database locali pre-aggiornamento
        conn.execute(text("ALTER TABLE automezzi ADD COLUMN marca_id INTEGER DEFAULT 1"))
    except Exception:
        pass
    
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
            ora_riconsegna_prevista TEXT,
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
    
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN ora_riconsegna_prevista TEXT"))
    except Exception:
        pass
    
    # Reset vehicles stuck in 'In Uso' from old booking logic (bookings no longer change vehicle stato)
    try:
        conn.execute(text("UPDATE automezzi SET stato = 'Disponibile' WHERE stato = 'In Uso'"))
    except Exception:
        pass
    
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN email_conducente TEXT"))
    except Exception:
        pass
    
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN ora_partenza_effettiva TEXT"))
    except Exception:
        pass
        
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN in_pausa INTEGER DEFAULT 0"))
    except Exception:
        pass
    
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN minuti_fermo INTEGER DEFAULT 0"))
    except Exception:
        pass
        
    try:
        conn.execute(text("ALTER TABLE viaggi_automezzi ADD COLUMN inizio_pausa TEXT"))
    except Exception:
        pass
        
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS tipi_manutenzione (
            tipo_manutenzione_id {DB_PK},
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            scadenza_anni INTEGER,
            scadenza_mesi INTEGER,
            scadenza_km INTEGER
        )
    """))

    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS automezzi_tipi_manutenzione (
            automezzo_id INTEGER NOT NULL,
            tipo_manutenzione_id INTEGER NOT NULL,
            data_inizio_calcolo TEXT,
            km_partenza_calcolo INTEGER,
            PRIMARY KEY(automezzo_id, tipo_manutenzione_id),
            FOREIGN KEY(automezzo_id) REFERENCES automezzi(automezzo_id) ON DELETE CASCADE,
            FOREIGN KEY(tipo_manutenzione_id) REFERENCES tipi_manutenzione(tipo_manutenzione_id) ON DELETE CASCADE
        )
    """))
    
    # Check if empty to seed initial data for marche
    count_marche = conn.execute(text("SELECT COUNT(*) FROM marche_automezzi")).scalar() or 0
    if count_marche == 0:
        marche_default = ["Fiat", "Tesla", "Audi", "Jeep", "Ford", "Toyota", "Renault", "Volkswagen", "BMW", "Mercedes-Benz", "Peugeot", "Opel"]
        for m in marche_default:
            exists = conn.execute(text("SELECT COUNT(*) FROM marche_automezzi WHERE nome = :nome"), {"nome": m}).scalar()
            if not exists:
                conn.execute(text("INSERT INTO marche_automezzi(nome) VALUES (:nome)"), {"nome": m})
            
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
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/")
    
    user_reparto_id = None
    with engine.connect() as conn:
        if user.get("ruolo") == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()

        # Fetch automezzi
        if user.get("ruolo") == "fleet_manager" and user_reparto_id is not None:
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
                WHERE a.reparto_assegnato_id = :rep
                ORDER BY a.automezzo_id DESC
            """), {"rep": user_reparto_id}).mappings().all()
        else:
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

        # Fetch tipi manutenzione
        tipi_manutenzione_mappings = conn.execute(text("SELECT * FROM tipi_manutenzione ORDER BY nome")).mappings().all()
        tipi_manutenzione = [dict(t) for t in tipi_manutenzione_mappings]

        # Fetch associations
        assoc = conn.execute(text("SELECT automezzo_id, tipo_manutenzione_id, data_inizio_calcolo, km_partenza_calcolo FROM automezzi_tipi_manutenzione")).mappings().all()
        veicolo_tipi = {}
        veicolo_tipi_dati = {}
        for row in assoc:
            aid = row["automezzo_id"]
            tid = row["tipo_manutenzione_id"]
            if aid not in veicolo_tipi:
                veicolo_tipi[aid] = []
                veicolo_tipi_dati[aid] = {}
            veicolo_tipi[aid].append(tid)
            veicolo_tipi_dati[aid][tid] = {
                "data_inizio": row["data_inizio_calcolo"],
                "km_partenza": row["km_partenza_calcolo"]
            }

        # Convert automezzi to dicts and attach types
        veicoli_list = []
        oggi = datetime.date.today()
        for row in automezzi:
            v_dict = dict(row)
            v_dict["tipi_manutenzione_ids"] = veicolo_tipi.get(v_dict["automezzo_id"], [])
            v_dict["tipi_manutenzione_dati"] = veicolo_tipi_dati.get(v_dict["automezzo_id"], {})
            
            v_dict["anzianita_anni"] = None
            if v_dict.get("data_immatricolazione"):
                try:
                    d_imm = datetime.datetime.strptime(v_dict["data_immatricolazione"], "%Y-%m-%d").date()
                    anni = oggi.year - d_imm.year - ((oggi.month, oggi.day) < (d_imm.month, d_imm.day))
                    v_dict["anzianita_anni"] = anni
                except Exception:
                    pass
                    
            veicoli_list.append(v_dict)

    return templates.TemplateResponse(r, "appautopark.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": veicoli_list,
        "sedi": sedi,
        "reparti": reparti,
        "marche": marche,
        "tipi_manutenzione": tipi_manutenzione,
        "user_reparto_id": user_reparto_id
    })

@router.post("/veicolo/nuovo")
async def add_vehicle(
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
    classe_euro: str = Form(None),
    tipi_manutenzione_ids: list[int] = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
        
        # Save associated maintenance types
        new_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
        if tipi_manutenzione_ids:
            form_data = await r.form()
            for tid in tipi_manutenzione_ids:
                d_inizio = form_data.get(f"data_inizio_{tid}")
                km_part = form_data.get(f"km_partenza_{tid}")
                
                din = d_inizio if d_inizio else None
                kmp = int(km_part) if km_part else None
                
                conn.execute(text("""
                    INSERT INTO automezzi_tipi_manutenzione (automezzo_id, tipo_manutenzione_id, data_inizio_calcolo, km_partenza_calcolo)
                    VALUES (:aid, :tid, :din, :kmp)
                """), {"aid": new_id, "tid": int(tid), "din": din, "kmp": kmp})
                
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/veicolo/modifica/{id}")
async def edit_vehicle(
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
    classe_euro: str = Form(None),
    tipi_manutenzione_ids: list[int] = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
        
        # Sync associated maintenance types
        conn.execute(text("DELETE FROM automezzi_tipi_manutenzione WHERE automezzo_id = :id"), {"id": id})
        if tipi_manutenzione_ids:
            form_data = await r.form()
            for tid in tipi_manutenzione_ids:
                d_inizio = form_data.get(f"data_inizio_{tid}")
                km_part = form_data.get(f"km_partenza_{tid}")
                
                din = d_inizio if d_inizio else None
                kmp = int(km_part) if km_part else None

                conn.execute(text("""
                    INSERT INTO automezzi_tipi_manutenzione (automezzo_id, tipo_manutenzione_id, data_inizio_calcolo, km_partenza_calcolo)
                    VALUES (:aid, :tid, :din, :kmp)
                """), {"aid": id, "tid": int(tid), "din": din, "kmp": kmp})
                
    return RedirectResponse(url="/admin/automezzi", status_code=303)

@router.post("/veicolo/elimina/{id}")
def delete_vehicle(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi_tipi_manutenzione WHERE automezzo_id = :id"), {"id": id})
        conn.execute(text("DELETE FROM manutenzioni_automezzi WHERE automezzo_id = :id"), {"id": id})
        conn.execute(text("DELETE FROM viaggi_automezzi WHERE automezzo_id = :id"), {"id": id})
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
        first_line = contents.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        reader = csv.reader(stream, delimiter=delimiter)
    except Exception:
        return RedirectResponse(url="/admin/automezzi/gestione?msg=import_err", status_code=303)
        
    headers = next(reader, None)
    if not headers:
        return RedirectResponse(url="/admin/automezzi/gestione?msg=import_err", status_code=303)
        
    headers = [h.strip().lower() for h in headers]
    imported_count = 0
    
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
            if data_immatricolazione:
                data_immatricolazione = data_immatricolazione.strip()
                parsed = None
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d", "%Y/%m/%d"):
                    try:
                        parsed = datetime.datetime.strptime(data_immatricolazione, fmt)
                        break
                    except ValueError:
                        continue
                if parsed:
                    data_immatricolazione = parsed.strftime("%Y-%m-%d")
                    
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
                        reparto_assegnato_id = :reparto_assegnato_id, fornitore = :fornitore, classe_euro = :classe_euro,
                        escluso_prenotazione = 1
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
                        reparto_assegnato_id, fornitore, classe_euro, escluso_prenotazione
                    ) VALUES (
                        :targa, :marca_id, :modello, :tipo, :colore, :alimentazione, :data_immatricolazione,
                        :proprieta, :canone_noleggio, :km_attuali, :stato, :sede_assegnata_id, :sede_attuale_id,
                        :reparto_assegnato_id, :fornitore, :classe_euro, 1
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
            
            imported_count += 1
                
    if imported_count == 0:
        return RedirectResponse(url="/admin/automezzi/gestione?msg=import_err", status_code=303)
        
    return RedirectResponse(url=f"/admin/automezzi/gestione?msg=import_ok&count={imported_count}", status_code=303)

@router.post("/admin/automezzi/svuota")
def empty_automezzi(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") != "admin":
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi_tipi_manutenzione"))
        conn.execute(text("DELETE FROM manutenzioni_automezzi"))
        conn.execute(text("DELETE FROM viaggi_automezzi"))
        conn.execute(text("DELETE FROM automezzi"))
        
    return RedirectResponse(url="/admin/automezzi/gestione?msg=clear_ok", status_code=303)

@router.get("/admin/automezzi/manutenzioni", response_class=HTMLResponse)
def list_manutenzioni(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
        
        programmate_query = conn.execute(text("""
            SELECT 
                a.automezzo_id, a.targa, b.nome as marca, a.modello, a.km_attuali,
                tm.nome as tipo_nome, tm.scadenza_mesi, tm.scadenza_km,
                atm.data_inizio_calcolo, atm.km_partenza_calcolo
            FROM automezzi a
            JOIN marche_automezzi b ON a.marca_id = b.marca_id
            JOIN automezzi_tipi_manutenzione atm ON a.automezzo_id = atm.automezzo_id
            JOIN tipi_manutenzione tm ON atm.tipo_manutenzione_id = tm.tipo_manutenzione_id
            ORDER BY b.nome, a.modello, tm.nome
        """)).mappings().all()

        def add_months(sourcedate, months):
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, [31, 29 if year%4==0 and (not year%100==0 or year%400==0) else 28, 31,30,31,30,31,31,30,31,30,31][month-1])
            return datetime.date(year, month, day)

        manutenzioni_programmate = []
        oggi = datetime.date.today()

        for row in programmate_query:
            prog = dict(row)
            
            prog['scadenza_stimata_data'] = None
            prog['giorni_rimanenti'] = None
            if prog['scadenza_mesi'] and prog['data_inizio_calcolo']:
                try:
                    d_inizio = datetime.datetime.strptime(prog['data_inizio_calcolo'], "%Y-%m-%d").date()
                    d_scadenza = add_months(d_inizio, prog['scadenza_mesi'])
                    prog['scadenza_stimata_data'] = d_scadenza
                    prog['giorni_rimanenti'] = (d_scadenza - oggi).days
                except:
                    pass
            
            prog['scadenza_stimata_km'] = None
            prog['km_rimanenti'] = None
            if prog['scadenza_km'] and prog['km_partenza_calcolo'] is not None:
                prog['scadenza_stimata_km'] = prog['km_partenza_calcolo'] + prog['scadenza_km']
                if prog['km_attuali'] is not None:
                    prog['km_rimanenti'] = prog['scadenza_stimata_km'] - prog['km_attuali']
            
            prog['stato_scadenza'] = "Regolare"
            prog['alert_class'] = "success"
            
            is_scaduta = False
            is_warning = False
            
            if prog['giorni_rimanenti'] is not None:
                if prog['giorni_rimanenti'] < 0:
                    is_scaduta = True
                elif prog['giorni_rimanenti'] <= 30:
                    is_warning = True
                    
            if prog['km_rimanenti'] is not None:
                if prog['km_rimanenti'] < 0:
                    is_scaduta = True
                elif prog['km_rimanenti'] <= 1000:
                    is_warning = True
                    
            if is_scaduta:
                prog['stato_scadenza'] = "Scaduta"
                prog['alert_class'] = "danger"
            elif is_warning:
                prog['stato_scadenza'] = "In Scadenza"
                prog['alert_class'] = "warning"
                
            manutenzioni_programmate.append(prog)
            
        # Fetch tipi_manutenzione for the add modal
        tipi_manutenzione_mappings = conn.execute(text("SELECT * FROM tipi_manutenzione ORDER BY nome")).mappings().all()
        tipi_manutenzione = [dict(t) for t in tipi_manutenzione_mappings]
        
    return templates.TemplateResponse(r, "admin_automezzi_manutenzioni.html", {
        "request": r, "cfg": CFG, "user": user, "manutenzioni": manutenzioni, "veicoli": veicoli, 
        "manutenzioni_programmate": manutenzioni_programmate, "tipi_manutenzione": tipi_manutenzione
    })

@router.post("/admin/automezzi/manutenzioni/nuova")
def add_manutenzione(
    r: Request,
    automezzo_id: int = Form(...),
    tipo_servizio: str = Form(...),
    data_inizio: str = Form(...),
    ora_inizio: str = Form(...),
    km_registrati: int = Form(...),
    luogo: str = Form(None),
    bloccante: int = Form(0),
    note: str = Form(None)
):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
                SET stato = 'In Manutenzione', km_attuali = CASE WHEN :km_registrati > km_attuali THEN :km_registrati ELSE km_attuali END
                WHERE automezzo_id = :automezzo_id
            """), {"automezzo_id": automezzo_id, "km_registrati": km_registrati})
        else:
            conn.execute(text("""
                UPDATE automezzi 
                SET km_attuali = CASE WHEN :km_registrati > km_attuali THEN :km_registrati ELSE km_attuali END
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
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
                SET stato = 'Disponibile', km_attuali = CASE WHEN :km_fine > km_attuali THEN :km_fine ELSE km_attuali END
                WHERE automezzo_id = :automezzo_id
            """), {"automezzo_id": m.automezzo_id, "km_fine": km_fine})
            
    return RedirectResponse(url="/admin/automezzi/manutenzioni", status_code=303)

@router.post("/admin/automezzi/manutenzioni/elimina/{id}")
def delete_manutenzione(id: int, r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
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
        nome_clean = nome.strip()
        exists = conn.execute(text("SELECT COUNT(*) FROM marche_automezzi WHERE nome = :nome"), {"nome": nome_clean}).scalar()
        if not exists:
            conn.execute(text("INSERT INTO marche_automezzi (nome) VALUES (:nome)"), {"nome": nome_clean})
        
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
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        if user.get("ruolo") == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar() or 0
            
            viaggi_in_corso = conn.execute(text("""
                SELECT v.*, a.targa, b.nome as marca, a.modello,
                       s_part.nome as sede_partenza_nome,
                       u.nome as user_nome, u.cognome as user_cognome
                FROM viaggi_automezzi v
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id
                JOIN marche_automezzi b ON a.marca_id = b.marca_id
                JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
                JOIN users u ON v.user_id = u.user_id
                WHERE a.reparto_assegnato_id = :rep 
                  AND v.ora_partenza_effettiva IS NOT NULL 
                  AND (v.ora_arrivo IS NULL OR v.km_finali IS NULL)
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"rep": user_reparto_id}).mappings().all()

            prenotazioni = conn.execute(text("""
                SELECT v.*, a.targa, b.nome as marca, a.modello,
                       s_part.nome as sede_partenza_nome,
                       u.nome as user_nome, u.cognome as user_cognome
                FROM viaggi_automezzi v
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id
                JOIN marche_automezzi b ON a.marca_id = b.marca_id
                JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
                JOIN users u ON v.user_id = u.user_id
                WHERE a.reparto_assegnato_id = :rep 
                  AND v.ora_partenza_effettiva IS NULL 
                  AND (v.ora_arrivo IS NULL OR v.km_finali IS NULL)
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"rep": user_reparto_id}).mappings().all()
            
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
                WHERE a.reparto_assegnato_id = :rep AND v.ora_arrivo IS NOT NULL AND v.km_finali IS NOT NULL
                ORDER BY v.data_viaggio DESC, v.ora_arrivo DESC
            """), {"rep": user_reparto_id}).mappings().all()
            
            veicoli = conn.execute(text("""
                SELECT a.automezzo_id, a.targa, b.nome as marca, a.modello, a.km_attuali, a.sede_attuale_id, s.nome as sede_attuale_nome
                FROM automezzi a 
                JOIN marche_automezzi b ON a.marca_id = b.marca_id 
                LEFT JOIN sedi s ON a.sede_attuale_id = s.sede_id
                WHERE a.reparto_assegnato_id = :rep
                ORDER BY b.nome, a.modello
            """), {"rep": user_reparto_id}).mappings().all()
        else:
            viaggi_in_corso = conn.execute(text("""
                SELECT v.*, a.targa, b.nome as marca, a.modello,
                       s_part.nome as sede_partenza_nome,
                       u.nome as user_nome, u.cognome as user_cognome
                FROM viaggi_automezzi v
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id
                JOIN marche_automezzi b ON a.marca_id = b.marca_id
                JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
                JOIN users u ON v.user_id = u.user_id
                WHERE v.ora_partenza_effettiva IS NOT NULL 
                  AND (v.ora_arrivo IS NULL OR v.km_finali IS NULL)
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """)).mappings().all()

            prenotazioni = conn.execute(text("""
                SELECT v.*, a.targa, b.nome as marca, a.modello,
                       s_part.nome as sede_partenza_nome,
                       u.nome as user_nome, u.cognome as user_cognome
                FROM viaggi_automezzi v
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id
                JOIN marche_automezzi b ON a.marca_id = b.marca_id
                JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
                JOIN users u ON v.user_id = u.user_id
                WHERE v.ora_partenza_effettiva IS NULL 
                  AND (v.ora_arrivo IS NULL OR v.km_finali IS NULL)
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
        "viaggi_in_corso": viaggi_in_corso, "prenotazioni": prenotazioni, "viaggi_completati": viaggi_completati,
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
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    if user.get("ruolo") == "fleet_manager":
        with engine.connect() as conn:
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            car_reparto_id = conn.execute(text("SELECT reparto_assegnato_id FROM automezzi WHERE automezzo_id = :id"), {"id": automezzo_id}).scalar()
        if car_reparto_id != user_reparto_id:
            import urllib.parse
            return RedirectResponse(url=f"/admin/automezzi/viaggi?error={urllib.parse.quote('Non sei autorizzato a inserire viaggi per veicoli di altri reparti.')}", status_code=303)
        
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
                    km_attuali = CASE WHEN :km_finali > km_attuali THEN :km_finali ELSE km_attuali END,
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
                    km_attuali = CASE WHEN :km_iniziali > km_attuali THEN :km_iniziali ELSE km_attuali END,
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
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    if user.get("ruolo") == "fleet_manager":
        with engine.connect() as conn:
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            car_reparto_id = conn.execute(text("""
                SELECT a.reparto_assegnato_id 
                FROM viaggi_automezzi v 
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id 
                WHERE v.viaggio_id = :vid
            """), {"vid": id}).scalar()
        if car_reparto_id != user_reparto_id:
            import urllib.parse
            return RedirectResponse(url=f"/admin/automezzi/viaggi?error={urllib.parse.quote('Non sei autorizzato a completare viaggi per veicoli di altri reparti.')}", status_code=303)
        
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
                    km_attuali = CASE WHEN :km_finali > km_attuali THEN :km_finali ELSE km_attuali END,
                    sede_attuale_id = :sede_arrivo_id
                WHERE automezzo_id = :automezzo_id
            """), {
                "automezzo_id": v.automezzo_id,
                "km_finali": km_finali,
                "sede_arrivo_id": sede_arrivo_id
            })
            
    return RedirectResponse(url="/admin/automezzi/viaggi", status_code=303)

@router.post("/admin/automezzi/viaggi/elimina/{id}")
def delete_viaggio(id: int, r: Request, nuovi_km: int = Form(None)):
    if "user" not in r.session: 
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    if user.get("ruolo") == "fleet_manager":
        with engine.connect() as conn:
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            car_reparto_id = conn.execute(text("""
                SELECT a.reparto_assegnato_id 
                FROM viaggi_automezzi v 
                JOIN automezzi a ON v.automezzo_id = a.automezzo_id 
                WHERE v.viaggio_id = :vid
            """), {"vid": id}).scalar()
        if car_reparto_id != user_reparto_id:
            import urllib.parse
            return RedirectResponse(url=f"/admin/automezzi/viaggi?error={urllib.parse.quote('Non sei autorizzato a eliminare viaggi per veicoli di altri reparti.')}", status_code=303)
        
    with engine.begin() as conn:
        v = conn.execute(text("SELECT automezzo_id, ora_arrivo FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).mappings().first()
        if v:
            aid = v["automezzo_id"]
            if not v["ora_arrivo"]:
                conn.execute(text("UPDATE automezzi SET stato = 'Disponibile' WHERE automezzo_id = :automezzo_id"), {"automezzo_id": aid})
            
            if nuovi_km is not None:
                conn.execute(text("UPDATE automezzi SET km_attuali = :km WHERE automezzo_id = :aid"), {"km": nuovi_km, "aid": aid})
                
            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})
            
    return RedirectResponse(url="/admin/automezzi/viaggi", status_code=303)

@router.get("/autopark", response_class=HTMLResponse)
def get_autopark(r: Request, msg: str = None, error: str = None):
    if "user" not in r.session: 
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if not CFG.get('modulo_autopark', True):
        return RedirectResponse(url="/")
    
    uid = user.get("id")
    role = user.get("ruolo")
    
    with engine.connect() as conn:
        # Get user's own reparto_id
        user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
        
        # Fetch all vehicles
        veicoli_all = conn.execute(text("""
            SELECT a.*,
                   COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0), 0) AS sede_attuale_id_resolved,
                   m.nome AS marca_nome, s.nome AS sede_attuale_nome
            FROM automezzi a
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0)) = s.sede_id
            ORDER BY m.nome, a.modello
        """)).mappings().all()
        
        veicoli_dicts = []
        for v in veicoli_all:
            veicoli_dicts.append({
                "automezzo_id": v["automezzo_id"],
                "targa": v["targa"],
                "marca_nome": v["marca_nome"],
                "modello": v["modello"],
                "km_attuali": v["km_attuali"],
                "stato": v["stato"],
                "escluso_prenotazione": v["escluso_prenotazione"],
                "sede_attuale_id": v["sede_attuale_id_resolved"],
                "sede_attuale_nome": v["sede_attuale_nome"] or "Tutte le Sedi"
            })
        
        # Build query for bookings
        base_query = """
            SELECT v.*, a.modello, a.targa, m.nome AS marca_nome, s.nome AS sede_partenza_nome,
                   u.nome AS driver_nome, u.cognome AS driver_cognome, u.email AS driver_email
            FROM viaggi_automezzi v
            JOIN automezzi a ON v.automezzo_id = a.automezzo_id
            JOIN marche_automezzi m ON a.marca_id = m.marca_id
            LEFT JOIN sedi s ON v.sede_partenza_id = s.sede_id
            JOIN users u ON v.user_id = u.user_id
        """
        
        if role in ("admin", "global_fleet_manager"):
            bookings_raw = conn.execute(text(base_query + " ORDER BY v.data_viaggio DESC, v.ora_partenza DESC")).mappings().all()
        elif role == "fleet_manager" and user_reparto_id is not None:
            bookings_raw = conn.execute(text(base_query + """
                WHERE u.reparto_id = :rep_id
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"rep_id": user_reparto_id}).mappings().all()
        else:
            bookings_raw = conn.execute(text(base_query + """
                WHERE v.user_id = :uid
                ORDER BY v.data_viaggio DESC, v.ora_partenza DESC
            """), {"uid": uid}).mappings().all()
            
        now = datetime.datetime.now()
        attive_list = []
        passate_list = []
        
        for p in bookings_raw:
            p_dict = dict(p)
            has_started = bool(p.get("ora_partenza_effettiva"))
            has_ended = bool(p.get("ora_arrivo"))
            
            p_dict["is_in_corso"] = has_started and not has_ended
            p_dict["in_pausa"] = bool(p.get("in_pausa", 0))
            p_dict["can_start"] = not has_started and not has_ended
            p_dict["can_complete"] = has_started and not has_ended
            
            try:
                reconsegna_dt = datetime.datetime.strptime(f"{p['data_viaggio']} {p['ora_riconsegna_prevista']}", "%Y-%m-%d %H:%M")
                is_past = now > reconsegna_dt
            except Exception:
                is_past = False
                
            if has_ended:
                passate_list.append(p_dict)
            elif is_past and not has_started:
                passate_list.append(p_dict)
            else:
                attive_list.append(p_dict)
                
        # Fetch all locations (sedi) with count of available vehicles
        sedi_list = conn.execute(text("""
            SELECT s.sede_id, s.nome,
                   (SELECT COUNT(*) FROM automezzi a 
                    WHERE (a.sede_attuale_id = s.sede_id 
                           OR a.sede_assegnata_id = s.sede_id
                           OR COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0), 0) = 0)
                      AND a.stato = 'Disponibile' 
                      AND a.escluso_prenotazione = 0) AS auto_disponibili
            FROM sedi s
            ORDER BY s.nome
        """)).mappings().all()
        
        # Instant booking properties
        instant_mode = r.query_params.get("instant") == "1"
        instant_date = now.strftime("%Y-%m-%d")
        instant_hour = now.strftime("%H:00")
        instant_actual_time = now.strftime("%H:%M")
        info = r.query_params.get("info")
        
    return templates.TemplateResponse(r, "autopark.html", {
        "request": r, 
        "cfg": CFG, 
        "user": user, 
        "veicoli": veicoli_dicts, 
        "prenotazioni_attive": attive_list, 
        "prenotazioni_passate": passate_list, 
        "sedi": sedi_list,
        "msg": msg,
        "error": error,
        "info": info,
        "instant": instant_mode,
        "instant_date": instant_date,
        "instant_hour": instant_hour,
        "instant_actual_time": instant_actual_time
    })

@router.post("/autopark/prenota")
def prenota_automezzo(
    r: Request,
    automezzo_id: int = Form(...),
    data_viaggio: str = Form(...),
    ora_partenza: str = Form(...),
    ora_riconsegna_prevista: str = Form(...),
    sede_partenza_id: int = Form(...),
    email_conducente: str = Form(None),
    note: str = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    role = user.get("ruolo")
    current_email = user.get("email")

    try:
        travel_dt = datetime.datetime.strptime(f"{data_viaggio} {ora_partenza}", "%Y-%m-%d %H:%M")
        if travel_dt <= datetime.datetime.now():
            import urllib.parse
            err_msg = urllib.parse.quote("La data e l'ora di partenza devono essere nel futuro.")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
    except Exception:
        import urllib.parse
        err_msg = urllib.parse.quote("Formato data o ora non valido.")
        return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)

    # Validate return hour is after departure hour
    if ora_riconsegna_prevista <= ora_partenza:
        import urllib.parse
        err_msg = urllib.parse.quote("L'ora di riconsegna deve essere successiva all'ora di partenza.")
        return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
    
    # 1. Resolve final_email of the driver based on role permissions
    if role in ("admin", "fleet_manager", "global_fleet_manager") and email_conducente:
        final_email = email_conducente.strip().lower()
    else:
        final_email = current_email.strip().lower() if current_email else ""
        
    with engine.connect() as conn:
        # Check if the driver user exists and is active
        driver = conn.execute(text("""
            SELECT user_id, reparto_id, email, nome, cognome 
            FROM users 
            WHERE LOWER(email) = LOWER(:email) AND attivo = 1
        """), {"email": final_email}).first()
        
    if not driver:
        import urllib.parse
        err_msg = urllib.parse.quote("Nessun utente attivo trovato con l'email del conducente indicata.")
        return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
        
    with engine.begin() as conn:
        # 2. Check department constraint for fleet manager
        if role == "fleet_manager":
            fm_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
            if driver.reparto_id != fm_reparto_id:
                import urllib.parse
                err_msg = urllib.parse.quote("Puoi prenotare solo per utenti appartenenti al tuo stesso reparto.")
                return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
                
        # 3. Check if the vehicle exists, is not excluded, and is at the correct location
        car = conn.execute(text("SELECT stato, km_attuali, escluso_prenotazione, sede_attuale_id, sede_assegnata_id FROM automezzi WHERE automezzo_id = :id"), {"id": automezzo_id}).first()
        car_sede = (car.sede_attuale_id if car and car.sede_attuale_id else (car.sede_assegnata_id if car else 0)) or 0
        if not car or car.escluso_prenotazione == 1 or (car_sede != 0 and car_sede != sede_partenza_id):
            import urllib.parse
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Il veicolo selezionato non è disponibile per questa sede di partenza.')}", status_code=303)
            
        km_iniziali = car.km_attuali or 0
        
        # 4. Check for time-slot overlap with existing bookings for this vehicle on this date
        overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE automezzo_id = :automezzo_id
              AND data_viaggio = :data_viaggio
              AND ora_arrivo IS NULL
              AND ora_partenza < :ora_riconsegna
              AND ora_riconsegna_prevista > :ora_partenza
        """), {
            "automezzo_id": automezzo_id,
            "data_viaggio": data_viaggio,
            "ora_partenza": ora_partenza,
            "ora_riconsegna": ora_riconsegna_prevista
        }).first()
        
        if overlap:
            import urllib.parse
            err_msg = urllib.parse.quote("Il veicolo è già prenotato in questa fascia oraria.")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
            
        # 5. Check for driver time-slot overlap on this date
        driver_overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :driver_id
              AND data_viaggio = :data_viaggio
              AND ora_arrivo IS NULL
              AND ora_partenza < :ora_riconsegna
              AND ora_riconsegna_prevista > :ora_partenza
        """), {
            "driver_id": driver.user_id,
            "data_viaggio": data_viaggio,
            "ora_partenza": ora_partenza,
            "ora_riconsegna": ora_riconsegna_prevista
        }).first()
        
        if driver_overlap:
            import urllib.parse
            err_msg = urllib.parse.quote("Il guidatore indicato ha già un'altra prenotazione attiva in questa fascia oraria.")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
        
        # 6. Insert new voyage record
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista, ora_arrivo, 
                km_iniziali, km_finali, sede_partenza_id, sede_arrivo_id, user_id, email_conducente, ora_partenza_effettiva, note
            ) VALUES (
                :automezzo_id, :data_viaggio, :ora_partenza, :ora_riconsegna_prevista, NULL,
                :km_iniziali, NULL, :sede_partenza_id, NULL, :user_id, :email_conducente, NULL, :note
            )
        """), {
            "automezzo_id": automezzo_id,
            "data_viaggio": data_viaggio,
            "ora_partenza": ora_partenza,
            "ora_riconsegna_prevista": ora_riconsegna_prevista,
            "km_iniziali": km_iniziali,
            "sede_partenza_id": sede_partenza_id,
            "user_id": driver.user_id,
            "email_conducente": driver.email,
            "note": note
        })
        
    return RedirectResponse(url="/autopark?msg=booked", status_code=303)

@router.post("/autopark/parti/{id}")
def parti_viaggio(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    
    with engine.begin() as conn:
        v = conn.execute(text("""
            SELECT viaggio_id, ora_partenza_effettiva
            FROM viaggi_automezzi
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()
        
        if not v:
            import urllib.parse
            err_msg = urllib.parse.quote("Prenotazione non trovata.")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
        
        if v.ora_partenza_effettiva:
            import urllib.parse
            err_msg = urllib.parse.quote("Il viaggio è già stato avviato.")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)
        
        now_str = datetime.datetime.now().strftime("%H:%M")
        conn.execute(text("""
            UPDATE viaggi_automezzi SET ora_partenza_effettiva = :ora WHERE viaggio_id = :id
        """), {"ora": now_str, "id": id})
    
    return RedirectResponse(url="/autopark?msg=started", status_code=303)

@router.post("/autopark/completa/{id}")
def completa_prenotazione(
    id: int,
    r: Request,
    km_finali: int = Form(...),
    sede_arrivo_id: int = Form(...),
    ora_arrivo: str = Form(...),
    note_finali: str = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    
    with engine.begin() as conn:
        # Fetch the voyage, verifying it belongs to the user
        v = conn.execute(text("""
            SELECT automezzo_id, km_iniziali, note, data_viaggio, ora_partenza, ora_partenza_effettiva, in_pausa, inizio_pausa, minuti_fermo
            FROM viaggi_automezzi 
            WHERE viaggio_id = :id AND user_id = :uid AND ora_arrivo IS NULL
        """), {"id": id, "uid": uid}).first()
        
        if not v:
            import urllib.parse
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Prenotazione non trovata o già completata.')}", status_code=303)
        
        if not v.ora_partenza_effettiva:
            import urllib.parse
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Devi prima avviare il viaggio con il pulsante Registra Viaggio.')}", status_code=303)

        # Validate that ora_arrivo is greater than ora_partenza_effettiva
        if ora_arrivo <= v.ora_partenza_effettiva:
            import urllib.parse
            err_msg = urllib.parse.quote(f"L'orario di rientro ({ora_arrivo}) deve essere successivo all'orario di partenza effettiva ({v.ora_partenza_effettiva}).")
            return RedirectResponse(url=f"/autopark?error={err_msg}", status_code=303)

        # Check if date has changed (compare today's date with data_viaggio)
        today_str = datetime.date.today().isoformat()
        warning_msg = None
        if today_str != v.data_viaggio:
            warning_msg = "Attenzione: la data corrente è diversa da quella di partenza. Il viaggio è stato registrato con data di fine pari alla data di partenza."
            
        import datetime as dt_mod
        minutes_fermo = v.minuti_fermo or 0
        if v.in_pausa and v.inizio_pausa:
            try:
                # Calculate pause duration up to the return time on data_viaggio
                inizio = dt_mod.datetime.fromisoformat(v.inizio_pausa)
                rientro_dt = dt_mod.datetime.strptime(f"{v.data_viaggio} {ora_arrivo}", "%Y-%m-%d %H:%M")
                if rientro_dt > inizio:
                    delta = rientro_dt - inizio
                    minutes_fermo += int(delta.total_seconds() / 60)
            except Exception:
                pass
            
        if km_finali < v.km_iniziali:
            import urllib.parse
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote(f'I km finali ({km_finali}) non possono essere inferiori a quelli iniziali ({v.km_iniziali}).')}", status_code=303)
            
        note_complete = (v.note or "") + (f" | Rientro: {note_finali}" if note_finali else "")
        
        # Update voyage record
        conn.execute(text("""
            UPDATE viaggi_automezzi
            SET ora_arrivo = :ora_arrivo, km_finali = :km_finali, sede_arrivo_id = :sede_arrivo_id, note = :note,
                in_pausa = 0, inizio_pausa = NULL, minuti_fermo = :minuti_fermo
            WHERE viaggio_id = :id
        """), {
            "id": id,
            "ora_arrivo": ora_arrivo,
            "km_finali": km_finali,
            "sede_arrivo_id": sede_arrivo_id,
            "note": note_complete,
            "minuti_fermo": minutes_fermo
        })
        
        # Update vehicle km and location
        conn.execute(text("""
            UPDATE automezzi
            SET km_attuali = CASE WHEN :km_finali > km_attuali THEN :km_finali ELSE km_attuali END,
                sede_attuale_id = :sede_arrivo_id
            WHERE automezzo_id = :automezzo_id
        """), {
            "automezzo_id": v.automezzo_id,
            "km_finali": km_finali,
            "sede_arrivo_id": sede_arrivo_id
        })
        
    import urllib.parse
    if warning_msg:
        return RedirectResponse(url=f"/autopark?msg={urllib.parse.quote(warning_msg)}", status_code=303)
    else:
        return RedirectResponse(url="/autopark?msg=completed", status_code=303)


@router.post("/autopark/annulla-viaggio/{id}")
def annulla_viaggio_fleet(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    role = user.get("ruolo")
    
    import urllib.parse
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        if not booking:
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Prenotazione non trovata.')}", status_code=303)
        if booking.user_id != uid and role not in ("admin", "global_fleet_manager"):
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Non sei autorizzato ad annullare questo viaggio.')}", status_code=303)
            
        conn.execute(text("UPDATE viaggi_automezzi SET ora_partenza_effettiva = NULL, in_pausa = 0 WHERE viaggio_id = :id"), {"id": id})
        
    return RedirectResponse(url=f"/autopark?msg={urllib.parse.quote('Avvio viaggio annullato. Stato prenotazione ripristinato.')}", status_code=303)


@router.post("/autopark/elimina/{id}")
def elimina_prenotazione(id: int, r: Request, nuovi_km: int = Form(None)):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    role = user.get("ruolo")
    
    import urllib.parse
    with engine.begin() as conn:
        if role in ("admin", "global_fleet_manager"):
            v = conn.execute(text("SELECT automezzo_id, km_iniziali, km_finali, user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).mappings().first()
        elif role == "fleet_manager":
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar() or 0
            v = conn.execute(text("""
                SELECT v.automezzo_id, v.km_iniziali, v.km_finali, v.user_id, v.ora_partenza_effettiva
                FROM viaggi_automezzi v
                JOIN users u ON v.user_id = u.user_id
                WHERE v.viaggio_id = :id AND u.reparto_id = :rep
            """), {"id": id, "rep": user_reparto_id}).mappings().first()
        else:
            # Normal user / operator: can only delete their own booking if not started yet
            v = conn.execute(
                text("SELECT automezzo_id, km_iniziali, km_finali, user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id AND user_id = :uid"),
                {"id": id, "uid": uid},
            ).mappings().first()
            
        if not v:
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Prenotazione non trovata o non sei autorizzato a eliminarla.')}", status_code=303)
            
        if role not in ("admin", "fleet_manager", "global_fleet_manager") and v["ora_partenza_effettiva"]:
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote('Non puoi eliminare un viaggio che è già iniziato o completato.')}", status_code=303)
            
        if v:
            k_init = v["km_iniziali"] or 0
            k_fin = v["km_finali"]
            aid = v["automezzo_id"]
            if k_fin is not None:
                diff = k_fin - k_init
                msg_text = f"Viaggio eliminato con successo! Il tragitto comprendeva {diff} km (KM Partenza: {k_init}, KM Arrivo: {k_fin})."
            else:
                msg_text = f"Prenotazione eliminata con successo! (KM iniziali veicolo: {k_init})."
                
            if nuovi_km is not None and role in ("admin", "fleet_manager", "global_fleet_manager"):
                conn.execute(text("UPDATE automezzi SET km_attuali = :km WHERE automezzo_id = :aid"), {"km": nuovi_km, "aid": aid})
                msg_text += f" I chilometri dell'auto sono stati impostati a {nuovi_km} km."
                
            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id})
            return RedirectResponse(url=f"/autopark?msg={urllib.parse.quote(msg_text)}", status_code=303)
            
    return RedirectResponse(url="/autopark?msg=deleted", status_code=303)

@router.post("/admin/automezzi/{id}/toggle-prenotazione")
def toggle_prenotazione_veicolo(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "fleet_manager", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        # Check vehicle reparto
        car = conn.execute(text("SELECT reparto_assegnato_id, escluso_prenotazione FROM automezzi WHERE automezzo_id = :id"), {"id": id}).first()
        if not car:
            return RedirectResponse(url="/admin/automezzi", status_code=303)
            
        if user.get("ruolo") == "fleet_manager":
            # Fetch fleet manager's reparto_id
            user_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if car.reparto_assegnato_id != user_reparto_id:
                import urllib.parse
                return RedirectResponse(url=f"/admin/automezzi?error={urllib.parse.quote('Non sei autorizzato a gestire i veicoli di altri reparti.')}", status_code=303)
                
        new_val = 1 if car.escluso_prenotazione == 0 else 0
        conn.execute(text("UPDATE automezzi SET escluso_prenotazione = :new_val WHERE automezzo_id = :id"), {"new_val": new_val, "id": id})
        
    return RedirectResponse(url="/admin/automezzi", status_code=303)


@router.post("/autopark/registra-viaggio")
def registra_viaggio(r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    today_str = datetime.date.today().isoformat()
    
    with engine.begin() as conn:
        # Find any active booking for the user today/past that has not started yet
        b = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :uid AND data_viaggio <= :today AND ora_partenza_effettiva IS NULL AND ora_arrivo IS NULL
            ORDER BY data_viaggio ASC, ora_partenza ASC
        """), {"uid": uid, "today": today_str}).mappings().first()
        
        if b:
            now_str = datetime.datetime.now().strftime("%H:%M")
            conn.execute(text("""
                UPDATE viaggi_automezzi
                SET ora_partenza_effettiva = :now_time, in_pausa = 0
                WHERE viaggio_id = :id
            """), {"now_time": now_str, "id": b["viaggio_id"]})
            return RedirectResponse(url="/autopark?msg=started", status_code=303)
        else:
            return RedirectResponse(url="/autopark?instant=1&info=no_booking", status_code=303)


@router.post("/autopark/registra-viaggio-istantaneo")
def registra_viaggio_istantaneo(
    r: Request,
    automezzo_id: int = Form(...),
    sede_partenza_id: int = Form(...),
    ora_riconsegna_prevista: str = Form(...),
    note: str = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    
    now = datetime.datetime.now()
    data_viaggio = now.strftime("%Y-%m-%d")
    ora_partenza = now.strftime("%H:00")
    ora_partenza_eff = now.strftime("%H:%M")
    
    import urllib.parse
    if ora_riconsegna_prevista <= ora_partenza:
        err_msg = "L'ora di riconsegna deve essere successiva all'ora di partenza."
        return RedirectResponse(url=f"/autopark?instant=1&error={urllib.parse.quote(err_msg)}", status_code=303)
        
    with engine.connect() as conn:
        # Check if user active
        driver = conn.execute(text("""
            SELECT user_id, reparto_id, email, nome, cognome 
            FROM users 
            WHERE user_id = :uid AND attivo = 1
        """), {"uid": uid}).first()
        
    if not driver:
        err_msg = "Utente conducente non trovato o non attivo."
        return RedirectResponse(url=f"/autopark?instant=1&error={urllib.parse.quote(err_msg)}", status_code=303)
        
    with engine.begin() as conn:
        # Check vehicle status and location
        car = conn.execute(
            text("SELECT km_attuali, escluso_prenotazione, sede_attuale_id, sede_assegnata_id FROM automezzi WHERE automezzo_id = :id"),
            {"id": automezzo_id},
        ).first()
        car_sede = (car.sede_attuale_id if car and car.sede_attuale_id else (car.sede_assegnata_id if car else 0)) or 0
        
        if not car or car.escluso_prenotazione == 1 or (car_sede != 0 and car_sede != sede_partenza_id):
            err_msg = "Il veicolo selezionato non è disponibile per questa sede di partenza."
            return RedirectResponse(url=f"/autopark?instant=1&error={urllib.parse.quote(err_msg)}", status_code=303)
            
        # Vehicle overlap
        overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE automezzo_id = :aid AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()
        
        if overlap:
            err_msg = "Il veicolo è già prenotato in questa fascia oraria."
            return RedirectResponse(url=f"/autopark?instant=1&error={urllib.parse.quote(err_msg)}", status_code=303)
            
        # Driver overlap
        driver_overlap = conn.execute(text("""
            SELECT viaggio_id FROM viaggi_automezzi
            WHERE user_id = :driver_id AND data_viaggio = :dv AND ora_arrivo IS NULL
              AND ora_partenza < :orc AND ora_riconsegna_prevista > :op
        """), {
            "driver_id": uid, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
        }).first()
        
        if driver_overlap:
            err_msg = "Hai già un'altra prenotazione attiva in questa fascia oraria."
            return RedirectResponse(url=f"/autopark?instant=1&error={urllib.parse.quote(err_msg)}", status_code=303)
            
        km_iniziali = car.km_attuali or 0
        conn.execute(text("""
            INSERT INTO viaggi_automezzi (
                automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista,
                ora_arrivo, km_iniziali, km_finali,
                sede_partenza_id, sede_arrivo_id, user_id, email_conducente, ora_partenza_effettiva, note, in_pausa
            ) VALUES (
                :aid, :dv, :op, :orc, NULL, :km, NULL, :sp, NULL, :driver_uid, :email, :ora_partenza_eff, :note, 0
            )
        """), {
            "aid": automezzo_id, "dv": data_viaggio,
            "op": ora_partenza, "orc": ora_riconsegna_prevista,
            "km": km_iniziali, "sp": sede_partenza_id,
            "driver_uid": uid, "email": driver.email, "ora_partenza_eff": ora_partenza_eff, "note": note,
        })
        
    return RedirectResponse(url="/autopark?msg=started", status_code=303)


@router.post("/autopark/avvia/{id}")
def avvia_prenotazione_id(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, ora_partenza_effettiva FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        import urllib.parse
        if not booking:
            err_msg = "Prenotazione non trovata."
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote(err_msg)}", status_code=303)
        if booking.user_id != uid and user.get("ruolo") not in ("admin", "global_fleet_manager"):
            err_msg = "Non sei autorizzato ad avviare questo viaggio."
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote(err_msg)}", status_code=303)
            
        now_str = datetime.datetime.now().strftime("%H:%M")
        conn.execute(text("UPDATE viaggi_automezzi SET ora_partenza_effettiva = :now, in_pausa = 0 WHERE viaggio_id = :id"), {"now": now_str, "id": id})
        
    return RedirectResponse(url="/autopark?msg=started", status_code=303)


@router.post("/autopark/pausa/{id}")
def toggle_pausa(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    uid = user.get("id")
    
    with engine.begin() as conn:
        booking = conn.execute(text("SELECT user_id, in_pausa, inizio_pausa, minuti_fermo FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": id}).first()
        import urllib.parse
        if not booking:
            err_msg = "Prenotazione non trovata."
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote(err_msg)}", status_code=303)
        if booking.user_id != uid and user.get("ruolo") not in ("admin", "global_fleet_manager"):
            err_msg = "Non sei autorizzato a modificare questo viaggio."
            return RedirectResponse(url=f"/autopark?error={urllib.parse.quote(err_msg)}", status_code=303)
            
        now = datetime.datetime.now()
        if not booking.in_pausa:
            # Entering pause
            conn.execute(text("""
                UPDATE viaggi_automezzi 
                SET in_pausa = 1, inizio_pausa = :inizio 
                WHERE viaggio_id = :id
            """), {"inizio": now.isoformat(), "id": id})
            msg_type = "paused"
        else:
            # Resuming from pause
            minutes_elapsed = 0
            if booking.inizio_pausa:
                try:
                    inizio = datetime.datetime.fromisoformat(booking.inizio_pausa)
                    delta = now - inizio
                    minutes_elapsed = int(delta.total_seconds() / 60)
                except Exception:
                    pass
            conn.execute(text("""
                UPDATE viaggi_automezzi 
                SET in_pausa = 0, inizio_pausa = NULL, minuti_fermo = COALESCE(minuti_fermo, 0) + :elapsed 
                WHERE viaggio_id = :id
            """), {"elapsed": minutes_elapsed, "id": id})
            msg_type = "resumed"
        
    return RedirectResponse(url=f"/autopark?msg={msg_type}", status_code=303)


@router.get("/admin/automezzi/tipi-manutenzione", response_class=HTMLResponse)
def list_tipi_manutenzione(r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
        return RedirectResponse(url="/")
        
    with engine.connect() as conn:
        tipi_mappings = conn.execute(text("SELECT * FROM tipi_manutenzione ORDER BY nome")).mappings().all()
        tipi = [dict(t) for t in tipi_mappings]
        
    return templates.TemplateResponse(r, "admin_automezzi_tipi_manutenzione.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "tipi": tipi
    })

@router.post("/admin/automezzi/tipi-manutenzione/aggiungi")
def add_tipo_manutenzione(
    r: Request,
    nome: str = Form(...),
    categoria: str = Form(...),
    scadenza_anni: int = Form(None),
    scadenza_mesi: int = Form(None),
    scadenza_km: int = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tipi_manutenzione (nome, categoria, scadenza_anni, scadenza_mesi, scadenza_km)
            VALUES (:nome, :categoria, :scadenza_anni, :scadenza_mesi, :scadenza_km)
        """), {
            "nome": nome.strip(),
            "categoria": categoria,
            "scadenza_anni": scadenza_anni if scadenza_anni else None,
            "scadenza_mesi": scadenza_mesi if scadenza_mesi else None,
            "scadenza_km": scadenza_km if scadenza_km else None
        })
    return RedirectResponse(url="/admin/automezzi/tipi-manutenzione", status_code=303)

@router.post("/admin/automezzi/tipi-manutenzione/modifica/{id}")
def edit_tipo_manutenzione(
    id: int,
    r: Request,
    nome: str = Form(...),
    categoria: str = Form(...),
    scadenza_anni: int = Form(None),
    scadenza_mesi: int = Form(None),
    scadenza_km: int = Form(None)
):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE tipi_manutenzione SET
                nome = :nome,
                categoria = :categoria,
                scadenza_anni = :scadenza_anni,
                scadenza_mesi = :scadenza_mesi,
                scadenza_km = :scadenza_km
            WHERE tipo_manutenzione_id = :id
        """), {
            "id": id,
            "nome": nome.strip(),
            "categoria": categoria,
            "scadenza_anni": scadenza_anni if scadenza_anni else None,
            "scadenza_mesi": scadenza_mesi if scadenza_mesi else None,
            "scadenza_km": scadenza_km if scadenza_km else None
        })
    return RedirectResponse(url="/admin/automezzi/tipi-manutenzione", status_code=303)

@router.post("/admin/automezzi/tipi-manutenzione/elimina/{id}")
def delete_tipo_manutenzione(id: int, r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login", status_code=303)
    user = r.session.get("user")
    if user.get("ruolo") not in ("admin", "global_fleet_manager"):
        return RedirectResponse(url="/", status_code=303)
        
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM automezzi_tipi_manutenzione WHERE tipo_manutenzione_id = :id"), {"id": id})
        conn.execute(text("DELETE FROM tipi_manutenzione WHERE tipo_manutenzione_id = :id"), {"id": id})
    return RedirectResponse(url="/admin/automezzi/tipi-manutenzione", status_code=303)

