"""Consumidor de eventos (S5-14): cada evento del catálogo crea la notificación de su destinatario."""
from datetime import datetime, timedelta, timezone

from redalimenta_comun.eventos import Consumidor, Evento, primera_vez

from . import repositorio as repo
from .db import sesiones

COLA = "notification.bandeja"
BOGOTA = timezone(timedelta(hours=-5))


def _hora(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone(BOGOTA).strftime("%d/%m/%y %H:%M")


def destinatarios(e: Evento) -> list[tuple[int, str]]:
    """(id_usuario, mensaje) por cada tipo de evento. Un evento sin destinatario no crea notificaciones."""
    d = e.datos
    alimento = f"«{d.get('nombre_alimento', '')}»"
    donante, receptor = d.get("id_donante"), d.get("id_receptor")
    ambos = lambda texto: [(donante, texto), (receptor, texto)]  # noqa: E731
    match e.tipo:
        case "USUARIO_REGISTRADO":
            return [(e.id_entidad, "Bienvenido a RedAlimenta. Un administrador verificará tu cuenta.")]
        case "USUARIO_VERIFICADO":
            if e.estado_nuevo == "APROBADA":
                return [(d["id_usuario"], "Tu cuenta fue verificada: ya puedes operar en RedAlimenta.")]
            return [(d["id_usuario"], f"Tu verificación fue rechazada. {d.get('observaciones') or ''}".strip())]
        case "DONACION_CREADA":
            if receptor:  # D-11: ofrecida para una solicitud del receptor
                return [(donante, f"Ofreciste {alimento} para la solicitud «{d.get('necesidad', '')}»."),
                        (receptor, f"Un donante ofreció {alimento} para tu solicitud «{d.get('necesidad', '')}». "
                                   "Resérvala en Buscar: está apartada para ti.")]
            return [(donante, f"Publicaste la donación {alimento}.")]
        case "DONACION_RESERVADA":
            return [(donante, f"{alimento} fue reservada. Confírmala antes de {_hora(d.get('fecha_expiracion'))}.")]
        case "DONACION_LIBERADA":
            return [(donante, f"{alimento} volvió a estar DISPONIBLE.")]
        case "DONACION_ENTREGADA":
            return [(donante, f"{alimento} quedó ENTREGADA. ¡Gracias por donar!")]
        case "DONACION_CANCELADA":
            return [(donante, f"Cancelaste la donación {alimento}.")]
        case "DONACION_VENCIDA":
            return [(donante, f"{alimento} venció y salió del catálogo.")]
        case "DONACION_POR_VENCER":
            texto = f"{alimento} vence pronto ({_hora(d.get('fecha_vencimiento'))})."
            return [(donante, texto)] + ([(receptor, texto)] if receptor else [])
        case "RESERVA_CREADA":
            return [(receptor, f"Reservaste {alimento}. El donante debe confirmar antes de "
                               f"{_hora(d.get('fecha_expiracion'))}.")]
        case "RESERVA_CONFIRMADA":
            return [(receptor, f"El donante confirmó tu reserva de {alimento}.")]
        case "RESERVA_EXPIRADA":
            return [(receptor, f"Tu reserva de {alimento} expiró sin confirmación."),
                    (donante, f"La reserva de {alimento} expiró sin confirmación.")]
        case "RESERVA_CANCELADA":
            if d.get("motivo"):
                return [(receptor, f"No se pudo reservar {alimento}: la donación ya no está disponible.")]
            return ambos(f"La reserva de {alimento} fue cancelada.")
        case "RESERVA_COMPLETADA":
            return [(receptor, f"Tu reserva de {alimento} quedó COMPLETADA.")]
        case "ENTREGA_PROGRAMADA":
            return [(donante, f"Entrega de {alimento} programada. Confírmala cuando ocurra."),
                    (receptor, f"Entrega de {alimento} programada. Confírmala cuando recibas el alimento.")]
        case "ENTREGA_CONFIRMADA":
            otro = receptor if d.get("por") == "donante" else donante
            accion = "reportó una incidencia en" if d.get("confirmacion") == "CON_INCIDENCIA" else "confirmó"
            return [(otro, f"El {d.get('por')} {accion} la entrega de {alimento}.")]
        case "ENTREGA_COMPLETADA":
            return ambos(f"Entrega de {alimento} completada por ambas partes.")
        case "ENTREGA_CON_INCIDENCIA":
            return ambos(f"La entrega de {alimento} quedó CON INCIDENCIA.")
        case "ENTREGA_CANCELADA":
            return ambos(f"La entrega de {alimento} fue cancelada.")
        case "NECESIDAD_CREADA" | "NECESIDAD_CERRADA" | "NECESIDAD_CANCELADA":
            return [(receptor, f"Necesidad «{d.get('descripcion')}»: {e.estado_nuevo}.")]
    return []


def procesar(evento: Evento) -> int:
    pares = [(u, m) for u, m in destinatarios(evento) if u]
    if not pares:
        return 0
    with sesiones()() as db:
        if not primera_vez(db, evento, COLA):  # S6-05: reentrega del broker → sin notificaciones repetidas
            return 0
        for id_usuario, mensaje in pares:
            repo.crear_notificacion(db, id_usuario, evento.tipo, mensaje)
        db.commit()
    return len(pares)


def consumidores() -> list[Consumidor]:
    return [Consumidor(COLA, ["#"], procesar)]
