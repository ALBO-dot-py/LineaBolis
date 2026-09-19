from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.appuntamento import TipoAppuntamentoRead, TipoAppuntamentoWrite
from .._transaction import write_transaction
from ..exceptions import ConflictError, NotFoundError
from .context import AppointmentActor

def _is_duplicate_name(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return (
        "unique constraint failed" in message
        and "tipo_appuntamento.nutrizionista_id" in message
        and "tipo_appuntamento.nome" in message
    )

async def crea_tipo_appuntamento(session: AsyncSession,*,nutrizionista_id: int,dati: TipoAppuntamentoWrite) -> TipoAppuntamentoRead:
    """Crea una nuova tipologia di appuntamento"""
    params = dati.to_sqlite_dict(exclude_unset=False)
    params["nutrizionista_id"] = nutrizionista_id
    try:
        async with write_transaction(session):
            row = (
                await session.execute(
                    text(
                        "INSERT INTO tipo_appuntamento ("
                        "nome, descrizione, prezzo_base_cent, nutrizionista_id, durata, "
                        "prenotabile_paziente, conferma_automatica) VALUES ("
                        ":nome, :descrizione, :prezzo_base_cent, :nutrizionista_id, :durata, "
                        ":prenotabile_paziente, :conferma_automatica) RETURNING *"
                    ),
                    params,
                )
            ).mappings().first()
    except IntegrityError as exc:
        # Il nome deve essere univoco tra le tipologie dello stesso nutrizionista
        if _is_duplicate_name(exc):
            raise ConflictError("Esiste già una tipologia di appuntamento con questo nome") from exc
        raise
    if row is None:
        raise RuntimeError("Qaulcosa è andato storto a seguito del salvataggio")
    return TipoAppuntamentoRead.model_validate(dict(row))

async def lista_tipi_appuntamento(session: AsyncSession,*,actor: AppointmentActor) -> list[TipoAppuntamentoRead]:
    """Elenca tutte le tipologie visibili all'attore corrente"""
    sql = "SELECT * FROM tipo_appuntamento WHERE nutrizionista_id = :nid"
    # Il paziente vede soltanto le tipologie abilitate alla prenotazione autonoma
    if actor.is_paziente:
        sql += " AND prenotabile_paziente = 1"
    sql += " ORDER BY nome COLLATE NOCASE, id"
    rows = (await session.execute(text(sql), {"nid": actor.nutrizionista_id})).mappings().all()
    return [TipoAppuntamentoRead.model_validate(dict(row)) for row in rows]

async def aggiorna_tipo_appuntamento(
    session: AsyncSession,*,tipo_id: int,nutrizionista_id: int,dati: TipoAppuntamentoWrite) -> TipoAppuntamentoRead:
    """Aggiorna una tipologia di appuntamento"""
    params = dati.to_sqlite_dict(exclude_unset=False)
    params.update({"tipo_id": tipo_id, "nutrizionista_id": nutrizionista_id})
    try:
        async with write_transaction(session, immediate=True):
            row = (
                await session.execute(
                    text(
                        "UPDATE tipo_appuntamento SET "
                        "nome = :nome, descrizione = :descrizione, "
                        "prezzo_base_cent = :prezzo_base_cent, durata = :durata, "
                        "prenotabile_paziente = :prenotabile_paziente, "
                        "conferma_automatica = :conferma_automatica "
                        "WHERE id = :tipo_id AND nutrizionista_id = :nutrizionista_id "
                        "RETURNING *"
                    ),
                    params,
                )
            ).mappings().first()
    except IntegrityError as exc:
        # Il nome deve essere univoco tra le tipologie dello stesso nutrizionista
        if _is_duplicate_name(exc):
            raise ConflictError("Esiste già una tipologia di appuntamento con questo nome") from exc
        raise
    if row is None:
        raise NotFoundError("TipoAppuntamento", tipo_id)
    return TipoAppuntamentoRead.model_validate(dict(row))

async def elimina_tipo_appuntamento(session: AsyncSession,*,tipo_id: int,nutrizionista_id: int) -> None:
    """Elimina una tipologia di appuntamento (non tocca quelli già creati)"""
    async with write_transaction(session, immediate=True):
        row = (
            await session.execute(
                text(
                    "DELETE FROM tipo_appuntamento "
                    "WHERE id = :tipo_id AND nutrizionista_id = :nutrizionista_id "
                    "RETURNING id"
                ),
                {"tipo_id": tipo_id, "nutrizionista_id": nutrizionista_id},
            )
        ).mappings().first()
    if row is None:
        raise NotFoundError("TipoAppuntamento", tipo_id)
