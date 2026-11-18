"""JWT firmado por identity-service y validado por todos los servicios (D-06), y autenticación interna.

- El token lleva id_usuario (sub), rol y estado de verificación, con vigencia corta.
- Las rutas internas (servicio a servicio, p. ej. la transición de una donación, D-01) exigen la cabecera
  X-Token-Interno, que solo conocen los servicios. El gateway (Sprint 6) no las expone.
"""
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errores import NoAutenticado, Prohibido


def _secreto() -> str:
    valor = os.environ.get("JWT_SECRETO")
    if not valor:
        raise RuntimeError("Define JWT_SECRETO (el mismo en todos los servicios)")
    if len(valor) < 32:  # S8-06: una clave corta permitiría adivinar la firma de los tokens
        raise RuntimeError("JWT_SECRETO debe tener al menos 32 caracteres aleatorios")
    return valor


def _minutos() -> int:
    return int(os.environ.get("JWT_MINUTOS", 60))


@dataclass(frozen=True)
class Actor:
    id_usuario: int
    rol: str
    verificacion: str
    nombre: str = ""

    @property
    def verificado(self) -> bool:
        return self.verificacion == "APROBADA"


def emitir_token(actor: Actor) -> str:
    carga = {"sub": str(actor.id_usuario), "rol": actor.rol, "verificacion": actor.verificacion,
             "nombre": actor.nombre, "exp": datetime.now(UTC) + timedelta(minutes=_minutos())}
    return jwt.encode(carga, _secreto(), algorithm="HS256")


def leer_token(token: str) -> Actor:
    try:
        carga = jwt.decode(token, _secreto(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as error:
        raise NoAutenticado("La sesión venció; inicia sesión de nuevo") from error
    except jwt.InvalidTokenError as error:
        raise NoAutenticado("Token inválido") from error
    return Actor(int(carga["sub"]), carga["rol"], carga["verificacion"], carga.get("nombre", ""))


_bearer = HTTPBearer(auto_error=False)


def actor_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Actor:
    if cred is None:
        raise NoAutenticado("Debes iniciar sesión")
    return leer_token(cred.credentials)


def requiere_rol(*roles: str):
    def dependencia(actor: Actor = Depends(actor_actual)) -> Actor:
        if actor.rol not in roles:
            raise Prohibido("No tienes permiso para esta acción")
        return actor
    return dependencia


def requiere_verificado(*roles: str):
    """Regla de negocio 1: solo usuarios verificados publican, registran necesidades y reservan."""
    def dependencia(actor: Actor = Depends(requiere_rol(*roles))) -> Actor:
        if not actor.verificado:
            raise Prohibido("Tu cuenta aún no está verificada por un administrador")
        return actor
    return dependencia


def token_interno() -> str:
    valor = os.environ.get("TOKEN_INTERNO")
    if not valor:
        raise RuntimeError("Define TOKEN_INTERNO (el mismo en todos los servicios)")
    return valor


def requiere_servicio_interno(x_token_interno: str | None = Header(default=None)) -> None:
    if not x_token_interno or not hmac.compare_digest(x_token_interno, token_interno()):
        raise Prohibido("Ruta interna: solo acepta llamadas de otros servicios")
