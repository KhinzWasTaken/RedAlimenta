"""Consultas CRUD de identity-service (S4-09). Todas parametrizadas; cada una recibe la sesión.

La transacción la confirma quien llama (db.commit()), para poder agrupar varias operaciones.
"""
import hashlib
import hmac
import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errores import Conflicto, ErrorDominio, NoEncontrado, TransicionInvalida
from .modelos import RegistroAuditoria, Rol, Usuario, VerificacionUsuario

ITERACIONES = 120_000
CAMPOS_EDITABLES = ("nombre", "telefono")  # "datos permitidos" del RF1


# --- Contraseñas ---------------------------------------------------------------

def hash_contrasena(contrasena: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal}${digest.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, iteraciones, sal, digest = guardado.split("$")
    except ValueError:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), int(iteraciones))
    return hmac.compare_digest(calculado.hex(), digest)


# --- Usuarios ------------------------------------------------------------------

def id_rol(db: Session, nombre_rol: str) -> int:
    valor = db.scalar(select(Rol.id_rol).where(Rol.nombre_rol == nombre_rol))
    if valor is None:
        raise ErrorDominio(f"Rol desconocido: {nombre_rol}")
    return valor


def crear_usuario(db: Session, nombre: str, correo: str, contrasena: str, rol: str,
                  telefono: str | None = None) -> Usuario:
    """Crea la cuenta ACTIVA y abre su verificación PENDIENTE."""
    usuario = Usuario(id_rol=id_rol(db, rol), nombre=nombre.strip(), correo_electronico=correo.strip().lower(),
                      contrasena_hash=hash_contrasena(contrasena), telefono=telefono)
    try:
        with db.begin_nested():
            db.add(usuario)
            db.flush()
    except IntegrityError as error:
        if "ux_usuario_correo" in str(error.orig):
            raise Conflicto("Ya existe una cuenta con ese correo") from error
        raise
    db.add(VerificacionUsuario(id_usuario=usuario.id_usuario))
    db.flush()
    return usuario


def obtener_usuario(db: Session, id_usuario: int) -> Usuario:
    usuario = db.get(Usuario, id_usuario)
    if usuario is None:
        raise NoEncontrado("Usuario no encontrado")
    return usuario


def buscar_por_correo(db: Session, correo: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(func.lower(Usuario.correo_electronico) == correo.strip().lower()))


def autenticar(db: Session, correo: str, contrasena: str) -> Usuario:
    usuario = buscar_por_correo(db, correo)
    if usuario is None or not verificar_contrasena(contrasena, usuario.contrasena_hash):
        raise ErrorDominio("Correo o contraseña incorrectos")
    if usuario.estado_cuenta != "ACTIVA":
        raise ErrorDominio("La cuenta está desactivada")
    return usuario


def listar_usuarios(db: Session, rol: str | None = None, estado_verificacion: str | None = None) -> list[dict]:
    """Usuarios con su rol y el estado de su verificación más reciente."""
    ultima = (select(VerificacionUsuario.id_usuario, func.max(VerificacionUsuario.id_verificacion).label("id_v"))
              .group_by(VerificacionUsuario.id_usuario).subquery())
    consulta = (
        select(Usuario, Rol.nombre_rol, VerificacionUsuario)
        .join(Rol, Rol.id_rol == Usuario.id_rol)
        .outerjoin(ultima, ultima.c.id_usuario == Usuario.id_usuario)
        .outerjoin(VerificacionUsuario, VerificacionUsuario.id_verificacion == ultima.c.id_v)
        .order_by(Usuario.id_usuario)
    )
    if rol:
        consulta = consulta.where(Rol.nombre_rol == rol)
    if estado_verificacion:
        consulta = consulta.where(VerificacionUsuario.estado_verificacion == estado_verificacion)
    return [{"usuario": u, "rol": r, "verificacion": v} for u, r, v in db.execute(consulta)]


