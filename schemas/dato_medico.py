from pydantic import Field
from .base import PublicRequest, SchemaBase
from .enums import TipoDatoMedico
from .types import IdPositivo

class DatoMedicoCreate(PublicRequest):
    """Payload per la creazione di un dato medico"""
    tipo: TipoDatoMedico
    descrizione: str = Field(..., min_length=1)

class DatoMedicoUpdate(PublicRequest):
    """Payload per l’aggiornamento di un dato medico"""
    tipo: TipoDatoMedico | None = None
    descrizione: str | None = Field(None, min_length=1)

class DatoMedicoRead(SchemaBase):
    """Schema di lettura di un dato medico"""
    id: int
    paziente_id: IdPositivo
    tipo: TipoDatoMedico
    descrizione: str
