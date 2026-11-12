"""Consultas de notification-service (RF7): crear, bandeja, contador, leer y archivar.

La transacción la confirma quien llama (db.commit()).
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .errores import ErrorDominio, NoEncontrado, TransicionInvalida
from .modelos import Notificacion

TRANSICIONES = {"NO_LEIDA": {"LEIDA", "ARCHIVADA"}, "LEIDA": {"ARCHIVADA"}}


def crear_notificacion(db: Session, id_usuario: int, tipo: str, mensaje: str) -> Notificacion:
    if not mensaje or not mensaje.strip():
        raise ErrorDominio("La notificación necesita un mensaje")
    n = Notificacion(id_usuario=id_usuario, tipo_notificacion=tipo, mensaje=mensaje.strip())
    db.add(n)
    db.flush()
    db.refresh(n)
    return n


def bandeja(db: Session, id_usuario: int, incluir_archivadas: bool = False, limite: int = 200) -> list[Notificacion]:
    consulta = (select(Notificacion).where(Notificacion.id_usuario == id_usuario)
                .order_by(Notificacion.fecha_creacion.desc(), Notificacion.id_notificacion.desc()).limit(limite))
    if not incluir_archivadas:
        consulta = consulta.where(Notificacion.estado_notificacion != "ARCHIVADA")
    return list(db.scalars(consulta))


def contar_no_leidas(db: Session, id_usuario: int) -> int:
    return db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.id_usuario == id_usuario, Notificacion.estado_notificacion == "NO_LEIDA"))


def _cambiar(db: Session, id_notificacion: int, id_usuario: int, nuevo: str) -> Notificacion:
    n = db.get(Notificacion, id_notificacion, with_for_update=True)
    if n is None or n.id_usuario != id_usuario:  # otra persona no la ve: misma respuesta que si no existiera
        raise NoEncontrado("Notificación no encontrada")
    if nuevo not in TRANSICIONES.get(n.estado_notificacion, set()):
        raise TransicionInvalida(f"La notificación ya está {n.estado_notificacion}")
    n.estado_notificacion = nuevo
    if nuevo == "LEIDA":
        n.fecha_lectura = func.now()
    db.flush()
    db.refresh(n)
    return n


def marcar_leida(db: Session, id_notificacion: int, id_usuario: int) -> Notificacion:
    return _cambiar(db, id_notificacion, id_usuario, "LEIDA")


def archivar(db: Session, id_notificacion: int, id_usuario: int) -> Notificacion:
    return _cambiar(db, id_notificacion, id_usuario, "ARCHIVADA")


def marcar_todas_leidas(db: Session, id_usuario: int) -> int:
    resultado = db.execute(update(Notificacion).where(
        Notificacion.id_usuario == id_usuario, Notificacion.estado_notificacion == "NO_LEIDA",
    ).values(estado_notificacion="LEIDA", fecha_lectura=func.now()))
    return resultado.rowcount
