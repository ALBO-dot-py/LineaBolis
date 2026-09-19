from pydantic import EmailStr
from .base import PublicRequest, SchemaBase
from .profilo import ProfiloNutrizionistaRead
from .types import CognomePersona, EmailUtente, NomePersona, Telefono
from .utente import UtenteRead
from .auth import LinkImpostazionePasswordResponse

class NutrizionistaCreateRequest(PublicRequest):
    """Payload per creazione di un nutrizionista"""
    nome: NomePersona
    cognome: CognomePersona
    email: EmailUtente
    telefono: Telefono | None = None

class NutrizionistaCreateResponse(LinkImpostazionePasswordResponse):
    """Schema di risposta dopo la creazione di un nutrizionista"""
    utente: UtenteRead
    profilo: ProfiloNutrizionistaRead

class NutrizionistaUpdateRequest(PublicRequest):
    """Payload richiesto per l’aggiornamento di un nutrizionista"""
    nome: NomePersona | None = None
    cognome: CognomePersona | None = None
    email: EmailUtente | None = None
    telefono: Telefono | None = None

class NutrizionistaAdminListItem(SchemaBase):
    """Schema di riepilogo di un nutrizionista per il pannello amministrativo"""
    utente: UtenteRead
    numero_pazienti_attivi: int

class AdminPazienteListItem(SchemaBase):
    """Schema di riepilogo di un paziente per il pannello amministrativo"""
    utente: UtenteRead
    nutrizionista_id: int
    nutrizionista_nome: str
    nutrizionista_email: EmailStr
