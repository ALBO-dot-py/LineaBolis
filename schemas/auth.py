from datetime import datetime
from typing import Literal
from pydantic import Field
from .base import PASSWORD_MIN_LENGTH, PublicRequest, SchemaBase, valida_nuova_password
from .types import EmailUtente
from .utente import UtenteRead

class LoginRequest(PublicRequest):
    """Payload per l’autenticazione di un utente"""
    email: EmailUtente
    password: str = Field(..., min_length=1, max_length=200)

class LoginResponse(SchemaBase):
    """Schema di risposta restituito dopo autenticazione riuscita"""
    token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime
    utente: UtenteRead

class LinkImpostazionePasswordResponse(SchemaBase):
    """Schema di risposta con il link per l’impostazione della password"""
    url_impostazione_password: str

class ImpostaPasswordRequest(PublicRequest):
    """Payload per impostare una nuova password tramite token"""
    token: str = Field(..., min_length=20, max_length=200)
    nuova_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=200)
    conferma_nuova_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=200)
    _check_password = valida_nuova_password("nuova_password", "conferma_nuova_password")
