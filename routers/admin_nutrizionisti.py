from fastapi import APIRouter, Query, Request, status
from schemas.admin import NutrizionistaAdminListItem,NutrizionistaCreateRequest,NutrizionistaCreateResponse,NutrizionistaUpdateRequest
from schemas.auth import LinkImpostazionePasswordResponse
from schemas.enums import StatoUtente
from schemas.utente import UtenteRead
from services import nutrizionista as service
from .dependencies import PagDep, RouterDependencies

def build_router(deps: RouterDependencies) -> APIRouter:
    router = APIRouter(prefix="/admin/nutrizionisti", tags=["admin-nutrizionisti"])
    T = deps.tipi()

    @router.get("", response_model=list[NutrizionistaAdminListItem])
    async def lista_nutrizionisti(db: T.Db,_: T.Admin,pag: PagDep,q: str | None = Query(None, max_length=100),stato_utente: StatoUtente | None = Query(None, alias="stato")) -> list[dict]:
        """Restituisce l’elenco dei nutrizionisti
        
        Args:
            db: sessione database
            _: admin autenticato
            pag: parametri di paginazione (skip e limit)
            q: testo opzionale usato per filtrare i risultati della ricerca
            stato_utente: stato utente opzionale con cui filtrare i risultati
        
        Returns:
            lista di nutrizionisti con le informazioni necessarie per la vista admin
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
        """
        return await service.lista_nutrizionisti(db, ricerca=q, stato=stato_utente, skip=pag.skip, limit=pag.limit)

    @router.post("", response_model=NutrizionistaCreateResponse, status_code=status.HTTP_201_CREATED)
    async def crea_nutrizionista(payload: NutrizionistaCreateRequest,request: Request,db: T.Db,_: T.Admin) -> dict:
        """Crea un nutrizionista        
        L’account viene creato disattivato e viene automaticamente generato un link per impostare la password
        
        Args:
            payload: dati necessari per creare il nuovo nutrizionista
            request: richiesta HTTP corrente
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati del nutrizionista creato, inclusi gli elementi previsti dal flusso di attivazione
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            ConflictError: email è già associata a un altro utente (HTTP 409)
            PasswordHashingUnavailableError: errore nella generazione dell’hash della password (HTTP 503)
        """
        return await service.crea_nutrizionista(db,base_url=str(request.base_url),**payload.model_dump())

    @router.put("/{nutrizionista_id}", response_model=UtenteRead)
    async def aggiorna_nutrizionista(nutrizionista_id: int,payload: NutrizionistaUpdateRequest,db: T.Db,_: T.Admin) -> UtenteRead:
        """Aggiorna i dati di un nutrizionista
        
        Args:
            nutrizionista_id: id del nutrizionista su cui eseguire l’operazione
            payload: campi dell’anagrafica del nutrizionista da aggiornare
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati aggiornati dell’utente nutrizionista
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: nutrizionista non esiste (HTTP 404)
            ConflictError: email è già associata a un altro utente (HTTP 409)
            ValidationError: dati violano una regola applicativa (HTTP 422)
        """
        return await service.aggiorna_anagrafica_nutrizionista(db,utente_id=nutrizionista_id,**payload.model_dump(exclude_unset=True))

    @router.patch("/{nutrizionista_id}/attiva", response_model=UtenteRead)
    async def attiva_nutrizionista(nutrizionista_id: int,db: T.Db,_: T.Admin) -> UtenteRead:
        """attiva l’account del nutrizionista indicato
               
        Args:
            nutrizionista_id: id del nutrizionista su cui eseguire l’operazione
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati del nutrizionista
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: nutrizionista non esiste (HTTP 404)
        """
        return await service.imposta_stato_nutrizionista(db, utente_id=nutrizionista_id, stato=StatoUtente.attivo)
    
    @router.patch("/{nutrizionista_id}/disattiva", response_model=UtenteRead)
    async def disattiva_nutrizionista(nutrizionista_id: int,db: T.Db,_: T.Admin) -> UtenteRead:
        """disattiva l’account del nutrizionista indicato
        La disattivazione è consentita SOLO SE non risultano pazienti assegnati
        Il cambio di stato revoca tutte le sessioni del nutrizionista
        
        Args:
            nutrizionista_id: id del nutrizionista su cui eseguire l’operazione
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati del nutrizionista
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: nutrizionista non esiste (HTTP 404)
            ValidationError: dati violano una regola applicativa (HTTP 422)
        """
        return await service.disabilita_nutrizionista(db, utente_id=nutrizionista_id)

    @router.post("/{nutrizionista_id}/logout-all")
    async def logout_all_nutrizionista(nutrizionista_id: int,db: T.Db,_: T.Admin) -> dict[str, bool]:
        """Revoca tutte le sessioni attive del nutrizionista indicato
                
        Args:
            nutrizionista_id: id del nutrizionista su cui eseguire l’operazione
            db: sessione database
            _: admin autenticato
        
        Returns:
            dizionario con 'ok=True' se la revoca è stata completata
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: nutrizionista non esiste (HTTP 404)
        """
        await service.logout_all_nutrizionista(db, utente_id=nutrizionista_id)
        return {"ok": True}

    @router.post("/{nutrizionista_id}/imposta-password",response_model=LinkImpostazionePasswordResponse)
    async def genera_link_impostazione_password(nutrizionista_id: int,request: Request,db: T.Db,_: T.Admin) -> LinkImpostazionePasswordResponse:
        """Genera un nuovo link per impostare la password del nutrizionista
        La generazione sostituisce l’eventuale link precedente, disattiva l’account, imposta una password casuale non conosciuta dall’utente e revoca tutte le sessioni esistenti
        
        Args:
            nutrizionista_id: id del nutrizionista su cui eseguire l’operazione
            request: richiesta HTTP corrente
            db: sessione database
            _: admin autenticato
        
        Returns:
            link per impostare la password
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: nutrizionista non esiste (HTTP 404)
            PasswordHashingUnavailableError: errore nella generazione dell’hash della password (HTTP 503)
        """
        url = await service.genera_link_impostazione_password_nutrizionista(db,utente_id=nutrizionista_id,base_url=str(request.base_url))
        return LinkImpostazionePasswordResponse(url_impostazione_password=url)
    return router