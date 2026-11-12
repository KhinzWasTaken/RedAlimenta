"""analytics-service · `uvicorn analitica.app:app --port 8005`"""
from redalimenta_comun.app import crear_app

from .consumidor import consumidores
from .db import sesiones
from .rutas import rutas, rutas_indicadores

app = crear_app("analytics-service", [rutas, rutas_indicadores], sesiones, consumidores,
                "Historial inmutable de eventos y trazabilidad (RF10); indicadores, cobertura y reportes "
                "CSV sobre el almacén de datos (RF9).")
