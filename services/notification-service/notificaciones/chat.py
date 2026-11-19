"""Chat entre donante y receptor (D-12): abrir y cerrar conversaciones por eventos, enviar y leer mensajes.

La transacción la confirma quien llama (db.commit()).
"""
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .errores import ErrorDominio, NoEncontrado, TransicionInvalida
from .modelos import Conversacion, Mensaje

MAX_TEXTO = 1000


# --- Ciclo de vida (lo mueven los eventos de catalog y fulfillment) ------------

def abrir(db: Session, id_donacion: int, id_donante: int, id_receptor: int, nombre_alimento: str,
          origen: str) -> Conversacion:
    """Crea la conversación de (donación, receptor) o la reabre si ya existía. Idempotente."""
    sentencia = insert(Conversacion).values(
        id_donacion=id_donacion, id_donante=id_donante, id_receptor=id_receptor,
        nombre_alimento=nombre_alimento[:120], origen=origen,
    ).on_conflict_do_update(
        index_elements=["id_donacion", "id_receptor"],
        set_={"estado_conversacion": "ABIERTA", "fecha_cierre": None},
    ).returning(Conversacion.id_conversacion)
    id_conversacion = db.execute(sentencia).scalar_one()
    db.flush()
    return db.get(Conversacion, id_conversacion, populate_existing=True)


def cerrar(db: Session, id_donacion: int, id_receptor: int | None = None) -> int:
    """Cierra la conversación de un receptor, o todas las de la donación si no se indica. Devuelve cuántas.

    Cuando termina solo la reserva de un receptor, la conversación nacida de una OFERTA sigue abierta:
    la donación continúa apartada para él (D-11) y puede volver a reservarla.
    """
    filtro = "id_donacion = :d AND estado_conversacion = 'ABIERTA'"
    parametros = {"d": id_donacion}
    if id_receptor is not None:
        filtro += " AND id_receptor = :r AND origen <> 'OFERTA'"
        parametros["r"] = id_receptor
    return db.execute(text(f"UPDATE conversacion SET estado_conversacion = 'CERRADA', fecha_cierre = now() "
                           f"WHERE {filtro}"), parametros).rowcount


# --- Uso por los participantes ---------------------------------------------------

def _propia(db: Session, id_conversacion: int, id_usuario: int, bloquear: bool = False) -> Conversacion:
    c = db.get(Conversacion, id_conversacion, with_for_update=bloquear)
    if c is None or id_usuario not in (c.id_donante, c.id_receptor):  # a otros: como si no existiera
        raise NoEncontrado("Conversación no encontrada")
    return c


SQL_MIAS = """
SELECT c.*, CASE WHEN c.id_donante = :u THEN c.id_receptor ELSE c.id_donante END AS id_contraparte,
       CASE WHEN c.id_donante = :u THEN 'DONANTE' ELSE 'RECEPTOR' END AS mi_papel,
       u.texto AS ultimo_texto, u.fecha_envio AS ultima_fecha, u.id_autor AS ultimo_autor,
       (SELECT count(*) FROM mensaje m WHERE m.id_conversacion = c.id_conversacion AND m.id_autor <> :u
          AND m.id_mensaje > CASE WHEN c.id_donante = :u THEN c.ultimo_leido_donante
                                  ELSE c.ultimo_leido_receptor END) AS no_leidos
FROM conversacion c
LEFT JOIN LATERAL (SELECT texto, fecha_envio, id_autor FROM mensaje m
                   WHERE m.id_conversacion = c.id_conversacion ORDER BY id_mensaje DESC LIMIT 1) u ON TRUE
WHERE :u IN (c.id_donante, c.id_receptor)
ORDER BY c.estado_conversacion, coalesce(u.fecha_envio, c.fecha_creacion) DESC
LIMIT 200
"""


def mias(db: Session, id_usuario: int) -> list[dict]:
    return [dict(f) for f in db.execute(text(SQL_MIAS), {"u": id_usuario}).mappings()]


def contar_no_leidos(db: Session, id_usuario: int) -> int:
    return db.scalar(text("""
        SELECT count(*) FROM mensaje m JOIN conversacion c ON c.id_conversacion = m.id_conversacion
        WHERE :u IN (c.id_donante, c.id_receptor) AND m.id_autor <> :u
          AND m.id_mensaje > CASE WHEN c.id_donante = :u THEN c.ultimo_leido_donante ELSE c.ultimo_leido_receptor END
    """), {"u": id_usuario})


def mensajes(db: Session, id_conversacion: int, id_usuario: int, despues_de: int = 0) -> tuple[Conversacion, list]:
    c = _propia(db, id_conversacion, id_usuario)
    lista = list(db.scalars(select(Mensaje).where(Mensaje.id_conversacion == id_conversacion,
                                                  Mensaje.id_mensaje > despues_de)
                            .order_by(Mensaje.id_mensaje).limit(500)))
    return c, lista


def enviar(db: Session, id_conversacion: int, id_usuario: int, texto: str) -> Mensaje:
    texto = (texto or "").strip()
    if not texto:
        raise ErrorDominio("El mensaje está vacío")
    if len(texto) > MAX_TEXTO:
        raise ErrorDominio(f"El mensaje supera {MAX_TEXTO} caracteres")
    c = _propia(db, id_conversacion, id_usuario, bloquear=True)
    if c.estado_conversacion != "ABIERTA":
        raise TransicionInvalida("La conversación está cerrada: la reserva o la donación ya terminó")
    m = Mensaje(id_conversacion=id_conversacion, id_autor=id_usuario, texto=texto)
    db.add(m)
    db.flush()
    db.refresh(m)
    _marcar(c, id_usuario, m.id_mensaje)  # lo propio cuenta como leído
    db.flush()
    return m


def _marcar(c: Conversacion, id_usuario: int, hasta: int) -> None:
    if id_usuario == c.id_donante:
        c.ultimo_leido_donante = max(c.ultimo_leido_donante, hasta)
    else:
        c.ultimo_leido_receptor = max(c.ultimo_leido_receptor, hasta)


def leer(db: Session, id_conversacion: int, id_usuario: int) -> Conversacion:
    """Marca como leído todo lo recibido hasta ahora."""
    c = _propia(db, id_conversacion, id_usuario, bloquear=True)
    ultimo = db.scalar(select(func.max(Mensaje.id_mensaje)).where(Mensaje.id_conversacion == id_conversacion)) or 0
    _marcar(c, id_usuario, ultimo)
    db.flush()
    return c


# --- Eventos que abren y cierran conversaciones ---------------------------------

def aplicar_evento(db: Session, tipo: str, id_entidad: int, d: dict) -> None:
    """Abre la conversación cuando hay contraparte y la cierra cuando la reserva o la donación terminan."""
    donante, receptor, alimento = d.get("id_donante"), d.get("id_receptor"), d.get("nombre_alimento") or "Donación"
    match tipo:
        case "RESERVA_CREADA" if donante and receptor:
            abrir(db, d["id_donacion"], donante, receptor, alimento, "RESERVA")
        case "DONACION_CREADA" if donante and receptor:  # D-11: ofrecida para la solicitud del receptor
            abrir(db, id_entidad, donante, receptor, alimento, "OFERTA")
        case "RESERVA_CANCELADA" | "RESERVA_EXPIRADA" if receptor:
            cerrar(db, d["id_donacion"], receptor)
        case "DONACION_ENTREGADA" | "DONACION_CANCELADA" | "DONACION_VENCIDA":
            cerrar(db, id_entidad)
