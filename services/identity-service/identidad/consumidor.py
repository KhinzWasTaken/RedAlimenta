"""Consumidor de auditoría (D-04): guarda en registro_auditoria los eventos de los demás servicios.

Los eventos propios de identity ya se auditan en su misma transacción, así que aquí se omiten.
Idempotente (S6-05): un id_evento ya procesado no se vuelve a auditar.
"""
from redalimenta_comun.eventos import Consumidor, Evento, primera_vez

from .db import sesiones
from .servicio import auditar

COLA = "identity.auditoria"


def procesar(evento: Evento) -> None:
    if evento.origen == "identity":
        return
    with sesiones()() as db:
        if not primera_vez(db, evento, COLA):  # S6-05: reentrega del broker → no se audita dos veces
            return
        auditar(db, evento)
        db.commit()


def consumidores() -> list[Consumidor]:
    return [Consumidor(COLA, ["#"], procesar)]
