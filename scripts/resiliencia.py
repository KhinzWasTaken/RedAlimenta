"""Prueba de resiliencia entre servicios (S6-04) sobre el sistema en Docker Compose.

    python scripts/resiliencia.py            (con `docker compose ... --profile app up -d` corriendo)

Apaga catalog-geo y comprueba que reservar responde un error claro (503) sin dejar reservas huérfanas,
que el resto del sistema sigue atendiendo, y que al volver catalog la reserva funciona.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e import Api, paso  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(RAIZ / "infra" / "docker-compose.yml"), "--env-file",
           str(RAIZ / "infra" / ".env"), "--profile", "app"]


def compose(*args: str) -> str:
    return subprocess.run([*COMPOSE, *args], check=True, capture_output=True, text=True).stdout


def reservas_activas(id_donacion: int) -> int:
    salida = compose("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "redalimenta_fulfillment", "-Atc",
                     "SELECT count(*) FROM reserva WHERE estado_reserva IN ('PENDIENTE','CONFIRMADA') "
                     f"AND id_donacion = {int(id_donacion)}")
    return int(salida.strip())


def main(argv: list[str]) -> int:
    base = argv[argv.index("--base") + 1] if "--base" in argv else "http://localhost:8080"
    api = Api(base)
    sesion = api("POST", "/api/auth/login", json={"correo": "receptor.medellin@redalimenta.co",
                                                  "contrasena": "demo123"}).json()
    receptor = {"Authorization": f"Bearer {sesion['token']}"}
    donacion = 13  # Fríjol cargamanto (Medellín), DISPONIBLE en los datos semilla
    print("Resiliencia: catalog-geo caído")
    compose("stop", "catalog")
    try:
        inicio = time.perf_counter()
        r = api("POST", "/api/reservas", receptor, None, json={"id_donacion": donacion})
        demora = time.perf_counter() - inicio
        assert r.status_code == 503, (r.status_code, r.text)
        paso(f"reservar responde 503 en {demora:.1f} s: «{r.json()['detail']}»")
        assert reservas_activas(donacion) == 0
        paso("no quedó ninguna reserva activa huérfana")
        assert api("GET", "/api/notificaciones", receptor).status_code == 200
        paso("los demás servicios siguen atendiendo (notificaciones)")
    finally:
        compose("start", "catalog")
    for _ in range(40):
        if api("GET", "/api/categorias", receptor, None).status_code == 200:
            break
        time.sleep(1)
    r = api("POST", "/api/reservas", receptor, 201, json={"id_donacion": donacion})
    assert reservas_activas(donacion) == 1
    paso(f"con catalog de vuelta la reserva funciona (reserva {r.json()['id_reserva']})")
    print("\n✓ Resiliencia correcta")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
