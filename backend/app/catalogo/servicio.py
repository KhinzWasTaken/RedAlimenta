"""Módulo de catálogo: donaciones, necesidades y búsqueda (RF2, RF3, RF4).

D-01: este módulo es el único que escribe `estado_donacion`, siempre a través de
`transicionar_donacion`, que valida que la transición sea legal.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import estados
from app.core.errores import ErrorDominio, NoEncontrado, Prohibido
from app.core.eventos import Evento, publicar
from app.core.seguridad import Actor
from app.core.tiempo import ahora, iso
from app.identidad.servicio import nombres_publicos

from . import busqueda
from .modelos import CategoriaAlimento, Donacion, NecesidadAlimentaria, UbicacionGeografica

EVENTO_POR_ESTADO = {
    "RESERVADA": "DONACION_RESERVADA",
    "DISPONIBLE": "DONACION_LIBERADA",
    "ENTREGADA": "DONACION_ENTREGADA",
    "CANCELADA": "DONACION_CANCELADA",
    "VENCIDA": "DONACION_VENCIDA",
}
ORDEN_URGENCIA = {n: i for i, n in enumerate(estados.NIVELES_URGENCIA)}


# --- Serialización -------------------------------------------------------------

def _ubicacion_dict(u: UbicacionGeografica) -> dict:
    return {"lat": u.latitud, "lon": u.longitud, "direccion_referencia": u.direccion_referencia,
            "ciudad": u.ciudad, "departamento": u.departamento}


def donacion_dict(db: Session, d: Donacion, nombres: dict[int, str] | None = None) -> dict:
    categoria = db.get(CategoriaAlimento, d.id_categoria)
    if nombres is None:
        nombres = nombres_publicos(db, {d.id_donante})
    return {
        "id_donacion": d.id_donacion,
        "id_donante": d.id_donante,
        "donante": nombres.get(d.id_donante),
        "nombre_alimento": d.nombre_alimento,
        "descripcion": d.descripcion,
        "id_categoria": d.id_categoria,
        "categoria": categoria.nombre_categoria if categoria else None,
        "cantidad": d.cantidad,
        "unidad_medida": d.unidad_medida,
        "fecha_vencimiento": iso(d.fecha_vencimiento),
        "fecha_publicacion": iso(d.fecha_publicacion),
        "condiciones_recogida": d.condiciones_recogida,
        "estado_donacion": d.estado_donacion,
        "ubicacion": _ubicacion_dict(db.get(UbicacionGeografica, d.id_ubicacion)),
    }


def necesidad_dict(db: Session, n: NecesidadAlimentaria) -> dict:
    categoria = db.get(CategoriaAlimento, n.id_categoria)
    return {
        "id_necesidad": n.id_necesidad,
        "id_receptor": n.id_receptor,
        "id_categoria": n.id_categoria,
        "categoria": categoria.nombre_categoria if categoria else None,
        "descripcion": n.descripcion,
        "cantidad_requerida": n.cantidad_requerida,
        "unidad_medida": n.unidad_medida,
        "nivel_urgencia": n.nivel_urgencia,
        "fecha_limite": iso(n.fecha_limite),
        "estado_necesidad": n.estado_necesidad,
        "ubicacion": _ubicacion_dict(db.get(UbicacionGeografica, n.id_ubicacion)),
    }


# --- Interfaz interna para otros módulos (D-01) --------------------------------

def obtener_donacion(db: Session, id_donacion: int) -> Donacion:
    d = db.get(Donacion, id_donacion)
    if d is None:
        raise NoEncontrado("Donación no encontrada")
    return d


def transicionar_donacion(db: Session, id_donacion: int, nuevo: str, id_actor: int | None,
                          datos: dict | None = None) -> Donacion:
    """Único punto que cambia `estado_donacion`. Lanza TransicionInvalida si no es legal."""
    d = obtener_donacion(db, id_donacion)
    estados.validar("donacion", d.estado_donacion, nuevo)
    if nuevo == "RESERVADA" and d.fecha_vencimiento <= ahora():
        raise estados.TransicionInvalida("La donación ya venció y no se puede reservar")
    anterior = d.estado_donacion
    d.estado_donacion = nuevo
    db.flush()
    publicar(db, Evento(
        tipo=EVENTO_POR_ESTADO[nuevo], entidad="donacion", id_entidad=d.id_donacion,
        estado_anterior=anterior, estado_nuevo=nuevo, id_actor=id_actor,
        datos={"id_donante": d.id_donante, "nombre_alimento": d.nombre_alimento, **(datos or {})},
    ))
    return d


def ids_donaciones_de(db: Session, id_donante: int) -> list[int]:
    return list(db.scalars(select(Donacion.id_donacion).where(Donacion.id_donante == id_donante)))


def donaciones_vencidas(db: Session) -> list[Donacion]:
    return list(db.scalars(select(Donacion).where(
        Donacion.estado_donacion == "DISPONIBLE", Donacion.fecha_vencimiento <= ahora())))


def donaciones_por_vencer(db: Session, horas: float) -> list[Donacion]:
    limite = ahora() + timedelta(hours=horas)
    return list(db.scalars(select(Donacion).where(
        Donacion.estado_donacion.in_(("DISPONIBLE", "RESERVADA")),
        Donacion.fecha_vencimiento > ahora(),
        Donacion.fecha_vencimiento <= limite,
    )))


# --- Categorías ----------------------------------------------------------------

def listar_categorias(db: Session) -> list[dict]:
    return [{"id_categoria": c.id_categoria, "nombre_categoria": c.nombre_categoria, "descripcion": c.descripcion}
            for c in db.scalars(select(CategoriaAlimento).order_by(CategoriaAlimento.nombre_categoria))]


def _validar_categoria(db: Session, id_categoria: int) -> None:
    if db.get(CategoriaAlimento, id_categoria) is None:
        raise ErrorDominio("La categoría no existe")


def _crear_ubicacion(db: Session, ubicacion: dict) -> UbicacionGeografica:
    u = UbicacionGeografica(
        latitud=ubicacion["lat"], longitud=ubicacion["lon"],
        direccion_referencia=ubicacion.get("direccion_referencia"),
        ciudad=ubicacion.get("ciudad") or "Bogotá",
        departamento=ubicacion.get("departamento") or "Cundinamarca",
    )
    db.add(u)
    db.flush()
    return u


# --- Donaciones ----------------------------------------------------------------

def crear_donacion(db: Session, actor: Actor, datos: dict) -> Donacion:
    _validar_categoria(db, datos["id_categoria"])
    if datos["cantidad"] <= 0:
        raise ErrorDominio("La cantidad debe ser mayor que cero")
    publicacion = datos.get("fecha_publicacion") or ahora()
    if datos["fecha_vencimiento"] <= publicacion:
        raise ErrorDominio("La fecha de vencimiento debe ser posterior a la publicación")
    u = _crear_ubicacion(db, datos["ubicacion"])
    d = Donacion(
        id_donante=actor.id_usuario, id_categoria=datos["id_categoria"], id_ubicacion=u.id_ubicacion,
        nombre_alimento=datos["nombre_alimento"], descripcion=datos.get("descripcion"),
        cantidad=datos["cantidad"], unidad_medida=datos["unidad_medida"],
        fecha_vencimiento=datos["fecha_vencimiento"], fecha_publicacion=publicacion,
        condiciones_recogida=datos.get("condiciones_recogida"), estado_donacion="DISPONIBLE",
    )
    db.add(d)
    db.flush()
    publicar(db, Evento(
        tipo="DONACION_CREADA", entidad="donacion", id_entidad=d.id_donacion,
        estado_anterior=None, estado_nuevo="DISPONIBLE", id_actor=actor.id_usuario,
        datos={"id_donante": d.id_donante, "nombre_alimento": d.nombre_alimento},
    ))
    return d


def _propia(db: Session, id_donacion: int, actor: Actor) -> Donacion:
    d = obtener_donacion(db, id_donacion)
    if d.id_donante != actor.id_usuario:
        raise Prohibido("Solo el donante dueño puede modificar esta donación")
    return d


def actualizar_donacion(db: Session, id_donacion: int, actor: Actor, cambios: dict) -> Donacion:
    d = _propia(db, id_donacion, actor)
    if d.estado_donacion != "DISPONIBLE":
        raise estados.TransicionInvalida("Solo se modifica una donación DISPONIBLE")
    for campo in ("nombre_alimento", "descripcion", "cantidad", "unidad_medida",
                  "fecha_vencimiento", "condiciones_recogida"):
        if cambios.get(campo) is not None:
            setattr(d, campo, cambios[campo])
    if d.cantidad <= 0 or d.fecha_vencimiento <= d.fecha_publicacion:
        raise ErrorDominio("Cantidad o fecha de vencimiento inválidas")
    db.flush()
    return d


def cancelar_donacion(db: Session, id_donacion: int, actor: Actor) -> Donacion:
    _propia(db, id_donacion, actor)
    return transicionar_donacion(db, id_donacion, "CANCELADA", actor.id_usuario)


def donaciones_de(db: Session, id_donante: int) -> list[dict]:
    filas = db.scalars(select(Donacion).where(Donacion.id_donante == id_donante)
                       .order_by(Donacion.id_donacion.desc()))
    nombres = nombres_publicos(db, {id_donante})
    return [donacion_dict(db, d, nombres) for d in filas]


def buscar_disponibles(db: Session, actor: Actor, lat: float | None, lon: float | None,
                       id_necesidad: int | None, id_categoria: int | None,
                       radio_km: float | None, orden: str = "prioridad") -> dict:
    """RF4 + D-07 + D-08: disponibles y vigentes, con distancia y puntaje."""
    if id_necesidad is not None:
        n = db.get(NecesidadAlimentaria, id_necesidad)
        if n is None or n.id_receptor != actor.id_usuario or n.estado_necesidad != "ABIERTA":
            raise ErrorDominio("La necesidad de referencia no es una de tus necesidades abiertas")
        u = db.get(UbicacionGeografica, n.id_ubicacion)
        lat, lon = u.latitud, u.longitud
    if lat is None or lon is None:
        raise ErrorDominio("Indica un punto de búsqueda (lat/lon) o una de tus necesidades abiertas")

    # Urgencia: mayor nivel de las necesidades abiertas del receptor en cada categoría
    urgencias: dict[int, str] = {}
    for n in db.scalars(select(NecesidadAlimentaria).where(
            NecesidadAlimentaria.id_receptor == actor.id_usuario,
            NecesidadAlimentaria.estado_necesidad == "ABIERTA")):
        actual = urgencias.get(n.id_categoria)
        if actual is None or ORDEN_URGENCIA[n.nivel_urgencia] > ORDEN_URGENCIA[actual]:
            urgencias[n.id_categoria] = n.nivel_urgencia

    radio = radio_km or None
    consulta = select(Donacion).where(Donacion.estado_donacion == "DISPONIBLE",
                                      Donacion.fecha_vencimiento > ahora())
    if id_categoria:
        consulta = consulta.where(Donacion.id_categoria == id_categoria)
    donaciones = list(db.scalars(consulta))
    nombres = nombres_publicos(db, {d.id_donante for d in donaciones})
    momento = ahora()
    resultados = []
    for d in donaciones:
        u = db.get(UbicacionGeografica, d.id_ubicacion)
        distancia = busqueda.haversine_km(lat, lon, u.latitud, u.longitud)
        if radio and distancia > radio:
            continue
        horas = (d.fecha_vencimiento - momento).total_seconds() / 3600
        item = donacion_dict(db, d, nombres)
        item["distancia_km"] = round(distancia, 3)
        item["nivel_urgencia"] = urgencias.get(d.id_categoria)
        item["prioridad"] = busqueda.puntaje(urgencias.get(d.id_categoria), distancia, horas, radio)
        resultados.append(item)
    if orden == "distancia":
        resultados.sort(key=lambda r: (r["distancia_km"], -r["prioridad"]["puntaje"]))
    else:
        resultados.sort(key=lambda r: (-r["prioridad"]["puntaje"], r["distancia_km"]))
    return {"punto": {"lat": lat, "lon": lon}, "radio_km": radio, "orden": orden, "resultados": resultados}


# --- Necesidades ---------------------------------------------------------------

def crear_necesidad(db: Session, actor: Actor, datos: dict) -> NecesidadAlimentaria:
    _validar_categoria(db, datos["id_categoria"])
    if datos["nivel_urgencia"] not in estados.NIVELES_URGENCIA:
        raise ErrorDominio("Nivel de urgencia inválido")
    if datos["cantidad_requerida"] <= 0:
        raise ErrorDominio("La cantidad debe ser mayor que cero")
    u = _crear_ubicacion(db, datos["ubicacion"])
    n = NecesidadAlimentaria(
        id_receptor=actor.id_usuario, id_categoria=datos["id_categoria"], id_ubicacion=u.id_ubicacion,
        descripcion=datos["descripcion"], cantidad_requerida=datos["cantidad_requerida"],
        unidad_medida=datos["unidad_medida"], nivel_urgencia=datos["nivel_urgencia"],
        fecha_limite=datos.get("fecha_limite"), estado_necesidad="ABIERTA",
    )
    db.add(n)
    db.flush()
    publicar(db, Evento(
        tipo="NECESIDAD_CREADA", entidad="necesidad", id_entidad=n.id_necesidad,
        estado_anterior=None, estado_nuevo="ABIERTA", id_actor=actor.id_usuario,
        datos={"id_receptor": n.id_receptor, "descripcion": n.descripcion},
    ))
    return n


def necesidades_de(db: Session, id_receptor: int) -> list[dict]:
    filas = db.scalars(select(NecesidadAlimentaria).where(NecesidadAlimentaria.id_receptor == id_receptor)
                       .order_by(NecesidadAlimentaria.id_necesidad.desc()))
    return [necesidad_dict(db, n) for n in filas]


def cambiar_estado_necesidad(db: Session, id_necesidad: int, nuevo: str, actor: Actor) -> NecesidadAlimentaria:
    n = db.get(NecesidadAlimentaria, id_necesidad)
    if n is None:
        raise NoEncontrado("Necesidad no encontrada")
    if n.id_receptor != actor.id_usuario:
        raise Prohibido("Solo puedes modificar tus propias necesidades")
    estados.validar("necesidad", n.estado_necesidad, nuevo)
    anterior = n.estado_necesidad
    n.estado_necesidad = nuevo
    db.flush()
    publicar(db, Evento(
        tipo=f"NECESIDAD_{'CERRADA' if nuevo == 'CERRADA' else 'CANCELADA'}", entidad="necesidad",
        id_entidad=n.id_necesidad, estado_anterior=anterior, estado_nuevo=nuevo, id_actor=actor.id_usuario,
        datos={"id_receptor": n.id_receptor, "descripcion": n.descripcion},
    ))
    return n

