from datetime import date, datetime
from ._common import APP_TZ
from functools import partial
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ._repo import get_by_id, update_by_id
from ._ownership import verifica_appartenenza_paziente as _verifica_ownership
from ._transaction import write_transaction
from schemas.enums import Ruolo, Sesso, StatoUtente
from schemas.profilo import ProfiloPazienteRead
from schemas.utente import UtenteRead
from . import utenti as svc_utenti
from .exceptions import ConflictError, NotFoundError, ValidationError

_UNSET = object()

_READ_TABLES = {"utente", "profilo_paziente"}
_UPDATE_TABLES = {"profilo_paziente"}
_get_utente = partial(get_by_id, table="utente", whitelist=_READ_TABLES)
_get_profilo = partial(get_by_id,table="profilo_paziente",whitelist=_READ_TABLES,id_field="utente_id")
_update_profilo = partial(update_by_id,table="profilo_paziente",whitelist=_UPDATE_TABLES,id_field="utente_id")

## Helper
async def _get_paziente_row(session: AsyncSession,paziente_id: int) -> dict[str, Any] | None:
    """Recupera l'utente soltanto se possiede il ruolo paziente oppure None"""
    row = await _get_utente(session, row_id=paziente_id)
    if row is None or row.get("ruolo") != Ruolo.paziente.value:
        return None
    return row

async def _verifica_nutrizionista_esiste(session: AsyncSession,nutrizionista_id: int) -> None:
    """Verifica che il nutrizionista esista e sia attivo"""
    result = await session.execute(
        text(
            "SELECT 1 FROM utente u "
            "JOIN profilo_nutrizionista pn ON pn.utente_id = u.id "
            "WHERE u.id = :id AND u.ruolo = 'N' AND u.stato = 'A'"
        ),
        {"id": nutrizionista_id},
    )
    if result.first() is None:
        raise NotFoundError("Nutrizionista", nutrizionista_id)

async def _codice_fiscale_esistente(session: AsyncSession,codice_fiscale: str,escludi_id: int | None = None) -> bool:
    """Verifica l'unicità del codice fiscale"""
    sql = (
        "SELECT 1 FROM profilo_paziente "
        "WHERE codice_fiscale = :cf COLLATE NOCASE"
    )
    params: dict[str, Any] = {"cf": codice_fiscale.strip().upper()}
    if escludi_id is not None:
        sql += " AND utente_id != :escludi_id"
        params["escludi_id"] = escludi_id
    return (await session.execute(text(sql), params)).first() is not None

def _profilo_read(row: dict[str, Any]) -> ProfiloPazienteRead:
    """Converte la riga del profilo paziente nel relativo schema"""
    return ProfiloPazienteRead.model_validate(row)

async def _leggi_utente_e_profilo(session: AsyncSession,paziente_id: int) -> dict[str, Any]:
    """Recupera utente e profilo del paziente già convertiti negli schemi"""
    utente_row = await _get_utente(session, row_id=paziente_id)
    profilo_row = await _get_profilo(session, row_id=paziente_id)
    if utente_row is None or profilo_row is None:
        raise NotFoundError("Risorsa non disponibile")
    return {
        "utente": svc_utenti._to_read(utente_row),
        "profilo": _profilo_read(profilo_row),
    }


