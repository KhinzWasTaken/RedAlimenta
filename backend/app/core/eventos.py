"""Bus de eventos en proceso (sustituye al broker en el prototipo).

Cada cambio de estado publica un evento con el sobre común del plan (sección 4).
Los suscriptores (auditoría y notificaciones) se ejecutan dentro de la misma
transacción, así que el cambio, su auditoría y su notificación se guardan juntos.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .tiempo import ahora


@dataclass
class Evento:
    tipo: str
    entidad: str
    id_entidad: int
    estado_anterior: str | None
    estado_nuevo: str | None
    id_actor: int | None
    datos: dict[str, Any] = field(default_factory=dict)
    id_evento: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    fecha: datetime = field(default_factory=ahora)


Suscriptor = Callable[[Session, Evento], None]
_suscriptores: list[Suscriptor] = []


def suscribir(funcion: Suscriptor) -> Suscriptor:
    if funcion not in _suscriptores:
        _suscriptores.append(funcion)
    return funcion


def publicar(db: Session, evento: Evento) -> None:
    for funcion in _suscriptores:
        funcion(db, evento)
