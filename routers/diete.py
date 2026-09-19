from fastapi import APIRouter, Query, Response, status
from schemas.dieta import ConsiderazioniFinaliRequest,DietaCreateRequest,DietaNutrizionistaRead,DietaStrutturaRequest,DietaUpdateRequest,DietePazienteNutrizionistaResponse,TemplateDietaRead,TemplateDietaSummary
from schemas.enums import TipoDieta
from services import diete as service
from .dependencies import PagDep, RouterDependencies

def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo diete

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(prefix="/diete", tags=["diete"])
    T = deps.tipi()

    @router.get("/templates", response_model=list[TemplateDietaSummary])
    async def lista_template(db: T.Db,current_user: T.Nutrizionista,pag: PagDep,tipo: TipoDieta | None = Query(None),) -> list[dict]:
        """Restituisce i template di dieta del nutrizionista autenticato

        I risultati possono essere filtrati per tipo di dieta e vengono restituiti secondo la paginazione richiesta

        Args:
            db: sessione database
            current_user: nutrizionista autenticato
            pag: parametri di paginazione
            tipo: tipo di dieta opzionale con cui filtrare i template

        Returns:
            una lista riassuntiva dei template di dieta disponibili

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.lista_template(db,nutrizionista_id=current_user.utente_id,tipo=tipo,skip=pag.skip,limit=pag.limit,)

    @router.post("/templates",response_model=TemplateDietaRead,status_code=status.HTTP_201_CREATED,)
    async def crea_template(payload: DietaStrutturaRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Salva un nuovo template di dieta

        La struttura ricevuta viene associata al nutrizionista autenticato per poter essere riutilizzata successivamente

        Args:
            payload: struttura completa del template di dieta da salvare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il template di dieta appena creato

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.salva_template(db,dati=payload,nutrizionista_id=current_user.utente_id,)

    @router.get("/templates/{template_id}", response_model=TemplateDietaRead)
    async def leggi_template(template_id: int,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Restituisce il dettaglio di un template di dieta

        Il template viene letto nel contesto del nutrizionista autenticato

        Args:
            template_id: id del template di dieta richiesto
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il template di dieta richiesto con la sua struttura completa

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
        """
        return await service.leggi_template(db,template_id=template_id,nutrizionista_id=current_user.utente_id,)

    @router.put("/templates/{template_id}", response_model=TemplateDietaRead)
    async def aggiorna_template(template_id: int,payload: DietaStrutturaRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Aggiorna la struttura di un template di dieta esistente

        Il salvataggio riutilizza lo stesso servizio impiegato per la creazione, specificando l’identificativo del template

        Args:
            template_id: id del template di dieta richiesto
            payload: nuova struttura da associare al template di dieta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il template di dieta con i dati aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
        """
        return await service.salva_template(db,template_id=template_id,dati=payload,nutrizionista_id=current_user.utente_id,)

    @router.delete("/templates/{template_id}",status_code=status.HTTP_204_NO_CONTENT,)
    async def elimina_template(template_id: int,db: T.Db,current_user: T.Nutrizionista,) -> Response:
        """Elimina il template di dieta indicato

        Al termine dell’operazione non viene restituito alcun contenuto

        Args:
            template_id: id del template di dieta richiesto
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
        """
        await service.elimina_template(db,template_id=template_id,nutrizionista_id=current_user.utente_id,)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/attiva",response_model=DietaNutrizionistaRead,status_code=status.HTTP_201_CREATED,)
    async def crea_dieta_attiva(payload: DietaCreateRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Crea una nuova dieta attiva per il paziente indicato

        Prima del salvataggio viene verificata l’associazione permanente tra paziente e nutrizionista; l’eventuale dieta attiva precedente viene archiviata automaticamente

        Args:
            payload: dati e struttura della dieta attiva da creare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la dieta attiva appena creata nel formato dedicato al nutrizionista

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
        """
        return await service.salva_dieta_attiva(db,dati=payload,nutrizionista_id=current_user.utente_id,)

    @router.put("/attiva/{dieta_id}",response_model=DietaNutrizionistaRead,)
    async def aggiorna_dieta_attiva(dieta_id: int,payload: DietaUpdateRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Sostituisce i dati e la struttura di una dieta attiva esistente

        La modifica è consentita soltanto sulla dieta ancora attiva e appartenente al nutrizionista autenticato

        Args:
            dieta_id: id della dieta su cui eseguire l’operazione
            payload: dati aggiornati della dieta attiva
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la dieta attiva con i dati aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
            ValidationError: la dieta non è più attiva (HTTP 422)
        """
        return await service.salva_dieta_attiva(db,dieta_id=dieta_id,dati=payload,nutrizionista_id=current_user.utente_id,)

    @router.get("/pazienti/{paziente_id}",response_model=DietePazienteNutrizionistaResponse,)
    async def leggi_diete_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Restituisce le diete associate a uno specifico paziente

        La vista è costruita per il nutrizionista autenticato e comprende le informazioni previste dal relativo pannello

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il riepilogo delle diete del paziente per il nutrizionista

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
        """
        return await service.get_diete_nutrizionista(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,)

    @router.get("/{dieta_id}", response_model=DietaNutrizionistaRead)
    async def leggi_dieta(dieta_id: int,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Restituisce il dettaglio della dieta indicata

        La lettura viene effettuata nel contesto del nutrizionista autenticato

        Args:
            dieta_id: id della dieta su cui eseguire l’operazione
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la dieta richiesta nel formato dedicato al nutrizionista

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
        """
        return await service.leggi_dieta(db,dieta_id=dieta_id,nutrizionista_id=current_user.utente_id,)

    @router.patch("/{dieta_id}/archivia", response_model=DietaNutrizionistaRead)
    async def archivia_dieta(dieta_id: int,payload: ConsiderazioniFinaliRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Archivia una dieta attiva e salva le eventuali considerazioni finali

        L’archiviazione valorizza data di fine e timestamp di chiusura; una dieta già archiviata non può essere archiviata di nuovo

        Args:
            dieta_id: id della dieta su cui eseguire l’operazione
            payload: considerazioni finali da associare all’archiviazione della dieta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la dieta dopo l’archiviazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
            ValidationError: la dieta è già archiviata (HTTP 422)
        """
        return await service.archivia_dieta(db,dieta_id=dieta_id,nutrizionista_id=current_user.utente_id,considerazioni_finali=payload.considerazioni_finali,)

    @router.patch("/{dieta_id}/considerazioni-finali",response_model=DietaNutrizionistaRead,)
    async def aggiorna_considerazioni_finali(dieta_id: int,payload: ConsiderazioniFinaliRequest,db: T.Db,current_user: T.Nutrizionista,) -> dict:
        """Aggiorna le considerazioni finali associate a una dieta

        Le considerazioni finali sono modificabili esclusivamente quando la dieta è già archiviata

        Args:
            dieta_id: id della dieta su cui eseguire l’operazione
            payload: nuove considerazioni finali da salvare sulla dieta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la dieta con le considerazioni finali aggiornate

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: la dieta o il template indicato non esiste nel contesto del nutrizionista (HTTP 404)
            ValidationError: la dieta non è archiviata (HTTP 422)
        """
        return await service.aggiorna_considerazioni_finali(db,dieta_id=dieta_id,nutrizionista_id=current_user.utente_id,considerazioni_finali=payload.considerazioni_finali,)

    return router