## Servizi pubblici
async def crea_paziente(session: AsyncSession,*,nome: str,cognome: str,email: str,telefono: str | None,nutrizionista_id: int,data_nascita: date,sesso: Sesso,codice_fiscale: str | None = None,peso_obiettivo_kg: float | None = None,note_nutrizionista: str | None = None,base_url: str) -> dict[str, Any]:
    """Crea un nuovo paziente disattivato e genera il link per impostare la password"""
    email_norm = email.strip().lower()
    cf_norm = codice_fiscale.strip().upper() if codice_fiscale else None
    pwd_hash = svc_utenti.hash_password_casuale()
    
    async with write_transaction(session):
        # Prima della creazione viene verificata esistenza nutrizionista e i dati del futuro paziente
        await _verifica_nutrizionista_esiste(session, nutrizionista_id)
        if await svc_utenti._email_esistente(session, email_norm):
            raise ConflictError()
        if cf_norm and await _codice_fiscale_esistente(session, cf_norm):
            raise ConflictError()
        result = await session.execute(
            text(
                "INSERT INTO utente "
                "(nome, cognome, email, telefono, ruolo, pwd, stato) "
                "VALUES (:nome, :cognome, :email, :telefono, 'P', :pwd, 'D')"
            ),
            {
                "nome": nome.strip(),
                "cognome": cognome.strip(),
                "email": email_norm,
                "telefono": telefono,
                "pwd": pwd_hash,
            },
        )
        paziente_id = int(result.lastrowid)
        # Utente e profilo paziente vengono creati nella stessa operazione
        await session.execute(
            text(
                "INSERT INTO profilo_paziente "
                "(utente_id, nutrizionista_id, codice_fiscale, data_nascita, sesso, "
                " peso_obiettivo_kg, note_nutrizionista) "
                "VALUES (:uid, :nid, :cf, :data_nascita, :sesso, :peso, :nn)"
            ),
            {
                "uid": paziente_id,
                "nid": nutrizionista_id,
                "cf": cf_norm,
                "data_nascita": data_nascita.isoformat(),
                "sesso": sesso.value,
                "peso": peso_obiettivo_kg,
                "nn": note_nutrizionista,
            },
        )
        url_impostazione_password = await svc_utenti.genera_link_password(session, utente_id=paziente_id, base_url=base_url)
    dati = await _leggi_utente_e_profilo(session, paziente_id)
    return {**dati, "url_impostazione_password": url_impostazione_password}

