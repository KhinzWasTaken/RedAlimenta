"""S4-10: CRUD de donaciones y necesidades, búsqueda por distancia con filtros y puntaje D-08."""
from datetime import timedelta

import pytest
from sqlalchemy import func, text

from catalogo import repositorio as repo
from catalogo.errores import ErrorDominio, NoEncontrado, TransicionInvalida
from catalogo.semilla import sembrar

PLAZA_BOLIVAR = (4.5981, -74.0760)
PARQUE_93 = (4.6767, -74.0483)


def ahora(db):
    return db.scalar(func.now())


def donar(db, lat, lon, horas=48, **extra):
    datos = dict(nombre_alimento="Arroz", id_categoria=4, cantidad=10, unidad_medida="kg",
                 ciudad="Bogotá", departamento="Cundinamarca",
                 fecha_vencimiento=None if horas is None else ahora(db) + timedelta(hours=horas))
    datos.update(extra)
    return repo.crear_donacion(db, 2, lat=lat, lon=lon, **datos)


def test_crud_de_donacion(db):
    d = donar(db, *PLAZA_BOLIVAR, descripcion="Bolsas de 1 kg", direccion="Cra 7 # 11-10")
    db.commit()
    assert d.estado_donacion == "DISPONIBLE" and d.fecha_publicacion is not None
    assert repo.obtener_donacion(db, d.id_donacion).nombre_alimento == "Arroz"
    assert repo.coordenadas(db, d.id_ubicacion) == pytest.approx(PLAZA_BOLIVAR)
    repo.actualizar_donacion(db, d.id_donacion, 2, cantidad=25, condiciones_recogida="Mañanas")
    db.commit()
    assert repo.obtener_donacion(db, d.id_donacion).cantidad == 25
    with pytest.raises(ErrorDominio, match="dueño"):
        repo.actualizar_donacion(db, d.id_donacion, 4, cantidad=1)
    with pytest.raises(ErrorDominio, match="no editables"):
        repo.actualizar_donacion(db, d.id_donacion, 2, estado_donacion="ENTREGADA")
    assert [x.id_donacion for x in repo.listar_donaciones(db, id_donante=2)] == [d.id_donacion]
    repo.cancelar_donacion(db, d.id_donacion, 2)
    db.commit()
    assert repo.obtener_donacion(db, d.id_donacion).estado_donacion == "CANCELADA"  # no se borra
    with pytest.raises(TransicionInvalida):
        repo.actualizar_donacion(db, d.id_donacion, 2, cantidad=3)
    with pytest.raises(NoEncontrado):
        repo.obtener_donacion(db, 999)
    with pytest.raises(ErrorDominio):
        donar(db, *PLAZA_BOLIVAR, cantidad=0)


def test_transiciones_de_donacion(db):
    d = donar(db, *PLAZA_BOLIVAR)
    assert repo.transicionar_donacion(db, d.id_donacion, "RESERVADA")[0] == "DISPONIBLE"
    assert repo.transicionar_donacion(db, d.id_donacion, "DISPONIBLE")[0] == "RESERVADA"
    repo.transicionar_donacion(db, d.id_donacion, "RESERVADA")
    repo.transicionar_donacion(db, d.id_donacion, "ENTREGADA")
    for estado in ("DISPONIBLE", "CANCELADA", "RESERVADA"):
        with pytest.raises(TransicionInvalida):
            repo.transicionar_donacion(db, d.id_donacion, estado)


def test_no_se_reserva_una_donacion_vencida(db):
    d = donar(db, *PLAZA_BOLIVAR, horas=1)
    # La donación se publicó hace 3 horas y venció hace 1 (aún no la ha marcado la tarea automática)
    db.execute(text("UPDATE donacion SET fecha_publicacion = now() - interval '3 hours', "
                    "fecha_vencimiento = now() - interval '1 hour' WHERE id_donacion = :i"), {"i": d.id_donacion})
    db.commit()
    db.expire_all()
    with pytest.raises(TransicionInvalida, match="venció"):
        repo.transicionar_donacion(db, d.id_donacion, "RESERVADA")
    assert repo.vencer_donaciones(db) == [d.id_donacion]
    assert repo.vencer_donaciones(db) == []


def test_vencer_donaciones_es_idempotente(db):
    sembrar(db)
    momento = ahora(db) + timedelta(hours=12)  # vencen los almuerzos (8 h) y nada más
    assert repo.vencer_donaciones(db, momento) == [5]
    assert repo.vencer_donaciones(db, momento) == []


def test_crud_de_necesidades_solo_las_propias(db):
    n = repo.crear_necesidad(db, 3, descripcion="Arroz para 50 almuerzos", id_categoria=4, cantidad_requerida=30,
                             unidad_medida="kg", nivel_urgencia="ALTA", lat=4.556, lon=-74.142,
                             ciudad="Bogotá", departamento="Cundinamarca")
    db.commit()
    repo.ajustar_necesidad(db, n.id_necesidad, 3, cantidad_requerida=45, nivel_urgencia="CRITICA")
    assert [x.id_necesidad for x in repo.listar_necesidades(db, id_receptor=3, estado="ABIERTA")] == [n.id_necesidad]
    with pytest.raises(ErrorDominio, match="propias"):
        repo.ajustar_necesidad(db, n.id_necesidad, 5, cantidad_requerida=1)
    with pytest.raises(ErrorDominio, match="urgencia"):
        repo.ajustar_necesidad(db, n.id_necesidad, 3, nivel_urgencia="EXTREMA")
    repo.cerrar_necesidad(db, n.id_necesidad, 3)
    db.commit()
    with pytest.raises(TransicionInvalida):
        repo.ajustar_necesidad(db, n.id_necesidad, 3, cantidad_requerida=1)


