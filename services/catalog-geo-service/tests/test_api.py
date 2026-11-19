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


def test_identificador_de_correlacion_viaja_hasta_el_evento(cliente, eventos):
    """S6-09: el id que pone el gateway vuelve en la respuesta y queda en el evento publicado."""
    r = cliente.post("/api/donaciones", json=nueva(), headers={**DONANTE, "X-Correlation-Id": "demo-123"})
    assert r.headers["X-Correlation-Id"] == "demo-123"
    assert eventos.eventos[-1].id_correlacion == "demo-123"
    sin = cliente.get("/api/categorias", headers=DONANTE)
    assert len(sin.headers["X-Correlation-Id"]) == 32  # si no llega, el servicio genera uno


def test_vivo_no_depende_de_la_base(cliente):
    assert cliente.get("/vivo").json()["estado"] == "vivo"


def test_solicitudes_d11_donante_ofrece_y_solo_el_receptor_reserva(cliente, semilla, eventos):
    """D-11: los donantes ven las necesidades abiertas, ofrecen una donación y queda apartada para ese receptor."""
    # Los donantes ven las solicitudes abiertas cerca de un punto, la más urgente primero y sin datos del receptor
    cerca = cliente.get("/api/necesidades/abiertas?lat=4.6&lon=-74.12&radio_km=20", headers=DONANTE).json()
    assert [n["id_necesidad"] for n in cerca] == [1, 2, 3, 4]
    assert cerca[0]["nivel_urgencia"] == "CRITICA" and cerca[0]["distancia_km"] > 0
    assert "id_receptor" not in cerca[0] and "direccion_referencia" not in cerca[0]["ubicacion"]
    todas = cliente.get("/api/necesidades/abiertas?id_categoria=4", headers=DONANTE).json()
    assert {n["id_necesidad"] for n in todas} == {1, 6} and todas[0]["distancia_km"] is None
    assert cliente.get("/api/necesidades/abiertas", headers=RECEPTOR).status_code == 403
    assert cliente.get("/api/necesidades/abiertas?lat=4.6", headers=DONANTE).status_code == 400

    # El donante ofrece una donación para la necesidad 1 (receptor 3)
    r = cliente.post("/api/donaciones", json=nueva(nombre_alimento="Arroz", id_necesidad=1), headers=DONANTE)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["id_necesidad"] == 1 and d["id_receptor_exclusivo"] == 3
    evento = eventos.eventos[-1]
    assert evento.tipo == "DONACION_CREADA" and evento.datos["id_receptor"] == 3 and evento.datos["id_necesidad"] == 1
    assert cliente.get("/api/necesidades/mias", headers=RECEPTOR).json()[-1]["ofertas"] == 1  # necesidad 1

    # Solo la ve el receptor que la pidió, y primero que las demás
    propia = cliente.get("/api/donaciones/disponibles?id_necesidad=1", headers=RECEPTOR).json()["resultados"]
    assert propia[0]["id_donacion"] == d["id_donacion"] and propia[0]["para_mi"] is True
    otro = token(9, "RECEPTOR")
    ajenas = cliente.get("/api/donaciones/disponibles?lat=4.57&lon=-74.13", headers=otro).json()["resultados"]
    assert d["id_donacion"] not in [x["id_donacion"] for x in ajenas]

    # catalog rechaza que otro receptor la reserve (D-01 + D-11)
    ruta = f"/internal/donaciones/{d['id_donacion']}/transiciones"
    ajena = cliente.post(ruta, json={"estado": "RESERVADA", "datos": {"id_receptor": 9}}, headers=INTERNO)
    assert ajena.status_code == 409 and "otro receptor" in ajena.json()["detail"]

    # Si el receptor cierra su necesidad, la donación queda abierta a todos
    cliente.post("/api/necesidades/1/cerrar", headers=RECEPTOR)
    ajenas = cliente.get("/api/donaciones/disponibles?lat=4.57&lon=-74.13", headers=otro).json()["resultados"]
    assert d["id_donacion"] in [x["id_donacion"] for x in ajenas]
    assert cliente.post(ruta, json={"estado": "RESERVADA", "datos": {"id_receptor": 9}},
                        headers=INTERNO).status_code == 200
    # Y ya no recibe ofertas
    assert cliente.post("/api/donaciones", json=nueva(id_necesidad=1), headers=DONANTE).status_code == 409
    assert cliente.post("/api/donaciones", json=nueva(id_necesidad=999), headers=DONANTE).status_code == 404
