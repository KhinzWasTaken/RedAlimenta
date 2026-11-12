"""Conexión a la base del servicio. La URL llega por la variable de entorno DATABASE_URL."""
import os
import re

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

NOMBRE_SERVICIO = "identity"
ROL_APP = os.environ.get("IDENTITY_APP_ROLE", "identity_app")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", ROL_APP):
    raise ValueError("IDENTITY_APP_ROLE no es un identificador válido")

# Nombres de restricciones e índices predecibles (los usan las migraciones y los mensajes de error)
CONVENCION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION)


def crear_motor(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Define DATABASE_URL (postgresql+psycopg://usuario:clave@host:puerto/redalimenta_identity)")
    return create_engine(url, pool_pre_ping=True)


def crear_sesiones(url: str | None = None):
    return sessionmaker(bind=crear_motor(url), autoflush=False, expire_on_commit=False)


_sesiones = None


def sesiones() -> sessionmaker:
    """Fábrica de sesiones del proceso (se crea al primer uso con DATABASE_URL)."""
    global _sesiones
    if _sesiones is None:
        _sesiones = crear_sesiones()
    return _sesiones


def usar_sesiones(fabrica: sessionmaker) -> None:
    """Permite a las pruebas apuntar el servicio a una base temporal."""
    global _sesiones
    _sesiones = fabrica
