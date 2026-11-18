"""S4-06 y S4-07: notificación con usuario, índice por usuario y estado, permisos del rol de aplicación, esquema = modelo y migraciones reversibles."""
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError

from notificaciones.db import ROL_APP, Base
from notificaciones.semilla import sembrar

from .conftest import ADMIN_URL, alembic_cfg


def test_rol_de_aplicacion_solo_cambia_estado_y_lectura(db):
    sembrar(db)
    db.commit()
    db.execute(text(f"SET ROLE {ROL_APP}"))
    db.execute(text("UPDATE notificacion SET estado_notificacion = 'LEIDA', fecha_lectura = now() "
                    "WHERE id_notificacion = 1"))  # permitido
    for sentencia in ("DELETE FROM notificacion", "UPDATE notificacion SET mensaje = 'X'"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with db.begin_nested():
                db.execute(text(sentencia))
    db.rollback()


def test_no_hay_notificacion_sin_usuario_ni_mensaje(db):
    for valores in ("(NULL, 'X', 'Hola')", "(1, 'X', '   ')"):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(f"INSERT INTO notificacion (id_usuario, tipo_notificacion, mensaje) VALUES {valores}"))


def test_indice_por_usuario_y_estado(db):
    assert db.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_notificacion_usuario_estado'")) \
        .endswith("(id_usuario, estado_notificacion)")


def test_el_esquema_coincide_con_el_modelo(motor):
    with motor.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []


def test_migraciones_se_aplican_y_revierten_desde_cero():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_notification_mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    motor = create_engine(url)
    try:
        command.upgrade(alembic_cfg(url), "head")
        assert {"notificacion"} <= set(inspect(motor).get_table_names())
        command.downgrade(alembic_cfg(url), "base")
        with motor.connect() as c:
            assert set(inspect(c).get_table_names()) == {"alembic_version"}
        command.upgrade(alembic_cfg(url), "head")
    finally:
        motor.dispose()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
        admin.dispose()
