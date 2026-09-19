from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.appuntamento import TipoAppuntamentoRead
from .._repo import get_owned
from .._ownership import verifica_appartenenza_paziente as _verifica_ownership
from .._common import iso_utc as _iso, utc_now as _now
from .. import configurazione
from ..exceptions import ForbiddenError, NotFoundError
from .context import AppointmentActor

MOTIVO_AUTOMATICO = "Rifiuto automatico per mancata risposta entro il termine previsto"
TESTO_DISDETTA_DEFAULT = (
    "Stai annullando l’appuntamento oltre il termine previsto. "
    "La disdetta verrà registrata come tardiva e sarà visibile nello storico degli appuntamenti. "
    "Inserisci una motivazione per proseguire."
)

STATO_LABEL = {
    "P": "In attesa del nutrizionista",
    "N": "In attesa del paziente",
    "C": "Confermato",
    "R": "Rifiutato dal nutrizionista",
    "Q": "Rifiutato dal paziente",
    "D": "Rifiuto automatico - mancata risposta del nutrizionista",
    "U": "Rifiuto automatico - mancata risposta del paziente",
    "A": "Annullato dal paziente",
    "X": "Annullato dal nutrizionista",
    "T": "Disdetta tardiva",
    "M": "Mancata presenza",
    "E": "Effettuato",
}

async def _config_ore(session: AsyncSession) -> tuple[int, int]:
    """Legge dalla configurazione applicativa le ore massime entro cui rispondere a una proposta e le ore minime di preavviso per non considerare un annullamento tardivo"""
    config = await configurazione.leggi_configurazione(session)
    return (config.ore_massime_risposta_appuntamento,config.ore_minime_annullamento_appuntamento)

async def _get_app(session: AsyncSession, app_id: int) -> dict[str, Any]:
    """Carica un appuntamento per ID"""
    row = (await session.execute(text("SELECT * FROM appuntamento WHERE id = :id"), {"id": app_id})).mappings().first()
    if row is None:
        raise NotFoundError("Appuntamento", app_id)
    return dict(row)

async def _get_tipo_utilizzabile(session: AsyncSession,*,tipo_id: int,actor: AppointmentActor) -> TipoAppuntamentoRead:
    """Carica una tipologia di appuntamento utilizzabile dall'attore corrente"""
    row = await get_owned(session,"tipo_appuntamento",tipo_id,owner_field="nutrizionista_id",owner_id=actor.nutrizionista_id,whitelist={"tipo_appuntamento"},resource_name="TipoAppuntamento",hide_unauthorized=True)
    tipo = TipoAppuntamentoRead.model_validate(row)
    # Il paziente può utilizzare soltanto tipologie abilitate alla prenotazione autonoma
    if actor.is_paziente and not tipo.prenotabile_paziente:
        raise ForbiddenError("La tipologia di appuntamento non è prenotabile dal paziente")
    return tipo

async def _verifica_appartenenza_paziente(session: AsyncSession, paziente_id: int, nutrizionista_id: int) -> None:
    """Verifica che il paziente sia effettivamente in carico al nutrizionista indicato (e che il suo account sia attivo)"""
    await _verifica_ownership(session, paziente_id, nutrizionista_id, richiedi_attivo=True)

async def _clausole_normalizzazione(session: AsyncSession,*,nutrizionista_id: int | None,paziente_id: int | None) -> tuple[list[str], dict[str, Any]]:
    """Costruisce le clausole WHERE e i parametri condivisi tra il controllo di esistenza (sola lettura) e l'UPDATE effettivo di normalizzazione"""
    ore, _ = await _config_ore(session)
    clauses = ["stato IN ('P','N')"]
    params: dict[str, Any] = {
        "ore": ore,
        "motivo": MOTIVO_AUTOMATICO,
        "evento": _iso(_now()),
    }
    # filtri opzionali (normalizzazione a solo quanto richiesto)
    if nutrizionista_id is not None:
        clauses.append("nutrizionista_id = :nid")
        params["nid"] = nutrizionista_id
    if paziente_id is not None:
        clauses.append("paziente_id = :pid")
        params["pid"] = paziente_id
    return clauses, params

async def _normalizzazioni_pendenti(session: AsyncSession,*,nutrizionista_id: int | None = None,paziente_id: int | None = None) -> bool:
    """Verifica se esistono proposte di appuntamento scadute ancora in stato 'P' o 'N' che devono essere normalizzate
    restituisce True se ne esiste almeno una"""
    clauses, params = await _clausole_normalizzazione(session, nutrizionista_id=nutrizionista_id, paziente_id=paziente_id)
    result = await session.execute(
        text(
            "SELECT 1 FROM appuntamento WHERE "
            + " AND ".join(clauses)
            + " AND julianday(proposta_at) + (:ore / 24.0) <= julianday(:evento) "
            "LIMIT 1"
        ),
        params,
    )
    return result.first() is not None

async def _normalizza_no_tx(session: AsyncSession,*,nutrizionista_id: int | None = None,paziente_id: int | None = None) -> int:
    """cerca gli appuntamenti scaduti ancora in attesa, cambia il loro stato in “rifiutato automaticamente”, 
    salva il motivo e la data dell'evento, e restituisce quanti appuntamenti ha modificato"""
    clauses, params = await _clausole_normalizzazione(
        session, nutrizionista_id=nutrizionista_id, paziente_id=paziente_id
    )
    result = await session.execute(
        text(
            "UPDATE appuntamento SET "
            "stato = CASE stato WHEN 'P' THEN 'D' ELSE 'U' END, "
            "motivo = :motivo, data_evento = :evento "
            "WHERE "
            + " AND ".join(clauses)
            + " AND julianday(proposta_at) + (:ore / 24.0) <= julianday(:evento)"
        ),
        params,
    )
    return max(int(result.rowcount or 0), 0)
