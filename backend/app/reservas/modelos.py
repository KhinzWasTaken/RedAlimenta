from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.estados import ESTADOS_CONFIRMACION, ESTADOS_ENTREGA, ESTADOS_RESERVA, check_sql
from app.core.tiempo import ahora


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (
        CheckConstraint(check_sql("estado_reserva", ESTADOS_RESERVA), name="ck_reserva_estado"),
        CheckConstraint("fecha_expiracion >= fecha_reserva", name="ck_reserva_expiracion"),
        # D-02: solo una reserva activa por donación
        Index("ux_reserva_activa", "id_donacion", unique=True,
              sqlite_where=text("estado_reserva IN ('PENDIENTE', 'CONFIRMADA')")),
    )
    id_reserva: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_donacion: Mapped[int] = mapped_column(Integer, index=True)  # D-06: sin FK al catálogo
    id_receptor: Mapped[int] = mapped_column(Integer, index=True)
    fecha_reserva: Mapped[datetime] = mapped_column(default=ahora)
    fecha_expiracion: Mapped[datetime]
    estado_reserva: Mapped[str] = mapped_column(String(20), default="PENDIENTE")


class Entrega(Base):
    __tablename__ = "entrega"
    __table_args__ = (CheckConstraint(check_sql("estado_entrega", ESTADOS_ENTREGA), name="ck_entrega_estado"),)
    id_entrega: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_reserva: Mapped[int] = mapped_column(ForeignKey("reserva.id_reserva"), unique=True)  # una por reserva
    fecha_programada: Mapped[datetime | None]
    fecha_entrega: Mapped[datetime | None]
    estado_entrega: Mapped[str] = mapped_column(String(20), default="PROGRAMADA")
    observaciones: Mapped[str | None] = mapped_column(Text)


class ConfirmacionEntrega(Base):
    __tablename__ = "confirmacion_entrega"
    __table_args__ = (
        UniqueConstraint("id_entrega", "id_usuario", name="ux_confirmacion_usuario"),
        CheckConstraint(check_sql("estado_confirmacion", ESTADOS_CONFIRMACION), name="ck_confirmacion_estado"),
    )
    id_confirmacion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_entrega: Mapped[int] = mapped_column(ForeignKey("entrega.id_entrega"))
    id_usuario: Mapped[int] = mapped_column(Integer)
    fecha_confirmacion: Mapped[datetime] = mapped_column(default=ahora)
    estado_confirmacion: Mapped[str] = mapped_column(String(20))
    observaciones: Mapped[str | None] = mapped_column(Text)
