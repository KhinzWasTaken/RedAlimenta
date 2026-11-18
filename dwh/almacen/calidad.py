"""Pruebas de calidad de datos (S7-06). Corren al final de cada carga y quedan en etl.resultado_calidad.

Cada regla es una consulta que cuenta filas con problema; la regla se aprueba si cuenta 0.
"""
from sqlalchemy import Connection, text

REGLAS: list[tuple[str, str, str]] = [
    ("sin_duplicados_donacion", "Una sola fila por donación (origen_dato, id_donacion)",
     "SELECT count(*) - count(DISTINCT (origen_dato, id_donacion)) FROM dw.fact_donacion"),
    ("sin_duplicados_reserva", "Una sola fila por reserva",
     "SELECT count(*) - count(DISTINCT (origen_dato, id_reserva)) FROM dw.fact_reserva"),
    ("sin_duplicados_entrega", "Una sola fila por entrega",
     "SELECT count(*) - count(DISTINCT (origen_dato, id_entrega)) FROM dw.fact_entrega"),
    ("sin_cantidades_no_positivas", "Ninguna cantidad menor o igual a cero en donaciones ni entregas",
     "SELECT (SELECT count(*) FROM dw.fact_donacion WHERE cantidad <= 0) "
     "     + (SELECT count(*) FROM dw.fact_entrega WHERE cantidad <= 0)"),
    ("reservas_con_donacion", "Toda reserva apunta a una donación del almacén (sin claves huérfanas)",
     "SELECT count(*) FROM dw.fact_reserva r WHERE NOT EXISTS (SELECT 1 FROM dw.fact_donacion d "
     "WHERE d.origen_dato = r.origen_dato AND d.id_donacion = r.id_donacion)"),
    ("entregas_con_reserva", "Toda entrega apunta a una reserva del almacén (sin claves huérfanas)",
     "SELECT count(*) FROM dw.fact_entrega e WHERE NOT EXISTS (SELECT 1 FROM dw.fact_reserva r "
     "WHERE r.origen_dato = e.origen_dato AND r.id_reserva = e.id_reserva)"),
    ("dimensiones_resueltas", "Hechos sin categoría, ubicación o participante desconocidos (-1)",
     "SELECT count(*) FROM dw.fact_donacion WHERE -1 IN (sk_categoria, sk_ubicacion, sk_donante, sk_estado)"),
    ("una_reserva_activa", "Como máximo una reserva activa por donación (D-02)",
     "SELECT count(*) FROM (SELECT r.origen_dato, r.id_donacion FROM dw.fact_reserva r "
     "JOIN dw.dim_estado e ON e.sk_estado = r.sk_estado WHERE e.estado IN ('PENDIENTE', 'CONFIRMADA') "
     "GROUP BY 1, 2 HAVING count(*) > 1) x"),
    ("fechas_en_orden", "publicación ≤ reserva ≤ entrega y entrega ≤ vencimiento",
     "SELECT (SELECT count(*) FROM dw.fact_reserva r JOIN dw.fact_donacion d ON d.origen_dato = r.origen_dato "
     "        AND d.id_donacion = r.id_donacion WHERE r.fecha_reserva < d.fecha_publicacion) "
     "     + (SELECT count(*) FROM dw.fact_entrega e JOIN dw.fact_reserva r ON r.origen_dato = e.origen_dato "
     "        AND r.id_reserva = e.id_reserva WHERE e.fecha_entrega < r.fecha_reserva) "
     "     + (SELECT count(*) FROM dw.fact_entrega e JOIN dw.fact_donacion d ON d.origen_dato = e.origen_dato "
     "        AND d.id_donacion = e.id_donacion WHERE e.fecha_entrega > d.fecha_vencimiento)"),
    ("entregada_con_dos_confirmaciones", "Donación ENTREGADA ⇔ entrega COMPLETADA y reserva COMPLETADA",
     "SELECT count(*) FROM dw.fact_donacion d JOIN dw.dim_estado ed ON ed.sk_estado = d.sk_estado "
     "WHERE (ed.estado = 'ENTREGADA') <> EXISTS (SELECT 1 FROM dw.fact_entrega e "
     "  JOIN dw.dim_estado ee ON ee.sk_estado = e.sk_estado JOIN dw.fact_reserva r ON r.origen_dato = e.origen_dato "
     "  AND r.id_reserva = e.id_reserva JOIN dw.dim_estado er ON er.sk_estado = r.sk_estado "
     "  WHERE e.origen_dato = d.origen_dato AND e.id_donacion = d.id_donacion "
     "  AND ee.estado = 'COMPLETADA' AND er.estado = 'COMPLETADA')"),
    ("conteos_origen_destino", "Las filas REAL del área de paso llegaron todas a los hechos",
     "SELECT abs((SELECT count(*) FROM stg.donacion WHERE origen_dato = 'REAL') "
     "         - (SELECT count(*) FROM dw.fact_donacion f WHERE origen_dato = 'REAL' AND EXISTS "
     "            (SELECT 1 FROM stg.donacion s WHERE s.origen_dato = 'REAL' AND s.id_donacion = f.id_donacion))) "
     "     + abs((SELECT count(*) FROM stg.reserva WHERE origen_dato = 'REAL') "
     "         - (SELECT count(*) FROM dw.fact_reserva f WHERE origen_dato = 'REAL' AND EXISTS "
     "            (SELECT 1 FROM stg.reserva s WHERE s.origen_dato = 'REAL' AND s.id_reserva = f.id_reserva))) "
     "     + abs((SELECT count(*) FROM stg.entrega WHERE origen_dato = 'REAL') "
     "         - (SELECT count(*) FROM dw.fact_entrega f WHERE origen_dato = 'REAL' AND EXISTS "
     "            (SELECT 1 FROM stg.entrega s WHERE s.origen_dato = 'REAL' AND s.id_entrega = f.id_entrega)))"),
    ("eventos_transformados", "Todo evento del área de paso quedó en fact_cambio_estado",
     "SELECT count(*) FROM stg.evento s WHERE NOT EXISTS (SELECT 1 FROM dw.fact_cambio_estado f "
     "WHERE f.id_evento = s.id_evento)"),
]


def evaluar(dwh: Connection, id_ejecucion: int) -> list[dict]:
    resultados = []
    for regla, descripcion, sql in REGLAS:
        problemas = dwh.execute(text(sql)).scalar() or 0
        resultados.append({"regla": regla, "descripcion": descripcion, "filas_con_problema": problemas,
                           "aprobada": problemas == 0})
        dwh.execute(text("""
            INSERT INTO etl.resultado_calidad (id_ejecucion, regla, descripcion, filas_con_problema, aprobada)
            VALUES (:e, :r, :d, :p, :a)"""), {"e": id_ejecucion, "r": regla, "d": descripcion, "p": problemas,
                                              "a": problemas == 0})
    return resultados


def informe_markdown(resultados: list[dict], resumen: dict) -> str:
    lineas = ["# Informe de calidad del almacén", "",
              f"Ejecución {resumen['id_ejecucion']} ({resumen['tipo']}) · {resumen['fecha']}", "",
              "| Regla | Qué comprueba | Filas con problema | Resultado |", "| --- | --- | --- | --- |"]
    lineas += [f"| `{r['regla']}` | {r['descripcion']} | {r['filas_con_problema']} | "
               f"{'✅ aprobada' if r['aprobada'] else '❌ falla'} |" for r in resultados]
    lineas += ["", "Volumen cargado:", ""] + [f"- {k}: {v}" for k, v in resumen["filas"].items()]
    return "\n".join(lineas) + "\n"
