class ServiceError(Exception):
    """Errore base"""

class NotFoundError(ServiceError):
    """La risorsa non esiste"""

class ConflictError(ServiceError):
    """Conflitto di unicità, risorsa referenziata o slot occupato"""

    def __init__(self, message: str = "La richiesta è in conflitto con lo stato corrente", *, details: object | None = None) -> None:
        """Inizializza il conflitto con un messaggio e, se disponibili, i dettagli"""
        super().__init__(message)
        self.details = details

class ForbiddenError(ServiceError):
    """Questo profilo non può eseguire l'operazione"""

class ValidationError(ServiceError):
    """Violazione di una regola applicativa"""

class InvalidCurrentPasswordError(ServiceError):
    """La password non corrisponde con quella salvata"""

class PasswordHashingUnavailableError(ServiceError):
    """Errore durante la generazione dell'hash password"""
