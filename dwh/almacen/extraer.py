"""Extracción de las bases transaccionales y del historial de eventos hacia el área de paso (S7-04, S7-05).

Las fuentes se leen con un rol de solo lectura (`dwh_lector`) y en transacciones READ ONLY: el ETL nunca
puede modificar una base transaccional.
"""
import json
from collections.abc import Iterable, Sequence

from sqlalchemy import Connection, create_engine, text

# Consultas de extracción por fuente (solo columnas necesarias; nada de datos personales: ni nombres,
# ni correos, ni teléfonos llegan al almacén — Ley 1581)
EXTRACCIONES = {
    "identity": {
        "usuario": ("""
            SELECT 'REAL', u.id_usuario, r.nombre_rol,
                   (SELECT v.estado_verificacion::text FROM verificacion_usuario v
                    WHERE v.id_usuario = u.id_usuario ORDER BY v.id_verificacion DESC LIMIT 1)
            FROM usuario u JOIN rol r ON r.id_rol = u.id_rol""",
                    ("origen_dato", "id_usuario", "rol", "estado_verificacion")),
    },
    "catalog": {
        "categoria": ("SELECT id_categoria, nombre_categoria FROM categoria_alimento",
                      ("id_categoria", "nombre_categoria")),
        "donacion": ("""
            SELECT 'REAL', d.id_donacion, d.id_donante, d.id_categoria, d.cantidad, d.unidad_medida,
                   d.fecha_publicacion, d.fecha_vencimiento, d.estado_donacion::text, u.ciudad, u.departamento,
                   ST_Y(u.coordenada_geografica::geometry), ST_X(u.coordenada_geografica::geometry)
            FROM donacion d JOIN ubicacion_geografica u ON u.id_ubicacion = d.id_ubicacion""",
                     ("origen_dato", "id_donacion", "id_donante", "id_categoria", "cantidad", "unidad_medida",
                      "fecha_publicacion", "fecha_vencimiento", "estado_donacion", "ciudad", "departamento",
                      "latitud", "longitud")),
    },
    "fulfillment": {
        "reserva": ("""
            SELECT 'REAL', id_reserva, id_donacion, id_receptor, fecha_reserva, fecha_expiracion,
                   estado_reserva::text FROM reserva""",
                    ("origen_dato", "id_reserva", "id_donacion", "id_receptor", "fecha_reserva",
                     "fecha_expiracion", "estado_reserva")),
        "entrega": ("""
            SELECT 'REAL', e.id_entrega, e.id_reserva, e.fecha_programada, e.fecha_entrega,
                   e.estado_entrega::text,
                   EXISTS (SELECT 1 FROM confirmacion_entrega c
                           WHERE c.id_entrega = e.id_entrega AND c.estado_confirmacion = 'CON_INCIDENCIA')
            FROM entrega e""",
                    ("origen_dato", "id_entrega", "id_reserva", "fecha_programada", "fecha_entrega",
                     "estado_entrega", "con_incidencia")),
    },
}
COLUMNAS_EVENTO = ("id_evento", "tipo", "version", "origen", "fecha", "id_actor", "entidad", "id_entidad",
                   "estado_anterior", "estado_nuevo", "datos", "id_correlacion", "fecha_recepcion")


def motor_lectura(url: str):
    """Conexión que la propia base trata como de solo lectura."""
    return create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})


def copiar(dwh: Connection, tabla: str, columnas: Sequence[str], filas: Iterable[Sequence]) -> int:
    """Carga masiva con COPY (rápida para los datos sintéticos). Devuelve las filas copiadas."""
    n = 0
    cursor = dwh.connection.driver_connection.cursor()
    with cursor.copy(f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN") as copia:
        for fila in filas:
            copia.write_row(fila)
            n += 1
    return n


def extraer_historico(dwh: Connection, fuentes: dict[str, str]) -> dict[str, int]:
    """Reemplaza en stg las filas REAL con una copia fresca de las bases transaccionales."""
    contados = {}
    for fuente, tablas in EXTRACCIONES.items():
        motor = motor_lectura(fuentes[fuente])
        with motor.connect() as origen:
            for tabla, (sql, columnas) in tablas.items():
                filas = origen.execute(text(sql)).all()
                if "origen_dato" in columnas:
                    dwh.execute(text(f"DELETE FROM stg.{tabla} WHERE origen_dato = 'REAL'"))
                else:  # catálogo compartido (categorías): se reemplaza entero
                    dwh.execute(text(f"DELETE FROM stg.{tabla}"))
                contados[tabla] = copiar(dwh, f"stg.{tabla}", columnas, filas)
        motor.dispose()
    return contados


def extraer_eventos(dwh: Connection, url_analytics: str, lote: int = 50_000) -> int:
    """Copia a stg.evento los eventos nuevos del historial de analytics (incremental por marca de agua)."""
    marca = dwh.execute(text("SELECT valor FROM etl.marca_agua WHERE fuente = 'eventos'")).scalar()
    motor = motor_lectura(url_analytics)
    with motor.connect() as origen:
        filas = origen.execute(text(f"""
            SELECT {', '.join(COLUMNAS_EVENTO)} FROM historial_evento
            WHERE fecha_recepcion >= coalesce(:marca, '-infinity'::timestamptz)
            ORDER BY fecha_recepcion LIMIT :lote"""), {"marca": marca, "lote": lote}).all()
    motor.dispose()
    if not filas:
        return 0
    # Los eventos en el borde de la marca pueden repetirse: se insertan sin duplicar (PK id_evento)
    dwh.execute(text("CREATE TEMP TABLE evento_nuevo (LIKE stg.evento INCLUDING DEFAULTS) ON COMMIT DROP"))
    copiar(dwh, "evento_nuevo", COLUMNAS_EVENTO,
           ([*f[:10], json.dumps(f[10]), *f[11:]] for f in filas))
    nuevos = dwh.execute(text(f"""
        INSERT INTO stg.evento ({', '.join(COLUMNAS_EVENTO)})
        SELECT {', '.join(COLUMNAS_EVENTO)} FROM evento_nuevo ON CONFLICT (id_evento) DO NOTHING""")).rowcount
    dwh.execute(text("""
        INSERT INTO etl.marca_agua (fuente, valor) VALUES ('eventos', :valor)
        ON CONFLICT (fuente) DO UPDATE SET valor = EXCLUDED.valor"""), {"valor": filas[-1][-1]})
    return nuevos
