"""API de analytics-service (S5-15): trazabilidad por entidad y por usuario, solo para administradores."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from redalimenta_comun.app import dependencia_sesion
from redalimenta_comun.seguridad import Actor, requiere_rol

from . import repositorio as repo
from .db import sesiones

rutas = APIRouter(prefix="/api/historial", tags=["historial"])
obtener_db = dependencia_sesion(sesiones)
ADMIN = requiere_rol("ADMINISTRADOR")


@rutas.get("/entidades/{entidad}")
def por_entidad(entidad: str, id_entidad: int | None = None, tipo: str | None = None,
                limite: int = Query(500, le=5000), _: Actor = Depends(ADMIN), db: Session = Depends(obtener_db)):
    """Reconstruye la vida de una donación, reserva o entrega en orden cronológico."""
    return [repo.a_dict(h) for h in repo.por_entidad(db, entidad, id_entidad, tipo, limite)]


@rutas.get("/usuarios/{id_usuario}")
def por_usuario(id_usuario: int, limite: int = Query(500, le=5000), _: Actor = Depends(ADMIN),
                db: Session = Depends(obtener_db)):
    return [repo.a_dict(h) for h in repo.por_usuario(db, id_usuario, limite)]
