import os

from alembic import context
from sqlalchemy import create_engine

config = context.config
url = config.attributes.get("url") or os.environ.get("DWH_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("Define DWH_DATABASE_URL para ejecutar las migraciones del almacén")


def run_migrations_online() -> None:
    motor = create_engine(url)
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    motor.dispose()


run_migrations_online()
