"""Indicadores del RF9 calculados sobre el modelo en estrella del almacén (S7-01, S8-01 a S8-03).

Todas las funciones aceptan los mismos filtros: periodo (desde, hasta), departamento, ciudad, categoría y
si se incluyen los datos sintéticos. Las series agrupan por día, mes o año. Cada cifra sale de una sola
consulta sobre `dw`, así que coincide con una consulta manual al almacén (lo prueban los tests).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

GRANULARIDAD = {"dia": "t.fecha", "mes": "date_trunc('month', t.fecha)::date",
                "anio": "date_trunc('year', t.fecha)::date"}

# indicador → (hecho, columna de tiempo, expresión de la medida)
INDICADORES = {
    "donaciones_registradas": ("dw.fact_donacion", "sk_tiempo_publicacion", "count(*)"),
    "reservas_gestionadas": ("dw.fact_reserva", "sk_tiempo_reserva", "count(*)"),
    "entregas_finalizadas": ("dw.fact_entrega", "sk_tiempo_entrega",
                             "count(*) FILTER (WHERE e.estado = 'COMPLETADA')"),
    "proporcion_canceladas_vencidas": (
        "dw.fact_donacion", "sk_tiempo_publicacion",
        "round(count(*) FILTER (WHERE e.estado IN ('CANCELADA', 'VENCIDA'))::numeric / nullif(count(*), 0), 4)"),
}


@dataclass(frozen=True)
class Filtros:
    desde: date
    hasta: date
    departamento: str | None = None
    ciudad: str | None = None
    id_categoria: int | None = None
    incluir_sinteticos: bool = True

    def sql(self) -> tuple[str, dict]:
        condiciones = ["t.fecha BETWEEN :desde AND :hasta"]
        params = {"desde": self.desde, "hasta": self.hasta}
        if not self.incluir_sinteticos:
            condiciones.append("f.origen_dato = 'REAL'")
        if self.departamento:
            condiciones.append("u.departamento = :departamento")
            params["departamento"] = self.departamento
        if self.ciudad:
            condiciones.append("u.ciudad = :ciudad")
            params["ciudad"] = self.ciudad
        if self.id_categoria:
            condiciones.append("c.id_categoria = :id_categoria")
            params["id_categoria"] = self.id_categoria
        return " AND ".join(condiciones), params


def _desde_hecho(hecho: str, col_tiempo: str) -> str:
    return f"""FROM {hecho} f
        JOIN dw.dim_tiempo t ON t.sk_tiempo = f.{col_tiempo}
        JOIN dw.dim_ubicacion u ON u.sk_ubicacion = f.sk_ubicacion
        JOIN dw.dim_categoria c ON c.sk_categoria = f.sk_categoria
        JOIN dw.dim_estado e ON e.sk_estado = f.sk_estado"""


def serie(db: Connection, indicador: str, filtros: Filtros, granularidad: str = "mes") -> list[dict]:
    """Valor del indicador por periodo."""
    hecho, col_tiempo, medida = INDICADORES[indicador]
    where, params = filtros.sql()
    sql = f"""SELECT {GRANULARIDAD[granularidad]} AS periodo, {medida} AS valor
        {_desde_hecho(hecho, col_tiempo)} WHERE {where} GROUP BY 1 ORDER BY 1"""
    return [{"periodo": f["periodo"], "valor": float(f["valor"]) if f["valor"] is not None else None}
            for f in db.execute(text(sql), params).mappings()]


def total(db: Connection, indicador: str, filtros: Filtros) -> float:
    """Valor del indicador en todo el periodo (no es la suma de la serie para las proporciones)."""
    hecho, col_tiempo, medida = INDICADORES[indicador]
    where, params = filtros.sql()
    valor = db.execute(text(f"SELECT {medida} {_desde_hecho(hecho, col_tiempo)} WHERE {where}"), params).scalar()
    return float(valor or 0)


def volumen_distribuido(db: Connection, filtros: Filtros) -> list[dict]:
    """Cantidad entregada por unidad de medida (no se suman kg con litros)."""
    where, params = filtros.sql()
    sql = f"""SELECT f.unidad_medida, sum(f.cantidad) AS cantidad, count(*) AS entregas
        {_desde_hecho('dw.fact_entrega', 'sk_tiempo_entrega')}
        WHERE {where} AND e.estado = 'COMPLETADA' GROUP BY 1 ORDER BY 2 DESC"""
    return [{"unidad_medida": f["unidad_medida"], "cantidad": float(f["cantidad"]), "entregas": f["entregas"]}
            for f in db.execute(text(sql), params).mappings()]


def cobertura(db: Connection, filtros: Filtros) -> list[dict]:
    """Indicadores por departamento y ciudad, con coordenadas para el mapa (S8-03)."""
    where, params = filtros.sql()
    sql = f"""SELECT u.departamento, u.ciudad, u.latitud, u.longitud,
               count(*) AS donaciones,
               count(*) FILTER (WHERE e.estado = 'ENTREGADA') AS entregadas,
               count(*) FILTER (WHERE e.estado IN ('CANCELADA', 'VENCIDA')) AS perdidas,
               round(count(*) FILTER (WHERE e.estado = 'ENTREGADA')::numeric / nullif(count(*), 0), 4) AS tasa_entrega
        {_desde_hecho('dw.fact_donacion', 'sk_tiempo_publicacion')}
        WHERE {where} AND u.sk_ubicacion <> -1
        GROUP BY 1, 2, 3, 4 ORDER BY donaciones DESC"""
    return [{**dict(f), "tasa_entrega": float(f["tasa_entrega"] or 0)} for f in db.execute(text(sql), params).mappings()]


def resumen(db: Connection, filtros: Filtros) -> dict:
    return {
        "donaciones_registradas": int(total(db, "donaciones_registradas", filtros)),
        "reservas_gestionadas": int(total(db, "reservas_gestionadas", filtros)),
        "entregas_finalizadas": int(total(db, "entregas_finalizadas", filtros)),
        "proporcion_canceladas_vencidas": total(db, "proporcion_canceladas_vencidas", filtros),
        "volumen_distribuido": volumen_distribuido(db, filtros),
    }


def opciones_filtros(db: Connection) -> dict:
    ubicaciones = db.execute(text("SELECT departamento, ciudad FROM dw.dim_ubicacion WHERE sk_ubicacion <> -1 "
                                  "ORDER BY 1, 2")).all()
    categorias = db.execute(text("SELECT id_categoria, nombre_categoria FROM dw.dim_categoria "
                                 "WHERE sk_categoria <> -1 ORDER BY 2")).all()
    rango = db.execute(text("SELECT min(fecha_publicacion)::date, max(fecha_publicacion)::date "
                            "FROM dw.fact_donacion")).one()
    return {
        "departamentos": sorted({d for d, _ in ubicaciones}),
        "ciudades": [{"departamento": d, "ciudad": c} for d, c in ubicaciones],
        "categorias": [{"id_categoria": i, "nombre_categoria": n} for i, n in categorias],
        "fecha_minima": rango[0], "fecha_maxima": rango[1],
    }


def ultima_carga(db: Connection) -> dict | None:
    fila = db.execute(text("""
        SELECT e.id_ejecucion, e.tipo, e.fin, e.estado,
               (SELECT count(*) FILTER (WHERE NOT aprobada) FROM etl.resultado_calidad r
                WHERE r.id_ejecucion = e.id_ejecucion) AS reglas_fallidas
        FROM etl.ejecucion e WHERE e.estado = 'EXITOSA' ORDER BY e.id_ejecucion DESC LIMIT 1""")).mappings().first()
    return dict(fila) if fila else None
