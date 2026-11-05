from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.estados import ESTADOS_DONACION, ESTADOS_NECESIDAD, NIVELES_URGENCIA, check_sql
from app.core.tiempo import ahora


class CategoriaAlimento(Base):
    __tablename__ = "categoria_alimento"
    id_categoria: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre_categoria: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(200))


class UbicacionGeografica(Base):
    """`coordenada_geografica` (PostGIS) se guarda como latitud/longitud en SQLite."""

    __tablename__ = "ubicacion_geografica"
    __table_args__ = (
        CheckConstraint("latitud BETWEEN -90 AND 90", name="ck_ubicacion_lat"),
        CheckConstraint("longitud BETWEEN -180 AND 180", name="ck_ubicacion_lon"),
    )
    id_ubicacion: Mapped[int] = mapped_column(Integer, primary_key=True)
    direccion_referencia: Mapped[str | None] = mapped_column(String(200))
    ciudad: Mapped[str] = mapped_column(String(80), default="Bogotá")
    departamento: Mapped[str] = mapped_column(String(80), default="Cundinamarca")
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)


class Donacion(Base):
    __tablename__ = "donacion"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_donacion_cantidad"),
        CheckConstraint("fecha_vencimiento > fecha_publicacion", name="ck_donacion_vencimiento"),
        CheckConstraint(check_sql("estado_donacion", ESTADOS_DONACION), name="ck_donacion_estado"),
    )
    id_donacion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_donante: Mapped[int] = mapped_column(Integer, index=True)  # D-06: sin FK a otro módulo
    id_categoria: Mapped[int] = mapped_column(ForeignKey("categoria_alimento.id_categoria"))
    id_ubicacion: Mapped[int] = mapped_column(ForeignKey("ubicacion_geografica.id_ubicacion"))
    nombre_alimento: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(Text)
    cantidad: Mapped[float] = mapped_column(Float)
    unidad_medida: Mapped[str] = mapped_column(String(30))
    fecha_vencimiento: Mapped[datetime]
    fecha_publicacion: Mapped[datetime] = mapped_column(default=ahora)
    condiciones_recogida: Mapped[str | None] = mapped_column(Text)
    estado_donacion: Mapped[str] = mapped_column(String(20), default="DISPONIBLE", index=True)


class NecesidadAlimentaria(Base):
    __tablename__ = "necesidad_alimentaria"
    __table_args__ = (
        CheckConstraint("cantidad_requerida > 0", name="ck_necesidad_cantidad"),
        CheckConstraint(check_sql("nivel_urgencia", NIVELES_URGENCIA), name="ck_necesidad_urgencia"),
        CheckConstraint(check_sql("estado_necesidad", ESTADOS_NECESIDAD), name="ck_necesidad_estado"),
    )
    id_necesidad: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_receptor: Mapped[int] = mapped_column(Integer, index=True)
    id_categoria: Mapped[int] = mapped_column(ForeignKey("categoria_alimento.id_categoria"))
    id_ubicacion: Mapped[int] = mapped_column(ForeignKey("ubicacion_geografica.id_ubicacion"))
    descripcion: Mapped[str] = mapped_column(Text)
    cantidad_requerida: Mapped[float] = mapped_column(Float)
    unidad_medida: Mapped[str] = mapped_column(String(30))
    nivel_urgencia: Mapped[str] = mapped_column(String(10))
    fecha_limite: Mapped[datetime | None]
    estado_necesidad: Mapped[str] = mapped_column(String(20), default="ABIERTA")
