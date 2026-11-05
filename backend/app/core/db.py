"""Motor SQLite y sesión.

Cada transacción empieza con BEGIN IMMEDIATE: SQLite serializa las escrituras y
evita el error "database is locked" por promoción de bloqueos. El control de
reserva única lo garantiza además el índice único parcial (D-02).
"""
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


def _crear_motor(url: str):
    motor = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(motor, "connect")
    def _al_conectar(conexion, _registro):
        conexion.isolation_level = None  # SQLAlchemy maneja BEGIN
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @event.listens_for(motor, "begin")
    def _al_iniciar(conexion):
        conexion.exec_driver_sql("BEGIN IMMEDIATE")

    return motor


motor = _crear_motor(config.DB_URL)
SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def obtener_db() -> Iterator[Session]:
    db = SesionLocal()
    try:
        yield db
    finally:
        db.close()


def crear_esquema() -> None:
    # Importa los modelos de cada módulo para registrarlos en Base.metadata
    from app.catalogo import modelos as _c  # noqa: F401
    from app.identidad import modelos as _i  # noqa: F401
    from app.notificaciones import modelos as _n  # noqa: F401
    from app.reservas import modelos as _r  # noqa: F401

    Base.metadata.create_all(motor)


def borrar_esquema() -> None:
    crear_esquema()
    Base.metadata.drop_all(motor)
