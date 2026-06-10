import os, json, csv, io, shutil, uuid, traceback
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, text
import bcrypt

from core import CFG, BASE_DIR, UPLOAD_DIR, engine, DB_TYPE, DB_PK, DB_DRIVER, templates
from utils import current_user, require_superuser, save_upload
from email_utils import send_email_async
import auth
import magazzini

# Init schema + seed
with engine.begin() as c:
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS reparti (
        reparto_id {DB_PK},
        nome TEXT NOT NULL,
        descrizione TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS servizi (
        servizio_id {DB_PK},
        descrizione TEXT NOT NULL,
        reparto_id INTEGER NOT NULL,
        accetta_ticket INTEGER DEFAULT 1
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS users (
        user_id {DB_PK},
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nome TEXT NOT NULL,
        cognome TEXT NOT NULL,
        email TEXT NOT NULL,
        telefono TEXT,
        ruolo TEXT NOT NULL,
        reparto_id INTEGER,
        attivo INTEGER DEFAULT 1,
        is_test INTEGER DEFAULT 0
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS operatori_servizi (
        id {DB_PK},
        user_id INTEGER NOT NULL,
        servizio_id INTEGER NOT NULL,
        UNIQUE(user_id, servizio_id)
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS tickets (
        ticket_id {DB_PK},
        codice_ticket TEXT,
        nome TEXT NOT NULL,
        cognome TEXT NOT NULL,
        email TEXT,
        telefono TEXT,
        sede TEXT,
        riferimento TEXT,
        reparto_id INTEGER,
        servizio_id INTEGER,
        descrizione TEXT NOT NULL,
        priorita TEXT DEFAULT 'media',
        stato TEXT DEFAULT 'nuova',
        ip TEXT,
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
        is_test INTEGER DEFAULT 0,
        reparto_appartenenza TEXT,
        allegato TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS ticket_notes (
        note_id {DB_PK},
        ticket_id INTEGER NOT NULL,
        autore TEXT,
        testo TEXT NOT NULL,
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
        allegato TEXT,
        is_internal INTEGER DEFAULT 0
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS assenze (
        assenza_id {DB_PK},
        user_id INTEGER NOT NULL,
        data_inizio TEXT NOT NULL,
        data_fine TEXT NOT NULL,
        motivo TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS festivita (
        festivita_id {DB_PK},
        data TEXT NOT NULL,
        descrizione TEXT NOT NULL
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS sedi (
        sede_id {DB_PK},
        nome TEXT NOT NULL
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS comuni (
        comune_id {DB_PK},
        nome TEXT UNIQUE NOT NULL
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS ruoli (
        ruolo_id {DB_PK},
        nome TEXT UNIQUE NOT NULL,
        descrizione TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS categorie (
        categoria_id {DB_PK},
        nome TEXT UNIQUE NOT NULL
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS materiali (
        materiale_id {DB_PK},
        nome TEXT UNIQUE NOT NULL,
        categoria_id INTEGER
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS ticket_materiali (
        id {DB_PK},
        ticket_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        quantita INTEGER NOT NULL
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS magazzini (
        magazzino_id {DB_PK},
        nome TEXT NOT NULL,
        sede_id INTEGER,
        categoria_id INTEGER,
        reparto_id INTEGER
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS giacenze (
        giacenza_id {DB_PK},
        magazzino_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        quantita INTEGER DEFAULT 0,
        UNIQUE(magazzino_id, materiale_id)
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS movimenti_magazzino (
        movimento_id {DB_PK},
        magazzino_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        operazione TEXT NOT NULL,
        quantita INTEGER NOT NULL,
        data_movimento TEXT NOT NULL,
        descrizione TEXT,
        sede_assegnazione_id INTEGER,
        posizione_fisica TEXT,
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
        marca TEXT,
        modello TEXT,
        allegato TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS trasferimenti (
        trasferimento_id {DB_PK},
        magazzino_partenza_id INTEGER NOT NULL,
        magazzino_dest_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        quantita INTEGER NOT NULL,
        stato TEXT DEFAULT 'in_consegna',
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
        user_partenza_id INTEGER NOT NULL,
        user_arrivo_id INTEGER,
        data_arrivo TEXT,
        note TEXT,
        allegato TEXT
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS avvisi (
        avviso_id {DB_PK},
        user_id INTEGER NOT NULL,
        servizio_id INTEGER,
        titolo TEXT NOT NULL,
        testo TEXT NOT NULL,
        gravita TEXT DEFAULT 'info',
        data_inizio TEXT,
        data_fine TEXT,
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS richieste_materiale (
        richiesta_id {DB_PK},
        user_id INTEGER NOT NULL,
        sede_dest_id INTEGER NOT NULL,
        categoria_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        quantita INTEGER NOT NULL,
        magazzino_id INTEGER,
        ticket_id INTEGER,
        stato TEXT DEFAULT 'nuova',
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP
    )"""))
    c.execute(text(f"""CREATE TABLE IF NOT EXISTS consegne_programmate (
        consegna_id {DB_PK},
        magazzino_id INTEGER NOT NULL,
        materiale_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        quantita INTEGER NOT NULL,
        data_programmata TEXT,
        descrizione TEXT,
        sede_assegnazione_id INTEGER,
        posizione_fisica TEXT,
        marca TEXT,
        modello TEXT,
        allegato TEXT,
        stato TEXT DEFAULT 'programmata',
        data_consegna_effettiva TEXT,
        user_consegna_id INTEGER,
        creato_il TEXT DEFAULT CURRENT_TIMESTAMP
    )"""))

    for stmt in [
        "ALTER TABLE tickets ADD COLUMN codice_ticket TEXT",
        "ALTER TABLE tickets ADD COLUMN riferimento TEXT",
        "ALTER TABLE tickets ADD COLUMN reparto_id INTEGER",
        "ALTER TABLE tickets ADD COLUMN servizio_id INTEGER",
        "ALTER TABLE tickets ADD COLUMN ip TEXT",
        "ALTER TABLE tickets ADD COLUMN reparto_appartenenza_id INTEGER",
        "ALTER TABLE tickets ADD COLUMN reparto_appartenenza TEXT",
        "ALTER TABLE users ADD COLUMN ultimo_accesso TEXT",
        "ALTER TABLE users ADD COLUMN reset_token TEXT",
        "ALTER TABLE users ADD COLUMN reset_expires TEXT",
        "ALTER TABLE reparti ADD COLUMN accetta_ticket INTEGER DEFAULT 1",
        "ALTER TABLE servizi ADD COLUMN accetta_ticket INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN is_test INTEGER DEFAULT 0",
        "ALTER TABLE tickets ADD COLUMN is_test INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN sede_id INTEGER",
        "ALTER TABLE tickets ADD COLUMN allegato TEXT",
        "ALTER TABLE ticket_notes ADD COLUMN allegato TEXT",
        "ALTER TABLE ticket_notes ADD COLUMN is_internal INTEGER DEFAULT 0",
        "ALTER TABLE materiali ADD COLUMN tipologia TEXT",
        "ALTER TABLE materiali ADD COLUMN categoria_id INTEGER",
        "ALTER TABLE magazzini ADD COLUMN categoria_id INTEGER",
        "ALTER TABLE magazzini ADD COLUMN reparto_id INTEGER",
        "ALTER TABLE users ADD COLUMN magazzino_id INTEGER",
        "ALTER TABLE movimenti_magazzino ADD COLUMN allegato TEXT",
        "ALTER TABLE users ADD COLUMN telefono TEXT",
        "ALTER TABLE sedi ADD COLUMN comune_id INTEGER",
        "ALTER TABLE movimenti_magazzino ADD COLUMN marca TEXT",
        "ALTER TABLE movimenti_magazzino ADD COLUMN modello TEXT"
    ]:
        try:
            c.execute(text(stmt))
        except Exception:
            pass

    def sql_insert_ignore(stmt, params=None):
        if DB_DRIVER.startswith("mysql"):
            stmt = stmt.replace("INSERT OR IGNORE", "INSERT IGNORE")
        c.execute(text(stmt), params or {})
        
    # seed ruoli
    sql_insert_ignore("INSERT OR IGNORE INTO ruoli(ruolo_id,nome,descrizione) VALUES (1,'admin','Amministratore (massima visibilità)'),(2,'responsabile','Responsabile del reparto (vede operatori, ticket, report)'),(3,'assistenza','Operatore di assistenza (gestisce ticket dei propri servizi)'),(4,'normale','Operatore normale (non vede/gestisce ticket)')")
    try:
        c.execute(text("UPDATE users SET ruolo = 'admin' WHERE ruolo = 'superuser'"))
        c.execute(text("UPDATE users SET ruolo = 'assistenza' WHERE ruolo = 'reparto'"))
    except:
        pass

    # Crea account amministratore base
    def h(p): return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    sql_insert_ignore("INSERT OR IGNORE INTO users(username,password_hash,nome,cognome,email,ruolo,attivo,is_test) VALUES (:u,:h,:n,:c,:e,:r,1,0)",
                     {"u":'admin',"h":h('admin'),"n":'Admin',"c":'Super',"e":'admin@example.com',"r":'admin'})

@asynccontextmanager
async def lifespan(app: FastAPI):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(BASE_DIR, "app_events.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{now}] Server AVVIATO - Troubletick v7.4 ({DB_TYPE})\n")
            
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                f.write(f"[{now}] DB: Connessione a {DB_TYPE} stabilita con successo.\n")
            except Exception as e:
                db_settings = {
                    "type": CFG.get("db_type", "sqlite"),
                    "host": CFG.get("db_host", ""),
                    "port": CFG.get("db_port", ""),
                    "name": CFG.get("db_name", ""),
                    "user": CFG.get("db_user", "")
                }
                f.write(f"[{now}] ERRORE DB: Impossibile connettersi al database!\n")
                f.write(f"[{now}] ERRORE DB - Impostazioni usate: {json.dumps(db_settings)}\n")
                f.write(f"[{now}] ERRORE DB - Dettaglio errore: {str(e)}\n")
    except Exception:
        pass
    yield
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{now}] Server FERMATO\n")
    except Exception:
        pass

app = FastAPI(title=f"{CFG.get('app_title','Troubletick')} v7.4 ({DB_TYPE})", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR,"static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def get_new_tickets_count(user):
    if not user or user.get("ruolo") == "normale":
        return 0
    try:
        with engine.connect() as c:
            uid = user.get("id")
            if user.get("ruolo") == "admin":
                return c.execute(text("SELECT COUNT(*) FROM tickets WHERE stato = 'nuova'")).scalar() or 0
            elif user.get("ruolo") == "responsabile":
                return c.execute(text("SELECT COUNT(*) FROM tickets WHERE stato = 'nuova' AND reparto_id = (SELECT reparto_id FROM users WHERE user_id = :uid)"), {"uid": uid}).scalar() or 0
            elif user.get("ruolo") == "assistenza":
                return c.execute(text("SELECT COUNT(*) FROM tickets WHERE stato = 'nuova' AND (reparto_id = (SELECT reparto_id FROM users WHERE user_id = :uid) OR servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid))"), {"uid": uid}).scalar() or 0
    except Exception:
        pass
    return 0

templates.env.globals["get_new_tickets_count"] = get_new_tickets_count

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(os.path.join(BASE_DIR, "app_events.log"), "a", encoding="utf-8") as f:
            f.write(f"\n[{now}] ERRORE 500 su {request.url.path}:\n")
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass
    return HTMLResponse("<h1>500 Internal Server Error</h1><p>Si è verificato un errore imprevisto sul server. Controlla il file <b>app_events.log</b> per visualizzare i dettagli tecnici.</p>", status_code=500)

app.include_router(auth.router)
app.include_router(magazzini.router)

@app.get("/", response_class=HTMLResponse)
def home(r: Request):
    user = r.session.get("user")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with engine.connect() as c:
        avvisi = c.execute(text("""
            SELECT a.*, s.descrizione as servizio_desc
            FROM avvisi a
            LEFT JOIN servizi s ON a.servizio_id = s.servizio_id
            WHERE (a.data_inizio IS NULL OR a.data_inizio <= :now)
              AND (a.data_fine IS NULL OR a.data_fine >= :now)
            ORDER BY 
              CASE a.gravita WHEN 'danger' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, 
              a.creato_il DESC
        """), {"now": now}).mappings().all()
    return templates.TemplateResponse(r, "home.html", {"request": r, "cfg": CFG, "avvisi": avvisi, "user": user})

@app.get("/new", response_class=HTMLResponse)
def new_form(r: Request):
    with engine.connect() as c:
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        reparti_dest = c.execute(text("SELECT reparto_id, nome FROM reparti WHERE accetta_ticket = 1 ORDER BY nome")).mappings().all()
        servizi = c.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi WHERE accetta_ticket = 1 ORDER BY descrizione")).mappings().all()
    return templates.TemplateResponse(r, "new_ticket.html", {"request": r, "cfg": CFG, "reparti": reparti, "reparti_dest": reparti_dest, "servizi": servizi})

@app.post("/new")
def create_ticket(r: Request,
                  background_tasks: BackgroundTasks,
                  nominativo: str=Form(...), email: str=Form(""), telefono: str=Form(""),
                  sede: str=Form(""),
                  reparto_id: int=Form(...), servizio_id: str = Form(None),
                  descrizione: str=Form(...),
                  allegato: UploadFile = File(None)):
    priorita = "media"
    ip = r.client.host if r.client else None
    servizio_id = int(servizio_id) if servizio_id else None
    
    allegato_filename = save_upload(allegato)

    parts = nominativo.strip().split(" ", 1)
    nome = parts[0]
    cognome = parts[1] if len(parts) > 1 else ""
    
    riferimento_parts = []
    if email: riferimento_parts.append(email)
    if telefono: riferimento_parts.append(telefono)
    riferimento = " / ".join(riferimento_parts)
    
    current_year = datetime.now().year
    with engine.begin() as c:
        max_code_str = c.execute(text("SELECT MAX(codice_ticket) FROM tickets WHERE creato_il LIKE :yp"), {"yp": f"{current_year}-%"}).scalar()
        if max_code_str and max_code_str.isdigit():
            next_code = int(max_code_str) + 1
        else:
            next_code = 1
        codice_ticket = f"{next_code:06d}"
        
        rep_nome = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": reparto_id}).scalar()
        serv_desc = "Nessun servizio specifico"
        if servizio_id:
            serv_desc = c.execute(text("SELECT descrizione FROM servizi WHERE servizio_id = :sid"), {"sid": servizio_id}).scalar()
            
        operatori_emails = []
        if servizio_id:
            operatori_emails = c.execute(text("SELECT u.email FROM users u JOIN operatori_servizi os ON u.user_id = os.user_id WHERE os.servizio_id = :sid AND u.email IS NOT NULL AND u.email != '' AND u.attivo = 1"), {"sid": servizio_id}).scalars().all()

        c.execute(text("""INSERT INTO tickets (codice_ticket, nome,cognome,email,telefono,riferimento,sede,reparto_id,servizio_id,descrizione,priorita,ip,allegato)
                          VALUES (:codice, :n,:c,:e,:tel,:r,:sede,:rid,:sid,:d,:p,:ip,:all)"""),
                 {"codice": codice_ticket, "n":nome,"c":cognome,"e":email,"tel":telefono,"r":riferimento,"sede":sede,"rid":reparto_id,"sid":servizio_id,
                  "d":descrizione,"p":priorita,"ip":ip,"all":allegato_filename})
                  
    if email:
        subject = f"[{CFG.get('company_name', 'Helpdesk')}] Conferma apertura Ticket #{codice_ticket}"
        body = templates.get_template("email_ticket_new.html").render({
            "cfg": CFG,
            "nome": nome,
            "codice_ticket": codice_ticket,
            "rep_nome": rep_nome,
            "serv_desc": serv_desc,
            "descrizione": descrizione
        })
        background_tasks.add_task(send_email_async, email, subject, body)
        
    if operatori_emails:
        subject_ops = f"[{CFG.get('company_name', 'Helpdesk')}] Nuovo Ticket #{codice_ticket} nel tuo servizio"
        body_ops = templates.get_template("email_ticket_operatore.html").render({
            "cfg": CFG,
            "titolo": "Nuovo ticket assegnato al tuo servizio",
            "codice_ticket": codice_ticket,
            "nome_richiedente": f"{nome} {cognome}".strip(),
            "serv_desc": serv_desc,
            "descrizione": descrizione
        })
        for op_email in set(operatori_emails):
            background_tasks.add_task(send_email_async, op_email, subject_ops, body_ops)
            
    url_redirect = f"/success?codice={codice_ticket}"
    if email:
        url_redirect += "&email=1"
        
    return RedirectResponse(url=url_redirect, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success(r: Request, codice: str = None, email: str = None):
    return templates.TemplateResponse(r, "success.html", {"request": r, "cfg": CFG, "codice": codice, "email_inviata": bool(email)})

@app.get("/status-ticket", response_class=HTMLResponse)
def status_ticket_form(r: Request):
    current_year = datetime.now().year
    return templates.TemplateResponse(r, "status_ticket.html", {"request": r, "cfg": CFG, "current_year": current_year})

@app.post("/status-ticket", response_class=HTMLResponse)
def status_ticket_action(r: Request, anno: str = Form(...), codice: str = Form(...)):
    codice_formattato = codice.strip().zfill(6) if codice.strip().isdigit() else codice.strip()
    with engine.connect() as c:
        ticket = c.execute(text("""
            SELECT t.ticket_id, t.codice_ticket, t.stato, t.creato_il, t.nome, t.cognome,
                   r.nome AS reparto_nome, s.descrizione AS servizio_desc
            FROM tickets t
            LEFT JOIN reparti r ON t.reparto_id = r.reparto_id
            LEFT JOIN servizi s ON t.servizio_id = s.servizio_id
            WHERE t.codice_ticket = :cod AND t.creato_il LIKE :anno
        """), {"cod": codice_formattato, "anno": f"{anno.strip()}-%"}).mappings().first()
        
        note = []
        if ticket:
            note = c.execute(text("""
                SELECT autore, testo, creato_il 
                FROM ticket_notes 
                WHERE ticket_id = :tid AND (is_internal = 0 OR is_internal IS NULL)
                ORDER BY creato_il DESC 
                LIMIT 3
            """), {"tid": ticket["ticket_id"]}).mappings().all()
        
    return templates.TemplateResponse(r, "status_ticket.html", {"request": r, "cfg": CFG, "ticket": ticket, "note": note, "cercato": True, "anno": anno, "codice": codice, "current_year": datetime.now().year})


@app.get("/tickets", response_class=HTMLResponse)
def tickets(r: Request, reparto_id: str = None, servizio_id: str = None, stato: str = None, priorita: str = None, q: str = None, con_materiale: str = None, my_tickets: str = None, assegnati_a_me: str = None):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        # Gestione primo accesso
        is_first_load = not any(k in r.query_params for k in ["reparto_id", "servizio_id", "stato", "priorita", "q", "con_materiale", "my_tickets", "assegnati_a_me"])
        if is_first_load:
            my_tickets = "1"

        reparto_id = int(reparto_id) if reparto_id and str(reparto_id).isdigit() else None
        servizio_id = int(servizio_id) if servizio_id and str(servizio_id).isdigit() else None
        
        if stato is None:
            stato = "aperti"
        elif stato == "":
            stato = None
            
        priorita = priorita if priorita else None

        # Costruisci la query con filtri dinamici
        where_clauses = []
        params = {}
        
        if user.get("ruolo") != "admin":
            if user.get("ruolo") == "normale":
                where_clauses.append("1 = 0")
            elif user.get("ruolo") == "responsabile":
                where_clauses.append("t.reparto_id = (SELECT reparto_id FROM users WHERE user_id = :user_id)")
                params["user_id"] = user.get("id")
            elif user.get("ruolo") == "assistenza":
                where_clauses.append("""
                    (t.reparto_id = (SELECT reparto_id FROM users WHERE user_id = :user_id) OR t.servizio_id IN (
                        SELECT servizio_id FROM operatori_servizi WHERE user_id = :user_id
                    ))
                """)
                params["user_id"] = user.get("id")

        if my_tickets == "1":
            where_clauses.append("""
                t.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid_my)
            """)
            params["uid_my"] = user.get("id")

        if assegnati_a_me == "1":
            autore_corrente = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
            where_clauses.append("""
                (SELECT autore FROM ticket_notes tn WHERE tn.ticket_id = t.ticket_id ORDER BY tn.creato_il DESC LIMIT 1) IN (:autore_normale, :autore_sistema)
            """)
            params["autore_normale"] = autore_corrente
            params["autore_sistema"] = f"Sistema ({autore_corrente})"

        if reparto_id:
            where_clauses.append("t.reparto_id = :reparto_id")
            params["reparto_id"] = reparto_id
        if servizio_id:
            where_clauses.append("t.servizio_id = :servizio_id")
            params["servizio_id"] = servizio_id
        if stato == "aperti":
            where_clauses.append("t.stato != 'chiusa'")
        elif stato:
            where_clauses.append("t.stato = :stato")
            params["stato"] = stato
        if priorita:
            where_clauses.append("t.priorita = :priorita")
            params["priorita"] = priorita
        if q:
            where_clauses.append("(t.nome LIKE :q OR t.cognome LIKE :q OR t.descrizione LIKE :q)")
            params["q"] = f"%{q}%"
        if con_materiale == "1":
            where_clauses.append("EXISTS(SELECT 1 FROM richieste_materiale rm WHERE rm.ticket_id = t.ticket_id AND rm.stato != 'annullata')")
        
        where_clause = " AND ".join(where_clauses)
        if where_clause:
            where_clause = " WHERE " + where_clause

        rows = c.execute(text(f"""
            SELECT t.ticket_id, t.codice_ticket, t.nome, t.cognome, t.riferimento, t.priorita, t.stato,
                   t.creato_il, t.ip, t.reparto_id, t.servizio_id, t.sede, t.is_test,
                   r.nome AS reparto_nome, s.descrizione AS servizio_desc,
                   t.descrizione,
                   (SELECT autore FROM ticket_notes tn WHERE tn.ticket_id = t.ticket_id ORDER BY tn.creato_il DESC LIMIT 1) AS ultimo_operatore,
                   (SELECT COUNT(*) FROM richieste_materiale rm WHERE rm.ticket_id = t.ticket_id AND rm.stato != 'annullata') AS req_totali,
                   (SELECT COUNT(*) FROM richieste_materiale rm WHERE rm.ticket_id = t.ticket_id AND rm.stato = 'evasa') AS req_evase
              FROM tickets t
              LEFT JOIN reparti r ON t.reparto_id = r.reparto_id
              LEFT JOIN servizi s ON t.servizio_id = s.servizio_id
              {where_clause}
             ORDER BY t.creato_il DESC
        """), params).mappings().all()
        
        # Recupera i dati per i filtri
        reparti = c.execute(text("SELECT DISTINCT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        servizi = c.execute(text("SELECT DISTINCT servizio_id, descrizione FROM servizi ORDER BY descrizione")).mappings().all()
        stati = c.execute(text("SELECT DISTINCT stato FROM tickets WHERE stato IS NOT NULL ORDER BY stato")).scalars().all()
        prioritas = c.execute(text("SELECT DISTINCT priorita FROM tickets WHERE priorita IS NOT NULL ORDER BY priorita")).scalars().all()
        
        # Recupera l'elenco degli operatori assenti nella giornata odierna
        from datetime import date
        oggi = date.today().isoformat()
        assenze_oggi = c.execute(text("""
            SELECT u.nome, u.cognome, u.username
              FROM assenze a
              JOIN users u ON a.user_id = u.user_id
             WHERE :oggi BETWEEN a.data_inizio AND a.data_fine
        """), {"oggi": oggi}).mappings().all()
        absent_names = [f"{au['nome']} {au['cognome']}".strip() or au['username'] for au in assenze_oggi]
        
        # Calcolo dei contatori per il cruscotto
        uid = user.get("id")
        base_where = ""
        base_params = {}
        if user.get("ruolo") == "normale":
            base_where = " WHERE 1 = 0"
        elif user.get("ruolo") == "responsabile":
            base_where = " WHERE t.reparto_id = (SELECT reparto_id FROM users WHERE user_id = :uid)"
            base_params["uid"] = uid
        elif user.get("ruolo") == "assistenza":
            base_where = " WHERE (t.reparto_id = (SELECT reparto_id FROM users WHERE user_id = :uid) OR t.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid))"
            base_params["uid"] = uid

        cnt_nuovi = c.execute(text(f"SELECT COUNT(*) FROM tickets t {base_where} {'AND' if base_where else 'WHERE'} t.stato = 'nuova'"), base_params).scalar() or 0
        cnt_presi = c.execute(text(f"SELECT COUNT(*) FROM tickets t {base_where} {'AND' if base_where else 'WHERE'} t.stato = 'presa_in_carico'"), base_params).scalar() or 0
        
        autore_corrente = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
        p_miei = dict(base_params); p_miei["a1"] = autore_corrente; p_miei["a2"] = f"Sistema ({autore_corrente})"
        cnt_miei = c.execute(text(f"SELECT COUNT(*) FROM tickets t {base_where} {'AND' if base_where else 'WHERE'} t.stato != 'chiusa' AND (SELECT autore FROM ticket_notes tn WHERE tn.ticket_id = t.ticket_id ORDER BY tn.creato_il DESC LIMIT 1) IN (:a1, :a2)"), p_miei).scalar() or 0
        
        p_servizi = dict(base_params); p_servizi["uid2"] = uid
        cnt_servizi = c.execute(text(f"SELECT COUNT(*) FROM tickets t {base_where} {'AND' if base_where else 'WHERE'} t.stato != 'chiusa' AND t.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid2)"), p_servizi).scalar() or 0
        
        counters = {"nuovi": cnt_nuovi, "presi": cnt_presi, "miei": cnt_miei, "servizi": cnt_servizi}
    
    return templates.TemplateResponse(r, "tickets.html", {
        "request": r, "cfg": CFG, "tickets": rows, "user": user,
        "reparti": reparti, "servizi": servizi, "stati": stati, "prioritas": prioritas,
        "filtri": {"reparto_id": reparto_id, "servizio_id": servizio_id, "stato": stato, "priorita": priorita, "q": q, "con_materiale": con_materiale, "my_tickets": my_tickets, "assegnati_a_me": assegnati_a_me},
        "absent_names": absent_names, "counters": counters
    })

@app.get("/ticket/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(r: Request, ticket_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.connect() as c:
        ticket = c.execute(text("""
            SELECT t.*, r.nome AS reparto_nome, s.descrizione AS servizio_desc,
                   COALESCE(t.reparto_appartenenza, ra.nome) AS reparto_appartenenza_nome
              FROM tickets t
              LEFT JOIN reparti r ON t.reparto_id = r.reparto_id
              LEFT JOIN reparti ra ON t.reparto_appartenenza_id = ra.reparto_id
              LEFT JOIN servizi s ON t.servizio_id = s.servizio_id
             WHERE t.ticket_id = :id
        """), {"id": ticket_id}).mappings().first()
        if not ticket:
            return RedirectResponse(url="/tickets")
            
        if user.get("ruolo") != "admin":
            if user.get("ruolo") == "normale":
                return RedirectResponse(url="/tickets")
                
            op_servizi = c.execute(text("SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid"), {"uid": user.get("id")}).scalars().all()
            user_reparto = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            
            can_view = False
            if user_reparto and ticket["reparto_id"] == user_reparto:
                can_view = True
            if user.get("ruolo") == "assistenza" and ticket["servizio_id"] in op_servizi:
                can_view = True
            if not can_view:
                return RedirectResponse(url="/tickets")

        notes = c.execute(text("""
            SELECT note_id, autore, testo, creato_il, allegato, is_internal
              FROM ticket_notes
             WHERE ticket_id = :id
             ORDER BY creato_il DESC
        """), {"id": ticket_id}).mappings().all()
        
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti WHERE accetta_ticket = 1 ORDER BY nome")).mappings().all()
        servizi = c.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi WHERE accetta_ticket = 1 ORDER BY descrizione")).mappings().all()
        
        richieste_mat = c.execute(text("""
            SELECT rm.*, m.nome as materiale_nome, c.nome as categoria_nome, s.nome as sede_nome, mag.nome as magazzino_nome
            FROM richieste_materiale rm
            JOIN materiali m ON rm.materiale_id = m.materiale_id
            JOIN categorie c ON rm.categoria_id = c.categoria_id
            JOIN sedi s ON rm.sede_dest_id = s.sede_id
            LEFT JOIN magazzini mag ON rm.magazzino_id = mag.magazzino_id
            WHERE rm.ticket_id = :id
            ORDER BY rm.creato_il DESC
        """), {"id": ticket_id}).mappings().all()
        
    return templates.TemplateResponse(r, "ticket_detail.html", {"request": r, "cfg": CFG, "ticket": ticket, "notes": notes, "user": user, "reparti": reparti, "servizi": servizi, "richieste_mat": richieste_mat})

@app.post("/ticket/{ticket_id}/note")
def add_ticket_note(r: Request, ticket_id: int, testo: str = Form(...), allegato: UploadFile = File(None), is_internal: int = Form(0)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    autore = f"{r.session['user'].get('nome','')} {r.session['user'].get('cognome','')}".strip() or r.session['user'].get('username')
    
    allegato_filename = save_upload(allegato)
    with engine.begin() as c:
        c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo, allegato, is_internal) VALUES (:tid, :a, :t, :all, :is_int)"""),
                 {"tid": ticket_id, "a": autore, "t": testo, "all": allegato_filename, "is_int": is_internal})
    return RedirectResponse(url=f"/ticket/{ticket_id}", status_code=303)

@app.post("/ticket/{ticket_id}/stato")
def update_ticket_status(r: Request, ticket_id: int, background_tasks: BackgroundTasks, stato: str = Form(...)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.begin() as c:
        c.execute(text("UPDATE tickets SET stato = :stato WHERE ticket_id = :id"), {"stato": stato, "id": ticket_id})
        
        autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
        stato_formatted = stato.replace("_", " ").title()
        testo = f"Stato modificato in: **{stato_formatted}**."
        c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo) VALUES (:tid, :a, :t)"""),
                 {"tid": ticket_id, "a": f"Sistema ({autore})", "t": testo})
                 
        if stato == "chiusa":
            ticket = c.execute(text("SELECT codice_ticket, nome, email FROM tickets WHERE ticket_id = :id"), {"id": ticket_id}).mappings().first()
            if ticket and ticket["email"]:
                subject = f"[{CFG.get('company_name', 'Helpdesk')}] Ticket #{ticket['codice_ticket']} Chiuso"
                body = templates.get_template("email_ticket_chiuso.html").render({
                    "cfg": CFG,
                    "nome": ticket["nome"],
                    "codice_ticket": ticket["codice_ticket"],
                    "autore": autore
                })
                background_tasks.add_task(send_email_async, ticket["email"], subject, body)
    return RedirectResponse(url=f"/ticket/{ticket_id}", status_code=303)

@app.post("/ticket/{ticket_id}/riassegna")
def reassign_ticket(r: Request, ticket_id: int, background_tasks: BackgroundTasks, reparto_id: int = Form(...), servizio_id: str = Form(None)):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    servizio_id_val = int(servizio_id) if servizio_id else None
    
    with engine.begin() as c:
        vecchio = c.execute(text("""
            SELECT r.nome as rep_nome, s.descrizione as serv_desc, t.codice_ticket, t.nome, t.cognome, t.descrizione
              FROM tickets t
              LEFT JOIN reparti r ON t.reparto_id = r.reparto_id
              LEFT JOIN servizi s ON t.servizio_id = s.servizio_id
             WHERE t.ticket_id = :id
        """), {"id": ticket_id}).mappings().first()
        
        c.execute(text("UPDATE tickets SET reparto_id = :rid, servizio_id = :sid WHERE ticket_id = :id"), 
                  {"rid": reparto_id, "sid": servizio_id_val, "id": ticket_id})
        
        nuovo_rep = c.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": reparto_id}).scalar()
        nuovo_serv = c.execute(text("SELECT descrizione FROM servizi WHERE servizio_id = :sid"), {"sid": servizio_id_val}).scalar() if servizio_id_val else "Nessuno"
        
        autore = f"{user.get('nome','')} {user.get('cognome','')}".strip() or user.get('username')
        testo = f"Ticket trasferito da **{vecchio['rep_nome'] or 'Nessuno'} ({vecchio['serv_desc'] or 'Nessuno'})** a **{nuovo_rep or 'Nessuno'} ({nuovo_serv})**."
        c.execute(text("""INSERT INTO ticket_notes (ticket_id, autore, testo) VALUES (:tid, :a, :t)"""),
                 {"tid": ticket_id, "a": f"Sistema ({autore})", "t": testo})
                 
        operatori_emails = []
        if servizio_id_val:
            operatori_emails = c.execute(text("SELECT u.email FROM users u JOIN operatori_servizi os ON u.user_id = os.user_id WHERE os.servizio_id = :sid AND u.email IS NOT NULL AND u.email != '' AND u.attivo = 1"), {"sid": servizio_id_val}).scalars().all()
            
    if operatori_emails:
        subject_ops = f"[{CFG.get('company_name', 'Helpdesk')}] Ticket #{vecchio['codice_ticket']} riassegnato al tuo servizio"
        body_ops = templates.get_template("email_ticket_operatore.html").render({
            "cfg": CFG,
            "titolo": "Ticket riassegnato al tuo servizio",
            "codice_ticket": vecchio['codice_ticket'],
            "nome_richiedente": f"{vecchio['nome']} {vecchio['cognome']}".strip(),
            "serv_desc": nuovo_serv,
            "descrizione": vecchio['descrizione']
        })
        for op_email in set(operatori_emails):
            background_tasks.add_task(send_email_async, op_email, subject_ops, body_ops)
                 
    return RedirectResponse(url=f"/ticket/{ticket_id}", status_code=303)

@app.post("/ticket/{ticket_id}/delete")
def delete_ticket(r: Request, ticket_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
        
    # Cancellazione file allegati dal disco
    with engine.connect() as c:
        ticket = c.execute(text("SELECT allegato FROM tickets WHERE ticket_id = :id"), {"id": ticket_id}).mappings().first()
        notes = c.execute(text("SELECT allegato FROM ticket_notes WHERE ticket_id = :id"), {"id": ticket_id}).mappings().all()
        
        files_to_delete = [n["allegato"] for n in notes if n["allegato"]]
        if ticket and ticket["allegato"]: files_to_delete.append(ticket["allegato"])
        
        for f in files_to_delete:
            try: os.remove(os.path.join(UPLOAD_DIR, f))
            except: pass
            
    with engine.begin() as c:
        c.execute(text("DELETE FROM ticket_materiali WHERE ticket_id = :id"), {"id": ticket_id})
        c.execute(text("DELETE FROM ticket_notes WHERE ticket_id = :id"), {"id": ticket_id})
        c.execute(text("DELETE FROM tickets WHERE ticket_id = :id"), {"id": ticket_id})
    return RedirectResponse(url="/tickets", status_code=303)

@app.post("/admin/tickets/delete_massivo")
def delete_tickets_massivo(r: Request, data_inizio: str = Form(...), data_fine: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
        
    with engine.begin() as c:
        files_to_delete = []
        tickets = c.execute(text("""
            SELECT ticket_id, allegato FROM tickets 
            WHERE date(creato_il) >= date(:start) AND date(creato_il) <= date(:end)
        """), {"start": data_inizio, "end": data_fine}).mappings().all()
        
        if not tickets:
            return RedirectResponse(url="/admin/impostazioni?msg=nessun_ticket", status_code=303)
            
        for t in tickets:
            if t["allegato"]: files_to_delete.append(t["allegato"])
            notes = c.execute(text("SELECT allegato FROM ticket_notes WHERE ticket_id = :id AND allegato IS NOT NULL"), {"id": t["ticket_id"]}).mappings().all()
            for n in notes:
                if n["allegato"]: files_to_delete.append(n["allegato"])
                
        c.execute(text("""
            DELETE FROM ticket_materiali 
            WHERE ticket_id IN (SELECT ticket_id FROM tickets WHERE date(creato_il) >= date(:start) AND date(creato_il) <= date(:end))
        """), {"start": data_inizio, "end": data_fine})
        
        c.execute(text("""
            DELETE FROM ticket_notes 
            WHERE ticket_id IN (SELECT ticket_id FROM tickets WHERE date(creato_il) >= date(:start) AND date(creato_il) <= date(:end))
        """), {"start": data_inizio, "end": data_fine})
        
        c.execute(text("""
            DELETE FROM tickets 
            WHERE date(creato_il) >= date(:start) AND date(creato_il) <= date(:end)
        """), {"start": data_inizio, "end": data_fine})
        
    for f in files_to_delete:
        try: os.remove(os.path.join(UPLOAD_DIR, f))
        except: pass
        
    return RedirectResponse(url="/admin/impostazioni?msg=delete_ok", status_code=303)

@app.get("/calendario", response_class=HTMLResponse)
def calendario(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        assenze = c.execute(text("""
            SELECT a.*, u.nome, u.cognome, u.username, r.nome as reparto_nome
            FROM assenze a
            JOIN users u ON a.user_id = u.user_id
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            ORDER BY a.data_inizio DESC
        """)).mappings().all()
            
        festivita = c.execute(text("""
            SELECT * FROM festivita ORDER BY data DESC
        """)).mappings().all()
            
    return templates.TemplateResponse(r, "calendario.html", {"request": r, "cfg": CFG, "user": user, "assenze": assenze, "festivita": festivita})

@app.post("/calendario/nuova")
def nuova_assenza(r: Request, data_inizio: str = Form(...), data_fine: str = Form(...), motivo: str = Form("")):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.begin() as c:
        c.execute(text("""INSERT INTO assenze (user_id, data_inizio, data_fine, motivo)
                          VALUES (:uid, :di, :df, :m)"""), 
                  {"uid": user.get("id"), "di": data_inizio, "df": data_fine, "m": motivo})
    return RedirectResponse(url="/calendario", status_code=303)

@app.post("/calendario/{assenza_id}/elimina")
def elimina_assenza(r: Request, assenza_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    with engine.begin() as c:
        if user.get("ruolo") == "admin":
            c.execute(text("DELETE FROM assenze WHERE assenza_id = :id"), {"id": assenza_id})
        else:
            c.execute(text("DELETE FROM assenze WHERE assenza_id = :id AND user_id = :uid"), {"id": assenza_id, "uid": user.get("id")})
    return RedirectResponse(url="/calendario", status_code=303)

@app.post("/calendario/festivita/nuova")
def nuova_festivita(r: Request, data: str = Form(...), descrizione: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("""INSERT INTO festivita (data, descrizione) VALUES (:d, :desc)"""), 
                  {"d": data, "desc": descrizione})
    return RedirectResponse(url="/calendario", status_code=303)

@app.post("/calendario/festivita/{festivita_id}/elimina")
def elimina_festivita(r: Request, festivita_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("DELETE FROM festivita WHERE festivita_id = :id"), {"id": festivita_id})
    return RedirectResponse(url="/calendario", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin(r: Request):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    with engine.connect() as c:
        stats = c.execute(text("SELECT stato, COUNT(*) as count FROM tickets GROUP BY stato")).mappings().all()
        labels = [s["stato"].replace("_", " ").title() if s["stato"] else "Altro" for s in stats]
        data = [s["count"] for s in stats]
        
    return templates.TemplateResponse(r, "admin.html", {"request": r, "cfg": CFG, "user": user, 
                                                     "chart_labels": json.dumps(labels), "chart_data": json.dumps(data)})

@app.get("/admin/impostazioni", response_class=HTMLResponse)
def admin_impostazioni(r: Request):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(r, "admin_impostazioni.html", {"request": r, "cfg": CFG, "user": user})

@app.post("/admin/impostazioni")
def save_impostazioni(r: Request, 
                      company_name: str = Form(...), 
                      helpdesk_email: str = Form(...),
                      smtp_server: str = Form(""),
                      smtp_port: str = Form(""),
                      smtp_user: str = Form(""),
                      smtp_password: str = Form(""),
                      smtp_tls: int = Form(0),
                      db_type: str = Form("sqlite"),
                      db_host: str = Form(""),
                      db_port: str = Form(""),
                      db_name: str = Form(""),
                      db_user: str = Form(""),
                      db_password: str = Form("")):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    CFG["company_name"] = company_name
    CFG["helpdesk_email"] = helpdesk_email
    
    CFG["smtp_server"] = smtp_server
    CFG["smtp_port"] = int(smtp_port) if smtp_port.isdigit() else (587 if smtp_server else "")
    CFG["smtp_user"] = smtp_user
    CFG["smtp_password"] = smtp_password
    CFG["smtp_tls"] = bool(smtp_tls)
    
    CFG["db_type"] = db_type
    CFG["db_host"] = db_host
    CFG["db_port"] = int(db_port) if db_port.isdigit() else ""
    CFG["db_name"] = db_name
    CFG["db_user"] = db_user
    CFG["db_password"] = db_password
    
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(CFG, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
        
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/report-copertura", response_class=HTMLResponse)
def report_copertura(r: Request, mese: int = None, anno: int = None):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login")
    if user.get("ruolo") not in ("admin", "responsabile"):
        return RedirectResponse(url="/tickets")
        
    import calendar
    from datetime import date
    oggi = date.today()
    
    anno = int(anno) if anno else oggi.year
    mese = int(mese) if mese else oggi.month
    num_days = calendar.monthrange(anno, mese)[1]
    
    with engine.connect() as c:
        where_rep = ""
        params = {}
        if user.get("ruolo") == "responsabile":
            rep_id = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if rep_id:
                where_rep = "WHERE r.reparto_id = :rep_id"
                params["rep_id"] = rep_id
                
        rows = c.execute(text("""
            SELECT s.servizio_id, s.descrizione as servizio_desc, 
                   r.reparto_id, r.nome as reparto_nome,
                   u.user_id, u.nome, u.cognome
            FROM servizi s
            JOIN reparti r ON s.reparto_id = r.reparto_id
            LEFT JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
            LEFT JOIN users u ON os.user_id = u.user_id AND u.attivo = 1 AND u.ruolo != 'admin'
            """ + where_rep + """
            ORDER BY r.nome, s.descrizione
        """), params).mappings().all()
        
        reparti_dict = {}
        user_names = {}
        for row in rows:
            r_nome = row["reparto_nome"]
            s_desc = row["servizio_desc"]
            uid = row["user_id"]
            
            if r_nome not in reparti_dict: reparti_dict[r_nome] = {}
            if s_desc not in reparti_dict[r_nome]: reparti_dict[r_nome][s_desc] = set()
            if uid: 
                reparti_dict[r_nome][s_desc].add(uid)
                user_names[uid] = f"{row['nome']} {row['cognome']}".strip()
                
        start_date = f"{anno}-{mese:02d}-01"
        end_date = f"{anno}-{mese:02d}-{num_days:02d}"
        assenze_rows = c.execute(text("""
            SELECT user_id, data_inizio, data_fine FROM assenze
            WHERE data_inizio <= :end AND data_fine >= :start
        """), {"start": start_date, "end": end_date}).mappings().all()
        
        absent_on_day = {d: set() for d in range(1, num_days + 1)}
        for a in assenze_rows:
            for d in range(1, num_days + 1):
                if a["data_inizio"] <= f"{anno}-{mese:02d}-{d:02d}" <= a["data_fine"]:
                    absent_on_day[d].add(a["user_id"])
        
        report_data = []
        for r_nome, servizi in reparti_dict.items():
            rep_data = {"reparto": r_nome, "servizi": []}
            for s_desc, users in servizi.items():
                copertura = []
                for d in range(1, num_days + 1):
                    present_users_ids = users - absent_on_day[d]
                    present_names = sorted([user_names[uid] for uid in present_users_ids])
                    tooltip = ", ".join(present_names) if present_names else "Nessuno"
                    copertura.append({"giorno": d, "presenti": len(present_users_ids), "totale": len(users), "tooltip": tooltip})
                rep_data["servizi"].append({"descrizione": s_desc, "copertura": copertura})
            report_data.append(rep_data)
            
    mesi_nomi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    return templates.TemplateResponse(r, "report_copertura.html", {"request": r, "cfg": CFG, "user": user, "report_data": report_data, "anno": anno, "mese": mese, "nome_mese": mesi_nomi[mese-1], "num_days": num_days, "days_range": list(range(1, num_days + 1))})

@app.get("/admin/reparti", response_class=HTMLResponse)
def admin_reparti(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        reparti = c.execute(text("SELECT reparto_id, nome, descrizione, accetta_ticket FROM reparti ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_reparti.html", {"request": r, "cfg": CFG, "user": user, "reparti": reparti, "error": error})

@app.get("/admin/servizi", response_class=HTMLResponse)
def admin_servizi(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        servizi = c.execute(text("SELECT s.servizio_id, s.descrizione, s.reparto_id, s.accetta_ticket, r.nome AS reparto_nome FROM servizi s LEFT JOIN reparti r ON s.reparto_id = r.reparto_id ORDER BY r.nome, s.descrizione")).mappings().all()
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_servizi.html", {"request": r, "cfg": CFG, "user": user, "servizi": servizi, "reparti": reparti, "error": error})

@app.post("/admin/reparto")
def add_reparto(r: Request, nome: str = Form(...), descrizione: str = Form(""), accetta_ticket: int = Form(0)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        c.execute(text("INSERT INTO reparti (nome, descrizione, accetta_ticket) VALUES (:nome, :descrizione, :at)"), {"nome": nome, "descrizione": descrizione, "at": accetta_ticket})
    return RedirectResponse(url="/admin/reparti", status_code=303)

@app.get("/admin/reparto/{reparto_id}/modifica", response_class=HTMLResponse)
def edit_reparto_form(r: Request, reparto_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        reparto = c.execute(text("SELECT * FROM reparti WHERE reparto_id = :id"), {"id": reparto_id}).mappings().first()
        if not reparto: return RedirectResponse(url="/admin/reparti")
    return templates.TemplateResponse(r, "edit_reparto.html", {"request": r, "cfg": CFG, "user": user, "reparto": reparto})

@app.post("/admin/reparto/{reparto_id}/modifica")
def edit_reparto_action(r: Request, reparto_id: int, nome: str = Form(...), descrizione: str = Form(""), accetta_ticket: int = Form(0)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("UPDATE reparti SET nome = :nome, descrizione = :desc, accetta_ticket = :at WHERE reparto_id = :id"),
                  {"nome": nome, "desc": descrizione, "at": accetta_ticket, "id": reparto_id})
    return RedirectResponse(url="/admin/reparti", status_code=303)

@app.post("/admin/reparto/delete")
def delete_reparto(r: Request, reparto_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        # Prevenzione eliminazione se in uso
        t_count = c.execute(text("SELECT COUNT(*) FROM tickets WHERE reparto_id = :id"), {"id": reparto_id}).scalar()
        s_count = c.execute(text("SELECT COUNT(*) FROM servizi WHERE reparto_id = :id"), {"id": reparto_id}).scalar()
        u_count = c.execute(text("SELECT COUNT(*) FROM users WHERE reparto_id = :id"), {"id": reparto_id}).scalar()
        if t_count > 0 or s_count > 0 or u_count > 0:
            return RedirectResponse(url="/admin/reparti?error=in_uso", status_code=303)
            
        c.execute(text("DELETE FROM reparti WHERE reparto_id = :id"), {"id": reparto_id})
    return RedirectResponse(url="/admin/reparti", status_code=303)

@app.post("/admin/servizio")
def add_servizio(r: Request, descrizione: str = Form(...), reparto_id: int = Form(...), accetta_ticket: int = Form(0)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        c.execute(text("INSERT INTO servizi (descrizione, reparto_id, accetta_ticket) VALUES (:descrizione, :reparto_id, :at)"), {"descrizione": descrizione, "reparto_id": reparto_id, "at": accetta_ticket})
    return RedirectResponse(url="/admin/servizi", status_code=303)

@app.get("/admin/servizio/{servizio_id}/modifica", response_class=HTMLResponse)
def edit_servizio_form(r: Request, servizio_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        servizio = c.execute(text("SELECT * FROM servizi WHERE servizio_id = :id"), {"id": servizio_id}).mappings().first()
        if not servizio: return RedirectResponse(url="/admin/servizi")
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "edit_servizio.html", {"request": r, "cfg": CFG, "user": user, "servizio": servizio, "reparti": reparti})

@app.post("/admin/servizio/{servizio_id}/modifica")
def edit_servizio_action(r: Request, servizio_id: int, descrizione: str = Form(...), reparto_id: int = Form(...), accetta_ticket: int = Form(0)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("UPDATE servizi SET descrizione = :desc, reparto_id = :rid, accetta_ticket = :at WHERE servizio_id = :id"),
                  {"desc": descrizione, "rid": reparto_id, "at": accetta_ticket, "id": servizio_id})
    return RedirectResponse(url="/admin/servizi", status_code=303)

@app.post("/admin/servizio/delete")
def delete_servizio(r: Request, servizio_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        # Prevenzione eliminazione se in uso
        t_count = c.execute(text("SELECT COUNT(*) FROM tickets WHERE servizio_id = :id"), {"id": servizio_id}).scalar()
        os_count = c.execute(text("SELECT COUNT(*) FROM operatori_servizi WHERE servizio_id = :id"), {"id": servizio_id}).scalar()
        if t_count > 0 or os_count > 0:
            return RedirectResponse(url="/admin/servizi?error=in_uso", status_code=303)
            
        c.execute(text("DELETE FROM servizi WHERE servizio_id = :id"), {"id": servizio_id})
    return RedirectResponse(url="/admin/servizi", status_code=303)

@app.get("/admin/sedi", response_class=HTMLResponse)
def admin_sedi(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        sedi = c.execute(text("""
            SELECT s.sede_id, s.nome, c.nome as comune_nome 
            FROM sedi s 
            LEFT JOIN comuni c ON s.comune_id = c.comune_id 
            ORDER BY s.nome
        """)).mappings().all()
        comuni = c.execute(text("SELECT comune_id, nome FROM comuni ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_sedi.html", {"request": r, "cfg": CFG, "user": user, "sedi": sedi, "comuni": comuni, "error": error})

@app.post("/admin/sede")
def add_sede(r: Request, nome: str = Form(...), comune_id: str = Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    comune_id_val = int(comune_id) if comune_id and str(comune_id).isdigit() else None
    with engine.begin() as c:
        c.execute(text("INSERT INTO sedi (nome, comune_id) VALUES (:nome, :cid)"), {"nome": nome, "cid": comune_id_val})
    return RedirectResponse(url="/admin/sedi", status_code=303)

@app.get("/admin/sede/{sede_id}/modifica", response_class=HTMLResponse)
def edit_sede_form(r: Request, sede_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        sede = c.execute(text("SELECT * FROM sedi WHERE sede_id = :id"), {"id": sede_id}).mappings().first()
        if not sede: return RedirectResponse(url="/admin/sedi")
        comuni = c.execute(text("SELECT comune_id, nome FROM comuni ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "edit_sede.html", {"request": r, "cfg": CFG, "user": user, "sede": sede, "comuni": comuni})

@app.post("/admin/sede/{sede_id}/modifica")
def edit_sede_action(r: Request, sede_id: int, nome: str = Form(...), comune_id: str = Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    comune_id_val = int(comune_id) if comune_id and str(comune_id).isdigit() else None
    with engine.begin() as c:
        c.execute(text("UPDATE sedi SET nome = :nome, comune_id = :cid WHERE sede_id = :id"),
                  {"nome": nome, "cid": comune_id_val, "id": sede_id})
    return RedirectResponse(url="/admin/sedi", status_code=303)

@app.post("/admin/sede/delete")
def delete_sede(r: Request, sede_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        # Prevenzione eliminazione se in uso
        u_count = c.execute(text("SELECT COUNT(*) FROM users WHERE sede_id = :id"), {"id": sede_id}).scalar()
        if u_count > 0:
            return RedirectResponse(url="/admin/sedi?error=in_uso", status_code=303)
            
        c.execute(text("DELETE FROM sedi WHERE sede_id = :id"), {"id": sede_id})
    return RedirectResponse(url="/admin/sedi", status_code=303)

# ===== IMPORTAZIONE CSV =====

@app.post("/admin/import/full")
async def import_full(r: Request, file: UploadFile = File(...), svuota_db: str = Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    try:
        contents = await file.read()
        data = json.loads(contents.decode("utf-8"))
        
        with engine.begin() as c:
            if svuota_db == "1":
                c.execute(text("DELETE FROM operatori_servizi"))
                c.execute(text("DELETE FROM users WHERE ruolo != 'admin'"))
                c.execute(text("DELETE FROM giacenze"))
                c.execute(text("DELETE FROM magazzini"))
                c.execute(text("DELETE FROM materiali"))
                c.execute(text("DELETE FROM servizi"))
                c.execute(text("DELETE FROM reparti"))
                c.execute(text("DELETE FROM categorie"))
                c.execute(text("DELETE FROM sedi"))
                c.execute(text("DELETE FROM comuni"))
                
            # Comuni
            for com in data.get("comuni", []):
                if not c.execute(text("SELECT comune_id FROM comuni WHERE nome = :n"), {"n": com["nome"]}).scalar():
                    c.execute(text("INSERT INTO comuni (nome) VALUES (:n)"), {"n": com["nome"]})
            # Sedi
            for s in data.get("sedi", []):
                com_id = c.execute(text("SELECT comune_id FROM comuni WHERE nome = :n"), {"n": s.get("comune")}).scalar()
                if not c.execute(text("SELECT sede_id FROM sedi WHERE nome = :n"), {"n": s["nome"]}).scalar():
                    c.execute(text("INSERT INTO sedi (nome, comune_id) VALUES (:n, :cid)"), {"n": s["nome"], "cid": com_id})
            # Categorie
            for cat in data.get("categorie", []):
                if not c.execute(text("SELECT categoria_id FROM categorie WHERE nome = :n"), {"n": cat["nome"]}).scalar():
                    c.execute(text("INSERT INTO categorie (nome) VALUES (:n)"), {"n": cat["nome"]})
            # Reparti
            for rep in data.get("reparti", []):
                if not c.execute(text("SELECT reparto_id FROM reparti WHERE nome = :n"), {"n": rep["nome"]}).scalar():
                    c.execute(text("INSERT INTO reparti (nome, descrizione, accetta_ticket) VALUES (:n, :d, :a)"),
                              {"n": rep["nome"], "d": rep.get("descrizione", ""), "a": rep.get("accetta_ticket", 1)})
            # Servizi
            for serv in data.get("servizi", []):
                rep_id = c.execute(text("SELECT reparto_id FROM reparti WHERE nome = :n"), {"n": serv.get("reparto")}).scalar()
                if rep_id and not c.execute(text("SELECT servizio_id FROM servizi WHERE descrizione = :d AND reparto_id = :rid"), {"d": serv["descrizione"], "rid": rep_id}).scalar():
                    c.execute(text("INSERT INTO servizi (descrizione, reparto_id, accetta_ticket) VALUES (:d, :rid, :at)"), {"d": serv["descrizione"], "rid": rep_id, "at": serv.get("accetta_ticket", 1)})
            # Materiali
            for mat in data.get("materiali", []):
                cat_id = c.execute(text("SELECT categoria_id FROM categorie WHERE nome = :n"), {"n": mat.get("categoria")}).scalar()
                if not c.execute(text("SELECT materiale_id FROM materiali WHERE nome = :n"), {"n": mat["nome"]}).scalar():
                    c.execute(text("INSERT INTO materiali (nome, categoria_id) VALUES (:n, :cid)"), 
                              {"n": mat["nome"], "cid": cat_id})
            # Magazzini
            for mag in data.get("magazzini", []):
                sede_id = c.execute(text("SELECT sede_id FROM sedi WHERE nome = :n"), {"n": mag.get("sede")}).scalar()
                cat_id = c.execute(text("SELECT categoria_id FROM categorie WHERE nome = :n"), {"n": mag.get("categoria")}).scalar()
                rep_id = c.execute(text("SELECT reparto_id FROM reparti WHERE nome = :n"), {"n": mag.get("reparto")}).scalar()
                if not c.execute(text("SELECT magazzino_id FROM magazzini WHERE nome = :n"), {"n": mag["nome"]}).scalar():
                    c.execute(text("INSERT INTO magazzini (nome, sede_id, categoria_id, reparto_id) VALUES (:n, :sid, :cid, :rid)"),
                              {"n": mag["nome"], "sid": sede_id, "cid": cat_id, "rid": rep_id})
            # Operatori
            def h(p): return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            for op in data.get("operatori", []):
                rep_id = c.execute(text("SELECT reparto_id FROM reparti WHERE nome = :n"), {"n": op.get("reparto")}).scalar()
                sede_id = c.execute(text("SELECT sede_id FROM sedi WHERE nome = :n"), {"n": op.get("sede")}).scalar()
                mag_id = c.execute(text("SELECT magazzino_id FROM magazzini WHERE nome = :n"), {"n": op.get("magazzino")}).scalar()
                if not c.execute(text("SELECT user_id FROM users WHERE username = :u OR email = :e"), {"u": op["username"], "e": op.get("email")}).scalar():
                    c.execute(text("""INSERT INTO users (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, sede_id, magazzino_id, attivo) 
                                      VALUES (:u, :h, :n, :c, :e, :tel, :ruolo, :rid, :sid, :mid, 1)"""),
                              {"u": op["username"], "h": h(op["password"]), "n": op.get("nome", ""), "c": op.get("cognome", ""), 
                               "e": op.get("email", ""), "tel": op.get("telefono", ""), "ruolo": op.get("ruolo", "assistenza"), "rid": rep_id, "sid": sede_id, "mid": mag_id})
    
    except Exception as e:
        return RedirectResponse(url="/admin/impostazioni?msg=import_err", status_code=303)
        
    return RedirectResponse(url="/admin/impostazioni?msg=import_ok", status_code=303)

@app.get("/admin/export/full.json")
def export_full(r: Request):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
        
    with engine.connect() as c:
        comuni = c.execute(text("SELECT nome FROM comuni")).mappings().all()
        sedi = c.execute(text("SELECT s.nome, c.nome as comune FROM sedi s LEFT JOIN comuni c ON s.comune_id = c.comune_id")).mappings().all()
        categorie = c.execute(text("SELECT nome FROM categorie")).mappings().all()
        reparti = c.execute(text("SELECT nome, descrizione, accetta_ticket FROM reparti")).mappings().all()
        
        servizi = c.execute(text("""
            SELECT s.descrizione, s.accetta_ticket, r.nome as reparto 
            FROM servizi s 
            JOIN reparti r ON s.reparto_id = r.reparto_id
        """)).mappings().all()
        
        materiali = c.execute(text("""
            SELECT m.nome, c.nome as categoria
            FROM materiali m 
            LEFT JOIN categorie c ON m.categoria_id = c.categoria_id
        """)).mappings().all()
        
        magazzini = c.execute(text("""
            SELECT m.nome, s.nome as sede, c.nome as categoria, r.nome as reparto 
            FROM magazzini m 
            LEFT JOIN sedi s ON m.sede_id = s.sede_id 
            LEFT JOIN categorie c ON m.categoria_id = c.categoria_id 
            LEFT JOIN reparti r ON m.reparto_id = r.reparto_id
        """)).mappings().all()
        
        operatori = c.execute(text("""
            SELECT u.username, u.nome, u.cognome, u.email, u.telefono, u.ruolo, 
                   r.nome as reparto, s.nome as sede, m.nome as magazzino
            FROM users u
            LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
            LEFT JOIN sedi s ON u.sede_id = s.sede_id
            LEFT JOIN magazzini m ON u.magazzino_id = m.magazzino_id
            WHERE u.ruolo != 'admin'
        """)).mappings().all()

    export_data = {
        "comuni": [dict(x) for x in comuni],
        "sedi": [dict(x) for x in sedi],
        "categorie": [dict(x) for x in categorie],
        "reparti": [dict(x) for x in reparti],
        "servizi": [dict(x) for x in servizi],
        "materiali": [dict(x) for x in materiali],
        "magazzini": [dict(x) for x in magazzini],
        "operatori": [{**dict(op), "password": ""} for op in operatori]
    }
        
    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=esportazione_anagrafiche.json"}
    )

@app.get("/admin/import/esempio.json")
def download_import_esempio(r: Request):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
        
    esempio = {
      "comuni": [
        {"nome": "Roma"},
        {"nome": "Milano"}
      ],
      "sedi": [
        {"nome": "Sede Centrale", "comune": "Roma"},
        {"nome": "Filiale Milano", "comune": "Milano"}
      ],
      "categorie": [
        {"nome": "Materiale Elettrico"},
        {"nome": "Arredamento Ufficio"}
      ],
      "reparti": [
        {"nome": "Ufficio Tecnico", "descrizione": "Gestione impianti e attrezzature", "accetta_ticket": 1},
        {"nome": "Risorse Umane", "descrizione": "Solo ad uso interno", "accetta_ticket": 0}
      ],
      "servizi": [
        {"descrizione": "Sostituzione Lampadine", "reparto": "Ufficio Tecnico", "accetta_ticket": 1},
        {"descrizione": "Malfunzionamento Climatizzatori", "reparto": "Ufficio Tecnico", "accetta_ticket": 1}
      ],
      "materiali": [
        {"nome": "Lampadina LED", "categoria": "Materiale Elettrico"},
        {"nome": "Sedia Ergonomica", "categoria": "Arredamento Ufficio"}
      ],
      "magazzini": [
        {"nome": "Magazzino Tecnico Roma", "sede": "Sede Centrale", "categoria": "Materiale Elettrico", "reparto": "Ufficio Tecnico"}
      ],
      "operatori": [
        {
          "username": "mario.tecnico",
          "password": "password123",
          "nome": "Mario",
          "cognome": "Rossi",
          "email": "mario.rossi@example.com",
          "telefono": "3331234567",
          "ruolo": "assistenza",
          "reparto": "Ufficio Tecnico",
          "sede": "Sede Centrale",
          "magazzino": "Magazzino Tecnico Roma"
        }
      ]
    }
    return Response(
        content=json.dumps(esempio, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=configurazione_iniziale_esempio.json"}
    )

@app.post("/admin/import/reparti")
async def import_reparti(r: Request, file: UploadFile = File(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    try:
        contents = await file.read()
        stream = io.StringIO(contents.decode("utf-8"))
        reader = csv.DictReader(stream)
        
        with engine.begin() as c:
            for row in reader:
                if row.get("nome"):
                    c.execute(text("""INSERT INTO reparti (nome, descrizione) 
                        VALUES (:nome, :descrizione)"""),
                        {"nome": row.get("nome").strip(), "descrizione": row.get("descrizione", "").strip()})
    except Exception as e:
        pass
    
    return RedirectResponse(url="/admin/reparti", status_code=303)

@app.post("/admin/import/servizi")
async def import_servizi(r: Request, file: UploadFile = File(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    try:
        contents = await file.read()
        stream = io.StringIO(contents.decode("utf-8"))
        reader = csv.DictReader(stream)
        
        with engine.begin() as c:
            for row in reader:
                if row.get("descrizione") and row.get("reparto_id"):
                    c.execute(text("""INSERT INTO servizi (descrizione, reparto_id, accetta_ticket) 
                        VALUES (:descrizione, :reparto_id, 1)"""),
                        {"descrizione": row.get("descrizione").strip(), "reparto_id": int(row.get("reparto_id"))})
    except Exception as e:
        pass
    
    return RedirectResponse(url="/admin/servizi", status_code=303)

@app.post("/admin/import/sedi")
async def import_sedi(r: Request, file: UploadFile = File(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    try:
        contents = await file.read()
        stream = io.StringIO(contents.decode("utf-8"))
        reader = csv.DictReader(stream)
        
        with engine.begin() as c:
            for row in reader:
                if row.get("nome"):
                    com_id = int(row.get("comune_id")) if row.get("comune_id") and str(row.get("comune_id")).isdigit() else None
                    c.execute(text("""INSERT INTO sedi (nome, comune_id) 
                        VALUES (:nome, :cid)"""),
                        {"nome": row.get("nome").strip(), "cid": com_id})
    except Exception as e:
        pass
    
    return RedirectResponse(url="/admin/sedi", status_code=303)

@app.get("/admin/comuni", response_class=HTMLResponse)
def admin_comuni(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        comuni = c.execute(text("SELECT comune_id, nome FROM comuni ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_comuni.html", {"request": r, "cfg": CFG, "user": user, "comuni": comuni, "error": error})

@app.post("/admin/comune")
def add_comune(r: Request, nome: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        c.execute(text("INSERT INTO comuni (nome) VALUES (:nome)"), {"nome": nome})
    return RedirectResponse(url="/admin/comuni", status_code=303)

@app.get("/admin/comune/{comune_id}/modifica", response_class=HTMLResponse)
def edit_comune_form(r: Request, comune_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        comune = c.execute(text("SELECT * FROM comuni WHERE comune_id = :id"), {"id": comune_id}).mappings().first()
        if not comune: return RedirectResponse(url="/admin/comuni")
    return templates.TemplateResponse(r, "edit_comune.html", {"request": r, "cfg": CFG, "user": user, "comune": comune})

@app.post("/admin/comune/{comune_id}/modifica")
def edit_comune_action(r: Request, comune_id: int, nome: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("UPDATE comuni SET nome = :nome WHERE comune_id = :id"),
                  {"nome": nome, "id": comune_id})
    return RedirectResponse(url="/admin/comuni", status_code=303)

@app.post("/admin/comune/delete")
def delete_comune(r: Request, comune_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.begin() as c:
        s_count = c.execute(text("SELECT COUNT(*) FROM sedi WHERE comune_id = :id"), {"id": comune_id}).scalar()
        if s_count > 0:
            return RedirectResponse(url="/admin/comuni?error=in_uso", status_code=303)
            
        c.execute(text("DELETE FROM comuni WHERE comune_id = :id"), {"id": comune_id})
    return RedirectResponse(url="/admin/comuni", status_code=303)

@app.post("/admin/import/comuni")
async def import_comuni(r: Request, file: UploadFile = File(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    try:
        contents = await file.read()
        stream = io.StringIO(contents.decode("utf-8"))
        reader = csv.DictReader(stream)
        
        with engine.begin() as c:
            for row in reader:
                if row.get("nome"):
                    try:
                        c.execute(text("""INSERT INTO comuni (nome) 
                            VALUES (:nome)"""),
                            {"nome": row.get("nome").strip()})
                    except Exception:
                        pass
    except Exception as e:
        pass
    
    return RedirectResponse(url="/admin/comuni", status_code=303)

@app.get("/admin/categorie", response_class=HTMLResponse)
def admin_categorie(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        categorie = c.execute(text("SELECT * FROM categorie ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_categorie.html", {"request": r, "cfg": CFG, "user": user, "categorie": categorie, "error": error})

@app.post("/admin/categoria")
def add_categoria(r: Request, nome: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("INSERT INTO categorie (nome) VALUES (:nome)"), {"nome": nome})
    return RedirectResponse(url="/admin/categorie", status_code=303)

@app.get("/admin/categoria/{categoria_id}/modifica", response_class=HTMLResponse)
def edit_categoria_form(r: Request, categoria_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        categoria = c.execute(text("SELECT * FROM categorie WHERE categoria_id = :id"), {"id": categoria_id}).mappings().first()
    return templates.TemplateResponse(r, "edit_categoria.html", {"request": r, "cfg": CFG, "user": user, "categoria": categoria})

@app.post("/admin/categoria/{categoria_id}/modifica")
def edit_categoria_action(r: Request, categoria_id: int, nome: str = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("UPDATE categorie SET nome = :nome WHERE categoria_id = :id"), {"nome": nome, "id": categoria_id})
    return RedirectResponse(url="/admin/categorie", status_code=303)

@app.post("/admin/categoria/delete")
def delete_categoria(r: Request, categoria_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        m_count = c.execute(text("SELECT COUNT(*) FROM materiali WHERE categoria_id = :id"), {"id": categoria_id}).scalar()
        mg_count = c.execute(text("SELECT COUNT(*) FROM magazzini WHERE categoria_id = :id"), {"id": categoria_id}).scalar()
        if m_count > 0 or mg_count > 0:
            return RedirectResponse(url="/admin/categorie?error=in_uso", status_code=303)
        c.execute(text("DELETE FROM categorie WHERE categoria_id = :id"), {"id": categoria_id})
    return RedirectResponse(url="/admin/categorie", status_code=303)

@app.get("/admin/materiali", response_class=HTMLResponse)
def admin_materiali(r: Request, error: str = None):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        materiali = c.execute(text("SELECT m.materiale_id, m.nome, c.nome as categoria_nome FROM materiali m LEFT JOIN categorie c ON m.categoria_id = c.categoria_id ORDER BY m.nome")).mappings().all()
        categorie = c.execute(text("SELECT * FROM categorie ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "admin_materiali.html", {"request": r, "cfg": CFG, "user": user, "materiali": materiali, "categorie": categorie, "error": error})

@app.post("/admin/materiale")
def add_materiale(r: Request, nome: str = Form(...), categoria_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("INSERT INTO materiali (nome, categoria_id) VALUES (:nome, :cid)"), {"nome": nome, "cid": categoria_id})
    return RedirectResponse(url="/admin/materiali", status_code=303)

@app.get("/admin/materiale/{materiale_id}/modifica", response_class=HTMLResponse)
def edit_materiale_form(r: Request, materiale_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.connect() as c:
        materiale = c.execute(text("SELECT * FROM materiali WHERE materiale_id = :id"), {"id": materiale_id}).mappings().first()
        categorie = c.execute(text("SELECT * FROM categorie ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "edit_materiale.html", {"request": r, "cfg": CFG, "user": user, "materiale": materiale, "categorie": categorie})

@app.post("/admin/materiale/{materiale_id}/modifica")
def edit_materiale_action(r: Request, materiale_id: int, nome: str = Form(...), categoria_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        c.execute(text("UPDATE materiali SET nome = :nome, categoria_id = :cid WHERE materiale_id = :id"), {"nome": nome, "cid": categoria_id, "id": materiale_id})
    return RedirectResponse(url="/admin/materiali", status_code=303)

@app.post("/admin/materiale/delete")
def delete_materiale(r: Request, materiale_id: int = Form(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse): return user
    with engine.begin() as c:
        g_count = c.execute(text("SELECT COUNT(*) FROM giacenze WHERE materiale_id = :id AND quantita > 0"), {"id": materiale_id}).scalar()
        tm_count = c.execute(text("SELECT COUNT(*) FROM ticket_materiali WHERE materiale_id = :id"), {"id": materiale_id}).scalar()
        if g_count > 0 or tm_count > 0:
            return RedirectResponse(url="/admin/materiali?error=in_uso", status_code=303)
        c.execute(text("DELETE FROM giacenze WHERE materiale_id = :id"), {"id": materiale_id})
        c.execute(text("DELETE FROM materiali WHERE materiale_id = :id"), {"id": materiale_id})
    return RedirectResponse(url="/admin/materiali", status_code=303)

@app.post("/admin/import/operatori")
async def import_operatori(r: Request, file: UploadFile = File(...)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    def h(p): return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    try:
        contents = await file.read()
        stream = io.StringIO(contents.decode("utf-8"))
        reader = csv.DictReader(stream)
        
        with engine.begin() as c:
            for row in reader:
                if row.get("username") and row.get("password"):
                    try:
                        c.execute(text("""INSERT INTO users 
                            (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, attivo) 
                            VALUES (:username, :password_hash, :nome, :cognome, :email, :telefono, 'assistenza', :reparto_id, 1)"""),
                            {"username": row.get("username").strip(),
                             "password_hash": h(row.get("password")),
                             "nome": row.get("nome", "").strip(),
                             "cognome": row.get("cognome", "").strip(),
                             "email": row.get("email", "").strip(),
                             "telefono": row.get("telefono", "").strip() if "telefono" in row else "",
                             "reparto_id": int(row.get("reparto_id")) if row.get("reparto_id") else None})
                    except:
                        pass
    except Exception as e:
        pass
    
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/operatori", response_class=HTMLResponse)
def operatori(r: Request):
    if "user" not in r.session:
        return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    # Se è superuser, reindirizza alla pagina di gestione
    if user.get("ruolo") == "admin":
        return RedirectResponse(url="/admin/operatori", status_code=303)
    
    with engine.connect() as c:
        where_clause = "WHERE u.ruolo != 'admin'"
        params = {}
        if user.get("ruolo") == "responsabile":
            user_rep = c.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": user.get("id")}).scalar()
            if user_rep:
                where_clause += " AND u.reparto_id = :rep"
                params["rep"] = user_rep

        rows = c.execute(text("""
            SELECT u.user_id, u.username, u.nome, u.cognome, u.email, u.telefono, u.ruolo, u.attivo, u.is_test,
                   GROUP_CONCAT(s.descrizione) AS servizi, sd.nome as sede_nome, m.nome as magazzino_nome
              FROM users u
              LEFT JOIN operatori_servizi os ON os.user_id = u.user_id
              LEFT JOIN servizi s ON s.servizio_id = os.servizio_id
              LEFT JOIN sedi sd ON u.sede_id = sd.sede_id
              LEFT JOIN magazzini m ON u.magazzino_id = m.magazzino_id
             """ + where_clause + """
             GROUP BY u.user_id
             ORDER BY u.nome
        """), params).mappings().all()
    return templates.TemplateResponse(r, "operatori.html", {"request": r, "cfg": CFG, "operatori": rows, "user": user})

# ===== GESTIONE OPERATORI PER ADMIN =====

@app.get("/admin/operatori", response_class=HTMLResponse)
def admin_operatori(r: Request):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        operatori = c.execute(text("""
            SELECT u.user_id, u.username, u.nome, u.cognome, u.email, u.telefono, u.ruolo, u.reparto_id, u.attivo, u.is_test,
                   GROUP_CONCAT(s.descrizione, ', ') AS servizi, r.nome AS reparto_nome, sd.nome AS sede_nome, m.nome AS magazzino_nome
              FROM users u
              LEFT JOIN operatori_servizi os ON os.user_id = u.user_id
              LEFT JOIN servizi s ON s.servizio_id = os.servizio_id
              LEFT JOIN reparti r ON u.reparto_id = r.reparto_id
              LEFT JOIN sedi sd ON u.sede_id = sd.sede_id
              LEFT JOIN magazzini m ON u.magazzino_id = m.magazzino_id
             WHERE u.ruolo != 'admin'
             GROUP BY u.user_id
             ORDER BY u.nome
        """)).mappings().all()
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        servizi = c.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi ORDER BY descrizione")).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        ruoli = c.execute(text("SELECT nome, descrizione FROM ruoli ORDER BY ruolo_id")).mappings().all()
        magazzini = c.execute(text("SELECT magazzino_id, nome, reparto_id FROM magazzini ORDER BY nome")).mappings().all()
    return templates.TemplateResponse(r, "manage_operatori.html", {"request": r, "cfg": CFG, "user": user, "operatori": operatori, "reparti": reparti, "servizi": servizi, "sedi": sedi, "ruoli": ruoli, "magazzini": magazzini})

@app.post("/admin/operatore/nuovo")
def new_operatore(r: Request, username: str=Form(...), password: str=Form(...), nome: str=Form(...), 
                  cognome: str=Form(...), email: str=Form(...), telefono: str=Form(None), 
                  reparto_id: int=Form(...), ruolo: str=Form('assistenza'), sede_id: str=Form(None), magazzino_id: str=Form(None), is_test: int=Form(0),
                  servizi: list=Form(None)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    servizi = servizi or []
    def h(p): return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    sede_id_val = int(sede_id) if sede_id and str(sede_id).isdigit() else None
    magazzino_id_val = int(magazzino_id) if magazzino_id and str(magazzino_id).isdigit() else None
    
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO users (username, password_hash, nome, cognome, email, telefono, ruolo, reparto_id, attivo, sede_id, magazzino_id, is_test)
                VALUES (:u, :h, :n, :c, :e, :tel, :ruolo, :r, 1, :sede, :mag, :is_test)
            """), {"u": username, "h": h(password), "n": nome, "c": cognome, "e": email, "tel": telefono, "ruolo": ruolo, "r": reparto_id, "sede": sede_id_val, "mag": magazzino_id_val, "is_test": is_test})
            
            user_id = c.execute(text("SELECT user_id FROM users WHERE username = :u"), {"u": username}).scalar()
            
            if user_id:
                for servizio_id in servizi:
                    try:
                        c.execute(text("""
                            INSERT INTO operatori_servizi (user_id, servizio_id) VALUES (:uid, :sid)
                        """), {"uid": user_id, "sid": int(servizio_id)})
                    except:
                        pass
        return RedirectResponse(url="/admin/operatori", status_code=303)
    except Exception as e:
        return RedirectResponse(url="/admin/operatori", status_code=303)

@app.get("/admin/operatore/{user_id}/modifica", response_class=HTMLResponse)
def edit_operatore_form(r: Request, user_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    with engine.connect() as c:
        operatore = c.execute(text("""
            SELECT u.user_id, u.username, u.nome, u.cognome, u.email, u.telefono, u.ruolo, u.reparto_id, u.attivo, u.ultimo_accesso, u.sede_id, u.magazzino_id, u.is_test
              FROM users u
             WHERE u.user_id = :id AND u.ruolo != 'admin'
        """), {"id": user_id}).mappings().first()
        
        if not operatore:
            return RedirectResponse(url="/admin/operatori")
        
        reparti = c.execute(text("SELECT reparto_id, nome FROM reparti ORDER BY nome")).mappings().all()
        servizi_assegnati = c.execute(text("""
            SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid
        """), {"uid": user_id}).scalars().all()
        servizi = c.execute(text("SELECT servizio_id, descrizione, reparto_id FROM servizi ORDER BY descrizione")).mappings().all()
        sedi = c.execute(text("SELECT sede_id, nome FROM sedi ORDER BY nome")).mappings().all()
        ruoli = c.execute(text("SELECT nome, descrizione FROM ruoli ORDER BY ruolo_id")).mappings().all()
        magazzini = c.execute(text("SELECT magazzino_id, nome, reparto_id FROM magazzini ORDER BY nome")).mappings().all()
    
    return templates.TemplateResponse(r, "edit_operatore.html", {
        "request": r, "cfg": CFG, "user": user, "operatore": operatore, 
        "reparti": reparti, "servizi": servizi, "servizi_assegnati": servizi_assegnati, "sedi": sedi, "ruoli": ruoli, "magazzini": magazzini
    })

@app.post("/admin/operatore/{user_id}/modifica")
def edit_operatore(r: Request, user_id: int, background_tasks: BackgroundTasks, nome: str=Form(...), cognome: str=Form(...), 
                   email: str=Form(...), telefono: str=Form(None), 
                   reparto_id: int=Form(...), ruolo: str=Form(...), attivo: int=Form(0),
                   password: str=Form(""), servizi: list=Form(None), sede_id: str=Form(None), magazzino_id: str=Form(None), is_test: int=Form(0)):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    servizi = servizi or []
    def h(p): return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    sede_id_val = int(sede_id) if sede_id and str(sede_id).isdigit() else None
    magazzino_id_val = int(magazzino_id) if magazzino_id and str(magazzino_id).isdigit() else None
    
    tel_param = {"tel": telefono} if telefono is not None else {}
    tel_sql = "telefono=:tel, " if telefono is not None else ""
    
    with engine.begin() as c:
        op_prev = c.execute(text("SELECT attivo, email, username FROM users WHERE user_id=:uid"), {"uid": user_id}).mappings().first()
        
        if password:
            c.execute(text(f"""
                UPDATE users SET nome=:n, cognome=:c, email=:e, {tel_sql}reparto_id=:r, ruolo=:ruolo, attivo=:a, password_hash=:p, sede_id=:sede, magazzino_id=:mag, is_test=:is_test
                 WHERE user_id=:uid AND ruolo != 'admin'
            """), {"n": nome, "c": cognome, "e": email, "r": reparto_id, "ruolo": ruolo, "a": attivo, "p": h(password), "sede": sede_id_val, "mag": magazzino_id_val, "is_test": is_test, "uid": user_id, **tel_param})
        else:
            c.execute(text(f"""
                UPDATE users SET nome=:n, cognome=:c, email=:e, {tel_sql}reparto_id=:r, ruolo=:ruolo, attivo=:a, sede_id=:sede, magazzino_id=:mag, is_test=:is_test
                 WHERE user_id=:uid AND ruolo != 'admin'
            """), {"n": nome, "c": cognome, "e": email, "r": reparto_id, "ruolo": ruolo, "a": attivo, "sede": sede_id_val, "mag": magazzino_id_val, "is_test": is_test, "uid": user_id, **tel_param})
        
        # Aggiorna servizi assegnati
        c.execute(text("DELETE FROM operatori_servizi WHERE user_id = :uid"), {"uid": user_id})
        for servizio_id in servizi:
            try:
                c.execute(text("""
                    INSERT INTO operatori_servizi (user_id, servizio_id) VALUES (:uid, :sid)
                """), {"uid": user_id, "sid": int(servizio_id)})
            except:
                pass
                
        if attivo == 1 and op_prev and op_prev["attivo"] == 0 and op_prev["email"]:
            subject = f"[{CFG.get('company_name', 'Helpdesk')}] Account Attivato"
            body = templates.get_template("email_operatore_attivo.html").render({"cfg": CFG, "nome": nome, "username": op_prev["username"]})
            background_tasks.add_task(send_email_async, op_prev["email"], subject, body)
    
    return RedirectResponse(url="/admin/operatori", status_code=303)

@app.post("/admin/operatore/{user_id}/toggle")
def toggle_operatore(r: Request, user_id: int, background_tasks: BackgroundTasks):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    with engine.begin() as c:
        op = c.execute(text("SELECT attivo, nome, email, username FROM users WHERE user_id=:uid AND ruolo != 'admin'"), {"uid": user_id}).mappings().first()
        if op:
            new_status = 0 if op["attivo"] else 1
            c.execute(text("UPDATE users SET attivo=:s WHERE user_id=:uid"), {"s": new_status, "uid": user_id})
            
            if new_status == 1 and op["attivo"] == 0 and op["email"]:
                subject = f"[{CFG.get('company_name', 'Helpdesk')}] Account Attivato"
                body = templates.get_template("email_operatore_attivo.html").render({"cfg": CFG, "nome": op["nome"], "username": op["username"]})
                background_tasks.add_task(send_email_async, op["email"], subject, body)
    
    return RedirectResponse(url="/admin/operatori", status_code=303)

@app.post("/admin/operatore/{user_id}/delete")
def delete_operatore(r: Request, user_id: int):
    user = require_superuser(r)
    if isinstance(user, RedirectResponse):
        return user
    
    with engine.begin() as c:
        c.execute(text("DELETE FROM operatori_servizi WHERE user_id = :uid"), {"uid": user_id})
        c.execute(text("DELETE FROM users WHERE user_id = :uid AND ruolo != 'admin'"), {"uid": user_id})
    
    return RedirectResponse(url="/admin/operatori", status_code=303)

# ===== GESTIONE AVVISI IN HOMEPAGE =====

@app.get("/avvisi", response_class=HTMLResponse)
def manage_avvisi(r: Request):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.connect() as c:
        if user.get("ruolo") == "admin":
            where_clause = "1=1"
            params = {}
            servizi = c.execute(text("SELECT servizio_id, descrizione FROM servizi ORDER BY descrizione")).mappings().all()
        else:
            where_clause = "a.user_id = :uid OR a.servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid)"
            params = {"uid": user.get("id")}
            servizi = c.execute(text("""
                SELECT s.servizio_id, s.descrizione 
                FROM servizi s
                JOIN operatori_servizi os ON s.servizio_id = os.servizio_id
                WHERE os.user_id = :uid
                ORDER BY s.descrizione
            """), {"uid": user.get("id")}).mappings().all()
            
        avvisi = c.execute(text(f"""
            SELECT a.*, s.descrizione as servizio_desc, u.nome, u.cognome
            FROM avvisi a
            LEFT JOIN servizi s ON a.servizio_id = s.servizio_id
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE {where_clause}
            ORDER BY a.creato_il DESC
        """), params).mappings().all()
            
    return templates.TemplateResponse(r, "manage_avvisi.html", {"request": r, "cfg": CFG, "user": user, "avvisi": avvisi, "servizi": servizi})

@app.post("/avviso/nuovo")
def nuovo_avviso(r: Request, titolo: str = Form(...), testo: str = Form(...), 
                 gravita: str = Form('info'), servizio_id: str = Form(None),
                 data_inizio: str = Form(""), ora_inizio: str = Form(""),
                 data_fine: str = Form(""), ora_fine: str = Form("")):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    dt_inizio = f"{data_inizio} {ora_inizio or '00:00'}:00" if data_inizio else None
    dt_fine = f"{data_fine} {ora_fine or '23:59'}:00" if data_fine else None
    sid = int(servizio_id) if servizio_id and str(servizio_id).isdigit() else None
    
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO avvisi (user_id, servizio_id, titolo, testo, gravita, data_inizio, data_fine)
            VALUES (:uid, :sid, :titolo, :testo, :gravita, :di, :df)
        """), {
            "uid": user.get("id"), "sid": sid, "titolo": titolo, "testo": testo,
            "gravita": gravita, "di": dt_inizio, "df": dt_fine
        })
    return RedirectResponse(url="/avvisi", status_code=303)

@app.post("/avviso/{avviso_id}/elimina")
def elimina_avviso(r: Request, avviso_id: int):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    with engine.begin() as c:
        if user.get("ruolo") == "admin":
            c.execute(text("DELETE FROM avvisi WHERE avviso_id = :id"), {"id": avviso_id})
        else:
            c.execute(text("DELETE FROM avvisi WHERE avviso_id = :id AND (user_id = :uid OR servizio_id IN (SELECT servizio_id FROM operatori_servizi WHERE user_id = :uid))"), 
                      {"id": avviso_id, "uid": user.get("id")})
    return RedirectResponse(url="/avvisi", status_code=303)

# ===== GESTIONE MAGAZZINI LATO UTENTE =====

@app.get("/magazzini", response_class=HTMLResponse)
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

@app.get("/magazzino/{magazzino_id}/movimento/{materiale_id}", response_class=HTMLResponse)
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
        from datetime import date
        oggi = date.today().isoformat()
        
    template_file = "magazzino_carico.html" if operazione == "carico" else "magazzino_scarico.html"
    return templates.TemplateResponse(r, template_file, {
        "request": r, "cfg": CFG, "user": user, 
        "magazzino": magazzino, "materiale": materiale,
        "operazione": operazione, "sedi": sedi, "magazzini_dest": magazzini_dest, "oggi": oggi
    })

@app.post("/magazzino/{magazzino_id}/movimento/{materiale_id}")
def magazzino_movimento_action(
    r: Request, magazzino_id: int, materiale_id: int, operazione: str = Form(...), quantita: int = Form(...),
    data_movimento: str = Form(...), descrizione: str = Form(""), 
    sede_assegnazione_id: str = Form(None), posizione_fisica: str = Form(""),
    marca: str = Form(""), modello: str = Form(""),
    magazzino_destinazione_id: str = Form(None),
    allegato: UploadFile = File(None)
):
    if "user" not in r.session: return RedirectResponse(url="/login")
    user = r.session.get("user")
    
    allegato_filename = save_upload(allegato)

    with engine.begin() as c:
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
            
    return RedirectResponse(url="/magazzini", status_code=303)

@app.get("/trasferimenti", response_class=HTMLResponse)
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

@app.post("/trasferimenti/{trasferimento_id}/ricevi")
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
@app.get("/magazzino/{magazzino_id}/log", response_class=HTMLResponse)
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
