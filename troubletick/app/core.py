import os, json
from sqlalchemy import create_engine, text
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    CFG = json.load(f)

db_type = CFG.get("db_type", "sqlite")
if db_type == "mysql":
    DATABASE_URL = f"mysql+pymysql://{CFG.get('db_user', '')}:{CFG.get('db_password', '')}@{CFG.get('db_host', 'localhost')}:{CFG.get('db_port', 3306)}/{CFG.get('db_name', '')}?charset=utf8mb4"
elif db_type == "postgresql":
    DATABASE_URL = f"postgresql://{CFG.get('db_user', '')}:{CFG.get('db_password', '')}@{CFG.get('db_host', 'localhost')}:{CFG.get('db_port', 5432)}/{CFG.get('db_name', '')}"
else:
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'troubletick.db')}"

DATABASE_URL = os.getenv("DATABASE_URL", DATABASE_URL)

DB_DRIVER = DATABASE_URL.split("://", 1)[0].lower()
connect_args = {"check_same_thread": False} if DB_DRIVER.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
DB_TYPE = "SQLite" if DB_DRIVER.startswith("sqlite") else "MySQL" if DB_DRIVER.startswith("mysql") else DB_DRIVER.upper()
DB_PK = "INTEGER PRIMARY KEY AUTOINCREMENT" if DB_DRIVER.startswith("sqlite") else "INTEGER PRIMARY KEY AUTO_INCREMENT"

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def get_last_inserted_id(conn):
    if DB_DRIVER.startswith("sqlite"):
        return conn.execute(text("SELECT last_insert_rowid()")).scalar()
    elif DB_DRIVER.startswith("mysql"):
        return conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    else:
        return conn.execute(text("SELECT LASTVAL()")).scalar()

def init_config():
    """Crea la tabella impostazioni_sistema se non esiste e sincronizza CFG con il DB"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS impostazioni_sistema (
                    chiave VARCHAR(100) PRIMARY KEY,
                    valore TEXT
                )
            """))
            rows = conn.execute(text("SELECT chiave, valore FROM impostazioni_sistema")).mappings().all()
            for r in rows:
                k = r["chiave"]
                v = r["valore"]
                if v is None:
                    continue
                v_str = str(v).strip()
                if v_str.lower() == "true":
                    CFG[k] = True
                elif v_str.lower() == "false":
                    CFG[k] = False
                elif v_str.isdigit():
                    CFG[k] = int(v_str)
                else:
                    CFG[k] = v_str
    except Exception as e:
        print("init_config warning:", e)

def save_config_item(key: str, value):
    """Salva una chiave di configurazione sia in CFG, sia nel DB, sia su config.json"""
    CFG[key] = value
    str_val = "true" if value is True else "false" if value is False else str(value)

    # 1. Salva nel DB (persistenza affidabile e multi-processo)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS impostazioni_sistema (
                    chiave VARCHAR(100) PRIMARY KEY,
                    valore TEXT
                )
            """))
            conn.execute(text("DELETE FROM impostazioni_sistema WHERE chiave = :k"), {"k": key})
            conn.execute(text("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (:k, :v)"), {"k": key, "v": str_val})
    except Exception as e:
        print(f"Errore salvataggio DB per {key}:", e)

    # 2. Salva in config.json
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(CFG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Errore salvataggio config.json:", e)

def save_all_config(new_dict: dict):
    """Aggiorna molteplici parametri sia in CFG, sia nel DB, sia su file config.json"""
    for k, v in new_dict.items():
        CFG[k] = v

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS impostazioni_sistema (
                    chiave VARCHAR(100) PRIMARY KEY,
                    valore TEXT
                )
            """))
            for k, v in new_dict.items():
                str_val = "true" if v is True else "false" if v is False else str(v)
                conn.execute(text("DELETE FROM impostazioni_sistema WHERE chiave = :k"), {"k": k})
                conn.execute(text("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (:k, :v)"), {"k": k, "v": str_val})
    except Exception as e:
        print("Errore salvataggio massivo DB:", e)

    try:
        with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(CFG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Errore salvataggio config.json:", e)

# Inizializza subito le impostazioni dal DB al caricamento del modulo
init_config()