def test_busqueda_ordenada_por_distancia_en_metros(db):
    cerca = donar(db, 4.6000, -74.0760)       # ~210 m al norte de la Plaza de Bolívar
    lejos = donar(db, *PARQUE_93)              # ~9,3 km
    fuera = donar(db, 6.2447, -75.5916)        # Medellín, fuera del radio
    reservada = donar(db, 4.5990, -74.0760)
    repo.transicionar_donacion(db, reservada.id_donacion, "RESERVADA")
    db.commit()
    r = repo.buscar_donaciones(db, id_receptor=3, lat=PLAZA_BOLIVAR[0], lon=PLAZA_BOLIVAR[1])
    assert [x["id_donacion"] for x in r] == [cerca.id_donacion, lejos.id_donacion]
    assert r[0]["distancia_m"] == pytest.approx(210, abs=5)
    assert r[1]["distancia_m"] == pytest.approx(9_300, rel=0.01)
    assert fuera.id_donacion not in [x["id_donacion"] for x in r]
    assert r[0]["lat"] == pytest.approx(4.6) and r[0]["ciudad"] == "Bogotá"  # listo para el mapa


def test_busqueda_excluye_vencidas_y_aplica_filtros(db):
    vigente = donar(db, *PLAZA_BOLIVAR, horas=48, cantidad=50)
    por_vencer = donar(db, *PLAZA_BOLIVAR, horas=1, cantidad=5)
    leche = donar(db, *PLAZA_BOLIVAR, id_categoria=2, nombre_alimento="Leche")
    sin_fecha = donar(db, *PLAZA_BOLIVAR, horas=None, id_categoria=7, nombre_alimento="Agua")
    db.commit()
    base = dict(id_receptor=3, lat=PLAZA_BOLIVAR[0], lon=PLAZA_BOLIVAR[1])
    ids = lambda **f: {x["id_donacion"] for x in repo.buscar_donaciones(db, **base, **f)}  # noqa: E731
    assert ids() == {vigente.id_donacion, por_vencer.id_donacion, leche.id_donacion, sin_fecha.id_donacion}
    assert ids(ahora=ahora(db) + timedelta(hours=2)) == {vigente.id_donacion, leche.id_donacion,
                                                          sin_fecha.id_donacion}
    assert ids(id_categoria=2) == {leche.id_donacion}
    assert ids(cantidad_minima=20) == {vigente.id_donacion}
    assert ids(vence_antes=ahora(db) + timedelta(hours=3)) == {por_vencer.id_donacion}


def test_puntaje_d08_verificado_a_mano(db):
    # Receptor 3 con necesidad ALTA de lácteos; donación de leche a 0 m que vence en 84 h.
    # 0,40·0,75 (ALTA) + 0,35·1 (0 m) + 0,25·(1 − 84/168) = 0,30 + 0,35 + 0,125 = 0,775
    momento = ahora(db)
    repo.crear_necesidad(db, 3, descripcion="Leche", id_categoria=2, cantidad_requerida=10, unidad_medida="litros",
                         nivel_urgencia="ALTA", lat=PLAZA_BOLIVAR[0], lon=PLAZA_BOLIVAR[1],
                         ciudad="Bogotá", departamento="Cundinamarca")
    leche = donar(db, *PLAZA_BOLIVAR, horas=84, id_categoria=2)
    # Arroz a 10 km (radio 20 km → cercanía 0,5), sin necesidad, vence en 168 h:
    # 0 + 0,35·0,5 + 0 = 0,175 (con la distancia real calculada por PostGIS)
    arroz = donar(db, PLAZA_BOLIVAR[0] + 0.0899, PLAZA_BOLIVAR[1], horas=168)
    db.commit()
    r = {x["id_donacion"]: x for x in repo.buscar_donaciones(db, id_receptor=3, lat=PLAZA_BOLIVAR[0],
                                                              lon=PLAZA_BOLIVAR[1], ahora=momento,
                                                              orden="prioridad")}
    assert float(r[leche.id_donacion]["puntaje"]) == pytest.approx(0.775, abs=1e-4)
    assert r[leche.id_donacion]["nivel_urgencia"] == "ALTA"
    esperado = 0.35 * (1 - r[arroz.id_donacion]["distancia_m"] / 20_000)
    assert float(r[arroz.id_donacion]["puntaje"]) == pytest.approx(esperado, abs=1e-4)
    assert float(r[arroz.id_donacion]["puntaje"]) == pytest.approx(0.175, abs=0.005)


def test_referencia_por_necesidad_d07(db):
    sembrar(db)
    db.commit()
    # Necesidad 1: arroz CRÍTICO en Ciudad Bolívar → el arroz de Kennedy queda primero por prioridad
    r = repo.buscar_donaciones(db, id_receptor=3, id_necesidad=1, orden="prioridad")
    assert r[0]["nombre_alimento"] in ("Arroz blanco", "Pechuga de pollo", "Yogur natural")
    assert all(x["ciudad"] == "Bogotá" for x in r)
    assert [x["puntaje"] for x in r] == sorted((x["puntaje"] for x in r), reverse=True)
    assert {x["id_donacion"] for x in r}.isdisjoint({11, 12, 14, 15, 18})  # no disponibles u otras ciudades
    with pytest.raises(ErrorDominio):
        repo.buscar_donaciones(db, id_receptor=5, id_necesidad=1)  # la necesidad no es suya
