import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.auth import LoginResponse
from schemas.enums import Ruolo, StatoUtente
from schemas.utente import UtenteRead
from . import configurazione
from ._common import hash_token, parse_utc, iso_utc, utc_now
from ._transaction import write_transaction
from .utenti import verifica_password


def _soglia_rinnovo(timeout_ore: int) -> timedelta:
    """Calcola la soglia temporale oltre la quale la sessione può essere rinnovata"""
    return timeout_ore * timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Rappresenta l'utente autenticato per la richiesta corrente"""
    utente_id: int
    ruolo: Ruolo
    token_hash: str
    utente: UtenteRead
    should_renew: bool

def _to_utente(row: dict[str, Any]) -> UtenteRead:
    """Converte un record della tabella 'utente' nello schema UtenteRead (nascondendo l'hash della password)"""
    return UtenteRead.model_validate(
        {
            "id": row["id"],
            "nome": row["nome"],
            "cognome": row["cognome"],
            "email": row["email"],
            "telefono": row["telefono"],
            "ruolo": row["ruolo"],
            "stato": row["stato"],
            "last_login_at": row["last_login_at"],
        }
    )

async def login(session: AsyncSession,*,email: str,password: str) -> LoginResponse | None:
    """Verifica le credenziali e, se corrette, apre una nuova sessione

    -Ritorna None se l'email non esiste o la password è sbagliata
    -Solleva ForbiddenError se l'utente esiste ma è stato disattivato
    -Se tutto va a buon fine: 
     1) crea un token casuale,
     2) salva l'hash in una nuova riga di sessione_autenticazione con le due scadenze 
     3) aggiorna last_login_at 
     4) restituisce il token in chiaro al chiamante
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id, nome, cognome, email, telefono, ruolo, pwd,
                       stato, last_login_at
                FROM utente
                WHERE email = :email COLLATE NOCASE
                LIMIT 1
                """
            ),
            {"email": email.strip().lower()},
        )
    ).mappings().first()
    if (
        row is None
        or not verifica_password(password, str(row["pwd"]))
        or row["stato"] != StatoUtente.attivo.value
    ):
        return None
    # Credenziali errate, utente inesistente e account disattivato restituiscono volutamente lo stesso esito
    # Per evitare di far trasparire o meno l'esistenza di un utente o meno all'interno del sistema
    # if row["stato"] != StatoUtente.attivo.value:
    #    raise ForbiddenError("Utente disattivato")


    # La sessione è limitata sia dall’inattività sia da una scadenza assoluta
    inattivita_h = await configurazione.leggi_intero(session, "sessione_timeout_inattivita_ore", default=1, minimo=1)
    assoluta_h = await configurazione.leggi_intero(session, "sessione_durata_assoluta_ore", default=6, minimo=1)
    now_sql = iso_utc(utc_now())
    now = parse_utc(now_sql)
    absolute_expires_at_sql = iso_utc(now + timedelta(hours=assoluta_h))
    expires_at_sql = iso_utc(min(now + timedelta(hours=inattivita_h), parse_utc(absolute_expires_at_sql)))
    expires_at = parse_utc(expires_at_sql)
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    async with write_transaction(session):
        # Prima di creare la nuova sessione vengono rimosse quelle già scadute
        await session.execute(
            text(
                "DELETE FROM sessione_autenticazione "
                "WHERE expires_at <= :now OR absolute_expires_at <= :now"
            ),
            {"now": now_sql},
        )
        await session.execute(
            text(
                """
                INSERT INTO sessione_autenticazione
                    (utente_id, token_hash, expires_at, absolute_expires_at)
                VALUES
                    (:utente_id, :token_hash, :expires_at, :absolute_expires_at)
                """
            ),
            {
                "utente_id": row["id"],
                "token_hash": token_hash,
                "expires_at": expires_at_sql,
                "absolute_expires_at": absolute_expires_at_sql,
            },
        )
        await session.execute(
            text(
                """
                UPDATE utente
                SET last_login_at = :last_login_at
                WHERE id = :utente_id
                """
            ),
            {
                "last_login_at": now_sql,
                "utente_id": row["id"],
            },
        )
    user_data = dict(row)
    user_data["last_login_at"] = now_sql
    utente = _to_utente(user_data)
    return LoginResponse(token=token,expires_at=expires_at,utente=utente)

