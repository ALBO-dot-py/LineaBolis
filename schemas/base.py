from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, model_validator

PASSWORD_MIN_LENGTH = 8
PASSWORD_CARATTERI_SPECIALI = r"!#$%&()*+,-./:;<=>?@[]^_{}"

def _valida_regole_password(password: str) -> None:
    """Controlla che la password rispetti le regole di sicurezza(policy)"""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"La password deve contenere almeno {PASSWORD_MIN_LENGTH} caratteri")
    if not any(c.isupper() for c in password):
        raise ValueError("La password deve contenere almeno una maiuscola")
    if not any(c.islower() for c in password):
        raise ValueError("La password deve contenere almeno una minuscola")
    if not any(c.isdigit() for c in password):
        raise ValueError("La password deve contenere almeno un numero")
    if not any(c in PASSWORD_CARATTERI_SPECIALI for c in password):
        raise ValueError("La password deve contenere almeno un carattere speciale")

def valida_nuova_password(campo_password: str, campo_conferma: str):
    """
    Validatore per verificare una nuova password e la relativa conferma,
    prima controlla le regole di sicurezza, poi verifica che i due valori coincidono
    """
    def _check(self):
        """Esegue i controlli sulla nuova password e sulla ripsettiva conferma"""
        _valida_regole_password(getattr(self, campo_password))
        if getattr(self, campo_password) != getattr(self, campo_conferma):
            raise ValueError("Le password non coincidono")
        return self
    return model_validator(mode="after")(_check)

class SchemaBase(BaseModel):
    """Schema base condiviso da tutti i modelli Pydantic"""
    model_config = ConfigDict(str_strip_whitespace=True,validate_assignment=True)
    def to_sqlite_dict(self,*,exclude_none: bool = False,exclude_unset: bool = True) -> dict:
        """Converte i dati in valori compatibili con SQLite"""
        raw = self.model_dump(exclude_none=exclude_none,exclude_unset=exclude_unset)
        out: dict = {}
        for key, value in raw.items():
            if isinstance(value, datetime):
                out[key] = value.isoformat()
            elif isinstance(value, date):
                out[key] = value.isoformat()
            elif isinstance(value, bool):
                out[key] = int(value)
            elif isinstance(value, Enum):
                out[key] = value.value
            else:
                out[key] = value
        return out

class PublicRequest(SchemaBase):
    """Schema base per i payload pubblici, NON accetta chiavi aggiuntive rispetto a quelle previste"""
    model_config = ConfigDict(str_strip_whitespace=True,validate_assignment=True,extra="forbid")
