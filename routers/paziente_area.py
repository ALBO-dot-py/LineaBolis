from datetime import date
from fastapi import APIRouter, Response, status
from schemas.appuntamento import AppuntamentoCreate,AppuntamentoResponse,MotivoAppuntamentoRequest,SlotPrenotabileResponse,TipoAppuntamentoRead
from schemas.dieta import DietaPazienteRead
from schemas.enums import Ruolo
from schemas.me import MeAppuntamentoCreateRequest,MeAppuntamentiPannelloResponse,MeProfiloResponse,MeProfiloUpdateRequest
from schemas.misurazione import ProgressiMisurazioniResponse
from schemas.dato_medico import DatoMedicoCreate,DatoMedicoUpdate,DatoMedicoRead
from schemas.pagamento import PagamentoPanelRead
from services import appuntamenti, dati_medici, diete, misurazioni, pagamenti, pazienti
from .dependencies import PagDep, RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router dell’area paziente

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per le operazioni del paziente autenticato
    """
    router = APIRouter(prefix="/me", tags=["me"])
    T = deps.tipi()

    @router.get("/profilo", response_model=MeProfiloResponse)
    async def leggi_profilo(db: T.Db,current_user: T.Paziente) -> dict:
        """Restituisce il profilo personale del paziente autenticato

        L’identificativo del paziente viene ricavato direttamente dalla sessione corrente

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            i dati del profilo personale del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo paziente (HTTP 403)
            NotFoundError: il profilo del paziente autenticato non esiste (HTTP 404)
        """
        return await pazienti.leggi_profilo_personale(db,paziente_id=current_user.utente_id)

    @router.put("/profilo", response_model=MeProfiloResponse)
    async def aggiorna_profilo(payload: MeProfiloUpdateRequest,db: T.Db,current_user: T.Paziente) -> dict:
        """Aggiorna il profilo personale del paziente autenticato

        Vengono applicati soltanto i campi effettivamente presenti nella richiesta

        Args:
            payload: campi del profilo personale che il paziente vuole aggiornare
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il profilo personale con i dati aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: email o codice fiscale entrano in conflitto con un altro utente (HTTP 409)
            ValidationError: uno dei campi aggiornati viola le regole applicative (HTTP 422)
        """
        return await pazienti.aggiorna_profilo_personale(db,paziente_id=current_user.utente_id,**payload.model_dump(exclude_unset=True))

    @router.get("/dieta", response_model=DietaPazienteRead)
    async def leggi_dieta_attiva(db: T.Db,current_user: T.Paziente) -> dict:
        """Restituisce la dieta attualmente attiva del paziente autenticato

        La ricerca usa direttamente l’identificativo del paziente associato alla sessione corrente

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            la dieta attiva del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: il paziente non ha una dieta attiva (HTTP 404)
        """
        return await diete.get_dieta_attiva(db,paziente_id=current_user.utente_id)

    @router.get("/misurazioni/progressi",response_model=ProgressiMisurazioniResponse)
    async def leggi_progressi_personali(db: T.Db,current_user: T.Paziente) -> dict:
        """Restituisce al paziente autenticato il riepilogo dei propri progressi

        La risposta confronta prima e ultima misurazione, calcola l’avanzamento verso il peso obiettivo quando disponibile e costruisce le serie storiche usando fino agli ultimi dieci valori per metrica

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il riepilogo dei progressi e delle serie storiche personali

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ValidationError: una misurazione salvata non consente di ricostruire correttamente i valori calcolati (HTTP 422)
        """
        return await misurazioni.leggi_progressi(db,paziente_id=current_user.utente_id,paziente_id_richiedente=current_user.utente_id)

    @router.get("/dati-medici", response_model=list[DatoMedicoRead])
    async def lista_dati_medici_personali(db: T.Db,current_user: T.Paziente,pag: PagDep) -> list[dict]:
        """Restituisce i dati medici del paziente autenticato

        La lettura è limitata ai dati del profilo corrente e rispetta la paginazione richiesta

        Args:
            db: sessione database
            current_user: paziente autenticato
            pag: parametri di paginazione

        Returns:
            la lista paginata dei dati medici personali

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
        """
        return await dati_medici.lista_dati_medici(db,paziente_id=current_user.utente_id,richiedente_id=current_user.utente_id,ruolo=Ruolo.paziente,tipo=None,skip=pag.skip,limit=pag.limit)

    @router.post("/dati-medici",response_model=DatoMedicoRead,status_code=status.HTTP_201_CREATED)
    async def crea_dato_medico_personale(payload: DatoMedicoCreate,db: T.Db,current_user: T.Paziente) -> dict:
        """Crea un nuovo dato medico nel profilo del paziente autenticato

        Il paziente viene ricavato dalla sessione e non deve essere specificato nella richiesta

        Args:
            payload: dati del nuovo elemento medico personale
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il dato medico appena creato

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ValidationError: la descrizione è vuota o non rispetta le regole applicative (HTTP 422)
        """
        return await dati_medici.crea_dato_medico(db,paziente_id=current_user.utente_id,**payload.model_dump())

    @router.put("/dati-medici/{dato_id}", response_model=DatoMedicoRead)
    async def aggiorna_dato_medico_personale(dato_id: int,payload: DatoMedicoUpdate,db: T.Db,current_user: T.Paziente) -> dict:
        """Aggiorna uno dei dati medici del paziente autenticato

        Vengono applicati soltanto i campi presenti nella richiesta di aggiornamento

        Args:
            dato_id: id del dato medico su cui eseguire l’operazione
            payload: campi del dato medico personale da aggiornare
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il dato medico con i valori aggiornati

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ValidationError: tipo o descrizione non sono validi (HTTP 422)
        """
        return await dati_medici.aggiorna_dato_medico(db,dato_id=dato_id,paziente_id=current_user.utente_id,**payload.model_dump(exclude_unset=True))

    @router.delete("/dati-medici/{dato_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def elimina_dato_medico_personale(dato_id: int,db: T.Db,current_user: T.Paziente) -> Response:
        """Elimina uno dei dati medici del paziente autenticato

        Al termine dell’operazione non viene restituito alcun contenuto

        Args:
            dato_id: id del dato medico su cui eseguire l’operazione
            db: sessione database
            current_user: paziente autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
        """
        await dati_medici.elimina_dato_medico(db,dato_id=dato_id,paziente_id=current_user.utente_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def _appointment_actor(db, paziente_id: int):
        """Costruisce l’attore appuntamenti associato al paziente autenticato

        Args:
            db: sessione database
            paziente_id: id del paziente

        Returns:
            attore applicativo del paziente e del nutrizionista associato

        Raises:
            NotFoundError: profilo del paziente non esiste (HTTP 404)
        """
        profilo = await pazienti.leggi_profilo_personale(db, paziente_id=paziente_id)
        return appuntamenti.AppointmentActor.paziente(paziente_id,nutrizionista_id=int(profilo["profilo"].nutrizionista_id))

    async def _appuntamento_dto(db, actor, app_id: int) -> AppuntamentoResponse:
        """Restituisce il DTO dell’appuntamento nel contesto dell’attore indicato

        Args:
            db: sessione database
            actor: attore applicativo autorizzato all’accesso
            app_id: id dell’appuntamento

        Returns:
            dati dell’appuntamento nel formato esposto dall’API
        """
        return await appuntamenti.leggi_appuntamento_dto(db, app_id=app_id, actor=actor)

    @router.get("/appuntamenti/tipi",response_model=list[TipoAppuntamentoRead])
    async def tipi_prenotabili(db: T.Db,current_user: T.Paziente) -> list[TipoAppuntamentoRead]:
        """Restituisce i tipi di appuntamento prenotabili dal paziente autenticato

        Il nutrizionista associato al paziente viene ricavato dal profilo prima di interrogare il servizio appuntamenti

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            la lista dei tipi di appuntamento disponibili per la prenotazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo paziente (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        return await appuntamenti.lista_tipi_appuntamento(db,actor=actor)

    @router.get("/appuntamenti/slot",response_model=list[SlotPrenotabileResponse])
    async def slot_prenotabili(tipo_appuntamento_id: int,data_da: date,db: T.Db,current_user: T.Paziente) -> list[SlotPrenotabileResponse]:
        """Restituisce gli slot che il paziente può prenotare

        Gli slot vengono calcolati per il tipo di appuntamento scelto e a partire dalla data indicata

        Args:
            tipo_appuntamento_id: id del tipo di appuntamento per cui calcolare gli slot
            data_da: data o data/ora iniziale da cui calcolare o filtrare i risultati
            db: sessione database
            current_user: paziente autenticato

        Returns:
            la lista degli slot disponibili per la prenotazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo paziente (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        return await appuntamenti.genera_slot_prenotabili(db,actor=actor,tipo_appuntamento_id=tipo_appuntamento_id,data_da=data_da)

    @router.get("/appuntamenti/pannello",response_model=MeAppuntamentiPannelloResponse)
    async def pannello_appuntamenti(db: T.Db,current_user: T.Paziente) -> MeAppuntamentiPannelloResponse:
        """Restituisce il pannello appuntamenti del paziente autenticato

        Il contesto dell’appuntamento viene costruito usando il nutrizionista associato al profilo del paziente

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il riepilogo degli appuntamenti del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        return await appuntamenti.pannello_paziente(db, actor=actor)

    @router.post("/appuntamenti",response_model=AppuntamentoResponse,status_code=status.HTTP_201_CREATED)
    async def crea_appuntamento(payload: MeAppuntamentoCreateRequest,db: T.Db,current_user: T.Paziente) -> AppuntamentoResponse:
        """Crea una nuova richiesta di appuntamento per il paziente autenticato

        Il paziente viene ricavato dalla sessione; lo slot deve essere prenotabile, rispettare disponibilità e vincoli temporali ed essere ancora libero

        Args:
            payload: dati necessari per creare o richiedere l’appuntamento
            db: sessione database
            current_user: paziente autenticato

        Returns:
            l’appuntamento appena creato nel formato esposto dall’API

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: lo slot selezionato non è più libero (HTTP 409)
            ValidationError: lo slot o i dati dell’appuntamento violano una regola applicativa (HTTP 422)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        result = await appuntamenti.crea_appuntamento(
            db,
            dati=AppuntamentoCreate(
                tipo_appuntamento_id=payload.tipo_appuntamento_id,
                data_ora_inizio=payload.data_ora_inizio,
                note_nutrizionista=None,
            ),
            actor=actor,
        )
        return await _appuntamento_dto(db, actor, result)

    @router.patch("/appuntamenti/{appuntamento_id}/accetta",response_model=AppuntamentoResponse)
    async def accetta_appuntamento(appuntamento_id: int,db: T.Db,current_user: T.Paziente) -> AppuntamentoResponse:
        """Accetta la proposta di appuntamento indicata per conto del paziente autenticato

        L’accettazione è ammessa soltanto quando la proposta è effettivamente in attesa della risposta del paziente e non è scaduta

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            db: sessione database
            current_user: paziente autenticato

        Returns:
            l’appuntamento aggiornato dopo l’accettazione

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: lo stato corrente non consente l’accettazione (HTTP 422)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        result = await appuntamenti.accetta_appuntamento(db, app_id=appuntamento_id, actor=actor)
        return await _appuntamento_dto(db, actor, result)

    @router.patch("/appuntamenti/{appuntamento_id}/rifiuta",response_model=AppuntamentoResponse)
    async def rifiuta_appuntamento(appuntamento_id: int,payload: MotivoAppuntamentoRequest,db: T.Db,current_user: T.Paziente) -> AppuntamentoResponse:
        """Rifiuta la proposta di appuntamento indicata per conto del paziente autenticato

        Il motivo è obbligatorio e il rifiuto è ammesso soltanto quando la proposta attende la risposta del paziente ed è ancora valida

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: motivo associato al rifiuto dell’appuntamento
            db: sessione database
            current_user: paziente autenticato

        Returns:
            l’appuntamento aggiornato dopo il rifiuto

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: il motivo manca o lo stato corrente non consente il rifiuto (HTTP 422)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        result = await appuntamenti.rifiuta_appuntamento(db,app_id=appuntamento_id,actor=actor,motivo=payload.motivo)
        return await _appuntamento_dto(db, actor, result)

    @router.patch("/appuntamenti/{appuntamento_id}/annulla",response_model=AppuntamentoResponse)
    async def annulla_appuntamento(appuntamento_id: int,payload: MotivoAppuntamentoRequest,db: T.Db,current_user: T.Paziente) -> AppuntamentoResponse:
        """Annulla un appuntamento del paziente autenticato registrando il motivo fornito

        La possibilità di annullamento dipende dallo stato e dall’orario dell’appuntamento; una cancellazione oltre il termine configurato può essere classificata come disdetta tardiva

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: motivo associato all’annullamento dell’appuntamento
            db: sessione database
            current_user: paziente autenticato

        Returns:
            l’appuntamento aggiornato dopo l’annullamento

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente non possiede il ruolo paziente o non è autorizzato alla risorsa (HTTP 403)
            NotFoundError: una risorsa necessaria all’operazione non esiste o non è più disponibile (HTTP 404)
            ConflictError: lo stato è cambiato nel frattempo, la proposta è scaduta o un vincolo di stato impedisce l’operazione (HTTP 409)
            ValidationError: il motivo manca oppure stato o orario non consentono l’annullamento (HTTP 422)
        """
        actor = await _appointment_actor(db, current_user.utente_id)
        result = await appuntamenti.annulla_appuntamento(db,app_id=appuntamento_id,actor=actor,motivo=payload.motivo)
        return await _appuntamento_dto(db, actor, result)

    @router.get("/pagamenti", response_model=PagamentoPanelRead)
    async def pannello_pagamenti(db: T.Db,current_user: T.Paziente) -> PagamentoPanelRead:
        """Restituisce il pannello pagamenti del paziente autenticato

        Il riepilogo viene limitato automaticamente al profilo associato alla sessione corrente

        Args:
            db: sessione database
            current_user: paziente autenticato

        Returns:
            il riepilogo dei pagamenti del paziente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo paziente (HTTP 403)
        """
        return await pagamenti.pannello_paziente(db,paziente_id=current_user.utente_id)

    return router
