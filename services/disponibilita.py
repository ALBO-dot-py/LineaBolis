from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.disponibilita import DisponibilitaCreate,DisponibilitaRead,IndisponibilitaCreate,IndisponibilitaRead
from ._common import APP_TZ, iso_utc as _iso, parse_utc as _parse_dt, require, utc_now as _now
from ._repo import get_owned as _repo_get_owned
from ._transaction import write_transaction
from .appuntamenti.comune import _normalizza_no_tx
from .exceptions import ConflictError, ValidationError

async def _get_owned(session: AsyncSession, table: str, row_id: int, nutrizionista_id: int) -> dict[str, Any]:
    """Carica una disponibilità o indisponibilità posseduta dal nutrizionista"""
    resource = "Disponibilita" if table == "disponibilita" else "Indisponibilita"
    return await _repo_get_owned(session,table,row_id,owner_field="nutrizionista_id",owner_id=nutrizionista_id,whitelist={"disponibilita", "indisponibilita"},resource_name=resource,hide_unauthorized=True)

async def _blocking_appointments(session: AsyncSession,nutrizionista_id: int,*,start: datetime | None = None,end: datetime | None = None) -> list[dict[str, Any]]:
    """Restituisce gli appuntamenti futuri o in corso che bloccano l'agenda, eventualmente limitati a un intervallo"""
    sql = (
        "SELECT a.id, a.paziente_id, "
        "trim(coalesce(u.nome,'') || ' ' || coalesce(u.cognome,'')) AS paziente_nome, "
        "a.stato, a.data_ora_inizio, a.data_ora_fine, a.nome AS tipo "
        "FROM appuntamento a LEFT JOIN utente u ON u.id=a.paziente_id "
        "WHERE a.nutrizionista_id=:nid AND a.stato IN ('P','N','C') "
        "AND a.data_ora_fine>:adesso "
    )
    params: dict[str, Any] = {"nid": nutrizionista_id, "adesso": _iso(_now())}
    # Se richiesto, vengono restituiti soltanto gli appuntamenti sovrapposti all'intervallo indicato
    if start is not None and end is not None:
        sql += "AND a.data_ora_inizio<:fine AND a.data_ora_fine>:inizio "
        params.update({"inizio": _iso(start), "fine": _iso(end)})
    sql += "ORDER BY a.data_ora_inizio, a.id"
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]

def _rientra_nella_fascia_ricorrente(appuntamento: dict[str, Any], disponibilita: dict[str, Any]) -> bool:
    """Verifica se l'appuntamento è contenuto nella fascia ricorrente indicata"""
    start = _parse_dt(appuntamento["data_ora_inizio"]).astimezone(APP_TZ)
    end = _parse_dt(appuntamento["data_ora_fine"]).astimezone(APP_TZ)
    if start.date() != end.date():
        return False
    return (
        start.weekday() == int(disponibilita["giorno_settimana"])
        and str(disponibilita["ora_inizio"]) <= start.strftime("%H:%M")
        and str(disponibilita["ora_fine"]) >= end.strftime("%H:%M")
    )

async def crea_disponibilita(
    session: AsyncSession,*,nutrizionista_id: int,dati: DisponibilitaCreate) -> DisponibilitaRead:
    """Crea una fascia ricorrente (le fasce esattamente adiacenti vengono unite)"""
    async with write_transaction(session, immediate=True):
        existing = (
            await session.execute(
                text(
                    "SELECT * FROM disponibilita "
                    "WHERE nutrizionista_id=:nid AND giorno_settimana=:giorno "
                    "ORDER BY ora_inizio, id"
                ),
                {"nid": nutrizionista_id, "giorno": dati.giorno_settimana},
            )
        ).mappings().all()
        # Una nuova fascia non può sovrapporsi a quelle già configurate nello stesso giorno
        if any(
            str(row["ora_inizio"]) < dati.ora_fine
            and str(row["ora_fine"]) > dati.ora_inizio
            for row in existing
        ):
            raise ConflictError("Le fasce di disponibilità non possono sovrapporsi")
        # Le fasce adiacenti vengono unite in un unico intervallo continuo
        left = next(
            (row for row in existing if str(row["ora_fine"]) == dati.ora_inizio),
            None,
        )
        right = next(
            (row for row in existing if str(row["ora_inizio"]) == dati.ora_fine),
            None,
        )
        if left is not None:
            final_end = str(right["ora_fine"]) if right is not None else dati.ora_fine
            if right is not None:
                await session.execute(
                    text("DELETE FROM disponibilita WHERE id=:id"),
                    {"id": int(right["id"])},
                )
            row = (
                await session.execute(
                    text(
                        "UPDATE disponibilita SET ora_fine=:fine "
                        "WHERE id=:id RETURNING *"
                    ),
                    {"id": int(left["id"]), "fine": final_end},
                )
            ).mappings().first()
        elif right is not None:
            row = (
                await session.execute(
                    text(
                        "UPDATE disponibilita SET ora_inizio=:inizio "
                        "WHERE id=:id RETURNING *"
                    ),
                    {"id": int(right["id"]), "inizio": dati.ora_inizio},
                )
            ).mappings().first()
        else:
            row = (
                await session.execute(
                    text(
                        "INSERT INTO disponibilita "
                        "(nutrizionista_id,giorno_settimana,ora_inizio,ora_fine) "
                        "VALUES(:nid,:giorno,:inizio,:fine) RETURNING *"
                    ),
                    {
                        "nid": nutrizionista_id,
                        "giorno": dati.giorno_settimana,
                        "inizio": dati.ora_inizio,
                        "fine": dati.ora_fine,
                    },
                )
            ).mappings().first()
        return DisponibilitaRead.model_validate(dict(require(row, "Errore durante il salvataggio delle disponibilità")))

