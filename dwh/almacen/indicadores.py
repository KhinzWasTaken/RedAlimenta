"""Indicadores del RF9 calculados sobre el modelo en estrella (S7-01; los usa la API del Sprint 8).

Cada indicador es una sola consulta con los mismos filtros: periodo (desde, hasta), granularidad
(dia, mes, anio), departamento, ciudad, categoría y si se incluyen los datos sintéticos.
"""
from datetime import date

from sqlalchemy import Connection, text

GRANULARIDAD = {"dia": "t.fecha", "mes": "date_trunc('month', t.fecha)::date", "anio": "date_trunc('year', t.fecha)::date"}

# indicador → (hecho, columna de tiempo, expresión de la medida)
INDICADORES = {
    "donaciones_registradas": ("dw.fact_donacion", "sk_tiempo_publicacion", "count(*)"),
    "reservas_gestionadas": ("dw.fact_reserva", "sk_tiempo_reserva", "count(*)"),
    "entregas_finalizadas": ("dw.fact_entrega", "sk_tiempo_entrega", "count(*) FILTER (WHERE e.estado = 'COMPLETADA')"),
    "proporcion_canceladas_vencidas": (
        "dw.fact_donacion", "sk_tiempo_publicacion",
        "round(count(*) FILTER (WHERE e.estado IN ('CANCELADA', 'VENCIDA'))::numeric / nullif(count(*), 0), 4)"),
}


def _filtros(departamento, ciudad, id_categoria, incluir_sinteticos) -> tuple[str, dict]:
    condiciones, params = ["t.fecha BETWEEN :desde AND :hasta"], {}
    if not incluir_sinteticos:
        condiciones.append("f.origen_dato = 'REAL'")
    if departamento:
        condiciones.append("u.departamento = :departamento")
        params["departamento"] = departamento
    if ciudad:
        condiciones.append("u.ciudad = :ciudad")
        params["ciudad"] = ciudad
    if id_categoria:
        condiciones.append("c.id_categoria = :id_categoria")
        params["id_categoria"] = id_categoria
    return " AND ".join(condiciones), params


def serie(dwh: Connection, indicador: str, desde: date, hasta: date, granularidad: str = "mes",
          departamento: str | None = None, ciudad: str | None = None, id_categoria: int | None = None,
          incluir_sinteticos: bool = True) -> list[dict]:
    """Valor del indicador por periodo."""
    hecho, col_tiempo, medida = INDICADORES[indicador]
    where, params = _filtros(departamento, ciudad, id_categoria, incluir_sinteticos)
    sql = f"""
        SELECT {GRANULARIDAD[granularidad]} AS periodo, {medida} AS valor
        FROM {hecho} f
        JOIN dw.dim_tiempo t ON t.sk_tiempo = f.{col_tiempo}
        JOIN dw.dim_ubicacion u ON u.sk_ubicacion = f.sk_ubicacion
        JOIN dw.dim_categoria c ON c.sk_categoria = f.sk_categoria
        JOIN dw.dim_estado e ON e.sk_estado = f.sk_estado
        WHERE {where}
        GROUP BY 1 ORDER BY 1"""
    return [dict(f) for f in dwh.execute(text(sql), {"desde": desde, "hasta": hasta, **params}).mappings()]


def volumen_distribuido(dwh: Connection, desde: date, hasta: date, **filtros) -> list[dict]:
    """Cantidad entregada por unidad de medida (no se suman kg con litros)."""
    where, params = _filtros(filtros.get("departamento"), filtros.get("ciudad"), filtros.get("id_categoria"),
                             filtros.get("incluir_sinteticos", True))
    sql = f"""
        SELECT f.unidad_medida, sum(f.cantidad) AS cantidad, count(*) AS entregas
        FROM dw.fact_entrega f
        JOIN dw.dim_tiempo t ON t.sk_tiempo = f.sk_tiempo_entrega
        JOIN dw.dim_ubicacion u ON u.sk_ubicacion = f.sk_ubicacion
        JOIN dw.dim_categoria c ON c.sk_categoria = f.sk_categoria
        JOIN dw.dim_estado e ON e.sk_estado = f.sk_estado
        WHERE {where} AND e.estado = 'COMPLETADA'
        GROUP BY 1 ORDER BY 2 DESC"""
    return [dict(f) for f in dwh.execute(text(sql), {"desde": desde, "hasta": hasta, **params}).mappings()]


def cobertura(dwh: Connection, desde: date, hasta: date, incluir_sinteticos: bool = True) -> list[dict]:
    """Indicadores por departamento y ciudad, con coordenadas para el mapa (S8-03)."""
    origen = "" if incluir_sinteticos else "AND f.origen_dato = 'REAL'"
    sql = f"""
        SELECT u.departamento, u.ciudad, u.latitud, u.longitud,
               count(*) AS donaciones,
               count(*) FILTER (WHERE e.estado = 'ENTREGADA') AS entregadas,
               count(*) FILTER (WHERE e.estado IN ('CANCELADA', 'VENCIDA')) AS perdidas,
               round(count(*) FILTER (WHERE e.estado = 'ENTREGADA')::numeric / nullif(count(*), 0), 4) AS tasa_entrega
        FROM dw.fact_donacion f
        JOIN dw.dim_tiempo t ON t.sk_tiempo = f.sk_tiempo_publicacion
        JOIN dw.dim_ubicacion u ON u.sk_ubicacion = f.sk_ubicacion
        JOIN dw.dim_estado e ON e.sk_estado = f.sk_estado
        WHERE t.fecha BETWEEN :desde AND :hasta {origen} AND u.sk_ubicacion <> -1
        GROUP BY 1, 2, 3, 4 ORDER BY donaciones DESC"""
    return [dict(f) for f in dwh.execute(text(sql), {"desde": desde, "hasta": hasta}).mappings()]
