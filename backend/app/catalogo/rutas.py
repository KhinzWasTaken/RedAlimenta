from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import obtener_db
from app.core.errores import NoEncontrado
from app.core.seguridad import Actor, actor_actual, requiere_rol, requiere_verificado
from app.core.tiempo import a_utc

from . import servicio

rutas = APIRouter(prefix="/api", tags=["catalogo"])


class UbicacionEntrada(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    direccion_referencia: str | None = None
    ciudad: str | None = "Bogotá"
    departamento: str | None = "Cundinamarca"


class DonacionEntrada(BaseModel):
    nombre_alimento: str = Field(min_length=2, max_length=120)
    descripcion: str | None = None
    id_categoria: int
    cantidad: float = Field(gt=0)
    unidad_medida: str = Field(min_length=1, max_length=30)
    fecha_vencimiento: datetime
    condiciones_recogida: str | None = None
    ubicacion: UbicacionEntrada


class DonacionCambios(BaseModel):
    nombre_alimento: str | None = None
    descripcion: str | None = None
    cantidad: float | None = Field(default=None, gt=0)
    unidad_medida: str | None = None
    fecha_vencimiento: datetime | None = None
    condiciones_recogida: str | None = None


class NecesidadEntrada(BaseModel):
    descripcion: str = Field(min_length=2)
    id_categoria: int
    cantidad_requerida: float = Field(gt=0)
    unidad_medida: str
    nivel_urgencia: str
    fecha_limite: datetime | None = None
    ubicacion: UbicacionEntrada


@rutas.get("/categorias")
def categorias(_: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return servicio.listar_categorias(db)


@rutas.post("/donaciones", status_code=201)
def crear_donacion(datos: DonacionEntrada, actor: Actor = Depends(requiere_verificado("DONANTE")),
                   db: Session = Depends(obtener_db)):
    valores = datos.model_dump()
    valores["fecha_vencimiento"] = a_utc(datos.fecha_vencimiento)
    d = servicio.crear_donacion(db, actor, valores)
    db.commit()
    return servicio.donacion_dict(db, d)


@rutas.get("/donaciones/mias")
def mis_donaciones(actor: Actor = Depends(requiere_rol("DONANTE")), db: Session = Depends(obtener_db)):
    return servicio.donaciones_de(db, actor.id_usuario)


@rutas.get("/donaciones/disponibles")
def disponibles(lat: float | None = None, lon: float | None = None, id_necesidad: int | None = None,
                id_categoria: int | None = None, radio_km: float | None = None, orden: str = "prioridad",
                actor: Actor = Depends(requiere_rol("RECEPTOR")), db: Session = Depends(obtener_db)):
    return servicio.buscar_disponibles(db, actor, lat, lon, id_necesidad, id_categoria, radio_km, orden)


@rutas.patch("/donaciones/{id_donacion}")
def actualizar(id_donacion: int, cambios: DonacionCambios,
               actor: Actor = Depends(requiere_verificado("DONANTE")), db: Session = Depends(obtener_db)):
    valores = cambios.model_dump()
    if cambios.fecha_vencimiento:
        valores["fecha_vencimiento"] = a_utc(cambios.fecha_vencimiento)
    d = servicio.actualizar_donacion(db, id_donacion, actor, valores)
    db.commit()
    return servicio.donacion_dict(db, d)


@rutas.post("/donaciones/{id_donacion}/cancelar")
def cancelar(id_donacion: int, actor: Actor = Depends(requiere_verificado("DONANTE")),
             db: Session = Depends(obtener_db)):
    d = servicio.cancelar_donacion(db, id_donacion, actor)
    db.commit()
    return servicio.donacion_dict(db, d)


@rutas.get("/necesidades/mias")
def mis_necesidades(actor: Actor = Depends(requiere_rol("RECEPTOR")), db: Session = Depends(obtener_db)):
    return servicio.necesidades_de(db, actor.id_usuario)


@rutas.post("/necesidades", status_code=201)
def crear_necesidad(datos: NecesidadEntrada, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
                    db: Session = Depends(obtener_db)):
    valores = datos.model_dump()
    valores["fecha_limite"] = a_utc(datos.fecha_limite) if datos.fecha_limite else None
    n = servicio.crear_necesidad(db, actor, valores)
    db.commit()
    return servicio.necesidad_dict(db, n)


@rutas.post("/necesidades/{id_necesidad}/{accion}")
def cerrar_necesidad(id_necesidad: int, accion: str, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
                     db: Session = Depends(obtener_db)):
    nuevo = {"cerrar": "CERRADA", "cancelar": "CANCELADA"}.get(accion)
    if nuevo is None:
        raise NoEncontrado("Acción no válida")
    n = servicio.cambiar_estado_necesidad(db, id_necesidad, nuevo, actor)
    db.commit()
    return servicio.necesidad_dict(db, n)
