"""Casos de uso de identity-service: combinan el repositorio, la auditoría y los eventos.

Los cambios de estado de este servicio se auditan en la misma transacción (D-04); los de los demás
servicios llegan por RabbitMQ (`consumidor.py`). Los eventos se publican después del commit.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from redalimenta_comun.eventos import Evento, Lote
from redalimenta_comun.seguridad import Actor, emitir_token

from . import repositorio as repo
from .errores import ErrorDominio, NoAutenticado
from .modelos import RegistroAuditoria, Rol, Usuario

ROLES_REGISTRABLES = ("DONANTE", "RECEPTOR")


def _iso(fecha):
    return None if fecha is None else fecha.isoformat()


def actor_de(db: Session, usuario: Usuario) -> Actor:
    rol = db.get(Rol, usuario.id_rol).nombre_rol
    v = repo.verificacion_actual(db, usuario.id_usuario)
    return Actor(usuario.id_usuario, rol, v.estado_verificacion if v else "PENDIENTE", usuario.nombre)


def perfil(db: Session, usuario: Usuario) -> dict:
    actor = actor_de(db, usuario)
    v = repo.verificacion_actual(db, usuario.id_usuario)
    return {
        "id_usuario": usuario.id_usuario, "nombre": usuario.nombre,
        "correo_electronico": usuario.correo_electronico, "telefono": usuario.telefono, "rol": actor.rol,
        "estado_cuenta": usuario.estado_cuenta, "fecha_registro": _iso(usuario.fecha_registro),
        "estado_verificacion": actor.verificacion,
        "verificacion": None if v is None else {
            "id_verificacion": v.id_verificacion, "estado_verificacion": v.estado_verificacion,
            "fecha_solicitud": _iso(v.fecha_solicitud), "fecha_resolucion": _iso(v.fecha_resolucion),
            "observaciones": v.observaciones,
        },
    }


def sesion(db: Session, usuario: Usuario) -> dict:
    return {"token": emitir_token(actor_de(db, usuario)), "usuario": perfil(db, usuario)}


def auditar(db: Session, evento: Evento) -> None:
    """Guarda un evento en registro_auditoria (solo inserción)."""
    actor = evento.id_actor if evento.id_actor and db.get(Usuario, evento.id_actor) else None
    if evento.estado_anterior == evento.estado_nuevo:  # evento sin cambio de estado: se guarda el detalle
        nuevo = json.dumps({"estado": evento.estado_nuevo, **evento.datos}, ensure_ascii=False, default=str)
    else:
        nuevo = evento.estado_nuevo
    db.add(RegistroAuditoria(id_usuario=actor, entidad_afectada=evento.entidad,
                             id_registro_afectado=evento.id_entidad, accion_realizada=evento.tipo,
                             valor_anterior=evento.estado_anterior, valor_nuevo=nuevo))
    db.flush()


def _registrar(db: Session, lote: Lote, *args, **datos) -> None:
    auditar(db, lote.agregar(*args, **datos))


# --- Casos de uso --------------------------------------------------------------

def registrar(db: Session, lote: Lote, nombre, correo, contrasena, rol, telefono=None) -> Usuario:
    if rol not in ROLES_REGISTRABLES:
        raise ErrorDominio("Solo se registran donantes o receptores; los administradores los crea otro administrador")
    if len(contrasena) < 8:
        raise ErrorDominio("La contraseña debe tener al menos 8 caracteres")
    u = repo.crear_usuario(db, nombre, correo, contrasena, rol, telefono)
    _registrar(db, lote, "USUARIO_REGISTRADO", "usuario", u.id_usuario, None, "ACTIVA", u.id_usuario, rol=rol)
    return u


def iniciar_sesion(db: Session, correo: str, contrasena: str) -> dict:
    return sesion(db, repo.autenticar(db, correo, contrasena))


def refrescar(db: Session, id_usuario: int) -> dict:
    u = db.get(Usuario, id_usuario)
    if u is None or u.estado_cuenta != "ACTIVA":
        raise NoAutenticado("La cuenta no está activa")
    return sesion(db, u)


def desactivar(db: Session, lote: Lote, id_usuario: int, id_actor: int) -> Usuario:
    u = repo.desactivar_usuario(db, id_usuario)
    _registrar(db, lote, "USUARIO_DESACTIVADO", "usuario", id_usuario, "ACTIVA", "DESACTIVADA", id_actor)
    return u


def solicitar_verificacion(db: Session, lote: Lote, id_usuario: int):
    v = repo.solicitar_verificacion(db, id_usuario)
    _registrar(db, lote, "VERIFICACION_SOLICITADA", "verificacion", v.id_verificacion, "RECHAZADA", "PENDIENTE",
               id_usuario, id_usuario=id_usuario)
    return v


def resolver_verificacion(db: Session, lote: Lote, id_verificacion, decision, observaciones, admin: Actor):
    v = repo.resolver_verificacion(db, id_verificacion, decision, admin.id_usuario, observaciones)
    _registrar(db, lote, "USUARIO_VERIFICADO", "verificacion", v.id_verificacion, "PENDIENTE", decision,
               admin.id_usuario, id_usuario=v.id_usuario, observaciones=observaciones)
    return v


def nombres_publicos(db: Session, ids: list[int]) -> dict[str, str]:
    """Solo el nombre (dato no sensible) para mostrar contrapartes; nunca correo ni teléfono (Ley 1581)."""
    if not ids:
        return {}
    filas = db.execute(select(Usuario.id_usuario, Usuario.nombre).where(Usuario.id_usuario.in_(ids[:200])))
    return {str(i): n for i, n in filas}


def auditoria(db: Session, entidad=None, id_registro=None, id_usuario=None, limite=200) -> list[dict]:
    filas = repo.consultar_auditoria(db, entidad, id_registro, id_usuario, limite)
    nombres = nombres_publicos(db, list({f.id_usuario for f in filas if f.id_usuario}))
    return [{
        "id_auditoria": f.id_auditoria, "id_usuario": f.id_usuario,
        "actor": nombres.get(str(f.id_usuario), "Sistema") if f.id_usuario else "Sistema",
        "entidad_afectada": f.entidad_afectada, "id_registro_afectado": f.id_registro_afectado,
        "accion_realizada": f.accion_realizada, "valor_anterior": f.valor_anterior, "valor_nuevo": f.valor_nuevo,
        "fecha_operacion": _iso(f.fecha_operacion),
    } for f in filas]
