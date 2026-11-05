"""Tareas automáticas (RF8, D-09). Son idempotentes: correrlas dos veces no duplica efectos."""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo import servicio as catalogo
from app.core import config
from app.core.db import SesionLocal
from app.core.errores import Conflicto, Prohibido
from app.core.eventos import Evento, publicar
from app.core.seguridad import Actor
from app.core.tiempo import ahora, hora_bogota
from app.identidad.servicio import existe_evento

from .modelos import Reserva
from .servicio import _cambiar_reserva, _es_parte, liberar_donacion, obtener_reserva

log = logging.getLogger("redalimenta.tareas")


def vencer_donaciones(db: Session) -> int:
    vencidas = catalogo.donaciones_vencidas(db)
    for d in vencidas:
        catalogo.transicionar_donacion(db, d.id_donacion, "VENCIDA", None)
    return len(vencidas)


def expirar_reservas(db: Session) -> int:
    pendientes = list(db.scalars(select(Reserva).where(
        Reserva.estado_reserva == "PENDIENTE", Reserva.fecha_expiracion <= ahora())))
    for r in pendientes:
        _cambiar_reserva(db, r, "EXPIRADA", None)
        liberar_donacion(db, r.id_donacion, None)
    return len(pendientes)


def avisar_por_vencer(db: Session) -> int:
    avisos = 0
    for d in catalogo.donaciones_por_vencer(db, config.AVISO_VENCER_HORAS):
        if existe_evento(db, "DONACION_POR_VENCER", "donacion", d.id_donacion):
            continue
        activa = db.scalars(select(Reserva).where(
            Reserva.id_donacion == d.id_donacion,
            Reserva.estado_reserva.in_(("PENDIENTE", "CONFIRMADA")))).first()
        publicar(db, Evento(
            tipo="DONACION_POR_VENCER", entidad="donacion", id_entidad=d.id_donacion,
            estado_anterior=d.estado_donacion, estado_nuevo=d.estado_donacion, id_actor=None,
            datos={"id_donante": d.id_donante, "nombre_alimento": d.nombre_alimento,
                   "vence": hora_bogota(d.fecha_vencimiento),
                   "id_receptor": activa.id_receptor if activa else None},
        ))
        avisos += 1
    return avisos


def ejecutar_todas(db: Session) -> dict:
    resultado = {
        "reservas_expiradas": expirar_reservas(db),
        "donaciones_vencidas": vencer_donaciones(db),
        "avisos_por_vencer": avisar_por_vencer(db),
    }
    db.commit()
    return resultado


def forzar_expiracion(db: Session, actor: Actor, id_reserva: int) -> dict:
    """Botón de demo: adelanta el plazo de una reserva PENDIENTE y ejecuta la expiración (D-09)."""
    if not config.MODO_DEMO:
        raise Prohibido("El modo demo está desactivado")
    r = obtener_reserva(db, id_reserva)
    es_donante, es_receptor = _es_parte(db, r, actor)
    if not (es_donante or es_receptor or actor.rol == "ADMINISTRADOR"):
        raise Prohibido("No participas en esta reserva")
    if r.estado_reserva != "PENDIENTE":
        raise Conflicto("Solo se puede expirar una reserva PENDIENTE")
    r.fecha_expiracion = max(ahora(), r.fecha_reserva)
    db.flush()
    return ejecutar_todas(db)


async def planificador() -> None:
    """Planificador interno (en Kubernetes sería un CronJob, ver plan sección 3)."""
    while True:
        await asyncio.sleep(config.PLANIFICADOR_SEGUNDOS)
        try:
            await asyncio.to_thread(_ciclo)
        except Exception:  # el planificador no debe morir por un fallo puntual
            log.exception("Fallo en las tareas programadas")


def _ciclo() -> None:
    with SesionLocal() as db:
        resultado = ejecutar_todas(db)
        if any(resultado.values()):
            log.info("Tareas programadas: %s", resultado)
