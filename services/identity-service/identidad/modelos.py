"""Modelo de identity-service (Sprint 3, entidades 1–4). Los comentarios alimentan el diccionario de datos."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ESTADO_CUENTA = Enum("ACTIVA", "DESACTIVADA", name="estado_cuenta")
ESTADO_VERIFICACION = Enum("PENDIENTE", "APROBADA", "RECHAZADA", name="estado_verificacion")
AHORA = func.now()


class Rol(Base):
    __tablename__ = "rol"
    __table_args__ = {"comment": "Tipos de usuario y sus permisos: DONANTE, RECEPTOR, ADMINISTRADOR."}
    id_rol: Mapped[int] = mapped_column(SmallInteger, primary_key=True, comment="Identificador del rol.")
    nombre_rol: Mapped[str] = mapped_column(String(30), unique=True, comment="Nombre único del rol.")
    descripcion: Mapped[str | None] = mapped_column(String(200), comment="Qué puede hacer el rol.")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("correo_electronico LIKE '%_@_%'", name="correo_valido"),
        Index("ux_usuario_correo", text("lower(correo_electronico)"), unique=True),
        {"comment": "Personas y organizaciones registradas (donantes, receptores, administradores)."},
    )
    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador del usuario.")
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol"), index=True, comment="Rol del usuario.")
    nombre: Mapped[str] = mapped_column(String(120), comment="Nombre de la persona u organización.")
    correo_electronico: Mapped[str] = mapped_column(
        String(254), comment="Correo de inicio de sesión; único sin distinguir mayúsculas.")
    contrasena_hash: Mapped[str] = mapped_column(
        String(255), comment="Hash PBKDF2-SHA256 de la contraseña; nunca la contraseña en claro.")
    telefono: Mapped[str | None] = mapped_column(String(30), comment="Teléfono de contacto (dato personal).")
    estado_cuenta: Mapped[str] = mapped_column(
        ESTADO_CUENTA, server_default="ACTIVA", comment="ACTIVA o DESACTIVADA; desactivar no borra la fila.")
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=AHORA, comment="Fecha de creación de la cuenta.")


class VerificacionUsuario(Base):
    __tablename__ = "verificacion_usuario"
    __table_args__ = (
        CheckConstraint("(estado_verificacion = 'PENDIENTE') = (fecha_resolucion IS NULL)", name="resolucion_fechada"),
        CheckConstraint("estado_verificacion = 'PENDIENTE' OR id_administrador IS NOT NULL",
                        name="resolucion_con_administrador"),
        Index("ux_verificacion_pendiente", "id_usuario", unique=True,
              postgresql_where=text("estado_verificacion = 'PENDIENTE'")),
        {"comment": "Procesos de verificación de identidad; solo un administrador los resuelve."},
    )
    id_verificacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), index=True, comment="Usuario que se verifica.")
    id_administrador: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario"), comment="Administrador que resolvió; NULL mientras está PENDIENTE.")
    estado_verificacion: Mapped[str] = mapped_column(
        ESTADO_VERIFICACION, server_default="PENDIENTE", comment="PENDIENTE, APROBADA o RECHAZADA.")
    fecha_solicitud: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=AHORA, comment="Cuándo se solicitó.")
    fecha_resolucion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Cuándo se resolvió; NULL mientras está PENDIENTE.")
    observaciones: Mapped[str | None] = mapped_column(Text, comment="Motivo de la decisión.")


class RegistroAuditoria(Base):
    __tablename__ = "registro_auditoria"
    __table_args__ = (
        Index("ix_auditoria_entidad", "entidad_afectada", "id_registro_afectado"),
        {"comment": "Historial de operaciones y cambios de estado de todos los servicios (D-04). Solo inserción."},
    )
    id_auditoria: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_usuario: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario"), index=True, comment="Quién hizo la operación; NULL = sistema.")
    entidad_afectada: Mapped[str] = mapped_column(String(40), comment="Entidad: donacion, reserva, entrega...")
    id_registro_afectado: Mapped[int] = mapped_column(BigInteger, comment="Identificador del registro afectado.")
    accion_realizada: Mapped[str] = mapped_column(String(60), comment="Acción o tipo de evento.")
    valor_anterior: Mapped[str | None] = mapped_column(Text, comment="Estado o valor antes del cambio.")
    valor_nuevo: Mapped[str | None] = mapped_column(Text, comment="Estado o valor después del cambio.")
    fecha_operacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=AHORA, comment="Cuándo ocurrió.")


class EventoProcesado(Base):
    """Añadido en el Sprint 6 (S6-05): eventos ya procesados por el consumidor, para no repetir efectos."""

    __tablename__ = "evento_procesado"
    __table_args__ = {"comment": "Idempotencia del consumidor: un id_evento se procesa una sola vez."}
    id_evento: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                                 comment="Identificador del evento recibido.")
    cola: Mapped[str] = mapped_column(String(60), comment="Cola de RabbitMQ que lo entregó.")
    fecha_proceso: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                    comment="Cuándo se procesó.")
