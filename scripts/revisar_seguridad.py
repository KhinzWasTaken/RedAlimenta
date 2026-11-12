"""Revisión automática de seguridad y datos personales (S8-06, Ley 1581 de 2012).

    python scripts/revisar_seguridad.py          revisa el repositorio y los contratos
    python scripts/revisar_seguridad.py --bases  además consulta el almacén (infra/.env): sin datos personales

Comprobaciones:
1. Ningún archivo .env real ni claves privadas en el repositorio; los secretos solo como variables.
2. Toda ruta de la API exige sesión (JWT) salvo las públicas a propósito; las internas exigen X-Token-Interno.
3. El almacén (y por tanto los reportes) no tiene columnas de datos personales.
4. Ninguna imagen (Dockerfile) define secretos.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
PUBLICAS = {("post", "/api/auth/login"), ("post", "/api/auth/registro"), ("get", "/salud"), ("get", "/vivo")}
DATOS_PERSONALES = {"nombre", "correo_electronico", "telefono", "contrasena_hash", "direccion_referencia"}
PATRONES_SECRETO = [
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "clave privada"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "clave de AWS"),
    (re.compile(r"(?i)(jwt_secreto|token_interno|password|contrase[nñ]a)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}"),
     "secreto con valor"),
]
PERMITIDOS = {"infra/.env.example"}  # plantilla con valores de ejemplo


def archivos() -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.split()


def revisar_repositorio(problemas: list[str]) -> None:
    for ruta in archivos():
        nombre = Path(ruta).name
        if (nombre == ".env" or nombre.endswith((".pem", ".key"))) and ruta not in PERMITIDOS:
            problemas.append(f"{ruta}: archivo de secretos versionado")
        if ruta in PERMITIDOS or ruta.endswith((".png", ".docx", "package-lock.json")):
            continue
        try:
            texto = (RAIZ / ruta).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for patron, tipo in PATRONES_SECRETO:
            if patron.search(texto):
                problemas.append(f"{ruta}: posible {tipo}")
        if nombre == "Dockerfile" and re.search(r"(?im)^\s*(ENV|ARG)\s+\S*(SECRETO|PASSWORD|TOKEN)\S*\s*=", texto):
            problemas.append(f"{ruta}: la imagen define un secreto")


def revisar_contratos(problemas: list[str]) -> int:
    revisadas = 0
    for archivo in sorted((RAIZ / "docs" / "contratos" / "openapi").glob("*.yaml")):
        esquema = yaml.safe_load(archivo.read_text(encoding="utf-8"))
        interno = archivo.name.endswith(".interno.yaml")
        for ruta, operaciones in esquema["paths"].items():
            for metodo, op in operaciones.items():
                revisadas += 1
                if interno:
                    cabeceras = {p.get("name", "").lower() for p in op.get("parameters", [])}
                    if "x-token-interno" not in cabeceras:
                        problemas.append(f"{archivo.name} {metodo.upper()} {ruta}: ruta interna sin X-Token-Interno")
                elif (metodo, ruta) not in PUBLICAS and not op.get("security"):
                    problemas.append(f"{archivo.name} {metodo.upper()} {ruta}: no exige sesión")
    return revisadas


def revisar_almacen(problemas: list[str]) -> None:
    sys.path.insert(0, str(RAIZ / "scripts"))
    from etl import url_dwh
    from sqlalchemy import create_engine, text
    motor = create_engine(url_dwh())
    with motor.connect() as c:
        columnas = {f[0] for f in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema IN ('dw', 'stg')"))}
    motor.dispose()
    for col in sorted(columnas & DATOS_PERSONALES):
        problemas.append(f"almacén: columna con dato personal «{col}»")


def main(argv: list[str]) -> int:
    problemas: list[str] = []
    revisar_repositorio(problemas)
    rutas = revisar_contratos(problemas)
    if "--bases" in argv:
        revisar_almacen(problemas)
    print(json.dumps({"archivos_revisados": len(archivos()), "operaciones_api_revisadas": rutas,
                      "problemas": problemas}, ensure_ascii=False, indent=2))
    print("✓ Sin hallazgos" if not problemas else f"✗ {len(problemas)} hallazgos")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
