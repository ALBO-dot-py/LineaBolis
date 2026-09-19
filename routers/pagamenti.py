from fastapi import APIRouter, Query
from schemas.pagamento import PagamentoPanelRead, PagamentoRead, PagamentoRequest
from services import pagamenti as service
from .dependencies import RouterDependencies


def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo pagamenti

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per il modulo
    """
    router = APIRouter(prefix="/pagamenti", tags=["pagamenti"])
    T = deps.tipi()

    @router.get("", response_model=PagamentoPanelRead)
    async def pannello_pagamenti(db: T.Db,current_user: T.Nutrizionista,paziente_id: int | None = Query(None, gt=0)) -> PagamentoPanelRead:
        """Restituisce il pannello pagamenti del nutrizionista autenticato

        Se viene indicato un paziente, il riepilogo viene limitato a quel profilo

        Args:
            db: sessione database
            current_user: nutrizionista autenticato
            paziente_id: id del paziente a cui si riferisce la richiesta

        Returns:
            il riepilogo dei pagamenti visibile al nutrizionista

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
        """
        return await service.pannello_nutrizionista(db,nutrizionista_id=current_user.utente_id,paziente_id=paziente_id)

    @router.post("/{appuntamento_id}/registra", response_model=PagamentoRead)
    async def registra_pagamento(appuntamento_id: int,payload: PagamentoRequest,db: T.Db,current_user: T.Nutrizionista) -> PagamentoRead:
        """Registra il pagamento relativo all’appuntamento indicato

        Il pagamento può essere registrato una sola volta, soltanto quando l’appuntamento è in uno stato pagabile; l’eventuale sconto non può superare il prezzo dell’appuntamento

        Args:
            appuntamento_id: id dell’appuntamento su cui eseguire l’operazione
            payload: dati del pagamento, compreso l’eventuale sconto applicato
            db: sessione database
            current_user: nutrizionista autenticato

        Returns:
            il pagamento registrato per l’appuntamento

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
            ForbiddenError: utente autenticato non possiede il ruolo nutrizionista (HTTP 403)
            NotFoundError: l’appuntamento indicato non esiste per il nutrizionista (HTTP 404)
            ConflictError: il pagamento è già stato registrato (HTTP 409)
            ValidationError: l’appuntamento non è ancora pagabile o lo sconto supera il prezzo (HTTP 422)
        """
        return await service.registra_pagamento(db,appuntamento_id=appuntamento_id,nutrizionista_id=current_user.utente_id,sconto_cent=payload.sconto_cent)

    return router
