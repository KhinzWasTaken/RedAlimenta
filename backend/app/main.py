"""Aplicación única de RedAlimenta (prototipo de clase).

Módulos: identidad, catálogo, reservas y entregas, notificaciones in-app.
Si existe `frontend/dist`, también sirve el frontend compilado en `/`.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.catalogo.rutas import rutas as rutas_catalogo
from app.core import config
from app.core.db import crear_esquema
from app.core.errores import ErrorDominio
from app.identidad import servicio as _auditoria  # noqa: F401  (registra el suscriptor de auditoría)
from app.identidad.rutas import rutas as rutas_identidad
from app.notificaciones import servicio as _notificaciones  # noqa: F401  (registra el suscriptor)
from app.notificaciones.rutas import rutas as rutas_notificaciones
from app.reservas import tareas
from app.reservas.rutas import rutas as rutas_reservas


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    crear_esquema()
    tarea = asyncio.create_task(tareas.planificador()) if config.PLANIFICADOR_ACTIVO else None
    yield
    if tarea:
        tarea.cancel()


app = FastAPI(title="RedAlimenta", version="0.1.0", lifespan=ciclo_de_vida)


@app.exception_handler(ErrorDominio)
async def manejar_error_dominio(_request: Request, error: ErrorDominio):
    return JSONResponse(status_code=error.codigo, content={"detail": error.mensaje})


@app.get("/api/salud")
def salud():
    return {"estado": "ok"}


for _rutas in (rutas_identidad, rutas_catalogo, rutas_reservas, rutas_notificaciones):
    app.include_router(_rutas)


if config.FRONTEND_DIST.joinpath("index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def frontend(ruta: str):
        if ruta.startswith("api"):
            raise HTTPException(404, "Recurso no encontrado")
        raiz = config.FRONTEND_DIST.resolve()
        archivo = (raiz / ruta).resolve()
        if ruta and archivo.is_relative_to(raiz) and archivo.is_file():
            return FileResponse(archivo)
        return FileResponse(config.FRONTEND_DIST / "index.html")
