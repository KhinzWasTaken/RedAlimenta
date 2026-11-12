"""API REST de fulfillment-service (S5-10 a S5-13)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.eventos import Lote
from redalimenta_comun.seguridad import Actor, requiere_rol, requiere_verificado

from . import repositorio as repo
from . import servicio
from .catalogo_cliente import cliente_catalogo
from .db import sesiones

rutas = APIRouter(prefix="/api")
obtener_db = dependencia_sesion(sesiones)
PARTES = ("DONANTE", "RECEPTOR")


class NuevaReserva(BaseModel):
    id_donacion: int


class Confirmacion(BaseModel):
    estado_confirmacion: str = Field("CONFIRMADA", description="CONFIRMADA o CON_INCIDENCIA")
    observaciones: str | None = Field(default=None, max_length=1000)


def _lote() -> Lote:
    return Lote("fulfillment")


@rutas.post("/reservas", status_code=201, tags=["reservas"])
def reservar(datos: NuevaReserva, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
             db: Session = Depends(obtener_db)):
    """D-02: con dos solicitudes simultáneas, una recibe 201 y la otra 409."""
    cat = cliente_catalogo()
    r = servicio.reservar(db, _lote(), cat, actor, datos.id_donacion)
    return servicio.una_reserva(db, cat, actor, r.id_reserva)


@rutas.get("/reservas/mias", tags=["reservas"])
def mis_reservas(actor: Actor = Depends(requiere_rol(*PARTES)), db: Session = Depends(obtener_db)):
    return servicio.mis_reservas(db, cliente_catalogo(), actor)


@rutas.get("/reservas/{id_reserva}", tags=["reservas"])
def ver_reserva(id_reserva: int, actor: Actor = Depends(requiere_rol(*PARTES, "ADMINISTRADOR")),
                db: Session = Depends(obtener_db)):
    return servicio.una_reserva(db, cliente_catalogo(), actor, id_reserva)


@rutas.post("/reservas/{id_reserva}/confirmar", tags=["reservas"])
def confirmar(id_reserva: int, actor: Actor = Depends(requiere_verificado("DONANTE")),
              db: Session = Depends(obtener_db)):
    cat = cliente_catalogo()
    servicio.confirmar(db, _lote(), cat, actor, id_reserva)
    return servicio.una_reserva(db, cat, actor, id_reserva)


@rutas.post("/reservas/{id_reserva}/cancelar", tags=["reservas"])
def cancelar(id_reserva: int, actor: Actor = Depends(requiere_rol(*PARTES, "ADMINISTRADOR")),
             db: Session = Depends(obtener_db)):
    cat = cliente_catalogo()
    servicio.cancelar(db, _lote(), cat, actor, id_reserva)
    return servicio.una_reserva(db, cat, actor, id_reserva)


@rutas.post("/reservas/{id_reserva}/forzar-expiracion", tags=["demostración"])
def forzar_expiracion(id_reserva: int, actor: Actor = Depends(requiere_rol(*PARTES, "ADMINISTRADOR")),
                      db: Session = Depends(obtener_db)):
    """Solo con MODO_DEMO=1: adelanta el plazo de una reserva PENDIENTE y la expira (D-09)."""
    tareas = servicio.forzar_expiracion(db, cliente_catalogo(), actor, id_reserva)
    return {"tareas": tareas, "estado_reserva": repo.obtener_reserva(db, id_reserva).estado_reserva}


@rutas.get("/entregas/mias", tags=["entregas"])
def mis_entregas(actor: Actor = Depends(requiere_rol(*PARTES)), db: Session = Depends(obtener_db)):
    return servicio.mis_reservas(db, cliente_catalogo(), actor, solo_con_entrega=True)


@rutas.post("/entregas/{id_entrega}/confirmar", tags=["entregas"])
def confirmar_entrega(id_entrega: int, datos: Confirmacion, actor: Actor = Depends(requiere_verificado(*PARTES)),
                      db: Session = Depends(obtener_db)):
    """RF6: la donación queda ENTREGADA solo con la confirmación del donante y la del receptor."""
    cat = cliente_catalogo()
    e = servicio.confirmar_entrega(db, _lote(), cat, actor, id_entrega, datos.estado_confirmacion,
                                   datos.observaciones)
    return servicio.una_reserva(db, cat, actor, e.id_reserva)


@rutas.post("/tareas/ejecutar", tags=["tareas"])
def ejecutar_tareas(_: Actor = Depends(requiere_rol("ADMINISTRADOR")), db: Session = Depends(obtener_db)):
    """Ejecuta ahora las tareas automáticas (RF8): idempotente."""
    return servicio.ejecutar_tareas(db, cliente_catalogo())
