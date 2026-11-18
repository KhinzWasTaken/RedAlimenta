"""S5-15: guarda cada evento sin permitir modificarlo; consulta por entidad y por usuario."""
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from analitica.consumidor import procesar
from analitica.db import ROL_APP, Base
from analitica.modelos import HistorialEvento
from redalimenta_comun.eventos import Evento

from .conftest import ADMIN_URL, alembic_cfg, token

ADMIN = token(1, "ADMINISTRADOR")


def ev(tipo, entidad, id_entidad, anterior, nuevo, actor, **datos):
    return Evento(tipo=tipo, entidad=entidad, id_entidad=id_entidad, estado_anterior=anterior, estado_nuevo=nuevo,
                  id_actor=actor, datos=datos, origen="prueba")


def test_guarda_sin_duplicar_y_consulta(cliente, Sesion):
    creada = ev("DONACION_CREADA", "donacion", 11, None, "DISPONIBLE", 4, id_donante=4)
    assert procesar(creada) is True
    assert procesar(creada) is False  # el broker lo reentregó: no se duplica
    procesar(ev("DONACION_RESERVADA", "donacion", 11, "DISPONIBLE", "RESERVADA", 5, id_donante=4, id_receptor=5))
    procesar(ev("RESERVA_CREADA", "reserva", 1, None, "PENDIENTE", 5, id_donante=4, id_receptor=5))
    procesar(ev("USUARIO_VERIFICADO", "verificacion", 3, "PENDIENTE", "APROBADA", 1, id_usuario=3))
    with Sesion() as db:
        assert db.scalar(select(func.count()).select_from(HistorialEvento)) == 4
    vida = cliente.get("/api/historial/entidades/donacion?id_entidad=11", headers=ADMIN).json()
    assert [(h["estado_anterior"], h["estado_nuevo"]) for h in vida] == [(None, "DISPONIBLE"), ("DISPONIBLE", "RESERVADA")]
    assert {h["tipo"] for h in cliente.get("/api/historial/usuarios/5", headers=ADMIN).json()} == {
        "DONACION_RESERVADA", "RESERVA_CREADA"}
    assert len(cliente.get("/api/historial/usuarios/4", headers=ADMIN).json()) == 3  # participa como donante
    assert cliente.get("/api/historial/usuarios/3", headers=ADMIN).json()[0]["tipo"] == "USUARIO_VERIFICADO"
    assert cliente.get("/api/historial/usuarios/5", headers=token(5, "RECEPTOR")).status_code == 403


def test_historial_inmutable(db):
    procesar(ev("DONACION_CREADA", "donacion", 1, None, "DISPONIBLE", 2))
    with pytest.raises(DBAPIError, match="solo inserción"):
        with db.begin_nested():
            db.execute(text("UPDATE historial_evento SET tipo = 'X'"))
    db.execute(text(f"SET ROLE {ROL_APP}"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with db.begin_nested():
            db.execute(text("DELETE FROM historial_evento"))
    db.rollback()


def test_esquema_y_migraciones(motor):
    with motor.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_analytics_mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    m = create_engine(url)
    try:
        command.upgrade(alembic_cfg(url), "head")
        command.downgrade(alembic_cfg(url), "base")
        assert set(inspect(m).get_table_names()) == {"alembic_version"}
    finally:
        m.dispose()
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
        admin.dispose()
