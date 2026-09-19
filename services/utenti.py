import base64
import hashlib
import hmac
import secrets
from typing import Any
from urllib.parse import quote
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.enums import StatoUtente
from schemas.utente import UtenteRead
from . import configurazione
from ._common import hash_token
from ._repo import get_by_id, update_by_id
from ._transaction import write_transaction
from .exceptions import ConflictError,InvalidCurrentPasswordError,NotFoundError,PasswordHashingUnavailableError,ValidationError

PBKDF2_ITERATIONS = 600_000
_READ_TABLES = {"utente"}
_UPDATE_TABLES = {"utente"}

def hash_password(password: str) -> str:
    """Calcola l'hash PBKDF2 della password"""
    try:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256",password.encode("utf-8"),salt.encode("ascii"),PBKDF2_ITERATIONS)
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest_b64}"
    except Exception as exc:
        raise PasswordHashingUnavailableError("Impossibile generare l'hash della password") from exc

def verifica_password(password: str, stored_hash: str) -> bool:
    """Verifica una password -> confrontato l’hash PBKDF2 con quello memorizzato"""
    try:
        # Un hash con formato o algoritmo inatteso non viene considerato valido
        algoritmo, iterazioni, salt, digest_b64 = stored_hash.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        digest_atteso = base64.b64decode(digest_b64.encode("ascii"), validate=True)
        digest = hashlib.pbkdf2_hmac("sha256",password.encode("utf-8"),salt.encode("ascii"),int(iterazioni))
        return hmac.compare_digest(digest, digest_atteso)
    except (ValueError, TypeError):
        return False

def hash_password_casuale() -> str:
    """Genera una password casuale"""
    return hash_password(secrets.token_urlsafe(48))

def _costruisci_url_impostazione_password(base_url: str, token: str) -> str:
    """Costruisce l’URL di impostazione password -> il token inserito nel fragment"""
    return (
        f"{base_url.rstrip('/')}/web/account%20e%20sicurezza/imposta-password.html"
        f"#token={quote(token, safe='')}"
    )

async def cambia_password(session: AsyncSession,*,utente_id: int,password_attuale: str,nuova_password: str) -> dict[str, bool]:
    """Cambia la password dell'utente autenticato"""
    row = (
        await session.execute(
            text("SELECT pwd FROM utente WHERE id=:id"),
            {"id": utente_id},
        )
    ).first()
    if not row:
        raise NotFoundError("Utente")
    # La modifica consentita solo dopo aver verificato la password corrente
    if not verifica_password(password_attuale, str(row[0])):
        raise InvalidCurrentPasswordError("Password attuale non corretta")

    async with write_transaction(session):
        await session.execute(
            text(
                "UPDATE utente SET pwd=:pwd WHERE id=:id"
            ),
            {"pwd": hash_password(nuova_password), "id": utente_id},
        )
        # Dopo il cambio password vengono invalidate tutte le sessioni aperte
        await revoca_sessioni_utente(session, utente_id)
    return {"ok": True}

