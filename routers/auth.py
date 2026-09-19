from dataclasses import dataclass
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.auth import ImpostaPasswordRequest, LoginRequest, LoginResponse
from schemas.enums import Ruolo
from schemas.utente import UtenteRead
from services import auth as service
from services import utenti as utenti_service
from services.exceptions import ForbiddenError
from .dependencies import DependencyCallable, RouterDependencies

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthDependencies:
    """Raccoglie le dipendenze FastAPI usate per autenticazione e autorizzazione"""
    get_current_user: DependencyCallable
    get_current_admin: DependencyCallable
    get_current_nutrizionista: DependencyCallable
    get_current_paziente: DependencyCallable

def _unauthorized() -> HTTPException:
    """Restituisce l’errore HTTP 401 standard per autenticazione non valida

    Returns:
        errore HTTP 401 con challenge Bearer
    """
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Non autenticato",headers={"WWW-Authenticate": "Bearer"})

def build_auth_dependencies(get_db: DependencyCallable) -> AuthDependencies:
    """Costruisce le dipendenze condivise di autenticazione e autorizzazione

    Args:
        get_db: dipendenza usata per ottenere la sessione database

    Returns:
        dipendenze per utente corrente e controlli di ruolo
    """
    Db = Annotated[AsyncSession, Depends(get_db)]
    Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]

    async def get_current_user(db: Db,credentials: Credentials) -> service.AuthenticatedUser:
        """Restituisce l’utente associato al token Bearer della richiesta

        La scadenza per inattività della sessione viene rinnovata quando necessario

        Args:
            db: sessione database
            credentials: credenziali Bearer ricevute dalla richiesta

        Returns:
            utente autenticato associato alla sessione corrente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
        """
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise _unauthorized()
        current_user = await service.authenticate_token(db,token=credentials.credentials)
        if current_user is None:
            raise _unauthorized()

        # Il rinnovo (solo se necessario) è completato prima di restituire l'utente
        # Se il DB è momentaneamente occupato il rinnovo verrà ritentato alla richiesta successiva
        if current_user.should_renew:
            try:
                await service.rinnova_sessione(db, token_hash=current_user.token_hash)
            except OperationalError:
                await db.rollback()
        return current_user
    CurrentUser = Annotated[service.AuthenticatedUser,Depends(get_current_user)]

    def require_role(role: Ruolo) -> DependencyCallable:
        """Costruisce una dipendenza che richiede il ruolo indicato

        Args:
            role: ruolo richiesto per accedere alla risorsa

        Returns:
            dipendenza FastAPI che verifica il ruolo dell’utente autenticato
        """
        async def dependency(current_user: CurrentUser) -> service.AuthenticatedUser:
            """Verifica che l’utente autenticato possieda il ruolo richiesto

            Args:
                current_user: utente autenticato

            Returns:
                utente autenticato autorizzato

            Raises:
                ForbiddenError: utente autenticato non possiede il ruolo richiesto (HTTP 403)
            """
            if current_user.ruolo != role:
                raise ForbiddenError("Ruolo non autorizzato")
            return current_user
        return dependency
    
    return AuthDependencies(
        get_current_user=get_current_user,
        get_current_admin=require_role(Ruolo.admin),
        get_current_nutrizionista=require_role(Ruolo.nutrizionista),
        get_current_paziente=require_role(Ruolo.paziente),
    )

def build_router(deps: RouterDependencies) -> APIRouter:
    """Costruisce il router del modulo autenticazione

    Args:
        deps: dipendenze condivise usate dal router

    Returns:
        router FastAPI configurato per login, password e gestione delle sessioni
    """
    router = APIRouter(prefix="/auth", tags=["auth"])
    T = deps.tipi()
    CurrentUser = Annotated[service.AuthenticatedUser,Depends(deps.get_current_user)]

    @router.post("/login", response_model=LoginResponse)
    async def login(payload: LoginRequest,db: T.Db) -> LoginResponse:
        """Autentica l’utente tramite email e password e apre una nuova sessione

        Credenziali errate, utente inesistente e account disattivato producono volutamente lo stesso errore 401. La sessione rispetta sia la scadenza per inattività sia la durata assoluta configurata

        Args:
            payload: credenziali email e password usate per l’accesso
            db: sessione database

        Returns:
            i dati della sessione appena creata, incluso il token di autenticazione

        Raises:
            HTTPException: email/password non sono valide oppure l’account è disattivato (HTTP 401)
        """
        result = await service.login(db,email=str(payload.email),password=payload.password)
        if result is None:
            raise _unauthorized()
        return result

    @router.post("/imposta-password",status_code=status.HTTP_204_NO_CONTENT)
    async def imposta_password(payload: ImpostaPasswordRequest,db: T.Db) -> Response:
        """Imposta una nuova password usando il token monouso ricevuto nella richiesta

        Il token deve esistere, non essere scaduto e non essere già stato usato. Un esito positivo attiva l’account, revoca le sessioni precedenti e consuma definitivamente il token

        Args:
            payload: token di impostazione password e nuova password da salvare
            db: sessione database

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            ValidationError: il link è inesistente, scaduto o già utilizzato (HTTP 422)
            PasswordHashingUnavailableError: il servizio non riesce a generare l’hash della password (HTTP 503)
        """
        await utenti_service.imposta_password_con_token(db,token=payload.token,nuova_password=payload.nuova_password)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/logout",status_code=status.HTTP_204_NO_CONTENT)
    async def logout(db: T.Db,current_user: CurrentUser) -> Response:
        """Termina la sessione corrente invalidando il token usato per la richiesta

        Dopo la revoca, lo stesso token non può più essere usato per autenticarsi

        Args:
            db: sessione database
            current_user: utente autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
        """
        await service.logout(db,token_hash=current_user.token_hash)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/logout-all",status_code=status.HTTP_204_NO_CONTENT)
    async def logout_all(db: T.Db,current_user: CurrentUser) -> Response:
        """Revoca tutte le sessioni attive dell’utente autenticato

        L’operazione invalida i token associati all’utente su tutti i dispositivi

        Args:
            db: sessione database
            current_user: utente autenticato

        Returns:
            una risposta vuota con stato HTTP 204

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
        """
        await service.logout_all(db, utente_id=current_user.utente_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/me", response_model=UtenteRead)
    async def me(current_user: CurrentUser) -> UtenteRead:
        """Restituisce i dati dell’utente autenticato

        La risposta viene ricavata direttamente dalle informazioni già validate dalla dipendenza di autenticazione

        Args:
            current_user: utente autenticato

        Returns:
            il profilo dell’utente associato alla sessione corrente

        Raises:
            HTTPException: token Bearer assente, scaduto o non valido (HTTP 401)
        """
        return current_user.utente

    return router