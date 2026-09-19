from fastapi import APIRouter, FastAPI
from . import admin_nutrizionisti,admin_pazienti,appuntamenti,auth,dati_medici,diete,disponibilita,misurazioni,operativita,paziente_area,pazienti,pagamenti
from .auth import AuthDependencies, build_auth_dependencies
from .dependencies import RouterDependencies
from .error_handlers import register_exception_handlers

_BUILDERS = (
    auth.build_router,
    admin_nutrizionisti.build_router,
    admin_pazienti.build_router,
    pazienti.build_router,
    dati_medici.build_router,
    misurazioni.build_router,
    diete.build_router,
    disponibilita.build_router,
    appuntamenti.build_router,
    pagamenti.build_router,
    paziente_area.build_router,
    operativita.build_router,
)

def build_api_router(dependencies: RouterDependencies) -> APIRouter:
    """Costruisce il router API principale e ci include tutti i router singoli/funzionali"""
    router = APIRouter()
    for builder in _BUILDERS:
        router.include_router(builder(dependencies))
    return router

def install_routers(app: FastAPI,dependencies: RouterDependencies,*,prefix: str = "/api/v1") -> None:
    """Registra in FastAPI i router e gli handler delle eccezioni"""
    register_exception_handlers(app)
    app.include_router(build_api_router(dependencies),prefix=prefix)

__all__ = [
    "AuthDependencies",
    "RouterDependencies",
    "build_api_router",
    "build_auth_dependencies",
    "install_routers",
    "register_exception_handlers",
]