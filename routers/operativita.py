from typing import Annotated
from fastapi import APIRouter, Depends
from schemas.configurazione import ConfigurazioneAppRequest, ConfigurazioneAppResponse
from schemas.utente import PasswordChange
from services import configurazione as configurazione_service
from services import utenti as utenti_service
from .dependencies import CurrentUser, RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo configurazione

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per configurazione e cambio password
    """
    router = APIRouter(tags=["configurazione"])
    T = deps.tipi()

    AnyUser = Annotated[CurrentUser, Depends(deps.get_current_user)]

    @router.get("/configurazione", response_model=ConfigurazioneAppResponse)
    async def get_configuration(db: T.Db,_admin: T.Admin) -> ConfigurazioneAppResponse:
        """Restituisce la configurazione applicativa corrente

        L’endpoint è riservato a un amministratore autenticato

        Args:
            db: sessione database
            _admin: admin autenticato

        Returns:
            la configurazione applicativa attualmente salvata

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
        """
        return await configurazione_service.leggi_configurazione(db)

    @router.put("/configurazione", response_model=ConfigurazioneAppResponse)
    async def put_configuration(payload: ConfigurazioneAppRequest,db: T.Db,_admin: T.Admin) -> ConfigurazioneAppResponse:
        """Aggiorna la configurazione applicativa

        I nuovi valori vengono validati dallo schema della richiesta e poi salvati dal servizio di configurazione

        Args:
            payload: nuovi valori della configurazione applicativa
            db: sessione database
            _admin: admin autenticato

        Returns:
            la configurazione applicativa dopo l’aggiornamento

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
        """
        return await configurazione_service.aggiorna_configurazione(db, payload)

    @router.put("/me/password")
    async def change_password(payload: PasswordChange,db: T.Db,current_user: AnyUser) -> dict[str, bool]:
        """Cambia la password dell’utente autenticato dopo aver verificato quella attuale

        Dopo il salvataggio vengono revocate tutte le sessioni dell’utente, compresa quella usata per eseguire la richiesta

        Args:
            payload: password attuale e nuova password richieste per il cambio
            db: sessione database
            current_user: utente autenticato

        Returns:
            un dizionario che indica l’esito positivo dell’operazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            NotFoundError: l’utente associato alla sessione non esiste più (HTTP 404)
            InvalidCurrentPasswordError: la password attuale non corrisponde a quella salvata (HTTP 400)
            PasswordHashingUnavailableError: il servizio non riesce a generare l’hash della password (HTTP 503)
        """
        return await utenti_service.cambia_password(db,utente_id=current_user.utente_id,password_attuale=payload.password_attuale,nuova_password=payload.nuova_password)

    return router