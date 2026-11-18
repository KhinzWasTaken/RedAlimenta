"""Consumidor de analytics: guarda todos los eventos en el historial (idempotente por id_evento)."""
from redalimenta_comun.eventos import Consumidor, Evento

from .db import sesiones
from .repositorio import guardar_evento

COLA = "analytics.historial"


def procesar(evento: Evento) -> bool:
    with sesiones()() as db:
        nuevo = guardar_evento(db, evento)
        db.commit()
    return nuevo


def consumidores() -> list[Consumidor]:
    return [Consumidor(COLA, ["#"], procesar)]
