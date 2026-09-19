from fastapi import APIRouter, Query, Request, status
from schemas.auth import LinkImpostazionePasswordResponse
from schemas.paziente import PazienteAnagraficaResponse,PazienteCreateRequest,PazienteCreateResponse,PazienteDetailResponse,PazienteUpdateRequest
from schemas.utente import UtenteRead
from services import pazienti as service
from .dependencies import PagDep, RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo pazienti

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(prefix="/pazienti", tags=["pazienti"])
    T = deps.tipi()

    @router.get("", response_model=list[PazienteDetailResponse])
    async def lista_pazienti(db: T.Db,current_user: T.Nutrizionista,pag: PagDep,includi_eliminati: bool = Query(False),cerca: str | None = Query(None, min_length=2)) -> list[dict]:
        """Restituisce i pazienti associati al nutrizionista autenticato

        La ricerca può includere anche i profili disabilitati, applicare un filtro testuale e usare la paginazione richiesta

        Args:
            db: sessione database
            current_user: nutrizionista autenticato
            pag: parametri di paginazione
            includi_eliminati: se ''True'', include anche i pazienti disabilitati nei risultati
            cerca: testo opzionale usato per cercare tra i pazienti

        Returns:
            la lista dei pazienti che rispettano i filtri applicati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.lista_pazienti(db,nutrizionista_id=current_user.utente_id,includi_disabilitati=includi_eliminati,cerca=cerca,skip=pag.skip,limit=pag.limit)

    @router.post("", response_model=PazienteCreateResponse, status_code=status.HTTP_201_CREATED)
    async def crea_paziente(payload: PazienteCreateRequest,request: Request,db: T.Db,current_user: T.Nutrizionista) -> dict:
        """Crea un nuovo paziente associandolo in modo permanente al nutrizionista autenticato

        Il nuovo account nasce disattivato; email e codice fiscale devono essere univoci e la risposta include il link monouso per impostare la password

        Args:
            payload: dati necessari per creare il nuovo paziente
            request: richiesta HTTP corrente
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            i dati del paziente appena creato e le informazioni previste dal flusso di onboarding

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            ConflictError: email o codice fiscale sono già associati a un altro utente (HTTP 409)
            PasswordHashingUnavailableError: il servizio non riesce a generare l’hash della password (HTTP 503)
        """
        return await service.crea_paziente(db,nutrizionista_id=current_user.utente_id,base_url=str(request.base_url),**payload.model_dump())

    @router.get("/{paziente_id}/anagrafica", response_model=PazienteAnagraficaResponse)
    async def leggi_anagrafica_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> dict:
        """Restituisce l’anagrafica completa del paziente indicato

        L’accesso viene eseguito nel contesto del nutrizionista autenticato

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’anagrafica completa del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
        """
        return await service.leggi_anagrafica_completa(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id)

    @router.get("/{paziente_id}", response_model=PazienteDetailResponse)
    async def leggi_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> dict:
        """Restituisce il dettaglio del paziente indicato

        Il paziente viene letto nel contesto del nutrizionista autenticato

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il dettaglio del paziente richiesto

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
        """
        return await service.leggi_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id)
    
    @router.put("/{paziente_id}", response_model=PazienteDetailResponse)
    async def aggiorna_paziente(paziente_id: int,payload: PazienteUpdateRequest,db: T.Db,current_user: T.Nutrizionista) -> dict:
        """Aggiorna i dati del paziente indicato

        Vengono applicati soltanto i campi effettivamente presenti nella richiesta

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            payload: campi del paziente da aggiornare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il dettaglio del paziente con i dati aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
            ConflictError: email o codice fiscale entrano in conflitto con un altro utente (HTTP 409)
            ValidationError: uno dei campi aggiornati viola le regole applicative (HTTP 422)
        """
        return await service.aggiorna_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,**payload.model_dump(exclude_unset=True))

    @router.patch("/{paziente_id}/attiva", response_model=UtenteRead)
    async def attiva_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> UtenteRead:
        """Riattiva il paziente indicato

        L’operazione viene eseguita dal nutrizionista a cui il paziente è associato

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            i dati utente del paziente dopo la riattivazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
        """
        return await service.abilita_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id)

    @router.patch("/{paziente_id}/disattiva", response_model=UtenteRead)
    async def disattiva_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> UtenteRead:
        """Disattiva il paziente indicato, verificando che appartenga al nutrizionista autenticato

        Il cambio di stato revoca automaticamente tutte le sessioni del paziente e impedisce nuovi accessi finché l’account non viene riattivato

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            i dati utente del paziente dopo la disattivazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
        """
        return await service.disabilita_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id)

    @router.post("/{paziente_id}/imposta-password",response_model=LinkImpostazionePasswordResponse)
    async def genera_link_impostazione_password(paziente_id: int,request: Request,db: T.Db,current_user: T.Nutrizionista) -> LinkImpostazionePasswordResponse:
        """Genera un nuovo link monouso per permettere al paziente di impostare la password

        La generazione sostituisce l’eventuale link precedente, disattiva l’account, imposta una password casuale non conosciuta dall’utente e revoca tutte le sessioni esistenti

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            request: richiesta HTTP corrente
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il link da usare per completare l’impostazione della password

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
            PasswordHashingUnavailableError: il servizio non riesce a generare l’hash della password (HTTP 503)
        """
        url = await service.genera_link_impostazione_password_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id,base_url=str(request.base_url))
        return LinkImpostazionePasswordResponse(url_impostazione_password=url)

    @router.post("/{paziente_id}/logout-all")
    async def logout_all_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> dict[str, bool]:
        """Revoca tutte le sessioni attive del paziente indicato

        Il nutrizionista può così forzare la disconnessione del proprio paziente da tutti i dispositivi

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            un dizionario con ''ok=True'' quando la revoca è stata completata

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente indicato non esiste (HTTP 404)
        """
        await service.logout_all_paziente(db,paziente_id=paziente_id,nutrizionista_id=current_user.utente_id)
        return {"ok": True}

    return router
