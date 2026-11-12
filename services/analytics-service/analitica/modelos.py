"""Historial de eventos de analytics-service (S5-15). No es una entidad del Sprint 3: es el registro
de eventos que el documento asigna a analytics ("guarda eventos de auditoría", D-04) y la fuente de la
carga continua del almacén de datos (S7-05)."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HistorialEvento(Base):
    __tablename__ = "historial_evento"
    __table_args__ = (
        Index("ix_historial_entidad", "entidad", "id_entidad"),
        Index("ix_historial_actor", "id_actor"),
        Index("ix_historial_fecha", "fecha"),
        Index("ix_historial_datos", "datos", postgresql_using="gin"),
        {"comment": "Eventos de todos los servicios, tal como se publicaron. Solo inserción."},
    )
    id_evento: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, comment="Identificador del evento; repetido = mismo evento (idempotencia).")
    tipo: Mapped[str] = mapped_column(String(60), comment="Tipo: RESERVA_CREADA, ENTREGA_CONFIRMADA...")
    version: Mapped[int] = mapped_column(SmallInteger, comment="Versión del esquema del evento.")
    origen: Mapped[str] = mapped_column(String(40), comment="Servicio que lo publicó.")
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="Cuándo ocurrió (según el origen).")
    id_actor: Mapped[int | None] = mapped_column(BigInteger, comment="Usuario que lo provocó; NULL = sistema.")
    entidad: Mapped[str] = mapped_column(String(40), comment="Entidad afectada.")
    id_entidad: Mapped[int] = mapped_column(BigInteger, comment="Identificador del registro afectado.")
    estado_anterior: Mapped[str | None] = mapped_column(String(40), comment="Estado antes del cambio.")
    estado_nuevo: Mapped[str | None] = mapped_column(String(40), comment="Estado después del cambio.")
    datos: Mapped[dict] = mapped_column(JSONB, comment="Contexto del evento (participantes, alimento...).")
    id_correlacion: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="Operación que lo originó (S6-09); une eventos de varios servicios.")
    fecha_recepcion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Cuándo lo recibió analytics.")
