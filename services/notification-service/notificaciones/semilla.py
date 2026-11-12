"""Datos semilla de notification-service (S4-08): avisos coherentes con las reservas semilla."""
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .modelos import Notificacion

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


def sembrar(db: Session) -> bool:
    if db.scalar(select(Notificacion.id_notificacion).limit(1)) is not None:
        return False
    for id_usuario, tipo, mensaje, estado in NOTIFICACIONES:
        db.add(Notificacion(id_usuario=id_usuario, tipo_notificacion=tipo, mensaje=mensaje,
                            estado_notificacion=estado,
                            fecha_lectura=text("now()") if estado in ("LEIDA", "ARCHIVADA") else None))
    db.flush()
    return True
