"""Tareas automáticas de fulfillment (RF8): expirar reservas, vencer donaciones, avisar y conciliar.

- En desarrollo corren en un hilo del servicio cada TAREAS_SEGUNDOS (60 por defecto; 0 lo desactiva).
- En Kubernetes (Sprint 6) corren como CronJob: `python -m cumplimiento.tareas` (una ejecución y termina).
"""
import logging
import threading

from . import config
from .catalogo_cliente import cliente_catalogo
from .db import sesiones
from .servicio import ejecutar_tareas

log = logging.getLogger("redalimenta.tareas")


def ejecutar_una_vez() -> dict:
    with sesiones()() as db:
        resultado = ejecutar_tareas(db, cliente_catalogo())
    if any(resultado.values()):
        log.info("Tareas programadas: %s", resultado)
    return resultado


class Planificador(threading.Thread):
    def __init__(self, segundos: int) -> None:
        super().__init__(name="planificador-tareas", daemon=True)
        self.segundos = segundos
        self._detener = threading.Event()

    def detener(self) -> None:
        self._detener.set()

    def run(self) -> None:
        while not self._detener.wait(self.segundos):
            try:
                ejecutar_una_vez()
            except Exception:  # un fallo puntual (p. ej. catalog caído) no detiene el planificador
                log.exception("Fallo en las tareas programadas")


def hilos() -> list:
    return [Planificador(config.TAREAS_SEGUNDOS)] if config.TAREAS_SEGUNDOS > 0 else []


if __name__ == "__main__":
    print(ejecutar_una_vez())
