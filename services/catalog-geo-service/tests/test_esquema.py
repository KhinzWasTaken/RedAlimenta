"""S4-04 y S4-07: PostGIS, restricciones, reglas de estado en la base, permisos y migraciones reversibles."""
import uuid
from datetime import timedelta

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from catalogo import repositorio as repo
from catalogo.db import ROL_APP, Base
from catalogo.semilla import sembrar

from .conftest import ADMIN_URL, alembic_cfg

BOGOTA = dict(lat=4.6097, lon=-74.0817, ciudad="Bogotá", departamento="Cundinamarca")


def nueva(db, **extra):
    datos = dict(nombre_alimento="Arroz", id_categoria=4, cantidad=10, unidad_medida="kg",
                 fecha_vencimiento=db.scalar(func.now()) + timedelta(days=2), **BOGOTA)
    datos.update(extra)
    return repo.crear_donacion(db, 2, **datos)


def test_postgis_y_indice_espacial(db):
    assert db.scalar(text("SELECT postgis_version()"))
    assert db.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_ubicacion_coordenada'")) \
        .lower().find("using gist") > 0
    assert db.scalar(text("SELECT srid FROM geography_columns WHERE f_table_name = 'ubicacion_geografica'")) == 4326


def test_cantidad_positiva_y_vencimiento_posterior(db):
    d = nueva(db)
    db.commit()
    with pytest.raises(IntegrityError, match="ck_donacion_cantidad_positiva"):
        with db.begin_nested():
            db.execute(text("UPDATE donacion SET cantidad = 0 WHERE id_donacion = :i"), {"i": d.id_donacion})
    with pytest.raises(IntegrityError, match="ck_donacion_vence_despues_de_publicar"):
        with db.begin_nested():
            db.execute(text("UPDATE donacion SET fecha_vencimiento = fecha_publicacion - interval '1 hour' "
                            "WHERE id_donacion = :i"), {"i": d.id_donacion})
    with pytest.raises(DBAPIError):  # estado fuera del ENUM
        with db.begin_nested():
            db.execute(text("UPDATE donacion SET estado_donacion = 'PERDIDA' WHERE id_donacion = :i"),
                       {"i": d.id_donacion})


def test_la_base_rechaza_transiciones_ilegales(db):
    d = nueva(db)
    db.execute(text("UPDATE donacion SET estado_donacion = 'VENCIDA' WHERE id_donacion = :i"), {"i": d.id_donacion})
    db.commit()
    with pytest.raises(DBAPIError, match="VENCIDA → DISPONIBLE"):
        with db.begin_nested():
            db.execute(text("UPDATE donacion SET estado_donacion = 'DISPONIBLE' WHERE id_donacion = :i"),
                       {"i": d.id_donacion})


def test_no_se_modifica_una_donacion_reservada(db):
    d = nueva(db)
    repo.transicionar_donacion(db, d.id_donacion, "RESERVADA")
    db.commit()
    with pytest.raises(DBAPIError, match="Solo se modifica una donación DISPONIBLE"):
        with db.begin_nested():
            db.execute(text("UPDATE donacion SET cantidad = 5 WHERE id_donacion = :i"), {"i": d.id_donacion})


def test_rol_de_aplicacion_no_borra(db):
    sembrar(db)
    db.commit()
    db.execute(text(f"SET ROLE {ROL_APP}"))
    assert db.scalar(text("SELECT count(*) FROM donacion")) == 18
    for tabla in ("donacion", "necesidad_alimentaria", "categoria_alimento"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with db.begin_nested():
                db.execute(text(f"DELETE FROM {tabla}"))
    db.rollback()


def test_el_esquema_coincide_con_el_modelo(motor):
    with motor.connect() as c:
        diferencias = compare_metadata(MigrationContext.configure(c), Base.metadata)
    # spatial_ref_sys pertenece a PostGIS, no al modelo
    assert [d for d in diferencias if "spatial_ref_sys" not in str(d)] == []


def test_migraciones_se_aplican_y_revierten_desde_cero():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_catalog_mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    motor = create_engine(url)
    try:
        command.upgrade(alembic_cfg(url), "head")
        assert {"categoria_alimento", "ubicacion_geografica", "donacion", "necesidad_alimentaria"} <= \
            set(inspect(motor).get_table_names())
        command.downgrade(alembic_cfg(url), "base")
        with motor.connect() as c:
            assert set(inspect(c).get_table_names()) == {"alembic_version", "spatial_ref_sys"}
        command.upgrade(alembic_cfg(url), "head")
    finally:
        motor.dispose()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
        admin.dispose()
