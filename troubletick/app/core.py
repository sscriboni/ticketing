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