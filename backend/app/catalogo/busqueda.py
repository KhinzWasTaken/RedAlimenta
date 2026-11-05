"""Distancia (Haversine) y puntaje de prioridad (D-08). Funciones puras."""
from math import asin, cos, radians, sin, sqrt

from app.core import config

RADIO_TIERRA_KM = 6371.0088
VALOR_URGENCIA = {"BAJA": 0.25, "MEDIA": 0.5, "ALTA": 0.75, "CRITICA": 1.0}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(sqrt(a))


def puntaje(nivel_urgencia: str | None, distancia_km: float, horas_para_vencer: float,
            radio_km: float | None = None) -> dict:
    """Puntaje = 0,40·urgencia + 0,35·cercanía + 0,25·proximidad del vencimiento (cada término 0–1)."""
    radio = radio_km or config.RADIO_KM_DEFECTO
    urgencia = VALOR_URGENCIA.get(nivel_urgencia or "", 0.0)
    cercania = 1 - min(max(distancia_km, 0) / radio, 1)
    vencimiento = 1 - min(max(horas_para_vencer, 0) / config.VENTANA_VENCIMIENTO_HORAS, 1)
    total = (config.PESO_URGENCIA * urgencia + config.PESO_CERCANIA * cercania
             + config.PESO_VENCIMIENTO * vencimiento)
    return {
        "puntaje": round(total, 4),
        "urgencia": round(urgencia, 4),
        "cercania": round(cercania, 4),
        "vencimiento": round(vencimiento, 4),
    }
