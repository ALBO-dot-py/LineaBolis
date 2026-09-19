from datetime import datetime
from typing import Optional
from pydantic import Field, field_validator
from .base import PublicRequest, SchemaBase
from .enums import AzioneAppuntamento, StatoAppuntamento
from .types import IdPositivo

class TipoAppuntamentoWrite(PublicRequest):
    """Schema di scrittura per una tipologia di appuntamento"""
    nome: str = Field(..., min_length=1, max_length=75)
    descrizione: Optional[str] = None
    prezzo_base_cent: int = Field(0, ge=0)
    durata: int = Field(..., ge=15, multiple_of=15, description="Durata in minuti")
    prenotabile_paziente: bool = True
    conferma_automatica: bool = Field(False,description="Conferma automaticamente gli appuntamenti di questa tipologia")

class TipoAppuntamentoRead(TipoAppuntamentoWrite):
    """Schema di lettura di una tipologia di appuntamento"""
    id: int
    nutrizionista_id: int
    model_config = SchemaBase.model_config

class AppuntamentoCreate(SchemaBase):
    """Schema d creazione di un appuntamento"""
    tipo_appuntamento_id: IdPositivo
    data_ora_inizio: datetime
    note_nutrizionista: Optional[str] = None

class AppuntamentoCreateRequest(PublicRequest):
    """Payload per la creazione di un appuntamento da parte del nutrizionista"""
    paziente_id: IdPositivo
    tipo_appuntamento_id: IdPositivo
    data_ora_inizio: datetime
    note_nutrizionista: Optional[str] = None

class MotivoAppuntamentoRequest(PublicRequest):
    """Payload per specificare il motivo di un’azione sull’appuntamento"""
    motivo: str = Field(..., min_length=1)
    @field_validator("motivo")
    @classmethod
    def motivo_non_vuoto(cls, value: str) -> str:
        """Verifica che il motivo contenga almeno un carattere non vuoto"""
        value = value.strip()
        if not value:
            raise ValueError("Il motivo è obbligatorio")
        return value

class DettaglioAppuntamentoResponse(SchemaBase):
    """Schema di dettaglio della tipologia di un appuntamento"""
    nome: str
    descrizione: Optional[str] = None
    durata_minuti: int
    prezzo_cent: int

class AppuntamentoResponse(SchemaBase):
    """Schema di risposta di un appuntamento"""
    id: int
    nutrizionista_id: int
    paziente_id: int
    paziente_nome: Optional[str] = None
    nutrizionista_nome: Optional[str] = None
    data_ora_inizio: datetime
    data_ora_fine: datetime
    stato: StatoAppuntamento
    stato_label: str
    motivo: Optional[str] = None
    data_evento: Optional[datetime] = None
    note_nutrizionista: Optional[str] = None
    tipo: DettaglioAppuntamentoResponse
    scadenza_risposta: Optional[datetime] = None
    azioni_consentite: list[AzioneAppuntamento] = Field(default_factory=list)
    pagato: bool = False
    annullamento_tardivo: bool = False
    testo_avviso_annullamento: Optional[str] = None

class SlotPrenotabileResponse(SchemaBase):
    """Schema di risposta di uno slot disponibile per la prenotazione"""
    data_ora_inizio: datetime
    data_ora_fine: datetime

class StatisticaEsitiMensiliRead(SchemaBase):
    """Schema di lettura degli esiti mensili degli appuntamenti"""
    mese: str
    effettuati: int
    assenze_disdette: int
