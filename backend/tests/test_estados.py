"""Transiciones de estado (docs/modelo/estados.md) y reglas que las acompañan."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DatabaseError

from app.catalogo import servicio as catalogo
from app.catalogo.busqueda import haversine_km, puntaje
from app.catalogo.modelos import Donacion
from app.core import estados
from app.core.errores import TransicionInvalida
from app.core.tiempo import ahora
from app.identidad.modelos import RegistroAuditoria
from app.reservas.modelos import Reserva

from .conftest import leer, login


@pytest.mark.parametrize("entidad,actual,nuevo,valida", [
    ("donacion", "DISPONIBLE", "RESERVADA", True),
    ("donacion", "RESERVADA", "DISPONIBLE", True),
    ("donacion", "RESERVADA", "ENTREGADA", True),
    ("donacion", "DISPONIBLE", "ENTREGADA", False),
    ("donacion", "VENCIDA", "DISPONIBLE", False),
    ("donacion", "ENTREGADA", "CANCELADA", False),
    ("donacion", "RESERVADA", "CANCELADA", False),
    ("reserva", "PENDIENTE", "CONFIRMADA", True),
    ("reserva", "PENDIENTE", "COMPLETADA", False),
    ("reserva", "EXPIRADA", "CONFIRMADA", False),
    ("reserva", "CONFIRMADA", "EXPIRADA", False),
    ("entrega", "PROGRAMADA", "COMPLETADA", True),
    ("entrega", "CON_INCIDENCIA", "COMPLETADA", False),
    ("verificacion", "APROBADA", "PENDIENTE", False),
    ("verificacion", "RECHAZADA", "PENDIENTE", False),
    ("notificacion", "ARCHIVADA", "NO_LEIDA", False),
])
def test_tabla_de_transiciones(entidad, actual, nuevo, valida):
    assert estados.es_valida(entidad, actual, nuevo) is valida


def test_catalogo_rechaza_transicion_ilegal(db):
    catalogo.transicionar_donacion(db, 1, "VENCIDA", None)
    with pytest.raises(TransicionInvalida):
        catalogo.transicionar_donacion(db, 1, "DISPONIBLE", None)


def test_verificacion_resuelta_no_se_resuelve_otra_vez(cliente, tokens):
    usuarios = cliente.get("/api/admin/usuarios", headers=tokens["admin"]).json()
    receptor = next(u for u in usuarios if u["rol"] == "RECEPTOR")
    r = cliente.post(f"/api/admin/verificaciones/{receptor['verificacion']['id_verificacion']}",
                     json={"decision": "RECHAZADA"}, headers=tokens["admin"])
    assert r.status_code == 409


def test_solo_verificados_y_con_rol_operan(cliente):
    sin_verificar = login(cliente, "receptor@redalimenta.co")
    assert cliente.post("/api/reservas", json={"id_donacion": 1}, headers=sin_verificar).status_code == 403
    donante = login(cliente, "donante@redalimenta.co")
    assert cliente.post("/api/reservas", json={"id_donacion": 1}, headers=donante).status_code == 403
    assert cliente.get("/api/admin/usuarios", headers=donante).status_code == 403
    assert cliente.get("/api/reservas/mias").status_code == 401


def test_forzar_expiracion_libera_la_donacion_y_es_idempotente(cliente, tokens, db):
    r = cliente.post("/api/reservas", json={"id_donacion": 4}, headers=tokens["receptor"])
    assert r.status_code == 201
    id_reserva = r.json()["id_reserva"]

    f = cliente.post(f"/api/reservas/{id_reserva}/forzar-expiracion", headers=tokens["receptor"])
    assert f.status_code == 200
    assert f.json()["estado_reserva"] == "EXPIRADA"
    assert leer(db, Donacion, 4, "estado_donacion") == "DISPONIBLE"

    auditoria_antes = db.scalar(select(func.count()).select_from(RegistroAuditoria))
    db.rollback()
    # correr las tareas otra vez no duplica efectos ni eventos
    segunda = cliente.post("/api/admin/tareas/ejecutar", headers=tokens["admin"]).json()
    assert segunda == {"reservas_expiradas": 0, "donaciones_vencidas": 0, "avisos_por_vencer": 0}
    assert db.scalar(select(func.count()).select_from(RegistroAuditoria)) == auditoria_antes
    db.rollback()

    # tras expirar, otro intento de reserva vuelve a funcionar
    assert cliente.post("/api/reservas", json={"id_donacion": 4}, headers=tokens["receptor"]).status_code == 201


def test_tarea_marca_vencidas(cliente, tokens, db):
    pasado = ahora() - timedelta(minutes=5)
    db.execute(update(Donacion).where(Donacion.id_donacion == 5).values(
        fecha_publicacion=pasado - timedelta(hours=1), fecha_vencimiento=pasado))
    db.commit()
    resultado = cliente.post("/api/admin/tareas/ejecutar", headers=tokens["admin"]).json()
    assert resultado["donaciones_vencidas"] == 1
    assert leer(db, Donacion, 5, "estado_donacion") == "VENCIDA"


def test_entrega_requiere_las_dos_confirmaciones(cliente, tokens, db):
    id_reserva = cliente.post("/api/reservas", json={"id_donacion": 6}, headers=tokens["receptor"]).json()["id_reserva"]
    confirmada = cliente.post(f"/api/reservas/{id_reserva}/confirmar", headers=tokens["donante"]).json()
    id_entrega = confirmada["entrega"]["id_entrega"]

    solo_donante = cliente.post(f"/api/entregas/{id_entrega}/confirmar", json={}, headers=tokens["donante"])
    assert solo_donante.json()["donacion"]["estado_donacion"] == "RESERVADA"
    repetida = cliente.post(f"/api/entregas/{id_entrega}/confirmar", json={}, headers=tokens["donante"])
    assert repetida.status_code == 409

    ambas = cliente.post(f"/api/entregas/{id_entrega}/confirmar", json={}, headers=tokens["receptor"]).json()
    assert ambas["donacion"]["estado_donacion"] == "ENTREGADA"
    assert ambas["estado_reserva"] == "COMPLETADA"
    assert ambas["entrega"]["estado_entrega"] == "COMPLETADA"


def test_solo_el_donante_confirma_y_cancelar_devuelve_disponible(cliente, tokens, db):
    id_reserva = cliente.post("/api/reservas", json={"id_donacion": 7}, headers=tokens["receptor"]).json()["id_reserva"]
    assert cliente.post(f"/api/reservas/{id_reserva}/confirmar", headers=tokens["receptor"]).status_code == 403
    assert cliente.post(f"/api/reservas/{id_reserva}/cancelar", headers=tokens["receptor"]).status_code == 200
    assert leer(db, Reserva, id_reserva, "estado_reserva") == "CANCELADA"
    assert leer(db, Donacion, 7, "estado_donacion") == "DISPONIBLE"
    # no se cancela una donación reservada: primero hay que liberar la reserva
    cliente.post("/api/reservas", json={"id_donacion": 7}, headers=tokens["receptor"])
    assert cliente.post("/api/donaciones/7/cancelar", headers=tokens["donante"]).status_code == 409


def test_auditoria_es_solo_insercion(cliente, tokens, db):
    assert db.scalar(select(func.count()).select_from(RegistroAuditoria)) >= 1
    with pytest.raises(DatabaseError):
        db.execute(text("UPDATE registro_auditoria SET accion_realizada = 'X'"))
    db.rollback()
    with pytest.raises(DatabaseError):
        db.execute(text("DELETE FROM registro_auditoria"))
    db.rollback()


def test_puntaje_d08_calculado_a_mano():
    # urgencia ALTA = 0,75; 5 km de 20 km → cercanía 0,75; 84 h de 168 h → vencimiento 0,5
    # 0,40·0,75 + 0,35·0,75 + 0,25·0,5 = 0,6875
    assert puntaje("ALTA", 5, 84, radio_km=20)["puntaje"] == pytest.approx(0.6875)
    assert puntaje(None, 50, 500, radio_km=20)["puntaje"] == 0


def test_haversine_bogota():
    # Plaza de Bolívar → Parque de la 93: ≈ 9,3 km
    assert haversine_km(4.5981, -74.0760, 4.6767, -74.0483) == pytest.approx(9.27, abs=0.2)
