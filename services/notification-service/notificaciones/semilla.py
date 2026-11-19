"""Datos semilla de notification-service (S4-08): avisos coherentes con las reservas semilla."""
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .modelos import Conversacion, Mensaje, Notificacion

# id_usuario, tipo, mensaje, estado
NOTIFICACIONES = [
    (5, "RESERVA_CREADA", "Reservaste «Bandejas paisas». El donante debe confirmar en las próximas 2 horas.",
     "NO_LEIDA"),
    (4, "DONACION_RESERVADA", "«Bandejas paisas» fue reservada por Fundación Manos Unidas. Confírmala a tiempo.",
     "NO_LEIDA"),
    (7, "RESERVA_CONFIRMADA", "El donante confirmó tu reserva de «Mercados familiares».", "LEIDA"),
    (6, "ENTREGA_PROGRAMADA", "Entrega de «Mercados familiares» programada para mañana.", "NO_LEIDA"),
    (5, "ENTREGA_COMPLETADA", "Entrega de «Arepas de maíz» completada por ambas partes.", "LEIDA"),
    (4, "DONACION_ENTREGADA", "«Arepas de maíz» quedó ENTREGADA. ¡Gracias por donar!", "ARCHIVADA"),
    (7, "RESERVA_EXPIRADA", "Tu reserva de «Plátano y yuca» expiró sin confirmación.", "NO_LEIDA"),
    (2, "DONACION_POR_VENCER", "«Almuerzos preparados» vence en menos de 24 horas.", "NO_LEIDA"),
]


# D-12: chats de las reservas semilla. donación, donante, receptor, alimento, estado, [(autor, texto)]
CONVERSACIONES = [
    (11, 4, 5, "Bandejas paisas", "ABIERTA", [
        (5, "Hola, reservamos las bandejas. ¿Podemos recogerlas hoy a las 4 p. m.?"),
        (4, "Claro, por la puerta de la cocina. Traigan neveras portátiles, por favor."),
    ]),
    (15, 6, 7, "Mercados familiares", "ABIERTA", [
        (6, "Confirmé la reserva. ¿Les sirve mañana a las 9 a. m. en la bodega?"),
    ]),
    (12, 4, 5, "Arepas de maíz", "CERRADA", [
        (5, "Recibimos las arepas, ¡muchas gracias!"),
    ]),
]


def sembrar(db: Session) -> bool:
    if db.scalar(select(Notificacion.id_notificacion).limit(1)) is not None:
        return False
    for id_usuario, tipo, mensaje, estado in NOTIFICACIONES:
        db.add(Notificacion(id_usuario=id_usuario, tipo_notificacion=tipo, mensaje=mensaje,
                            estado_notificacion=estado,
                            fecha_lectura=text("now()") if estado in ("LEIDA", "ARCHIVADA") else None))
    for id_donacion, donante, receptor, alimento, estado, mensajes in CONVERSACIONES:
        c = Conversacion(id_donacion=id_donacion, id_donante=donante, id_receptor=receptor,
                         nombre_alimento=alimento, origen="RESERVA")
        db.add(c)
        db.flush()
        for autor, texto in mensajes:  # se escriben con la conversación abierta (el trigger lo exige)
            db.add(Mensaje(id_conversacion=c.id_conversacion, id_autor=autor, texto=texto))
            db.flush()
        if estado == "CERRADA":
            c.estado_conversacion, c.fecha_cierre = "CERRADA", text("now()")
    db.flush()
    return True
