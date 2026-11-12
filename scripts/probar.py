"""Ejecuta las pruebas de cada servicio contra PostgreSQL real.

    python scripts/probar.py                 todos los servicios
    python scripts/probar.py fulfillment     solo los servicios cuyo nombre contenga el texto

Usa PRUEBAS_ADMIN_URL si existe; si no, la arma con infra/.env (superusuario contra localhost).
Cada servicio crea y borra su propia base temporal, así que no toca los datos de las bases reales.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bd import RAIZ, SERVICIOS, url  # noqa: E402

from sqlalchemy.engine import make_url  # noqa: E402


def main(argv: list[str]) -> int:
    entorno = dict(os.environ)
    if "PRUEBAS_ADMIN_URL" not in entorno:
        entorno["PRUEBAS_ADMIN_URL"] = make_url(url("identity")).set(database="postgres").render_as_string(
            hide_password=False)
    filtro = argv[0] if argv else ""
    fallidos = []
    for _, carpeta, _ in SERVICIOS:
        if filtro not in carpeta:
            continue
        print(f"\n=== {carpeta} ===", flush=True)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                           cwd=RAIZ / "services" / carpeta, env=entorno)
        if r.returncode:
            fallidos.append(carpeta)
    print("\n" + ("✓ Todas las pruebas pasaron" if not fallidos else f"✗ Fallaron: {', '.join(fallidos)}"))
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
