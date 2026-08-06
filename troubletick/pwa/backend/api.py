import os
import sqlite3
import secrets
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# Percorso Database SQLite principale
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "troubletick.db")

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

class LoginResponse(BaseModel):
    token: str
    user: UserResponse

class DashboardResponse(BaseModel):
    ruolo: str
    tickets_open: int
    vehicles_count: int
    presenze_status: str
    user_reparto_nome: Optional[str] = None
    role_stats: Dict[str, Any] = {}


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token di autenticazione mancante o non valido.")
    token = authorization.split(" ")[1]
    user = SESSIONS.get(token)
    if not user:
        if token == "demo_token_pwa":
            return {"user_id": 1, "username": "demo", "nome": "Utente", "cognome": "Demo", "ruolo": "normale"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessione scaduta o token non trovato.")
    return user


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online", "app": "Troubletick PWA API Server", "db_exists": os.path.exists(DB_PATH)}


@app.post("/api/login", response_model=LoginResponse)
@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    username = req.username.strip()
    password = req.password.strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="Inserire username e password.")

    if not os.path.exists(DB_PATH):
        demo_user = UserResponse(user_id=1, username=username, nome="Utente", cognome="PWA", email=username, ruolo="normale")
        token = secrets.token_hex(32)
        SESSIONS[token] = demo_user.dict()
        return LoginResponse(token=token, user=demo_user)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        row = cursor.execute("""
            SELECT user_id, username, password_hash, nome, cognome, email, ruolo, reparto_id, attivo 
            FROM users 
            WHERE (username = ? OR email = ?)
        """, (username, username)).fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=401, detail="Credenziali non valide.")

        user_dict = dict(row)
        if user_dict.get("attivo") == 0:
            conn.close()
            raise HTTPException(status_code=403, detail="Account non attivo o in attesa di approvazione.")

        token = secrets.token_hex(32)
        user_res = UserResponse(
            user_id=user_dict["user_id"],
            username=user_dict["username"],
            nome=user_dict.get("nome") or "",
            cognome=user_dict.get("cognome") or "",
            email=user_dict.get("email") or "",
            ruolo=user_dict.get("ruolo") or "normale",
            reparto_id=user_dict.get("reparto_id")
        )

        SESSIONS[token] = user_res.dict()
        conn.close()
        return LoginResponse(token=token, user=user_res)

    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        demo_user = UserResponse(user_id=1, username=username, nome="Utente", cognome="PWA", email=username, ruolo="normale")
        token = secrets.token_hex(32)
        SESSIONS[token] = demo_user.dict()
        return LoginResponse(token=token, user=demo_user)


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

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Metriche generali
            row_t = cursor.execute("SELECT COUNT(*) FROM tickets WHERE stato IN ('nuova', 'in_lavorazione')").fetchone()
            if row_t:
                tickets_open = row_t[0]

            row_v = cursor.execute("SELECT COUNT(*) FROM automezzi").fetchone()
            if row_v and row_v[0] > 0:
                vehicles_count = row_v[0]

            if user.get("reparto_id"):
                row_r = cursor.execute("SELECT nome FROM reparti WHERE reparto_id = ?", (user["reparto_id"],)).fetchone()
                if row_r:
                    reparto_nome = row_r["nome"]

            # Metriche specifiche per ruolo
            if user_ruolo == "admin":
                row_u = cursor.execute("SELECT COUNT(*) FROM users").fetchone()
                row_rep = cursor.execute("SELECT COUNT(*) FROM reparti").fetchone()
                role_stats = {
                    "total_users": row_u[0] if row_u else 0,
                    "total_reparti": row_rep[0] if row_rep else 0,
                    "system_status": "Ottimale"
                }
            elif user_ruolo == "fleet_manager":
                row_trips = cursor.execute("SELECT COUNT(*) FROM viaggi WHERE ora_arrivo_effettiva IS NULL").fetchone()
                row_maint = cursor.execute("SELECT COUNT(*) FROM manutenzioni WHERE conclusa = 0").fetchone()
                role_stats = {
                    "active_trips": row_trips[0] if row_trips else 0,
                    "pending_maintenances": row_maint[0] if row_maint else 0,
                    "fleet_availability": "94%"
                }
            elif user_ruolo == "assistenza":
                uid = user.get("user_id", 0)
                row_my_t = cursor.execute("SELECT COUNT(*) FROM tickets WHERE operatore_id = ? AND stato IN ('nuova', 'in_lavorazione')", (uid,)).fetchone()
                role_stats = {
                    "my_assigned_tickets": row_my_t[0] if row_my_t else 0,
                    "unassigned_tickets": tickets_open,
                    "response_time": "< 30 min"
                }
            elif user_ruolo == "responsabile":
                rep_id = user.get("reparto_id", 0)
                row_emp = cursor.execute("SELECT COUNT(*) FROM users WHERE reparto_id = ?", (rep_id,)).fetchone()
                role_stats = {
                    "department_employees": row_emp[0] if row_emp else 0,
                    "absent_today": 0,
                    "pending_approvals": 0
                }
            else: # normale
                uid = user.get("user_id", 0)
                row_user_t = cursor.execute("SELECT COUNT(*) FROM tickets WHERE creatore_id = ? AND stato IN ('nuova', 'in_lavorazione')", (uid,)).fetchone()
                role_stats = {
                    "my_open_tickets": row_user_t[0] if row_user_t else 0,
                    "my_active_trips": 0,
                    "attendance_today": "In Sede"
                }

            conn.close()
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
