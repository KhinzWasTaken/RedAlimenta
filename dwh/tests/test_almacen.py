"""S7-01 a S7-07: modelo, carga histórica, carga continua, datos sintéticos, calidad, indicadores y reintentos."""
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from almacen import sintetico
from analitica import indicadores
from almacen.cargar import cargar
from almacen.extraer import motor_lectura
from redalimenta_comun.eventos import Evento

from .conftest import valor


def aprobadas(resultado) -> dict:
    return {r["regla"]: r["aprobada"] for r in resultado["calidad"]}


def test_dimensiones_precargadas(motor_dwh):
    assert valor(motor_dwh, "SELECT count(*) FROM dw.dim_tiempo WHERE sk_tiempo > 0") == 4018  # 2020–2030
    assert valor(motor_dwh, "SELECT nombre_dia FROM dw.dim_tiempo WHERE fecha = '2026-08-10'") == "lunes"
    assert valor(motor_dwh, "SELECT count(*) FROM dw.dim_estado WHERE entidad = 'donacion'") == 5


def test_carga_historica_repetible_y_con_conteos_iguales(motor_dwh, fuentes):
    primera = cargar(motor_dwh, "historica", fuentes, reintentos=1)
    assert all(aprobadas(primera).values()), aprobadas(primera)
    origen = create_engine(fuentes["catalog"])
    with origen.connect() as c:
        donaciones = c.execute(text("SELECT count(*) FROM donacion")).scalar()
    origen.dispose()
    assert valor(motor_dwh, "SELECT count(*) FROM dw.fact_donacion") == donaciones == 18
    assert valor(motor_dwh, "SELECT count(*) FROM dw.fact_reserva") == 5
    assert valor(motor_dwh, "SELECT count(*) FROM dw.fact_entrega") == 2
    segunda = cargar(motor_dwh, "historica", fuentes, reintentos=1)
    assert segunda["filas"]["dw.fact_donacion"] == 18  # repetir la carga no duplica
    assert valor(motor_dwh, "SELECT count(DISTINCT sk_ubicacion) FROM dw.fact_donacion") == 3  # Bogotá, Medellín, Cali
    # sin datos personales en el almacén
    columnas = valor(motor_dwh, "SELECT string_agg(column_name, ',') FROM information_schema.columns "
                                "WHERE table_schema IN ('dw', 'stg')")
    assert not {"nombre", "correo_electronico", "telefono"} & set(columnas.split(","))


def test_carga_continua_desde_eventos(motor_dwh, fuentes):
    cargar(motor_dwh, "historica", fuentes, reintentos=1)
    from analitica.repositorio import guardar_evento
    ahora = datetime.now(UTC)

    def evento(tipo, entidad, id_entidad, anterior, nuevo, minutos, **datos):
        return Evento(tipo=tipo, entidad=entidad, id_entidad=id_entidad, estado_anterior=anterior,
                      estado_nuevo=nuevo, id_actor=datos.get("id_receptor", 4), datos=datos, origen="prueba",
                      fecha=(ahora + timedelta(minutes=minutos)).isoformat())

    eventos = [
        evento("DONACION_CREADA", "donacion", 500, None, "DISPONIBLE", 1, id_donante=4, id_categoria=4,
               ciudad="Medellín", departamento="Antioquia", cantidad=30, unidad_medida="kg"),
        evento("RESERVA_CREADA", "reserva", 600, None, "PENDIENTE", 2, id_reserva=600, id_donacion=500,
               id_donante=4, id_receptor=5),
        evento("DONACION_RESERVADA", "donacion", 500, "DISPONIBLE", "RESERVADA", 2, id_donante=4),
        evento("RESERVA_CONFIRMADA", "reserva", 600, "PENDIENTE", "CONFIRMADA", 3, id_donacion=500, id_receptor=5),
        evento("RESERVA_EXPIRADA", "reserva", 1, "PENDIENTE", "EXPIRADA", 4, id_donacion=11, id_receptor=5),
        evento("DONACION_LIBERADA", "donacion", 11, "RESERVADA", "DISPONIBLE", 4, id_donante=4),
    ]
    analytics = create_engine(fuentes["analytics"])
    with Session(analytics) as db:
        for e in eventos:
            guardar_evento(db, e)
        db.commit()
    resultado = cargar(motor_dwh, "eventos", fuentes, reintentos=1)
    assert resultado["filas"]["stg.evento (nuevos)"] == 6
    estado = lambda tabla, col, i: valor(motor_dwh, f"SELECT e.estado FROM dw.{tabla} f JOIN dw.dim_estado e "  # noqa: E731
                                                     f"USING (sk_estado) WHERE origen_dato = 'REAL' AND {col} = :i", i=i)
    assert estado("fact_donacion", "id_donacion", 500) == "RESERVADA"  # nueva donación llegada por eventos
    assert estado("fact_reserva", "id_reserva", 600) == "CONFIRMADA"
    assert estado("fact_reserva", "id_reserva", 1) == "EXPIRADA"  # semilla actualizada por un evento
    assert estado("fact_donacion", "id_donacion", 11) == "DISPONIBLE"
    assert valor(motor_dwh, "SELECT count(*) FROM dw.fact_cambio_estado") == 6
    # El mismo evento entregado de nuevo no se duplica ni vuelve a mover estados
    with Session(analytics) as db:
        guardar_evento(db, eventos[0])
        db.commit()
    again = cargar(motor_dwh, "eventos", fuentes, reintentos=1)
    assert again["filas"]["dw.fact_cambio_estado"] == 6 and all(aprobadas(again).values())
    analytics.dispose()


