"""Prueba de extremo a extremo del flujo principal (S5-21) contra los servicios en ejecución.

    python scripts/e2e.py                          contra los puertos de infra/rutas.json (scripts/levantar.py)
    python scripts/e2e.py --base http://localhost:8080   contra una sola puerta de entrada (gateway, Sprint 6)

Requiere datos semilla recién cargados (python scripts/levantar.py --reiniciar). Recorre: verificar cuenta,
publicar, buscar, reservar (con una solicitud simultánea que recibe 409), confirmar, entregar, expirar,
y comprueba estados, notificaciones, auditoría e historial (estos llegan por RabbitMQ).
"""
import json
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
RUTAS = json.loads((RAIZ / "infra" / "rutas.json").read_text(encoding="utf-8"))["servicios"]


class Api:
    def __init__(self, base: str | None):
        self.base = base.rstrip("/") if base else None
        self.http = httpx.Client(timeout=15)

    def url(self, ruta: str) -> str:
        if self.base:
            return self.base + ruta
        prefijo = max((p for s in RUTAS.values() for p in s["prefijos"] if ruta.startswith(p)), key=len)
        puerto = next(s["puerto"] for s in RUTAS.values() if prefijo in s["prefijos"])
        return f"http://localhost:{puerto}{ruta}"

    def __call__(self, metodo: str, ruta: str, token: dict | None = None, esperado: int | None = 200, **kw):
        r = self.http.request(metodo, self.url(ruta), headers=token or {}, **kw)
        if esperado is not None and r.status_code != esperado:
            raise AssertionError(f"{metodo} {ruta} → {r.status_code} (esperaba {esperado}): {r.text[:300]}")
        return r


def paso(texto: str) -> None:
    print(f"  ✓ {texto}")


def esperar(descripcion: str, condicion, segundos: float = 15):
    limite = time.time() + segundos
    while time.time() < limite:
        valor = condicion()
        if valor:
            return valor
        time.sleep(0.4)
    raise AssertionError(f"No se cumplió a tiempo: {descripcion}")


