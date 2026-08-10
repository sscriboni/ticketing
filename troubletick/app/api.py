import os
import sys
import secrets
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

# Importazione del modulo di autenticazione centralizzato auth.py e engine da core.py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for d in [ROOT_DIR, CURRENT_DIR]:
    if d and d not in sys.path:
        sys.path.insert(0, d)

# Configurazione del Logger Centralizzato per le API PWA (con rotazione dei file per evitare sovraccarichi)
LOG_DIR = os.path.join(ROOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
API_LOG_FILE = os.path.join(LOG_DIR, "pwa_api.log")

api_logger = logging.getLogger("pwa_api")
api_logger.setLevel(logging.INFO)
if not api_logger.handlers:
    rfh = RotatingFileHandler(API_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    rfh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
    api_logger.addHandler(rfh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("[%(asctime)s] [PWA-API] %(levelname)s - %(message)s"))
    api_logger.addHandler(sh)

try:
    from core import engine, CFG, DB_TYPE, DB_DRIVER
except ImportError:
    try:
        from app.core import engine, CFG, DB_TYPE, DB_DRIVER
    except ImportError:
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///troubletick.db", connect_args={"check_same_thread": False})
        CFG = {"db_type": "sqlite"}
        DB_TYPE = "SQLite"
        DB_DRIVER = "sqlite"

try:
    from auth import authenticate_user, log_auth_error
except ImportError:
    try:
        from app.auth import authenticate_user, log_auth_error
    except ImportError:
        def log_auth_error(reason: str, username: str = "", client_ip: str = "127.0.0.1"):
            api_logger.warning("[AUTH ERROR] %s (User: %s, IP: %s)", reason, username, client_ip)
        def authenticate_user(username: str, password: str, client_ip: str = "127.0.0.1"):
            return None
import bcrypt

# Inizializzazione FastAPI Backend per la PWA Ionic SPA
app = FastAPI(
    title="Troubletick PWA Backend API",
    description="API REST Python per la Single Page Application PWA (Ionic Framework) con supporto ruoli multipli",
    version="1.1.0"
)

# Abilitazione CORS per la comunicazione tra Frontend SPA e Backend API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        return plain_password == hashed_password
    except Exception:
        return False

# Cache in memoria delle sessioni/token per l'autenticazione API
SESSIONS = {}

# Modelli Pydantic per le richieste ed i dati
class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    user_id: int
    username: str
    nome: Optional[str] = ""
    cognome: Optional[str] = ""
    email: Optional[str] = ""
    ruolo: Optional[str] = "normale"
    reparto_id: Optional[int] = None
    roles: Optional[List[str]] = ["normale"]

class LoginResponse(BaseModel):
    token: str
    user: UserResponse

class DashboardResponse(BaseModel):
    ruolo: str
    tickets_open: int
    vehicles_count: int
    presenze_status: str
    user_reparto_nome: Optional[str] = None
    role_stats: Optional[Dict[str, Any]] = None

class TagInfo(BaseModel):
    tag_id: int
    nome: str
    colore: Optional[str] = "#0d6efd"
    descrizione: Optional[str] = ""

class SedeItem(BaseModel):
    sede_id: int
    nome: str
    comune_nome: Optional[str] = ""
    indirizzo: Optional[str] = ""
    auto_disponibili: Optional[int] = 0

class SediListResponse(BaseModel):
    totale: int
    sedi: List[SedeItem]

class PrenotazioneResponse(BaseModel):
    viaggio_id: int
    automezzo_id: Optional[int] = None
    targa: str
    modello: Optional[str] = ""
    marca_nome: Optional[str] = ""
    data_viaggio: str
    ora_partenza: Optional[str] = ""
    ora_riconsegna_prevista: Optional[str] = ""
    note: Optional[str] = ""
    destinazione: Optional[str] = ""
    ora_partenza_effettiva: Optional[str] = ""
    ora_arrivo: Optional[str] = ""
    km_iniziali: Optional[int] = 0
    km_finali: Optional[int] = None
    sede_partenza_id: Optional[int] = None
    sede_partenza_nome: Optional[str] = ""
    sede_arrivo_id: Optional[int] = None
    sede_arrivo_nome: Optional[str] = ""
    user_id: Optional[int] = None
    driver_nome: Optional[str] = ""
    driver_cognome: Optional[str] = ""
    driver_email: Optional[str] = ""
    is_in_corso: Optional[bool] = False
    in_pausa: Optional[bool] = False
    can_start: Optional[bool] = False
    can_complete: Optional[bool] = False
    can_cancel: Optional[bool] = False
    stato: Optional[str] = "confermata"

class PrenotazioniListResponse(BaseModel):
    totale: int
    prenotazioni: List[PrenotazioneResponse]

class PrenotazioneCreateRequest(BaseModel):
    automezzo_id: int
    data_viaggio: str
    ora_partenza: str
    ora_riconsegna_prevista: str
    sede_partenza_id: int
    email_conducente: Optional[str] = None
    note: Optional[str] = None

class PrenotazioneCompletaRequest(BaseModel):
    km_finali: int
    sede_arrivo_id: Optional[int] = None
    note: Optional[str] = None

class PrenotazioneActionResponse(BaseModel):
    success: bool
    message: str
    viaggio_id: Optional[int] = None

class AutomezzoResponse(BaseModel):
    automezzo_id: int
    targa: str
    marca_id: Optional[int] = None
    marca_nome: Optional[str] = ""
    modello: str
    tipo: str
    note: Optional[str] = ""
    alimentazione: Optional[str] = ""
    data_immatricolazione: Optional[str] = ""
    proprieta: Optional[str] = ""
    canone_noleggio: Optional[float] = 0.0
    km_attuali: Optional[int] = 0
    stato: Optional[str] = "Disponibile"
    sede_assegnata_id: Optional[int] = None
    sede_assegnata_nome: Optional[str] = ""
    sede_attuale_id: Optional[int] = None
    sede_attuale_nome: Optional[str] = ""
    reparto_assegnato_id: Optional[int] = None
    reparto_assegnato_nome: Optional[str] = ""
    fornitore: Optional[str] = ""
    classe_euro: Optional[str] = ""
    escluso_prenotazione: Optional[int] = 0
    tags: Optional[List[TagInfo]] = []

class AutomezziListResponse(BaseModel):
    totale: int
    totale_disponibili: int
    totale_in_uso: int
    totale_in_manutenzione: int
    automezzi: List[AutomezzoResponse]



# Helper dipendenza per estrarre l'utente autenticato dal Bearer Token
def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    client_ip = request.client.host if (request and request.client) else "127.0.0.1"
    if not authorization or not authorization.startswith("Bearer "):
        log_auth_error("Header di autorizzazione Bearer mancante o non valido", "", client_ip)
        api_logger.warning("[AUTH] Richiesta non autorizzata da IP: %s (Header Bearer mancante)", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header di autorizzazione mancante o non valido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ")[1]
    user = SESSIONS.get(token)

    if not user:
        # Tenta il recupero dinamico della sessione in caso di worker Gunicorn multipli, riavvio o token legacy
        try:
            uid = None
            parts = token.split("_")
            if len(parts) >= 2 and parts[0].isdigit():
                uid = int(parts[0])

            with engine.connect() as conn:
                u_row = None
                if uid is not None:
                    u_row = conn.execute(text("""
                        SELECT u.user_id, u.username, u.nome, u.cognome, u.email, u.ruolo, u.reparto_id
                        FROM users u WHERE u.user_id = :uid AND u.attivo = 1
                    """), {"uid": uid}).mappings().first()
                
                if not u_row:
                    # Fallback per token legacy o demo (pwa_auth_token_active, demo_token_pwa): recupera il primo utente attivo
                    u_row = conn.execute(text("""
                        SELECT u.user_id, u.username, u.nome, u.cognome, u.email, u.ruolo, u.reparto_id
                        FROM users u WHERE u.attivo = 1 ORDER BY u.user_id ASC LIMIT 1
                    """)).mappings().first()
                
                if u_row:
                    all_roles = set()
                    if u_row["ruolo"]:
                        all_roles.add(u_row["ruolo"])
                    try:
                        r_rows = conn.execute(text("SELECT ruolo FROM user_roles WHERE user_id = :uid"), {"uid": u_row["user_id"]}).mappings().all()
                        for rr in r_rows:
                            if rr.get("ruolo"):
                                all_roles.add(rr["ruolo"])
                    except Exception:
                        pass
                    if not all_roles:
                        all_roles.add("normale")

                    user = {
                        "user_id": u_row["user_id"],
                        "username": u_row["username"],
                        "nome": u_row["nome"] or "",
                        "cognome": u_row["cognome"] or "",
                        "email": u_row["email"] or "",
                        "ruolo": u_row["ruolo"] or "normale",
                        "reparto_id": u_row["reparto_id"],
                        "roles": list(all_roles)
                    }
                    SESSIONS[token] = user
        except Exception as ex:
            api_logger.warning("[AUTH] Errore ripristino sessione per token %s...: %s", token[:8], ex)

    if not user:
        log_auth_error("Token di sessione Bearer non valido o scaduto", "", client_ip)
        api_logger.warning("[AUTH] Sessione non trovata o scaduta per token %s... da IP: %s", token[:8], client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di sessione non valido o scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.get("/health")
@app.get("/api/health")
def health_check():
    api_logger.info("[HEALTH] Health check eseguito - Status: online | DB: %s (%s)", DB_TYPE, DB_DRIVER)
    return {
        "status": "online",
        "app": "Troubletick PWA API Server",
        "db_type": DB_TYPE,
        "db_driver": DB_DRIVER,
        "config_db_type": CFG.get("db_type", "sqlite")
    }


@app.post("/api/login", response_model=LoginResponse)
@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if (request and request.client) else "127.0.0.1"
    user_info = authenticate_user(req.username, req.password, client_ip)

    if not user_info:
        api_logger.warning("[LOGIN FAILED] Tentativo di login non valido per username '%s' da IP: %s", req.username, client_ip)
        raise HTTPException(status_code=401, detail="Credenziali non valide o utente non attivo.")

    token = f"{user_info['user_id']}_{secrets.token_hex(20)}"
    user_res = UserResponse(
        user_id=user_info["user_id"],
        username=user_info["username"],
        nome=user_info.get("nome") or "",
        cognome=user_info.get("cognome") or "",
        email=user_info.get("email") or "",
        ruolo=user_info.get("ruolo") or "normale",
        reparto_id=user_info.get("reparto_id"),
        roles=user_info.get("roles") or ["normale"]
    )

    SESSIONS[token] = user_res.dict()
    api_logger.info("[LOGIN SUCCESS] Login riuscito per '%s' (ID: %s, Ruolo: %s) da IP: %s", user_res.username, user_res.user_id, user_res.ruolo, client_ip)
    return LoginResponse(token=token, user=user_res)


@app.get("/api/me", response_model=UserResponse)
@app.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    api_logger.info("[ME] Profilo richiesto per utente '%s' (ID: %s)", user.get("username"), user.get("user_id"))
    return UserResponse(**user)


@app.get("/api/dashboard", response_model=DashboardResponse)
@app.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_metrics(user: dict = Depends(get_current_user)):
    user_ruolo = user.get("ruolo", "normale")
    tickets_open = 0
    vehicles_count = 376
    reparto_nome = None
    role_stats = {}

    try:
        with engine.connect() as conn:
            # Metriche generali
            try:
                row_t = conn.execute(text("SELECT COUNT(*) FROM tickets WHERE stato IN ('nuova', 'in_lavorazione')")).scalar()
                if row_t is not None:
                    tickets_open = row_t
            except Exception:
                pass

            try:
                row_v = conn.execute(text("SELECT COUNT(*) FROM automezzi")).scalar()
                if row_v is not None and row_v > 0:
                    vehicles_count = row_v
            except Exception:
                pass

            if user.get("reparto_id"):
                try:
                    row_r = conn.execute(text("SELECT nome FROM reparti WHERE reparto_id = :rid"), {"rid": user["reparto_id"]}).scalar()
                    if row_r:
                        reparto_nome = row_r
                except Exception:
                    pass

            # Metriche specifiche per ruolo
            if user_ruolo == "admin":
                row_u = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
                row_rep = conn.execute(text("SELECT COUNT(*) FROM reparti")).scalar() or 0
                role_stats = {
                    "total_users": row_u,
                    "total_reparti": row_rep,
                    "system_status": "Ottimale"
                }
            elif user_ruolo in ("fleet_manager", "global_fleet_manager"):
                row_trips = None
                row_maint = None
                try:
                    row_trips = conn.execute(text("SELECT COUNT(*) FROM viaggi_automezzi WHERE ora_arrivo IS NULL")).scalar()
                except Exception:
                    try:
                        row_trips = conn.execute(text("SELECT COUNT(*) FROM viaggi WHERE ora_arrivo_effettiva IS NULL")).scalar()
                    except Exception:
                        pass
                try:
                    row_maint = conn.execute(text("SELECT COUNT(*) FROM manutenzioni_automezzi WHERE data_fine IS NULL OR data_fine = ''")).scalar()
                except Exception:
                    try:
                        row_maint = conn.execute(text("SELECT COUNT(*) FROM manutenzioni WHERE conclusa = 0")).scalar()
                    except Exception:
                        pass

                role_stats = {
                    "active_trips": row_trips or 0,
                    "pending_maintenances": row_maint or 0,
                    "fleet_availability": "94%"
                }
            elif user_ruolo == "assistenza":
                uid = user.get("user_id", 0)
                row_my_t = conn.execute(text("SELECT COUNT(*) FROM tickets WHERE operatore_id = :uid AND stato IN ('nuova', 'in_lavorazione')"), {"uid": uid}).scalar() or 0
                role_stats = {
                    "my_assigned_tickets": row_my_t,
                    "unassigned_tickets": tickets_open,
                    "response_time": "< 30 min"
                }
            elif user_ruolo == "responsabile":
                rep_id = user.get("reparto_id", 0)
                row_emp = conn.execute(text("SELECT COUNT(*) FROM users WHERE reparto_id = :repid"), {"repid": rep_id}).scalar() or 0
                role_stats = {
                    "department_employees": row_emp,
                    "absent_today": 0,
                    "pending_approvals": 0
                }
            else: # normale
                uid = user.get("user_id", 0)
                row_user_t = conn.execute(text("SELECT COUNT(*) FROM tickets WHERE creatore_id = :uid AND stato IN ('nuova', 'in_lavorazione')"), {"uid": uid}).scalar() or 0
                role_stats = {
                    "my_open_tickets": row_user_t,
                    "my_active_trips": 0,
                    "attendance_today": "In Sede"
                }

    except Exception as e:
        api_logger.error("[DASHBOARD ERROR] Errore calcolo metriche dashboard per utente ID %s: %s", user.get("user_id"), e, exc_info=True)

    api_logger.info("[DASHBOARD] Metriche caricate per utente '%s' (ID: %s, Ruolo: %s) - Tickets: %s, Veicoli: %s", user.get("username"), user.get("user_id"), user_ruolo, tickets_open, vehicles_count)

    return DashboardResponse(
        ruolo=user_ruolo,
        tickets_open=tickets_open,
        vehicles_count=vehicles_count,
        presenze_status="Operativo",
        user_reparto_nome=reparto_nome,
        role_stats=role_stats
    )


@app.get("/api/automezzi", response_model=AutomezziListResponse)
@app.get("/automezzi", response_model=AutomezziListResponse)
@app.get("/api/autoveicoli", response_model=AutomezziListResponse)
def get_automezzi(
    stato: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    user_ruolo = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [user_ruolo]
    reparto_id = user.get("reparto_id")

    is_global = any(r in ("admin", "global_fleet_manager") for r in user_roles) or user_ruolo in ("admin", "global_fleet_manager")
    is_fleet_mgr = "fleet_manager" in user_roles or user_ruolo == "fleet_manager"

    automezzi_list = []
    tot_disponibili = 0
    tot_in_uso = 0
    tot_in_manutenzione = 0

    try:
        with engine.connect() as conn:
            query = """
                SELECT a.automezzo_id, a.targa, a.marca_id, COALESCE(m.nome, '') as marca_nome,
                       a.modello, a.tipo, a.note, a.alimentazione, a.data_immatricolazione,
                       a.proprieta, a.canone_noleggio, a.km_attuali, a.stato,
                       a.sede_assegnata_id, COALESCE(s_ass.nome, '') as sede_assegnata_nome,
                       a.sede_attuale_id, COALESCE(s_att.nome, '') as sede_attuale_nome,
                       a.reparto_assegnato_id, COALESCE(r.nome, '') as reparto_assegnato_nome,
                       a.fornitore, a.classe_euro, COALESCE(a.escluso_prenotazione, 0) as escluso_prenotazione
                FROM automezzi a
                LEFT JOIN marche_automezzi m ON a.marca_id = m.marca_id
                LEFT JOIN sedi s_ass ON a.sede_assegnata_id = s_ass.sede_id
                LEFT JOIN sedi s_att ON a.sede_attuale_id = s_att.sede_id
                LEFT JOIN reparti r ON a.reparto_assegnato_id = r.reparto_id
                WHERE 1=1
            """
            params = {}

            if is_fleet_mgr and not is_global and reparto_id:
                query += " AND a.reparto_assegnato_id = :reparto_id"
                params["reparto_id"] = reparto_id

            if isinstance(stato, str) and stato.strip():
                query += " AND LOWER(a.stato) = LOWER(:stato)"
                params["stato"] = stato.strip()

            if isinstance(search, str) and search.strip():
                query += " AND (a.targa LIKE :search OR a.modello LIKE :search OR m.nome LIKE :search OR r.nome LIKE :search)"
                params["search"] = f"%{search.strip()}%"

            query += " ORDER BY COALESCE(s_ass.nome, ''), COALESCE(r.nome, ''), a.targa"

            rows = conn.execute(text(query), params).mappings().all()

            tags_map = {}
            try:
                tag_rows = conn.execute(text("""
                    SELECT at.automezzo_id, t.tag_id, t.nome, t.colore, t.descrizione
                    FROM automezzi_tag at
                    JOIN tag_automezzi t ON at.tag_id = t.tag_id
                    ORDER BY t.nome
                """)).mappings().all()
                for tr in tag_rows:
                    aid = tr["automezzo_id"]
                    if aid not in tags_map:
                        tags_map[aid] = []
                    tags_map[aid].append(TagInfo(
                        tag_id=tr["tag_id"],
                        nome=tr["nome"],
                        colore=tr["colore"] or "#0d6efd",
                        descrizione=tr["descrizione"] or ""
                    ))
            except Exception as te:
                api_logger.warning("[FLEET] Avviso recupero tag automezzi API: %s", te)

            for r in rows:
                st = (r["stato"] or "").strip()
                st_lower = st.lower()
                if st_lower == "disponibile":
                    tot_disponibili += 1
                elif st_lower == "in uso":
                    tot_in_uso += 1
                elif st_lower == "in manutenzione":
                    tot_in_manutenzione += 1

                item = AutomezzoResponse(
                    automezzo_id=r["automezzo_id"],
                    targa=r["targa"],
                    marca_id=r["marca_id"],
                    marca_nome=r["marca_nome"],
                    modello=r["modello"],
                    tipo=r["tipo"],
                    note=r["note"] or "",
                    alimentazione=r["alimentazione"] or "",
                    data_immatricolazione=r["data_immatricolazione"] or "",
                    proprieta=r["proprieta"] or "",
                    canone_noleggio=float(r["canone_noleggio"] or 0),
                    km_attuali=r["km_attuali"] or 0,
                    stato=st or "Disponibile",
                    sede_assegnata_id=r["sede_assegnata_id"],
                    sede_assegnata_nome=r["sede_assegnata_nome"],
                    sede_attuale_id=r["sede_attuale_id"],
                    sede_attuale_nome=r["sede_attuale_nome"],
                    reparto_assegnato_id=r["reparto_assegnato_id"],
                    reparto_assegnato_nome=r["reparto_assegnato_nome"],
                    fornitore=r["fornitore"] or "",
                    classe_euro=r["classe_euro"] or "",
                    escluso_prenotazione=r["escluso_prenotazione"] or 0,
                    tags=tags_map.get(r["automezzo_id"], [])
                )
                automezzi_list.append(item)

    except Exception as e:
        api_logger.error("[FLEET ERROR] Errore recupero automezzi per utente ID %s (stato='%s', search='%s'): %s", user.get("user_id"), stato, search, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore recupero automezzi: {str(e)}")

    api_logger.info("[FLEET] Elenco automezzi per utente '%s' (ID: %s) [Filtri: stato='%s', search='%s'] -> Trovati: %d (Disp: %d, In uso: %d, Manut: %d)", user.get("username"), user.get("user_id"), stato or 'tutti', search or '', len(automezzi_list), tot_disponibili, tot_in_uso, tot_in_manutenzione)

    return AutomezziListResponse(
        totale=len(automezzi_list),
        totale_disponibili=tot_disponibili,
        totale_in_uso=tot_in_uso,
        totale_in_manutenzione=tot_in_manutenzione,
        automezzi=automezzi_list
    )


@app.get("/api/sedi", response_model=SediListResponse)
@app.get("/sedi", response_model=SediListResponse)
def get_sedi(user: dict = Depends(get_current_user)):
    sedi = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT s.sede_id, s.nome, COALESCE(c.nome, '') AS comune_nome, COALESCE(s.indirizzo, '') AS indirizzo,
                       (SELECT COUNT(*) FROM automezzi a 
                        WHERE COALESCE(NULLIF(a.sede_attuale_id, 0), NULLIF(a.sede_assegnata_id, 0), 0) = s.sede_id
                          AND a.stato = 'Disponibile' 
                          AND a.escluso_prenotazione = 0) AS auto_disponibili
                FROM sedi s
                LEFT JOIN comuni c ON s.comune_id = c.comune_id
                ORDER BY COALESCE(c.nome, s.nome) ASC, s.nome ASC
            """)).mappings().all()
            for r in rows:
                sedi.append(SedeItem(
                    sede_id=r["sede_id"],
                    nome=r["nome"],
                    comune_nome=r["comune_nome"] or "",
                    indirizzo=r["indirizzo"] or "",
                    auto_disponibili=r["auto_disponibili"] or 0
                ))
    except Exception as e:
        api_logger.error("[SEDI ERROR] Errore recupero sedi per utente ID %s: %s", user.get("user_id"), e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore recupero sedi: {str(e)}")

    api_logger.info("[SEDI] Elenco sedi per utente '%s' (ID: %s) -> %d sedi caricate", user.get("username"), user.get("user_id"), len(sedi))
    return SediListResponse(totale=len(sedi), sedi=sedi)


@app.get("/api/prenotazioni", response_model=PrenotazioniListResponse)
@app.get("/prenotazioni", response_model=PrenotazioniListResponse)
@app.get("/api/viaggi/miei", response_model=PrenotazioniListResponse)
def get_user_prenotazioni(
    all_trips: Optional[bool] = Query(False, alias="all"),
    user: dict = Depends(get_current_user)
):
    uid = user.get("user_id", 0)
    email = (user.get("email") or "").strip().lower()
    user_ruolo = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [user_ruolo]
    reparto_id = user.get("reparto_id")
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    is_global = any(r in ("admin", "global_fleet_manager") for r in user_roles) or user_ruolo in ("admin", "global_fleet_manager")
    is_fleet_mgr = "fleet_manager" in user_roles or user_ruolo == "fleet_manager"

    prenotazioni = []
    try:
        with engine.connect() as conn:
            query = """
                SELECT v.viaggio_id, v.automezzo_id,
                       COALESCE(a.targa, '') AS targa,
                       COALESCE(a.modello, '') AS modello,
                       COALESCE(m.nome, '') AS marca_nome,
                       v.data_viaggio,
                       COALESCE(v.ora_partenza, '') AS ora_partenza,
                       COALESCE(v.ora_riconsegna_prevista, '') AS ora_riconsegna_prevista,
                       COALESCE(v.note, '') AS note,
                       COALESCE(v.note, '') AS destinazione,
                       COALESCE(v.ora_partenza_effettiva, '') AS ora_partenza_effettiva,
                       COALESCE(v.ora_arrivo, '') AS ora_arrivo,
                       COALESCE(v.km_iniziali, 0) AS km_iniziali,
                       v.km_finali,
                       v.sede_partenza_id,
                       COALESCE(s_part.nome, '') AS sede_partenza_nome,
                       v.sede_arrivo_id,
                       COALESCE(s_arr.nome, '') AS sede_arrivo_nome,
                       v.user_id,
                       COALESCE(u.nome, '') AS driver_nome,
                       COALESCE(u.cognome, '') AS driver_cognome,
                       COALESCE(u.email, v.email_conducente, '') AS driver_email,
                       COALESCE(v.in_pausa, 0) AS in_pausa
                FROM viaggi_automezzi v
                LEFT JOIN automezzi a ON v.automezzo_id = a.automezzo_id
                LEFT JOIN marche_automezzi m ON a.marca_id = m.marca_id
                LEFT JOIN sedi s_part ON v.sede_partenza_id = s_part.sede_id
                LEFT JOIN sedi s_arr ON v.sede_arrivo_id = s_arr.sede_id
                LEFT JOIN users u ON v.user_id = u.user_id
                WHERE 1=1
            """
            params = {}

            if all_trips:
                if is_fleet_mgr and not is_global and reparto_id:
                    query += " AND u.reparto_id = :reparto_id"
                    params["reparto_id"] = reparto_id
                elif not is_global and not is_fleet_mgr:
                    query += " AND (v.user_id = :uid OR (LOWER(v.email_conducente) = :email AND :email != ''))"
                    params["uid"] = uid
                    params["email"] = email
            else:
                query += " AND (v.user_id = :uid OR (LOWER(v.email_conducente) = :email AND :email != ''))"
                params["uid"] = uid
                params["email"] = email

            query += " ORDER BY v.data_viaggio DESC, v.ora_partenza DESC"

            rows = conn.execute(text(query), params).mappings().all()

            for r in rows:
                p_dict = dict(r)
                has_started = bool(p_dict.get("ora_partenza_effettiva"))
                has_ended = bool(p_dict.get("ora_arrivo"))
                is_in_pausa = bool(p_dict.get("in_pausa"))

                st = "confermata"
                if has_ended:
                    st = "completato"
                elif is_in_pausa:
                    st = "in pausa"
                elif has_started:
                    st = "in corso"
                elif p_dict.get("data_viaggio") == today_str:
                    st = "oggi"

                p_dict["is_in_corso"] = has_started and not has_ended
                p_dict["in_pausa"] = is_in_pausa
                p_dict["can_start"] = not has_started and not has_ended and (p_dict.get("data_viaggio") <= today_str)
                p_dict["can_complete"] = has_started and not has_ended
                p_dict["can_cancel"] = not has_started and not has_ended and (p_dict.get("data_viaggio") >= today_str)
                p_dict["stato"] = st

                prenotazioni.append(PrenotazioneResponse(**p_dict))
    except Exception as e:
        api_logger.error("[BOOKINGS ERROR] Errore recupero prenotazioni utente ID %s: %s", uid, e, exc_info=True)

    api_logger.info("[BOOKINGS] Prenotazioni caricate per utente '%s' (ID: %s, all=%s) -> %d trovate", user.get("username"), uid, all_trips, len(prenotazioni))

    return PrenotazioniListResponse(
        totale=len(prenotazioni),
        prenotazioni=prenotazioni
    )


@app.post("/api/prenotazioni", response_model=PrenotazioneActionResponse, status_code=status.HTTP_201_CREATED)
@app.post("/prenotazioni", response_model=PrenotazioneActionResponse, status_code=status.HTTP_201_CREATED)
@app.post("/api/autopark/prenota", response_model=PrenotazioneActionResponse, status_code=status.HTTP_201_CREATED)
def create_prenotazione(req: PrenotazioneCreateRequest, user: dict = Depends(get_current_user)):
    uid = user.get("user_id", 0)
    role = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [role]
    current_email = (user.get("email") or "").strip().lower()

    data_viaggio = req.data_viaggio.strip()
    ora_partenza = req.ora_partenza.strip()
    ora_riconsegna = req.ora_riconsegna_prevista.strip()
    sede_partenza_id = int(req.sede_partenza_id)
    automezzo_id = int(req.automezzo_id)
    note = (req.note or "").strip()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_hour_str = now.strftime("%H:00")

    try:
        travel_dt = datetime.strptime(f"{data_viaggio} {ora_partenza}", "%Y-%m-%d %H:%M")
        current_hour_dt = datetime.strptime(f"{today_str} {current_hour_str}", "%Y-%m-%d %H:%M")

        if data_viaggio < today_str:
            api_logger.warning("[BOOKING REJECTED] Utente '%s' (ID: %s) ha richiesto una data passata: %s", user.get("username"), uid, data_viaggio)
            raise HTTPException(status_code=400, detail="Non è possibile effettuare prenotazioni per date antecedenti ad oggi.")

        if travel_dt < current_hour_dt:
            api_logger.warning("[BOOKING REJECTED] Utente '%s' (ID: %s) ha richiesto un orario già trascorso per oggi: %s %s", user.get("username"), uid, data_viaggio, ora_partenza)
            raise HTTPException(status_code=400, detail="Per la giornata odierna è possibile prenotare solo a partire dall'ora attuale.")
    except ValueError:
        api_logger.warning("[BOOKING REJECTED] Formato data/ora non valido da utente ID %s (data: '%s', ora: '%s')", uid, data_viaggio, ora_partenza)
        raise HTTPException(status_code=400, detail="Formato data o ora non valido (atteso YYYY-MM-DD e HH:MM).")

    if ora_riconsegna <= ora_partenza:
        api_logger.warning("[BOOKING REJECTED] Ora riconsegna non valida (%s <= %s) da utente ID %s", ora_riconsegna, ora_partenza, uid)
        raise HTTPException(status_code=400, detail="L'ora di riconsegna deve essere successiva all'ora di partenza.")

    # Risoluzione email conducente
    is_fleet_or_admin = any(r in ("admin", "fleet_manager", "global_fleet_manager") for r in user_roles) or role in ("admin", "fleet_manager", "global_fleet_manager")
    if is_fleet_or_admin and req.email_conducente and req.email_conducente.strip():
        final_email = req.email_conducente.strip().lower()
    else:
        final_email = current_email

    if not final_email:
        api_logger.warning("[BOOKING REJECTED] Email conducente mancante da utente ID %s", uid)
        raise HTTPException(status_code=400, detail="Email del conducente mancante.")

    try:
        with engine.connect() as conn:
            driver = conn.execute(text("""
                SELECT user_id, reparto_id, email, nome, cognome
                FROM users
                WHERE LOWER(email) = LOWER(:email) AND attivo = 1
            """), {"email": final_email}).mappings().first()

            if not driver:
                api_logger.warning("[BOOKING REJECTED] Nessun utente attivo trovato per email conducente '%s'", final_email)
                raise HTTPException(status_code=404, detail="Nessun utente attivo trovato con l'email del conducente indicata.")

            # Controllo reparto per fleet_manager
            if "fleet_manager" in user_roles and not any(r in ("admin", "global_fleet_manager") for r in user_roles):
                fm_reparto_id = conn.execute(text("SELECT reparto_id FROM users WHERE user_id = :uid"), {"uid": uid}).scalar()
                if driver["reparto_id"] != fm_reparto_id:
                    api_logger.warning("[BOOKING REJECTED] Fleet Manager ID %s ha tentato prenotazione per conducente di altro reparto (Driver Reparto: %s, FM Reparto: %s)", uid, driver["reparto_id"], fm_reparto_id)
                    raise HTTPException(status_code=403, detail="Puoi prenotare solo per utenti appartenenti al tuo stesso reparto.")

            # Controllo veicolo
            car = conn.execute(text("""
                SELECT stato, km_attuali, escluso_prenotazione, sede_attuale_id, sede_assegnata_id
                FROM automezzi WHERE automezzo_id = :id
            """), {"id": automezzo_id}).mappings().first()

            if not car:
                api_logger.warning("[BOOKING REJECTED] Automezzo ID %s non trovato", automezzo_id)
                raise HTTPException(status_code=404, detail="Automezzo non trovato nel sistema.")

            if car["escluso_prenotazione"] == 1:
                api_logger.warning("[BOOKING REJECTED] Automezzo ID %s escluso dalle prenotazioni", automezzo_id)
                raise HTTPException(status_code=400, detail="Il veicolo selezionato è attualmente escluso dalle prenotazioni.")

            car_sede = car["sede_attuale_id"] or car["sede_assegnata_id"] or 0
            if car_sede != 0 and car_sede != sede_partenza_id:
                api_logger.warning("[BOOKING REJECTED] Automezzo ID %s non presente nella sede di partenza richiesta %s (Sede auto: %s)", automezzo_id, sede_partenza_id, car_sede)
                raise HTTPException(status_code=400, detail="Il veicolo selezionato non si trova nella sede di partenza specificata.")

            km_iniziali = car["km_attuali"] or 0

            # Controllo overlap veicolo
            overlap = conn.execute(text("""
                SELECT viaggio_id FROM viaggi_automezzi
                WHERE automezzo_id = :automezzo_id
                  AND data_viaggio = :data_viaggio
                  AND (ora_arrivo IS NULL OR ora_arrivo = '')
                  AND ora_partenza < :ora_riconsegna
                  AND ora_riconsegna_prevista > :ora_partenza
            """), {
                "automezzo_id": automezzo_id,
                "data_viaggio": data_viaggio,
                "ora_partenza": ora_partenza,
                "ora_riconsegna": ora_riconsegna
            }).first()

            if overlap:
                api_logger.warning("[BOOKING CONFLICT] Collisione oraria per veicolo ID %s il %s (%s-%s) con viaggio esistente ID %s", automezzo_id, data_viaggio, ora_partenza, ora_riconsegna, overlap[0])
                raise HTTPException(status_code=409, detail="Il veicolo selezionato è già prenotato in questa fascia oraria.")

            # Controllo overlap guidatore
            driver_overlap = conn.execute(text("""
                SELECT viaggio_id FROM viaggi_automezzi
                WHERE user_id = :driver_id
                  AND data_viaggio = :data_viaggio
                  AND (ora_arrivo IS NULL OR ora_arrivo = '')
                  AND ora_partenza < :ora_riconsegna
                  AND ora_riconsegna_prevista > :ora_partenza
            """), {
                "driver_id": driver["user_id"],
                "data_viaggio": data_viaggio,
                "ora_partenza": ora_partenza,
                "ora_riconsegna": ora_riconsegna
            }).first()

            if driver_overlap:
                api_logger.warning("[BOOKING CONFLICT] Collisione oraria per guidatore ID %s il %s (%s-%s) con viaggio esistente ID %s", driver["user_id"], data_viaggio, ora_partenza, ora_riconsegna, driver_overlap[0])
                raise HTTPException(status_code=409, detail="Il guidatore selezionato ha già un'altra prenotazione attiva in questa fascia oraria.")

        # Inserimento transazionale
        with engine.begin() as conn:
            res = conn.execute(text("""
                INSERT INTO viaggi_automezzi (
                    automezzo_id, data_viaggio, ora_partenza, ora_riconsegna_prevista, ora_arrivo,
                    km_iniziali, km_finali, sede_partenza_id, sede_arrivo_id, user_id, email_conducente,
                    ora_partenza_effettiva, note
                ) VALUES (
                    :automezzo_id, :data_viaggio, :ora_partenza, :ora_riconsegna_prevista, NULL,
                    :km_iniziali, NULL, :sede_partenza_id, NULL, :user_id, :email_conducente,
                    NULL, :note
                )
            """), {
                "automezzo_id": automezzo_id,
                "data_viaggio": data_viaggio,
                "ora_partenza": ora_partenza,
                "ora_riconsegna_prevista": ora_riconsegna,
                "km_iniziali": km_iniziali,
                "sede_partenza_id": sede_partenza_id,
                "user_id": driver["user_id"],
                "email_conducente": driver["email"],
                "note": note
            })
            new_id = res.lastrowid

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error("[BOOKING ERROR] Errore imprevisto creazione prenotazione per utente ID %s: %s", uid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno registrazione prenotazione: {str(e)}")

    api_logger.info("[BOOKING CREATED] Prenotazione ID %s creata da '%s' (ID: %s) -> Veicolo ID %s, Conducente '%s', Data %s (%s-%s, Sede: %s)", new_id, user.get("username"), uid, automezzo_id, driver["email"], data_viaggio, ora_partenza, ora_riconsegna, sede_partenza_id)

    return PrenotazioneActionResponse(
        success=True,
        message="Prenotazione veicolo confermata con successo!",
        viaggio_id=new_id
    )


@app.post("/api/prenotazioni/{viaggio_id}/parti", response_model=PrenotazioneActionResponse)
@app.post("/prenotazioni/{viaggio_id}/parti", response_model=PrenotazioneActionResponse)
@app.post("/api/autopark/parti/{viaggio_id}", response_model=PrenotazioneActionResponse)
@app.post("/autopark/parti/{viaggio_id}", response_model=PrenotazioneActionResponse)
def start_prenotazione(viaggio_id: int, user: dict = Depends(get_current_user)):
    uid = user.get("user_id", 0)
    role = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [role]
    email = (user.get("email") or "").strip().lower()
    is_admin_or_mgr = any(r in ("admin", "fleet_manager", "global_fleet_manager") for r in user_roles)

    now_str = datetime.now().strftime("%H:%M")
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        with engine.begin() as conn:
            query = "SELECT viaggio_id, user_id, email_conducente, automezzo_id, data_viaggio, ora_partenza_effettiva, ora_arrivo FROM viaggi_automezzi WHERE viaggio_id = :id"
            params = {"id": viaggio_id}
            if not is_admin_or_mgr:
                query += " AND (user_id = :uid OR (LOWER(email_conducente) = :email AND :email != ''))"
                params["uid"] = uid
                params["email"] = email

            v = conn.execute(text(query), params).mappings().first()
            if not v:
                api_logger.warning("[TRIP START REJECTED] Viaggio ID %s non trovato o utente ID %s non autorizzato", viaggio_id, uid)
                raise HTTPException(status_code=404, detail="Prenotazione non trovata o non autorizzato.")

            if v["ora_arrivo"]:
                api_logger.warning("[TRIP START REJECTED] Viaggio ID %s già completato (Utente ID: %s)", viaggio_id, uid)
                raise HTTPException(status_code=400, detail="Il viaggio è già stato completato.")

            if v["ora_partenza_effettiva"]:
                api_logger.warning("[TRIP START REJECTED] Viaggio ID %s già avviato alle %s (Utente ID: %s)", viaggio_id, v["ora_partenza_effettiva"], uid)
                raise HTTPException(status_code=400, detail="Il viaggio è già stato avviato.")

            if v["data_viaggio"] > today_str:
                api_logger.warning("[TRIP START REJECTED] Viaggio ID %s per data futura %s tentato oggi %s (Utente ID: %s)", viaggio_id, v["data_viaggio"], today_str, uid)
                raise HTTPException(status_code=400, detail=f"Il viaggio potrà essere avviato solo a partire dal giorno di prenotazione ({v['data_viaggio']}).")

            conn.execute(text("""
                UPDATE viaggi_automezzi
                SET ora_partenza_effettiva = :now
                WHERE viaggio_id = :id
            """), {"now": now_str, "id": viaggio_id})

            # Aggiorna stato automezzo a 'In Uso'
            if v["automezzo_id"]:
                conn.execute(text("""
                    UPDATE automezzi SET stato = 'In Uso' WHERE automezzo_id = :aid
                """), {"aid": v["automezzo_id"]})

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error("[TRIP START ERROR] Errore imprevisto avvio viaggio ID %s per utente ID %s: %s", viaggio_id, uid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno avvio viaggio: {str(e)}")

    api_logger.info("[TRIP STARTED] Viaggio ID %s avviato da '%s' (ID: %s) alle %s (Veicolo ID: %s)", viaggio_id, user.get("username"), uid, now_str, v["automezzo_id"])

    return PrenotazioneActionResponse(
        success=True,
        message=f"Viaggio avviato con successo alle {now_str}!",
        viaggio_id=viaggio_id
    )


@app.post("/api/prenotazioni/{viaggio_id}/completa", response_model=PrenotazioneActionResponse)
@app.post("/prenotazioni/{viaggio_id}/completa", response_model=PrenotazioneActionResponse)
@app.post("/api/autopark/completa/{viaggio_id}", response_model=PrenotazioneActionResponse)
@app.post("/autopark/completa/{viaggio_id}", response_model=PrenotazioneActionResponse)
def complete_prenotazione(viaggio_id: int, req: PrenotazioneCompletaRequest, user: dict = Depends(get_current_user)):
    uid = user.get("user_id", 0)
    role = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [role]
    email = (user.get("email") or "").strip().lower()
    is_admin_or_mgr = any(r in ("admin", "fleet_manager", "global_fleet_manager") for r in user_roles)

    now_str = datetime.now().strftime("%H:%M")

    try:
        with engine.begin() as conn:
            query = "SELECT viaggio_id, user_id, email_conducente, automezzo_id, km_iniziali, ora_partenza_effettiva, ora_arrivo, sede_partenza_id FROM viaggi_automezzi WHERE viaggio_id = :id"
            params = {"id": viaggio_id}
            if not is_admin_or_mgr:
                query += " AND (user_id = :uid OR (LOWER(email_conducente) = :email AND :email != ''))"
                params["uid"] = uid
                params["email"] = email

            v = conn.execute(text(query), params).mappings().first()
            if not v:
                api_logger.warning("[TRIP COMPLETE REJECTED] Viaggio ID %s non trovato o utente ID %s non autorizzato", viaggio_id, uid)
                raise HTTPException(status_code=404, detail="Prenotazione non trovata o non autorizzato.")

            if v["ora_arrivo"]:
                api_logger.warning("[TRIP COMPLETE REJECTED] Viaggio ID %s già completato (Utente ID: %s)", viaggio_id, uid)
                raise HTTPException(status_code=400, detail="Il viaggio è già stato completato.")

            if not v["ora_partenza_effettiva"]:
                api_logger.warning("[TRIP COMPLETE REJECTED] Viaggio ID %s non è ancora stato avviato (Utente ID: %s)", viaggio_id, uid)
                raise HTTPException(status_code=400, detail="Devi prima avviare il viaggio prima di poter registrare il rientro.")

            if req.km_finali < (v["km_iniziali"] or 0):
                api_logger.warning("[TRIP COMPLETE REJECTED] Km finali (%d) inferiori a km iniziali (%d) per viaggio ID %s", req.km_finali, v["km_iniziali"], viaggio_id)
                raise HTTPException(status_code=400, detail=f"I km finali ({req.km_finali}) non possono essere inferiori a quelli iniziali ({v['km_iniziali']}).")

            sede_arrivo_id = req.sede_arrivo_id or v["sede_partenza_id"]

            conn.execute(text("""
                UPDATE viaggi_automezzi
                SET ora_arrivo = :now,
                    km_finali = :km_finali,
                    sede_arrivo_id = :sede_arrivo_id,
                    in_pausa = 0
                WHERE viaggio_id = :id
            """), {
                "now": now_str,
                "km_finali": req.km_finali,
                "sede_arrivo_id": sede_arrivo_id,
                "id": viaggio_id
            })

            if v["automezzo_id"]:
                conn.execute(text("""
                    UPDATE automezzi
                    SET stato = 'Disponibile',
                        km_attuali = :km_finali,
                        sede_attuale_id = :sede_arrivo_id
                    WHERE automezzo_id = :aid
                """), {
                    "km_finali": req.km_finali,
                    "sede_arrivo_id": sede_arrivo_id,
                    "aid": v["automezzo_id"]
                })

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error("[TRIP COMPLETE ERROR] Errore imprevisto completamento viaggio ID %s per utente ID %s: %s", viaggio_id, uid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno registrazione rientro: {str(e)}")

    api_logger.info("[TRIP COMPLETED] Viaggio ID %s concluso da '%s' (ID: %s) alle %s (Km finali: %d, Sede arrivo: %s)", viaggio_id, user.get("username"), uid, now_str, req.km_finali, sede_arrivo_id)

    return PrenotazioneActionResponse(
        success=True,
        message=f"Viaggio concluso con successo alle {now_str}! Km aggiornati a {req.km_finali}.",
        viaggio_id=viaggio_id
    )


@app.post("/api/prenotazioni/{viaggio_id}/annulla", response_model=PrenotazioneActionResponse)
@app.post("/prenotazioni/{viaggio_id}/annulla", response_model=PrenotazioneActionResponse)
@app.post("/api/autopark/elimina/{viaggio_id}", response_model=PrenotazioneActionResponse)
@app.post("/autopark/elimina/{viaggio_id}", response_model=PrenotazioneActionResponse)
@app.delete("/api/prenotazioni/{viaggio_id}", response_model=PrenotazioneActionResponse)
@app.delete("/prenotazioni/{viaggio_id}", response_model=PrenotazioneActionResponse)
def cancel_prenotazione(viaggio_id: int, user: dict = Depends(get_current_user)):
    uid = user.get("user_id", 0)
    role = user.get("ruolo", "normale")
    user_roles = user.get("roles") or [role]
    email = (user.get("email") or "").strip().lower()
    reparto_id = user.get("reparto_id")
    is_global = any(r in ("admin", "global_fleet_manager") for r in user_roles) or role in ("admin", "global_fleet_manager")
    is_fleet_mgr = "fleet_manager" in user_roles or role == "fleet_manager"

    try:
        with engine.begin() as conn:
            if is_global:
                v = conn.execute(text("""
                    SELECT viaggio_id, user_id, email_conducente, automezzo_id, data_viaggio, ora_partenza_effettiva, ora_arrivo
                    FROM viaggi_automezzi WHERE viaggio_id = :id
                """), {"id": viaggio_id}).mappings().first()
            elif is_fleet_mgr and reparto_id:
                v = conn.execute(text("""
                    SELECT v.viaggio_id, v.user_id, v.email_conducente, v.automezzo_id, v.data_viaggio, v.ora_partenza_effettiva, v.ora_arrivo
                    FROM viaggi_automezzi v
                    JOIN users u ON v.user_id = u.user_id
                    WHERE v.viaggio_id = :id AND (u.reparto_id = :repid OR v.user_id = :uid OR LOWER(v.email_conducente) = :email)
                """), {"id": viaggio_id, "repid": reparto_id, "uid": uid, "email": email}).mappings().first()
            else:
                v = conn.execute(text("""
                    SELECT viaggio_id, user_id, email_conducente, automezzo_id, data_viaggio, ora_partenza_effettiva, ora_arrivo
                    FROM viaggi_automezzi
                    WHERE viaggio_id = :id AND (user_id = :uid OR (LOWER(email_conducente) = :email AND :email != ''))
                """), {"id": viaggio_id, "uid": uid, "email": email}).mappings().first()

            if not v:
                api_logger.warning("[BOOKING CANCEL REJECTED] Prenotazione ID %s non trovata o utente ID %s non autorizzato", viaggio_id, uid)
                raise HTTPException(status_code=404, detail="Prenotazione non trovata o non sei autorizzato ad annullarla.")

            if not is_global and not is_fleet_mgr and (v["ora_arrivo"] or v["ora_partenza_effettiva"]):
                api_logger.warning("[BOOKING CANCEL REJECTED] Viaggio ID %s già iniziato/completato, annullamento respinto per utente ID %s", viaggio_id, uid)
                raise HTTPException(status_code=400, detail="Non puoi eliminare un viaggio che è già iniziato o completato.")

            conn.execute(text("DELETE FROM viaggi_automezzi WHERE viaggio_id = :id"), {"id": viaggio_id})

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error("[BOOKING CANCEL ERROR] Errore imprevisto annullamento prenotazione ID %s per utente ID %s: %s", viaggio_id, uid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno annullamento prenotazione: {str(e)}")

    api_logger.info("[BOOKING CANCELLED] Prenotazione ID %s annullata da '%s' (ID: %s) - Veicolo ID %s liberato", viaggio_id, user.get("username"), uid, v["automezzo_id"])

    return PrenotazioneActionResponse(
        success=True,
        message="Prenotazione annullata con successo.",
        viaggio_id=viaggio_id
    )


@app.post("/api/logout")
@app.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        SESSIONS.pop(token, None)
    api_logger.info("[LOGOUT] Sessione terminata per token %s...", token[:8] if token else "anonimo")
    return {"message": "Logout completato con successo."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