def test_sinteticos_coherentes_y_deterministas(motor_dwh):
    a, b = sintetico.generar(3000, semilla=7), sintetico.generar(3000, semilla=7)
    assert a.donaciones[:50] == b.donaciones[:50] and len(a.reservas) == len(b.reservas)
    assert len({d[9] for d in a.donaciones}) >= 15  # distribuidas en el territorio
    resultado = cargar(motor_dwh, "sintetica", n_sinteticas=3000, reintentos=1)
    assert all(aprobadas(resultado).values()), aprobadas(resultado)
    assert valor(motor_dwh, "SELECT count(*) FROM dw.fact_donacion WHERE origen_dato = 'SINTETICO'") == 3000
    meses = valor(motor_dwh, "SELECT count(DISTINCT date_trunc('month', fecha_publicacion)) FROM dw.fact_donacion")
    assert meses >= 18  # distribuidas en el tiempo
    pico = valor(motor_dwh, """SELECT round(avg(n) FILTER (WHERE dia BETWEEN '2026-08-10' AND '2026-08-31')
                                      / avg(n) FILTER (WHERE dia BETWEEN '2026-06-01' AND '2026-07-31'), 1)
                               FROM (SELECT fecha_publicacion::date dia, count(*) n FROM dw.fact_donacion GROUP BY 1) x""")
    assert pico > 2  # más donaciones tras el terremoto


def test_calidad_detecta_problemas(motor_dwh):
    cargar(motor_dwh, "sintetica", n_sinteticas=500, reintentos=1)
    with motor_dwh.begin() as c:  # se corrompe a propósito una reserva
        c.execute(text("UPDATE dw.fact_reserva SET fecha_reserva = fecha_reserva - interval '400 days' "
                       "WHERE sk_reserva = (SELECT min(sk_reserva) FROM dw.fact_reserva)"))
    from almacen import calidad
    with motor_dwh.begin() as c:
        id_e = c.execute(text("INSERT INTO etl.ejecucion (tipo) VALUES ('prueba') RETURNING id_ejecucion")).scalar()
        resultados = {r["regla"]: r for r in calidad.evaluar(c, id_e)}
    assert resultados["fechas_en_orden"]["filas_con_problema"] == 1 and not resultados["fechas_en_orden"]["aprobada"]
    assert valor(motor_dwh, "SELECT count(*) FROM etl.resultado_calidad WHERE id_ejecucion = :e", e=id_e) == len(resultados)


def test_indicadores_iguales_a_consulta_manual(motor_dwh):
    cargar(motor_dwh, "sintetica", n_sinteticas=2000, reintentos=1)
    f = indicadores.Filtros(date(2025, 1, 1), date.today())
    with motor_dwh.connect() as c:
        donaciones = sum(p["valor"] for p in indicadores.serie(c, "donaciones_registradas", f, "anio"))
        entregas = sum(p["valor"] for p in indicadores.serie(c, "entregas_finalizadas", f, "mes"))
        volumen = {v["unidad_medida"]: v["cantidad"] for v in indicadores.volumen_distribuido(c, f)}
        bogota = indicadores.total(c, "donaciones_registradas", indicadores.Filtros(f.desde, f.hasta, ciudad="Bogotá"))
        cobertura = indicadores.cobertura(c, f)
        manual = c.execute(text("""
            SELECT count(*), (SELECT count(*) FROM stg.entrega WHERE estado_entrega = 'COMPLETADA'),
                   count(*) FILTER (WHERE ciudad = 'Bogotá')
            FROM stg.donacion""")).one()
        volumen_manual = dict(c.execute(text("""
            SELECT d.unidad_medida, sum(d.cantidad)::float FROM stg.entrega e
            JOIN stg.reserva r USING (origen_dato, id_reserva) JOIN stg.donacion d USING (origen_dato, id_donacion)
            WHERE e.estado_entrega = 'COMPLETADA' GROUP BY 1""")).all())
        proporcion = indicadores.serie(c, "proporcion_canceladas_vencidas", f, "anio")
    assert donaciones == manual[0] and entregas == manual[1] and bogota == manual[2]
    assert volumen == pytest.approx(volumen_manual)
    assert cobertura[0]["ciudad"] == "Bogotá" and cobertura[0]["latitud"] is not None
    assert all(0 < p["valor"] < 1 for p in proporcion)


def test_carga_fallida_se_registra_se_reintenta_y_no_deja_nada_a_medias(motor_dwh, fuentes):
    malas = {**fuentes, "catalog": fuentes["catalog"].replace("prueba_", "no_existe_")}
    with pytest.raises(Exception):
        cargar(motor_dwh, "historica", malas, reintentos=2, espera=0)
    with motor_dwh.connect() as c:
        estados = [f[0] for f in c.execute(text("SELECT estado FROM etl.ejecucion ORDER BY id_ejecucion"))]
    assert estados == ["FALLIDA", "FALLIDA"]
    assert valor(motor_dwh, "SELECT count(*) FROM stg.usuario") == 0  # la transacción se revirtió completa
    assert cargar(motor_dwh, "historica", fuentes, reintentos=1)["intento"] == 1


def test_las_fuentes_se_leen_en_solo_lectura(fuentes):
    motor = motor_lectura(fuentes["catalog"])
    with motor.connect() as c, pytest.raises(DBAPIError, match="read-only"):
        c.execute(text("UPDATE donacion SET cantidad = 1"))
    motor.dispose()
