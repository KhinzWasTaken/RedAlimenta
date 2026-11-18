"""20 reservas simultáneas de la misma donación contra el sistema desplegado (S6-08, D-02).

    python scripts/carga_reservas.py --base http://localhost:8080      (Compose)
    python scripts/carga_reservas.py --base http://localhost:30080     (Kubernetes)

Con varias réplicas de fulfillment detrás del gateway, exactamente una solicitud recibe 201 y las demás 409:
la garantía la da el índice único parcial de la base, no la memoria de una réplica.
"""
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e import Api, paso  # noqa: E402

SOLICITUDES = 20


def main(argv: list[str]) -> int:
    api = Api(argv[argv.index("--base") + 1] if "--base" in argv else "http://localhost:8080")

    def entrar(correo):
        return {"Authorization": "Bearer " + api("POST", "/api/auth/login",
                                                 json={"correo": correo, "contrasena": "demo123"}).json()["token"]}

    donante = entrar("donante.cali@redalimenta.co")
    receptores = [entrar("receptor.cali@redalimenta.co"), entrar("receptor.medellin@redalimenta.co")]
    donacion = api("POST", "/api/donaciones", donante, 201, json={
        "nombre_alimento": "Carga concurrente", "id_categoria": 4, "cantidad": 10, "unidad_medida": "kg",
        "fecha_vencimiento": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "ubicacion": {"lat": 3.45, "lon": -76.53, "ciudad": "Cali", "departamento": "Valle del Cauca"}}).json()
    barrera = threading.Barrier(SOLICITUDES)

    def reservar(i):
        barrera.wait()
        r = api("POST", "/api/reservas", receptores[i % 2], None, json={"id_donacion": donacion["id_donacion"]})
        return r.status_code, r.headers.get("X-Correlation-Id")

    with ThreadPoolExecutor(SOLICITUDES) as grupo:
        resultados = list(grupo.map(reservar, range(SOLICITUDES)))
    codigos = Counter(c for c, _ in resultados)
    print(f"Respuestas: {dict(codigos)}")
    assert codigos[201] == 1 and codigos[409] == SOLICITUDES - 1, codigos
    activas = [r for t in receptores for r in api("GET", "/api/reservas/mias", t).json()
               if r["id_donacion"] == donacion["id_donacion"] and r["estado_reserva"] in ("PENDIENTE", "CONFIRMADA")]
    assert len(activas) == 1, activas
    assert api("GET", f"/api/donaciones/{donacion['id_donacion']}", donante).json()["estado_donacion"] == "RESERVADA"
    paso(f"{SOLICITUDES} reservas simultáneas: una 201, {SOLICITUDES - 1} con 409 y una sola reserva activa")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