def actualizar_usuario(db: Session, id_usuario: int, **cambios) -> Usuario:
    """Solo cambia los datos permitidos (nombre y teléfono); correo, rol y estado no se editan aquí."""
    no_permitidos = set(cambios) - set(CAMPOS_EDITABLES)
    if no_permitidos:
        raise ErrorDominio(f"Campos no editables: {', '.join(sorted(no_permitidos))}")
    usuario = obtener_usuario(db, id_usuario)
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(usuario, campo, valor)
    db.flush()
    return usuario


def desactivar_usuario(db: Session, id_usuario: int) -> Usuario:
    """Desactivar no borra la fila: se conserva para la trazabilidad."""
    usuario = obtener_usuario(db, id_usuario)
    if usuario.estado_cuenta == "DESACTIVADA":
        raise TransicionInvalida("La cuenta ya está desactivada")
    usuario.estado_cuenta = "DESACTIVADA"
    db.flush()
    return usuario


# --- Verificación --------------------------------------------------------------

def verificacion_actual(db: Session, id_usuario: int) -> VerificacionUsuario | None:
    return db.scalar(select(VerificacionUsuario).where(VerificacionUsuario.id_usuario == id_usuario)
                     .order_by(VerificacionUsuario.id_verificacion.desc()).limit(1))


def solicitar_verificacion(db: Session, id_usuario: int) -> VerificacionUsuario:
    """Abre una nueva verificación (p. ej. tras un rechazo). Solo una PENDIENTE por usuario."""
    obtener_usuario(db, id_usuario)
    actual = verificacion_actual(db, id_usuario)
    if actual is not None and actual.estado_verificacion != "RECHAZADA":
        raise Conflicto(f"El usuario ya tiene una verificación {actual.estado_verificacion}")
    v = VerificacionUsuario(id_usuario=id_usuario)
    db.add(v)
    db.flush()
    return v


def resolver_verificacion(db: Session, id_verificacion: int, decision: str, id_administrador: int,
                          observaciones: str | None = None, cuando: datetime | None = None) -> VerificacionUsuario:
    if decision not in ("APROBADA", "RECHAZADA"):
        raise ErrorDominio("La decisión debe ser APROBADA o RECHAZADA")
    v = db.get(VerificacionUsuario, id_verificacion, with_for_update=True)
    if v is None:
        raise NoEncontrado("Verificación no encontrada")
    if v.estado_verificacion != "PENDIENTE":
        raise TransicionInvalida(f"La verificación ya está {v.estado_verificacion}")
    v.estado_verificacion = decision
    v.id_administrador = id_administrador
    v.fecha_resolucion = cuando or func.now()
    v.observaciones = observaciones
    db.flush()
    return v


# --- Auditoría (solo inserción) ------------------------------------------------

def registrar_auditoria(db: Session, entidad: str, id_registro: int, accion: str, id_usuario: int | None = None,
                        valor_anterior: str | None = None, valor_nuevo: str | None = None) -> RegistroAuditoria:
    fila = RegistroAuditoria(id_usuario=id_usuario, entidad_afectada=entidad, id_registro_afectado=id_registro,
                             accion_realizada=accion, valor_anterior=valor_anterior, valor_nuevo=valor_nuevo)
    db.add(fila)
    db.flush()
    return fila


def consultar_auditoria(db: Session, entidad: str | None = None, id_registro: int | None = None,
                        id_usuario: int | None = None, limite: int = 200) -> list[RegistroAuditoria]:
    consulta = select(RegistroAuditoria).order_by(RegistroAuditoria.id_auditoria.desc()).limit(limite)
    if entidad:
        consulta = consulta.where(RegistroAuditoria.entidad_afectada == entidad)
    if id_registro is not None:
        consulta = consulta.where(RegistroAuditoria.id_registro_afectado == id_registro)
    if id_usuario is not None:
        consulta = consulta.where(RegistroAuditoria.id_usuario == id_usuario)
    return list(db.scalars(consulta))
