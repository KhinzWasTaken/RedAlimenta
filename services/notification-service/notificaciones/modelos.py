"""Modelo de notification-service (Sprint 3, entidad 12). Los comentarios alimentan el diccionario de datos."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ESTADO_NOTIFICACION = Enum("NO_LEIDA", "LEIDA", "ARCHIVADA", name="estado_notificacion")
ESTADO_CONVERSACION = Enum("ABIERTA", "CERRADA", name="estado_conversacion")


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


class EventoProcesado(Base):
    """Añadido en el Sprint 6 (S6-05): eventos ya procesados por el consumidor, para no repetir efectos."""

    __tablename__ = "evento_procesado"
    __table_args__ = {"comment": "Idempotencia del consumidor: un id_evento se procesa una sola vez."}
    id_evento: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                                 comment="Identificador del evento recibido.")
    cola: Mapped[str] = mapped_column(String(60), comment="Cola de RabbitMQ que lo entregó.")
    fecha_proceso: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                    comment="Cuándo se procesó.")


class Conversacion(Base):
    """D-12: chat entre el donante y un receptor sobre una donación, para pactar la entrega y resolver dudas."""

    __tablename__ = "conversacion"
    __table_args__ = (
        UniqueConstraint("id_donacion", "id_receptor"),
        CheckConstraint("id_donante <> id_receptor", name="participantes_distintos"),
        CheckConstraint("(estado_conversacion = 'CERRADA') = (fecha_cierre IS NOT NULL)", name="cierre_fechado"),
        Index("ix_conversacion_donante", "id_donante"),
        Index("ix_conversacion_receptor", "id_receptor"),
        {"comment": "Chat donante–receptor de una donación. Se abre cuando el receptor la reserva o el donante "
                    "la ofrece para su solicitud; se cierra cuando la reserva o la donación terminan."},
    )
    id_conversacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_donacion: Mapped[int] = mapped_column(
        BigInteger, comment="Donación de la que se habla (catalog-geo; sin FK entre bases, D-06).")
    id_donante: Mapped[int] = mapped_column(BigInteger, comment="Donante (identity-service).")
    id_receptor: Mapped[int] = mapped_column(BigInteger, comment="Receptor (identity-service).")
    nombre_alimento: Mapped[str] = mapped_column(String(120), comment="Alimento, para mostrar la conversación.")
    origen: Mapped[str] = mapped_column(
        String(20), comment="RESERVA (el receptor la reservó) u OFERTA (el donante la ofreció a su solicitud).")
    estado_conversacion: Mapped[str] = mapped_column(
        ESTADO_CONVERSACION, server_default="ABIERTA", comment="ABIERTA (se puede escribir) o CERRADA (solo lectura).")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Cuándo se abrió.")
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="Cuándo se cerró.")
    ultimo_leido_donante: Mapped[int] = mapped_column(
        BigInteger, server_default="0", comment="Último id_mensaje que leyó el donante (para contar no leídos).")
    ultimo_leido_receptor: Mapped[int] = mapped_column(
        BigInteger, server_default="0", comment="Último id_mensaje que leyó el receptor.")


class Mensaje(Base):
    """D-12: mensajes del chat. Solo inserción: lo dicho queda como se dijo (trazabilidad de lo pactado)."""

    __tablename__ = "mensaje"
    __table_args__ = (
        CheckConstraint("length(trim(texto)) BETWEEN 1 AND 1000", name="texto_valido"),
        Index("ix_mensaje_conversacion", "id_conversacion", "id_mensaje"),
        {"comment": "Mensajes de cada conversación; no se modifican ni se borran."},
    )
    id_mensaje: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador (orden de envío).")
    id_conversacion: Mapped[int] = mapped_column(
        ForeignKey("conversacion.id_conversacion"), comment="Conversación a la que pertenece.")
    id_autor: Mapped[int] = mapped_column(BigInteger, comment="Quién lo escribió: el donante o el receptor.")
    texto: Mapped[str] = mapped_column(Text, comment="Contenido, de 1 a 1.000 caracteres.")
    fecha_envio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Cuándo se envió.")
