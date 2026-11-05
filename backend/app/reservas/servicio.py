"""Módulo de reservas y entregas (RF5, RF6).

D-02: la reserva se inserta primero (el índice único parcial decide quién gana) y
después se pide al catálogo pasar la donación a RESERVADA. Si el catálogo rechaza,
la reserva queda CANCELADA (compensación).
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogo import servicio as catalogo
from app.core import config, estados
from app.core.errores import Conflicto, NoEncontrado, Prohibido, TransicionInvalida
from app.core.eventos import Evento, publicar
from app.core.seguridad import Actor
from app.core.tiempo import ahora, hora_bogota, iso
from app.identidad.servicio import nombres_publicos

from .modelos import ConfirmacionEntrega, Entrega, Reserva


def _evento(db: Session, tipo: str, entidad: str, id_entidad: int, anterior: str | None,
            nuevo: str | None, id_actor: int | None, **datos) -> None:
    publicar(db, Evento(tipo=tipo, entidad=entidad, id_entidad=id_entidad, estado_anterior=anterior,
                        estado_nuevo=nuevo, id_actor=id_actor, datos=datos))


def _contexto(db: Session, r: Reserva) -> dict:
    d = catalogo.obtener_donacion(db, r.id_donacion)
    return {"id_reserva": r.id_reserva, "id_donacion": d.id_donacion, "id_donante": d.id_donante,
            "id_receptor": r.id_receptor, "nombre_alimento": d.nombre_alimento}


def _cambiar_reserva(db: Session, r: Reserva, nuevo: str, id_actor: int | None, **extra) -> None:
    estados.validar("reserva", r.estado_reserva, nuevo)
    anterior = r.estado_reserva
    r.estado_reserva = nuevo
    db.flush()
    _evento(db, f"RESERVA_{nuevo}", "reserva", r.id_reserva, anterior, nuevo, id_actor,
            **_contexto(db, r), **extra)


def _cambiar_entrega(db: Session, e: Entrega, r: Reserva, nuevo: str, id_actor: int | None) -> None:
    estados.validar("entrega", e.estado_entrega, nuevo)
    anterior = e.estado_entrega
    e.estado_entrega = nuevo
    if nuevo == "COMPLETADA":
        e.fecha_entrega = ahora()
    db.flush()
    _evento(db, f"ENTREGA_{nuevo}", "entrega", e.id_entrega, anterior, nuevo, id_actor,
            id_entrega=e.id_entrega, **_contexto(db, r))


def liberar_donacion(db: Session, id_donacion: int, id_actor: int | None) -> None:
    """Devuelve la donación a DISPONIBLE si sigue vigente; si no, la marca VENCIDA (vía catálogo, D-01)."""
    d = catalogo.obtener_donacion(db, id_donacion)
    if d.estado_donacion != "RESERVADA":
        return
    nuevo = "DISPONIBLE" if d.fecha_vencimiento > ahora() else "VENCIDA"
    catalogo.transicionar_donacion(db, id_donacion, nuevo, id_actor)


def obtener_reserva(db: Session, id_reserva: int) -> Reserva:
    r = db.get(Reserva, id_reserva)
    if r is None:
        raise NoEncontrado("Reserva no encontrada")
    return r


def _es_parte(db: Session, r: Reserva, actor: Actor) -> tuple[bool, bool]:
    d = catalogo.obtener_donacion(db, r.id_donacion)
    return d.id_donante == actor.id_usuario, r.id_receptor == actor.id_usuario


# --- Reservas ------------------------------------------------------------------

def reservar(db: Session, actor: Actor, id_donacion: int) -> Reserva:
    catalogo.obtener_donacion(db, id_donacion)  # 404 si no existe
    momento = ahora()
    r = Reserva(id_donacion=id_donacion, id_receptor=actor.id_usuario, fecha_reserva=momento,
                fecha_expiracion=momento + timedelta(hours=config.PLAZO_RESERVA_HORAS),
                estado_reserva="PENDIENTE")
    try:
        with db.begin_nested():
            db.add(r)
            db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflicto("Esta donación ya tiene una reserva activa")
    _evento(db, "RESERVA_CREADA", "reserva", r.id_reserva, None, "PENDIENTE", actor.id_usuario,
            **_contexto(db, r), fecha_expiracion=hora_bogota(r.fecha_expiracion))
    try:
        catalogo.transicionar_donacion(db, id_donacion, "RESERVADA", actor.id_usuario,
                                       {"id_receptor": actor.id_usuario, "id_reserva": r.id_reserva,
                                        "fecha_expiracion": hora_bogota(r.fecha_expiracion)})
    except TransicionInvalida as error:
        # Compensación D-02: el catálogo rechazó la transición
        _cambiar_reserva(db, r, "CANCELADA", None, motivo=f"Catálogo rechazó: {error.mensaje}")
        db.commit()
        raise Conflicto(f"No se pudo reservar: {error.mensaje}")
    return r


def confirmar_reserva(db: Session, actor: Actor, id_reserva: int) -> Reserva:
    r = obtener_reserva(db, id_reserva)
    es_donante, _ = _es_parte(db, r, actor)
    if not es_donante:
        raise Prohibido("Solo el donante de la donación confirma la reserva")
    if r.estado_reserva == "PENDIENTE" and r.fecha_expiracion <= ahora():
        raise Conflicto("El plazo de confirmación de la reserva ya venció")
    _cambiar_reserva(db, r, "CONFIRMADA", actor.id_usuario)
    e = Entrega(id_reserva=r.id_reserva, fecha_programada=ahora() + timedelta(days=1),
                estado_entrega="PROGRAMADA")
    db.add(e)
    db.flush()
    _evento(db, "ENTREGA_PROGRAMADA", "entrega", e.id_entrega, None, "PROGRAMADA", actor.id_usuario,
            id_entrega=e.id_entrega, **_contexto(db, r))
    return r


def cancelar_reserva(db: Session, actor: Actor, id_reserva: int) -> Reserva:
    r = obtener_reserva(db, id_reserva)
    es_donante, es_receptor = _es_parte(db, r, actor)
    if not (es_donante or es_receptor or actor.rol == "ADMINISTRADOR"):
        raise Prohibido("No participas en esta reserva")
    _cambiar_reserva(db, r, "CANCELADA", actor.id_usuario)
    e = db.scalars(select(Entrega).where(Entrega.id_reserva == r.id_reserva)).first()
    if e is not None and estados.es_valida("entrega", e.estado_entrega, "CANCELADA"):
        _cambiar_entrega(db, e, r, "CANCELADA", actor.id_usuario)
    liberar_donacion(db, r.id_donacion, actor.id_usuario)
    return r


# --- Entregas ------------------------------------------------------------------

def confirmar_entrega(db: Session, actor: Actor, id_entrega: int, estado_confirmacion: str,
                      observaciones: str | None) -> Entrega:
    e = db.get(Entrega, id_entrega)
    if e is None:
        raise NoEncontrado("Entrega no encontrada")
    r = obtener_reserva(db, e.id_reserva)
    es_donante, es_receptor = _es_parte(db, r, actor)
    if not (es_donante or es_receptor):
        raise Prohibido("Solo el donante y el receptor confirman la entrega")
    if estado_confirmacion not in estados.ESTADOS_CONFIRMACION:
        raise Conflicto("Estado de confirmación inválido")
    if e.estado_entrega not in ("PROGRAMADA", "CON_INCIDENCIA"):
        raise TransicionInvalida(f"La entrega está {e.estado_entrega} y no admite confirmaciones")
    c = ConfirmacionEntrega(id_entrega=e.id_entrega, id_usuario=actor.id_usuario,
                            estado_confirmacion=estado_confirmacion, observaciones=observaciones)
    try:
        with db.begin_nested():
            db.add(c)
            db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflicto("Ya registraste tu confirmación de esta entrega")
    _evento(db, "ENTREGA_CONFIRMADA", "entrega", e.id_entrega, e.estado_entrega, e.estado_entrega,
            actor.id_usuario, id_entrega=e.id_entrega, confirmacion=estado_confirmacion,
            por="donante" if es_donante else "receptor", **_contexto(db, r))

    if estado_confirmacion == "CON_INCIDENCIA":
        if e.estado_entrega == "PROGRAMADA":
            e.observaciones = observaciones
            _cambiar_entrega(db, e, r, "CON_INCIDENCIA", actor.id_usuario)
        return e

    confirmados = set(db.scalars(select(ConfirmacionEntrega.id_usuario).where(
        ConfirmacionEntrega.id_entrega == e.id_entrega,
        ConfirmacionEntrega.estado_confirmacion == "CONFIRMADA")))
    d = catalogo.obtener_donacion(db, r.id_donacion)
    if e.estado_entrega == "PROGRAMADA" and {d.id_donante, r.id_receptor} <= confirmados:
        # Regla de negocio: ENTREGADA solo con las dos confirmaciones
        _cambiar_entrega(db, e, r, "COMPLETADA", actor.id_usuario)
        _cambiar_reserva(db, r, "COMPLETADA", actor.id_usuario)
        catalogo.transicionar_donacion(db, r.id_donacion, "ENTREGADA", actor.id_usuario,
                                       {"id_receptor": r.id_receptor})
    return e


# --- Consultas -----------------------------------------------------------------

def _entrega_dict(db: Session, e: Entrega | None, actor: Actor, nombres: dict[int, str]) -> dict | None:
    if e is None:
        return None
    confirmaciones = list(db.scalars(select(ConfirmacionEntrega).where(
        ConfirmacionEntrega.id_entrega == e.id_entrega).order_by(ConfirmacionEntrega.id_confirmacion)))
    return {
        "id_entrega": e.id_entrega,
        "estado_entrega": e.estado_entrega,
        "fecha_programada": iso(e.fecha_programada),
        "fecha_entrega": iso(e.fecha_entrega),
        "observaciones": e.observaciones,
        "yo_confirme": any(c.id_usuario == actor.id_usuario for c in confirmaciones),
        "confirmaciones": [{
            "id_usuario": c.id_usuario, "nombre": nombres.get(c.id_usuario),
            "estado_confirmacion": c.estado_confirmacion, "observaciones": c.observaciones,
            "fecha_confirmacion": iso(c.fecha_confirmacion),
        } for c in confirmaciones],
    }


def reserva_dict(db: Session, r: Reserva, actor: Actor) -> dict:
    d = catalogo.obtener_donacion(db, r.id_donacion)
    nombres = nombres_publicos(db, {d.id_donante, r.id_receptor})
    e = db.scalars(select(Entrega).where(Entrega.id_reserva == r.id_reserva)).first()
    return {
        "id_reserva": r.id_reserva,
        "estado_reserva": r.estado_reserva,
        "fecha_reserva": iso(r.fecha_reserva),
        "fecha_expiracion": iso(r.fecha_expiracion),
        "id_receptor": r.id_receptor,
        "receptor": nombres.get(r.id_receptor),
        "donacion": catalogo.donacion_dict(db, d, nombres),
        "entrega": _entrega_dict(db, e, actor, nombres),
        "soy": "donante" if d.id_donante == actor.id_usuario else "receptor",
    }


def mis_reservas(db: Session, actor: Actor) -> list[dict]:
    consulta = select(Reserva).order_by(Reserva.id_reserva.desc())
    if actor.rol == "RECEPTOR":
        consulta = consulta.where(Reserva.id_receptor == actor.id_usuario)
    elif actor.rol == "DONANTE":
        consulta = consulta.where(Reserva.id_donacion.in_(catalogo.ids_donaciones_de(db, actor.id_usuario)))
    return [reserva_dict(db, r, actor) for r in db.scalars(consulta)]
