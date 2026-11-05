"""Configuración por variables de entorno (sin secretos en el repositorio)."""
import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
RAIZ_REPO = BACKEND_DIR.parent


def _float(nombre: str, defecto: float) -> float:
    return float(os.environ.get(nombre, defecto))


DB_URL = os.environ.get("REDALIMENTA_DB_URL", f"sqlite:///{BACKEND_DIR / 'redalimenta.db'}")

# Si no se define, se genera una clave aleatoria por proceso: los tokens dejan de valer al reiniciar.
JWT_SECRETO = os.environ.get("REDALIMENTA_JWT_SECRETO") or secrets.token_urlsafe(48)
JWT_MINUTOS = int(os.environ.get("REDALIMENTA_JWT_MINUTOS", 60))

# D-09
PLAZO_RESERVA_HORAS = _float("REDALIMENTA_PLAZO_RESERVA_HORAS", 2)
AVISO_VENCER_HORAS = _float("REDALIMENTA_AVISO_VENCER_HORAS", 24)

# D-08 (pesos y normalización)
PESO_URGENCIA = _float("REDALIMENTA_PESO_URGENCIA", 0.40)
PESO_CERCANIA = _float("REDALIMENTA_PESO_CERCANIA", 0.35)
PESO_VENCIMIENTO = _float("REDALIMENTA_PESO_VENCIMIENTO", 0.25)
RADIO_KM_DEFECTO = _float("REDALIMENTA_RADIO_KM", 20)
VENTANA_VENCIMIENTO_HORAS = _float("REDALIMENTA_VENTANA_VENCIMIENTO_HORAS", 168)

# Planificador interno de tareas (RF8) y botón de demo "forzar expiración"
PLANIFICADOR_ACTIVO = os.environ.get("REDALIMENTA_PLANIFICADOR", "1") == "1"
PLANIFICADOR_SEGUNDOS = int(os.environ.get("REDALIMENTA_PLANIFICADOR_SEGUNDOS", 60))
MODO_DEMO = os.environ.get("REDALIMENTA_MODO_DEMO", "1") == "1"

FRONTEND_DIST = Path(os.environ.get("REDALIMENTA_FRONTEND_DIST", RAIZ_REPO / "frontend" / "dist"))