async def authenticate_token(session: AsyncSession,*,token: str) -> AuthenticatedUser | None:
    """
    Ricostruisce l'utente autenticato a partire dal token Bearer inviato nella richiesta HTTP
    -Restituisce None se il token non corrisponde a nessuna sessione, se la sessione è scaduta (per inattività o in assoluto) o se l'utente è disattivato
    """
    token_hash = hash_token(token)
    row = (
        await session.execute(
            text(
                """
                SELECT u.id, u.nome, u.cognome, u.email, u.telefono,
                       u.ruolo, u.stato,
                       u.last_login_at,
                       s.expires_at, s.absolute_expires_at
                FROM sessione_autenticazione AS s
                JOIN utente AS u ON u.id = s.utente_id
                WHERE s.token_hash = :token_hash
                LIMIT 1
                """
            ),
            {"token_hash": token_hash},
        )
    ).mappings().first()
    if row is None:
        return None
    # La sessione resta valida solo se entrambe le scadenze sono future e l’account è attivo
    now = utc_now()
    if parse_utc(row["expires_at"]) <= now:
        return None
    if parse_utc(row["absolute_expires_at"]) <= now:
        return None
    if row["stato"] != StatoUtente.attivo.value:
        return None
    utente = _to_utente(dict(row))
    inattivita_h = await configurazione.leggi_intero(session, "sessione_timeout_inattivita_ore", default=1, minimo=1)
    return AuthenticatedUser(utente_id=utente.id,ruolo=utente.ruolo,token_hash=token_hash,utente=utente,should_renew=(parse_utc(row["expires_at"]) <= now + _soglia_rinnovo(inattivita_h)))

async def logout(session: AsyncSession, *, token_hash: str) -> None:
    """Termina la sessione corrente eliminando la relativa riga da sessione_autenticazione (logout sul solo dispositivo/token corrente)"""
    async with write_transaction(session):
        await session.execute(
            text(
                "DELETE FROM sessione_autenticazione "
                "WHERE token_hash = :token_hash"
            ),
            {"token_hash": token_hash},
        )

async def rinnova_sessione(session: AsyncSession, *, token_hash: str) -> None:
    """Rinnova la scadenza per inattività se manca meno di metà del timeout"""
    ore = await configurazione.leggi_intero(session, "sessione_timeout_inattivita_ore", default=1, minimo=1)
    now_sql = iso_utc(utc_now())
    fmt = "%Y-%m-%dT%H:%M:%fZ"
    async with write_transaction(session):
        # Il rinnovo dell’inattività non può mai superare la scadenza assoluta della sessione
        await session.execute(
            text(
                """
                UPDATE sessione_autenticazione
                SET expires_at = MIN(
                    strftime(:fmt, :now, :nuovo_offset),
                    absolute_expires_at
                )
                WHERE token_hash = :token_hash
                  AND expires_at > :now
                  AND absolute_expires_at > :now
                  AND expires_at < strftime(:fmt, :now, :soglia_offset)
                """
            ),
            {
                "fmt": fmt,
                "now": now_sql,
                "nuovo_offset": f"+{ore * 60} minutes",
                "soglia_offset": f"+{int(_soglia_rinnovo(ore).total_seconds() // 60)} minutes",
                "token_hash": token_hash,
            },
        )

async def logout_all(session: AsyncSession, *, utente_id: int) -> None:
    """Revoca tutte le sessioni attive di un utente (tutti i dispositivi)"""
    async with write_transaction(session):
        await session.execute(
            text(
                "DELETE FROM sessione_autenticazione "
                "WHERE utente_id = :utente_id"
            ),
            {"utente_id": utente_id},
        )