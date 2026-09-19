from fastapi import APIRouter, Query, Request
from schemas.admin import AdminPazienteListItem
from schemas.auth import LinkImpostazionePasswordResponse
from schemas.enums import StatoUtente
from schemas.utente import UtenteRead
from services import pazienti as service
from .dependencies import PagDep, RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    router = APIRouter(prefix="/admin/pazienti", tags=["admin-pazienti"])
    T = deps.tipi()

    @router.get("", response_model=list[AdminPazienteListItem])
    async def lista_pazienti(db: T.Db,_: T.Admin,pag: PagDep,q: str | None = Query(None, max_length=100),stato_utente: StatoUtente | None = Query(None, alias="stato"),nutrizionista_id: int | None = Query(None, gt=0)) -> list[dict]:
        """Restituisce l’elenco dei pazienti per la vista admin
        
        Args:
            db: sessione database
            _: admin autenticato
            pag: parametri di paginazione (skip e limit)
            q: testo opzionale usato per filtrare i risultati della ricerca
            stato_utente: stato utente opzionale con cui filtrare i risultati
            nutrizionista_id: id del nutrizionista opzionale con cui filtrare i pazienti
        
        Returns:
            lista pazienti con le informazioni previste per la vista admin
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
        """
        return await service.lista_pazienti_admin(db,ricerca=q,stato=stato_utente,nutrizionista_id=nutrizionista_id,skip=pag.skip,limit=pag.limit)

    @router.patch("/{paziente_id}/attiva", response_model=UtenteRead)
    async def attiva_paziente(paziente_id: int, db: T.Db, _: T.Admin) -> UtenteRead:
        """attiva il paziente indicato
              
        Args:
            paziente_id: id del paziente 
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati aggiornati del paziente dopo la riattivazione.
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: paziente non esiste (HTTP 404)
        """
        return await service.imposta_stato_paziente(db, paziente_id=paziente_id, stato=StatoUtente.attivo)

    @router.patch("/{paziente_id}/disattiva", response_model=UtenteRead)
    async def disattiva_paziente(paziente_id: int, db: T.Db, _: T.Admin) -> UtenteRead:
        """disattiva il paziente indicato
        
        Args:
            paziente_id: id del paziente 
            db: sessione database
            _: admin autenticato
        
        Returns:
            dati del paziente

        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: paziente non esiste (HTTP 404)
        """
        return await service.imposta_stato_paziente(db, paziente_id=paziente_id, stato=StatoUtente.disattivo)

    @router.post("/{paziente_id}/imposta-password",response_model=LinkImpostazionePasswordResponse)
    async def genera_link_impostazione_password(paziente_id: int,request: Request,db: T.Db,_: T.Admin) -> LinkImpostazionePasswordResponse:
        """Genera un nuovo link monouso per impostare la password del paziente.
        
        La generazione sostituisce l’eventuale link precedente, disattiva l’account, imposta una password casuale non conosciuta dall’utente e revoca tutte le sessioni esistenti.
        
        Args:
            request: richiesta HTTP corrente
            paziente_id: id del paziente 
            db: sessione database
            _: admin autenticato
        
        Returns:
            link per impostare la password
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: paziente non esiste (HTTP 404)
            PasswordHashingUnavailableError: errore nella generazione dell’hash della password (HTTP 503)
        """
        url = await service.genera_link_impostazione_password_paziente(db,paziente_id=paziente_id,base_url=str(request.base_url))
        return LinkImpostazionePasswordResponse(url_impostazione_password=url)

    @router.post("/{paziente_id}/logout-all")
    async def logout_all_paziente(paziente_id: int,db: T.Db,_: T.Admin) -> dict[str, bool]:
        """revoca tutte le sessioni attive del paziente indicato
                
        Args:
            paziente_id: id del paziente 
            db: sessione database
            _: admin autenticato
        
        Returns:
            dizionario con 'ok=True' se la revoca è stata completata
        
        Raises:
            HTTPException: bearer Token assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo admin (HTTP 403)
            NotFoundError: paziente non esiste (HTTP 404)
        """
        await service.logout_all_paziente(db, paziente_id=paziente_id)
        return {"ok": True}

    return router
