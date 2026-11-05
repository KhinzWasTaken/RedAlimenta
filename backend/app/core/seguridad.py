"""Contraseñas con PBKDF2 y JWT con id_usuario, rol y verificación (D-06)."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

ITERACIONES = 120_000


def hash_contrasena(contrasena: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal}${digest.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, iteraciones, sal, digest = guardado.split("$")
    except ValueError:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), int(iteraciones))
    return hmac.compare_digest(calculado.hex(), digest)


@dataclass
class Actor:
    id_usuario: int
    rol: str
    verificacion: str
    nombre: str

    @property
    def verificado(self) -> bool:
        return self.verificacion == "APROBADA"


def emitir_token(actor: Actor) -> str:
    carga = {
        "sub": str(actor.id_usuario),
        "rol": actor.rol,
        "verificacion": actor.verificacion,
        "nombre": actor.nombre,
        "exp": datetime.now(UTC) + timedelta(minutes=config.JWT_MINUTOS),
    }
    return jwt.encode(carga, config.JWT_SECRETO, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def actor_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Actor:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Debes iniciar sesión")
    try:
        carga = jwt.decode(cred.credentials, config.JWT_SECRETO, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión venció; inicia sesión de nuevo")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")
    return Actor(int(carga["sub"]), carga["rol"], carga["verificacion"], carga.get("nombre", ""))


def requiere_rol(*roles: str):
    def dependencia(actor: Actor = Depends(actor_actual)) -> Actor:
        if actor.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción")
        return actor

    return dependencia


def requiere_verificado(*roles: str):
    """Rol permitido y cuenta verificada (regla de negocio 1)."""

    def dependencia(actor: Actor = Depends(requiere_rol(*roles))) -> Actor:
        if not actor.verificado:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Tu cuenta aún no está verificada por un administrador",
            )
        return actor

    return dependencia
