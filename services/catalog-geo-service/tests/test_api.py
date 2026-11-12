"""S5-06 a S5-09: donaciones, necesidades, búsqueda y la transición interna de estado (D-01)."""
from datetime import UTC, datetime, timedelta

import pytest

from catalogo.semilla import sembrar

from .conftest import INTERNO, token

DONANTE, DONANTE_MED, RECEPTOR, RECEPTOR_MED = token(2, "DONANTE"), token(4, "DONANTE"), token(3, "RECEPTOR"), \
    token(5, "RECEPTOR")
ADMIN = token(1, "ADMINISTRADOR")
UBICACION = {"lat": 4.5700, "lon": -74.1300, "direccion_referencia": "Calle 60 Sur # 20-10",
             "ciudad": "Bogotá", "departamento": "Cundinamarca"}


@pytest.fixture
def semilla(Sesion):
    with Sesion() as db:
        sembrar(db)
        db.commit()


def nueva(**extra):
    return {"nombre_alimento": "Lentejas", "id_categoria": 4, "cantidad": 50, "unidad_medida": "kg",
            "fecha_vencimiento": (datetime.now(UTC) + timedelta(hours=30)).isoformat(), "ubicacion": UBICACION,
            **extra}


def test_solo_donantes_verificados_publican(cliente, eventos):
    assert cliente.post("/api/donaciones", json=nueva(), headers=token(8, "DONANTE", "PENDIENTE")).status_code == 403
    assert cliente.post("/api/donaciones", json=nueva(), headers=RECEPTOR).status_code == 403
    assert cliente.post("/api/donaciones", json=nueva(cantidad=0), headers=DONANTE).status_code == 422
    vencida = nueva(fecha_vencimiento=(datetime.now(UTC) - timedelta(hours=1)).isoformat())
    assert cliente.post("/api/donaciones", json=vencida, headers=DONANTE).status_code == 409  # CHECK de la base
    r = cliente.post("/api/donaciones", json=nueva(), headers=DONANTE)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado_donacion"] == "DISPONIBLE" and d["ubicacion"]["lat"] == pytest.approx(4.57)
    assert eventos.tipos() == ["DONACION_CREADA"] and eventos.eventos[0].datos["id_donante"] == 2


def test_modificar_y_cancelar_solo_el_dueno(cliente, semilla, eventos):
    assert cliente.patch("/api/donaciones/1", json={"cantidad": 45}, headers=DONANTE).json()["cantidad"] == 45
    assert cliente.patch("/api/donaciones/1", json={"cantidad": 1}, headers=DONANTE_MED).status_code == 403
    assert cliente.patch("/api/donaciones/11", json={"cantidad": 1}, headers=DONANTE_MED).status_code == 409  # RESERVADA
    assert cliente.post("/api/donaciones/1/cancelar", headers=DONANTE).json()["estado_donacion"] == "CANCELADA"
    assert cliente.post("/api/donaciones/1/cancelar", headers=DONANTE).status_code == 409
    assert [d["id_donacion"] for d in cliente.get("/api/donaciones/mias", headers=DONANTE_MED).json()] == [14, 13, 12, 11]
    assert eventos.tipos() == ["DONACION_ACTUALIZADA", "DONACION_CANCELADA"]


def test_busqueda_con_distancia_y_puntaje(cliente, semilla):
    r = cliente.get("/api/donaciones/disponibles?id_necesidad=1", headers=RECEPTOR).json()
    puntajes = [x["prioridad"]["puntaje"] for x in r["resultados"]]
    assert puntajes == sorted(puntajes, reverse=True) and r["punto"]["lat"] == pytest.approx(4.556)
    assert all(x["estado_donacion"] == "DISPONIBLE" and x["ubicacion"]["ciudad"] == "Bogotá" for x in r["resultados"])
    por_distancia = cliente.get("/api/donaciones/disponibles?lat=4.556&lon=-74.142&orden=distancia",
                                headers=RECEPTOR).json()["resultados"]
    distancias = [x["distancia_m"] for x in por_distancia]
    assert distancias == sorted(distancias) and por_distancia[0]["distancia_km"] == pytest.approx(distancias[0] / 1000, abs=0.001)
    lacteos = cliente.get("/api/donaciones/disponibles?id_necesidad=2&id_categoria=2", headers=RECEPTOR).json()
    assert {x["categoria"] for x in lacteos["resultados"]} == {"Lácteos y huevos"}
    assert cliente.get("/api/donaciones/disponibles?id_necesidad=1", headers=RECEPTOR_MED).status_code == 400
    assert cliente.get("/api/donaciones/disponibles", headers=RECEPTOR).status_code == 400
    assert cliente.get("/api/donaciones/disponibles?lat=4.6&lon=-74.1", headers=DONANTE).status_code == 403


