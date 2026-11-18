"""S5-10 a S5-13: reserva concurrente por la API, compensación, confirmaciones, entrega y tareas."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from cumplimiento.catalogo_cliente import usar_cliente
from cumplimiento.modelos import Reserva

from .catalogo_falso import CatalogoFalso
from .conftest import token

RECEPTOR, OTRO_RECEPTOR = token(5, "RECEPTOR"), token(7, "RECEPTOR")
DONANTE, OTRO_DONANTE, ADMIN = token(4, "DONANTE"), token(6, "DONANTE"), token(1, "ADMINISTRADOR")


@pytest.fixture
def catalogo():
    falso = CatalogoFalso()
    usar_cliente(falso)
    return falso


def reservar(cliente, id_donacion=10, cabecera=RECEPTOR):
    return cliente.post("/api/reservas", json={"id_donacion": id_donacion}, headers=cabecera)


def test_dos_solicitudes_simultaneas_201_y_409(cliente, catalogo):
    barrera = threading.Barrier(2)

    def intentar(cabecera):
        barrera.wait()
        return reservar(cliente, 10, cabecera).status_code

    with ThreadPoolExecutor(2) as grupo:
        codigos = sorted(grupo.map(intentar, [RECEPTOR, OTRO_RECEPTOR]))
    assert codigos == [201, 409]
    assert catalogo.datos[10]["estado_donacion"] == "RESERVADA"
    assert catalogo.transiciones == [(10, "RESERVADA")]


def test_solo_receptores_verificados_reservan(cliente, catalogo):
    assert reservar(cliente, 10, token(3, "RECEPTOR", "PENDIENTE")).status_code == 403
    assert reservar(cliente, 10, DONANTE).status_code == 403
    assert reservar(cliente, 99).status_code == 404


def test_si_catalog_rechaza_la_reserva_queda_cancelada(cliente, catalogo, eventos, Sesion):
    catalogo.rechazar_transiciones = True
    r = reservar(cliente)
    assert r.status_code == 409 and "No se pudo reservar" in r.json()["detail"]
    with Sesion() as db:
        assert [x.estado_reserva for x in db.scalars(select(Reserva))] == ["CANCELADA"]
    assert eventos.tipos() == ["RESERVA_CREADA", "RESERVA_CANCELADA"]


def test_si_catalog_esta_caido_no_quedan_reservas_huerfanas(cliente, catalogo, Sesion):
    catalogo.caido = True
    assert reservar(cliente).status_code == 503
    catalogo.caido = False
    with Sesion() as db:
        assert db.scalar(select(func.count()).select_from(Reserva).where(
            Reserva.estado_reserva.in_(("PENDIENTE", "CONFIRMADA")))) == 0
    assert reservar(cliente).status_code == 201  # se puede volver a intentar


def test_solo_el_donante_confirma_y_cancelar_libera(cliente, catalogo, eventos):
    reserva = reservar(cliente).json()
    assert reserva["fecha_expiracion"] and reserva["donacion"]["nombre_alimento"] == "Fríjol"
    assert cliente.post(f"/api/reservas/{reserva['id_reserva']}/confirmar", headers=OTRO_DONANTE).status_code == 403
    confirmada = cliente.post(f"/api/reservas/{reserva['id_reserva']}/confirmar", headers=DONANTE).json()
    assert confirmada["estado_reserva"] == "CONFIRMADA" and confirmada["entrega"]["estado_entrega"] == "PROGRAMADA"
    assert cliente.post(f"/api/reservas/{reserva['id_reserva']}/cancelar", headers=OTRO_RECEPTOR).status_code == 403
    cancelada = cliente.post(f"/api/reservas/{reserva['id_reserva']}/cancelar", headers=RECEPTOR).json()
    assert cancelada["estado_reserva"] == "CANCELADA" and cancelada["entrega"]["estado_entrega"] == "CANCELADA"
    assert catalogo.datos[10]["estado_donacion"] == "DISPONIBLE"
    assert eventos.tipos()[-4:] == ["RESERVA_CONFIRMADA", "ENTREGA_PROGRAMADA", "RESERVA_CANCELADA",
                                    "ENTREGA_CANCELADA"]


def test_entrega_con_las_dos_confirmaciones(cliente, catalogo, eventos):
    r = reservar(cliente).json()
    entrega = cliente.post(f"/api/reservas/{r['id_reserva']}/confirmar", headers=DONANTE).json()["entrega"]
    ruta = f"/api/entregas/{entrega['id_entrega']}/confirmar"
    assert cliente.post(ruta, json={}, headers=OTRO_DONANTE).status_code == 403
    una = cliente.post(ruta, json={}, headers=RECEPTOR).json()
    assert una["entrega"]["estado_entrega"] == "PROGRAMADA" and catalogo.datos[10]["estado_donacion"] == "RESERVADA"
    assert cliente.post(ruta, json={}, headers=RECEPTOR).status_code == 409
    dos = cliente.post(ruta, json={"observaciones": "Todo bien"}, headers=DONANTE).json()
    assert dos["estado_reserva"] == "COMPLETADA" and dos["entrega"]["estado_entrega"] == "COMPLETADA"
    assert catalogo.datos[10]["estado_donacion"] == "ENTREGADA"
    assert eventos.tipos()[-4:] == ["ENTREGA_CONFIRMADA", "ENTREGA_CONFIRMADA", "ENTREGA_COMPLETADA",
                                    "RESERVA_COMPLETADA"]
    assert [x["id_reserva"] for x in cliente.get("/api/entregas/mias", headers=DONANTE).json()] == [r["id_reserva"]]


def test_incidencia_queda_registrada(cliente, catalogo):
    r = reservar(cliente).json()
    entrega = cliente.post(f"/api/reservas/{r['id_reserva']}/confirmar", headers=DONANTE).json()["entrega"]
    x = cliente.post(f"/api/entregas/{entrega['id_entrega']}/confirmar",
                     json={"estado_confirmacion": "CON_INCIDENCIA", "observaciones": "Llegó la mitad"},
                     headers=RECEPTOR).json()
    assert x["entrega"]["estado_entrega"] == "CON_INCIDENCIA" and x["entrega"]["observaciones"] == "Llegó la mitad"


def test_tareas_idempotentes_expiran_avisan_y_concilian(cliente, catalogo, eventos):
    r = reservar(cliente).json()
    forzada = cliente.post(f"/api/reservas/{r['id_reserva']}/forzar-expiracion", headers=RECEPTOR).json()
    assert forzada["estado_reserva"] == "EXPIRADA" and forzada["tareas"]["reservas_expiradas"] == 1
    assert catalogo.datos[10]["estado_donacion"] == "DISPONIBLE"
    assert forzada["tareas"]["avisos_por_vencer"] == 1  # la donación 11 vence en 5 h
    antes = len(eventos.eventos)
    segunda = cliente.post("/api/tareas/ejecutar", headers=ADMIN).json()
    assert segunda == {"reservas_expiradas": 0, "donaciones_vencidas": 0, "avisos_por_vencer": 0, "conciliadas": 0}
    assert len(eventos.eventos) == antes  # sin eventos duplicados
    # conciliación: la donación 12 quedó RESERVADA sin reserva activa (p. ej. falló una llamada)
    catalogo.datos[12]["estado_donacion"] = "RESERVADA"
    assert cliente.post("/api/tareas/ejecutar", headers=ADMIN).json()["conciliadas"] == 1
    assert catalogo.datos[12]["estado_donacion"] == "DISPONIBLE"
    assert cliente.post("/api/tareas/ejecutar", headers=RECEPTOR).status_code == 403


def test_mis_reservas_por_rol(cliente, catalogo):
    reservar(cliente, 10)
    reservar(cliente, 12, OTRO_RECEPTOR)
    assert [x["id_donacion"] for x in cliente.get("/api/reservas/mias", headers=RECEPTOR).json()] == [10]
    assert [x["id_donacion"] for x in cliente.get("/api/reservas/mias", headers=OTRO_DONANTE).json()] == [12]
    assert cliente.get("/api/reservas/mias", headers=DONANTE).json()[0]["soy"] == "donante"
