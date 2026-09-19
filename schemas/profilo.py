from pydantic import Field
from .base import SchemaBase
from .enums import Sesso
from .types import CodiceFiscale, DataNonFutura, IdPositivo

class ProfiloNutrizionistaBase(SchemaBase):
    """Schema base del profilo nutrizionista"""
    utente_id: IdPositivo

class ProfiloNutrizionistaRead(ProfiloNutrizionistaBase):
    """Schema di lettura del profilo nutrizionista"""

class ProfiloPazienteBase(SchemaBase):
    """Schema base del profilo paziente"""
    utente_id: IdPositivo
    nutrizionista_id: IdPositivo
    codice_fiscale: CodiceFiscale | None = Field(None, max_length=16)
    data_nascita: DataNonFutura
    sesso: Sesso
    peso_obiettivo_kg: float | None = Field(None, gt=0)
    note_nutrizionista: str | None = None

class ProfiloPazienteRead(ProfiloPazienteBase):
    """Schema di lettura del profilo paziente"""
