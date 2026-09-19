from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.appuntamento import StatisticaEsitiMensiliRead
from .._common import APP_TZ, iso_utc, month_start, parse_utc, utc_now

async def esiti_ultimi_6_mesi(
    session: AsyncSession, *, nutrizionista_id: int
) -> list[StatisticaEsitiMensiliRead]:
    """Conteggia per mese gli appuntamenti effettuati e gli esiti negativi"""
    now = utc_now().astimezone(APP_TZ)
    months = [month_start(now, offset) for offset in range(-5, 2)]
    labels = [month.strftime("%Y-%m") for month in months[:6]]

    # Vengono preparati tutti i mesi, anche quelli senza appuntamenti, per ottenere una serie continua
    counts = {
        label: {"effettuati": 0, "assenze_disdette": 0}
        for label in labels
    }
    rows = (await session.execute(text(
        "SELECT data_ora_inizio, stato FROM appuntamento "
        "WHERE nutrizionista_id = :id AND stato IN ('E', 'M', 'T') "
        "AND data_ora_inizio >= :start AND data_ora_inizio < :end"
    ), {
        "id": nutrizionista_id,
        "start": iso_utc(months[0]),
        "end": iso_utc(months[6]),
    })).mappings()

    # Ogni esito viene ricondotto al mese locale in cui era previsto l’appuntamento
    for row in rows:
        label = parse_utc(row["data_ora_inizio"]).astimezone(APP_TZ).strftime("%Y-%m")
        if row["stato"] == "E":
            counts[label]["effettuati"] += 1
        else:
            counts[label]["assenze_disdette"] += 1

    return [
        StatisticaEsitiMensiliRead(mese=label, **counts[label])
        for label in labels
    ]
