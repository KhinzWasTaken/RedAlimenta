"""Módulo de identidad: usuarios, autenticación, verificación y auditoría (RF1, RF10)."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import estados
from app.core.errores import ErrorDominio, NoEncontrado
from app.core.eventos import Evento, publicar, suscribir
from app.core.seguridad import Actor, emitir_token, hash_contrasena, verificar_contrasena
from app.core.tiempo import ahora, iso

from .modelos import RegistroAuditoria, Rol, Usuario, VerificacionUsuario


# --- Consultas -----------------------------------------------------------------

def verificacion_actual(db: Session, id_usuario: int) -> VerificacionUsuario | None:
    return db.scalars(
        select(VerificacionUsuario)
        .where(VerificacionUsuario.id_usuario == id_usuario)
        .order_by(VerificacionUsuario.id_verificacion.desc())
        .limit(1)
    ).first()


def _rol(db: Session, usuario: Usuario) -> str:
    return db.get(Rol, usuario.id_rol).nombre_rol


def actor_de(db: Session, usuario: Usuario) -> Actor:
    rol = _rol(db, usuario)
    verificacion = verificacion_actual(db, usuario.id_usuario)
    estado = verificacion.estado_verificacion if verificacion else "PENDIENTE"
    return Actor(usuario.id_usuario, rol, estado, usuario.nombre)


def perfil(db: Session, usuario: Usuario) -> dict:
    actor = actor_de(db, usuario)
    return {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre,
        "correo_electronico": usuario.correo_electronico,
        "telefono": usuario.telefono,
        "rol": actor.rol,
        "estado_cuenta": usuario.estado_cuenta,
        "estado_verificacion": actor.verificacion,
    }


def nombres_publicos(db: Session, ids: set[int]) -> dict[int, str]:
    """Solo el nombre (dato no sensible) para mostrar contrapartes; nunca correo ni teléfono."""
    if not ids:
        return {}
    filas = db.execute(select(Usuario.id_usuario, Usuario.nombre).where(Usuario.id_usuario.in_(ids)))
    return {i: n for i, n in filas}


# --- Autenticación -------------------------------------------------------------

def iniciar_sesion(db: Session, correo: str, contrasena: str) -> dict:
    usuario = db.scalars(select(Usuario).where(Usuario.correo_electronico == correo.strip().lower())).first()
    if usuario is None or not verificar_contrasena(contrasena, usuario.contrasena_hash):
        raise ErrorDominio("Correo o contraseña incorrectos")
    if usuario.estado_cuenta != "ACTIVA":
        raise ErrorDominio("La cuenta está desactivada")
    return {"token": emitir_token(actor_de(db, usuario)), "usuario": perfil(db, usuario)}


def refrescar(db: Session, id_usuario: int) -> dict:
    usuario = db.get(Usuario, id_usuario)
    if usuario is None or usuario.estado_cuenta != "ACTIVA":
        raise ErrorDominio("La cuenta no está activa")
    return {"token": emitir_token(actor_de(db, usuario)), "usuario": perfil(db, usuario)}


def crear_usuario(db: Session, nombre: str, correo: str, contrasena: str, rol: str,
                  telefono: str | None = None, verificacion: str = "PENDIENTE") -> Usuario:
    id_rol = db.scalars(select(Rol.id_rol).where(Rol.nombre_rol == rol)).one()
    usuario = Usuario(id_rol=id_rol, nombre=nombre, correo_electronico=correo.lower(),
                      contrasena_hash=hash_contrasena(contrasena), telefono=telefono)
    db.add(usuario)
    db.flush()
    v = VerificacionUsuario(id_usuario=usuario.id_usuario, estado_verificacion=verificacion)
    if verificacion != "PENDIENTE":
        v.fecha_resolucion = ahora()
        v.observaciones = "Cuenta semilla"
    db.add(v)
    db.flush()
    return usuario


# --- Administración: verificación y auditoría ----------------------------------

def listar_usuarios(db: Session) -> list[dict]:
    resultado = []
    for usuario in db.scalars(select(Usuario).order_by(Usuario.id_usuario)):
        datos = perfil(db, usuario)
        v = verificacion_actual(db, usuario.id_usuario)
        datos["verificacion"] = None if v is None else {
            "id_verificacion": v.id_verificacion,
            "estado_verificacion": v.estado_verificacion,
            "fecha_solicitud": iso(v.fecha_solicitud),
            "fecha_resolucion": iso(v.fecha_resolucion),
            "observaciones": v.observaciones,
        }
        resultado.append(datos)
    return resultado


def resolver_verificacion(db: Session, id_verificacion: int, decision: str,
                          observaciones: str | None, admin: Actor) -> VerificacionUsuario:
    v = db.get(VerificacionUsuario, id_verificacion)
    if v is None:
        raise NoEncontrado("Verificación no encontrada")
    if decision not in ("APROBADA", "RECHAZADA"):
        raise ErrorDominio("La decisión debe ser APROBADA o RECHAZADA")
    estados.validar("verificacion", v.estado_verificacion, decision)
    anterior = v.estado_verificacion
    v.estado_verificacion = decision
    v.id_administrador = admin.id_usuario
    v.fecha_resolucion = ahora()
    v.observaciones = observaciones
    db.flush()
    publicar(db, Evento(
        tipo="USUARIO_VERIFICADO", entidad="verificacion", id_entidad=v.id_verificacion,
        estado_anterior=anterior, estado_nuevo=decision, id_actor=admin.id_usuario,
        datos={"id_usuario": v.id_usuario, "observaciones": observaciones},
    ))
    return v


def listar_auditoria(db: Session, entidad: str | None = None, id_registro: int | None = None,
                     limite: int = 200) -> list[dict]:
    consulta = select(RegistroAuditoria).order_by(RegistroAuditoria.id_auditoria.desc()).limit(limite)
    if entidad:
        consulta = consulta.where(RegistroAuditoria.entidad_afectada == entidad)
    if id_registro is not None:
        consulta = consulta.where(RegistroAuditoria.id_registro_afectado == id_registro)
    filas = list(db.scalars(consulta))
    nombres = nombres_publicos(db, {f.id_usuario for f in filas if f.id_usuario})
    return [{
        "id_auditoria": f.id_auditoria,
        "id_usuario": f.id_usuario,
        "actor": nombres.get(f.id_usuario, "Sistema") if f.id_usuario else "Sistema",
        "entidad_afectada": f.entidad_afectada,
        "id_registro_afectado": f.id_registro_afectado,
        "accion_realizada": f.accion_realizada,
        "valor_anterior": f.valor_anterior,
        "valor_nuevo": f.valor_nuevo,
        "fecha_operacion": iso(f.fecha_operacion),
    } for f in filas]


def existe_evento(db: Session, accion: str, entidad: str, id_registro: int) -> bool:
    return db.scalars(select(RegistroAuditoria.id_auditoria).where(
        RegistroAuditoria.accion_realizada == accion,
        RegistroAuditoria.entidad_afectada == entidad,
        RegistroAuditoria.id_registro_afectado == id_registro,
    ).limit(1)).first() is not None


@suscribir
def registrar_auditoria(db: Session, evento: Evento) -> None:
    """D-04: cada evento queda en registro_auditoria."""
    if evento.estado_anterior == evento.estado_nuevo:
        anterior, nuevo = evento.estado_anterior, json.dumps(
            {"estado": evento.estado_nuevo, **evento.datos}, ensure_ascii=False, default=str)
    else:
        anterior, nuevo = evento.estado_anterior, evento.estado_nuevo
    db.add(RegistroAuditoria(
        id_usuario=evento.id_actor,
        entidad_afectada=evento.entidad,
        id_registro_afectado=evento.id_entidad,
        accion_realizada=evento.tipo,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        fecha_operacion=evento.fecha,
    ))

