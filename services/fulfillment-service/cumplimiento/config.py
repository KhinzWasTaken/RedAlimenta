"""Plazos automáticos (D-09), configurables por variables de entorno."""
import os

PLAZO_RESERVA_HORAS = float(os.environ.get("PLAZO_RESERVA_HORAS", 2))
AVISO_POR_VENCER_HORAS = float(os.environ.get("AVISO_POR_VENCER_HORAS", 24))
TAREAS_SEGUNDOS = int(os.environ.get("TAREAS_SEGUNDOS", 60))  # 0 = sin planificador interno (CronJob en Sprint 6)
MODO_DEMO = os.environ.get("MODO_DEMO", "0") == "1"  # habilita el botón "forzar expiración"
