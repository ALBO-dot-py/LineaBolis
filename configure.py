from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "app.db"
CONFIG_PATH = ROOT / "config.json"
ENV_PATH = ROOT / ".env"

if not DB_PATH.exists():
    raise SystemExit("app.db non trovato. Creare prima il database con schema.sql e seed.sql")

# SQLAlchemy richiede quattro slash per i percorsi assoluti Unix e tre su Windows
# Path.as_posix() permette di costruire correttamente entrambi i casi
database_url = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

CONFIG_PATH.write_text(
    json.dumps({"DATABASE_URL": database_url}, indent=2) + "\n",
    encoding="utf-8",
)

ENV_PATH.write_text(f"DATABASE_URL={database_url}\n", encoding="utf-8")

print(f"Database creato: {DB_PATH}")
