"""Consultas de catalog-geo-service (S4-10): CRUD de donaciones y necesidades y búsqueda geoespacial.

La transacción la confirma quien llama (db.commit()). Todas las consultas son parametrizadas.
D-01: `transicionar_donacion` es el único punto que cambia `estado_donacion`.
"""
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import config
from .errores import ErrorDominio, NoEncontrado, Prohibido, TransicionInvalida
from .modelos import CategoriaAlimento, Donacion, NecesidadAlimentaria, UbicacionGeografica

TRANSICIONES_DONACION = {
    "DISPONIBLE": {"RESERVADA", "CANCELADA", "VENCIDA"},
    "RESERVADA": {"DISPONIBLE", "VENCIDA", "ENTREGADA"},
}
CAMPOS_DONACION = ("nombre_alimento", "descripcion", "cantidad", "unidad_medida", "fecha_vencimiento",
                   "condiciones_recogida", "id_categoria")
CAMPOS_NECESIDAD = ("descripcion", "cantidad_requerida", "unidad_medida", "nivel_urgencia", "fecha_limite")


# --- Ubicaciones y categorías --------------------------------------------------

def crear_ubicacion(db: Session, lat: float, lon: float, ciudad: str, departamento: str,
                    direccion: str | None = None) -> UbicacionGeografica:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErrorDominio("Coordenadas fuera de rango")
    u = UbicacionGeografica(direccion_referencia=direccion, ciudad=ciudad, departamento=departamento,
                            coordenada_geografica=WKTElement(f"POINT({lon} {lat})", srid=4326))
    db.add(u)
    db.flush()
    return u


def coordenadas(db: Session, id_ubicacion: int) -> tuple[float, float]:
    """(lat, lon) de una ubicación."""
    fila = db.execute(text("SELECT ST_Y(coordenada_geografica::geometry), ST_X(coordenada_geografica::geometry) "
                           "FROM ubicacion_geografica WHERE id_ubicacion = :id"), {"id": id_ubicacion}).one()
    return float(fila[0]), float(fila[1])


def listar_categorias(db: Session) -> list[CategoriaAlimento]:
    return list(db.scalars(select(CategoriaAlimento).order_by(CategoriaAlimento.nombre_categoria)))


def _validar_categoria(db: Session, id_categoria: int) -> None:
    if db.get(CategoriaAlimento, id_categoria) is None:
        raise ErrorDominio("La categoría no existe")


# --- Donaciones ----------------------------------------------------------------

def crear_donacion(db: Session, id_donante: int, *, nombre_alimento: str, id_categoria: int, cantidad,
                   unidad_medida: str, lat: float, lon: float, ciudad: str, departamento: str,
                   fecha_vencimiento: datetime | None = None, descripcion: str | None = None,
                   condiciones_recogida: str | None = None, direccion: str | None = None,
                   id_necesidad: int | None = None) -> Donacion:
    _validar_categoria(db, id_categoria)
    if Decimal(str(cantidad)) <= 0:
        raise ErrorDominio("La cantidad debe ser mayor que cero")
    if id_necesidad is not None:  # D-11: se ofrece para una solicitud abierta
        n = db.get(NecesidadAlimentaria, id_necesidad)
        if n is None:
            raise NoEncontrado("Necesidad no encontrada")
        if n.estado_necesidad != "ABIERTA":
            raise TransicionInvalida(f"La necesidad está {n.estado_necesidad} y ya no recibe ofertas")
    u = crear_ubicacion(db, lat, lon, ciudad, departamento, direccion)
    d = Donacion(id_donante=id_donante, id_categoria=id_categoria, id_ubicacion=u.id_ubicacion,
                 nombre_alimento=nombre_alimento, descripcion=descripcion, cantidad=cantidad,
                 unidad_medida=unidad_medida, fecha_vencimiento=fecha_vencimiento,
                 condiciones_recogida=condiciones_recogida, id_necesidad=id_necesidad)
    db.add(d)
    db.flush()
    db.refresh(d)
    return d


