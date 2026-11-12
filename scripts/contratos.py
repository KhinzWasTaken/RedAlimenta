"""Exporta los contratos OpenAPI de cada servicio a docs/contratos/openapi/<servicio>.yaml (S5-01).

    python scripts/contratos.py            regenera los archivos
    python scripts/contratos.py --revisar  falla si el código y los contratos guardados difieren

Los contratos salen del código de FastAPI; las rutas /internal se publican en un archivo aparte para dejar
claro que no pasan por el gateway.
"""
import json
import os
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "contratos" / "openapi"
RUTAS = json.loads((RAIZ / "infra" / "rutas.json").read_text(encoding="utf-8"))["servicios"]

os.environ.setdefault("EVENTOS_BACKEND", "memoria")
os.environ.setdefault("CONSUMIR_EVENTOS", "0")
for s in RUTAS.values():
    sys.path.insert(0, str(RAIZ / "services" / s["carpeta"]))


def contratos() -> dict[str, str]:
    salida = {}
    for nombre, s in RUTAS.items():
        app = __import__(f"{s['paquete']}.app", fromlist=["app"]).app
        esquema = app.openapi()
        publicas = {r: v for r, v in esquema["paths"].items() if not r.startswith("/internal")}
        internas = {r: v for r, v in esquema["paths"].items() if r.startswith("/internal")}
        salida[f"{s['carpeta']}.yaml"] = yaml.safe_dump({**esquema, "paths": publicas}, allow_unicode=True,
                                                        sort_keys=False)
        if internas:
            salida[f"{s['carpeta']}.interno.yaml"] = yaml.safe_dump(
                {**esquema, "info": {**esquema["info"], "title": esquema["info"]["title"] + " (interno)"},
                 "paths": internas}, allow_unicode=True, sort_keys=False)
    return salida


def main(argv: list[str]) -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    distintos = []
    for archivo, texto in contratos().items():
        ruta = DESTINO / archivo
        if "--revisar" in argv:
            if not ruta.exists() or ruta.read_text(encoding="utf-8") != texto:
                distintos.append(archivo)
        else:
            ruta.write_text(texto, encoding="utf-8")
            print(f"» {ruta.relative_to(RAIZ)}")
    if distintos:
        print("✗ El código cambió y los contratos no:", ", ".join(distintos))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
