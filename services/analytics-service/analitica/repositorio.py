"""Historial de eventos (S5-15): guardar sin duplicar y consultar por entidad o por usuario."""
import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from redalimenta_comun.eventos import Evento

from .modelos import HistorialEvento

CAMPOS_PARTICIPANTE = ("id_donante", "id_receptor", "id_usuario")


def guardar_evento(db: Session, e: Evento) -> bool:
    """Inserta el evento; si ya estaba (mismo id_evento, p. ej. reentrega del broker) no hace nada."""
    fila = db.execute(insert(HistorialEvento).values(
        id_evento=uuid.UUID(e.id_evento), tipo=e.tipo, version=e.version, origen=e.origen or "desconocido",
        fecha=datetime.fromisoformat(e.fecha), id_actor=e.id_actor, entidad=e.entidad, id_entidad=e.id_entidad,
        estado_anterior=e.estado_anterior, estado_nuevo=e.estado_nuevo, datos=e.datos or {},
    ).on_conflict_do_nothing(index_elements=["id_evento"]).returning(HistorialEvento.id_evento)).first()
    return fila is not None


def por_entidad(db: Session, entidad: str, id_entidad: int | None = None, tipo: str | None = None,
                limite: int = 500) -> list[HistorialEvento]:
    consulta = select(HistorialEvento).where(HistorialEvento.entidad == entidad)
    if id_entidad is not None:
        consulta = consulta.where(HistorialEvento.id_entidad == id_entidad)
    if tipo:
        consulta = consulta.where(HistorialEvento.tipo == tipo)
    return list(db.scalars(consulta.order_by(HistorialEvento.fecha, HistorialEvento.fecha_recepcion).limit(limite)))


def por_usuario(db: Session, id_usuario: int, limite: int = 500) -> list[HistorialEvento]:
    """Eventos que hizo el usuario o en los que participa (donante, receptor o verificado)."""
    condiciones = [HistorialEvento.id_actor == id_usuario] + [
        HistorialEvento.datos.contains({campo: id_usuario}) for campo in CAMPOS_PARTICIPANTE]
    return list(db.scalars(select(HistorialEvento).where(or_(*condiciones))
                           .order_by(HistorialEvento.fecha, HistorialEvento.fecha_recepcion).limit(limite)))


def a_dict(h: HistorialEvento) -> dict:
    return {"id_evento": str(h.id_evento), "tipo": h.tipo, "version": h.version, "origen": h.origen,
            "fecha": h.fecha.isoformat(), "id_actor": h.id_actor, "entidad": h.entidad, "id_entidad": h.id_entidad,
            "estado_anterior": h.estado_anterior, "estado_nuevo": h.estado_nuevo, "datos": h.datos}
