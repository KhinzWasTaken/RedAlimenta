"""Modelo de notification-service (Sprint 3, entidad 12). Los comentarios alimentan el diccionario de datos."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ESTADO_NOTIFICACION = Enum("NO_LEIDA", "LEIDA", "ARCHIVADA", name="estado_notificacion")


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = (
        CheckConstraint("estado_notificacion <> 'LEIDA' OR fecha_lectura IS NOT NULL", name="leida_fechada"),
        CheckConstraint("length(trim(mensaje)) > 0", name="mensaje_no_vacio"),
        # Bandeja y contador de no leídas de cada usuario
        Index("ix_notificacion_usuario_estado", "id_usuario", "estado_notificacion"),
        {"comment": "Avisos in-app generados por los eventos de los demás servicios."},
    )
    id_notificacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, comment="Destinatario (identity-service; sin FK entre bases, D-06). Obligatorio.")
    tipo_notificacion: Mapped[str] = mapped_column(
        String(60), comment="Evento que la originó: RESERVA_CREADA, ENTREGA_CONFIRMADA...")
    mensaje: Mapped[str] = mapped_column(Text, comment="Texto para el usuario.")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Cuándo se generó.")
    fecha_lectura: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Cuándo la leyó el usuario.")
    estado_notificacion: Mapped[str] = mapped_column(
        ESTADO_NOTIFICACION, server_default="NO_LEIDA", comment="NO_LEIDA, LEIDA o ARCHIVADA.")
