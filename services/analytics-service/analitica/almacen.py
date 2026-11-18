"""Conexión de solo lectura al almacén de datos (redalimenta_dwh) para la API de indicadores (S8-01).

La URL llega por DWH_DATABASE_URL (rol analytics_app, que solo tiene SELECT sobre dw). Las consultas además
corren en transacciones READ ONLY.
"""
import os
from collections.abc import Iterator

from sqlalchemy import Connection, Engine, create_engine

from .errores import ServicioNoDisponible

_motor: Engine | None = None


def motor_almacen() -> Engine:
    global _motor
    if _motor is None:
        url = os.environ.get("DWH_DATABASE_URL")
        if not url:
            raise ServicioNoDisponible("El almacén de datos no está configurado (DWH_DATABASE_URL)")
        _motor = create_engine(url, pool_pre_ping=True,
                               connect_args={"options": "-c default_transaction_read_only=on"})
    return _motor


def usar_motor(motor: Engine | None) -> None:
    global _motor
    _motor = motor


def conexion_almacen() -> Iterator[Connection]:
    with motor_almacen().connect() as c:
        yield c
