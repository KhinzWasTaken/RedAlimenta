"""Doble de prueba de la API interna de catalog-geo-service.

Reproduce sus reglas (transiciones permitidas, 409 si es ilegal) para probar fulfillment en aislamiento.
La integración real entre los dos servicios la cubre la prueba de extremo a extremo (scripts/e2e.py).
"""
import threading
from datetime import UTC, datetime, timedelta

from cumplimiento.errores import NoEncontrado, ServicioNoDisponible, TransicionInvalida

TRANSICIONES = {"DISPONIBLE": {"RESERVADA", "CANCELADA", "VENCIDA"}, "RESERVADA": {"DISPONIBLE", "VENCIDA", "ENTREGADA"}}


class CatalogoFalso:
    def __init__(self):
        self._candado = threading.Lock()
        self.caido = False
        self.rechazar_transiciones = False
        self.transiciones: list[tuple[int, str]] = []
        vence = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        pronto = (datetime.now(UTC) + timedelta(hours=5)).isoformat()
        self.datos = {
            10: {"id_donacion": 10, "id_donante": 4, "nombre_alimento": "Fríjol", "estado_donacion": "DISPONIBLE",
                 "fecha_vencimiento": vence},
            11: {"id_donacion": 11, "id_donante": 4, "nombre_alimento": "Arepas", "estado_donacion": "DISPONIBLE",
                 "fecha_vencimiento": pronto},
            12: {"id_donacion": 12, "id_donante": 6, "nombre_alimento": "Plátano", "estado_donacion": "DISPONIBLE",
                 "fecha_vencimiento": vence},
        }

    def _vivo(self):
        if self.caido:
            raise ServicioNoDisponible("El catálogo no responde; intenta de nuevo en unos segundos")

    def donaciones(self, ids=None, id_donante=None, estado=None):
        self._vivo()
        return [dict(d) for d in self.datos.values()
                if (ids is None or d["id_donacion"] in ids) and (id_donante is None or d["id_donante"] == id_donante)
                and (estado is None or d["estado_donacion"] == estado)]

    def donacion(self, id_donacion):
        self._vivo()
        if id_donacion not in self.datos:
            raise NoEncontrado("Donación no encontrada")
        return dict(self.datos[id_donacion])

    def transicionar(self, id_donacion, estado, id_actor, datos=None):
        self._vivo()
        with self._candado:
            d = self.datos[id_donacion]
            if self.rechazar_transiciones or estado not in TRANSICIONES.get(d["estado_donacion"], set()):
                raise TransicionInvalida(f"Transición de donación no permitida: {d['estado_donacion']} → {estado}")
            anterior, d["estado_donacion"] = d["estado_donacion"], estado
            self.transiciones.append((id_donacion, estado))
            return {"estado_anterior": anterior, "donacion": dict(d)}

    def vencer(self):
        self._vivo()
        return []

    def por_vencer(self, horas):
        self._vivo()
        limite = datetime.now(UTC) + timedelta(hours=horas)
        return [dict(d) for d in self.datos.values() if d["estado_donacion"] in ("DISPONIBLE", "RESERVADA")
                and datetime.fromisoformat(d["fecha_vencimiento"]) <= limite]
