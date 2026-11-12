"""analytics-service · `uvicorn analitica.app:app --port 8005`"""
from redalimenta_comun.app import crear_app

from .consumidor import consumidores
from .db import sesiones
from .rutas import rutas

app = crear_app("analytics-service", [rutas], sesiones, consumidores,
                "Historial inmutable de eventos y trazabilidad (RF10). Indicadores y reportes en los "
                "Sprints 7 y 8 (RF9).")
