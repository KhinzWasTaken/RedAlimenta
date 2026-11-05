from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import obtener_db
from app.core.seguridad import Actor, requiere_rol, requiere_verificado

from . import servicio, tareas

rutas = APIRouter(prefix="/api", tags=["reservas y entregas"])

PARTICIPANTE = ("DONANTE", "RECEPTOR")


class ReservaEntrada(BaseModel):
    id_donacion: int


class ConfirmacionEntrada(BaseModel):
    estado_confirmacion: str = "CONFIRMADA"  # CONFIRMADA | CON_INCIDENCIA
    observaciones: str | None = None


@rutas.post("/reservas", status_code=201)
def reservar(datos: ReservaEntrada, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
             db: Session = Depends(obtener_db)):
    r = servicio.reservar(db, actor, datos.id_donacion)
    db.commit()
    return servicio.reserva_dict(db, r, actor)


@rutas.get("/reservas/mias")
def mis_reservas(actor: Actor = Depends(requiere_rol(*PARTICIPANTE)), db: Session = Depends(obtener_db)):
    return servicio.mis_reservas(db, actor)


@rutas.post("/reservas/{id_reserva}/confirmar")
def confirmar(id_reserva: int, actor: Actor = Depends(requiere_verificado("DONANTE")),
              db: Session = Depends(obtener_db)):
    r = servicio.confirmar_reserva(db, actor, id_reserva)
    db.commit()
    return servicio.reserva_dict(db, r, actor)


@rutas.post("/reservas/{id_reserva}/cancelar")
def cancelar(id_reserva: int, actor: Actor = Depends(requiere_verificado(*PARTICIPANTE)),
             db: Session = Depends(obtener_db)):
    r = servicio.cancelar_reserva(db, actor, id_reserva)
    db.commit()
    return servicio.reserva_dict(db, r, actor)


@rutas.post("/reservas/{id_reserva}/forzar-expiracion")
def forzar_expiracion(id_reserva: int,
                      actor: Actor = Depends(requiere_rol("DONANTE", "RECEPTOR", "ADMINISTRADOR")),
                      db: Session = Depends(obtener_db)):
    resultado = tareas.forzar_expiracion(db, actor, id_reserva)
    r = servicio.obtener_reserva(db, id_reserva)
    return {"tareas": resultado, "estado_reserva": r.estado_reserva}


@rutas.post("/entregas/{id_entrega}/confirmar")
def confirmar_entrega(id_entrega: int, datos: ConfirmacionEntrada,
                      actor: Actor = Depends(requiere_verificado(*PARTICIPANTE)),
                      db: Session = Depends(obtener_db)):
    e = servicio.confirmar_entrega(db, actor, id_entrega, datos.estado_confirmacion, datos.observaciones)
    db.commit()
    r = servicio.obtener_reserva(db, e.id_reserva)
    return servicio.reserva_dict(db, r, actor)


@rutas.post("/admin/tareas/ejecutar")
def ejecutar_tareas(_: Actor = Depends(requiere_rol("ADMINISTRADOR")), db: Session = Depends(obtener_db)):
    return tareas.ejecutar_todas(db)
