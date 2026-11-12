"""S4-05 y S4-07: permisos del rol de aplicación, esquema = modelo y migraciones reversibles."""
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from cumplimiento.db import ROL_APP, Base
from cumplimiento.semilla import sembrar

from .conftest import ADMIN_URL, alembic_cfg


def test_rol_de_aplicacion_no_borra_ni_altera_confirmaciones(db):
    sembrar(db)
    db.commit()
    db.execute(text(f"SET ROLE {ROL_APP}"))
    assert db.scalar(text("SELECT count(*) FROM reserva")) == 5
    for sentencia in ("DELETE FROM reserva", "DELETE FROM entrega",
                      "UPDATE confirmacion_entrega SET estado_confirmacion = 'CON_INCIDENCIA'"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with db.begin_nested():
                db.execute(text(sentencia))
    db.rollback()


def test_el_esquema_coincide_con_el_modelo(motor):
    with motor.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []


def test_migraciones_se_aplican_y_revierten_desde_cero():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_fulfillment_mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    motor = create_engine(url)
    try:
        command.upgrade(alembic_cfg(url), "head")
        assert {"reserva", "entrega", "confirmacion_entrega"} <= set(inspect(motor).get_table_names())
        command.downgrade(alembic_cfg(url), "base")
        with motor.connect() as c:
            assert set(inspect(c).get_table_names()) == {"alembic_version"}
        command.upgrade(alembic_cfg(url), "head")
    finally:
        motor.dispose()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
        admin.dispose()
