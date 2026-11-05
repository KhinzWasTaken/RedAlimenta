from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import obtener_db
from app.core.errores import NoEncontrado
from app.core.seguridad import Actor, actor_actual, requiere_rol

from . import servicio
from .modelos import Usuario

rutas = APIRouter(prefix="/api", tags=["identidad"])


class Credenciales(BaseModel):
    correo: str
    contrasena: str


class Decision(BaseModel):
    decision: str  # APROBADA | RECHAZADA
    observaciones: str | None = None


@rutas.post("/auth/login")
def login(datos: Credenciales, db: Session = Depends(obtener_db)):
    return servicio.iniciar_sesion(db, datos.correo, datos.contrasena)


@rutas.post("/auth/refresh")
def refresh(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    """Emite un token nuevo con el estado de verificación vigente (D-06)."""
    return servicio.refrescar(db, actor.id_usuario)


@rutas.get("/auth/me")
def me(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    usuario = db.get(Usuario, actor.id_usuario)
    if usuario is None:
        raise NoEncontrado("Usuario no encontrado")
    return servicio.perfil(db, usuario)


@rutas.get("/admin/usuarios")
def usuarios(_: Actor = Depends(requiere_rol("ADMINISTRADOR")), db: Session = Depends(obtener_db)):
    return servicio.listar_usuarios(db)


@rutas.post("/admin/verificaciones/{id_verificacion}")
def resolver(id_verificacion: int, datos: Decision,
             admin: Actor = Depends(requiere_rol("ADMINISTRADOR")), db: Session = Depends(obtener_db)):
    v = servicio.resolver_verificacion(db, id_verificacion, datos.decision, datos.observaciones, admin)
    db.commit()
    return {"id_verificacion": v.id_verificacion, "estado_verificacion": v.estado_verificacion}


@rutas.get("/admin/auditoria")
def auditoria(entidad: str | None = None, id_registro: int | None = None, limite: int = 200,
              _: Actor = Depends(requiere_rol("ADMINISTRADOR")), db: Session = Depends(obtener_db)):
    return servicio.listar_auditoria(db, entidad, id_registro, min(limite, 1000))
