import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Annotated, Optional
from pydantic import BeforeValidator, EmailStr, Field
from pydantic.functional_validators import AfterValidator

APP_TZ = ZoneInfo("Europe/Rome")
_RE_ORA_HHMM = re.compile(r"^(\d{2}):(\d{2})$")
_RE_CF = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$", re.IGNORECASE)


def _val_ora(value: str) -> str:
    """Valida HH:MM nell'intervallo 00:00–23:59"""
    match = _RE_ORA_HHMM.match(value)
    if not match:
        raise ValueError("orario non valido")
    ore, minuti = int(match.group(1)), int(match.group(2))
    if not (0 <= ore <= 23 and 0 <= minuti <= 59):
        raise ValueError(f"Orario fuori intervallo: '{value}'")
    return value


def _val_cf(value: Optional[str]) -> Optional[str]:
    """Valida e normalizza il formato del codice fiscale"""
    if value is None:
        return value
    value = value.strip().upper()
    if not _RE_CF.match(value):
        raise ValueError("codice fiscale non valido")
    return value


def _val_data_non_futura(value: date) -> date:
    """Verifica che la data non sia successiva alla data corrente"""
    oggi = datetime.now(APP_TZ).date()
    if value > oggi:
        raise ValueError("La data non può essere futura")
    return value


def _testo_vuoto_a_none(value: object) -> object:
    """Converte una stringa vuota o composta da soli spazi in None"""
    if isinstance(value, str):
        return value.strip() or None
    return value


def _normalizza_email(value: object) -> object:
    """Normalizza l’indirizzo email rimuovendo spazi e convertendolo in minuscolo"""
    return value.strip().lower() if isinstance(value, str) else value


OraHHMM = Annotated[str, AfterValidator(_val_ora)]
"""Orario nel formato HH:MM (00:00–23:59)"""

CodiceFiscale = Annotated[Optional[str], AfterValidator(_val_cf)]
"""Codice fiscale opzionale nel formato italiano standard"""

DataNonFutura = Annotated[date, AfterValidator(_val_data_non_futura)]
"""Data non successiva alla data corrente"""

TestoOpzionale = Annotated[str | None, BeforeValidator(_testo_vuoto_a_none)]
"""Testo opzionale che converte valori vuoti in None"""

GiornoSettimana = Annotated[int, Field(ge=0, le=6)]
"""Giorno della settimana rappresentato con un intero da 0 a 6"""

IdPositivo = Annotated[int, Field(gt=0)]
"""Identificativo intero strettamente positivo"""

NomePersona = Annotated[str, Field(min_length=1, max_length=20)]
"""Nome di una persona"""

CognomePersona = Annotated[str, Field(min_length=1, max_length=20)]
"""Cognome di una persona"""

EmailUtente = Annotated[EmailStr, BeforeValidator(_normalizza_email), Field(max_length=100)]
"""Indirizzo email normalizzato utilizzato dagli utenti"""

Telefono = Annotated[str, Field(max_length=15)]
"""Numero di telefono"""
