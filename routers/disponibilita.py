from fastapi import APIRouter, Response, status
from schemas.disponibilita import DisponibilitaCreate,DisponibilitaRead,IndisponibilitaCreate,IndisponibilitaRead
from services import disponibilita as service
from .dependencies import RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo disponibilita

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(tags=["disponibilita"])
    T = deps.tipi()

    @router.get("/disponibilita", response_model=list[DisponibilitaRead])
    async def lista_disponibilita(db: T.Db,current_user: T.Nutrizionista) -> list[DisponibilitaRead]:
        """Restituisce le fasce di disponibilità del nutrizionista autenticato

        Le disponibilità rappresentano gli intervalli ricorrenti o configurati usati per il calcolo degli slot

        Args:
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la lista delle fasce di disponibilità configurate

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.lista_disponibilita(db, nutrizionista_id=current_user.utente_id)

    @router.post("/disponibilita",response_model=DisponibilitaRead,status_code=status.HTTP_201_CREATED)
    async def crea_disponibilita(payload: DisponibilitaCreate,db: T.Db,current_user: T.Nutrizionista) -> DisponibilitaRead:
        """Crea una fascia di disponibilità ricorrente per il nutrizionista autenticato

        Le fasce sovrapposte non sono ammesse; quelle esattamente adiacenti nello stesso giorno vengono unite automaticamente in un unico intervallo

        Args:
            payload: dati della fascia di disponibilità da creare o estendere
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la fascia di disponibilità risultante dall’operazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            ConflictError: la nuova fascia si sovrappone a una disponibilità già configurata (HTTP 409)
        """
        return await service.crea_disponibilita(db,nutrizionista_id=current_user.utente_id,dati=payload)

    @router.delete("/disponibilita/{disponibilita_id}",status_code=status.HTTP_204_NO_CONTENT)
    async def elimina_disponibilita(disponibilita_id: int,db: T.Db,current_user: T.Nutrizionista) -> Response:
        """Elimina una fascia di disponibilità ricorrente del nutrizionista

        La fascia non viene rimossa se l’operazione lascerebbe scoperti appuntamenti futuri ancora da gestire o effettuare

        Args:
            disponibilita_id: id della fascia di disponibilità da eliminare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: la rimozione lascerebbe scoperti appuntamenti futuri ancora attivi (HTTP 409)
        """
        await service.elimina_disponibilita(db,disp_id=disponibilita_id,nutrizionista_id=current_user.utente_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/indisponibilita", response_model=list[IndisponibilitaRead])
    async def lista_indisponibilita(db: T.Db,current_user: T.Nutrizionista) -> list[IndisponibilitaRead]:
        """Restituisce i periodi di indisponibilità del nutrizionista autenticato

        Questi periodi vengono usati per escludere intervalli che altrimenti risulterebbero disponibili

        Args:
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la lista dei periodi di indisponibilità configurati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.lista_indisponibilita(db, nutrizionista_id=current_user.utente_id)

    @router.post("/indisponibilita",response_model=IndisponibilitaRead,status_code=status.HTTP_201_CREATED)
    async def crea_indisponibilita(payload: IndisponibilitaCreate,db: T.Db,current_user: T.Nutrizionista) -> IndisponibilitaRead:
        """Registra un periodo non ricorrente di indisponibilità del nutrizionista

        Il periodo deve avere almeno una parte futura e non può sovrapporsi ad appuntamenti ancora da gestire; il motivo viene conservato insieme all’intervallo

        Args:
            payload: intervallo di indisponibilità da registrare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il periodo di indisponibilità appena creato

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            ConflictError: il periodo si sovrappone ad appuntamenti ancora da gestire (HTTP 409)
            ValidationError: il periodo è già completamente trascorso (HTTP 422)
        """
        return await service.crea_indisponibilita(db,nutrizionista_id=current_user.utente_id,dati=payload)

    @router.delete("/indisponibilita/{indisponibilita_id}",status_code=status.HTTP_204_NO_CONTENT)
    async def elimina_indisponibilita(indisponibilita_id: int,db: T.Db,current_user: T.Nutrizionista) -> Response:
        """Elimina il periodo di indisponibilità indicato

        Al termine dell’operazione non viene restituito alcun contenuto

        Args:
            indisponibilita_id: id del periodo di indisponibilità da eliminare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
        """
        await service.elimina_indisponibilita(db,indisp_id=indisponibilita_id,nutrizionista_id=current_user.utente_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
