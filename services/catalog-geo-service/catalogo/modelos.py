"""Modelo de catalog-geo-service (Sprint 3, entidades 5–8). Los comentarios alimentan el diccionario de datos."""
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ESTADO_DONACION = Enum("DISPONIBLE", "RESERVADA", "ENTREGADA", "CANCELADA", "VENCIDA", name="estado_donacion")
ESTADO_NECESIDAD = Enum("ABIERTA", "CERRADA", "CANCELADA", name="estado_necesidad")
NIVEL_URGENCIA = Enum("BAJA", "MEDIA", "ALTA", "CRITICA", name="nivel_urgencia")
TS = DateTime(timezone=True)


class CategoriaAlimento(Base):
    __tablename__ = "categoria_alimento"
    __table_args__ = {"comment": "Clasificación de los alimentos de donaciones y necesidades."}
    id_categoria: Mapped[int] = mapped_column(SmallInteger, primary_key=True, comment="Identificador.")
    nombre_categoria: Mapped[str] = mapped_column(String(60), unique=True, comment="Nombre único de la categoría.")
    descripcion: Mapped[str | None] = mapped_column(String(200), comment="Qué alimentos incluye.")


class UbicacionGeografica(Base):
    __tablename__ = "ubicacion_geografica"
    __table_args__ = (
        Index("ix_ubicacion_coordenada", "coordenada_geografica", postgresql_using="gist"),
        {"comment": "Puntos de recogida (donaciones) y de entrega (necesidades)."},
    )
    id_ubicacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    direccion_referencia: Mapped[str | None] = mapped_column(
        String(200), comment="Dirección escrita como referencia; el punto manda.")
    ciudad: Mapped[str] = mapped_column(String(80), comment="Ciudad o municipio.")
    departamento: Mapped[str] = mapped_column(String(80), comment="Departamento de Colombia.")
    coordenada_geografica: Mapped[str] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False), comment="Punto WGS84 (SRID 4326); distancias en metros.")


class Donacion(Base):
    __tablename__ = "donacion"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("fecha_vencimiento IS NULL OR fecha_vencimiento > fecha_publicacion",
                        name="vence_despues_de_publicar"),
        {"comment": "Alimentos ofrecidos por los donantes. Solo este servicio cambia estado_donacion (D-01)."},
    )
    id_donacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_donante: Mapped[int] = mapped_column(
        BigInteger, index=True, comment="Usuario donante (identity-service; sin FK entre bases, D-06).")
    id_categoria: Mapped[int] = mapped_column(
        ForeignKey("categoria_alimento.id_categoria"), index=True, comment="Categoría del alimento.")
    id_ubicacion: Mapped[int] = mapped_column(
        ForeignKey("ubicacion_geografica.id_ubicacion"), index=True, comment="Punto de recogida.")
    nombre_alimento: Mapped[str] = mapped_column(String(120), comment="Qué se dona.")
    descripcion: Mapped[str | None] = mapped_column(Text, comment="Detalle del alimento.")
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="Cantidad ofrecida; mayor que cero.")
    unidad_medida: Mapped[str] = mapped_column(String(30), comment="kg, litros, unidades, porciones...")
    fecha_vencimiento: Mapped[datetime | None] = mapped_column(
        TS, comment="Hasta cuándo es apto; NULL si no aplica (p. ej. agua embotellada).")
    fecha_publicacion: Mapped[datetime] = mapped_column(TS, server_default=func.now(), comment="Cuándo se publicó.")
    condiciones_recogida: Mapped[str | None] = mapped_column(Text, comment="Horario, cadena de frío, acceso...")
    estado_donacion: Mapped[str] = mapped_column(
        ESTADO_DONACION, server_default="DISPONIBLE", index=True,
        comment="DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA o VENCIDA.")


class NecesidadAlimentaria(Base):
    __tablename__ = "necesidad_alimentaria"
    __table_args__ = (
        CheckConstraint("cantidad_requerida > 0", name="cantidad_positiva"),
        {"comment": "Lo que necesitan los receptores; alimenta la búsqueda y la prioridad (D-05)."},
    )
    id_necesidad: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="Identificador.")
    id_receptor: Mapped[int] = mapped_column(
        BigInteger, index=True, comment="Usuario receptor (identity-service; sin FK entre bases, D-06).")
    id_categoria: Mapped[int] = mapped_column(
        ForeignKey("categoria_alimento.id_categoria"), index=True, comment="Tipo de alimento requerido.")
    id_ubicacion: Mapped[int] = mapped_column(
        ForeignKey("ubicacion_geografica.id_ubicacion"), index=True, comment="Dónde se atiende a la población.")
    descripcion: Mapped[str] = mapped_column(Text, comment="Qué se necesita y para quién.")
    cantidad_requerida: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="Cantidad requerida; mayor que cero.")
    unidad_medida: Mapped[str] = mapped_column(String(30), comment="kg, litros, unidades, porciones...")
    nivel_urgencia: Mapped[str] = mapped_column(NIVEL_URGENCIA, comment="BAJA, MEDIA, ALTA o CRITICA.")
    fecha_limite: Mapped[datetime | None] = mapped_column(TS, comment="Hasta cuándo se necesita.")
    estado_necesidad: Mapped[str] = mapped_column(
        ESTADO_NECESIDAD, server_default="ABIERTA", comment="ABIERTA, CERRADA o CANCELADA.")
