from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.estados import ESTADOS_NOTIFICACION, check_sql
from app.core.tiempo import ahora


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = (
        CheckConstraint(check_sql("estado_notificacion", ESTADOS_NOTIFICACION), name="ck_notificacion_estado"),
        Index("ix_notificacion_usuario_estado", "id_usuario", "estado_notificacion"),
    )
    id_notificacion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False)  # sin usuario no hay notificación
    tipo_notificacion: Mapped[str] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(Text)
    fecha_creacion: Mapped[datetime] = mapped_column(default=ahora)
    fecha_lectura: Mapped[datetime | None]
    estado_notificacion: Mapped[str] = mapped_column(String(20), default="NO_LEIDA")
