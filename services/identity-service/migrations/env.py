import os

from alembic import context
from sqlalchemy import create_engine

from identidad.db import Base
from identidad import modelos  # noqa: F401  (registra las tablas)

config = context.config
url = config.attributes.get("url") or os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("Define DATABASE_URL para ejecutar las migraciones")


def run_migrations_online() -> None:
    conexion_externa = config.attributes.get("connection")
    if conexion_externa is not None:
        context.configure(connection=conexion_externa, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    motor = create_engine(url)
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    motor.dispose()


run_migrations_online()
