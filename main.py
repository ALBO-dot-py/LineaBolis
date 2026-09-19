from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import AsyncIterator
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from routers import (
    RouterDependencies,
    build_auth_dependencies,
    install_routers,
)
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Non è stato possibile individuare il DB")

url = make_url(DATABASE_URL)

if url.get_backend_name() != "sqlite":
    raise RuntimeError("DATABASE_URL deve usare SQLite")

# L'applicazione usa esclusivamente SQLAlchemy asincrono: accetta anche
# sqlite:///... e normalizza sempre il driver a sqlite+aiosqlite.
url = url.set(drivername="sqlite+aiosqlite")
DATABASE_URL = url.render_as_string(hide_password=False)

if not url.database or url.database == ":memory:":
    raise RuntimeError(
        "database SQLite non esistente"
    )

database_path = Path(url.database).expanduser()

if not database_path.is_absolute():
    database_path = Path.cwd() / database_path

database_path.parent.mkdir(parents=True, exist_ok=True)


def initialize_database() -> None:
    """Crea le strutture mancanti usando esclusivamente ''schema.sql''."""
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.executescript(schema)


initialize_database()

engine = create_async_engine(DATABASE_URL, echo=False)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(
    dbapi_connection,
    _connection_record,
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


app = FastAPI(
    title="API nutrizionista",
    version="1.0.0",
)

WEB_CSP = (
    "default-src 'self'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
)


@app.middleware("http")
async def web_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/web"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Content-Security-Policy"] = WEB_CSP
    return response

app.mount("/web", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

@app.on_event("shutdown")
async def on_shutdown() -> None:
    await engine.dispose()

@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse("/web/login.html")

auth_dependencies = build_auth_dependencies(get_db)


install_routers(
    app,
    RouterDependencies(
        get_db=get_db,
        get_current_user=auth_dependencies.get_current_user,
        get_current_admin=auth_dependencies.get_current_admin,
        get_current_nutrizionista=(
            auth_dependencies.get_current_nutrizionista
        ),
        get_current_paziente=(
            auth_dependencies.get_current_paziente
        ),
    ),
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
