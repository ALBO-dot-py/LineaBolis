from datetime import date, datetime
from pydantic import Field
from .base import PublicRequest, SchemaBase
from .enums import Sesso
from .types import CodiceFiscale, CognomePersona, DataNonFutura, EmailUtente, IdPositivo, NomePersona, Telefono
from .utente import UtenteRead
from .appuntamento import AppuntamentoResponse

class MeProfiloPazienteRead(SchemaBase):
    """Schema di lettura del profilo paziente richiesto dal paziente autenticato"""
    utente_id: int
    nutrizionista_id: int
    codice_fiscale: CodiceFiscale = None
    data_nascita: date
    sesso: Sesso
    peso_obiettivo_kg: float | None = None

class MeProfiloResponse(SchemaBase):
    """Schema di risposta del profilo richiesto dal paziente autenticato"""
    utente: UtenteRead
    profilo: MeProfiloPazienteRead

class MeProfiloUpdateRequest(PublicRequest):
    """Payload per aggiornare il profilo, richiesto dal paziente autenticato"""
    nome: NomePersona | None = None
    cognome: CognomePersona | None = None
    email: EmailUtente | None = None
    telefono: Telefono | None = None
    codice_fiscale: CodiceFiscale = None
    data_nascita: DataNonFutura | None = None
    sesso: Sesso | None = None
    peso_obiettivo_kg: float | None = Field(None, gt=0)


class MeAppuntamentoCreateRequest(PublicRequest):
    """Payload richiesto al paziente autenticato per creare una richiesta di appuntamento"""
    tipo_appuntamento_id: IdPositivo
    data_ora_inizio: datetime

class MeAppuntamentiPannelloResponse(SchemaBase):
    """Schema di risposta del pannello appuntamenti richiesto dal paziente autenticato"""
    prossimi_appuntamenti: list[AppuntamentoResponse]
    richieste_da_confermare: list[AppuntamentoResponse]
    storico_richieste: list[AppuntamentoResponse]
    storico_appuntamenti_effettuati: list[AppuntamentoResponse]
    appuntamenti_da_chiudere: list[AppuntamentoResponse] = Field(default_factory=list)
    storico_assenze_disdette: list[AppuntamentoResponse] = Field(default_factory=list)

__all__ = [
    "MeAppuntamentoCreateRequest",
    "MeAppuntamentiPannelloResponse",
    "MeProfiloResponse",
    "MeProfiloUpdateRequest",
]
