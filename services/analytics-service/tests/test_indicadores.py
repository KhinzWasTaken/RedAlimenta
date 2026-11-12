"""S8-01 a S8-03: API de indicadores igual a la consulta manual, CSV con los mismos totales y cobertura."""
import csv
import io

import pytest
from sqlalchemy import text

from .conftest import token

ADMIN = token(1, "ADMINISTRADOR")


def manual(motor, sql):
    with motor.connect() as c:
        return c.execute(text(sql)).scalar()


def test_resumen_igual_a_consulta_manual(cliente, almacen):
    r = cliente.get("/api/indicadores/resumen", headers=ADMIN).json()
    assert r["donaciones_registradas"] == manual(almacen, "SELECT count(*) FROM dw.fact_donacion") == 1500
    assert r["reservas_gestionadas"] == manual(almacen, "SELECT count(*) FROM dw.fact_reserva")
    assert r["entregas_finalizadas"] == manual(
        almacen, "SELECT count(*) FROM dw.fact_entrega f JOIN dw.dim_estado e USING (sk_estado) "
                 "WHERE e.estado = 'COMPLETADA'")
    perdidas = manual(almacen, "SELECT round(count(*) FILTER (WHERE e.estado IN ('CANCELADA','VENCIDA'))::numeric "
                               "/ count(*), 4) FROM dw.fact_donacion f JOIN dw.dim_estado e USING (sk_estado)")
    assert r["proporcion_canceladas_vencidas"] == pytest.approx(float(perdidas))
    kg = manual(almacen, "SELECT sum(f.cantidad) FROM dw.fact_entrega f JOIN dw.dim_estado e USING (sk_estado) "
                         "WHERE e.estado = 'COMPLETADA' AND f.unidad_medida = 'kg'")
    assert {v["unidad_medida"]: v["cantidad"] for v in r["volumen_distribuido"]}["kg"] == pytest.approx(float(kg))
    assert r["ultima_carga"]["tipo"] == "sintetica" and r["ultima_carga"]["reglas_fallidas"] == 0


def test_series_filtros_y_granularidad(cliente, almacen):
    total = cliente.get("/api/indicadores/resumen", headers=ADMIN).json()["donaciones_registradas"]
    for granularidad in ("dia", "mes", "anio"):
        puntos = cliente.get(f"/api/indicadores/serie?granularidad={granularidad}", headers=ADMIN).json()["puntos"]
        assert sum(p["valor"] for p in puntos) == total
    bogota = cliente.get("/api/indicadores/resumen?ciudad=Bogotá", headers=ADMIN).json()["donaciones_registradas"]
    assert bogota == manual(almacen, "SELECT count(*) FROM dw.fact_donacion f JOIN dw.dim_ubicacion u "
                                     "USING (sk_ubicacion) WHERE u.ciudad = 'Bogotá'") and 0 < bogota < total
    granos = cliente.get("/api/indicadores/resumen?id_categoria=4&desde=2026-01-01&hasta=2026-06-30",
                         headers=ADMIN).json()["donaciones_registradas"]
    assert granos == manual(almacen, """SELECT count(*) FROM dw.fact_donacion f JOIN dw.dim_categoria c
        USING (sk_categoria) JOIN dw.dim_tiempo t ON t.sk_tiempo = f.sk_tiempo_publicacion
        WHERE c.id_categoria = 4 AND t.fecha BETWEEN '2026-01-01' AND '2026-06-30'""")
    solo_reales = cliente.get("/api/indicadores/resumen?incluir_sinteticos=false", headers=ADMIN).json()
    assert solo_reales["donaciones_registradas"] == 0
    assert cliente.get("/api/indicadores/serie?indicador=inventado", headers=ADMIN).status_code == 400
    assert cliente.get("/api/indicadores/resumen?desde=2026-02-01&hasta=2026-01-01", headers=ADMIN).status_code == 400


def test_cobertura_por_region_lista_para_el_mapa(cliente, almacen):
    regiones = cliente.get("/api/indicadores/cobertura", headers=ADMIN).json()
    assert regiones[0]["ciudad"] == "Bogotá" and regiones[0]["latitud"] is not None
    assert sum(r["donaciones"] for r in regiones) == 1500
    assert all(0 <= r["tasa_entrega"] <= 1 for r in regiones)
    opciones = cliente.get("/api/indicadores/filtros", headers=ADMIN).json()
    assert "Antioquia" in opciones["departamentos"] and len(opciones["categorias"]) == 7


def test_csv_con_los_mismos_totales_que_la_pantalla(cliente, almacen):
    def leer(ruta):
        r = cliente.get(ruta, headers=ADMIN)
        assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
        return list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))

    pantalla = cliente.get("/api/indicadores/serie?indicador=entregas_finalizadas&granularidad=mes",
                           headers=ADMIN).json()["puntos"]
    archivo = leer("/api/reportes/serie.csv?indicador=entregas_finalizadas&granularidad=mes")
    assert [float(f["valor"]) for f in archivo] == [p["valor"] for p in pantalla]
    cobertura = cliente.get("/api/indicadores/cobertura?departamento=Antioquia", headers=ADMIN).json()
    assert sum(int(f["donaciones"]) for f in leer("/api/reportes/cobertura.csv?departamento=Antioquia")) == sum(
        r["donaciones"] for r in cobertura)
    resumen = {f["indicador"]: float(f["valor"]) for f in leer("/api/reportes/resumen.csv")}
    assert resumen["donaciones_registradas"] == 1500
    assert cliente.get("/api/reportes/otro.csv", headers=ADMIN).status_code == 400


def test_solo_el_administrador_y_almacen_configurado(cliente, almacen):
    assert cliente.get("/api/indicadores/resumen", headers=token(2, "DONANTE")).status_code == 403
    assert cliente.get("/api/reportes/resumen.csv").status_code == 401
    from analitica.almacen import usar_motor
    usar_motor(None)
    try:
        r = cliente.get("/api/indicadores/resumen", headers=ADMIN)
        assert r.status_code == 503 and "almacén" in r.json()["detail"]
    finally:
        usar_motor(almacen)
