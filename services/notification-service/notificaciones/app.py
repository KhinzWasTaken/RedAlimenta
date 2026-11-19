"""notification-service · `uvicorn notificaciones.app:app --port 8004`"""
from redalimenta_comun.app import crear_app

from .consumidor import consumidores
from .db import sesiones
from .rutas import rutas, rutas_chat

app = crear_app("notification-service", [rutas, rutas_chat], sesiones, consumidores,
                "Bandeja de notificaciones in-app generada a partir de los eventos (RF7) y chat entre donante y receptor (D-12).")
