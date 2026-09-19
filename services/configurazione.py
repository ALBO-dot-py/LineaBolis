from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.configurazione import ConfigurazioneAppRequest, ConfigurazioneAppResponse
from ._transaction import write_transaction

_CHIAVI = tuple(ConfigurazioneAppRequest.model_fields)

async def leggi_configurazione(session: AsyncSession) -> ConfigurazioneAppResponse:
    """Legge la configurazione dell'app e la converte nello schema di risposta"""
    rows = (
        await session.execute(
            text("SELECT chiave, valore FROM configurazione_app"),
        )
    ).all()
    valori: dict[str, object] = {}
    for key, value in rows:
        # Eventuali chiavi non previste dallo schema applicativo vengono ignorate
        if key not in _CHIAVI:
            continue
        valori[key] = str(value) if key == "testo_avviso_disdetta_tardiva" else int(value)
    return ConfigurazioneAppResponse.model_validate(valori)

async def aggiorna_configurazione(session: AsyncSession,configurazione: ConfigurazioneAppRequest) -> ConfigurazioneAppResponse:
    valori = configurazione.model_dump()
    async with write_transaction(session):
        # Vengono salvate tutte le chiavi previste per mantenere la configurazione completa
        for key in _CHIAVI:
            await session.execute(
                text(
                    "INSERT INTO configurazione_app(chiave, valore) "
                    "VALUES(:k, :v) "
                    "ON CONFLICT(chiave) DO UPDATE SET valore=excluded.valore"
                ),
                {"k": key, "v": str(valori[key])},
            )
    return await leggi_configurazione(session)

async def leggi_intero(session: AsyncSession,chiave: str,*,default: int,minimo: int = 0) -> int:
    row = (
        await session.execute(
            text("SELECT valore FROM configurazione_app WHERE chiave = :chiave"),
            {"chiave": chiave},
        )
    ).first()
    # In assenza di un valore utilizzabile viene applicato quanto fornito dal chiamante
    if row is None:
        return default
    try:
        value = int(row[0])
    except (TypeError, ValueError):
        return default
    return value if value >= minimo else default
