"""Orquestación de las cargas del almacén (S7-04, S7-05, S7-07).

Cada carga corre en una transacción, queda registrada en etl.ejecucion y termina con las pruebas de calidad.
Si falla, la transacción se revierte (no quedan cargas a medias), la ejecución queda FALLIDA con su error
y se reintenta con espera creciente hasta `reintentos` veces.
"""
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, text

from . import calidad, extraer, sintetico

log = logging.getLogger("redalimenta.etl")
SQL = Path(__file__).parent / "sql"


def _ejecutar_sql(conexion, archivo: str) -> None:
    conexion.exec_driver_sql((SQL / archivo).read_text(encoding="utf-8"))


def _registrar_inicio(motor: Engine, tipo: str, intento: int) -> int:
    with motor.begin() as c:
        return c.execute(text("INSERT INTO etl.ejecucion (tipo, intento) VALUES (:t, :i) RETURNING id_ejecucion"),
                         {"t": tipo, "i": intento}).scalar()


def _registrar_fin(motor: Engine, id_ejecucion: int, estado: str, filas: dict | None = None,
                   error: str | None = None) -> None:
    with motor.begin() as c:
        c.execute(text("UPDATE etl.ejecucion SET fin = now(), estado = :e, filas = :f, error = :err "
                       "WHERE id_ejecucion = :id"),
                  {"e": estado, "f": json.dumps(filas or {}), "err": error, "id": id_ejecucion})


def _conteo_hechos(conexion) -> dict:
    return {f"dw.{t}": conexion.execute(text(f"SELECT count(*) FROM dw.{t}")).scalar()
            for t in ("fact_donacion", "fact_reserva", "fact_entrega", "fact_cambio_estado")}


def cargar(motor: Engine, tipo: str, fuentes: dict[str, str] | None = None, n_sinteticas: int = 50_000,
           semilla: int = 2026, reintentos: int = 3, espera: float = 5.0) -> dict:
    """tipo: 'historica' (bases transaccionales), 'eventos' (incremental), 'sintetica' o 'completa' (las tres)."""
    for intento in range(1, reintentos + 1):
        id_ejecucion = _registrar_inicio(motor, tipo, intento)
        try:
            with motor.begin() as dwh:
                filas = {}
                if tipo in ("sintetica", "completa"):
                    filas.update(_cargar_sinteticos(dwh, n_sinteticas, semilla))
                if tipo in ("historica", "completa"):
                    filas.update({f"stg.{k}": v for k, v in extraer.extraer_historico(dwh, fuentes).items()})
                    _ejecutar_sql(dwh, "transformar.sql")
                elif tipo == "sintetica":
                    _ejecutar_sql(dwh, "transformar.sql")
                if tipo in ("eventos", "completa"):
                    filas["stg.evento (nuevos)"] = extraer.extraer_eventos(dwh, fuentes["analytics"])
                    _ejecutar_sql(dwh, "transformar_eventos.sql")
                filas.update(_conteo_hechos(dwh))
                resultados = calidad.evaluar(dwh, id_ejecucion)
            _registrar_fin(motor, id_ejecucion, "EXITOSA", filas)
            fallidas = [r["regla"] for r in resultados if not r["aprobada"]]
            log.info("Carga %s %s: %s; calidad: %s", tipo, id_ejecucion, filas,
                     "todas aprobadas" if not fallidas else f"fallan {fallidas}")
            return {"id_ejecucion": id_ejecucion, "tipo": tipo, "intento": intento, "filas": filas,
                    "calidad": resultados, "fecha": datetime.now(UTC).isoformat(timespec="seconds")}
        except Exception as error:  # se registra y se reintenta; la transacción ya se revirtió
            _registrar_fin(motor, id_ejecucion, "FALLIDA", error=f"{type(error).__name__}: {error}"[:2000])
            log.warning("Carga %s falló (intento %d de %d): %s", tipo, intento, reintentos, error)
            if intento == reintentos:
                raise
            time.sleep(espera * intento)


def _cargar_sinteticos(dwh, n: int, semilla: int) -> dict:
    lote = sintetico.generar(n, semilla)
    for tabla in ("entrega", "reserva", "donacion", "usuario"):
        dwh.execute(text(f"DELETE FROM stg.{tabla} WHERE origen_dato = 'SINTETICO'"))
    # Los hechos sintéticos se regeneran completos (la misma semilla produce los mismos datos)
    for tabla in ("fact_entrega", "fact_reserva", "fact_donacion"):
        dwh.execute(text(f"DELETE FROM dw.{tabla} WHERE origen_dato = 'SINTETICO'"))
    dwh.execute(text("INSERT INTO stg.categoria (id_categoria, nombre_categoria) VALUES (:i, :n) "
                     "ON CONFLICT (id_categoria) DO NOTHING"), [{"i": i, "n": n} for i, n in lote.categorias])
    return {
        "stg.usuario (sintéticos)": extraer.copiar(dwh, "stg.usuario", ("origen_dato", "id_usuario", "rol",
                                                                        "estado_verificacion"), lote.usuarios),
        "stg.donacion (sintéticas)": extraer.copiar(dwh, "stg.donacion", (
            "origen_dato", "id_donacion", "id_donante", "id_categoria", "cantidad", "unidad_medida",
            "fecha_publicacion", "fecha_vencimiento", "estado_donacion", "ciudad", "departamento", "latitud",
            "longitud"), lote.donaciones),
        "stg.reserva (sintéticas)": extraer.copiar(dwh, "stg.reserva", (
            "origen_dato", "id_reserva", "id_donacion", "id_receptor", "fecha_reserva", "fecha_expiracion",
            "estado_reserva"), lote.reservas),
        "stg.entrega (sintéticas)": extraer.copiar(dwh, "stg.entrega", (
            "origen_dato", "id_entrega", "id_reserva", "fecha_programada", "fecha_entrega", "estado_entrega",
            "con_incidencia"), lote.entregas),
    }
