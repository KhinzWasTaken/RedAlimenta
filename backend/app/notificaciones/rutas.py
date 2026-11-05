from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import obtener_db
from app.core.seguridad import Actor, actor_actual

from . import servicio

rutas = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])


@rutas.get("")
def bandeja(archivadas: bool = False, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return servicio.bandeja(db, actor.id_usuario, archivadas)


@rutas.get("/no-leidas")
def contador(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return {"no_leidas": servicio.no_leidas(db, actor.id_usuario)}


@rutas.post("/leer-todas")
def leer_todas(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    servicio.leer_todas(db, actor.id_usuario)
    db.commit()
    return {"no_leidas": 0}


@rutas.post("/{id_notificacion}/leer")
def leer(id_notificacion: int, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    n = servicio.cambiar_estado(db, actor.id_usuario, id_notificacion, "LEIDA")
    db.commit()
    return n


@rutas.post("/{id_notificacion}/archivar")
def archivar(id_notificacion: int, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    n = servicio.cambiar_estado(db, actor.id_usuario, id_notificacion, "ARCHIVADA")
    db.commit()
    return n