def obtener_donacion(db: Session, id_donacion: int, bloquear: bool = False) -> Donacion:
    d = db.get(Donacion, id_donacion, with_for_update=bloquear)
    if d is None:
        raise NoEncontrado("Donación no encontrada")
    return d


def listar_donaciones(db: Session, id_donante: int | None = None, estado: str | None = None) -> list[Donacion]:
    consulta = select(Donacion).order_by(Donacion.id_donacion.desc())
    if id_donante is not None:
        consulta = consulta.where(Donacion.id_donante == id_donante)
    if estado:
        consulta = consulta.where(Donacion.estado_donacion == estado)
    return list(db.scalars(consulta))


def actualizar_donacion(db: Session, id_donacion: int, id_donante: int, **cambios) -> Donacion:
    no_permitidos = set(cambios) - set(CAMPOS_DONACION)
    if no_permitidos:
        raise ErrorDominio(f"Campos no editables: {', '.join(sorted(no_permitidos))}")
    d = obtener_donacion(db, id_donacion, bloquear=True)
    if d.id_donante != id_donante:
        raise Prohibido("Solo el donante dueño modifica la donación")
    if d.estado_donacion != "DISPONIBLE":
        raise TransicionInvalida(f"Solo se modifica una donación DISPONIBLE (está {d.estado_donacion})")
    if "id_categoria" in cambios:
        _validar_categoria(db, cambios["id_categoria"])
    for campo, valor in cambios.items():
        setattr(d, campo, valor)
    db.flush()
    return d


def receptor_exclusivo(db: Session, d: Donacion) -> int | None:
    """D-11: receptor que tiene la exclusiva de una donación ofrecida para su necesidad, mientras siga ABIERTA."""
    if d.id_necesidad is None:
        return None
    n = db.get(NecesidadAlimentaria, d.id_necesidad)
    return n.id_receptor if n is not None and n.estado_necesidad == "ABIERTA" else None


def transicionar_donacion(db: Session, id_donacion: int, nuevo: str,
                          id_receptor: int | None = None) -> tuple[str, Donacion]:
    """Único punto que cambia el estado (D-01). Devuelve (estado_anterior, donación).

    Para RESERVADA, `id_receptor` es quien reserva: una donación ofrecida para una necesidad abierta
    solo la reserva el receptor de esa necesidad (D-11).
    """
    d = obtener_donacion(db, id_donacion, bloquear=True)
    if nuevo not in TRANSICIONES_DONACION.get(d.estado_donacion, set()):
        raise TransicionInvalida(f"Transición de donación no permitida: {d.estado_donacion} → {nuevo}")
    if nuevo == "RESERVADA" and d.fecha_vencimiento is not None and d.fecha_vencimiento <= db.scalar(func.now()):
        raise TransicionInvalida("La donación ya venció y no se puede reservar")
    if nuevo == "RESERVADA":
        exclusivo = receptor_exclusivo(db, d)
        if exclusivo is not None and exclusivo != id_receptor:
            raise TransicionInvalida("Esta donación fue ofrecida para la necesidad de otro receptor")
    anterior = d.estado_donacion
    d.estado_donacion = nuevo
    db.flush()
    return anterior, d


def cancelar_donacion(db: Session, id_donacion: int, id_donante: int) -> Donacion:
    if obtener_donacion(db, id_donacion).id_donante != id_donante:
        raise Prohibido("Solo el donante dueño cancela la donación")
    return transicionar_donacion(db, id_donacion, "CANCELADA")[1]


def vencer_donaciones(db: Session, ahora: datetime | None = None) -> list[int]:
    """Tarea RF8: pasa a VENCIDA las DISPONIBLE con fecha cumplida. Idempotente; una sola sentencia."""
    filas = db.execute(text("""
        UPDATE donacion SET estado_donacion = 'VENCIDA'
        WHERE estado_donacion = 'DISPONIBLE' AND fecha_vencimiento <= coalesce(:ahora, now())
        RETURNING id_donacion"""), {"ahora": ahora})
    return sorted(f[0] for f in filas)


# --- Necesidades ---------------------------------------------------------------

