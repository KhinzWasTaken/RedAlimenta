"""identity-service · `uvicorn identidad.app:app --port 8001`"""
from redalimenta_comun.app import crear_app

from .consumidor import consumidores
from .db import sesiones
from .rutas import rutas

app = crear_app("identity-service", [rutas], sesiones, consumidores,
                "Usuarios, autenticación JWT, verificación de cuentas y auditoría (RF1, RF10).")
