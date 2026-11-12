"""S4-03 y S4-07: restricciones del esquema, permisos del rol de aplicación y migraciones reversibles."""
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from identidad import repositorio as repo
from identidad.db import ROL_APP, Base
from identidad.semilla import sembrar

from .conftest import ADMIN_URL, alembic_cfg


def test_correo_unico_sin_distinguir_mayusculas(db):
    repo.crear_usuario(db, "Ana", "ana@ejemplo.co", "x", "DONANTE")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO usuario (id_rol, nombre, correo_electronico, contrasena_hash) "
                            "VALUES (1, 'Otra', 'ANA@EJEMPLO.CO', 'x')"))


def test_estados_y_claves_validas(db):
    with pytest.raises(DBAPIError):  # valor fuera del ENUM
        with db.begin_nested():
            db.execute(text("INSERT INTO usuario (id_rol, nombre, correo_electronico, contrasena_hash, "
                            "estado_cuenta) VALUES (1, 'X', 'x@x.co', 'x', 'BORRADA')"))
    with pytest.raises(IntegrityError):  # rol inexistente
        with db.begin_nested():
            db.execute(text("INSERT INTO usuario (id_rol, nombre, correo_electronico, contrasena_hash) "
                            "VALUES (9, 'X', 'y@x.co', 'x')"))
    with pytest.raises(IntegrityError):  # correo sin formato
        with db.begin_nested():
            db.execute(text("INSERT INTO usuario (id_rol, nombre, correo_electronico, contrasena_hash) "
                            "VALUES (1, 'X', 'sin-arroba', 'x')"))


def test_rol_de_aplicacion_no_modifica_ni_borra_auditoria(db):
    sembrar(db)
    db.commit()
    db.execute(text(f"SET ROLE {ROL_APP}"))
    db.execute(text("INSERT INTO registro_auditoria (entidad_afectada, id_registro_afectado, accion_realizada) "
                    "VALUES ('donacion', 1, 'DONACION_CREADA')"))  # insertar sí puede
    for sentencia in ("UPDATE registro_auditoria SET accion_realizada = 'X'",
                      "DELETE FROM registro_auditoria",
                      "DELETE FROM usuario WHERE id_usuario = 8"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with db.begin_nested():
                db.execute(text(sentencia))
    db.rollback()


def test_auditoria_inmutable_incluso_para_el_dueno(db):
    sembrar(db)
    db.commit()
    with pytest.raises(DBAPIError, match="solo inserción"):
        with db.begin_nested():
            db.execute(text("UPDATE registro_auditoria SET valor_nuevo = 'X'"))
    with pytest.raises(DBAPIError, match="solo inserción"):
        with db.begin_nested():
            db.execute(text("DELETE FROM registro_auditoria"))


def test_el_esquema_coincide_con_el_modelo(motor):
    with motor.connect() as c:
        diferencias = compare_metadata(MigrationContext.configure(c), Base.metadata)
    # El índice funcional lower(correo) no lo puede comparar Alembic; lo demás debe coincidir
    diferencias = [d for d in diferencias if "ux_usuario_correo" not in str(d)]
    assert diferencias == []


def test_migraciones_se_aplican_y_revierten_desde_cero():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_identity_mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    motor = create_engine(url)
    try:
        command.upgrade(alembic_cfg(url), "head")
        assert {"rol", "usuario", "verificacion_usuario", "registro_auditoria"} <= set(inspect(motor).get_table_names())
        command.downgrade(alembic_cfg(url), "base")
        with motor.connect() as c:
            assert set(inspect(c).get_table_names()) == {"alembic_version"}
            assert c.scalar(text("SELECT count(*) FROM pg_type WHERE typname IN "
                                 "('estado_cuenta', 'estado_verificacion')")) == 0
        command.upgrade(alembic_cfg(url), "head")  # y se puede volver a aplicar
    finally:
        motor.dispose()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
        admin.dispose()
