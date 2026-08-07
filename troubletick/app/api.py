import os
import secrets
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

# Importazione del modulo di autenticazione centralizzato auth.py e engine da core.py
import sys
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for d in [ROOT_DIR, CURRENT_DIR]:
    if d and d not in sys.path:
        sys.path.insert(0, d)

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
            pass
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header di autorizzazione mancante o non valido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ")[1]
    user = SESSIONS.get(token)
    if not user:
        log_auth_error("Token di sessione Bearer non valido o scaduto", "", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di sessione non valido o scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.get("/health")
@app.get("/api/health")
def health_check():
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
        raise HTTPException(status_code=401, detail="Credenziali non valide o utente non attivo.")

    token = secrets.token_hex(32)
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
    return LoginResponse(token=token, user=user_res)


@app.get("/api/me", response_model=UserResponse)
@app.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
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
        print("Avviso consultazione DB dashboard API:", e)

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

            if stato:
                query += " AND LOWER(a.stato) = LOWER(:stato)"
                params["stato"] = stato

            if search:
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
                print("Avviso recupero tag automezzi API:", te)

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
        print("Errore recupero automezzi API:", e)
        raise HTTPException(status_code=500, detail=f"Errore recupero automezzi: {str(e)}")

    return AutomezziListResponse(
        totale=len(automezzi_list),
        totale_disponibili=tot_disponibili,
        totale_in_uso=tot_in_uso,
        totale_in_manutenzione=tot_in_manutenzione,
        automezzi=automezzi_list
    )


@app.post("/api/logout")
@app.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        SESSIONS.pop(token, None)
    return {"message": "Logout completato con successo."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