def crear_necesidad(db: Session, id_receptor: int, *, descripcion: str, id_categoria: int, cantidad_requerida,
                    unidad_medida: str, nivel_urgencia: str, lat: float, lon: float, ciudad: str,
                    departamento: str, fecha_limite: datetime | None = None,
                    direccion: str | None = None) -> NecesidadAlimentaria:
    _validar_categoria(db, id_categoria)
    if nivel_urgencia not in config.VALOR_URGENCIA:
        raise ErrorDominio("Nivel de urgencia inválido")
    if Decimal(str(cantidad_requerida)) <= 0:
        raise ErrorDominio("La cantidad debe ser mayor que cero")
    u = crear_ubicacion(db, lat, lon, ciudad, departamento, direccion)
    n = NecesidadAlimentaria(id_receptor=id_receptor, id_categoria=id_categoria, id_ubicacion=u.id_ubicacion,
                             descripcion=descripcion, cantidad_requerida=cantidad_requerida,
                             unidad_medida=unidad_medida, nivel_urgencia=nivel_urgencia, fecha_limite=fecha_limite)
    db.add(n)
    db.flush()
    db.refresh(n)
    return n


def _necesidad_propia(db: Session, id_necesidad: int, id_receptor: int) -> NecesidadAlimentaria:
    n = db.get(NecesidadAlimentaria, id_necesidad, with_for_update=True)
    if n is None:
        raise NoEncontrado("Necesidad no encontrada")
    if n.id_receptor != id_receptor:
        raise Prohibido("Un receptor solo modifica sus propias necesidades")
    return n


def listar_necesidades(db: Session, id_receptor: int | None = None, estado: str | None = None):
    consulta = select(NecesidadAlimentaria).order_by(NecesidadAlimentaria.id_necesidad.desc())
    if id_receptor is not None:
        consulta = consulta.where(NecesidadAlimentaria.id_receptor == id_receptor)
    if estado:
        consulta = consulta.where(NecesidadAlimentaria.estado_necesidad == estado)
    return list(db.scalars(consulta))


def ajustar_necesidad(db: Session, id_necesidad: int, id_receptor: int, **cambios) -> NecesidadAlimentaria:
    no_permitidos = set(cambios) - set(CAMPOS_NECESIDAD)
    if no_permitidos:
        raise ErrorDominio(f"Campos no editables: {', '.join(sorted(no_permitidos))}")
    n = _necesidad_propia(db, id_necesidad, id_receptor)
    if n.estado_necesidad != "ABIERTA":
        raise TransicionInvalida(f"La necesidad está {n.estado_necesidad}")
    if "nivel_urgencia" in cambios and cambios["nivel_urgencia"] not in config.VALOR_URGENCIA:
        raise ErrorDominio("Nivel de urgencia inválido")
    for campo, valor in cambios.items():
        setattr(n, campo, valor)
    db.flush()
    return n


def cerrar_necesidad(db: Session, id_necesidad: int, id_receptor: int, estado: str = "CERRADA"):
    if estado not in ("CERRADA", "CANCELADA"):
        raise ErrorDominio("El cierre debe ser CERRADA o CANCELADA")
    n = _necesidad_propia(db, id_necesidad, id_receptor)
    if n.estado_necesidad != "ABIERTA":
        raise TransicionInvalida(f"La necesidad ya está {n.estado_necesidad}")
    n.estado_necesidad = estado
    db.flush()
    return n


# --- Búsqueda geoespacial con prioridad (RF4, D-07, D-08) ----------------------

