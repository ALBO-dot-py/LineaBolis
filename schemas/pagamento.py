from datetime import datetime
from pydantic import Field
from .base import PublicRequest, SchemaBase

class PagamentoRead(SchemaBase):
    """Schema di lettura di un pagamento associato a un appuntamento"""
    appuntamento_id: int
    prezzo_cent: int
    sconto_cent: int
    totale_cent: int
    pagato_at: datetime | None = None
    giorni_scaduto: int = 0
    appuntamento_tipo_nome: str
    appuntamento_data_ora_inizio: datetime
    paziente_nome: str

class PagamentoRequest(PublicRequest):
    """Payload per aggiornare lo sconto di un pagamento"""
    sconto_cent: int = Field(0, ge=0)

class PagamentoSezioneRead(SchemaBase):
    """Schema di lettura di una sezione del pannello pagamenti"""
    items: list[PagamentoRead]
    count: int
    totale_cent: int

class PagamentoSintesiRead(SchemaBase):
    """Schema di sintesi di un insieme di pagamenti"""
    count: int
    totale_cent: int

class StatisticaImportoMensileRead(SchemaBase):
    """Schema di lettura di un importo mensile aggregato"""
    mese: str
    totale_cent: int

class PagamentoStatisticheRead(SchemaBase):
    """Schema di lettura delle statistiche del pannello pagamenti"""
    da_incassare_oggi: PagamentoSintesiRead
    in_sospeso: PagamentoSintesiRead
    pagati_ultimi_6_mesi: int
    in_sospeso_ultimi_6_mesi: int
    incassi_ultimi_6_mesi: list[StatisticaImportoMensileRead]

class PagamentoPanelRead(SchemaBase):
    """Schema di risposta completo del pannello pagamenti"""
    aperti: PagamentoSezioneRead
    pagati: PagamentoSezioneRead
    statistiche: PagamentoStatisticheRead | None = None
