from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.appuntamento import SlotPrenotabileResponse
from .._common import APP_TZ, iso_utc as _iso, parse_utc as _parse_dt, utc_now as _now
from .._transaction import write_transaction
from .comune import _config_ore,_get_tipo_utilizzabile,_normalizza_no_tx,_normalizzazioni_pendenti
from .context import AppointmentActor
from ..exceptions import ConflictError, ValidationError

async def _verifica_disponibilita(session: AsyncSession,nutrizionista_id: int,inizio: datetime,fine: datetime) -> None:
    """Verifica che l'appuntamento sia interamente compreso in una fascia di disponibilità del nutrizionista e 
    che inizi a un orario valido della griglia di 15 minuti"""
    local_start = _parse_dt(inizio).astimezone(APP_TZ)
    local_end = _parse_dt(fine).astimezone(APP_TZ)
    # Lo slot deve partire da un minuto esatto e rimanere nello stesso giorno
    if local_start.second or local_start.microsecond:
        raise ValidationError("L’orario di inizio deve essere espresso al minuto")
    if local_start.date() != local_end.date():
        raise ValidationError("Un appuntamento non può attraversare la mezzanotte")
    rows = (
        await session.execute(
            text(
                "SELECT ora_inizio, ora_fine FROM disponibilita "
                "WHERE nutrizionista_id = :nid AND giorno_settimana = :giorno "
                "AND ora_inizio <= :inizio AND ora_fine >= :fine "
                "ORDER BY ora_inizio"
            ),
            {
                "nid": nutrizionista_id,
                "giorno": local_start.weekday(),
                "inizio": local_start.strftime("%H:%M"),
                "fine": local_end.strftime("%H:%M"),
            },
        )
    ).mappings().all()
    if not rows:
        raise ValidationError("Lo slot non rientra nelle disponibilità del nutrizionista")
    
    # Nelle fasce compatibili ne basta una con partenza allineata alla griglia di 15 minuti
    for row in rows:
        fascia_h, fascia_m = map(int, str(row["ora_inizio"]).split(":"))
        fascia_start = datetime.combine(local_start.date(), time(fascia_h, fascia_m), APP_TZ)
        delta_minuti = int((local_start - fascia_start).total_seconds() // 60)
        if delta_minuti >= 0 and delta_minuti % 15 == 0:
            return
    raise ValidationError("L’orario selezionato non rispetta gli slot disponibili")

async def _verifica_slot_libero(session: AsyncSession,nutrizionista_id: int,inizio: datetime,fine: datetime,*,escludi_id: int | None = None) -> None:
    """Verifica che lo slot richiesto non si sovrapponga a indisponibilità o ad altri appuntamenti attivi del nutrizionista"""
    params: dict[str, Any] = {
        "nid": nutrizionista_id,
        "inizio": _iso(inizio),
        "fine": _iso(fine),
    }
    exclusion = ""

    # In caso di spostamento viene escluso l’appuntamento che stiamo verificando
    if escludi_id is not None:
        exclusion = " AND id != :escludi_id"
        params["escludi_id"] = escludi_id

    conflitto = (
        await session.execute(
            text(
                "SELECT 1 FROM indisponibilita WHERE nutrizionista_id = :nid "
                "AND data_ora_inizio < :fine AND data_ora_fine > :inizio "
                "UNION ALL "
                "SELECT 1 FROM appuntamento WHERE nutrizionista_id = :nid "
                "AND stato IN ('P','N','C') "
                "AND data_ora_inizio < :fine AND data_ora_fine > :inizio"
                + exclusion
                + " LIMIT 1"
            ),
            params,
        )
    ).first()
    if conflitto is not None:
        raise ConflictError("L’orario selezionato non è più disponibile.")

async def _valida_slot(session: AsyncSession,*,nutrizionista_id: int,inizio: datetime,fine: datetime) -> None:
    """Combina le verifiche di disponibilità e di slot libero prima di creare/spostare un appuntamento"""
    await _verifica_disponibilita(session, nutrizionista_id, inizio, fine)
    await _verifica_slot_libero(session, nutrizionista_id, inizio, fine)

async def genera_slot_prenotabili(session: AsyncSession,*,actor: AppointmentActor,tipo_appuntamento_id: int,data_da: date) -> list[SlotPrenotabileResponse]:
    """Genera gli slot prenotabili per un dato tipo di appuntamento, su una finestra di 7 giorni a partire da 'data_da'
    Considera le disponibilità del nutrizionista, la durata del tipo di appuntamento, il preavviso minimo e gli slot già occupati o indisponibili"""
    nutrizionista_id = actor.nutrizionista_id
    tipo = await _get_tipo_utilizzabile(session,tipo_id=tipo_appuntamento_id,actor=actor)

    # Prima di generare gli slot vengono eliminati dal blocco agenda le proposte ormai scadute
    if await _normalizzazioni_pendenti(session, nutrizionista_id=nutrizionista_id):
        async with write_transaction(session, immediate=True):
            await _normalizza_no_tx(session, nutrizionista_id=nutrizionista_id)
    ore_risposta, ore_annullamento = await _config_ore(session)

    # Il primo slot utile deve lasciare il tempo previsto per risposta ed eventuale annullamento
    minimo = _now() + timedelta(hours=ore_risposta + ore_annullamento)
    durata = timedelta(minutes=tipo.durata)
    end_date = data_da + timedelta(days=7)

    fasce = (
        await session.execute(
            text(
                "SELECT giorno_settimana, ora_inizio, ora_fine FROM disponibilita "
                "WHERE nutrizionista_id = :nid ORDER BY giorno_settimana, ora_inizio"
            ),
            {"nid": nutrizionista_id},
        )
    ).mappings().all()
    by_day: dict[int, list[tuple[str, str]]] = {}
    for row in fasce:
        by_day.setdefault(int(row["giorno_settimana"]), []).append(
            (str(row["ora_inizio"]), str(row["ora_fine"]))
        )

    range_start = datetime.combine(data_da, time.min, APP_TZ).astimezone(timezone.utc)
    range_end = datetime.combine(end_date, time.min, APP_TZ).astimezone(timezone.utc)

    indisponibilita = (
        await session.execute(
            text(
                "SELECT data_ora_inizio, data_ora_fine FROM indisponibilita "
                "WHERE nutrizionista_id = :nid AND data_ora_inizio < :fine "
                "AND data_ora_fine > :inizio"
            ),
            {"nid": nutrizionista_id, "inizio": _iso(range_start), "fine": _iso(range_end)},
        )
    ).mappings().all()

    bloccanti = (
        await session.execute(
            text(
                "SELECT data_ora_inizio, data_ora_fine FROM appuntamento "
                "WHERE nutrizionista_id = :nid AND stato IN ('P','N','C') "
                "AND data_ora_inizio < :fine AND data_ora_fine > :inizio"
            ),
            {"nid": nutrizionista_id, "inizio": _iso(range_start), "fine": _iso(range_end)},
        )
    ).mappings().all()

    # Indisponibilità e appuntamenti attivi concorrono allo stesso insieme di intervalli occupati
    busy = [
        (_parse_dt(row["data_ora_inizio"]), _parse_dt(row["data_ora_fine"]))
        for row in [*indisponibilita, *bloccanti]
    ]

    # Si scorre ogni fascia a passi di 15 minuti e vengono mantenuti solo gli intervalli realmente liberi
    slots: list[SlotPrenotabileResponse] = []
    for offset in range(7):
        day = data_da + timedelta(days=offset)
        for start_hm, end_hm in by_day.get(day.weekday(), []):
            sh, sm = map(int, start_hm.split(":"))
            eh, em = map(int, end_hm.split(":"))
            cursor_local = datetime.combine(day, time(sh, sm), APP_TZ)
            fascia_end_local = datetime.combine(day, time(eh, em), APP_TZ)
            while cursor_local + durata <= fascia_end_local:
                end_local = cursor_local + durata
                start_utc = cursor_local.astimezone(timezone.utc)
                end_utc = end_local.astimezone(timezone.utc)
                if start_utc >= minimo and cursor_local.date() == end_local.date():
                    overlap = any(a < end_utc and b > start_utc for a, b in busy)
                    if not overlap:
                        slots.append(
                            SlotPrenotabileResponse(
                                data_ora_inizio=cursor_local,
                                data_ora_fine=end_local,
                            )
                        )
                cursor_local += timedelta(minutes=15)
    return sorted(slots, key=lambda item: item.data_ora_inizio)
