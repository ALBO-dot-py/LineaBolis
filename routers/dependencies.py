from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated, Any, Protocol
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

class CurrentUser(Protocol):
    """Definisce il contratto minimo dell’utente autenticato usato dai router"""
    utente_id: int

DependencyCallable = Callable[..., Any]

@dataclass(frozen=True, slots=True)
class Paginazione:
    """Raccoglie i parametri di paginazione validati da FastAPI"""
    skip: int = Query(0, ge=0)
    limit: int = Query(50, ge=1, le=200)

PagDep = Annotated[Paginazione, Depends()]

@dataclass(frozen=True, slots=True)
class RouterDependencies:
    """Raccoglie le dipendenze condivise usate per costruire i router"""
    get_db: DependencyCallable
    get_current_user: DependencyCallable
    get_current_admin: DependencyCallable
    get_current_nutrizionista: DependencyCallable
    get_current_paziente: DependencyCallable

    def tipi(self) -> SimpleNamespace:
        """Restituisce gli alias Annotated condivisi dai router

        Returns:
            namespace con sessione database e dipendenze utente tipizzate
        """
        return SimpleNamespace(
            Db=Annotated[AsyncSession, Depends(self.get_db)],
            Admin=Annotated[CurrentUser, Depends(self.get_current_admin)],
            Nutrizionista=Annotated[
                CurrentUser,
                Depends(self.get_current_nutrizionista),
            ],
            Paziente=Annotated[CurrentUser, Depends(self.get_current_paziente)],
        )