SQL_BUSQUEDA = """
WITH punto AS (
  SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g
), urgencia AS (
  SELECT id_categoria,
         max(CASE nivel_urgencia WHEN 'BAJA' THEN 0.25 WHEN 'MEDIA' THEN 0.5
                                 WHEN 'ALTA' THEN 0.75 WHEN 'CRITICA' THEN 1.0 END) AS valor,
         max(nivel_urgencia) AS nivel
  FROM necesidad_alimentaria
  WHERE id_receptor = :id_receptor AND estado_necesidad = 'ABIERTA'
  GROUP BY id_categoria
), candidatas AS (
  SELECT d.id_donacion, d.id_donante, d.id_categoria, c.nombre_categoria, d.nombre_alimento, d.cantidad,
         d.unidad_medida, d.fecha_vencimiento, d.condiciones_recogida, u.direccion_referencia, u.ciudad,
         d.id_necesidad, nd.id_necesidad IS NOT NULL AS para_mi,
         u.departamento, ST_Y(u.coordenada_geografica::geometry) AS lat, ST_X(u.coordenada_geografica::geometry) AS lon,
         ST_Distance(u.coordenada_geografica, p.g) AS distancia_m,
         coalesce(ur.valor, 0) AS urgencia, ur.nivel AS nivel_urgencia,
         greatest(0, 1 - ST_Distance(u.coordenada_geografica, p.g) / :radio_m) AS cercania,
         CASE WHEN d.fecha_vencimiento IS NULL THEN 0
              ELSE greatest(0, 1 - extract(epoch FROM d.fecha_vencimiento - :ahora) / 3600 / :ventana_h) END
           AS vencimiento
  FROM donacion d
  JOIN ubicacion_geografica u ON u.id_ubicacion = d.id_ubicacion
  JOIN categoria_alimento c ON c.id_categoria = d.id_categoria
  CROSS JOIN punto p
  LEFT JOIN urgencia ur ON ur.id_categoria = d.id_categoria
  LEFT JOIN necesidad_alimentaria nd ON nd.id_necesidad = d.id_necesidad AND nd.estado_necesidad = 'ABIERTA'
  WHERE d.estado_donacion = 'DISPONIBLE'
    AND (d.fecha_vencimiento IS NULL OR d.fecha_vencimiento > :ahora)
    AND (nd.id_necesidad IS NULL OR nd.id_receptor = :id_receptor)  -- D-11: exclusiva del receptor que la pidió
    AND ST_DWithin(u.coordenada_geografica, p.g, :radio_m)
    {filtros}
)
SELECT *, round((:w_u * urgencia + :w_c * cercania + :w_v * vencimiento)::numeric, 4) AS puntaje
FROM candidatas
ORDER BY {orden}
LIMIT :limite
"""


def buscar_donaciones(db: Session, *, id_receptor: int, lat: float | None = None, lon: float | None = None,
                      id_necesidad: int | None = None, radio_m: float | None = None,
                      id_categoria: int | None = None, cantidad_minima=None, vence_antes: datetime | None = None,
                      orden: str = "distancia", ahora: datetime | None = None, limite: int = 100) -> list[dict]:
    """Donaciones DISPONIBLES y vigentes cerca de un punto, con distancia en metros y puntaje D-08.

    El punto es (lat, lon) o la ubicación de una necesidad ABIERTA del receptor (D-07).
    orden = "distancia" (más cercana primero) o "prioridad" (mayor puntaje primero).
    """
    if id_necesidad is not None:
        n = db.get(NecesidadAlimentaria, id_necesidad)
        if n is None or n.id_receptor != id_receptor or n.estado_necesidad != "ABIERTA":
            raise ErrorDominio("La necesidad de referencia no es una necesidad abierta del receptor")
        lat, lon = coordenadas(db, n.id_ubicacion)
    if lat is None or lon is None:
        raise ErrorDominio("Indica un punto (lat, lon) o una necesidad abierta como referencia")
    if orden not in ("distancia", "prioridad"):
        raise ErrorDominio("El orden debe ser distancia o prioridad")

    filtros, parametros = [], {}
    if id_categoria is not None:
        filtros.append("AND d.id_categoria = :id_categoria")
        parametros["id_categoria"] = id_categoria
    if cantidad_minima is not None:
        filtros.append("AND d.cantidad >= :cantidad_minima")
        parametros["cantidad_minima"] = cantidad_minima
    if vence_antes is not None:
        filtros.append("AND d.fecha_vencimiento <= :vence_antes")
        parametros["vence_antes"] = vence_antes
    sql = SQL_BUSQUEDA.format(
        filtros="\n    ".join(filtros),
        orden="para_mi DESC, " + ("distancia_m, puntaje DESC" if orden == "distancia" else "puntaje DESC, distancia_m"),
    )
    parametros.update({
        "lat": lat, "lon": lon, "id_receptor": id_receptor, "radio_m": radio_m or config.RADIO_M_DEFECTO,
        "ventana_h": config.VENTANA_VENCIMIENTO_H, "ahora": ahora or db.scalar(func.now()),
        "w_u": config.PESO_URGENCIA, "w_c": config.PESO_CERCANIA, "w_v": config.PESO_VENCIMIENTO, "limite": limite,
    })
    return [dict(f) for f in db.execute(text(sql), parametros).mappings()]


