"""Despliegue en Kubernetes local (S6-06 a S6-08): Docker Desktop con Kubernetes activado, o kind.

    python scripts/k8s.py imagenes      construye las 7 imágenes (y si hay un clúster kind, se las carga)
    python scripts/k8s.py desplegar     crea el Secret desde infra/.env, aplica infra/k8s y espera a que todo esté listo
    python scripts/k8s.py probar        prueba de extremo a extremo, 20 reservas contra 2 réplicas y borrado de un pod
    python scripts/k8s.py borrar        elimina el namespace redalimenta (incluidos los datos)

Requisitos: docker y kubectl apuntando al clúster (`kubectl config current-context`). Frontend en
http://localhost:30080 (NodePort del gateway; en kind, crea el clúster con scripts/kind.yaml).
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bd import _leer_env  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
NS = "redalimenta"
BASE = "http://localhost:30080"
RUTAS = json.loads((RAIZ / "infra" / "rutas.json").read_text(encoding="utf-8"))["servicios"]
SECRETOS = ("POSTGRES_PASSWORD", "APP_DB_PASSWORD", "RABBITMQ_USER", "RABBITMQ_PASSWORD", "JWT_SECRETO", "TOKEN_INTERNO")


def correr(*args, entrada: str | None = None, capturar: bool = False) -> str:
    print("»", " ".join(args))
    r = subprocess.run(args, input=entrada, text=True, check=True, capture_output=capturar)
    return r.stdout if capturar else ""


def kubectl(*args, **kw) -> str:
    return correr("kubectl", "-n", NS, *args, **kw)


def imagenes() -> None:
    construir = [(f"redalimenta/{n}:local", str(RAIZ / "services"), str(RAIZ / "services" / s["carpeta"] / "Dockerfile"))
                 for n, s in RUTAS.items()]
    construir += [("redalimenta/herramientas:local", str(RAIZ), str(RAIZ / "infra" / "herramientas" / "Dockerfile")),
                  ("redalimenta/gateway:local", str(RAIZ), str(RAIZ / "frontend" / "Dockerfile"))]
    for etiqueta, contexto, dockerfile in construir:
        correr("docker", "build", "-f", dockerfile, "-t", etiqueta, contexto)
    if shutil.which("kind") and "redalimenta" in correr("kind", "get", "clusters", capturar=True).split():
        for etiqueta, _, _ in construir:
            correr("kind", "load", "docker-image", "--name", "redalimenta", etiqueta)
        for externa in ("postgis/postgis:16-3.4", "rabbitmq:3.13-management"):
            correr("docker", "pull", externa)
            correr("kind", "load", "docker-image", "--name", "redalimenta", externa)


def desplegar() -> None:
    env = _leer_env()
    env.setdefault("RABBITMQ_USER", "redalimenta")
    faltan = [k for k in SECRETOS if not env.get(k)]
    if faltan:
        sys.exit(f"Faltan en infra/.env: {', '.join(faltan)}")
    correr("kubectl", "apply", "-f", str(RAIZ / "infra" / "k8s" / "namespace.yaml"))
    # Secret y script de inicio de PostgreSQL: se generan aquí para no guardar secretos en el repositorio
    secreto = correr("kubectl", "-n", NS, "create", "secret", "generic", "redalimenta-secretos",
                     *[f"--from-literal={k}={env[k]}" for k in SECRETOS], "--dry-run=client", "-o", "yaml",
                     capturar=True)
    kubectl("apply", "-f", "-", entrada=secreto)
    init = kubectl("create", "configmap", "postgres-init",
                   f"--from-file={RAIZ / 'infra' / 'postgres' / 'init' / '01-bases.sh'}", "--dry-run=client",
                   "-o", "yaml", capturar=True)
    kubectl("apply", "-f", "-", entrada=init)
    kubectl("delete", "job", "migraciones", "--ignore-not-found")
    correr("kubectl", "apply", "-k", str(RAIZ / "infra" / "k8s"))
    kubectl("rollout", "status", "statefulset/postgres", "--timeout=300s")
    kubectl("rollout", "status", "deployment/rabbitmq", "--timeout=300s")
    kubectl("wait", "--for=condition=complete", "job/migraciones", "--timeout=300s")
    for nombre in (*RUTAS, "gateway"):
        kubectl("rollout", "status", f"deployment/{nombre}", "--timeout=300s")
    kubectl("get", "pods", "-o", "wide")
    print(f"\n✓ RedAlimenta en {BASE}")


def probar() -> None:
    correr(sys.executable, str(RAIZ / "scripts" / "e2e.py"), "--base", BASE)
    correr(sys.executable, str(RAIZ / "scripts" / "carga_reservas.py"), "--base", BASE)
    # S6-08: al borrar un pod, el servicio sigue respondiendo gracias a la otra réplica
    pods = kubectl("get", "pods", "-l", "app=catalog", "-o", "jsonpath={.items[0].metadata.name}", capturar=True)
    kubectl("delete", "pod", pods, "--wait=false")
    import httpx
    fallos = 0
    for _ in range(30):
        try:
            fallos += httpx.get(f"{BASE}/api/categorias", timeout=5).status_code not in (200, 401)
        except httpx.HTTPError:
            fallos += 1
        time.sleep(0.3)
    print(f"Solicitudes fallidas mientras se reemplazaba el pod de catalog: {fallos} de 30")
    kubectl("rollout", "status", "deployment/catalog", "--timeout=180s")
    kubectl("get", "cronjob,jobs")


def main(argv: list[str]) -> int:
    acciones = {"imagenes": imagenes, "desplegar": desplegar, "probar": probar,
                "borrar": lambda: correr("kubectl", "delete", "namespace", NS, "--ignore-not-found")}
    if not argv or argv[0] not in acciones:
        print(__doc__)
        return 2
    acciones[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
