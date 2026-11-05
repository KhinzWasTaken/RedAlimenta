"""Módulo de notificaciones in-app (RF7): consume los eventos y crea la bandeja de cada usuario."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import estados
from app.core.errores import NoEncontrado, Prohibido
from app.core.eventos import Evento, suscribir
from app.core.tiempo import ahora, iso

from .modelos import Notificacion


def destinatarios(evento: Evento) -> list[tuple[int, str]]:
    """Quién recibe qué mensaje por cada tipo de evento."""
    d = evento.datos
    alimento = d.get("nombre_alimento", "")
    donante, receptor = d.get("id_donante"), d.get("id_receptor")
    t = evento.tipo
    if t == "USUARIO_VERIFICADO":
        texto = ("Tu cuenta fue verificada: ya puedes operar en RedAlimenta."
                 if evento.estado_nuevo == "APROBADA" else
                 f"Tu verificación fue rechazada. {d.get('observaciones') or ''}".strip())
        return [(d["id_usuario"], texto)]
    if t == "DONACION_CREADA":
        return [(donante, f"Publicaste la donación «{alimento}».")]
    if t == "DONACION_RESERVADA":
        return [(donante, f"«{alimento}» fue reservada. Confírmala antes de {d.get('fecha_expiracion')}.")]
    if t == "DONACION_LIBERADA":
        return [(donante, f"«{alimento}» volvió a estar DISPONIBLE.")]
    if t == "DONACION_ENTREGADA":
        return [(donante, f"«{alimento}» quedó ENTREGADA. ¡Gracias por donar!")]
    if t == "DONACION_CANCELADA":
        return [(donante, f"Cancelaste la donación «{alimento}».")]
    if t == "DONACION_VENCIDA":
        return [(donante, f"«{alimento}» venció y salió del catálogo.")]
    if t == "DONACION_POR_VENCER":
        mensaje = f"«{alimento}» vence pronto ({d.get('vence')})."
        return [(donante, mensaje)] + ([(receptor, mensaje)] if receptor else [])
    if t == "RESERVA_CREADA":
        return [(receptor, f"Reservaste «{alimento}». El donante debe confirmar antes de {d.get('fecha_expiracion')}.")]
    if t == "RESERVA_CONFIRMADA":
        return [(receptor, f"El donante confirmó tu reserva de «{alimento}».")]
    if t == "RESERVA_EXPIRADA":
        return [(receptor, f"Tu reserva de «{alimento}» expiró sin confirmación."),
                (donante, f"La reserva de «{alimento}» expiró sin confirmación.")]
    if t == "RESERVA_CANCELADA":
        if d.get("motivo"):
            return [(receptor, f"No se pudo reservar «{alimento}»: la donación ya no está disponible.")]
        return [(receptor, f"La reserva de «{alimento}» fue cancelada."),
                (donante, f"La reserva de «{alimento}» fue cancelada.")]
    if t == "RESERVA_COMPLETADA":
        return [(receptor, f"Tu reserva de «{alimento}» quedó COMPLETADA.")]
    if t == "ENTREGA_PROGRAMADA":
        return [(donante, f"Entrega de «{alimento}» programada. Confírmala cuando ocurra."),
                (receptor, f"Entrega de «{alimento}» programada. Confírmala cuando recibas el alimento.")]
    if t == "ENTREGA_CONFIRMADA":
        otro = receptor if d.get("por") == "donante" else donante
        accion = "reportó una incidencia en" if d.get("confirmacion") == "CON_INCIDENCIA" else "confirmó"
        return [(otro, f"El {d.get('por')} {accion} la entrega de «{alimento}».")]
    if t == "ENTREGA_COMPLETADA":
        return [(donante, f"Entrega de «{alimento}» completada por ambas partes."),
                (receptor, f"Entrega de «{alimento}» completada por ambas partes.")]
    if t == "ENTREGA_CON_INCIDENCIA":
        return [(donante, f"La entrega de «{alimento}» quedó CON INCIDENCIA."),
                (receptor, f"La entrega de «{alimento}» quedó CON INCIDENCIA.")]
    if t == "ENTREGA_CANCELADA":
        return [(donante, f"La entrega de «{alimento}» fue cancelada."),
                (receptor, f"La entrega de «{alimento}» fue cancelada.")]
    if t.startswith("NECESIDAD_"):
        return [(receptor, f"Necesidad «{d.get('descripcion')}»: {evento.estado_nuevo}.")]
    return []


@suscribir
def al_recibir_evento(db: Session, evento: Evento) -> None:
    for id_usuario, mensaje in destinatarios(evento):
        if id_usuario:
            db.add(Notificacion(id_usuario=id_usuario, tipo_notificacion=evento.tipo, mensaje=mensaje,
                                fecha_creacion=evento.fecha, estado_notificacion="NO_LEIDA"))


def _dict(n: Notificacion) -> dict:
    return {"id_notificacion": n.id_notificacion, "tipo_notificacion": n.tipo_notificacion,
            "mensaje": n.mensaje, "fecha_creacion": iso(n.fecha_creacion),
            "fecha_lectura": iso(n.fecha_lectura), "estado_notificacion": n.estado_notificacion}


def bandeja(db: Session, id_usuario: int, incluir_archivadas: bool = False) -> list[dict]:
    consulta = select(Notificacion).where(Notificacion.id_usuario == id_usuario)
    if not incluir_archivadas:
        consulta = consulta.where(Notificacion.estado_notificacion != "ARCHIVADA")
    return [_dict(n) for n in db.scalars(consulta.order_by(Notificacion.id_notificacion.desc()).limit(200))]


def no_leidas(db: Session, id_usuario: int) -> int:
    return db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.id_usuario == id_usuario, Notificacion.estado_notificacion == "NO_LEIDA"))


def cambiar_estado(db: Session, id_usuario: int, id_notificacion: int, nuevo: str) -> dict:
    n = db.get(Notificacion, id_notificacion)
    if n is None:
        raise NoEncontrado("Notificación no encontrada")
    if n.id_usuario != id_usuario:
        raise Prohibido("Esta notificación no es tuya")
    estados.validar("notificacion", n.estado_notificacion, nuevo)
    n.estado_notificacion = nuevo
    if nuevo == "LEIDA":
        n.fecha_lectura = ahora()
    db.flush()
    return _dict(n)


def leer_todas(db: Session, id_usuario: int) -> None:
    db.execute(update(Notificacion).where(
        Notificacion.id_usuario == id_usuario, Notificacion.estado_notificacion == "NO_LEIDA",
    ).values(estado_notificacion="LEIDA", fecha_lectura=ahora()))
