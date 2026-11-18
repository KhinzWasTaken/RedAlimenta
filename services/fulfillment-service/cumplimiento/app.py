"""fulfillment-service · `uvicorn cumplimiento.app:app --port 8003`"""
from redalimenta_comun.app import crear_app

from .db import sesiones
from .rutas import rutas
from .tareas import hilos

app = crear_app("fulfillment-service", [rutas], sesiones, hilos,
                "Reservas con control de concurrencia, entregas con confirmación bilateral y tareas "
                "automáticas (RF5, RF6, RF8).")
