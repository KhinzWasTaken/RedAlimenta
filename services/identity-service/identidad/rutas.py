"""API REST de identity-service (S5-03, S5-04, S5-05)."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.eventos import Lote
from redalimenta_comun.seguridad import Actor, actor_actual, requiere_rol

from . import repositorio as repo
from . import servicio
from .db import sesiones

rutas = APIRouter(prefix="/api")
obtener_db = dependencia_sesion(sesiones)
ADMIN = requiere_rol("ADMINISTRADOR")


class Registro(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    correo: str = Field(min_length=5, max_length=254)
    contrasena: str = Field(min_length=8, max_length=128)
    rol: str = Field(description="DONANTE o RECEPTOR")
    telefono: str | None = Field(default=None, max_length=30)


class Credenciales(BaseModel):
    correo: str
    contrasena: str


class CambiosPerfil(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)


class Decision(BaseModel):
    decision: str = Field(description="APROBADA o RECHAZADA")
    observaciones: str | None = None


def _confirmar(db: Session, lote: Lote) -> None:
    db.commit()
    lote.publicar()


# --- Autenticación (S5-03) -----------------------------------------------------

@rutas.post("/auth/registro", status_code=201, tags=["autenticación"])
def registro(datos: Registro, db: Session = Depends(obtener_db)):
    """Crea una cuenta de donante o receptor; queda PENDIENTE de verificación."""
    lote = Lote("identity")
    u = servicio.registrar(db, lote, datos.nombre, datos.correo, datos.contrasena, datos.rol, datos.telefono)
    _confirmar(db, lote)
    return servicio.sesion(db, u)


@rutas.post("/auth/login", tags=["autenticación"])
def login(datos: Credenciales, db: Session = Depends(obtener_db)):
    return servicio.iniciar_sesion(db, datos.correo, datos.contrasena)


@rutas.post("/auth/refresh", tags=["autenticación"])
def refresh(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    """Token nuevo con el estado de verificación vigente (D-06)."""
    return servicio.refrescar(db, actor.id_usuario)


@rutas.get("/auth/me", tags=["autenticación"])
def me(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return servicio.perfil(db, repo.obtener_usuario(db, actor.id_usuario))


# --- Perfil propio (S5-04) -----------------------------------------------------

@rutas.get("/usuarios/me", tags=["perfil"])
def mi_perfil(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return servicio.perfil(db, repo.obtener_usuario(db, actor.id_usuario))


@rutas.patch("/usuarios/me", tags=["perfil"])
def actualizar_perfil(cambios: CambiosPerfil, actor: Actor = Depends(actor_actual),
                      db: Session = Depends(obtener_db)):
    u = repo.actualizar_usuario(db, actor.id_usuario, **cambios.model_dump(exclude_none=True))
    db.commit()
    return servicio.perfil(db, u)


@rutas.post("/usuarios/me/desactivar", tags=["perfil"])
def desactivar_mi_cuenta(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    lote = Lote("identity")
    u = servicio.desactivar(db, lote, actor.id_usuario, actor.id_usuario)
    _confirmar(db, lote)
    return servicio.perfil(db, u)


@rutas.post("/usuarios/me/verificacion", status_code=201, tags=["perfil"])
def solicitar_verificacion(actor: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    """Vuelve a pedir verificación después de un rechazo."""
    lote = Lote("identity")
    servicio.solicitar_verificacion(db, lote, actor.id_usuario)
    _confirmar(db, lote)
    return servicio.perfil(db, repo.obtener_usuario(db, actor.id_usuario))


@rutas.get("/usuarios/nombres", tags=["perfil"])
def nombres(ids: str = Query(description="Identificadores separados por coma"),
            _: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    """Nombres públicos de usuarios (sin datos personales), para mostrar contrapartes."""
    return servicio.nombres_publicos(db, [int(x) for x in ids.split(",") if x.strip().isdigit()])


# --- Administración (S5-05) ----------------------------------------------------

@rutas.get("/admin/usuarios", tags=["administración"])
def usuarios(rol: str | None = None, estado_verificacion: str | None = None, _: Actor = Depends(ADMIN),
             db: Session = Depends(obtener_db)):
    return [servicio.perfil(db, f["usuario"]) for f in repo.listar_usuarios(db, rol, estado_verificacion)]


@rutas.get("/admin/usuarios/{id_usuario}", tags=["administración"])
def usuario(id_usuario: int, _: Actor = Depends(ADMIN), db: Session = Depends(obtener_db)):
    return servicio.perfil(db, repo.obtener_usuario(db, id_usuario))


@rutas.post("/admin/usuarios/{id_usuario}/desactivar", tags=["administración"])
def desactivar_usuario(id_usuario: int, admin: Actor = Depends(ADMIN), db: Session = Depends(obtener_db)):
    lote = Lote("identity")
    u = servicio.desactivar(db, lote, id_usuario, admin.id_usuario)
    _confirmar(db, lote)
    return servicio.perfil(db, u)


@rutas.post("/admin/verificaciones/{id_verificacion}", tags=["administración"])
def resolver(id_verificacion: int, datos: Decision, admin: Actor = Depends(ADMIN),
             db: Session = Depends(obtener_db)):
    lote = Lote("identity")
    v = servicio.resolver_verificacion(db, lote, id_verificacion, datos.decision, datos.observaciones, admin)
    _confirmar(db, lote)
    return servicio.perfil(db, repo.obtener_usuario(db, v.id_usuario))


@rutas.get("/admin/auditoria", tags=["administración"])
def auditoria(entidad: str | None = None, id_registro: int | None = None, id_usuario: int | None = None,
              limite: int = Query(200, le=1000), _: Actor = Depends(ADMIN), db: Session = Depends(obtener_db)):
    """Quién cambió qué y cuándo (RF10)."""
    return servicio.auditoria(db, entidad, id_registro, id_usuario, limite)
