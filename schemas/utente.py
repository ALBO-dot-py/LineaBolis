from datetime import datetime
from typing import Optional
from pydantic import Field
from .base import PASSWORD_MIN_LENGTH, PublicRequest, SchemaBase, valida_nuova_password
from .enums import Ruolo, StatoUtente
from .types import CognomePersona, EmailUtente, NomePersona, Telefono

class PasswordChange(PublicRequest):
    """Payload per il cambio password con verifica delle policy e della conferma"""
    password_attuale: str = Field(..., min_length=1, max_length=200)
    nuova_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=200)
    conferma_nuova_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=200)
    _check_password = valida_nuova_password("nuova_password", "conferma_nuova_password")

class UtenteBase(SchemaBase):
    """Schema base con i dati comuni di un utente"""
    nome: NomePersona
    cognome: CognomePersona
    email: EmailUtente = Field(..., description="Username di login")
    telefono: Telefono | None = None
    ruolo: Ruolo
    stato: StatoUtente = StatoUtente.attivo

class UtenteRead(UtenteBase):
    """Schema di lettura di un utente"""
    id: int
    last_login_at: Optional[datetime] = None
