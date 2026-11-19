"""API REST de notification-service (S5-14): cada usuario ve y modifica solo su bandeja."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.seguridad import Actor, actor_actual

from . import chat
from . import repositorio as repo
from .db import sesiones

rutas = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])
rutas_chat = APIRouter(prefix="/api/conversaciones", tags=["chat (D-12)"])
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


# --- Chat entre donante y receptor (D-12) ----------------------------------------

class NuevoMensaje(BaseModel):
    texto: str = Field(min_length=1, max_length=chat.MAX_TEXTO)


def _iso(valor):
    return valor.isoformat() if valor else None


def _conversacion(c: dict) -> dict:
    return {"id_conversacion": c["id_conversacion"], "id_donacion": c["id_donacion"],
            "nombre_alimento": c["nombre_alimento"], "origen": c["origen"],
            "estado_conversacion": c["estado_conversacion"], "id_donante": c["id_donante"],
            "id_receptor": c["id_receptor"], "id_contraparte": c["id_contraparte"], "mi_papel": c["mi_papel"],
            "no_leidos": int(c["no_leidos"]), "fecha_creacion": _iso(c["fecha_creacion"]),
            "ultimo_mensaje": None if c["ultimo_texto"] is None else {
                "texto": c["ultimo_texto"], "fecha_envio": _iso(c["ultima_fecha"]), "id_autor": c["ultimo_autor"]}}


def _mensaje(m) -> dict:
    return {"id_mensaje": m.id_mensaje, "id_autor": m.id_autor, "texto": m.texto, "fecha_envio": _iso(m.fecha_envio)}


@rutas_chat.get("")
def conversaciones(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    """Las conversaciones del usuario (como donante o receptor), con su último mensaje y no leídos."""
    return [_conversacion(c) for c in chat.mias(db, actor.id_usuario)]


@rutas_chat.get("/no-leidos")
def mensajes_no_leidos(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return {"no_leidos": chat.contar_no_leidos(db, actor.id_usuario)}


@rutas_chat.get("/{id_conversacion}/mensajes")
def mensajes(id_conversacion: int, despues_de: int = 0, actor: Actor = Depends(actor_actual),
             db: Session = Depends(obtener_db)):
    c, lista = chat.mensajes(db, id_conversacion, actor.id_usuario, despues_de)
    return {"estado_conversacion": c.estado_conversacion, "mensajes": [_mensaje(m) for m in lista]}


@rutas_chat.post("/{id_conversacion}/mensajes", status_code=201)
def enviar(id_conversacion: int, datos: NuevoMensaje, actor: Actor = Depends(actor_actual),
           db: Session = Depends(obtener_db)):
    m = chat.enviar(db, id_conversacion, actor.id_usuario, datos.texto)
    db.commit()
    return _mensaje(m)


@rutas_chat.post("/{id_conversacion}/leer")
def leer_conversacion(id_conversacion: int, actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    chat.leer(db, id_conversacion, actor.id_usuario)
    db.commit()
    return {"no_leidos": chat.contar_no_leidos(db, actor.id_usuario)}
