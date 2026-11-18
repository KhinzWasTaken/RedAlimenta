"""Genera el diccionario de datos (S4-12) leyendo el catálogo de PostgreSQL de cada base.

Así el documento no puede desfasarse del esquema: los textos salen de COMMENT ON (definidos en
las migraciones) y los tipos, nulos, claves, restricciones, índices y triggers, de la propia base.
"""
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

SERVICIO_DE_BASE = {
    "identity": "identity-service", "catalog": "catalog-geo-service",
    "fulfillment": "fulfillment-service", "notification": "notification-service",
    "analytics": "analytics-service", "dwh": "almacén de datos",
}
EXCLUIDAS = ("alembic_version", "spatial_ref_sys")

SQL_TABLAS = """
SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE n.nspname || '.' || c.relname END, obj_description(c.oid, 'pg_class')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'stg', 'dw', 'etl') AND c.relkind = 'r' AND c.relname NOT IN :excluidas
ORDER BY c.oid
"""
SQL_COLUMNAS = """
SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE n.nspname || '.' || c.relname END,
       a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull,
       pg_get_expr(d.adbin, d.adrelid), col_description(c.oid, a.attnum)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname IN ('public', 'stg', 'dw', 'etl') AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
  AND c.relname NOT IN :excluidas
ORDER BY c.relname, a.attnum
"""
SQL_RESTRICCIONES = """
SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE n.nspname || '.' || c.relname END,
       con.conname, con.contype, pg_get_constraintdef(con.oid)
FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'stg', 'dw', 'etl') AND c.relname NOT IN :excluidas
ORDER BY c.relname, con.contype, con.conname
"""
SQL_INDICES = """
SELECT CASE WHEN schemaname = 'public' THEN tablename ELSE schemaname || '.' || tablename END,
       indexname, indexdef FROM pg_indexes
WHERE schemaname IN ('public', 'stg', 'dw', 'etl') AND tablename NOT IN :excluidas
  AND indexname NOT IN (SELECT conname FROM pg_constraint)
ORDER BY tablename, indexname
"""
SQL_TRIGGERS = """
SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE n.nspname || '.' || c.relname END, t.tgname, p.proname
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_proc p ON p.oid = t.tgfoid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal ORDER BY c.relname, t.tgname
"""
SQL_ENUMS = """
SELECT t.typname, string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder)
FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid GROUP BY t.typname ORDER BY t.typname
"""
TIPO_RESTRICCION = {"p": "PK", "f": "FK", "u": "UNIQUE", "c": "CHECK", "x": "EXCLUDE"}


def _celda(valor) -> str:
    return "" if valor is None else str(valor).replace("|", "\\|").replace("\n", " ")


def generar(urls: dict[str, str], destino: Path) -> None:
    lineas = [
        "# Diccionario de datos",
        "",
        "Generado con `python scripts/bd.py diccionario` a partir del catálogo de PostgreSQL de cada base;",
        "no se edita a mano. Las descripciones salen de los `COMMENT ON` de las migraciones.",
        "La justificación de la normalización está en `docs/modelo/normalizacion.md`.",
        "",
    ]
    for base, url in urls.items():
        motor = create_engine(url)
        params = {"excluidas": EXCLUIDAS}
        with motor.connect() as c:
            from sqlalchemy import bindparam
            exp = lambda sql: text(sql).bindparams(bindparam("excluidas", expanding=True))  # noqa: E731
            tablas = c.execute(exp(SQL_TABLAS), params).all()
            columnas = defaultdict(list)
            for fila in c.execute(exp(SQL_COLUMNAS), params):
                columnas[fila[0]].append(fila[1:])
            restricciones = defaultdict(list)
            for fila in c.execute(exp(SQL_RESTRICCIONES), params):
                restricciones[fila[0]].append(fila[1:])
            indices = defaultdict(list)
            for fila in c.execute(exp(SQL_INDICES), params):
                indices[fila[0]].append(fila[1:])
            triggers = defaultdict(list)
            for fila in c.execute(text(SQL_TRIGGERS)):
                triggers[fila[0]].append(fila[1:])
            enums = c.execute(text(SQL_ENUMS)).all()
        motor.dispose()

        lineas += [f"## Base `redalimenta_{base}` ({SERVICIO_DE_BASE[base]})", ""]
        if enums:
            lineas += ["**Tipos enumerados (D-03)**", "", "| Tipo | Valores |", "| --- | --- |"]
            lineas += [f"| `{n}` | {v} |" for n, v in enums] + [""]
        for tabla, descripcion in tablas:
            lineas += [f"### `{tabla}`", "", _celda(descripcion), "",
                       "| Columna | Tipo | Nulo | Por defecto | Descripción |", "| --- | --- | --- | --- | --- |"]
            for col, tipo, nulo, defecto, desc in columnas[tabla]:
                lineas.append(f"| `{col}` | {_celda(tipo)} | {'sí' if nulo else 'no'} | "
                              f"{_celda(defecto)} | {_celda(desc)} |")
            if restricciones[tabla]:
                lineas += ["", "Restricciones:", ""]
                lineas += [f"- **{TIPO_RESTRICCION.get(t, t)}** `{n}`: `{_celda(d)}`"
                           for n, t, d in restricciones[tabla]]
            if indices[tabla]:
                lineas += ["", "Índices:", ""]
                lineas += [f"- `{n}`: `{_celda(d.split(' USING ', 1)[-1])}`" for n, d in indices[tabla]]
            if triggers[tabla]:
                lineas += ["", "Triggers:", ""]
                lineas += [f"- `{n}` → `{f}()`" for n, f in triggers[tabla]]
            lineas.append("")
    destino.write_text("\n".join(lineas), encoding="utf-8")
    print(f"» Diccionario escrito en {destino.relative_to(destino.parents[2])}")
