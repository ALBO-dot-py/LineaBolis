from pydantic import Field, model_validator
from .base import PublicRequest, SchemaBase

class ConfigurazioneAppBase:
    """Schema base con i parametri di configurazione dell’applicazione"""
    ore_massime_risposta_appuntamento: int = Field(..., ge=1)
    ore_minime_annullamento_appuntamento: int = Field(..., ge=0)
    testo_avviso_disdetta_tardiva: str = Field(..., min_length=1, max_length=2000)
    sessione_timeout_inattivita_ore: int = Field(..., ge=1)
    sessione_durata_assoluta_ore: int = Field(..., ge=1)
    token_password_validita_ore: int = Field(..., ge=1)

    @model_validator(mode="after")
    def valida_durate_sessione(self):
        """Verifica la coerenza tra timeout di inattività e durata assoluta della sessione"""
        if self.sessione_durata_assoluta_ore < self.sessione_timeout_inattivita_ore:
            raise ValueError("La durata assoluta della sessione non può essere inferiore al timeout per inattività")
        return self

class ConfigurazioneAppRequest(ConfigurazioneAppBase, PublicRequest):
    """Payload richiesto per la configurazione, NON accetta chiavi aggiuntive rispetto a quelle previste"""

class ConfigurazioneAppResponse(ConfigurazioneAppBase, SchemaBase):
    """Schema di risposta della configurazione con valori già convertiti nei tipi corretti"""
