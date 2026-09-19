from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from services.exceptions import ConflictError,ForbiddenError,InvalidCurrentPasswordError,NotFoundError,PasswordHashingUnavailableError,ValidationError

def _json(status_code: int, detail: str, *, headers: dict[str, str] | None = None) -> JSONResponse:
    """Crea template per una risposta di errore"""
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)

def register_exception_handlers(app: FastAPI) -> None:
    """Registra le funzioni che gestiscono gli errori dell’app e li trasformano in risposte HTTP chiare e uniformi"""
    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, __: NotFoundError) -> JSONResponse:
        """risorsa non trovata -> HTTP 404"""
        return _json(404, "Risorsa non disponibile")

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
        """accesso non autorizzato -> HTTP 403"""
        return _json(403, str(exc))

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        """conflitto -> HTTP 409"""
        content = {"detail": str(exc) or "Impossibile completare l'operazione"}
        if exc.details is not None:
            content["conflitti"] = exc.details
        return JSONResponse(status_code=409, content=content)

    @app.exception_handler(InvalidCurrentPasswordError)
    async def invalid_current_password_handler(_: Request,exc: InvalidCurrentPasswordError) -> JSONResponse:
        """password attuale errata -> HTTP 400"""
        return _json(400, str(exc))

    @app.exception_handler(ValidationError)
    async def validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        """errore di validazione applicativa -> HTTP 422"""
        return _json(422, str(exc))

    @app.exception_handler(PasswordHashingUnavailableError)
    async def hashing_handler(_: Request, __: PasswordHashingUnavailableError) -> JSONResponse:
        """errore durante hashing -> HTTP 503"""
        return _json(503, "Servizio di hashing password non disponibile")

    @app.exception_handler(RequestValidationError)
    async def request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        """errori di validazione schema -> HTTP 422"""
        errori = exc.errors()
        if not errori:
            return _json(422, "Richiesta non valida")
        messaggio = str(errori[0].get("msg", "Richiesta non valida"))
        prefisso = "Value error, "
        if messaggio.startswith(prefisso):
            messaggio = messaggio[len(prefisso):]
        return _json(422, messaggio)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        """vincoli di integrità del database -> HTTP 409 o 422"""
        messaggio = str(exc.orig).lower()
        if "unique" in messaggio or "foreign key" in messaggio:
            return _json(409, "Conflitto con una risorsa esistente o referenziata")
        return _json(422, "Vincolo dei dati non rispettato")

    @app.exception_handler(OperationalError)
    async def operational_error(_: Request, exc: OperationalError) -> JSONResponse:
        """errori database"""
        messaggio = str(exc.orig).lower()
        if "database is locked" in messaggio or "database table is locked" in messaggio:
            return _json(503,"Database occupato, riprovare",headers={"Retry-After": "1"})
        return _json(500, "Errore interno del database")
    
    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
        """errori inattesi -> HTTP 500"""
        return _json(500, "Errore del server")