async def leggi_paziente(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int) -> dict[str, Any]:
    """Restituisce utente e profilo del paziente (SE assegnato al nutrizionista)"""
    await _verifica_ownership(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
    return await _leggi_utente_e_profilo(session, paziente_id)


async def lista_pazienti(session: AsyncSession,*,nutrizionista_id: int,includi_disabilitati: bool = False,cerca: str | None = None,skip: int = 0,limit: int = 50) -> list[dict[str, Any]]:
    """Restituisce l'elenco paginato dei pazienti del nutrizionista"""
    sql = (
        "SELECT "
        "u.id, u.nome, u.cognome, u.email, u.telefono, u.ruolo, "
        "u.stato, u.last_login_at, "
        "pp.utente_id, pp.nutrizionista_id, pp.codice_fiscale, pp.data_nascita, "
        "pp.sesso, pp.peso_obiettivo_kg, pp.note_nutrizionista "
        "FROM utente u JOIN profilo_paziente pp ON pp.utente_id = u.id "
        "WHERE pp.nutrizionista_id = :nid AND u.ruolo = 'P'"
    )
    params: dict[str, Any] = {"nid": nutrizionista_id, "limit": limit, "skip": skip}
    if not includi_disabilitati:
        sql += " AND u.stato = 'A'"
    if cerca and cerca.strip():
        sql += (
            " AND (lower(u.nome) LIKE :cerca "
            "OR lower(u.cognome) LIKE :cerca "
            "OR lower(u.nome || ' ' || u.cognome) LIKE :cerca "
            "OR lower(u.cognome || ' ' || u.nome) LIKE :cerca)"
        )
        params["cerca"] = f"%{cerca.strip().lower()}%"
    sql += " ORDER BY u.cognome, u.nome LIMIT :limit OFFSET :skip"

    rows = (await session.execute(text(sql), params)).mappings().all()

    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        # Ricostruiti i dizionari separati per utente e profilo rinominando i campi con il loro nome originale
        utente = {
            "id": row["id"],
            "nome": row["nome"],
            "cognome": row["cognome"],
            "email": row["email"],
            "telefono": row["telefono"],
            "ruolo": row["ruolo"],
            "stato": row["stato"],
            "last_login_at": row["last_login_at"],
        }
        profilo = {
            "utente_id": row["utente_id"],
            "nutrizionista_id": row["nutrizionista_id"],
            "codice_fiscale": row["codice_fiscale"],
            "data_nascita": row["data_nascita"],
            "sesso": row["sesso"],
            "peso_obiettivo_kg": row["peso_obiettivo_kg"],
            "note_nutrizionista": row["note_nutrizionista"],
        }
        output.append(
            {
                "utente": UtenteRead.model_validate(utente),
                "profilo": ProfiloPazienteRead.model_validate(profilo),
            }
        )
    return output

async def aggiorna_paziente(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int,nome: str | object = _UNSET,cognome: str | object = _UNSET,email: str | object = _UNSET,telefono: str | None | object = _UNSET,codice_fiscale: str | None | object = _UNSET,data_nascita: date | object = _UNSET,sesso: Sesso | object = _UNSET,peso_obiettivo_kg: float | None | object = _UNSET,note_nutrizionista: str | None | object = _UNSET) -> dict[str, Any]:
    """Aggiorna parzialmente utente e/o profilo del paziente"""
    async with write_transaction(session):
        await _verifica_ownership(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
        if await _get_paziente_row(session, paziente_id) is None:
            raise NotFoundError("Risorsa non disponibile")
        # I campi dell’utente sono gestiti separatamente da quelli del profilo
        upd_utente: dict[str, Any] = {}
        if nome is not _UNSET:
            upd_utente["nome"] = nome
        if cognome is not _UNSET:
            upd_utente["cognome"] = cognome
        if email is not _UNSET:
            upd_utente["email"] = email
        if telefono is not _UNSET:
            upd_utente["telefono"] = telefono
        if upd_utente:
            await svc_utenti._aggiorna_utente_senza_commit(session,utente_id=paziente_id,aggiornamenti=upd_utente)
        # Vengono preparati gli aggiornamenti specifici del profilo paziente
        upd_profilo: dict[str, Any] = {}
        if codice_fiscale is not _UNSET:
            cf_norm = (
                str(codice_fiscale).strip().upper()
                if codice_fiscale is not None
                else None
            )
            if cf_norm and await _codice_fiscale_esistente(
                session,
                cf_norm,
                escludi_id=paziente_id,
            ):
                raise ConflictError()
            upd_profilo["codice_fiscale"] = cf_norm
        if data_nascita is not _UNSET:
            if not isinstance(data_nascita, date):
                raise ValidationError("data_nascita non può essere nulla")
            upd_profilo["data_nascita"] = data_nascita.isoformat()
        if sesso is not _UNSET:
            if not isinstance(sesso, Sesso):
                raise ValidationError("sesso non può essere nullo")
            upd_profilo["sesso"] = sesso.value
        if peso_obiettivo_kg is not _UNSET:
            upd_profilo["peso_obiettivo_kg"] = peso_obiettivo_kg
        if note_nutrizionista is not _UNSET:
            upd_profilo["note_nutrizionista"] = note_nutrizionista

        if upd_profilo:
            await _update_profilo(session, row_id=paziente_id, campi=upd_profilo)
    return await _leggi_utente_e_profilo(session, paziente_id)

async def disabilita_paziente(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int) -> UtenteRead:
    """Porta il paziente allo stato 'disattivo' e revoca le sue sessioni"""
    return await imposta_stato_paziente(session,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,stato=StatoUtente.disattivo)

async def abilita_paziente(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int) -> UtenteRead:
    """Porta il paziente allo stato 'attivo'"""
    return await imposta_stato_paziente(session,paziente_id=paziente_id,nutrizionista_id=nutrizionista_id,stato=StatoUtente.attivo)

async def _verifica_paziente_gestibile(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None = None) -> None:
    """
    Verifica che il paziente esista 
    -'nutrizionista_id' valorizzato, viene effettuato il controllo di appartenenza al nutrizionista, altrimenti no
    """
    if nutrizionista_id is not None:
        await _verifica_ownership(session, paziente_id, nutrizionista_id, richiedi_attivo=False)
    if await _get_paziente_row(session, paziente_id) is None:
        raise NotFoundError("Risorsa non disponibile")

async def imposta_stato_paziente(session: AsyncSession,*,paziente_id: int,stato: StatoUtente,nutrizionista_id: int | None = None) -> UtenteRead:
    """Aggiorna lo stato del paziente dopo aver effettuato il controllo di appartenza al nutrizionista"""
    async with write_transaction(session):
        await _verifica_paziente_gestibile(session, paziente_id=paziente_id, nutrizionista_id=nutrizionista_id)
        row = await svc_utenti.imposta_stato_utente(session, utente_id=paziente_id, nuovo_stato=stato)
        return svc_utenti._to_read(row)

async def genera_link_impostazione_password_paziente(session: AsyncSession,*,paziente_id: int,base_url: str,nutrizionista_id: int | None = None) -> str:
    """Genera un nuovo link  per impostare la password del paziente autenticato"""
    async with write_transaction(session, immediate=True):
        await _verifica_paziente_gestibile(session, paziente_id=paziente_id, nutrizionista_id=nutrizionista_id)
        return await svc_utenti.genera_link_password(session, utente_id=paziente_id, base_url=base_url)

async def leggi_anagrafica_completa(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int) -> dict[str, Any]:
    """Restituisce l'anagrafica per il nutrizionista, includendo i dati medici"""
    base = await leggi_paziente(session, paziente_id=paziente_id, nutrizionista_id=nutrizionista_id)
    profilo = base["profilo"]
    today = datetime.now(APP_TZ).date()
    eta = None
    # L’età viene calcolata alla data corrente solo se la data di nascita è disponibile
    if profilo.data_nascita:
        eta = today.year - profilo.data_nascita.year - ((today.month, today.day) < (profilo.data_nascita.month, profilo.data_nascita.day))
    dati_medici = (
        await session.execute(
            text(
                "SELECT id, paziente_id, tipo, descrizione "
                "FROM paziente_dato_medico WHERE paziente_id = :pid ORDER BY tipo, descrizione"
            ),
            {"pid": paziente_id},
        )
    ).mappings().all()
    return {
        **base,
        "eta": eta,
        "dati_medici": [dict(row) for row in dati_medici],
    }

async def leggi_profilo_personale(session: AsyncSession,*,paziente_id: int) -> dict[str, Any]:
    """Restituisce il profilo del paziente autenticato"""
    return await _leggi_utente_e_profilo(session, paziente_id)

async def aggiorna_profilo_personale(session: AsyncSession,*,paziente_id: int,**aggiornamenti: Any) -> dict[str, Any]:
    """Aggiorna il profilo del paziente autenticato (NO note interne)"""
    profilo = await _get_profilo(session, row_id=paziente_id)
    if profilo is None:
        raise NotFoundError("Risorsa non disponibile")
    # Le note interne del nutrizionista non sono modificabili dal paziente
    aggiornamenti.pop("note_nutrizionista", None)
    return await aggiorna_paziente(session,paziente_id=paziente_id,nutrizionista_id=int(profilo["nutrizionista_id"]),**aggiornamenti)

async def lista_pazienti_admin(session: AsyncSession,*,ricerca: str | None = None,stato: StatoUtente | None = None,nutrizionista_id: int | None = None,skip: int = 0,limit: int = 50) -> list[dict[str, Any]]:
    """Elenca i pazienti"""
    sql = (
        "SELECT p.*, pp.nutrizionista_id, "
        "n.nome AS nutrizionista_nome, n.cognome AS nutrizionista_cognome, "
        "n.email AS nutrizionista_email "
        "FROM utente p "
        "JOIN profilo_paziente pp ON pp.utente_id = p.id "
        "JOIN utente n ON n.id = pp.nutrizionista_id "
        "WHERE p.ruolo = 'P'"
    )
    params: dict[str, Any] = {"limit": limit, "skip": skip}
    if stato is not None:
        sql += " AND p.stato = :stato"
        params["stato"] = stato.value
    if nutrizionista_id is not None:
        sql += " AND pp.nutrizionista_id = :nid"
        params["nid"] = nutrizionista_id
    if ricerca and (ricerca := ricerca.strip()):
        sql += (
            " AND (p.nome LIKE :q OR p.cognome LIKE :q OR p.email LIKE :q "
            "OR pp.codice_fiscale LIKE :q OR (p.nome || ' ' || p.cognome) LIKE :q)"
        )
        params["q"] = f"%{ricerca}%"
    sql += " ORDER BY p.cognome, p.nome LIMIT :limit OFFSET :skip"

    rows = (await session.execute(text(sql), params)).mappings().all()
    return [
        {
            "utente": svc_utenti._to_read(dict(row)),
            "nutrizionista_id": int(row["nutrizionista_id"]),
            "nutrizionista_nome": f"{row['nutrizionista_nome']} {row['nutrizionista_cognome']}",
            "nutrizionista_email": row["nutrizionista_email"],
        }
        for row in rows
    ]

async def logout_all_paziente(session: AsyncSession,*,paziente_id: int,nutrizionista_id: int | None = None) -> None:
    """Revoca tutte le sessioni del paziente, se il paziente è associato al nutrizionista richiedente"""
    async with write_transaction(session):
        await _verifica_paziente_gestibile(session, paziente_id=paziente_id, nutrizionista_id=nutrizionista_id)
        await svc_utenti.revoca_sessioni_utente(session, paziente_id)