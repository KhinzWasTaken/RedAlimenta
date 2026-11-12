"""Levanta RedAlimenta completo en una máquina (Sprint 5, antes de Docker y Kubernetes).

    python scripts/levantar.py               PostgreSQL + RabbitMQ (Docker), migraciones, 5 servicios y frontend
    python scripts/levantar.py --reiniciar   además borra los datos y vuelve a sembrar (demo desde cero)
    python scripts/levantar.py --sin-frontend

Cada servicio corre con su propio rol de base de datos (mínimo privilegio) y los secretos de infra/.env.
Frontend: http://localhost:5173 · APIs: http://localhost:8001..8005/docs · RabbitMQ: http://localhost:15672
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bd import RAIZ, _leer_env  # noqa: E402
from bd import main as bd  # noqa: E402

RUTAS = json.loads((RAIZ / "infra" / "rutas.json").read_text(encoding="utf-8"))["servicios"]


def entorno_servicio(nombre: str, env: dict) -> dict:
    base = {**os.environ, **env}
    host = env.get("PGHOST", "localhost")
    base.update({
        "DATABASE_URL": (f"postgresql+psycopg://{nombre}_app:{env['APP_DB_PASSWORD']}@{host}:"
                         f"{env.get('POSTGRES_PORT', 5432)}/redalimenta_{nombre}"),
        "RABBITMQ_URL": (f"amqp://{env.get('RABBITMQ_USER', 'redalimenta')}:{env['RABBITMQ_PASSWORD']}@{host}:"
                         f"{env.get('RABBITMQ_PORT', 5672)}/%2F"),
        "CATALOG_URL": f"http://localhost:{RUTAS['catalog']['puerto']}",
        "MODO_DEMO": env.get("MODO_DEMO", "1"),
        "PYTHONUNBUFFERED": "1",
    })
    return base


def main(argv: list[str]) -> int:
    env = _leer_env()
    faltan = [k for k in ("POSTGRES_PASSWORD", "APP_DB_PASSWORD", "RABBITMQ_PASSWORD", "JWT_SECRETO", "TOKEN_INTERNO")
              if not env.get(k)]
    if faltan:
        sys.exit(f"Faltan en infra/.env: {', '.join(faltan)} (copia infra/.env.example)")

    if shutil.which("docker") and "--sin-docker" not in argv:
        print("» Levantando PostgreSQL y RabbitMQ…")
        subprocess.run(["docker", "compose", "-f", str(RAIZ / "infra" / "docker-compose.yml"), "--env-file",
                        str(RAIZ / "infra" / ".env"), "up", "-d", "--wait", "postgres", "rabbitmq"], check=True)
    bd(["reiniciar"] if "--reiniciar" in argv else ["migrar"])
    if "--reiniciar" not in argv:
        bd(["sembrar"])

    procesos = []
    for nombre, s in RUTAS.items():
        print(f"» {s['carpeta']} en http://localhost:{s['puerto']}/docs")
        procesos.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", f"{s['paquete']}.app:app", "--port", str(s["puerto"]), "--no-access-log"],
            cwd=RAIZ / "services" / s["carpeta"], env=entorno_servicio(nombre, env)))
    if "--sin-frontend" not in argv:
        npm = shutil.which("npm")
        if npm is None:
            print("! npm no está instalado: se omite el frontend")
        else:
            if not (RAIZ / "frontend" / "node_modules").exists():
                subprocess.run([npm, "install"], cwd=RAIZ / "frontend", check=True)
            procesos.append(subprocess.Popen([npm, "run", "dev"], cwd=RAIZ / "frontend"))
            print("» Frontend en http://localhost:5173")
    print("\nCtrl+C para detener todo.\n")
    try:
        while all(p.poll() is None for p in procesos):
            time.sleep(1)
        print("! Un proceso terminó; se detiene todo.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procesos:
            if p.poll() is None:
                p.send_signal(signal.SIGINT) if os.name != "nt" else p.terminate()
        for p in procesos:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