# --- Lecturas con detalle (para la API) ----------------------------------------

SQL_DETALLE_DONACION = """
SELECT d.id_donacion, d.id_donante, d.id_categoria, c.nombre_categoria AS categoria, d.nombre_alimento,
       d.descripcion, d.cantidad, d.unidad_medida, d.fecha_vencimiento, d.fecha_publicacion,
       d.condiciones_recogida, d.estado_donacion, u.direccion_referencia, u.ciudad, u.departamento,
       ST_Y(u.coordenada_geografica::geometry) AS lat, ST_X(u.coordenada_geografica::geometry) AS lon,
       d.id_necesidad, nd.descripcion AS necesidad,
       CASE WHEN nd.estado_necesidad = 'ABIERTA' THEN nd.id_receptor END AS id_receptor_exclusivo
FROM donacion d
JOIN categoria_alimento c ON c.id_categoria = d.id_categoria
JOIN ubicacion_geografica u ON u.id_ubicacion = d.id_ubicacion
LEFT JOIN necesidad_alimentaria nd ON nd.id_necesidad = d.id_necesidad
WHERE {filtro}
ORDER BY d.id_donacion DESC
LIMIT 500
"""
SQL_DETALLE_NECESIDAD = """
SELECT n.id_necesidad, n.id_receptor, n.id_categoria, c.nombre_categoria AS categoria, n.descripcion,
       n.cantidad_requerida, n.unidad_medida, n.nivel_urgencia, n.fecha_limite, n.estado_necesidad,
       u.direccion_referencia, u.ciudad, u.departamento,
       ST_Y(u.coordenada_geografica::geometry) AS lat, ST_X(u.coordenada_geografica::geometry) AS lon,
       (SELECT count(*) FROM donacion o WHERE o.id_necesidad = n.id_necesidad
          AND o.estado_donacion IN ('DISPONIBLE', 'RESERVADA', 'ENTREGADA')) AS ofertas
FROM necesidad_alimentaria n
JOIN categoria_alimento c ON c.id_categoria = n.id_categoria
JOIN ubicacion_geografica u ON u.id_ubicacion = n.id_ubicacion
WHERE {filtro}
ORDER BY n.id_necesidad DESC
"""


def detalle_donaciones(db: Session, ids: list[int] | None = None, id_donante: int | None = None,
                       estado: str | None = None) -> list[dict]:
    filtros, params = ["TRUE"], {}
    if ids is not None:
        filtros.append("d.id_donacion = ANY(:ids)")
        params["ids"] = list(ids)
    if id_donante is not None:
        filtros.append("d.id_donante = :id_donante")
        params["id_donante"] = id_donante
    if estado:
        filtros.append("d.estado_donacion = :estado")
        params["estado"] = estado
    sql = SQL_DETALLE_DONACION.format(filtro=" AND ".join(filtros))
    return [dict(f) for f in db.execute(text(sql), params).mappings()]


def detalle_necesidades(db: Session, ids: list[int] | None = None, id_receptor: int | None = None) -> list[dict]:
    filtros, params = ["TRUE"], {}
    if ids is not None:
        filtros.append("n.id_necesidad = ANY(:ids)")
        params["ids"] = list(ids)
    if id_receptor is not None:
        filtros.append("n.id_receptor = :id_receptor")
        params["id_receptor"] = id_receptor
    return [dict(f) for f in db.execute(text(SQL_DETALLE_NECESIDAD.format(filtro=" AND ".join(filtros))),
                                        params).mappings()]


