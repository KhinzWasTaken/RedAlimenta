"""ETL del almacén de datos (Sprint 7).

    python scripts/etl.py cargar completa      sintéticos + bases transaccionales + eventos (primera vez)
    python scripts/etl.py cargar historica     copia fresca de las bases transaccionales (solo lectura)
    python scripts/etl.py cargar eventos       carga continua desde el historial de eventos (incremental)
    python scripts/etl.py cargar sintetica [--n 50000]   regenera los datos sintéticos (semilla fija)
    python scripts/etl.py informe              escribe docs/dwh/informe-calidad.md con la última carga
    python scripts/etl.py indicadores          imprime los indicadores principales (RF9)

Conexiones: DWH_DATABASE_URL y FUENTE_<BASE>_URL si existen; si no, se arman con infra/.env usando el rol
del ETL (dwh_app) para escribir en el almacén y el rol de solo lectura (dwh_lector) para leer las fuentes.
"""
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dwh"))
sys.path.insert(0, str(RAIZ / "services" / "analytics-service"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

from almacen import calidad  # noqa: E402
from almacen.cargar import cargar  # noqa: E402
from analitica import indicadores  # noqa: E402
from bd import _leer_env  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
FUENTES = ("identity", "catalog", "fulfillment", "analytics")


def _url(base: str, usuario: str) -> str:
    env = {**_leer_env(), **{k: v for k, v in os.environ.items() if k.startswith(("POSTGRES_", "PGHOST", "APP_DB"))}}
    return URL.create("postgresql+psycopg", username=usuario, password=env.get("APP_DB_PASSWORD"),
                      host=env.get("PGHOST", "localhost"), port=int(env.get("POSTGRES_PORT", 5432)),
                      database=base).render_as_string(hide_password=False)


def url_dwh() -> str:
    return os.environ.get("DWH_DATABASE_URL") or _url("redalimenta_dwh", "dwh_app")


def urls_fuentes() -> dict[str, str]:
    return {f: os.environ.get(f"FUENTE_{f.upper()}_URL") or _url(f"redalimenta_{f}", "dwh_lector") for f in FUENTES}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("cargar", "informe", "indicadores"):
        print(__doc__)
        return 2
    motor = create_engine(url_dwh())
    if argv[0] == "cargar":
        tipo = argv[1] if len(argv) > 1 else "completa"
        n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 50_000
        resultado = cargar(motor, tipo, urls_fuentes(), n_sinteticas=n)
        print(json.dumps({k: v for k, v in resultado.items() if k != "calidad"}, ensure_ascii=False, indent=2))
        fallidas = [r["regla"] for r in resultado["calidad"] if not r["aprobada"]]
        print("✓ Calidad: todas las reglas aprobadas" if not fallidas else f"✗ Calidad: fallan {fallidas}")
        return 1 if fallidas else 0
    with motor.connect() as c:
        if argv[0] == "informe":
            ultima = c.execute(text("SELECT id_ejecucion, tipo, fin, filas FROM etl.ejecucion WHERE estado = "
                                    "'EXITOSA' ORDER BY id_ejecucion DESC LIMIT 1")).mappings().first()
            if ultima is None:
                sys.exit("No hay cargas exitosas todavía")
            resultados = [dict(f) for f in c.execute(text(
                "SELECT regla, descripcion, filas_con_problema, aprobada FROM etl.resultado_calidad "
                "WHERE id_ejecucion = :e ORDER BY id_resultado"), {"e": ultima["id_ejecucion"]}).mappings()]
            destino = RAIZ / "docs" / "dwh" / "informe-calidad.md"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(calidad.informe_markdown(resultados, {
                "id_ejecucion": ultima["id_ejecucion"], "tipo": ultima["tipo"],
                "fecha": ultima["fin"].isoformat(timespec="seconds"), "filas": ultima["filas"]}), encoding="utf-8")
            print(f"» {destino.relative_to(RAIZ)}")
            return 0
        f = indicadores.Filtros(date(2025, 1, 1), date.today())
        for nombre in indicadores.INDICADORES:
            serie = indicadores.serie(c, nombre, f, "anio")
            print(f"{nombre}: " + ", ".join(f"{p['periodo'].year}={p['valor']:g}" for p in serie))
        print("volumen entregado:", ", ".join(f"{v['cantidad']:.0f} {v['unidad_medida']}"
                                             for v in indicadores.volumen_distribuido(c, f)))
        print("cobertura (5 primeras):", ", ".join(f"{r['ciudad']} {r['donaciones']} ({r['tasa_entrega']:.0%})"
                                                  for r in indicadores.cobertura(c, f)[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
