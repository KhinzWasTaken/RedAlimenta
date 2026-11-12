"""catalog-geo-service · `uvicorn catalogo.app:app --port 8002`"""
from redalimenta_comun.app import crear_app

from .db import sesiones
from .rutas import internas, rutas

app = crear_app("catalog-geo-service", [rutas, internas], sesiones, None,
                "Donaciones, necesidades, búsqueda geoespacial con prioridad (RF2, RF3, RF4) y "
                "transiciones de estado de la donación para otros servicios (D-01).")
