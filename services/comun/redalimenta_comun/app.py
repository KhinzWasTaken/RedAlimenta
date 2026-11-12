"""App base de cada servicio: errores con formato único, ruta de salud y consumidores en segundo plano."""
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .correlacion import FiltroCorrelacion, MiddlewareCorrelacion
from .errores import registrar_manejadores

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s [%(name)s] [%(correlacion)s] %(message)s")
for _manejador in logging.getLogger().handlers:
    _manejador.addFilter(FiltroCorrelacion())


def dependencia_sesion(sesiones: Callable[[], sessionmaker]):
    """Dependencia de FastAPI que abre una sesión por petición (la fábrica se resuelve al primer uso)."""
    def obtener() -> Iterator[Session]:
        with sesiones()() as db:
            yield db
    return obtener


def crear_app(nombre: str, routers: list[APIRouter], sesiones: Callable[[], sessionmaker],
              consumidores: Callable[[], list] | None = None, descripcion: str = "") -> FastAPI:
    """Crea la app del servicio. `consumidores` arranca hilos que leen RabbitMQ (CONSUMIR_EVENTOS=1)."""

    @asynccontextmanager
    async def ciclo(_app: FastAPI):
        hilos = []
        if consumidores and os.environ.get("CONSUMIR_EVENTOS", "1") == "1":
            hilos = consumidores()
            for hilo in hilos:
                hilo.start()
        yield
        for hilo in hilos:
            hilo.detener()

    app = FastAPI(title=f"RedAlimenta · {nombre}", version="1.0.0", description=descripcion, lifespan=ciclo)
    registrar_manejadores(app)
    app.add_middleware(MiddlewareCorrelacion)

    @app.get("/salud", tags=["salud"])
    def salud():
        """Preparación (readiness): el servicio y su base responden."""
        with sesiones()() as db:
            db.execute(text("SELECT 1"))
        return {"estado": "ok", "servicio": nombre}

    @app.get("/vivo", tags=["salud"])
    def vivo():
        """Vida (liveness): el proceso responde, aunque su base esté caída (no conviene reiniciarlo por eso)."""
        return {"estado": "vivo", "servicio": nombre}

    for router in routers:
        app.include_router(router)
    return app
