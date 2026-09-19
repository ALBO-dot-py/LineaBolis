from fastapi import APIRouter, Response, status
from schemas.dato_medico import DatoMedicoCreate,DatoMedicoUpdate,DatoMedicoRead
from services import dati_medici as service
from .dependencies import RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo dati medici

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(tags=["dati-medici"])
    T = deps.tipi()

    @router.post("/pazienti/{paziente_id}/dati-medici",response_model=DatoMedicoRead,status_code=status.HTTP_201_CREATED,)
    async def crea_dato_medico(paziente_id: int,payload: DatoMedicoCreate,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Crea un nuovo dato medico per il paziente indicato

        Il nutrizionista autenticato viene passato al servizio per verificare il contesto di accesso al paziente

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            payload: dati del nuovo elemento medico da registrare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il dato medico appena creato

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente o il dato medico richiesto non esiste (HTTP 404)
            ValidationError: la descrizione è vuota o non rispetta le regole applicative (HTTP 422)
        """
        return await service.crea_dato_medico(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,**payload.model_dump(),)

    @router.put("/pazienti/{paziente_id}/dati-medici/{dato_id}",response_model=DatoMedicoRead,status_code=status.HTTP_200_OK,)
    async def aggiorna_dato_medico(paziente_id: int,dato_id: int,payload: DatoMedicoUpdate,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Aggiorna un dato medico del paziente indicato

        Vengono applicati soltanto i campi presenti nella richiesta di aggiornamento

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            dato_id: id del dato medico su cui eseguire l’operazione
            payload: campi del dato medico da aggiornare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il dato medico con i valori aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente o il dato medico richiesto non esiste (HTTP 404)
            ValidationError: tipo o descrizione non sono validi (HTTP 422)
        """
        return await service.aggiorna_dato_medico(db,dato_id=dato_id,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,**payload.model_dump(exclude_unset=True),)

    @router.delete("/pazienti/{paziente_id}/dati-medici/{dato_id}",status_code=status.HTTP_204_NO_CONTENT,)
    async def elimina_dato_medico(paziente_id: int,dato_id: int,db: T.Db,current_user: T.Nutrizionista,) -> Response:
        """Elimina il dato medico indicato dal profilo del paziente

        Al termine dell’operazione non viene restituito alcun contenuto

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            dato_id: id del dato medico su cui eseguire l’operazione
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente o il dato medico richiesto non esiste (HTTP 404)
        """
        await service.elimina_dato_medico(db,dato_id=dato_id,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