async def imposta_password_con_token(session: AsyncSession,*,token: str,nuova_password: str) -> None:
    """Imposta la password tramite un token monouso"""
    async with write_transaction(session, immediate=True):
        row = (
            await session.execute(
                text(
                    "SELECT utente_id FROM token_password "
                    "WHERE token_hash=:token_hash "
                    "AND expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                ),
                {"token_hash": hash_token(token)},
            )
        ).first()
        # Il token deve essere presente e valido
        if row is None:
            raise ValidationError("Link non valido, scaduto o già utilizzato")

        utente_id = int(row[0])
        # L’uso del link attiva l’account, revoca le vecchie sessioni e consuma il token
        await session.execute(
            text(
                "UPDATE utente SET pwd=:pwd, stato='A' WHERE id=:id"
            ),
            {"pwd": hash_password(nuova_password), "id": utente_id},
        )
        await revoca_sessioni_utente(session, utente_id)
        await session.execute(
            text("DELETE FROM token_password WHERE utente_id=:uid"),
            {"uid": utente_id},
        )

async def _email_esistente(session: AsyncSession,email: str,escludi_id: int | None = None) -> bool:
    sql = "SELECT 1 FROM utente WHERE email = :email COLLATE NOCASE"
    params: dict[str, Any] = {"email": email.strip().lower()}
    if escludi_id is not None:
        sql += " AND id != :escludi_id"
        params["escludi_id"] = escludi_id
    return (await session.execute(text(sql), params)).first() is not None

def _to_read(row: dict[str, Any]) -> UtenteRead:
    """Converte una record utente nello schema (escluso hash della password)"""
    return UtenteRead.model_validate({k: v for k, v in row.items() if k != "pwd"})

async def revoca_sessioni_utente(session: AsyncSession, utente_id: int) -> None:
    """Elimina tutte le sessioni dell’utente"""
    await session.execute(
        text("DELETE FROM sessione_autenticazione WHERE utente_id = :uid"),
        {"uid": utente_id},
    )

async def _require_utente(session: AsyncSession, utente_id: int) -> dict[str, Any]:
    """Recupera l'utente"""
    row = await get_by_id(session, "utente", utente_id, whitelist=_READ_TABLES)
    if row is None:
        raise NotFoundError("Utente", utente_id)
    return row


async def genera_link_password(session: AsyncSession,*,utente_id: int,base_url: str) -> str:
    await _require_utente(session, utente_id)

    validita_ore = await configurazione.leggi_intero(session,"token_password_validita_ore",default=24,minimo=1)
    token = secrets.token_urlsafe(32)

    # Mantenuto un solo link di impostazione password valido per ogni utente
    await session.execute(
        text("DELETE FROM token_password WHERE utente_id=:uid"),
        {"uid": utente_id},
    )
    await session.execute(
        text(
            "UPDATE utente SET pwd=:pwd, stato='D' WHERE id=:uid"
        ),
        {"pwd": hash_password_casuale(), "uid": utente_id},
    )
    await revoca_sessioni_utente(session, utente_id)
    await session.execute(
        text(
            "INSERT INTO token_password "
            "(utente_id, token_hash, expires_at) VALUES "
            "(:uid, :token_hash, strftime('%Y-%m-%dT%H:%M:%fZ', 'now', :offset))"
        ),
        {
            "uid": utente_id,
            "token_hash": hash_token(token),
            "offset": f"+{validita_ore} hours",
        },
    )
    return _costruisci_url_impostazione_password(base_url, token)

def _normalizza_aggiornamenti_anagrafica(aggiornamenti: dict[str, Any]) -> dict[str, Any]:
    """Normalizza e valida i campi anagrafici comuni di un utente"""
    messaggi = {
        "nome": "nome non può essere nullo o vuoto",
        "cognome": "cognome non può essere nullo o vuoto",
        "email": "email non può essere nulla o vuota",
    }
    for campo, messaggio in messaggi.items():
        if campo in aggiornamenti:
            valore = aggiornamenti[campo]
            if valore is None or not str(valore).strip():
                raise ValidationError(messaggio)
            aggiornamenti[campo] = str(valore).strip()
    if "email" in aggiornamenti:
        aggiornamenti["email"] = aggiornamenti["email"].lower()
    if "telefono" in aggiornamenti:
        telefono = aggiornamenti["telefono"]
        if telefono is not None and not str(telefono).strip():
            raise ValidationError("telefono non può essere una stringa vuota")
    return aggiornamenti

async def _aggiorna_utente_senza_commit(session: AsyncSession,*,utente_id: int,aggiornamenti: dict[str, Any]) -> dict[str, Any]:
    """Aggiorna i campi dell’utente senza gestire la transazione, normalizzando e verificando l’eventuale email"""
    await _require_utente(session, utente_id)
    aggiornamenti = _normalizza_aggiornamenti_anagrafica(aggiornamenti)
    # L’email viene normalizzata e controllata SOLO SE fa parte dell’aggiornamento
    if "email" in aggiornamenti and aggiornamenti["email"] is not None:
        email = str(aggiornamenti["email"])
        if await _email_esistente(session, email, escludi_id=utente_id):
            raise ConflictError()
    return await update_by_id(session,"utente",utente_id,aggiornamenti,whitelist=_UPDATE_TABLES)

async def imposta_stato_utente(session: AsyncSession,*,utente_id: int,nuovo_stato: StatoUtente) -> dict[str, Any]:
    """
    Aggiorna lo stato dell’utente
    Quando viene disattivato, ne revoca tutte le sessioni
    """
    await _require_utente(session, utente_id)
    updated = await update_by_id(session,"utente",utente_id,{"stato": nuovo_stato.value},whitelist=_UPDATE_TABLES)
    # Un account disattivato non deve mantenere sessioni valide
    if nuovo_stato == StatoUtente.disattivo:
        await revoca_sessioni_utente(session, utente_id)
    return updated
