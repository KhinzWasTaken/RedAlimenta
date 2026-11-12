"""Modelo de fulfillment-service (Sprint 3, entidades 9–11). Los comentarios alimentan el diccionario de datos."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ESTADO_RESERVA = Enum("PENDIENTE", "CONFIRMADA", "EXPIRADA", "COMPLETADA", "CANCELADA", name="estado_reserva")
ESTADO_ENTREGA = Enum("PROGRAMADA", "COMPLETADA", "CON_INCIDENCIA", "CANCELADA", name="estado_entrega")
ESTADO_CONFIRMACION = Enum("CONFIRMADA", "CON_INCIDENCIA", name="estado_confirmacion")
TS = DateTime(timezone=True)


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (
        CheckConstraint("fecha_expiracion > fecha_reserva", name="expira_despues_de_reservar"),
        # D-02: solo una reserva activa por donación; gana quien inserta primero
        Index("ux_reserva_activa", "id_donacion", unique=True,
              postgresql_where=text("estado_reserva IN ('PENDIENTE', 'CONFIRMADA')")),
        # Tarea de expiración (RF8): solo recorre las pendientes
        Index("ix_reserva_pendiente_expiracion", "fecha_expiracion",
              postgresql_where=text("estado_reserva = 'PENDIENTE'")),
        {"comment": "Solicitudes de reserva; cubren la donación completa (D-05)."},
    )
    id_reserva: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_donacion: Mapped[int] = mapped_column(
        BigInteger, index=True, comment="Donación reservada (catalog-geo-service; sin FK entre bases, D-06).")
    id_receptor: Mapped[int] = mapped_column(
        BigInteger, index=True, comment="Usuario receptor (identity-service; sin FK entre bases, D-06).")
    fecha_reserva: Mapped[datetime] = mapped_column(TS, server_default=func.now(), comment="Cuándo se reservó.")
    fecha_expiracion: Mapped[datetime] = mapped_column(
        TS, comment="Plazo para que el donante confirme (D-09: 2 horas por defecto).")
    estado_reserva: Mapped[str] = mapped_column(
        ESTADO_RESERVA, server_default="PENDIENTE",
        comment="PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA o CANCELADA.")


class Entrega(Base):
    __tablename__ = "entrega"
    __table_args__ = (
        CheckConstraint("estado_entrega <> 'COMPLETADA' OR fecha_entrega IS NOT NULL", name="completada_fechada"),
        {"comment": "Entrega de una reserva confirmada; una por reserva."},
    )
    id_entrega: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_reserva: Mapped[int] = mapped_column(
        ForeignKey("reserva.id_reserva"), unique=True, comment="Reserva que se entrega (una entrega por reserva).")
    fecha_programada: Mapped[datetime | None] = mapped_column(TS, comment="Cuándo se acordó entregar.")
    fecha_entrega: Mapped[datetime | None] = mapped_column(TS, comment="Cuándo se completó la entrega.")
    estado_entrega: Mapped[str] = mapped_column(
        ESTADO_ENTREGA, server_default="PROGRAMADA", comment="PROGRAMADA, COMPLETADA, CON_INCIDENCIA o CANCELADA.")
    observaciones: Mapped[str | None] = mapped_column(Text, comment="Notas o descripción de la incidencia.")


class ConfirmacionEntrega(Base):
    __tablename__ = "confirmacion_entrega"
    __table_args__ = (
        UniqueConstraint("id_entrega", "id_usuario"),  # máximo una confirmación por usuario y entrega
        {"comment": "Confirmación bilateral: la donación queda ENTREGADA con la del donante y la del receptor."},
    )
    id_confirmacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_entrega: Mapped[int] = mapped_column(
        ForeignKey("entrega.id_entrega"), index=True, comment="Entrega que se confirma.")
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, comment="Donante o receptor que confirma (identity-service; sin FK entre bases, D-06).")
    fecha_confirmacion: Mapped[datetime] = mapped_column(TS, server_default=func.now(), comment="Cuándo confirmó.")
    estado_confirmacion: Mapped[str] = mapped_column(ESTADO_CONFIRMACION, comment="CONFIRMADA o CON_INCIDENCIA.")
    observaciones: Mapped[str | None] = mapped_column(Text, comment="Comentario o detalle de la incidencia.")


class AvisoVencimiento(Base):
    """Añadido en el Sprint 5 (no está en el modelo del Sprint 3): memoria de la tarea de avisos.

    Hace idempotente el aviso DONACION_POR_VENCER (S5-13): una donación se avisa una sola vez.
    """

    __tablename__ = "aviso_vencimiento"
    __table_args__ = {"comment": "Donaciones ya avisadas como por vencer (idempotencia de la tarea RF8)."}
    id_donacion: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False,
        comment="Donación avisada (catalog-geo-service; sin FK entre bases, D-06).")
    fecha_aviso: Mapped[datetime] = mapped_column(TS, server_default=func.now(), comment="Cuándo se avisó.")
