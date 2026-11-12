"""Consumidor de auditoría (D-04): guarda en registro_auditoria los eventos de los demás servicios.

Los eventos propios de identity ya se auditan en su misma transacción, así que aquí se omiten.
"""
from redalimenta_comun.eventos import Consumidor, Evento

from .db import sesiones
from .servicio import auditar

COLA = "identity.auditoria"


def procesar(evento: Evento) -> None:
    if evento.origen == "identity":
        return
    with sesiones()() as db:
        auditar(db, evento)
        db.commit()


def consumidores() -> list[Consumidor]:
    return [Consumidor(COLA, ["#"], procesar)]
