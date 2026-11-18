"""Datos semilla de fulfillment-service (S4-08): reservas en todos los estados.

Coinciden con catalog-geo-service (catalogo/semilla.py): donación 11 y 15 RESERVADA, 12 ENTREGADA,
13 y 16 DISPONIBLE. Receptores: 5 (Medellín) y 7 (Cali); donantes: 4 (Medellín) y 6 (Cali).
"""
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .modelos import ConfirmacionEntrega, Entrega, Reserva

# id_reserva, id_donacion, id_receptor, horas desde que se reservó, estado
RESERVAS = [
    (1, 11, 5, 0.5, "PENDIENTE"),
    (2, 15, 7, 3, "CONFIRMADA"),
    (3, 12, 5, 26, "COMPLETADA"),
    (4, 16, 7, 5, "EXPIRADA"),
    (5, 13, 5, 8, "CANCELADA"),
]


def sembrar(db: Session) -> bool:
    if db.scalar(select(Reserva.id_reserva).limit(1)) is not None:
        return False
    ahora = db.scalar(func.now())
    for id_r, id_d, receptor, horas, estado in RESERVAS:
        reservada = ahora - timedelta(hours=horas)
        db.add(Reserva(id_reserva=id_r, id_donacion=id_d, id_receptor=receptor, fecha_reserva=reservada,
                       fecha_expiracion=reservada + timedelta(hours=2), estado_reserva=estado))
    db.flush()
    db.add(Entrega(id_entrega=1, id_reserva=2, fecha_programada=ahora + timedelta(days=1),
                   estado_entrega="PROGRAMADA"))
    db.add(Entrega(id_entrega=2, id_reserva=3, fecha_programada=ahora - timedelta(hours=20),
                   fecha_entrega=ahora - timedelta(hours=18), estado_entrega="COMPLETADA"))
    db.flush()
    db.add(ConfirmacionEntrega(id_entrega=2, id_usuario=4, estado_confirmacion="CONFIRMADA",
                               fecha_confirmacion=ahora - timedelta(hours=18, minutes=30)))
    db.add(ConfirmacionEntrega(id_entrega=2, id_usuario=5, estado_confirmacion="CONFIRMADA",
                               fecha_confirmacion=ahora - timedelta(hours=18), observaciones="Llegó completo"))
    db.flush()
    for tabla, columna in (("reserva", "id_reserva"), ("entrega", "id_entrega"),
                           ("confirmacion_entrega", "id_confirmacion")):
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabla}', '{columna}'), "
                        f"(SELECT max({columna}) FROM {tabla}))"))
    return True
