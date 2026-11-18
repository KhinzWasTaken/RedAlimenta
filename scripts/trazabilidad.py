"""Verifica la matriz de trazabilidad (S8-07): cada prueba citada en docs/trazabilidad.md existe.

    python scripts/trazabilidad.py             comprueba que existan (rápido, sin base de datos)
    python scripts/trazabilidad.py --ejecutar  además corre exactamente esas pruebas contra PostgreSQL
"""
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bd import url  # noqa: E402

from sqlalchemy.engine import make_url  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CARPETAS = {"identity": "services/identity-service", "catalog": "services/catalog-geo-service",
            "fulfillment": "services/fulfillment-service", "notification": "services/notification-service",
            "analytics": "services/analytics-service", "dwh": "dwh"}
REFERENCIA = re.compile(r"`(\w+)/(test_\w+)::(test_\w+)`")


def main(argv: list[str]) -> int:
    texto = (RAIZ / "docs" / "trazabilidad.md").read_text(encoding="utf-8")
    referencias = sorted(set(REFERENCIA.findall(texto)))
    faltan, por_carpeta = [], defaultdict(set)
    for servicio, archivo, prueba in referencias:
        ruta = RAIZ / CARPETAS[servicio] / "tests" / f"{archivo}.py"
        if not ruta.exists() or not re.search(rf"^def {prueba}\(", ruta.read_text(encoding="utf-8"), re.M):
            faltan.append(f"{servicio}/{archivo}::{prueba}")
        else:
            por_carpeta[CARPETAS[servicio]].add(f"tests/{archivo}.py::{prueba}")
    filas = sum(1 for linea in texto.splitlines() if linea.startswith("| ") and not linea.startswith("| ---"))
    print(f"{len(referencias)} pruebas citadas en {filas} filas de la matriz")
    if faltan:
        print("✗ No existen:", *faltan, sep="\n  ")
        return 1
    print("✓ Todas las pruebas citadas existen")
    if "--ejecutar" in argv:
        entorno = dict(os.environ)
        entorno.setdefault("PRUEBAS_ADMIN_URL", make_url(url("identity")).set(database="postgres")
                           .render_as_string(hide_password=False))
        for carpeta, pruebas in sorted(por_carpeta.items()):
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sorted(pruebas)],
                               cwd=RAIZ / carpeta, env=entorno, capture_output=True, text=True)
            print(f"  {carpeta}: {r.stdout.strip().splitlines()[-1]}")
            if r.returncode:
                print(r.stdout[-2000:])
                return 1
        print("✓ Todas las pruebas de la matriz pasan")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
