"""Transacciones de fulfillment-service (S4-11): reservar, confirmar, cancelar, expirar y entregar.

La transacción la confirma quien llama (db.commit()). El estado de la donación lo cambia
catalog-geo-service (D-01): estas funciones devuelven lo que el llamador debe pedirle.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .errores import Conflicto, ErrorDominio, NoEncontrado, TransicionInvalida
from .modelos import ConfirmacionEntrega, Entrega, Reserva

ACTIVAS = ("PENDIENTE", "CONFIRMADA")


def _ahora(db: Session) -> datetime:
    return db.scalar(func.now())


# --- Reservas ------------------------------------------------------------------

def reservar(db: Session, id_donacion: int, id_receptor: int, plazo_horas: float | None = None) -> Reserva:
    """D-02: inserta primero; el índice único parcial decide quién gana. El perdedor recibe Conflicto (409)."""
    momento = _ahora(db)
    r = Reserva(id_donacion=id_donacion, id_receptor=id_receptor, fecha_reserva=momento,
                fecha_expiracion=momento + timedelta(hours=plazo_horas or config.PLAZO_RESERVA_HORAS))
    try:
        with db.begin_nested():
            db.add(r)
            db.flush()
    except IntegrityError as error:
        if "ux_reserva_activa" in str(error.orig):
            raise Conflicto("Esta donación ya tiene una reserva activa") from error
        raise
    db.refresh(r)
    return r


def obtener_reserva(db: Session, id_reserva: int, bloquear: bool = False) -> Reserva:
    r = db.get(Reserva, id_reserva, with_for_update=bloquear)
    if r is None:
        raise NoEncontrado("Reserva no encontrada")
    return r


def reserva_activa(db: Session, id_donacion: int) -> Reserva | None:
    return db.scalar(select(Reserva).where(Reserva.id_donacion == id_donacion, Reserva.estado_reserva.in_(ACTIVAS)))


def listar_reservas(db: Session, id_receptor: int | None = None, ids_donaciones: list[int] | None = None,
                    estado: str | None = None) -> list[Reserva]:
    consulta = select(Reserva).order_by(Reserva.id_reserva.desc())
    if id_receptor is not None:
        consulta = consulta.where(Reserva.id_receptor == id_receptor)
    if ids_donaciones is not None:
        consulta = consulta.where(Reserva.id_donacion.in_(ids_donaciones))
    if estado:
        consulta = consulta.where(Reserva.estado_reserva == estado)
    return list(db.scalars(consulta))


def confirmar_reserva(db: Session, id_reserva: int, fecha_programada: datetime | None = None) -> Entrega:
    """El donante acepta: la reserva pasa a CONFIRMADA y se programa la entrega."""
    r = obtener_reserva(db, id_reserva, bloquear=True)
    if r.estado_reserva != "PENDIENTE":
        raise TransicionInvalida(f"La reserva está {r.estado_reserva}")
    if r.fecha_expiracion <= _ahora(db):
        raise Conflicto("El plazo de confirmación de la reserva ya venció")
    r.estado_reserva = "CONFIRMADA"
    db.flush()  # la base exige que la reserva ya esté CONFIRMADA al programar la entrega
    e = Entrega(id_reserva=r.id_reserva, fecha_programada=fecha_programada, estado_entrega="PROGRAMADA")
    db.add(e)
    db.flush()
    return e


def cancelar_reserva(db: Session, id_reserva: int) -> Reserva:
    """Cancela una reserva activa y su entrega abierta. El llamador debe liberar la donación en catalog."""
    r = obtener_reserva(db, id_reserva, bloquear=True)
    if r.estado_reserva not in ACTIVAS:
        raise TransicionInvalida(f"La reserva está {r.estado_reserva}")
    r.estado_reserva = "CANCELADA"
    e = entrega_de_reserva(db, id_reserva)
    if e is not None and e.estado_entrega in ("PROGRAMADA", "CON_INCIDENCIA"):
        e.estado_entrega = "CANCELADA"
    db.flush()
    return r


def expirar_reservas(db: Session, ahora: datetime | None = None) -> list[tuple[int, int]]:
    """Tarea RF8: PENDIENTE con plazo vencido → EXPIRADA. Una sola sentencia; idempotente.

    Devuelve (id_reserva, id_donacion) para que catalog devuelva cada donación a DISPONIBLE.
    """
    filas = db.execute(text("""
        UPDATE reserva SET estado_reserva = 'EXPIRADA'
        WHERE estado_reserva = 'PENDIENTE' AND fecha_expiracion <= coalesce(:ahora, now())
        RETURNING id_reserva, id_donacion"""), {"ahora": ahora})
    return sorted((f[0], f[1]) for f in filas)


# --- Entregas ------------------------------------------------------------------

def entrega_de_reserva(db: Session, id_reserva: int) -> Entrega | None:
    return db.scalar(select(Entrega).where(Entrega.id_reserva == id_reserva))


def obtener_entrega(db: Session, id_entrega: int, bloquear: bool = False) -> Entrega:
    e = db.get(Entrega, id_entrega, with_for_update=bloquear)
    if e is None:
        raise NoEncontrado("Entrega no encontrada")
    return e


def confirmaciones(db: Session, id_entrega: int) -> list[ConfirmacionEntrega]:
    return list(db.scalars(select(ConfirmacionEntrega).where(ConfirmacionEntrega.id_entrega == id_entrega)
                           .order_by(ConfirmacionEntrega.id_confirmacion)))


def registrar_confirmacion(db: Session, id_entrega: int, id_usuario: int, id_donante: int,
                           estado_confirmacion: str = "CONFIRMADA", observaciones: str | None = None) -> bool:
    """Confirmación bilateral (RF6). Devuelve True si con esta confirmación la entrega quedó COMPLETADA.

    id_donante lo aporta catalog-geo-service (el dueño de la donación). Si devuelve True, el llamador
    pide a catalog pasar la donación a ENTREGADA.
    """
    if estado_confirmacion not in ("CONFIRMADA", "CON_INCIDENCIA"):
        raise ErrorDominio("La confirmación debe ser CONFIRMADA o CON_INCIDENCIA")
    e = obtener_entrega(db, id_entrega, bloquear=True)
    r = obtener_reserva(db, e.id_reserva, bloquear=True)
    if id_usuario not in (id_donante, r.id_receptor):
        raise ErrorDominio("Solo el donante y el receptor confirman la entrega")
    if e.estado_entrega not in ("PROGRAMADA", "CON_INCIDENCIA"):
        raise TransicionInvalida(f"La entrega está {e.estado_entrega}")
    try:
        with db.begin_nested():
            db.add(ConfirmacionEntrega(id_entrega=id_entrega, id_usuario=id_usuario,
                                       estado_confirmacion=estado_confirmacion, observaciones=observaciones))
            db.flush()
    except IntegrityError as error:
        raise Conflicto("Ya registraste tu confirmación de esta entrega") from error

    if estado_confirmacion == "CON_INCIDENCIA":
        if e.estado_entrega == "PROGRAMADA":
            e.estado_entrega = "CON_INCIDENCIA"
            e.observaciones = observaciones
            db.flush()
        return False
    confirmados = set(db.scalars(select(ConfirmacionEntrega.id_usuario).where(
        ConfirmacionEntrega.id_entrega == id_entrega, ConfirmacionEntrega.estado_confirmacion == "CONFIRMADA")))
    if e.estado_entrega == "PROGRAMADA" and {id_donante, r.id_receptor} <= confirmados:
        e.estado_entrega = "COMPLETADA"
        e.fecha_entrega = _ahora(db)
        r.estado_reserva = "COMPLETADA"
        db.flush()
        return True
    return False
