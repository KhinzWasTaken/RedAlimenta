"""API REST de notification-service (S5-14): cada usuario ve y modifica solo su bandeja."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.seguridad import Actor, actor_actual

from . import repositorio as repo
from .db import sesiones

rutas = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])
obtener_db = dependencia_sesion(sesiones)


def _dict(n) -> dict:
    return {"id_notificacion": n.id_notificacion, "tipo_notificacion": n.tipo_notificacion, "mensaje": n.mensaje,
            "fecha_creacion": n.fecha_creacion.isoformat(),
            "fecha_lectura": n.fecha_lectura.isoformat() if n.fecha_lectura else None,
            "estado_notificacion": n.estado_notificacion}


@rutas.get("")
def bandeja(archivadas: bool = False, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return [_dict(n) for n in repo.bandeja(db, actor.id_usuario, archivadas)]


@rutas.get("/no-leidas")
def no_leidas(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return {"no_leidas": repo.contar_no_leidas(db, actor.id_usuario)}


@rutas.post("/leer-todas")
def leer_todas(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    marcadas = repo.marcar_todas_leidas(db, actor.id_usuario)
    db.commit()
    return {"marcadas": marcadas, "no_leidas": 0}


@rutas.post("/{id_notificacion}/leer")
def leer(id_notificacion: int, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    n = repo.marcar_leida(db, id_notificacion, actor.id_usuario)
    db.commit()
    return _dict(n)


@rutas.post("/{id_notificacion}/archivar")
def archivar(id_notificacion: int, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    n = repo.archivar(db, id_notificacion, actor.id_usuario)
    db.commit()
    return _dict(n)
