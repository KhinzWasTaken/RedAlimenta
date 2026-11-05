"""Enumeraciones (D-03) y transiciones permitidas (docs/modelo/estados.md)."""
from .errores import TransicionInvalida

ROLES = ("DONANTE", "RECEPTOR", "ADMINISTRADOR")
ESTADOS_CUENTA = ("ACTIVA", "DESACTIVADA")
ESTADOS_VERIFICACION = ("PENDIENTE", "APROBADA", "RECHAZADA")
ESTADOS_DONACION = ("DISPONIBLE", "RESERVADA", "ENTREGADA", "CANCELADA", "VENCIDA")
ESTADOS_NECESIDAD = ("ABIERTA", "CERRADA", "CANCELADA")
ESTADOS_RESERVA = ("PENDIENTE", "CONFIRMADA", "EXPIRADA", "COMPLETADA", "CANCELADA")
ESTADOS_ENTREGA = ("PROGRAMADA", "COMPLETADA", "CON_INCIDENCIA", "CANCELADA")
ESTADOS_CONFIRMACION = ("CONFIRMADA", "CON_INCIDENCIA")
ESTADOS_NOTIFICACION = ("NO_LEIDA", "LEIDA", "ARCHIVADA")
NIVELES_URGENCIA = ("BAJA", "MEDIA", "ALTA", "CRITICA")

TRANSICIONES: dict[str, dict[str, set[str]]] = {
    "verificacion": {"PENDIENTE": {"APROBADA", "RECHAZADA"}},
    "donacion": {
        "DISPONIBLE": {"RESERVADA", "CANCELADA", "VENCIDA"},
        "RESERVADA": {"DISPONIBLE", "VENCIDA", "ENTREGADA"},
    },
    "reserva": {
        "PENDIENTE": {"CONFIRMADA", "EXPIRADA", "CANCELADA"},
        "CONFIRMADA": {"COMPLETADA", "CANCELADA"},
    },
    "entrega": {
        "PROGRAMADA": {"COMPLETADA", "CON_INCIDENCIA", "CANCELADA"},
        "CON_INCIDENCIA": {"CANCELADA"},
    },
    "necesidad": {"ABIERTA": {"CERRADA", "CANCELADA"}},
    "notificacion": {"NO_LEIDA": {"LEIDA", "ARCHIVADA"}, "LEIDA": {"ARCHIVADA"}},
}


def es_valida(entidad: str, actual: str, nuevo: str) -> bool:
    return nuevo in TRANSICIONES[entidad].get(actual, set())


def validar(entidad: str, actual: str, nuevo: str) -> None:
    if not es_valida(entidad, actual, nuevo):
        raise TransicionInvalida(f"Transición no permitida para {entidad}: {actual} → {nuevo}")


def check_sql(columna: str, valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})"
