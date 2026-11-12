"""Cliente de la API interna de catalog-geo-service (D-01): única dependencia síncrona entre servicios.

Tiempo límite corto y reintentos acotados solo en lecturas; si catalog no responde se lanza
ServicioNoDisponible (503) para que el caso de uso compense y no deje reservas huérfanas.
"""
import os
import time

import httpx

from redalimenta_comun import correlacion
from redalimenta_comun.seguridad import token_interno

from .errores import Conflicto, NoEncontrado, ServicioNoDisponible, TransicionInvalida


class ClienteCatalogo:
    def __init__(self, url: str | None = None, cliente: httpx.Client | None = None, tiempo_limite: float = 3.0):
        self.url = (url or os.environ.get("CATALOG_URL", "http://localhost:8002")).rstrip("/")
        self._http = cliente or httpx.Client(timeout=tiempo_limite)

    def _pedir(self, metodo: str, ruta: str, reintentos: int = 1, **kwargs) -> httpx.Response:
        for intento in range(reintentos + 1):
            try:
                return self._http.request(metodo, f"{self.url}{ruta}", headers={"X-Token-Interno": token_interno(),
                                                   correlacion.CABECERA: correlacion.actual()},
                                          **kwargs)
            except httpx.HTTPError as error:
                if intento == reintentos:
                    raise ServicioNoDisponible("El catálogo no responde; intenta de nuevo en unos segundos") from error
                time.sleep(0.3 * (intento + 1))

    def donaciones(self, ids: list[int] | None = None, id_donante: int | None = None,
                   estado: str | None = None) -> list[dict]:
        if ids is not None and not ids:
            return []
        params = {}
        if ids is not None:
            params["ids"] = ",".join(str(i) for i in sorted(set(ids)))
        if id_donante is not None:
            params["id_donante"] = id_donante
        if estado:
            params["estado"] = estado
        r = self._pedir("GET", "/internal/donaciones", reintentos=2, params=params)
        r.raise_for_status()
        return r.json()

    def donacion(self, id_donacion: int) -> dict:
        lista = self.donaciones(ids=[id_donacion])
        if not lista:
            raise NoEncontrado("Donación no encontrada")
        return lista[0]

    def transicionar(self, id_donacion: int, estado: str, id_actor: int | None, datos: dict | None = None) -> dict:
        """Sin reintentos: una transición no es idempotente y un reintento podría aplicarla dos veces."""
        r = self._pedir("POST", f"/internal/donaciones/{id_donacion}/transiciones", reintentos=0,
                        json={"estado": estado, "id_actor": id_actor, "datos": datos or {}})
        if r.status_code == 409:
            raise TransicionInvalida(r.json().get("detail", "Transición rechazada por el catálogo"))
        if r.status_code == 404:
            raise NoEncontrado("Donación no encontrada")
        if r.status_code >= 400:
            raise Conflicto(r.json().get("detail", "El catálogo rechazó la operación"))
        return r.json()

    def vencer(self) -> list[int]:
        r = self._pedir("POST", "/internal/tareas/vencer", reintentos=0)
        r.raise_for_status()
        return r.json()["vencidas"]

    def por_vencer(self, horas: float) -> list[dict]:
        r = self._pedir("GET", "/internal/donaciones-por-vencer", reintentos=2, params={"horas": horas})
        r.raise_for_status()
        return r.json()


_cliente: ClienteCatalogo | None = None


def cliente_catalogo() -> ClienteCatalogo:
    global _cliente
    if _cliente is None:
        _cliente = ClienteCatalogo()
    return _cliente


def usar_cliente(nuevo) -> None:
    global _cliente
    _cliente = nuevo
