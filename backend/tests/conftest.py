import os
import tempfile
from pathlib import Path

# Base de pruebas aislada y sin planificador; debe definirse antes de importar la app
_DIR = Path(tempfile.mkdtemp(prefix="redalimenta-pruebas-"))
os.environ["REDALIMENTA_DB_URL"] = f"sqlite:///{_DIR / 'pruebas.db'}"
os.environ["REDALIMENTA_PLANIFICADOR"] = "0"
os.environ["REDALIMENTA_MODO_DEMO"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SesionLocal, borrar_esquema, crear_esquema  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import CONTRASENA_DEMO, sembrar  # noqa: E402


@pytest.fixture(autouse=True)
def base_limpia():
    borrar_esquema()
    crear_esquema()
    with SesionLocal() as db:
        sembrar(db)
    yield


@pytest.fixture
def db():
    with SesionLocal() as sesion:
        yield sesion


def leer(db, modelo, id_, campo):
    """Lee un campo y cierra la transacción (BEGIN IMMEDIATE bloquearía a la API)."""
    db.expire_all()
    valor = getattr(db.get(modelo, id_), campo)
    db.rollback()
    return valor


@pytest.fixture
def cliente():
    return TestClient(app)


def login(cliente, correo, contrasena=CONTRASENA_DEMO):
    r = cliente.post("/api/auth/login", json={"correo": correo, "contrasena": contrasena})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def tokens(cliente):
    """Tokens de los tres usuarios semilla, con el receptor ya verificado por el administrador."""
    admin = login(cliente, "admin@redalimenta.co")
    usuarios = cliente.get("/api/admin/usuarios", headers=admin).json()
    receptor = next(u for u in usuarios if u["rol"] == "RECEPTOR")
    r = cliente.post(f"/api/admin/verificaciones/{receptor['verificacion']['id_verificacion']}",
                     json={"decision": "APROBADA"}, headers=admin)
    assert r.status_code == 200, r.text
    return {
        "admin": admin,
        "donante": login(cliente, "donante@redalimenta.co"),
        "receptor": login(cliente, "receptor@redalimenta.co"),
    }
