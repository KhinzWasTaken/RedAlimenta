"""Errores de dominio y su traducción a HTTP con un formato único: {"detail": "...", "error": "Tipo"}."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

log = logging.getLogger("redalimenta")


class ErrorDominio(Exception):
    codigo = 400


class NoAutenticado(ErrorDominio):
    codigo = 401


class Prohibido(ErrorDominio):
    codigo = 403


class NoEncontrado(ErrorDominio):
    codigo = 404


class Conflicto(ErrorDominio):
    codigo = 409


class TransicionInvalida(Conflicto):
    """Transición de estado no permitida por docs/modelo/estados.md."""


class ServicioNoDisponible(ErrorDominio):
    """Otro servicio no respondió (p. ej. catalog caído al reservar)."""
    codigo = 503


def _respuesta(codigo: int, mensaje: str, tipo: str) -> JSONResponse:
    return JSONResponse(status_code=codigo, content={"detail": mensaje, "error": tipo})


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(_: Request, error: ErrorDominio):
        return _respuesta(error.codigo, str(error), type(error).__name__)

    @app.exception_handler(DBAPIError)
    async def _base(_: Request, error: DBAPIError):
        # Las reglas que hace cumplir la base (CHECK, UNIQUE, triggers) llegan como conflicto 409
        origen = getattr(error, "orig", None)
        estado = getattr(origen, "sqlstate", "") or ""
        if isinstance(error, IntegrityError) or estado.startswith("23"):
            mensaje = str(origen).splitlines()[0] if origen else "Conflicto con los datos existentes"
            return _respuesta(409, mensaje, "Conflicto")
        log.exception("Error de base de datos")
        return _respuesta(500, "Error interno de la base de datos", "ErrorInterno")
