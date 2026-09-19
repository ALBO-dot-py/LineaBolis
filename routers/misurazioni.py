from typing import Literal
from fastapi import APIRouter, Query, status
from schemas.misurazione import MisurazioneCreateRequest,MisurazioneResponse,ProgressiMisurazioniResponse
from services import misurazioni as service
from .dependencies import RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo misurazioni

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(tags=["misurazioni"])
    T = deps.tipi()

    @router.get("/pazienti/{paziente_id}/misurazioni",response_model=list[MisurazioneResponse],status_code=status.HTTP_200_OK)
    async def lista_misurazioni(paziente_id: int,db: T.Db,current_user: T.Nutrizionista,skip: int = Query(0, ge=0),limit: int = Query(10, ge=1, le=200),order: Literal["asc", "desc"] = Query("desc"),) -> list[dict]:
        """Restituisce le misurazioni registrate per un paziente

        I risultati possono essere paginati e ordinati cronologicamente nel verso richiesto

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato
            skip: numero di risultati iniziali da saltare; deve essere maggiore o uguale a zero
            limit: numero massimo di risultati da restituire, entro i limiti validati dall’endpoint
            order: ordinamento cronologico delle misurazioni: ''asc'' oppure ''desc''

        Returns:
            la lista delle misurazioni del paziente secondo paginazione e ordinamento

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il profilo del paziente indicato non esiste (HTTP 404)
            ValidationError: una misurazione salvata non consente di ricostruire correttamente i valori calcolati (HTTP 422)
        """
        return await service.lista_misurazioni(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,skip=skip,limit=limit,order=order,)

    @router.get("/pazienti/{paziente_id}/misurazioni/progressi",response_model=ProgressiMisurazioniResponse,status_code=status.HTTP_200_OK)
    async def leggi_progressi(paziente_id: int,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Restituisce il riepilogo dei progressi del paziente a partire dalle misurazioni disponibili

        La risposta confronta prima e ultima misurazione, calcola l’avanzamento verso il peso obiettivo quando disponibile e costruisce le serie storiche usando fino agli ultimi dieci valori per metrica

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il riepilogo dei progressi e delle serie storiche del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il profilo del paziente indicato non esiste (HTTP 404)
            ValidationError: una misurazione salvata non consente di ricostruire correttamente i valori calcolati (HTTP 422)
        """
        return await service.leggi_progressi(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,)

    @router.post("/pazienti/{paziente_id}/misurazioni",response_model=MisurazioneResponse,status_code=status.HTTP_201_CREATED,)
    async def crea_misurazione(paziente_id: int,payload: MisurazioneCreateRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Registra la misurazione del paziente per la data indicata

        Per ogni paziente viene mantenuta una sola misurazione per data: se esiste già viene aggiornata. La massa grassa viene ricalcolata usando età, sesso e le quattro pliche richieste

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            payload: valori della nuova misurazione da registrare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la misurazione appena registrata

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il profilo del paziente indicato non esiste (HTTP 404)
            ValidationError: la data precede la nascita del paziente o i dati antropometrici non consentono il calcolo (HTTP 422)
        """
        return await service.crea_misurazione(db,paziente_id=paziente_id,dati=payload,nutrizionista_id=current_user.utente_id,)

    return router
