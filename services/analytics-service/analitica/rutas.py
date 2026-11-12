"""API de analytics-service, solo para administradores: trazabilidad por entidad y por usuario (S5-15) e
indicadores, cobertura y reportes CSV sobre el almacén de datos (S8-01 a S8-03)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.seguridad import Actor, requiere_rol

from . import indicadores as ind
from . import repositorio as repo
from .almacen import conexion_almacen
from .db import sesiones
from .errores import ErrorDominio

rutas = APIRouter(prefix="/api/historial", tags=["historial"])
obtener_db = dependencia_sesion(sesiones)
ADMIN = requiere_rol("ADMINISTRADOR")


@rutas.get("/entidades/{entidad}")
def por_entidad(entidad: str, id_entidad: int | None = None, tipo: str | None = None,
                limite: int = Query(500, le=5000), _: Actor = Depends(ADMIN), db: Session = Depends(obtener_db)):
    """Reconstruye la vida de una donación, reserva o entrega en orden cronológico."""
    return [repo.a_dict(h) for h in repo.por_entidad(db, entidad, id_entidad, tipo, limite)]


@rutas.get("/usuarios/{id_usuario}")
def por_usuario(id_usuario: int, limite: int = Query(500, le=5000), _: Actor = Depends(ADMIN),
                db: Session = Depends(obtener_db)):
    return [repo.a_dict(h) for h in repo.por_usuario(db, id_usuario, limite)]


# --- Indicadores y reportes (S8-01, S8-02, S8-03) -------------------------------------------------------
rutas_indicadores = APIRouter(prefix="/api", tags=["indicadores y reportes"])


def filtros(desde: date = date(2025, 1, 1), hasta: date | None = None, departamento: str | None = None,
            ciudad: str | None = None, id_categoria: int | None = None,
            incluir_sinteticos: bool = Query(True, description="Incluir los datos sintéticos del almacén")) -> ind.Filtros:
    hasta = hasta or date.today()
    if desde > hasta:
        raise ErrorDominio("La fecha inicial es posterior a la final")
    return ind.Filtros(desde, hasta, departamento, ciudad, id_categoria, incluir_sinteticos)


def _validar_indicador(indicador: str, granularidad: str) -> None:
    if indicador not in ind.INDICADORES:
        raise ErrorDominio(f"Indicador desconocido; usa uno de: {', '.join(ind.INDICADORES)}")
    if granularidad not in ind.GRANULARIDAD:
        raise ErrorDominio("La granularidad debe ser dia, mes o anio")


@rutas_indicadores.get("/indicadores/resumen")
def resumen(f: ind.Filtros = Depends(filtros), _: Actor = Depends(ADMIN), dwh: Connection = Depends(conexion_almacen)):
    """Totales del periodo: donaciones, reservas, entregas finalizadas, volumen y proporción perdida (RF9)."""
    return {**ind.resumen(dwh, f), "ultima_carga": ind.ultima_carga(dwh)}


@rutas_indicadores.get("/indicadores/serie")
def serie(indicador: str = "donaciones_registradas", granularidad: str = "mes", f: ind.Filtros = Depends(filtros),
          _: Actor = Depends(ADMIN), dwh: Connection = Depends(conexion_almacen)):
    _validar_indicador(indicador, granularidad)
    return {"indicador": indicador, "granularidad": granularidad, "puntos": ind.serie(dwh, indicador, f, granularidad)}


@rutas_indicadores.get("/indicadores/cobertura")
def cobertura(f: ind.Filtros = Depends(filtros), _: Actor = Depends(ADMIN),
              dwh: Connection = Depends(conexion_almacen)):
    """Por departamento y ciudad, con coordenadas listas para el mapa."""
    return ind.cobertura(dwh, f)


@rutas_indicadores.get("/indicadores/filtros")
def opciones(_: Actor = Depends(ADMIN), dwh: Connection = Depends(conexion_almacen)):
    return ind.opciones_filtros(dwh)


def _csv(nombre: str, columnas: list[str], filas: list[dict]) -> Response:
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(filas)
    # BOM para que Excel abra bien las tildes; mismos números que la pantalla (S8-02)
    return Response("\ufeff" + salida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="redalimenta-{nombre}.csv"'})


@rutas_indicadores.get("/reportes/{reporte}.csv")
def exportar(reporte: str, indicador: str = "donaciones_registradas", granularidad: str = "mes",
             f: ind.Filtros = Depends(filtros), _: Actor = Depends(ADMIN), dwh: Connection = Depends(conexion_almacen)):
    """Exporta a CSV: serie, cobertura, volumen o resumen, con los mismos filtros de la pantalla."""
    if reporte == "serie":
        _validar_indicador(indicador, granularidad)
        return _csv(f"{indicador}-{granularidad}", ["periodo", "valor"], ind.serie(dwh, indicador, f, granularidad))
    if reporte == "cobertura":
        return _csv("cobertura", ["departamento", "ciudad", "donaciones", "entregadas", "perdidas", "tasa_entrega",
                                  "latitud", "longitud"], ind.cobertura(dwh, f))
    if reporte == "volumen":
        return _csv("volumen", ["unidad_medida", "cantidad", "entregas"], ind.volumen_distribuido(dwh, f))
    if reporte == "resumen":
        r = ind.resumen(dwh, f)
        filas = [{"indicador": k, "valor": v} for k, v in r.items() if k != "volumen_distribuido"]
        filas += [{"indicador": f"volumen_{v['unidad_medida']}", "valor": v["cantidad"]} for v in r["volumen_distribuido"]]
        return _csv("resumen", ["indicador", "valor"], filas)
    raise ErrorDominio("Reporte desconocido: usa serie, cobertura, volumen o resumen")
