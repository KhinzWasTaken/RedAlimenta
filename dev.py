"""Modo desarrollo: backend con recarga automática (:8000) y Vite con recarga en caliente (:5173).

    python dev.py               abre http://localhost:5173 (Vite reenvía /api al backend)
    python dev.py --reiniciar   borra y vuelve a sembrar la base antes de arrancar
"""
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"


def main() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("No se encontró npm. Instala Node.js 18+.")
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)

    semilla = [sys.executable, "-m", "app.seed"] + (["--reiniciar"] if "--reiniciar" in sys.argv else [])
    subprocess.run(semilla, cwd=BACKEND, check=True)

    procesos = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], cwd=BACKEND),
        subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND),
    ]
    print("\n» Backend http://localhost:8000/docs · Frontend http://localhost:5173  (Ctrl+C para detener)\n")
    try:
        for p in procesos:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procesos:
            p.terminate()


if __name__ == "__main__":
    main()
