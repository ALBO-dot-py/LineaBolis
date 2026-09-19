from datetime import date, datetime
from fastapi import APIRouter, Query, Response, status
from schemas.appuntamento import AppuntamentoCreate,AppuntamentoCreateRequest,AppuntamentoResponse,MotivoAppuntamentoRequest,SlotPrenotabileResponse,StatisticaEsitiMensiliRead,TipoAppuntamentoRead,TipoAppuntamentoWrite
from schemas.enums import StatoAppuntamento
from schemas.me import MeAppuntamentiPannelloResponse
from services import appuntamenti as service
from .dependencies import RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo appuntamenti

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per la gestione degli appuntamenti
    """
    router = APIRouter(prefix="/appuntamenti", tags=["appuntamenti"])
    T = deps.tipi()

    def actor_nutrizionista(current_user, *, paziente_id: int | None = None):
        """Costruisce l’attore appuntamenti per il nutrizionista autenticato

        Args:
            current_user: nutrizionista autenticato
            paziente_id: id opzionale del paziente associato all’operazione

        Returns:
            attore applicativo usato dal servizio appuntamenti
        """
        return service.AppointmentActor.nutrizionista(current_user.utente_id, paziente_id=paziente_id)

    async def dto(db, actor, app_id: int) -> AppuntamentoResponse:
        """Restituisce il DTO dell’appuntamento nel contesto dell’attore indicato

        Args:
            db: sessione database
            actor: attore applicativo autorizzato all’accesso
            app_id: id dell’appuntamento

        Returns:
            dati dell’appuntamento nel formato esposto dall’API
        """
        return await service.leggi_appuntamento_dto(db, app_id=app_id, actor=actor)

    @router.get("/statistiche/esiti",response_model=list[StatisticaEsitiMensiliRead])
    async def statistiche_esiti(db: T.Db, current_user: T.Nutrizionista) -> list[StatisticaEsitiMensiliRead]:
        """Restituisce le statistiche mensili sugli esiti degli appuntamenti

        Il riepilogo è calcolato sugli ultimi sei mesi per il nutrizionista autenticato

        Args:
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una lista di statistiche mensili relative agli esiti degli appuntamenti

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.esiti_ultimi_6_mesi(db, nutrizionista_id=current_user.utente_id)

    @router.get("/tipi", response_model=list[TipoAppuntamentoRead])
    async def lista_tipi(db: T.Db,current_user: T.Nutrizionista) -> list[TipoAppuntamentoRead]:
        """Restituisce i tipi di appuntamento configurati dal nutrizionista

        La lettura avviene nel contesto del nutrizionista autenticato

        Args:
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la lista dei tipi di appuntamento disponibili

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.lista_tipi_appuntamento(db,actor=actor_nutrizionista(current_user))

    @router.post("/tipi",response_model=TipoAppuntamentoRead,status_code=status.HTTP_201_CREATED)
    async def crea_tipo(payload: TipoAppuntamentoWrite,db: T.Db,current_user: T.Nutrizionista) -> TipoAppuntamentoRead:
        """Crea un nuovo tipo di appuntamento per il nutrizionista autenticato

        Il tipo definisce nome, durata, prezzo e comportamento di prenotazione; per uno stesso nutrizionista il nome deve essere univoco

        Args:
            payload: configurazione del nuovo tipo di appuntamento
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il tipo di appuntamento appena creato

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            ConflictError: esiste già una tipologia con lo stesso nome per il nutrizionista (HTTP 409)
        """
        return await service.crea_tipo_appuntamento(db,nutrizionista_id=current_user.utente_id,dati=payload)

    @router.put("/tipi/{tipo_id}", response_model=TipoAppuntamentoRead)
    async def aggiorna_tipo(tipo_id: int,payload: TipoAppuntamentoWrite,db: T.Db,current_user: T.Nutrizionista) -> TipoAppuntamentoRead:
        """Aggiorna un tipo di appuntamento esistente appartenente al nutrizionista autenticato

        Il nuovo nome non può entrare in conflitto con un’altra tipologia già configurata dallo stesso nutrizionista

        Args:
            tipo_id: id del tipo di appuntamento da modificare
            payload: nuova configurazione da applicare al tipo di appuntamento
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il tipo di appuntamento con i dati aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            NotFoundError: la tipologia indicata non esiste per il nutrizionista (HTTP 404)
            ConflictError: il nuovo nome è già usato da un’altra tipologia del nutrizionista (HTTP 409)
        """
        return await service.aggiorna_tipo_appuntamento(db,tipo_id=tipo_id,nutrizionista_id=current_user.utente_id,dati=payload)

    @router.delete("/tipi/{tipo_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def elimina_tipo(tipo_id: int,db: T.Db,current_user: T.Nutrizionista) -> Response:
        """Elimina il tipo di appuntamento indicato

        Al termine l’endpoint non restituisce un corpo di risposta

        Args:
            tipo_id: id del tipo di appuntamento da modificare
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            NotFoundError: la tipologia indicata non esiste per il nutrizionista (HTTP 404)
        """
        await service.elimina_tipo_appuntamento(db,tipo_id=tipo_id,nutrizionista_id=current_user.utente_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/slot", response_model=list[SlotPrenotabileResponse])
    async def lista_slot(tipo_appuntamento_id: int,data_da: date,db: T.Db,current_user: T.Nutrizionista) -> list[SlotPrenotabileResponse]:
        """Calcola gli slot prenotabili per un tipo di appuntamento a partire dalla data richiesta

        Il calcolo considera durata della tipologia, disponibilità ricorrenti, indisponibilità, appuntamenti già presenti e vincoli temporali configurati

        Args:
            tipo_appuntamento_id: id del tipo di appuntamento per cui calcolare gli slot
            data_da: data o data/ora iniziale da cui calcolare o filtrare i risultati
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            la lista degli slot disponibili per la prenotazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.genera_slot_prenotabili(db,actor=actor_nutrizionista(current_user),tipo_appuntamento_id=tipo_appuntamento_id,data_da=data_da)

    @router.get("", response_model=list[AppuntamentoResponse])
    async def lista_appuntamenti(response: Response,db: T.Db,current_user: T.Nutrizionista,paziente_id: int | None = Query(None, gt=0),stato_appuntamento: StatoAppuntamento | None = Query(None, alias="stato"),data_da: datetime | None = Query(None),data_a: datetime | None = Query(None),skip: int = Query(0, ge=0),limit: int = Query(500, gt=0, le=500)) -> list[AppuntamentoResponse]:
        """Restituisce gli appuntamenti del nutrizionista applicando i filtri richiesti

        Args:
            response: risposta HTTP su cui viene impostato l’header di paginazione 'X-Has-More'
            db: sessione database
            current_user: nutrizionista autenticato
            paziente_id: id del paziente a cui si riferisce la richiesta
            stato_appuntamento: stato opzionale con cui filtrare gli appuntamenti
            data_da: data o data/ora iniziale da cui calcolare o filtrare i risultati
            data_a: data/ora finale entro cui limitare gli appuntamenti restituiti
            skip: numero di risultati iniziali da saltare; deve essere maggiore o uguale a zero
            limit: numero massimo di risultati da restituire, entro i limiti validati dall’endpoint

        Returns:
            la lista degli appuntamenti che rispettano filtri e paginazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        items, has_more = await service.lista_appuntamenti_dto(db,actor=actor_nutrizionista(current_user, paziente_id=paziente_id),stato=stato_appuntamento,data_da=data_da,data_a=data_a,skip=skip,limit=limit)
        response.headers["X-Has-More"] = "true" if has_more else "false"
        return items

    @router.post("",response_model=AppuntamentoResponse,status_code=status.HTTP_201_CREATED)
    async def crea_appuntamento(payload: AppuntamentoCreateRequest,db: T.Db,current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Crea un nuovo appuntamento per il paziente indicato nella richiesta

        Lo slot deve rispettare disponibilità e vincoli temporali ed essere ancora libero. Lo stato iniziale dipende dall’attore che propone l’appuntamento e dalle regole della tipologia

        Args:
            payload: dati necessari per creare o richiedere l’appuntamento
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento appena creato nel formato esposto dall’API

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente, la tipologia o una risorsa necessaria non è disponibile (HTTP 404)
            ConflictError: lo slot selezionato non è più libero (HTTP 409)
            ValidationError: lo slot o i dati dell’appuntamento violano una regola applicativa (HTTP 422)
        """
        actor = actor_nutrizionista(current_user, paziente_id=payload.paziente_id)
        result = await service.crea_appuntamento(
            db,
            dati=AppuntamentoCreate(
                tipo_appuntamento_id=payload.tipo_appuntamento_id,
                data_ora_inizio=payload.data_ora_inizio,
                note_nutrizionista=payload.note_nutrizionista,
            ),
            actor=actor,
        )
        return await dto(db, actor, result)

    @router.patch("/{appuntamento_id}/accetta", response_model=AppuntamentoResponse)
    async def accetta_appuntamento(appuntamento_id: int, db: T.Db, current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Accetta la proposta di appuntamento indicata e restituisce il relativo stato aggiornato

        L’accettazione è ammessa solo dall’attore corretto e finché la proposta è ancora valida

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento aggiornato dopo l’accettazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste o non è visibile all’attore corrente (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: lo stato corrente non consente l’accettazione (HTTP 422)
        """
        actor = actor_nutrizionista(current_user)
        result = await service.accetta_appuntamento(db, app_id=appuntamento_id, actor=actor)
        return await dto(db, actor, result)

    @router.patch("/{appuntamento_id}/rifiuta", response_model=AppuntamentoResponse)
    async def rifiuta_appuntamento(appuntamento_id: int,payload: MotivoAppuntamentoRequest,db: T.Db,current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Rifiuta la proposta di appuntamento indicata registrando il motivo fornito

        Il rifiuto è consentito solo all’attore che deve rispondere e finché la proposta non è già scaduta o passata a un altro stato

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: motivo associato al rifiuto dell’appuntamento
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento aggiornato dopo il rifiuto

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste o non è visibile all’attore corrente (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: il motivo manca o lo stato corrente non consente il rifiuto (HTTP 422)
        """
        actor = actor_nutrizionista(current_user)
        result = await service.rifiuta_appuntamento(db, app_id=appuntamento_id, actor=actor, motivo=payload.motivo)
        return await dto(db, actor, result)

    @router.patch("/{appuntamento_id}/annulla", response_model=AppuntamentoResponse)
    async def annulla_appuntamento(appuntamento_id: int,payload: MotivoAppuntamentoRequest,db: T.Db,current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Annulla l’appuntamento indicato registrando il motivo fornito

        Le regole applicate dipendono da stato, attore, orario dell’appuntamento e presenza di un pagamento già registrato

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: motivo associato all’annullamento dell’appuntamento
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento aggiornato dopo l’annullamento

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste o non è visibile all’attore corrente (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: il motivo manca oppure stato, attore o orario non consentono l’annullamento (HTTP 422)
        """
        actor = actor_nutrizionista(current_user)
        result = await service.annulla_appuntamento(db, app_id=appuntamento_id, actor=actor, motivo=payload.motivo)
        return await dto(db, actor, result)

    @router.patch("/{appuntamento_id}/mancata-presenza",response_model=AppuntamentoResponse)
    async def mancata_presenza(appuntamento_id: int,payload: MotivoAppuntamentoRequest,db: T.Db,current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Segna un appuntamento confermato come mancata presenza e ne registra il motivo

        L’operazione è riservata al nutrizionista ed è ammessa soltanto nella finestra temporale prevista dal servizio

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: motivo da registrare insieme alla mancata presenza
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento aggiornato dopo la registrazione della mancata presenza

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: l’appuntamento non è confermato o la marcatura avviene fuori dalla finestra consentita (HTTP 422)
        """
        actor = actor_nutrizionista(current_user)
        result = await service.marca_mancata_presenza(db, app_id=appuntamento_id, actor=actor, motivo=payload.motivo)
        return await dto(db, actor, result)

    @router.patch("/{appuntamento_id}/eseguito", response_model=AppuntamentoResponse)
    async def marca_eseguito(appuntamento_id: int, db: T.Db, current_user: T.Nutrizionista) -> AppuntamentoResponse:
        """Segna un appuntamento confermato come effettuato

        L’operazione è riservata al nutrizionista ed è ammessa soltanto nella finestra temporale prevista dal servizio

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            l’appuntamento aggiornato dopo la conferma dell’esecuzione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: l’appuntamento non è confermato o la marcatura avviene fuori dalla finestra consentita (HTTP 422)
        """
        actor = actor_nutrizionista(current_user)
        result = await service.marca_appuntamento_eseguito(db, app_id=appuntamento_id, actor=actor)
        return await dto(db, actor, result)

    @router.get("/pazienti/{paziente_id}/pannello",response_model=MeAppuntamentiPannelloResponse)
    async def pannello_paziente(paziente_id: int,db: T.Db,current_user: T.Nutrizionista) -> dict:
        """Restituisce il pannello appuntamenti di uno specifico paziente

        Il servizio verifica l’appartenenza del paziente al nutrizionista autenticato prima di costruire il riepilogo

        Args:
            paziente_id: id del paziente a cui si riferisce la richiesta
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il riepilogo degli appuntamenti del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo nutrizionista o non è autorizzato alla risorsa (HTTP 403)
        """
        return await service.pannello_paziente(
            db,
            actor=actor_nutrizionista(
                current_user, paziente_id=paziente_id
            ),
            verifica_appartenenza=True,
        )

    return router
