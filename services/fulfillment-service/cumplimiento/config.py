"""Plazos automáticos (D-09), configurables por variables de entorno."""
import os

PLAZO_RESERVA_HORAS = float(os.environ.get("PLAZO_RESERVA_HORAS", 2))
AVISO_POR_VENCER_HORAS = float(os.environ.get("AVISO_POR_VENCER_HORAS", 24))
