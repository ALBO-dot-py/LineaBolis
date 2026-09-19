from dataclasses import dataclass
from schemas.enums import Ruolo
from ..exceptions import ValidationError

@dataclass(frozen=True, slots=True)
class AppointmentActor:
    ruolo: Ruolo
    utente_id: int
    nutrizionista_id: int
    paziente_id: int | None = None

    @classmethod
    def nutrizionista(cls, utente_id: int, *, paziente_id: int | None = None) -> "AppointmentActor":
        """Costruisce l'attore nutrizionista, eventualmente con paziente"""
        return cls(ruolo=Ruolo.nutrizionista,utente_id=utente_id,nutrizionista_id=utente_id,paziente_id=paziente_id)

    @classmethod
    def paziente(cls, utente_id: int, *, nutrizionista_id: int) -> "AppointmentActor":
        """Costruisce l'attore paziente"""
        return cls(ruolo=Ruolo.paziente,utente_id=utente_id,nutrizionista_id=nutrizionista_id,paziente_id=utente_id,)

    @property
    def is_paziente(self) -> bool:
        return self.ruolo is Ruolo.paziente
    def require_paziente_id(self) -> int:
        """Restituisce il paziente associato o segnala che è obbligatorio"""
        # Alcune operazioni richiedono un paziente esplicito
        if self.paziente_id is None:
            raise ValidationError("Il paziente è obbligatorio per questa operazione")
        return self.paziente_id
