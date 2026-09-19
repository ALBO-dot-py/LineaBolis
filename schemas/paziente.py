from pydantic import Field
from .auth import LinkImpostazionePasswordResponse
from .base import PublicRequest, SchemaBase
from .dato_medico import DatoMedicoRead
from .enums import Sesso
from .profilo import ProfiloPazienteRead
from .types import CodiceFiscale, CognomePersona, DataNonFutura, EmailUtente, NomePersona, Telefono
from .utente import UtenteRead

class PazienteCreateRequest(PublicRequest):
    """Payload per la creazione di un paziente"""
    nome: NomePersona
    cognome: CognomePersona
    email: EmailUtente
    telefono: Telefono | None = None
    codice_fiscale: CodiceFiscale | None = None
    data_nascita: DataNonFutura
    sesso: Sesso
    peso_obiettivo_kg: float | None = Field(None, gt=0)
    note_nutrizionista: str | None = None

class PazienteUpdateRequest(PublicRequest):
    """Payload per l’aggiornamento di un paziente"""
    nome: NomePersona | None = None
    cognome: CognomePersona | None = None
    email: EmailUtente | None = None
    telefono: Telefono | None = None
    codice_fiscale: CodiceFiscale | None = None
    data_nascita: DataNonFutura | None = None
    sesso: Sesso | None = None
    peso_obiettivo_kg: float | None = Field(None, gt=0)
    note_nutrizionista: str | None = None

class PazienteDetailResponse(SchemaBase):
    """Schema di risposta con utente e profilo del paziente"""
    utente: UtenteRead
    profilo: ProfiloPazienteRead

class PazienteCreateResponse(PazienteDetailResponse,LinkImpostazionePasswordResponse):
    """Schema di risposta restituito dopo la creazione di un paziente"""

class PazienteAnagraficaResponse(PazienteDetailResponse):
    """Schema di risposta con anagrafica e dati medici del paziente"""
    eta: int | None = None
    dati_medici: list[DatoMedicoRead] = Field(default_factory=list)
