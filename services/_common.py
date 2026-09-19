import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any
from .exceptions import ValidationError

APP_TZ = ZoneInfo("Europe/Rome")

def hash_token(token: str) -> str:
    """Calcola l'hash SHA-256 del token di sessione"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def utc_now() -> datetime:
    """Restituisce data e ora correnti in UTC"""
    return datetime.now(timezone.utc)

def iso_utc(value: datetime) -> str:
    """Converte un oggetto datetime e restituisce una stringa ISO 8601 in UTC"""
    return parse_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_utc(value: datetime | str) -> datetime:
    """Converte un oggetto datetime o una stringa ISO restituiendo un datetime in UTC"""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    # I valori senza timezone vengono interpretati come UTC
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def month_start(value: datetime, offset: int = 0) -> datetime:
    """Restituisce l'inizio del mese relativo alla data indicata"""
    month = value.year * 12 + value.month - 1 + offset
    return value.replace(
        year=month // 12,
        month=month % 12 + 1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

def require(value, message: str = "Stato interno inatteso") -> Any:
    """Verifica che un valore sia presente e valido"""
    if value is None:
        raise ValidationError(message)
    return value