def test_necesidades_solo_las_propias(cliente, semilla, eventos):
    datos = {"descripcion": "Arroz para 40 almuerzos", "id_categoria": 4, "cantidad_requerida": 20,
             "unidad_medida": "kg", "nivel_urgencia": "ALTA", "ubicacion": UBICACION}
    assert cliente.post("/api/necesidades", json=datos, headers=token(3, "RECEPTOR", "PENDIENTE")).status_code == 403
    n = cliente.post("/api/necesidades", json=datos, headers=token(5, "RECEPTOR")).json()
    assert n["estado_necesidad"] == "ABIERTA"
    assert cliente.patch(f"/api/necesidades/{n['id_necesidad']}", json={"nivel_urgencia": "CRITICA"},
                         headers=RECEPTOR).status_code == 403
    assert cliente.patch(f"/api/necesidades/{n['id_necesidad']}", json={"nivel_urgencia": "CRITICA"},
                         headers=RECEPTOR_MED).json()["nivel_urgencia"] == "CRITICA"
    assert cliente.post(f"/api/necesidades/{n['id_necesidad']}/cerrar", headers=RECEPTOR_MED).json()[
        "estado_necesidad"] == "CERRADA"
    assert eventos.tipos() == ["NECESIDAD_CREADA", "NECESIDAD_AJUSTADA", "NECESIDAD_CERRADA"]


def test_transicion_interna_d01(cliente, semilla, eventos):
    cuerpo = {"estado": "RESERVADA", "id_actor": 3, "datos": {"id_receptor": 3, "id_reserva": 9}}
    assert cliente.post("/internal/donaciones/1/transiciones", json=cuerpo).status_code == 403  # sin token interno
    assert cliente.post("/internal/donaciones/1/transiciones", json=cuerpo,
                        headers={"X-Token-Interno": "falso"}).status_code == 403
    r = cliente.post("/internal/donaciones/1/transiciones", json=cuerpo, headers=INTERNO)
    assert r.status_code == 200 and r.json()["estado_anterior"] == "DISPONIBLE"
    evento = eventos.eventos[-1]
    assert evento.tipo == "DONACION_RESERVADA" and evento.datos["id_receptor"] == 3 and evento.id_actor == 3
    # ilegal: VENCIDA → DISPONIBLE (donación 18)
    ilegal = cliente.post("/internal/donaciones/18/transiciones", json={"estado": "DISPONIBLE"}, headers=INTERNO)
    assert ilegal.status_code == 409 and "VENCIDA → DISPONIBLE" in ilegal.json()["detail"]


def test_lecturas_y_tareas_internas(cliente, semilla, eventos):
    lista = cliente.get("/internal/donaciones?ids=11,15", headers=INTERNO).json()
    assert {d["id_donacion"]: d["id_donante"] for d in lista} == {11: 4, 15: 6}
    assert {d["id_donacion"] for d in cliente.get("/internal/donaciones?id_donante=6", headers=INTERNO).json()} == {
        15, 16, 17, 18}
    assert [d["id_donacion"] for d in cliente.get("/internal/donaciones-por-vencer?horas=24",
                                                   headers=INTERNO).json()] == [5, 11, 1]
    assert cliente.post("/internal/tareas/vencer", headers=INTERNO).json() == {"vencidas": []}


def test_categorias_las_mantiene_el_administrador(cliente):
    assert cliente.post("/api/admin/categorias", json={"nombre_categoria": "Bebés"}, headers=DONANTE).status_code == 403
    c = cliente.post("/api/admin/categorias", json={"nombre_categoria": "Alimentos para bebés",
                                                    "descripcion": "Fórmulas y compotas"}, headers=ADMIN).json()
    assert c["id_categoria"] == 8
    assert cliente.patch("/api/admin/categorias/8", json={"nombre_categoria": "Bebés y lactantes"},
                         headers=ADMIN).json()["nombre_categoria"] == "Bebés y lactantes"
    assert "Bebés y lactantes" in [x["nombre_categoria"] for x in cliente.get("/api/categorias", headers=DONANTE).json()]
    assert cliente.post("/api/admin/categorias", json={"nombre_categoria": "Panadería"}, headers=ADMIN).status_code == 409
