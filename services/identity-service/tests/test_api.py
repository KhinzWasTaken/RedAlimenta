"""S5-03, S5-04, S5-05: registro, JWT, perfil propio, verificación por el administrador y auditoría."""
import jwt
import pytest

from identidad.consumidor import procesar
from identidad.semilla import sembrar
from redalimenta_comun.eventos import Evento

from .conftest import token


@pytest.fixture
def semilla(Sesion):
    with Sesion() as db:
        sembrar(db)
        db.commit()


def entrar(cliente, correo, clave="demo123"):
    r = cliente.post("/api/auth/login", json={"correo": correo, "contrasena": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()


def test_registro_y_login_con_jwt(cliente, eventos):
    r = cliente.post("/api/auth/registro", json={"nombre": "Comedor Luz", "correo": "luz@ejemplo.co",
                                                 "contrasena": "clave-larga-1", "rol": "RECEPTOR"})
    assert r.status_code == 201, r.text
    assert r.json()["usuario"]["estado_verificacion"] == "PENDIENTE"
    assert "contrasena_hash" not in r.json()["usuario"]
    assert eventos.tipos() == ["USUARIO_REGISTRADO"]
    _, sesion = entrar(cliente, "LUZ@ejemplo.co", "clave-larga-1")
    carga = jwt.decode(sesion["token"], options={"verify_signature": False})
    assert carga["rol"] == "RECEPTOR" and carga["verificacion"] == "PENDIENTE" and "exp" in carga
    assert cliente.post("/api/auth/login", json={"correo": "luz@ejemplo.co", "contrasena": "x"}).status_code == 401
    duplicado = cliente.post("/api/auth/registro", json={"nombre": "Otro", "correo": "luz@ejemplo.co",
                                                          "contrasena": "clave-larga-2", "rol": "DONANTE"})
    assert duplicado.status_code == 409
    admin = cliente.post("/api/auth/registro", json={"nombre": "Yo", "correo": "yo@x.co",
                                                     "contrasena": "clave-larga-3", "rol": "ADMINISTRADOR"})
    assert admin.status_code == 400


def test_el_token_vence(cliente, semilla, monkeypatch):
    monkeypatch.setenv("JWT_MINUTOS", "-1")
    cabecera, _ = entrar(cliente, "donante@redalimenta.co")
    r = cliente.get("/api/auth/me", headers=cabecera)
    assert r.status_code == 401 and "venció" in r.json()["detail"]


def test_ruta_de_administrador_responde_403_a_un_donante(cliente, semilla):
    donante, _ = entrar(cliente, "donante@redalimenta.co")
    assert cliente.get("/api/admin/usuarios", headers=donante).status_code == 403
    assert cliente.get("/api/admin/usuarios").status_code == 401
    admin, _ = entrar(cliente, "admin@redalimenta.co")
    assert len(cliente.get("/api/admin/usuarios", headers=admin).json()) == 8


def test_perfil_propio(cliente, semilla, eventos):
    cabecera, _ = entrar(cliente, "donante@redalimenta.co")
    r = cliente.patch("/api/usuarios/me", json={"nombre": "La Cosecha S.A.S.", "telefono": "3109998877"},
                      headers=cabecera)
    assert r.json()["nombre"] == "La Cosecha S.A.S."
    nombres = cliente.get("/api/usuarios/nombres?ids=2,3,99", headers=cabecera).json()
    assert nombres == {"2": "La Cosecha S.A.S.", "3": "Comedor Comunitario Esperanza"}
    r = cliente.post("/api/usuarios/me/desactivar", headers=cabecera)
    assert r.json()["estado_cuenta"] == "DESACTIVADA"
    assert cliente.post("/api/auth/login", json={"correo": "donante@redalimenta.co",
                                                 "contrasena": "demo123"}).status_code == 401
    assert "USUARIO_DESACTIVADO" in eventos.tipos()


def test_verificacion_por_el_administrador_queda_auditada(cliente, semilla, eventos):
    admin, _ = entrar(cliente, "admin@redalimenta.co")
    receptor, sesion = entrar(cliente, "receptor@redalimenta.co")
    id_v = sesion["usuario"]["verificacion"]["id_verificacion"]
    r = cliente.post(f"/api/admin/verificaciones/{id_v}", json={"decision": "APROBADA", "observaciones": "RUT ok"},
                     headers=admin)
    assert r.json()["estado_verificacion"] == "APROBADA"
    # el receptor obtiene un token nuevo con el estado actualizado
    assert cliente.post("/api/auth/refresh", headers=receptor).json()["usuario"]["estado_verificacion"] == "APROBADA"
    # una verificación resuelta no se vuelve a resolver
    assert cliente.post(f"/api/admin/verificaciones/{id_v}", json={"decision": "RECHAZADA"},
                        headers=admin).status_code == 409
    historial = cliente.get(f"/api/admin/auditoria?entidad=verificacion&id_registro={id_v}", headers=admin).json()
    assert historial[0]["accion_realizada"] == "USUARIO_VERIFICADO"
    assert (historial[0]["valor_anterior"], historial[0]["valor_nuevo"]) == ("PENDIENTE", "APROBADA")
    assert historial[0]["actor"] == "Administración RedAlimenta"
    evento = eventos.eventos[-1]
    assert evento.tipo == "USUARIO_VERIFICADO" and evento.datos["id_usuario"] == 3


def test_el_consumidor_audita_eventos_de_otros_servicios(cliente, semilla):
    procesar(Evento(tipo="DONACION_RESERVADA", entidad="donacion", id_entidad=11, estado_anterior="DISPONIBLE",
                    estado_nuevo="RESERVADA", id_actor=5, origen="catalog-geo"))
    procesar(Evento(tipo="ENTREGA_CONFIRMADA", entidad="entrega", id_entidad=1, estado_anterior="PROGRAMADA",
                    estado_nuevo="PROGRAMADA", id_actor=999, datos={"por": "donante"}, origen="fulfillment"))
    admin, _ = entrar(cliente, "admin@redalimenta.co")
    reservada = cliente.get("/api/admin/auditoria?entidad=donacion&id_registro=11", headers=admin).json()
    assert reservada[0]["valor_nuevo"] == "RESERVADA" and reservada[0]["actor"] == "Fundación Manos Unidas"
    entrega = cliente.get("/api/admin/auditoria?entidad=entrega", headers=admin).json()[0]
    assert entrega["actor"] == "Sistema" and '"por": "donante"' in entrega["valor_nuevo"]  # actor desconocido


def test_salud(cliente):
    assert cliente.get("/salud").json() == {"estado": "ok", "servicio": "identity-service"}


def test_token_de_otro_servicio_es_valido_aqui(cliente, semilla):
    """D-06: cualquier servicio confía en el token firmado con el secreto compartido."""
    assert cliente.get("/api/usuarios/me", headers=token(5, "RECEPTOR")).json()["nombre"] == "Fundación Manos Unidas"


def test_evento_repetido_no_se_audita_dos_veces(cliente, semilla, Sesion):
    """S6-05: el broker puede entregar dos veces el mismo mensaje."""
    from sqlalchemy import func, select

    from identidad.modelos import RegistroAuditoria
    evento = Evento(tipo="DONACION_CREADA", entidad="donacion", id_entidad=40, estado_nuevo="DISPONIBLE",
                    id_actor=2, origen="catalog-geo")
    procesar(evento)
    procesar(Evento.desde_json(evento.a_json()))  # la misma entrega otra vez
    with Sesion() as db:
        assert db.scalar(select(func.count()).select_from(RegistroAuditoria).where(
            RegistroAuditoria.id_registro_afectado == 40)) == 1
