"""Pruebas del almacén contra PostgreSQL real: bases fuente temporales (migradas y sembradas) y un almacén
temporal. PRUEBAS_ADMIN_URL apunta a un superusuario del servidor (como en los servicios)."""
import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("EVENTOS_BACKEND", "memoria")

RAIZ = Path(__file__).resolve().parents[2]
for carpeta in ("identity-service", "catalog-geo-service", "fulfillment-service", "analytics-service", "comun"):
    sys.path.insert(0, str(RAIZ / "services" / carpeta))
sys.path.insert(0, str(RAIZ / "dwh"))

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

ADMIN_URL = os.environ.get("PRUEBAS_ADMIN_URL", "postgresql+psycopg://postgres@localhost:5432/postgres")
FUENTES = {"identity": ("identity-service", "identidad"), "catalog": ("catalog-geo-service", "catalogo"),
           "fulfillment": ("fulfillment-service", "cumplimiento"), "analytics": ("analytics-service", "analitica")}


def _crear_base(prefijo: str) -> str:
    nombre = f"prueba_{prefijo}_{uuid.uuid4().hex[:8]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {nombre}"))
    admin.dispose()
    return make_url(ADMIN_URL).set(database=nombre).render_as_string(hide_password=False)


def _borrar_base(url: str) -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {make_url(url).database} WITH (FORCE)"))
    admin.dispose()


def migrar(url: str, ini: Path) -> None:
    cfg = Config(str(ini))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def fuentes():
    """Bases transaccionales temporales con el esquema y los datos semilla de cada servicio."""
    urls = {}
    for nombre, (carpeta, paquete) in FUENTES.items():
        url = urls[nombre] = _crear_base(f"dwhfuente_{nombre}")
        migrar(url, RAIZ / "services" / carpeta / "alembic.ini")
        semilla = RAIZ / "services" / carpeta / paquete / "semilla.py"
        if semilla.exists():
            modulo = __import__(f"{paquete}.semilla", fromlist=["sembrar"])
            motor = create_engine(url)
            with Session(motor) as db:
                modulo.sembrar(db)
                db.commit()
            motor.dispose()
    yield urls
    for url in urls.values():
        _borrar_base(url)


@pytest.fixture
def motor_dwh():
    """Almacén nuevo para cada prueba."""
    url = _crear_base("dwh")
    migrar(url, RAIZ / "dwh" / "alembic.ini")
    motor = create_engine(url)
    yield motor
    motor.dispose()
    _borrar_base(url)


def valor(motor, sql: str, **params):
    with motor.connect() as c:
        return c.execute(text(sql), params).scalar()
