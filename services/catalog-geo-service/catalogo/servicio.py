"""Casos de uso de catalog-geo-service: repositorio + eventos. D-01: solo aquí cambia estado_donacion."""
from datetime import datetime

from sqlalchemy.orm import Session

from redalimenta_comun.eventos import Lote

from . import repositorio as repo
from .errores import NoEncontrado, Prohibido

EVENTO_POR_ESTADO = {
    "RESERVADA": "DONACION_RESERVADA", "DISPONIBLE": "DONACION_LIBERADA", "ENTREGADA": "DONACION_ENTREGADA",
    "CANCELADA": "DONACION_CANCELADA", "VENCIDA": "DONACION_VENCIDA",
}


def _iso(valor: datetime | None):
    return None if valor is None else valor.isoformat()


def donacion_api(d: dict) -> dict:
    return {
        "id_donacion": d["id_donacion"], "id_donante": d["id_donante"], "id_categoria": d["id_categoria"],
        "categoria": d.get("categoria") or d.get("nombre_categoria"), "nombre_alimento": d["nombre_alimento"],
        "descripcion": d.get("descripcion"), "cantidad": float(d["cantidad"]), "unidad_medida": d["unidad_medida"],
        "fecha_vencimiento": _iso(d["fecha_vencimiento"]), "fecha_publicacion": _iso(d.get("fecha_publicacion")),
        "condiciones_recogida": d.get("condiciones_recogida"), "estado_donacion": d.get("estado_donacion", "DISPONIBLE"),
        "ubicacion": {"lat": d["lat"], "lon": d["lon"], "direccion_referencia": d["direccion_referencia"],
                      "ciudad": d["ciudad"], "departamento": d["departamento"]},
        "id_necesidad": d.get("id_necesidad"), "necesidad": d.get("necesidad"),
        "id_receptor_exclusivo": d.get("id_receptor_exclusivo"),
    }


def necesidad_api(n: dict) -> dict:
    return {
        "id_necesidad": n["id_necesidad"], "id_receptor": n["id_receptor"], "id_categoria": n["id_categoria"],
        "categoria": n["categoria"], "descripcion": n["descripcion"],
        "cantidad_requerida": float(n["cantidad_requerida"]), "unidad_medida": n["unidad_medida"],
        "nivel_urgencia": n["nivel_urgencia"], "fecha_limite": _iso(n["fecha_limite"]),
        "estado_necesidad": n["estado_necesidad"], "ofertas": int(n.get("ofertas") or 0),
        "ubicacion": {"lat": n["lat"], "lon": n["lon"], "direccion_referencia": n["direccion_referencia"],
                      "ciudad": n["ciudad"], "departamento": n["departamento"]},
    }


def solicitud_api(n: dict) -> dict:
    """D-11: lo que un donante ve de una necesidad abierta (sin receptor ni dirección escrita)."""
    distancia = n.get("distancia_m")
    return {
        "id_necesidad": n["id_necesidad"], "id_categoria": n["id_categoria"], "categoria": n["categoria"],
        "descripcion": n["descripcion"], "cantidad_requerida": float(n["cantidad_requerida"]),
        "unidad_medida": n["unidad_medida"], "nivel_urgencia": n["nivel_urgencia"],
        "fecha_limite": _iso(n["fecha_limite"]), "ofertas": int(n["ofertas"]),
        "distancia_km": None if distancia is None else round(float(distancia) / 1000, 3),
        "ubicacion": {"lat": n["lat"], "lon": n["lon"], "ciudad": n["ciudad"], "departamento": n["departamento"]},
    }


def una_donacion(db: Session, id_donacion: int) -> dict:
    filas = repo.detalle_donaciones(db, ids=[id_donacion])
    if not filas:
        raise NoEncontrado("Donación no encontrada")
    return donacion_api(filas[0])


def una_necesidad(db: Session, id_necesidad: int) -> dict:
    filas = repo.detalle_necesidades(db, ids=[id_necesidad])
    if not filas:
        raise NoEncontrado("Necesidad no encontrada")
    return necesidad_api(filas[0])


# --- Donaciones ----------------------------------------------------------------

def crear_donacion(db: Session, lote: Lote, id_donante: int, datos: dict) -> int:
    d = repo.crear_donacion(db, id_donante, **datos)
    para = {}
    if d.id_necesidad is not None:  # D-11: el receptor que la pidió recibe el aviso
        n = repo.detalle_necesidades(db, ids=[d.id_necesidad])[0]
        para = {"id_necesidad": d.id_necesidad, "id_receptor": n["id_receptor"], "necesidad": n["descripcion"]}
    lote.agregar("DONACION_CREADA", "donacion", d.id_donacion, None, "DISPONIBLE", id_donante,
                 id_donante=id_donante, nombre_alimento=d.nombre_alimento, id_categoria=d.id_categoria,
                 ciudad=datos["ciudad"], departamento=datos["departamento"], cantidad=float(d.cantidad),
                 unidad_medida=d.unidad_medida, **para)
    return d.id_donacion


