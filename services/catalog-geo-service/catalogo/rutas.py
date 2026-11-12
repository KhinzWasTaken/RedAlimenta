"""API REST de catalog-geo-service (S5-06, S5-07, S5-08) y API interna (S5-09)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.eventos import Lote
from redalimenta_comun.seguridad import (
    Actor, actor_actual, requiere_rol, requiere_servicio_interno, requiere_verificado,
)

from . import repositorio as repo
from . import servicio
from .db import sesiones
from .errores import ErrorDominio

rutas = APIRouter(prefix="/api")
internas = APIRouter(prefix="/internal", tags=["interno (solo servicios)"],
                     dependencies=[Depends(requiere_servicio_interno)])
obtener_db = dependencia_sesion(sesiones)


class Ubicacion(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    direccion_referencia: str | None = Field(default=None, max_length=200)
    ciudad: str = Field(min_length=2, max_length=80)
    departamento: str = Field(min_length=2, max_length=80)


class NuevaDonacion(BaseModel):
    nombre_alimento: str = Field(min_length=2, max_length=120)
    id_categoria: int
    cantidad: float = Field(gt=0)
    unidad_medida: str = Field(min_length=1, max_length=30)
    fecha_vencimiento: datetime | None = Field(default=None, description="Con zona horaria; NULL si no aplica")
    descripcion: str | None = None
    condiciones_recogida: str | None = None
    ubicacion: Ubicacion


class CambiosDonacion(BaseModel):
    nombre_alimento: str | None = Field(default=None, min_length=2, max_length=120)
    id_categoria: int | None = None
    cantidad: float | None = Field(default=None, gt=0)
    unidad_medida: str | None = Field(default=None, max_length=30)
    fecha_vencimiento: datetime | None = None
    descripcion: str | None = None
    condiciones_recogida: str | None = None


class NuevaNecesidad(BaseModel):
    descripcion: str = Field(min_length=2)
    id_categoria: int
    cantidad_requerida: float = Field(gt=0)
    unidad_medida: str = Field(min_length=1, max_length=30)
    nivel_urgencia: str = Field(description="BAJA, MEDIA, ALTA o CRITICA")
    fecha_limite: datetime | None = None
    ubicacion: Ubicacion


class CambiosNecesidad(BaseModel):
    descripcion: str | None = None
    cantidad_requerida: float | None = Field(default=None, gt=0)
    unidad_medida: str | None = None
    nivel_urgencia: str | None = None
    fecha_limite: datetime | None = None


class Categoria(BaseModel):
    nombre_categoria: str = Field(min_length=2, max_length=60)
    descripcion: str | None = Field(default=None, max_length=200)


class Transicion(BaseModel):
    estado: str
    id_actor: int | None = None
    datos: dict = Field(default_factory=dict, description="Contexto que viaja en el evento (p. ej. id_receptor)")


def _plano(u: Ubicacion) -> dict:
    return {"lat": u.lat, "lon": u.lon, "direccion": u.direccion_referencia, "ciudad": u.ciudad,
            "departamento": u.departamento}


def _confirmar(db: Session, lote: Lote) -> None:
    db.commit()
    lote.publicar()


# --- Categorías (S5-20) --------------------------------------------------------

@rutas.get("/categorias", tags=["categorías"])
def categorias(_: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return [{"id_categoria": c.id_categoria, "nombre_categoria": c.nombre_categoria, "descripcion": c.descripcion}
            for c in repo.listar_categorias(db)]


@rutas.post("/admin/categorias", status_code=201, tags=["categorías"])
def crear_categoria(datos: Categoria, _: Actor = Depends(requiere_rol("ADMINISTRADOR")),
                    db: Session = Depends(obtener_db)):
    c = repo.crear_categoria(db, datos.nombre_categoria, datos.descripcion)
    db.commit()
    return {"id_categoria": c.id_categoria, "nombre_categoria": c.nombre_categoria, "descripcion": c.descripcion}


@rutas.patch("/admin/categorias/{id_categoria}", tags=["categorías"])
def editar_categoria(id_categoria: int, datos: Categoria, _: Actor = Depends(requiere_rol("ADMINISTRADOR")),
                     db: Session = Depends(obtener_db)):
    c = repo.actualizar_categoria(db, id_categoria, datos.nombre_categoria, datos.descripcion)
    db.commit()
    return {"id_categoria": c.id_categoria, "nombre_categoria": c.nombre_categoria, "descripcion": c.descripcion}


# --- Donaciones (S5-06) --------------------------------------------------------

@rutas.post("/donaciones", status_code=201, tags=["donaciones"])
def publicar(datos: NuevaDonacion, actor: Actor = Depends(requiere_verificado("DONANTE")),
             db: Session = Depends(obtener_db)):
    lote = Lote("catalog-geo")
    valores = datos.model_dump(exclude={"ubicacion"}) | _plano(datos.ubicacion)
    id_donacion = servicio.crear_donacion(db, lote, actor.id_usuario, valores)
    _confirmar(db, lote)
    return servicio.una_donacion(db, id_donacion)


@rutas.get("/donaciones/mias", tags=["donaciones"])
def mis_donaciones(actor: Actor = Depends(requiere_rol("DONANTE")), db: Session = Depends(obtener_db)):
    return [servicio.donacion_api(d) for d in repo.detalle_donaciones(db, id_donante=actor.id_usuario)]


@rutas.get("/donaciones/disponibles", tags=["búsqueda"])
def disponibles(lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
                id_necesidad: int | None = None, id_categoria: int | None = None,
                radio_km: float | None = Query(None, gt=0, le=200), cantidad_minima: float | None = None,
                vence_antes: datetime | None = None, orden: str = Query("prioridad", pattern="^(prioridad|distancia)$"),
                actor: Actor = Depends(requiere_rol("RECEPTOR")), db: Session = Depends(obtener_db)):
    """RF4: disponibles y vigentes cerca de un punto (D-07), con distancia y puntaje (D-08), listas para el mapa."""
    return servicio.buscar(db, actor.id_usuario, lat=lat, lon=lon, id_necesidad=id_necesidad,
                           id_categoria=id_categoria, radio_m=radio_km * 1000 if radio_km else None,
                           cantidad_minima=cantidad_minima, vence_antes=vence_antes, orden=orden)


@rutas.get("/donaciones/{id_donacion}", tags=["donaciones"])
def ver_donacion(id_donacion: int, _: Actor = Depends(actor_actual), db: Session = Depends(obtener_db)):
    return servicio.una_donacion(db, id_donacion)


@rutas.patch("/donaciones/{id_donacion}", tags=["donaciones"])
def modificar(id_donacion: int, cambios: CambiosDonacion, actor: Actor = Depends(requiere_verificado("DONANTE")),
              db: Session = Depends(obtener_db)):
    valores = cambios.model_dump(exclude_none=True)
    if not valores:
        raise ErrorDominio("No hay cambios")
    lote = Lote("catalog-geo")
    servicio.actualizar_donacion(db, lote, id_donacion, actor.id_usuario, valores)
    _confirmar(db, lote)
    return servicio.una_donacion(db, id_donacion)


@rutas.post("/donaciones/{id_donacion}/cancelar", tags=["donaciones"])
def cancelar(id_donacion: int, actor: Actor = Depends(requiere_verificado("DONANTE")),
             db: Session = Depends(obtener_db)):
    lote = Lote("catalog-geo")
    donacion = servicio.cancelar_donacion(db, lote, id_donacion, actor.id_usuario)
    _confirmar(db, lote)
    return donacion


# --- Necesidades (S5-07) -------------------------------------------------------

@rutas.get("/necesidades/mias", tags=["necesidades"])
def mis_necesidades(actor: Actor = Depends(requiere_rol("RECEPTOR")), db: Session = Depends(obtener_db)):
    return [servicio.necesidad_api(n) for n in repo.detalle_necesidades(db, id_receptor=actor.id_usuario)]


@rutas.post("/necesidades", status_code=201, tags=["necesidades"])
def registrar_necesidad(datos: NuevaNecesidad, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
                        db: Session = Depends(obtener_db)):
    lote = Lote("catalog-geo")
    valores = datos.model_dump(exclude={"ubicacion"}) | _plano(datos.ubicacion)
    id_necesidad = servicio.crear_necesidad(db, lote, actor.id_usuario, valores)
    _confirmar(db, lote)
    return servicio.una_necesidad(db, id_necesidad)


@rutas.patch("/necesidades/{id_necesidad}", tags=["necesidades"])
def ajustar(id_necesidad: int, cambios: CambiosNecesidad, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
            db: Session = Depends(obtener_db)):
    valores = cambios.model_dump(exclude_none=True)
    if not valores:
        raise ErrorDominio("No hay cambios")
    lote = Lote("catalog-geo")
    servicio.ajustar_necesidad(db, lote, id_necesidad, actor.id_usuario, valores)
    _confirmar(db, lote)
    return servicio.una_necesidad(db, id_necesidad)


@rutas.post("/necesidades/{id_necesidad}/{accion}", tags=["necesidades"])
def cerrar(id_necesidad: int, accion: str, actor: Actor = Depends(requiere_verificado("RECEPTOR")),
           db: Session = Depends(obtener_db)):
    estado = {"cerrar": "CERRADA", "cancelar": "CANCELADA"}.get(accion)
    if estado is None:
        raise ErrorDominio("Acción no válida: usa cerrar o cancelar")
    lote = Lote("catalog-geo")
    servicio.cerrar_necesidad(db, lote, id_necesidad, actor.id_usuario, estado)
    _confirmar(db, lote)
    return servicio.una_necesidad(db, id_necesidad)


# --- API interna (S5-09): solo otros servicios, con X-Token-Interno ------------

@internas.get("/donaciones")
def donaciones_internas(ids: str | None = None, id_donante: int | None = None, estado: str | None = None,
                        db: Session = Depends(obtener_db)):
    lista = [int(x) for x in ids.split(",") if x.strip().isdigit()] if ids else None
    return [servicio.donacion_api(d) for d in repo.detalle_donaciones(db, ids=lista, id_donante=id_donante,
                                                                     estado=estado)]


@internas.post("/donaciones/{id_donacion}/transiciones")
def transicion(id_donacion: int, datos: Transicion, db: Session = Depends(obtener_db)):
    """D-01: fulfillment pide cada cambio de estado; aquí se valida (409 si es ilegal) y se anuncia."""
    lote = Lote("catalog-geo")
    anterior, donacion = servicio.transicionar(db, lote, id_donacion, datos.estado, datos.id_actor, datos.datos)
    _confirmar(db, lote)
    return {"estado_anterior": anterior, "donacion": donacion}


@internas.post("/tareas/vencer")
def vencer(db: Session = Depends(obtener_db)):
    """RF8: la tarea programada de fulfillment pide marcar VENCIDA lo que pasó su fecha."""
    lote = Lote("catalog-geo")
    ids = servicio.vencer(db, lote)
    _confirmar(db, lote)
    return {"vencidas": ids}


@internas.get("/donaciones-por-vencer")
def por_vencer(horas: float = 24, db: Session = Depends(obtener_db)):
    return [{**d, "fecha_vencimiento": d["fecha_vencimiento"].isoformat()}
            for d in repo.donaciones_por_vencer(db, horas)]
