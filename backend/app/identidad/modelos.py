from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.estados import ESTADOS_CUENTA, ESTADOS_VERIFICACION, check_sql
from app.core.tiempo import ahora


class Rol(Base):
    __tablename__ = "rol"
    id_rol: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre_rol: Mapped[str] = mapped_column(String(30), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(200))


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint(check_sql("estado_cuenta", ESTADOS_CUENTA), name="ck_usuario_estado"),)
    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol"))
    nombre: Mapped[str] = mapped_column(String(120))
    correo_electronico: Mapped[str] = mapped_column(String(120), unique=True)
    contrasena_hash: Mapped[str] = mapped_column(String(200))
    telefono: Mapped[str | None] = mapped_column(String(30))
    estado_cuenta: Mapped[str] = mapped_column(String(20), default="ACTIVA")
    fecha_registro: Mapped[datetime] = mapped_column(default=ahora)


class VerificacionUsuario(Base):
    __tablename__ = "verificacion_usuario"
    __table_args__ = (
        CheckConstraint(check_sql("estado_verificacion", ESTADOS_VERIFICACION), name="ck_verificacion_estado"),
    )
    id_verificacion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), index=True)
    id_administrador: Mapped[int | None] = mapped_column(ForeignKey("usuario.id_usuario"))
    estado_verificacion: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    fecha_solicitud: Mapped[datetime] = mapped_column(default=ahora)
    fecha_resolucion: Mapped[datetime | None]
    observaciones: Mapped[str | None] = mapped_column(Text)


class RegistroAuditoria(Base):
    """Solo inserción (D-04): los disparadores de abajo bloquean UPDATE y DELETE."""

    __tablename__ = "registro_auditoria"
    id_auditoria: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int | None] = mapped_column(Integer)  # actor; NULL = sistema
    entidad_afectada: Mapped[str] = mapped_column(String(40), index=True)
    id_registro_afectado: Mapped[int] = mapped_column(Integer, index=True)
    accion_realizada: Mapped[str] = mapped_column(String(40))
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_nuevo: Mapped[str | None] = mapped_column(Text)
    fecha_operacion: Mapped[datetime] = mapped_column(default=ahora)


for _accion in ("UPDATE", "DELETE"):
    event.listen(
        RegistroAuditoria.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER trg_auditoria_no_{_accion.lower()} BEFORE {_accion} ON registro_auditoria "
            f"BEGIN SELECT RAISE(ABORT, 'registro_auditoria es de solo inserción'); END;"
        ),
    )
