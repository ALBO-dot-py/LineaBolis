from datetime import date, datetime
from pydantic import Field, model_validator
from .base import PublicRequest, SchemaBase
from .enums import StatoDieta, TipoDieta
from .types import GiornoSettimana, IdPositivo, TestoOpzionale

class AlimentoPayload(PublicRequest):
    """Payload di un alimento associato a un’opzione di pasto"""
    descrizione: str = Field(..., min_length=1, max_length=200)

class OpzionePastoPayload(PublicRequest):
    """Payload di un’opzione di pasto con i relativi alimenti"""
    alimenti: list[AlimentoPayload] = Field(min_length=1)

class PastoPayload(PublicRequest):
    """Payload di un pasto con le relative opzioni"""
    giorno_settimana: GiornoSettimana | None = None
    nome: str = Field(..., min_length=1, max_length=200)
    note: TestoOpzionale = None
    opzioni: list[OpzionePastoPayload] = Field(min_length=1)

class DietaStrutturaRequest(PublicRequest):
    """Payload base con la struttura e i pasti di una dieta"""
    nome: str = Field(..., min_length=1, max_length=200)
    tipo: TipoDieta
    note: TestoOpzionale = None
    pasti: list[PastoPayload] = Field(min_length=1)

    @model_validator(mode="after")
    def valida_struttura(self):
        """Validatore della struttura dei pasti in base al tipo di dieta scelto,
            le diete settimanali devono avere almeno un pasto associato a ogni giorno"""
        if self.tipo == TipoDieta.giornaliero:
            if any(pasto.giorno_settimana is not None for pasto in self.pasti):
                raise ValueError("il giorno della settimana non è previsto per una dieta giornaliera")
            return self
        if any(pasto.giorno_settimana is None for pasto in self.pasti):
            raise ValueError("ogni pasto di una dieta settimanale deve avere il giorno a cui riferirsi")
        giorni_presenti = {pasto.giorno_settimana for pasto in self.pasti}
        if giorni_presenti != set(range(7)):
            raise ValueError("una dieta settimanale deve contenere almeno un pasto per ciascun giorno")
        return self

class DietaCreateRequest(DietaStrutturaRequest):
    """Payload per la creazione di una dieta"""
    paziente_id: IdPositivo
    note_nutrizionista: TestoOpzionale = None

class DietaUpdateRequest(DietaStrutturaRequest):
    """Payload per l’aggiornamento di una dieta"""
    note_nutrizionista: TestoOpzionale = None

class ConsiderazioniFinaliRequest(PublicRequest):
    """Payload per aggiornare le considerazioni finali"""
    considerazioni_finali: TestoOpzionale = None

class AlimentoRead(SchemaBase):
    """Schema di lettura di un alimento"""
    id: int
    ordine: int
    descrizione: str

class OpzionePastoRead(SchemaBase):
    """Schema di lettura di un’opzione di pasto"""
    id: int
    ordine: int
    alimenti: list[AlimentoRead] = Field(default_factory=list)

class PastoRead(SchemaBase):
    """Schema di lettura di un pasto"""
    id: int
    ordine: int
    nome: str
    giorno_settimana: int | None = None
    note: str | None = None
    opzioni: list[OpzionePastoRead] = Field(default_factory=list)

class TemplateDietaSummary(SchemaBase):
    """Schema di riepilogo di un template di dieta"""
    id: int
    nome: str
    tipo: TipoDieta
    note: str | None = None

class TemplateDietaRead(TemplateDietaSummary):
    """Schema di lettura completo di un template di dieta"""
    pasti: list[PastoRead] = Field(default_factory=list)

class DietaProgressiResponse(SchemaBase):
    """Schema di risposta con i progressi associati a una dieta"""
    dieta_id: int
    dati_sufficienti: bool
    prima_misurazione_id: int | None = None
    ultima_misurazione_id: int | None = None
    data_prima_misurazione: date | None = None
    data_ultima_misurazione: date | None = None
    kg_delta: float | None = None
    obiettivo_delta_kg: float | None = None
    massa_grassa_delta: float | None = None
    pliche_delta: dict[str, float] = Field(default_factory=dict)

class DietaBaseRead(SchemaBase):
    """Schema base di lettura di una dieta"""
    id: int
    paziente_id: int
    nutrizionista_id: int
    nutrizionista_nome: str | None = None
    nome: str
    tipo: TipoDieta
    stato: StatoDieta
    data_inizio_validita: date
    data_fine_validita: date | None = None
    note: str | None = None

class DietaPazienteRead(DietaBaseRead):
    """Schema di lettura della dieta esposta al paziente"""
    pasti: list[PastoRead] = Field(default_factory=list)

class DietaNutrizionistaSummary(DietaBaseRead):
    """Schema di riepilogo della dieta esposta al nutrizionista"""
    archiviata_at: datetime | None = None
    note_nutrizionista: str | None = None
    considerazioni_finali: str | None = None
    progressi: DietaProgressiResponse | None = None

class DietaNutrizionistaRead(DietaNutrizionistaSummary):
    """Schema di lettura completo della dieta esposta al nutrizionista"""
    pasti: list[PastoRead] = Field(default_factory=list)

class DietePazienteNutrizionistaResponse(SchemaBase):
    """Schema di risposta con dieta attiva e diete archiviate di un paziente"""
    attiva: DietaNutrizionistaSummary | None = None
    archiviate: list[DietaNutrizionistaSummary] = Field(default_factory=list)
