from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.enums import Ruolo, TipoDatoMedico
from . import _repo
from ._common import require
from ._ownership import verifica_appartenenza_paziente
from ._transaction import write_transaction
from .exceptions import ForbiddenError, NotFoundError, ValidationError

_UNSET = object()
_CAMPI = "id, paziente_id, tipo, descrizione"
_TABELLA = "paziente_dato_medico"
_WHITELIST = (_TABELLA,)

def _descrizione_valida(descrizione: str) -> str:
    """Viene normalizzata la descrizione e rifiutati valori vuoti o composti solo da spazi"""
    valore = descrizione.strip()
    if not valore:
        raise ValidationError("La descrizione non può essere vuota")
    return valore

async def _verifica_scrittura(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None,dato_id: int | None = None,) -> dict[str, Any] | None:
    """
    Vengono verificati i vincoli di accesso (necessario prima di creare, modificare o eliminare un dato medico)
    -Se ''dato_id' è valorizzato controlla anche esistenza e appartenenza del dato al paziente
    """
    dato = (await _repo.get_by_id(session,_TABELLA,dato_id,whitelist=_WHITELIST,) if dato_id is not None else None)
    if dato_id is not None:
        # Controllo esistenza del dato
        if dato is None:
            raise NotFoundError("DatoMedico", dato_id)
        # Controllo appartenzna dato al paziente
        if int(dato["paziente_id"]) != paziente_id:
            if nutrizionista_id is None:
                raise ForbiddenError("Accesso negato")
            raise NotFoundError("DatoMedico", dato_id)
    # controllo appartenenza nutrizionista al paziente
    if nutrizionista_id is not None:
        await verifica_appartenenza_paziente(session,paziente_id,nutrizionista_id,richiedi_attivo=False,messaggio="Il paziente non appartiene al nutrizionista",)
    return dato

async def crea_dato_medico(session: AsyncSession,*,paziente_id: int,tipo: TipoDatoMedico,descrizione: str,nutrizionista_id: int | None = None,) -> dict[str, Any]:
    """Viene creato un dato medico dopo aver verificato l’accesso e normalizzato la descrizione"""
    async with write_transaction(session):
        await _verifica_scrittura(session, paziente_id=paziente_id, nutrizionista_id=nutrizionista_id)
        row = (
            await session.execute(
                text(
                    "INSERT INTO paziente_dato_medico "
                    "(paziente_id, tipo, descrizione) "
                    "VALUES (:pid, :tipo, :descrizione) "
                    f"RETURNING {_CAMPI}"
                ),
                {
                    "pid": paziente_id,
                    "tipo": tipo.value,
                    "descrizione": _descrizione_valida(descrizione),
                },
            )
        ).mappings().first()
        row = require(row, "Errore nella creazione del dato medico")
        return dict(row)

async def lista_dati_medici(session: AsyncSession,*,paziente_id: int,richiedente_id: int,ruolo: Ruolo,tipo: TipoDatoMedico | None = None,skip: int = 0,limit: int = 50,) -> list[dict[str, Any]]:
    """
    Vengono restituti i dati medici del paziente applicando i controlli sulla base del ruolo
    -tipo limita facoltativamente il risultato a una sola categoria di dato medico
    """
    # controllo se i dati appartengono al paziente che li ha richiesti
    if ruolo == Ruolo.paziente:
        if richiedente_id != paziente_id:
            raise ForbiddenError("Accesso negato")
    # controllo appartenenza dati paziente al nutrizionista che li ha richiesto    
    elif ruolo == Ruolo.nutrizionista:
        await verifica_appartenenza_paziente(session,paziente_id,richiedente_id,richiedi_attivo=False,messaggio="Il paziente non appartiene al nutrizionista")
    # Altri ruoli rifiutati
    elif ruolo != Ruolo.admin:
        raise ForbiddenError("Ruolo non autorizzato")
    sql = f"SELECT {_CAMPI} FROM paziente_dato_medico WHERE paziente_id = :pid"
    params: dict[str, Any] = {"pid": paziente_id, "limit": limit, "skip": skip}
    if tipo is not None:
        sql += " AND tipo = :tipo"
        params["tipo"] = tipo.value
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :skip"
    return [dict(row) for row in (await session.execute(text(sql), params)).mappings().all()]

async def aggiorna_dato_medico(session: AsyncSession,*,dato_id: int,paziente_id: int,nutrizionista_id: int | None = None,tipo: TipoDatoMedico | object = _UNSET,descrizione: str | object = _UNSET,) -> dict[str, Any]:
    """
    Viene aggiornato in modo parziale un dato medico dopo i controlli di accesso
    I parametri impopstati a '_UNSET' vengono lasciati invariati e distinti da valori forniti
    """
    async with write_transaction(session):
        dato = await _verifica_scrittura(session,dato_id=dato_id,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,)
        dato = require(dato, "Dato medico non trovato")
        # Vengono costruiti solo i campi che il chiamante ha effettivamente richiesto di modificare
        aggiornamenti: dict[str, Any] = {}
        if tipo is not _UNSET:
            if not isinstance(tipo, TipoDatoMedico):
                raise ValidationError("Tipo dato medico non valido")
            aggiornamenti["tipo"] = tipo.value
        if descrizione is not _UNSET:
            if descrizione is None:
                raise ValidationError("La descrizione non può essere nulla")
            aggiornamenti["descrizione"] = _descrizione_valida(str(descrizione))
        # Nessuna modifica richiesta, viene restituito il dato già verificato
        if not aggiornamenti:
            return dato
        return await _repo.update_by_id(session, _TABELLA, dato_id, aggiornamenti, whitelist=_WHITELIST)

async def elimina_dato_medico(session: AsyncSession,*,dato_id: int,paziente_id: int,nutrizionista_id: int | None = None,) -> None:
    """Viene eliminato un dato medico solo dopo averne verificato appartenenza e permessi"""
    async with write_transaction(session):
        await _verifica_scrittura(session,dato_id=dato_id,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,)
        await session.execute(
            text("DELETE FROM paziente_dato_medico WHERE id = :id"), 
            {"id": dato_id}
        )
