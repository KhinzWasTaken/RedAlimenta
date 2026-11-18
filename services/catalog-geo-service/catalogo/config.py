"""Pesos y normalización de la prioridad (D-08), configurables por variables de entorno."""
import os


def _f(nombre: str, defecto: float) -> float:
    return float(os.environ.get(nombre, defecto))


PESO_URGENCIA = _f("PESO_URGENCIA", 0.40)
PESO_CERCANIA = _f("PESO_CERCANIA", 0.35)
PESO_VENCIMIENTO = _f("PESO_VENCIMIENTO", 0.25)
RADIO_M_DEFECTO = _f("RADIO_BUSQUEDA_M", 20_000)  # normaliza la cercanía y limita la búsqueda
VENTANA_VENCIMIENTO_H = _f("VENTANA_VENCIMIENTO_H", 168)  # a 7 días o más, la proximidad vale 0

VALOR_URGENCIA = {"BAJA": 0.25, "MEDIA": 0.5, "ALTA": 0.75, "CRITICA": 1.0}
