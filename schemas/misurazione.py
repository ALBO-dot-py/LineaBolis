from datetime import date
from typing import Literal, Optional
from pydantic import ConfigDict, Field
from .base import SchemaBase
from .types import DataNonFutura

class MisurazioneBase(SchemaBase):
    """Schema base con i dati di una misurazione"""
    data: date
    peso_kg: float = Field(..., gt=0)
    altezza_cm: float = Field(..., gt=0)
    note_nutrizionista: Optional[str] = None
    note_paziente: Optional[str] = None

    # pliche obbligatorie per il calcolo della massa grassa
    plica_tricipitale_mm: float = Field(..., gt=0)
    plica_bicipitale_mm: float = Field(..., gt=0)
    plica_sottoscapolare_mm: float = Field(..., gt=0)
    plica_sovrailiaca_mm: float = Field(..., gt=0)

    # pliche e circonferenze facoltative
    plica_ombelicale_mm: Optional[float] = Field(None, gt=0)
    plica_pettorale_mm: Optional[float] = Field(None, gt=0)
    plica_coscia_mm: Optional[float] = Field(None, gt=0)
    circ_vita_cm: Optional[float] = Field(None, gt=0)
    circ_fianchi_cm: Optional[float] = Field(None, gt=0)
    circ_bicipite_cm: Optional[float] = Field(None, gt=0)
    circ_coscia_cm: Optional[float] = Field(None, gt=0)
    circ_torace_cm: Optional[float] = Field(None, gt=0)
    circ_addome_cm: Optional[float] = Field(None, gt=0)

class MisurazioneCreateRequest(MisurazioneBase):
    """Payload per la creazione di una misurazione"""
    data: DataNonFutura
    model_config = ConfigDict(str_strip_whitespace=True,validate_assignment=True,extra="forbid",)

class MisurazioneResponse(MisurazioneBase):
    """Schema di risposta di una misurazione"""
    id: int
    paziente_id: int
    bmi: float
    somma_pliche_mm: float
    massa_grassa_perc: float

class PuntoTemporale(SchemaBase):
    """Schema di un punto appartenente a una serie temporale"""
    data: date
    valore: float

class SerieTemporale(SchemaBase):
    """Schema di una serie temporale relativa a una metrica"""
    metrica: str
    unita: Literal["kg", "%", "mm", "cm"]
    punti: list[PuntoTemporale]

class SintesiMisurazione(SchemaBase):
    """Schema di sintesi dei principali valori di una misurazione"""
    data: date
    peso_kg: float
    massa_grassa_perc: float
    bmi: float

class AvanzamentoMisurazioni(SchemaBase):
    """Schema di sintesi dell’avanzamento tra le misurazioni"""
    percentuale: Optional[float] = None
    peso_perso_kg: float
    massa_grassa_perc_persa: float
    numero_misurazioni: int

class ProgressiMisurazioniResponse(SchemaBase):
    """Schema di risposta con l’andamento complessivo delle misurazioni"""
    partenza: Optional[SintesiMisurazione] = None
    attuale: Optional[SintesiMisurazione] = None
    peso_obiettivo_kg: Optional[float] = None
    avanzamento: Optional[AvanzamentoMisurazioni] = None
    serie: list[SerieTemporale]