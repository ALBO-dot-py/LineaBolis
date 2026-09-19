from collections.abc import Collection, Mapping
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ._common import require
from .exceptions import ForbiddenError, NotFoundError

def _validate_identifier(value: str) -> None:
    """Verifica che 'value' sia un identificatore valido (no spazi, caratteri speciali, ecc.), per poterlo interpolare in sicurezza in una query SQL grezza senza rischiare injection"""
    if not value.isidentifier():
        raise ValueError("Identificatore SQL non valido")

def _validate_table(table: str, whitelist: Collection[str]) -> None:
    """Verifica che il nome tabella richiesto sia tra quelli esplicitamente consentiti dal chiamante (whitelist)"""
    if table not in whitelist:
        raise ValueError("Tabella non consentita")

async def get_by_id(session: AsyncSession,table: str,row_id: int,*,whitelist: Collection[str],id_field: str = "id") -> dict[str, Any] | None:
    """Legge per ID un record da una tabella consentita"""
    _validate_table(table, whitelist)
    _validate_identifier(id_field)
    row = (
        await session.execute(
            text(f"SELECT * FROM {table} WHERE {id_field} = :id"),
            {"id": row_id},
        )
    ).mappings().first()
    return dict(row) if row else None

async def update_by_id(session: AsyncSession,table: str,row_id: int,campi: Mapping[str, Any],*,whitelist: Collection[str],id_field: str = "id") -> dict[str, Any]:
    """Aggiorna per ID un record di una tabella consentita"""
    _validate_table(table, whitelist)
    _validate_identifier(id_field)
    for campo in campi:
        _validate_identifier(campo)

    # Se non ci sono campi da modificare viene restituito il record corrente 
    if not campi:
        row = await get_by_id(session, table, row_id, whitelist=whitelist, id_field=id_field)
        return require(row, "Record non trovato durante l'aggiornamento")
    set_clause = ", ".join(f"{campo} = :{campo}" for campo in campi)
    row = (
        await session.execute(
            text(
                f"UPDATE {table} SET {set_clause} "
                f"WHERE {id_field} = :id RETURNING *"
            ),
            {**campi, "id": row_id},
        )
    ).mappings().first()
    row = require(row, "Record non trovato durante l'aggiornamento")
    return dict(row)

async def get_owned(session: AsyncSession,table: str,row_id: int,*,owner_field: str,owner_id: int,whitelist: Collection[str],resource_name: str | None = None,forbidden_message: str | None = None,id_field: str = "id",missing_as_forbidden: bool = False,hide_unauthorized: bool = False) -> dict[str, Any]:
    """Legge un record per ID e verifica che appartenga all'utente previsto

    - Se la riga non esiste: solleva NotFoundError (404), a meno che 'missing_as_forbidden' non richieda di trattarla come ForbiddenError.
    - Se la riga esiste ma appartiene a un altro utente: solleva ForbiddenError (403), 
    a meno che 'hide_unauthorized' non imponga di restituire un 404 "come se non esistesse", 
    per non rivelare a un utente non autorizzato l'esistenza della risorsa altrui
    """
    _validate_identifier(owner_field)
    row = await get_by_id(session, table, row_id, whitelist=whitelist, id_field=id_field)
    resource = resource_name or table.capitalize()
    message = forbidden_message or f"Accesso a {table} negato"

    # Distinto errore di NotFound e ForbiddenError
    if row is None:
        if missing_as_forbidden:
            raise ForbiddenError(message)
        raise NotFoundError(resource, row_id)
    if row[owner_field] != owner_id:
        if hide_unauthorized:
            raise NotFoundError(resource, row_id)
        raise ForbiddenError(message)
    return row
