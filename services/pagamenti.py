from datetime import datetime, timedelta
from typing import Any, Literal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.pagamento import PagamentoPanelRead, PagamentoRead, PagamentoSezioneRead, PagamentoStatisticheRead
from ._common import APP_TZ, iso_utc, month_start, parse_utc, utc_now
from ._transaction import write_transaction
from .exceptions import ConflictError, NotFoundError, ValidationError

OwnerField = Literal["nutrizionista_id", "paziente_id"]
_SELECT = """
SELECT a.id AS appuntamento_id, a.prezzo_cent, a.sconto_cent, a.pagato_at,
       a.stato AS appuntamento_stato, a.nome AS appuntamento_tipo_nome,
       a.data_ora_inizio AS appuntamento_data_ora_inizio,
       trim(pu.nome || ' ' || pu.cognome) AS paziente_nome
FROM appuntamento a
JOIN utente pu ON pu.id = a.paziente_id
"""

def _bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Restituisce in timezone l’inizio del giorno corrente e il limite del giorno successivo"""
    start = (now or utc_now()).astimezone(APP_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)

def stato_pagamento(row: dict[str, Any], now: datetime | None = None) -> str | None:
    """Determina se un appuntamento risulta pagato, incassabile oggi, scaduto oppure non ancora di interesse per i pagamenti"""
    if row.get("pagato_at"):
        return "pagato"
    start, end = _bounds(now)
    when = parse_utc(row["appuntamento_data_ora_inizio"])
    # Gli appuntamenti di oggi sono incassabili se confermati o già eseguiti
    if start <= when < end and row["appuntamento_stato"] in {"C", "E"}:
        return "oggi"
    return "scaduto" if when < start and row["appuntamento_stato"] == "E" else None

def _read(row: dict[str, Any], status: str, now: datetime) -> PagamentoRead:
    """Converte una riga appuntamento nel DTO di pagamento, calcolando anche gli eventuali giorni di ritardo"""
    days = 0
    if status == "scaduto":
        today, _ = _bounds(now)
        when = parse_utc(row["appuntamento_data_ora_inizio"]).astimezone(APP_TZ)
        days = max(0, (today.date() - when.date()).days)
    return PagamentoRead.model_validate({
        **row,
        "totale_cent": int(row["prezzo_cent"]) - int(row["sconto_cent"]),
        "giorni_scaduto": days,
    })

def _section(items: list[PagamentoRead]) -> PagamentoSezioneRead:
    """Raggruppa i pagamenti in una sezione comprendente conteggio e totale"""
    return PagamentoSezioneRead(items=items, count=len(items), totale_cent=sum(item.totale_cent for item in items))

async def _rows(session: AsyncSession, owner: OwnerField, owner_id: int, paziente_id: int | None = None) -> list[dict[str, Any]]:
    """Carica gli appuntamenti per il nutrizionista loggato"""
    sql, params = _SELECT + f" WHERE a.{owner} = :owner_id", {"owner_id": owner_id}
    if paziente_id:
        sql += " AND a.paziente_id = :paziente_id"
        params["paziente_id"] = paziente_id
    return [dict(row) for row in (await session.execute(text(sql), params)).mappings()]

def _panel(rows: list[dict[str, Any]], now: datetime, with_stats: bool = False) -> PagamentoPanelRead:
    """
    Costruisce il pannello pagamenti (distinti quelli aperti e quelli già pagati)
    -'with_stats=True' calcola anche indicatori giornalieri e aggregati degli ultimi sei mesi
    """
    open_items: list[PagamentoRead] = []
    paid_items: list[PagamentoRead] = []

    # Le statistiche aggregate sono necessarie nel pannello generale del nutrizionista
    if with_stats:
        today, _ = _bounds(now)
        months = [month_start(now, offset) for offset in range(-5, 2)]
        labels = [month.strftime("%Y-%m") for month in months[:6]]
        revenue = dict.fromkeys(labels, 0)
        today_count = today_total = overdue_count = overdue_total = paid_6m = pending_6m = 0

    # Separati gli appuntamenti già pagati da quelli non ancora incassati
    for row in rows:
        status = stato_pagamento(row, now)
        if status:
            item = _read(row, status, now)
            (paid_items if status == "pagato" else open_items).append(item)
        if not with_stats:
            continue
        amount = int(row["prezzo_cent"]) - int(row["sconto_cent"])
        when = parse_utc(row["appuntamento_data_ora_inizio"]).astimezone(APP_TZ)
        if status == "oggi":
            today_count, today_total = today_count + 1, today_total + amount
        elif status == "scaduto":
            overdue_count, overdue_total = overdue_count + 1, overdue_total + amount
            pending_6m += months[0] <= when < today
        if row["pagato_at"]:
            paid_at = parse_utc(row["pagato_at"]).astimezone(APP_TZ)
            if months[0] <= paid_at < months[6]:
                paid_6m += 1
                revenue[paid_at.strftime("%Y-%m")] += amount

    open_items.sort(key=lambda item: item.appuntamento_data_ora_inizio)
    paid_items.sort(key=lambda item: item.pagato_at, reverse=True)
    stats = PagamentoStatisticheRead(
        da_incassare_oggi={"count": today_count, "totale_cent": today_total},
        in_sospeso={"count": overdue_count, "totale_cent": overdue_total},
        pagati_ultimi_6_mesi=paid_6m,
        in_sospeso_ultimi_6_mesi=pending_6m,
        incassi_ultimi_6_mesi=[{"mese": label, "totale_cent": revenue[label]} for label in labels],
    ) if with_stats else None
    return PagamentoPanelRead(aperti=_section(open_items), pagati=_section(paid_items), statistiche=stats)

async def pannello_nutrizionista(session: AsyncSession, *, nutrizionista_id: int, paziente_id: int | None = None) -> PagamentoPanelRead:
    """
    Restituito il pannello pagamenti del nutrizionista (filtrabile per paziente)
    -'paziente_id' valorizzato, vengono incluse le statistiche aggregate
    """
    now = utc_now().astimezone(APP_TZ)
    rows = await _rows(session, "nutrizionista_id", nutrizionista_id, paziente_id)
    return _panel(rows, now, with_stats=paziente_id is None)

async def pannello_paziente(session: AsyncSession, *, paziente_id: int) -> PagamentoPanelRead:
    """Restituisce al paziente il proprio pannello con pagamenti aperti e già registrati"""
    now = utc_now().astimezone(APP_TZ)
    return _panel(await _rows(session, "paziente_id", paziente_id), now)

async def registra_pagamento(session: AsyncSession, *, appuntamento_id: int, nutrizionista_id: int, sconto_cent: int) -> PagamentoRead:
    """Registra pagamento e sconto di un appuntamento incassabile, verificando eventuali duplicati o sconti superiori al prezzo"""
    async with write_transaction(session, immediate=True):
        row = (await session.execute(text(
            _SELECT + " WHERE a.id = :id AND a.nutrizionista_id = :nutrizionista_id"
        ), {"id": appuntamento_id, "nutrizionista_id": nutrizionista_id})).mappings().first()
        if row is None:
            raise NotFoundError("Appuntamento", appuntamento_id)
        current = dict(row)
        # Il pagamento è consentito solo quando l’appuntamento è già incassabile
        status = stato_pagamento(current)
        if status == "pagato":
            raise ConflictError("Pagamento già registrato")
        if status not in {"oggi", "scaduto"}:
            raise ValidationError("Pagamento non ancora registrabile")
        # Lo sconto non può produrre un totale negativo
        if sconto_cent > int(current["prezzo_cent"]):
            raise ValidationError("Lo sconto non può superare il prezzo")
        paid_at = iso_utc(utc_now())
        await session.execute(text(
            "UPDATE appuntamento SET sconto_cent = :sconto, pagato_at = :pagato_at WHERE id = :id"
        ), {"sconto": sconto_cent, "pagato_at": paid_at, "id": appuntamento_id})
    return _read({**current, "sconto_cent": sconto_cent, "pagato_at": paid_at}, "pagato", utc_now())