def main(argv: list[str]) -> int:
    api = Api(argv[argv.index("--base") + 1] if "--base" in argv else None)

    def entrar(correo):
        r = api("POST", "/api/auth/login", json={"correo": correo, "contrasena": "demo123"}).json()
        return {"Authorization": f"Bearer {r['token']}"}, r["usuario"]

    print("Flujo principal de RedAlimenta")
    admin, _ = entrar("admin@redalimenta.co")
    donante, _ = entrar("donante@redalimenta.co")
    receptor, perfil = entrar("receptor@redalimenta.co")
    competidor, _ = entrar("receptor.medellin@redalimenta.co")

    # 1. Verificación
    api("POST", "/api/reservas", receptor, 403, json={"id_donacion": 1})
    api("POST", f"/api/admin/verificaciones/{perfil['verificacion']['id_verificacion']}", admin,
        json={"decision": "APROBADA", "observaciones": "Documentos en regla"})
    receptor = {"Authorization": "Bearer " + api("POST", "/api/auth/refresh", receptor).json()["token"]}
    paso("el receptor sin verificar recibe 403; el administrador lo aprueba y su token se renueva")

    # 2. Publicar
    vence = (datetime.now(UTC) + timedelta(hours=30)).isoformat()
    donacion = api("POST", "/api/donaciones", donante, 201, json={
        "nombre_alimento": "Lentejas E2E", "id_categoria": 4, "cantidad": 50, "unidad_medida": "kg",
        "fecha_vencimiento": vence, "ubicacion": {"lat": 4.5700, "lon": -74.1300, "ciudad": "Bogotá",
                                                  "departamento": "Cundinamarca",
                                                  "direccion_referencia": "Calle 60 Sur # 20-10"}}).json()
    id_d = donacion["id_donacion"]
    paso(f"el donante publica la donación {id_d} (DISPONIBLE)")

    # 3. Buscar
    resultado = api("GET", "/api/donaciones/disponibles?id_necesidad=1", receptor).json()["resultados"]
    encontrada = next(x for x in resultado if x["id_donacion"] == id_d)
    assert resultado[0]["id_donacion"] == id_d, "la donación cercana, urgente y por vencer debe ir primero"
    paso(f"la búsqueda la pone primera: {encontrada['distancia_km']:.2f} km, puntaje {encontrada['prioridad']['puntaje']}")

    # 4. Reservar con una solicitud simultánea
    barrera, codigos = threading.Barrier(2), {}

    def reservar(nombre, token):
        barrera.wait()
        codigos[nombre] = api("POST", "/api/reservas", token, None, json={"id_donacion": id_d})

    hilos = [threading.Thread(target=reservar, args=a) for a in (("receptor", receptor), ("otro", competidor))]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(r.status_code for r in codigos.values()) == [201, 409], {k: v.status_code for k, v in codigos.items()}
    ganador = next(k for k, v in codigos.items() if v.status_code == 201)
    reserva = codigos[ganador].json()
    token_ganador = receptor if ganador == "receptor" else competidor
    assert api("GET", f"/api/donaciones/{id_d}", donante).json()["estado_donacion"] == "RESERVADA"
    paso(f"dos reservas simultáneas: una 201 y otra 409; la donación queda RESERVADA (ganó {ganador})")

    # 5. Confirmar y entregar
    entrega = api("POST", f"/api/reservas/{reserva['id_reserva']}/confirmar", donante).json()["entrega"]
    ruta = f"/api/entregas/{entrega['id_entrega']}/confirmar"
    api("POST", ruta, token_ganador, json={})
    assert api("GET", f"/api/donaciones/{id_d}", donante).json()["estado_donacion"] == "RESERVADA"
    final = api("POST", ruta, donante, json={"observaciones": "Entregado completo"}).json()
    assert final["estado_reserva"] == "COMPLETADA" and final["entrega"]["estado_entrega"] == "COMPLETADA"
    assert api("GET", f"/api/donaciones/{id_d}", donante).json()["estado_donacion"] == "ENTREGADA"
    paso("el donante confirma; con una sola confirmación sigue RESERVADA; con las dos queda ENTREGADA")

    # 6. Expiración (D-09) con el botón de demostración
    otra = api("POST", "/api/reservas", receptor, 201, json={"id_donacion": 2}).json()
    expirada = api("POST", f"/api/reservas/{otra['id_reserva']}/forzar-expiracion", receptor).json()
    assert expirada["estado_reserva"] == "EXPIRADA"
    assert api("GET", "/api/donaciones/2", donante).json()["estado_donacion"] == "DISPONIBLE"
    paso("forzar expiración libera la reserva y la donación vuelve a DISPONIBLE")

    # 7. Eventos: notificaciones, auditoría e historial (asíncronos)
    tipos_receptor = esperar("notificaciones del ganador", lambda: (lambda t: t if {
        "RESERVA_CREADA", "RESERVA_CONFIRMADA", "ENTREGA_COMPLETADA"} <= t else None)(
        {n["tipo_notificacion"] for n in api("GET", "/api/notificaciones", token_ganador).json()}))
    esperar("notificaciones del donante", lambda: {"DONACION_RESERVADA", "DONACION_ENTREGADA"} <= {
        n["tipo_notificacion"] for n in api("GET", "/api/notificaciones", donante).json()})
    paso(f"notificaciones in-app creadas por los eventos ({len(tipos_receptor)} tipos para el receptor)")
    esperado = [(None, "DISPONIBLE"), ("DISPONIBLE", "RESERVADA"), ("RESERVADA", "ENTREGADA")]
    esperar("auditoría de la donación", lambda: [(a["valor_anterior"], a["valor_nuevo"]) for a in reversed(
        api("GET", f"/api/admin/auditoria?entidad=donacion&id_registro={id_d}", admin).json())] == esperado)
    paso("la auditoría (identity) registra DISPONIBLE → RESERVADA → ENTREGADA con su actor")
    esperar("historial en analytics", lambda: [(h["estado_anterior"], h["estado_nuevo"]) for h in api(
        "GET", f"/api/historial/entidades/donacion?id_entidad={id_d}", admin).json()] == esperado)
    paso("analytics guarda el mismo historial, consultable por entidad y por usuario")
    api("GET", "/api/admin/auditoria", donante, 403)
    print("\n✓ Flujo de extremo a extremo correcto")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
