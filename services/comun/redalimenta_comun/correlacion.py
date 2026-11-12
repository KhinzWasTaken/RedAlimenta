"""Identificador de correlación (S6-09): una operación se sigue a través de los servicios con un mismo id.

- El gateway pone la cabecera X-Correlation-Id (o la genera el primer servicio que la recibe sin ella).
- Cada servicio la guarda en una variable de contexto, la escribe en sus registros, la devuelve en la
  respuesta, la reenvía en las llamadas a otros servicios y la incluye en los eventos que publica.
- Los consumidores toman la del evento, así que la auditoría, las notificaciones y el historial que provoca
  una petición aparecen en los registros con el mismo identificador.
"""
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CABECERA = "X-Correlation-Id"
_actual: ContextVar[str] = ContextVar("id_correlacion", default="-")
log = logging.getLogger("redalimenta.http")


def actual() -> str:
    return _actual.get()


def fijar(valor: str | None) -> None:
    _actual.set((valor or uuid.uuid4().hex)[:64])


class FiltroCorrelacion(logging.Filter):
    """Agrega `correlacion` a cada registro para usarlo en el formato de los logs."""

    def filter(self, registro: logging.LogRecord) -> bool:
        registro.correlacion = actual()
        return True


class MiddlewareCorrelacion(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        fijar(request.headers.get(CABECERA))
        inicio = time.perf_counter()
        respuesta = await call_next(request)
        respuesta.headers[CABECERA] = actual()
        if request.url.path != "/salud":
            log.info("%s %s → %s (%.0f ms)", request.method, request.url.path, respuesta.status_code,
                     (time.perf_counter() - inicio) * 1000)
        return respuesta
