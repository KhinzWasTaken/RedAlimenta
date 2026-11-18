"""notification-service · `uvicorn notificaciones.app:app --port 8004`"""
from redalimenta_comun.app import crear_app

from .consumidor import consumidores
from .db import sesiones
from .rutas import rutas

app = crear_app("notification-service", [rutas], sesiones, consumidores,
                "Bandeja de notificaciones in-app generada a partir de los eventos (RF7).")
