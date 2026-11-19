"""Casos de uso de fulfillment-service: reservas, entregas y tareas, coordinados con catalog (D-01, D-02).

Patrón de cada operación: (1) cambio local y commit, (2) petición a catalog, (3) si catalog rechaza o no
responde, compensación local. Los eventos se publican al final, solo con lo que quedó confirmado.
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from redalimenta_comun.eventos import Lote
from redalimenta_comun.seguridad import Actor

from . import config
from . import repositorio as repo
from .catalogo_cliente import ClienteCatalogo
from .errores import Conflicto, Prohibido, ServicioNoDisponible, TransicionInvalida
from .modelos import AvisoVencimiento, Entrega, Reserva

log = logging.getLogger("redalimenta.fulfillment")


def _iso(v: datetime | None):
    return None if v is None else v.isoformat()


def _contexto(r: Reserva, d: dict) -> dict:
    return {"id_reserva": r.id_reserva, "id_donacion": r.id_donacion, "id_receptor": r.id_receptor,
            "id_donante": d["id_donante"], "nombre_alimento": d["nombre_alimento"]}


def _vigente(d: dict) -> bool:
    vence = d.get("fecha_vencimiento")
    return vence is None or datetime.fromisoformat(vence) > datetime.now(UTC)


def _partes(cat: ClienteCatalogo, r: Reserva, actor: Actor) -> tuple[dict, bool, bool]:
    d = cat.donacion(r.id_donacion)
    return d, d["id_donante"] == actor.id_usuario, r.id_receptor == actor.id_usuario


def _liberar(cat: ClienteCatalogo, origen: str, d: dict, id_actor: int | None, motivo: str) -> None:
    """Devuelve la donación a DISPONIBLE (o VENCIDA si ya pasó su fecha). Si catalog falla, la tarea de
    conciliación lo corregirá después; la operación local ya quedó confirmada."""
    if d["estado_donacion"] != "RESERVADA":
        return
    try:
        cat.transicionar(d["id_donacion"], "DISPONIBLE" if _vigente(d) else "VENCIDA", id_actor, {"motivo": motivo})
    except (ServicioNoDisponible, TransicionInvalida) as error:
        log.warning("%s: no se pudo liberar la donación %s (%s); quedará para conciliar",
                    origen, d["id_donacion"], error)


# --- Reservas ------------------------------------------------------------------

def reservar(db: Session, lote: Lote, cat: ClienteCatalogo, actor: Actor, id_donacion: int) -> Reserva:
    d = cat.donacion(id_donacion)  # 404 si no existe; 503 si catalog no responde
    if d["estado_donacion"] != "DISPONIBLE":
        raise Conflicto(f"La donación está {d['estado_donacion']}")
    if d.get("id_receptor_exclusivo") not in (None, actor.id_usuario):  # D-11 (catalog también lo valida)
        raise Conflicto("Esta donación fue ofrecida para la necesidad de otro receptor")
    r = repo.reservar(db, id_donacion, actor.id_usuario)  # D-02: gana quien inserta primero (409 al resto)
    db.commit()
    lote.agregar("RESERVA_CREADA", "reserva", r.id_reserva, None, "PENDIENTE", actor.id_usuario,
                 **_contexto(r, d), fecha_expiracion=_iso(r.fecha_expiracion))
    try:
        cat.transicionar(id_donacion, "RESERVADA", actor.id_usuario,
                         {"id_receptor": actor.id_usuario, "id_reserva": r.id_reserva,
                          "fecha_expiracion": _iso(r.fecha_expiracion)})
    except (TransicionInvalida, ServicioNoDisponible) as error:
        # Compensación D-02: catalog rechazó (o no respondió) → la reserva queda CANCELADA
        repo.cancelar_reserva(db, r.id_reserva)
        db.commit()
        lote.agregar("RESERVA_CANCELADA", "reserva", r.id_reserva, "PENDIENTE", "CANCELADA", None,
                     **_contexto(r, d), motivo=str(error))
        lote.publicar()
        if isinstance(error, ServicioNoDisponible):
            raise
        raise Conflicto(f"No se pudo reservar: {error}") from error
    lote.publicar()
    return r


def confirmar(db: Session, lote: Lote, cat: ClienteCatalogo, actor: Actor, id_reserva: int) -> Reserva:
    r = repo.obtener_reserva(db, id_reserva)
    d, es_donante, _ = _partes(cat, r, actor)
    if not es_donante:
        raise Prohibido("Solo el donante de la donación confirma la reserva")
    e = repo.confirmar_reserva(db, id_reserva)
    db.commit()
    ctx = _contexto(r, d)
    lote.agregar("RESERVA_CONFIRMADA", "reserva", r.id_reserva, "PENDIENTE", "CONFIRMADA", actor.id_usuario, **ctx)
    lote.agregar("ENTREGA_PROGRAMADA", "entrega", e.id_entrega, None, "PROGRAMADA", actor.id_usuario,
                 id_entrega=e.id_entrega, **ctx)
    lote.publicar()
    return r


def cancelar(db: Session, lote: Lote, cat: ClienteCatalogo, actor: Actor, id_reserva: int) -> Reserva:
    r = repo.obtener_reserva(db, id_reserva)
    d, es_donante, es_receptor = _partes(cat, r, actor)
    if not (es_donante or es_receptor or actor.rol == "ADMINISTRADOR"):
        raise Prohibido("No participas en esta reserva")
    anterior = r.estado_reserva
    e = repo.entrega_de_reserva(db, id_reserva)
    entrega_antes = e.estado_entrega if e else None
    repo.cancelar_reserva(db, id_reserva)
    db.commit()
    ctx = _contexto(r, d)
    lote.agregar("RESERVA_CANCELADA", "reserva", r.id_reserva, anterior, "CANCELADA", actor.id_usuario, **ctx,
                 por="donante" if es_donante else "receptor" if es_receptor else "administrador")
    if e is not None and entrega_antes != e.estado_entrega:
        lote.agregar("ENTREGA_CANCELADA", "entrega", e.id_entrega, entrega_antes, "CANCELADA", actor.id_usuario,
                     id_entrega=e.id_entrega, **ctx)
    _liberar(cat, "cancelar", d, actor.id_usuario, "reserva cancelada")
    lote.publicar()
    return r


def confirmar_entrega(db: Session, lote: Lote, cat: ClienteCatalogo, actor: Actor, id_entrega: int,
                      estado: str, observaciones: str | None) -> Entrega:
    e = repo.obtener_entrega(db, id_entrega)
    r = repo.obtener_reserva(db, e.id_reserva)
    d, es_donante, _ = _partes(cat, r, actor)
    antes = e.estado_entrega
    completada = repo.registrar_confirmacion(db, id_entrega, actor.id_usuario, d["id_donante"], estado, observaciones)
    db.commit()
    db.refresh(e)
    ctx = _contexto(r, d)
    lote.agregar("ENTREGA_CONFIRMADA", "entrega", id_entrega, antes, antes, actor.id_usuario, id_entrega=id_entrega,
                 confirmacion=estado, por="donante" if es_donante else "receptor", observaciones=observaciones, **ctx)
    if e.estado_entrega == "CON_INCIDENCIA" and antes != "CON_INCIDENCIA":
        lote.agregar("ENTREGA_CON_INCIDENCIA", "entrega", id_entrega, antes, "CON_INCIDENCIA", actor.id_usuario,
                     id_entrega=id_entrega, observaciones=observaciones, **ctx)
    if completada:
        # Regla de negocio: ENTREGADA solo con las dos confirmaciones
        lote.agregar("ENTREGA_COMPLETADA", "entrega", id_entrega, antes, "COMPLETADA", actor.id_usuario,
                     id_entrega=id_entrega, **ctx)
        lote.agregar("RESERVA_COMPLETADA", "reserva", r.id_reserva, "CONFIRMADA", "COMPLETADA", actor.id_usuario, **ctx)
        try:
            cat.transicionar(r.id_donacion, "ENTREGADA", actor.id_usuario, {"id_receptor": r.id_receptor})
        except (ServicioNoDisponible, TransicionInvalida) as error:
            log.warning("No se pudo marcar ENTREGADA la donación %s (%s); quedará para conciliar",
                        r.id_donacion, error)
    lote.publicar()
    return e


# --- Consultas -----------------------------------------------------------------

def reserva_dict(db: Session, r: Reserva, donacion: dict | None, actor: Actor) -> dict:
    e = repo.entrega_de_reserva(db, r.id_reserva)
    entrega = None
    if e is not None:
        confs = repo.confirmaciones(db, e.id_entrega)
        entrega = {
            "id_entrega": e.id_entrega, "estado_entrega": e.estado_entrega,
            "fecha_programada": _iso(e.fecha_programada), "fecha_entrega": _iso(e.fecha_entrega),
            "observaciones": e.observaciones, "yo_confirme": any(c.id_usuario == actor.id_usuario for c in confs),
            "confirmaciones": [{"id_usuario": c.id_usuario, "estado_confirmacion": c.estado_confirmacion,
                                "observaciones": c.observaciones, "fecha_confirmacion": _iso(c.fecha_confirmacion)}
                               for c in confs],
        }
    return {
        "id_reserva": r.id_reserva, "id_donacion": r.id_donacion, "id_receptor": r.id_receptor,
        "estado_reserva": r.estado_reserva, "fecha_reserva": _iso(r.fecha_reserva),
        "fecha_expiracion": _iso(r.fecha_expiracion), "donacion": donacion, "entrega": entrega,
        "soy": "donante" if donacion and donacion["id_donante"] == actor.id_usuario else
               "receptor" if r.id_receptor == actor.id_usuario else "administrador",
    }


def mis_reservas(db: Session, cat: ClienteCatalogo, actor: Actor, solo_con_entrega: bool = False) -> list[dict]:
    if actor.rol == "DONANTE":
        mias = {d["id_donacion"]: d for d in cat.donaciones(id_donante=actor.id_usuario)}
        reservas = repo.listar_reservas(db, ids_donaciones=list(mias)) if mias else []
    else:
        reservas = repo.listar_reservas(db, id_receptor=actor.id_usuario)
        mias = {d["id_donacion"]: d for d in cat.donaciones(ids=[r.id_donacion for r in reservas])}
    salida = [reserva_dict(db, r, mias.get(r.id_donacion), actor) for r in reservas]
    return [x for x in salida if x["entrega"]] if solo_con_entrega else salida


def una_reserva(db: Session, cat: ClienteCatalogo, actor: Actor, id_reserva: int) -> dict:
    r = repo.obtener_reserva(db, id_reserva)
    d, es_donante, es_receptor = _partes(cat, r, actor)
    if not (es_donante or es_receptor or actor.rol == "ADMINISTRADOR"):
        raise Prohibido("No participas en esta reserva")
    return reserva_dict(db, r, d, actor)


# --- Tareas automáticas (RF8, S5-13) --------------------------------------------

def expirar(db: Session, lote: Lote, cat: ClienteCatalogo, ahora: datetime | None = None) -> int:
    pares = repo.expirar_reservas(db, ahora)
    db.commit()
    if not pares:
        return 0
    donaciones = {d["id_donacion"]: d for d in cat.donaciones(ids=[p[1] for p in pares])}
    for id_reserva, id_donacion in pares:
        d = donaciones.get(id_donacion, {"id_donante": None, "nombre_alimento": "", "estado_donacion": ""})
        r = repo.obtener_reserva(db, id_reserva)
        lote.agregar("RESERVA_EXPIRADA", "reserva", id_reserva, "PENDIENTE", "EXPIRADA", None, **_contexto(r, d))
        if d.get("id_donacion"):
            _liberar(cat, "expirar", d, None, "reserva expirada")
    return len(pares)


def avisar_por_vencer(db: Session, lote: Lote, cat: ClienteCatalogo) -> int:
    avisos = 0
    for d in cat.por_vencer(config.AVISO_POR_VENCER_HORAS):
        nueva = db.execute(insert(AvisoVencimiento).values(id_donacion=d["id_donacion"])
                           .on_conflict_do_nothing().returning(AvisoVencimiento.id_donacion)).first()
        if nueva is None:
            continue  # ya avisada: la tarea es idempotente
        activa = repo.reserva_activa(db, d["id_donacion"])
        lote.agregar("DONACION_POR_VENCER", "donacion", d["id_donacion"], d["estado_donacion"],
                     d["estado_donacion"], None, id_donacion=d["id_donacion"], id_donante=d["id_donante"],
                     nombre_alimento=d["nombre_alimento"], fecha_vencimiento=d["fecha_vencimiento"],
                     id_receptor=activa.id_receptor if activa else None)
        avisos += 1
    db.commit()
    return avisos


def conciliar(db: Session, cat: ClienteCatalogo) -> int:
    """Riesgo del plan: donación RESERVADA sin reserva activa (o COMPLETADA sin ENTREGADA) si falló una llamada."""
    corregidas = 0
    for d in cat.donaciones(estado="RESERVADA"):
        activa = repo.reserva_activa(db, d["id_donacion"])
        if activa is not None:
            continue
        completada = db.scalar(select(Reserva).where(Reserva.id_donacion == d["id_donacion"],
                                                     Reserva.estado_reserva == "COMPLETADA"))
        destino = "ENTREGADA" if completada else ("DISPONIBLE" if _vigente(d) else "VENCIDA")
        try:
            cat.transicionar(d["id_donacion"], destino, None, {"motivo": "conciliación"})
            corregidas += 1
        except (TransicionInvalida, ServicioNoDisponible) as error:
            log.warning("Conciliación de la donación %s pendiente: %s", d["id_donacion"], error)
    return corregidas


def ejecutar_tareas(db: Session, cat: ClienteCatalogo, ahora: datetime | None = None) -> dict:
    """Ejecutarla dos veces seguidas no duplica efectos ni eventos."""
    lote = Lote("fulfillment")
    resultado = {"reservas_expiradas": expirar(db, lote, cat, ahora), "donaciones_vencidas": len(cat.vencer()),
                 "avisos_por_vencer": avisar_por_vencer(db, lote, cat), "conciliadas": conciliar(db, cat)}
    lote.publicar()
    return resultado


def forzar_expiracion(db: Session, cat: ClienteCatalogo, actor: Actor, id_reserva: int) -> dict:
    """Botón de demostración (D-09): adelanta el plazo de una reserva PENDIENTE y ejecuta las tareas."""
    if not config.MODO_DEMO:
        raise Prohibido("El modo demostración está desactivado")
    r = repo.obtener_reserva(db, id_reserva, bloquear=True)
    _, es_donante, es_receptor = _partes(cat, r, actor)
    if not (es_donante or es_receptor or actor.rol == "ADMINISTRADOR"):
        raise Prohibido("No participas en esta reserva")
    if r.estado_reserva != "PENDIENTE":
        raise TransicionInvalida("Solo se expira una reserva PENDIENTE")
    r.fecha_expiracion = func.greatest(func.now(), r.fecha_reserva + func.make_interval(0, 0, 0, 0, 0, 0, 0.001))
    db.commit()
    return ejecutar_tareas(db, cat)