def actualizar_donacion(db: Session, lote: Lote, id_donacion: int, id_donante: int, cambios: dict) -> None:
    d = repo.actualizar_donacion(db, id_donacion, id_donante, **cambios)
    lote.agregar("DONACION_ACTUALIZADA", "donacion", id_donacion, d.estado_donacion, d.estado_donacion, id_donante,
                 id_donante=id_donante, nombre_alimento=d.nombre_alimento, campos=sorted(cambios))


def transicionar(db: Session, lote: Lote, id_donacion: int, nuevo: str, id_actor: int | None,
                 datos: dict | None = None) -> tuple[str, dict]:
    """D-01: valida y aplica la transición, y anuncia el cambio. Devuelve (estado anterior, donación)."""
    anterior, d = repo.transicionar_donacion(db, id_donacion, nuevo, (datos or {}).get("id_receptor"))
    lote.agregar(EVENTO_POR_ESTADO[nuevo], "donacion", id_donacion, anterior, nuevo, id_actor,
                 id_donante=d.id_donante, nombre_alimento=d.nombre_alimento, **(datos or {}))
    return anterior, una_donacion(db, id_donacion)


def cancelar_donacion(db: Session, lote: Lote, id_donacion: int, id_donante: int) -> dict:
    if repo.obtener_donacion(db, id_donacion).id_donante != id_donante:
        raise Prohibido("Solo el donante dueño cancela la donación")
    return transicionar(db, lote, id_donacion, "CANCELADA", id_donante)[1]


def vencer(db: Session, lote: Lote, ahora: datetime | None = None) -> list[int]:
    ids = repo.vencer_donaciones(db, ahora)
    for d in repo.detalle_donaciones(db, ids=ids) if ids else []:
        lote.agregar("DONACION_VENCIDA", "donacion", d["id_donacion"], "DISPONIBLE", "VENCIDA", None,
                     id_donante=d["id_donante"], nombre_alimento=d["nombre_alimento"])
    return ids


def buscar(db: Session, id_receptor: int, **filtros) -> dict:
    resultados = repo.buscar_donaciones(db, id_receptor=id_receptor, **filtros)
    if filtros.get("id_necesidad") is not None:
        n = una_necesidad(db, filtros["id_necesidad"])
        lat, lon = n["ubicacion"]["lat"], n["ubicacion"]["lon"]
    else:
        lat, lon = filtros["lat"], filtros["lon"]
    salida = []
    for r in resultados:
        item = donacion_api(r)
        item.update({
            "distancia_m": round(float(r["distancia_m"]), 1), "distancia_km": round(float(r["distancia_m"]) / 1000, 3),
            "nivel_urgencia": r["nivel_urgencia"], "para_mi": bool(r["para_mi"]),
            "prioridad": {"puntaje": float(r["puntaje"]), "urgencia": float(r["urgencia"]),
                          "cercania": round(float(r["cercania"]), 4), "vencimiento": round(float(r["vencimiento"]), 4)},
        })
        salida.append(item)
    return {"punto": {"lat": lat, "lon": lon}, "orden": filtros.get("orden", "distancia"), "resultados": salida}


# --- Necesidades ---------------------------------------------------------------

def crear_necesidad(db: Session, lote: Lote, id_receptor: int, datos: dict) -> int:
    n = repo.crear_necesidad(db, id_receptor, **datos)
    lote.agregar("NECESIDAD_CREADA", "necesidad", n.id_necesidad, None, "ABIERTA", id_receptor,
                 id_receptor=id_receptor, descripcion=n.descripcion, nivel_urgencia=n.nivel_urgencia)
    return n.id_necesidad


def ajustar_necesidad(db: Session, lote: Lote, id_necesidad: int, id_receptor: int, cambios: dict) -> None:
    n = repo.ajustar_necesidad(db, id_necesidad, id_receptor, **cambios)
    lote.agregar("NECESIDAD_AJUSTADA", "necesidad", id_necesidad, "ABIERTA", "ABIERTA", id_receptor,
                 id_receptor=id_receptor, descripcion=n.descripcion, campos=sorted(cambios))


def cerrar_necesidad(db: Session, lote: Lote, id_necesidad: int, id_receptor: int, estado: str) -> None:
    n = repo.cerrar_necesidad(db, id_necesidad, id_receptor, estado)
    lote.agregar(f"NECESIDAD_{estado}", "necesidad", id_necesidad, "ABIERTA", estado, id_receptor,
                 id_receptor=id_receptor, descripcion=n.descripcion)
