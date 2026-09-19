from datetime import datetime
from pydantic import Field, model_validator
from .base import PublicRequest, SchemaBase
from .types import GiornoSettimana, OraHHMM

def _minuti(value: str) -> int:
    """Converte un orario HH:MM nel numero di minuti dall’inizio della giornata"""
    ore, minuti = map(int, value.split(":"))
    return ore * 60 + minuti

def valida_fascia_oraria(ora_inizio: str, ora_fine: str) -> None:
    """Verifica che la fascia oraria abbia un ordine corretto tra inizio e fine e controlla che entrambi gli intervalli siano di 15 minuti"""
    if ora_fine <= ora_inizio:
        raise ValueError("L'ora di fine deve essere successiva all'ora di inizio")
    if _minuti(ora_inizio) % 15 or _minuti(ora_fine) % 15:
        raise ValueError("Inizio e fine devono essere su intervalli di 15 minuti")

class _FasciaBase(SchemaBase):
    """Schema base di una fascia di disponibilità settimanale"""
    giorno_settimana: GiornoSettimana
    ora_inizio: OraHHMM
    ora_fine: OraHHMM

    @model_validator(mode="after")
    def valida_fascia(self):
        """Verifica la validità della fascia oraria configurata"""
        valida_fascia_oraria(self.ora_inizio, self.ora_fine)
        return self

class DisponibilitaCreate(_FasciaBase, PublicRequest):
    """Payload richiesto per la creazione di una disponibilità, NON accetta chiavi aggiuntive rispetto a quelle previste"""

class DisponibilitaRead(_FasciaBase):
    """Schema di lettura di una disponibilità settimanale"""
    id: int
    nutrizionista_id: int

class _IndisponibilitaBase(SchemaBase):
    """Schema base di un intervallo di indisponibilità"""
    data_ora_inizio: datetime
    data_ora_fine: datetime
    motivo: str = Field(min_length=1)

    @model_validator(mode="after")
    def valida_intervallo(self):
        """validatore per controllare che un intervallo abbia senso e sia corretto"""
        if self.data_ora_fine <= self.data_ora_inizio:
            raise ValueError("La fine deve essere successiva all'inizio")
        return self

class IndisponibilitaCreate(_IndisponibilitaBase, PublicRequest):
    """Payload per la creazione di un’indisponibilità, NON accetta chiavi aggiuntive rispetto a quelle previste"""

class IndisponibilitaRead(_IndisponibilitaBase):
    """Schema di lettura di un’indisponibilità"""
    id: int
    nutrizionista_id: int