SQL_SOLICITUDES = """
WITH punto AS (
  SELECT CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL
              ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision), CAST(:lat AS double precision)),
                              4326)::geography END AS g
)
SELECT n.id_necesidad, n.id_categoria, c.nombre_categoria AS categoria, n.descripcion, n.cantidad_requerida,
       n.unidad_medida, n.nivel_urgencia, n.fecha_limite, u.ciudad, u.departamento,
       ST_Y(u.coordenada_geografica::geometry) AS lat, ST_X(u.coordenada_geografica::geometry) AS lon,
       ST_Distance(u.coordenada_geografica, p.g) AS distancia_m,
       (SELECT count(*) FROM donacion o WHERE o.id_necesidad = n.id_necesidad
          AND o.estado_donacion IN ('DISPONIBLE', 'RESERVADA', 'ENTREGADA')) AS ofertas
FROM necesidad_alimentaria n
JOIN categoria_alimento c ON c.id_categoria = n.id_categoria
JOIN ubicacion_geografica u ON u.id_ubicacion = n.id_ubicacion
CROSS JOIN punto p
WHERE n.estado_necesidad = 'ABIERTA'
  AND (n.fecha_limite IS NULL OR n.fecha_limite > now())
  AND (p.g IS NULL OR ST_DWithin(u.coordenada_geografica, p.g, :radio_m))
  AND (CAST(:id_categoria AS smallint) IS NULL OR n.id_categoria = CAST(:id_categoria AS smallint))
ORDER BY CASE n.nivel_urgencia WHEN 'CRITICA' THEN 0 WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
         distancia_m NULLS LAST, n.fecha_limite NULLS LAST, n.id_necesidad
LIMIT 200
"""


def solicitudes_abiertas(db: Session, lat: float | None = None, lon: float | None = None,
                         radio_m: float | None = None, id_categoria: int | None = None) -> list[dict]:
    """D-11: necesidades ABIERTAS y vigentes que ven los donantes, la más urgente primero.

    No incluye al receptor ni su dirección escrita (política de datos): solo ciudad, punto y lo que se necesita.
    """
    if (lat is None) != (lon is None):
        raise ErrorDominio("Indica latitud y longitud juntas")
    parametros = {"lat": lat, "lon": lon, "radio_m": radio_m or config.RADIO_M_DEFECTO, "id_categoria": id_categoria}
    return [dict(f) for f in db.execute(text(SQL_SOLICITUDES), parametros).mappings()]


def donaciones_por_vencer(db: Session, horas: float, ahora: datetime | None = None) -> list[dict]:
    """DISPONIBLES o RESERVADAS que vencen dentro de `horas` (aviso RF8, D-09)."""
    return [dict(f) for f in db.execute(text("""
        SELECT id_donacion, id_donante, nombre_alimento, fecha_vencimiento, estado_donacion FROM donacion
        WHERE estado_donacion IN ('DISPONIBLE', 'RESERVADA')
          AND fecha_vencimiento > coalesce(:ahora, now())
          AND fecha_vencimiento <= coalesce(:ahora, now()) + make_interval(secs => :segundos)
        ORDER BY fecha_vencimiento"""), {"ahora": ahora, "segundos": horas * 3600}).mappings()]


def crear_categoria(db: Session, nombre: str, descripcion: str | None = None) -> CategoriaAlimento:
    siguiente = (db.scalar(select(func.max(CategoriaAlimento.id_categoria))) or 0) + 1
    c = CategoriaAlimento(id_categoria=siguiente, nombre_categoria=nombre.strip(), descripcion=descripcion)
    db.add(c)
    db.flush()
    return c


def actualizar_categoria(db: Session, id_categoria: int, nombre: str | None = None,
                         descripcion: str | None = None) -> CategoriaAlimento:
    c = db.get(CategoriaAlimento, id_categoria)
    if c is None:
        raise NoEncontrado("Categoría no encontrada")
    if nombre:
        c.nombre_categoria = nombre.strip()
    if descripcion is not None:
        c.descripcion = descripcion
    db.flush()
    return c