async def lista_disponibilita(session: AsyncSession, *, nutrizionista_id: int) -> list[DisponibilitaRead]:
    """Elenca tutte le disponibilità, ordinate per giorno e orario"""
    rows = (
        await session.execute(
            text(
                "SELECT * FROM disponibilita WHERE nutrizionista_id=:nid "
                "ORDER BY giorno_settimana, ora_inizio, id"
            ),
            {"nid": nutrizionista_id},
        )
    ).mappings().all()
    return [DisponibilitaRead.model_validate(dict(row)) for row in rows]

async def elimina_disponibilita(session: AsyncSession, *, disp_id: int, nutrizionista_id: int) -> None:
    """Elimina una fascia ricorrente se non contiene appuntamenti futuri ancora attivi"""
    async with write_transaction(session, immediate=True):
        current = await _get_owned(session, "disponibilita", disp_id, nutrizionista_id)
        await _normalizza_no_tx(session, nutrizionista_id=nutrizionista_id)
        # Non viene eliminata una fascia se sono scoperti appuntamenti ancora attivi
        conflicts = [
            row
            for row in await _blocking_appointments(session, nutrizionista_id)
            if _rientra_nella_fascia_ricorrente(row, current)
        ]
        if conflicts:
            raise ConflictError("La modifica lascerebbe scoperti appuntamenti ancora da gestire o effettuare",details=conflicts)
        await session.execute(
            text("DELETE FROM disponibilita WHERE id=:id AND nutrizionista_id=:nid"),
            {"id": disp_id, "nid": nutrizionista_id},
        )

async def crea_indisponibilita(session: AsyncSession,*,nutrizionista_id: int,dati: IndisponibilitaCreate) -> IndisponibilitaRead:
    """Crea un periodo di indisponibilità per il nutrizionista, ma solo se in quell’intervallo non ci sono appuntamenti ancora da gestire"""
    start = _parse_dt(dati.data_ora_inizio)
    end = _parse_dt(dati.data_ora_fine)
    # Un blocco agenda deve avere almeno una parte ancora futura
    if end <= _now():
        raise ValidationError("Non è possibile creare un’indisponibilità già terminata")

    async with write_transaction(session, immediate=True):
        await _normalizza_no_tx(session, nutrizionista_id=nutrizionista_id)
        # Prima di bloccare il periodo viene verificata l'assenza di appuntamenti da gestire
        conflicts = await _blocking_appointments(session,nutrizionista_id,start=start,end=end)
        if conflicts:
            raise ConflictError("Prima di bloccare il periodo, gestire gli appuntamenti sovrapposti",details=conflicts)
        row = (
            await session.execute(
                text(
                    "INSERT INTO indisponibilita "
                    "(nutrizionista_id,data_ora_inizio,data_ora_fine,motivo) "
                    "VALUES(:nid,:inizio,:fine,:motivo) RETURNING *"
                ),
                {
                    "nid": nutrizionista_id,
                    "inizio": _iso(start),
                    "fine": _iso(end),
                    "motivo": dati.motivo,
                },
            )
        ).mappings().first()
        return IndisponibilitaRead.model_validate(dict(require(row, "Errore durante la creazione dell'indisponibilità")))

async def lista_indisponibilita(session: AsyncSession, *, nutrizionista_id: int) -> list[IndisponibilitaRead]:
    """Elenca le indisponibilità attive o future"""
    rows = (
        await session.execute(
            text(
                "SELECT * FROM indisponibilita "
                "WHERE nutrizionista_id=:nid AND data_ora_fine>:adesso "
                "ORDER BY data_ora_inizio, id"
            ),
            {"nid": nutrizionista_id, "adesso": _iso(_now())},
        )
    ).mappings().all()
    return [IndisponibilitaRead.model_validate(dict(row)) for row in rows]

async def elimina_indisponibilita(session: AsyncSession, *, indisp_id: int, nutrizionista_id: int) -> None:
    """Elimina un'indisponibilità"""
    async with write_transaction(session):
        await _get_owned(session, "indisponibilita", indisp_id, nutrizionista_id)
        await session.execute(
            text("DELETE FROM indisponibilita WHERE id=:id AND nutrizionista_id=:nid"),
            {"id": indisp_id, "nid": nutrizionista_id},
        )