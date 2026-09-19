from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ._common import require
from ._repo import get_by_id
from ._transaction import write_transaction
from schemas.enums import Ruolo, StatoUtente
from schemas.profilo import ProfiloNutrizionistaRead
from schemas.utente import UtenteBase, UtenteRead
from . import utenti as svc_utenti
from .exceptions import ConflictError, NotFoundError, ValidationError

_READ_TABLES = {"utente", "profilo_nutrizionista"}

## Helper
async def _get_nutrizionista_row(session: AsyncSession,utente_id: int) -> dict[str, Any] | None:
    """Recupera l'utente soltanto se possiede il ruolo nutrizionista oppure None"""
    row = await get_by_id(session, "utente", utente_id, whitelist=_READ_TABLES)
    if row is None or row.get("ruolo") != Ruolo.nutrizionista.value:
        return None
    return row

async def _require_nutrizionista(session: AsyncSession,utente_id: int) -> dict[str, Any]:
    """Recupera il nutrizionista o solleva NotFoundError"""
    row = await _get_nutrizionista_row(session, utente_id)
    if row is None:
        raise NotFoundError("Nutrizionista", utente_id)
    return row

async def imposta_stato_nutrizionista(session: AsyncSession,*,utente_id: int,stato: StatoUtente) -> UtenteRead:
    """Abilita o disabilita il nutrizionista"""
    async with write_transaction(session):
        await _require_nutrizionista(session, utente_id)
        row = await svc_utenti.imposta_stato_utente(session,utente_id=utente_id,nuovo_stato=stato)
        return svc_utenti._to_read(row)

## Servizi Pubblico
async def crea_nutrizionista(session: AsyncSession,*,nome: str,cognome: str,email: str,telefono: str | None = None,base_url: str) -> dict[str, Any]:
    """Crea un nuovo nutrizionista disattivato e genera il link per impostare la password"""
    utente = UtenteBase(nome=nome,cognome=cognome,email=email,telefono=telefono,ruolo=Ruolo.nutrizionista,stato=StatoUtente.disattivo)
    valori = utente.to_sqlite_dict(exclude_unset=False)
    email_norm = valori["email"]
    valori["pwd"] = svc_utenti.hash_password_casuale()

    async with write_transaction(session):
        # L’email deve essere libera prima di creare utente e profilo del nutrizionista
        if await svc_utenti._email_esistente(session, email_norm):
            raise ConflictError()
        result = await session.execute(
            text(
                "INSERT INTO utente "
                "(nome, cognome, email, telefono, ruolo, pwd, stato) "
                "VALUES (:nome, :cognome, :email, :telefono, :ruolo, :pwd, :stato)"
            ),
            valori,
        )
        utente_id = int(result.lastrowid)

        await session.execute(
            text(
                "INSERT INTO profilo_nutrizionista (utente_id) VALUES (:uid)"
            ),
            {"uid": utente_id},
        )
        url_impostazione_password = await svc_utenti.genera_link_password(session, utente_id=utente_id, base_url=base_url)

        utente_row = await get_by_id(session,"utente",utente_id,whitelist=_READ_TABLES)
        profilo_row = await get_by_id(session,"profilo_nutrizionista",utente_id,whitelist=_READ_TABLES,id_field="utente_id")

    utente_row = require(utente_row, "Utente nutrizionista non trovato dopo la creazione")
    profilo_row = require(profilo_row, "Profilo nutrizionista non trovato dopo la creazione")
    return {
        "utente": svc_utenti._to_read(utente_row),
        "profilo": ProfiloNutrizionistaRead.model_validate(profilo_row),
        "url_impostazione_password": url_impostazione_password,
    }

async def lista_nutrizionisti(session: AsyncSession,*,ricerca: str | None = None,stato: StatoUtente | None = None,skip: int = 0,limit: int = 50) -> list[dict[str, Any]]:
    """Restituisce i nutrizionisti e, per ciascuno, mostra il numero dei propri pazienti attivi"""
    sql = (
        "SELECT u.*, COUNT(CASE WHEN p.stato = 'A' THEN 1 END) AS numero_pazienti_attivi "
        "FROM utente u "
        "LEFT JOIN profilo_paziente pp ON pp.nutrizionista_id = u.id "
        "LEFT JOIN utente p ON p.id = pp.utente_id AND p.ruolo = 'P' "
        "WHERE u.ruolo = :ruolo"
    )
    params: dict[str, Any] = {"ruolo": Ruolo.nutrizionista.value}

    if stato is not None:
        sql += " AND u.stato = :stato"
        params["stato"] = stato.value
    if ricerca and (ricerca := ricerca.strip()):
        sql += " AND (u.nome LIKE :q OR u.cognome LIKE :q OR u.email LIKE :q)"
        params["q"] = f"%{ricerca}%"

    sql += " GROUP BY u.id ORDER BY u.cognome, u.nome LIMIT :limit OFFSET :skip"
    params.update(limit=limit, skip=skip)
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [
        {
            "utente": svc_utenti._to_read(dict(row)),
            "numero_pazienti_attivi": int(row["numero_pazienti_attivi"] or 0),
        }
        for row in rows
    ]

async def aggiorna_anagrafica_nutrizionista(session: AsyncSession,*,utente_id: int,**aggiornamenti: Any) -> UtenteRead:
    """Aggiorna l'anagrafica di un nutrizionista"""
    consentiti = {"nome", "cognome", "email", "telefono"}
    if sconosciuti := aggiornamenti.keys() - consentiti:
        campo = next(iter(sconosciuti))
        raise TypeError(
            "aggiorna_anagrafica_nutrizionista() got an unexpected "
            f"keyword argument '{campo}'"
        )

    async with write_transaction(session):
        await _require_nutrizionista(session, utente_id)
        row = await svc_utenti._aggiorna_utente_senza_commit(session,utente_id=utente_id,aggiornamenti=aggiornamenti)
        return svc_utenti._to_read(row)

async def disabilita_nutrizionista(session: AsyncSession,*,utente_id: int) -> UtenteRead:
    """Disattiva il nutrizionist SOLO SE non ha pazienti assegnati"""
    async with write_transaction(session):
        await _require_nutrizionista(session, utente_id)

        # Un nutrizionista con pazienti ancora assegnati non può essere disattivato
        count = int((await session.execute(
            text("SELECT COUNT(*) FROM profilo_paziente WHERE nutrizionista_id=:id"),
            {"id": utente_id},
        )).scalar_one())

        if count:
            raise ValidationError("Impossibile disattivare in quanto risultano assegnati ancora dei pazienti assegnati")

        row = await svc_utenti.imposta_stato_utente(session,utente_id=utente_id,nuovo_stato=StatoUtente.disattivo)
        return svc_utenti._to_read(row)

async def logout_all_nutrizionista(session: AsyncSession,*,utente_id: int) -> None:
    """Revoca tutte le sessioni del nutrizionista"""
    async with write_transaction(session):
        await _require_nutrizionista(session, utente_id)
        await svc_utenti.revoca_sessioni_utente(session, utente_id)

async def genera_link_impostazione_password_nutrizionista(session: AsyncSession,*,utente_id: int,base_url: str) -> str:
    """Disattiva il nutrizionista e genera un nuovo link monouso"""
    async with write_transaction(session, immediate=True):
        await _require_nutrizionista(session, utente_id)
        return await svc_utenti.genera_link_password(session,utente_id=utente_id,base_url=base_url)
