"""Pruebas contra PostgreSQL real (no se simula la base, plan sección 8).

Crea una base temporal en el servidor indicado por PRUEBAS_ADMIN_URL (un superusuario), aplica
las migraciones, y la borra al final. Ejemplo:
    PRUEBAS_ADMIN_URL=postgresql+psycopg://postgres:clave@localhost:5432/postgres pytest
"""
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from cumplimiento.db import ROL_APP

SERVICIO = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("PRUEBAS_ADMIN_URL", "postgresql+psycopg://postgres@localhost:5432/postgres")
TABLAS = ("confirmacion_entrega", "entrega", "reserva")


def alembic_cfg(url: str) -> Config:
    cfg = Config(str(SERVICIO / "alembic.ini"))
    cfg.attributes["url"] = url
    return cfg


@pytest.fixture(scope="session")
def url_base():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    nombre = f"prueba_fulfillment_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        if not c.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROL_APP}):
            c.execute(text(f"CREATE ROLE {ROL_APP} NOLOGIN"))
        c.execute(text(f"CREATE DATABASE {nombre}"))
    url = make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)
    command.upgrade(alembic_cfg(url), "head")
    yield url
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def motor(url_base):
    m = create_engine(url_base)
    yield m
    m.dispose()


@pytest.fixture
def Sesion(motor):
    # Cada prueba empieza con las tablas vacías
    with motor.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(Sesion):
    with Sesion() as sesion:
        yield sesion
        sesion.rollback()
